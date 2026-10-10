from datetime import datetime, time, timedelta
from decimal import Decimal
import csv
import json
import os
import urllib.parse
import urllib.request
from urllib.parse import unquote

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Min, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import (
    Contact, ContactStatusLog, Deal, EmailCampaign, EmailSend, Meeting, Note, Plan, SavedRecipient, Subscription,
    Unsubscribe,
)
from .forms import ContactForm, DealForm, NoteForm, MeetingForm, LeadsGeneratorForm, PlanForm, SubscriptionForm
from .services import (
    change_status, expire_one_week_prospects, merge_contacts, start_campaign, status_since_subquery,
)
from .reps import SESSION_KEY as REP_SESSION_KEY, active_reps, current_rep
from .utils import normalize_phone

PAGE_SIZE = 50
OPEN_DEAL_STAGES = ('prospecting', 'proposal', 'negotiation')


_COUNTRY_CONFIG = {
    'us': {'label': 'United States', 'gl': 'us'},
    'sa': {'label': 'South Africa', 'gl': 'za'},
}


def _leads_generator_fetch(*, keyword: str, state: str = '', city: str = '', max_results: int = 25, country: str = 'us', website_filter: str = 'no_website'):
    """
    Fetch businesses matching filters.

    website_filter:
      'no_website'   — only businesses without a website
      'any'          — all businesses regardless of website
      'with_website' — only businesses that have a website

    This is intentionally implemented as a provider hook. You need to decide which
    provider/API this project uses (the token must NOT be committed).

    Expected return format: list[dict] with keys:
      - name (str)
      - phone (str|None)
      - website (str|None)
      - address (str|None)
      - source_id (str|None) (provider id)
    """
    token = os.environ.get('LEADS_GENERATOR_API_TOKEN', '').strip()
    if not token:
        raise RuntimeError('LEADS_GENERATOR_API_TOKEN is not set')

    country_cfg = _COUNTRY_CONFIG.get(country) or _COUNTRY_CONFIG['us']

    q_parts = [keyword.strip()]
    if city.strip():
        q_parts.append(city.strip())
    if state.strip():
        q_parts.append(state.strip())
    q_parts.append(country_cfg['label'])
    query = ' '.join([p for p in q_parts if p])

    out = []
    seen = set()

    def _extract_website(result: dict) -> str:
        # SerpApi can put website at top-level or under links.website
        w = (result.get('website') or '').strip()
        if w:
            return w
        links = result.get('links') or {}
        if isinstance(links, dict):
            w2 = (links.get('website') or '').strip()
            if w2:
                return w2
        return ''

    # SerpApi Google Maps Local Results API:
    # https://serpapi.com/search?engine=google_maps&type=search&q=...
    # We paginate with start=0,20,40,... because "no website" listings often appear deeper.
    for start in (0, 20, 40, 60, 80, 100):
        if len(out) >= max_results:
            break

        params = {
            'engine': 'google_maps',
            'type': 'search',
            'q': query,
            'hl': 'en',
            'gl': country_cfg['gl'],
            'google_domain': 'google.com',
            'api_key': token,
            'start': start,
            'no_cache': 'true',
        }
        url = 'https://serpapi.com/search.json?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'User-Agent': 'crmtracker/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode('utf-8', errors='replace')
        data = json.loads(body)
        local_results = data.get('local_results') or []

        # If pagination isn't supported for this query without ll, SerpApi may return empty pages.
        # Don't fail; just stop early.
        if start > 0 and not local_results:
            break

        for r in local_results:
            if len(out) >= max_results:
                break

            website = _extract_website(r)
            if website_filter == 'no_website' and website:
                continue
            if website_filter == 'with_website' and not website:
                continue

            source_id = str(r.get('data_id') or r.get('place_id') or r.get('data_cid') or '').strip()
            if source_id and source_id in seen:
                continue
            if source_id:
                seen.add(source_id)

            title = (r.get('title') or '').strip()
            if not title:
                continue
            phone = (r.get('phone') or '').strip()
            if not phone:
                continue
            out.append({
                'name': title,
                'company': title,
                'phone': phone,
                'website': website,
                'address': (r.get('address') or '').strip(),
                'source_id': source_id,
            })

    return out


# ── Helpers ─────────────────────────────────────────────────────────────────

def _json_body(request):
    """Parse a JSON request body. Returns (data, error_response)."""
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        return None, JsonResponse({'error': 'Invalid JSON'}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse({'error': 'Invalid JSON'}, status=400)
    return data, None


def _paginate(request, queryset):
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return page, params.urlencode()


def _list_url_for(contact):
    if contact.status == 'inactive':
        return reverse('inactive_leads')
    if contact.pipeline == 'driveops':
        return reverse('driveops')
    return reverse('sa_leads' if contact.region == 'sa' else 'us_leads')


def _csv_cell(value):
    """Stringify for CSV; neutralise leading characters spreadsheets would run as a formula."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def _contacts_csv(queryset, filename):
    """Download the given contacts as CSV (Zoho/HubSpot-style list export)."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(['Name', 'Company', 'Phone', 'Email', 'Status', 'Lost reason', 'Pipeline', 'Region',
                     'Owner', 'Estimated value', 'Created'])
    for c in queryset.select_related('owner').iterator():
        writer.writerow([_csv_cell(v) for v in (
            c.name, c.company, c.phone, c.email, c.get_status_display(), c.get_lost_reason_display(),
            c.get_pipeline_display(), c.get_region_display(), c.owner.get_username() if c.owner else '',
            c.estimated_value, timezone.localtime(c.created_at).strftime('%Y-%m-%d'),
        )])
    return response


# ── Rep picker ──────────────────────────────────────────────────────────────

@require_POST
def choose_rep(request):
    """Set which rep is working in this browser. No password: this replaces the old logins."""
    rep = active_reps().filter(pk=request.POST.get('rep') or 0).first()
    if rep:
        request.session[REP_SESSION_KEY] = rep.pk
    else:
        request.session.pop(REP_SESSION_KEY, None)
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('dashboard')
    return redirect(next_url)


# ── Dashboard ───────────────────────────────────────────────────────────────

def dashboard(request):
    today = timezone.localdate()
    start_of_today = timezone.make_aware(datetime.combine(today, time.min))
    end_of_today = start_of_today + timedelta(days=1)

    deal_totals = Deal.objects.aggregate(
        total=Count('id'),
        open_value=Sum('value', filter=Q(stage__in=OPEN_DEAL_STAGES)),
        won_value=Sum('value', filter=Q(stage='won')),
    )
    stage_counts = dict(Deal.objects.values_list('stage').annotate(n=Count('id')).order_by())
    prospect_value = Contact.objects.filter(status='prospect').aggregate(total=Sum('estimated_value'))['total'] or 0

    rep = current_rep(request)
    my_meetings = Meeting.objects.filter(completed=False).select_related('contact')
    if rep and Contact.objects.filter(owner=rep).exists():
        my_meetings = my_meetings.filter(Q(contact__owner=rep) | Q(contact__owner__isnull=True))
    follow_ups = Contact.objects.filter(status__in=Contact.FOLLOW_UP_STATUSES)
    if rep:
        follow_ups = follow_ups.filter(owner=rep)

    return render(request, 'crm/dashboard.html', {
        'total_contacts': Contact.objects.exclude(status='inactive').count(),
        'total_deals': deal_totals['total'],
        'pipeline_value': (deal_totals['open_value'] or 0) + prospect_value,
        'won_value': deal_totals['won_value'] or 0,
        'stage_data': [(stage, stage_counts.get(stage, 0), label) for stage, label in Deal.STAGE_CHOICES],
        'recent_contacts': Contact.objects.all()[:5],
        'recent_deals': Deal.objects.select_related('contact')[:5],
        'todays_meetings': my_meetings.filter(scheduled_at__gte=start_of_today, scheduled_at__lt=end_of_today),
        'overdue_meetings': my_meetings.filter(scheduled_at__lt=start_of_today).order_by('-scheduled_at')[:10],
        'no_next_step_count': _without_next_step(follow_ups).count(),
    })


def _without_next_step(queryset):
    """Leads that need a follow-up but have no open meeting scheduled (Pipedrive's 'no next activity')."""
    return queryset.exclude(meetings__completed=False)


# ── Leads ───────────────────────────────────────────────────────────────────

def _filter_contacts(request, queryset):
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(company__icontains=q) | Q(phone__icontains=q)
        )
    if status:
        queryset = queryset.filter(status=status)
    return queryset, q, status


def contact_list(request):
    contacts, q, status = _filter_contacts(request, Contact.objects.annotate(deal_count=Count('deals')).order_by('-created_at'))
    return render(request, 'crm/contact_list.html', {
        'us_contacts': contacts.filter(region='us'),
        'sa_contacts': contacts.filter(region='sa'),
        'q': q,
        'status': status,
        'status_choices': Contact.STATUS_CHOICES,
    })


def _active_phone_duplicates(pipeline, region=None):
    """Active contacts in this pipeline (and region, if given) whose normalised phone matches another
    active contact in the same list, or any inactive contact (any region)."""
    active = Contact.objects.filter(pipeline=pipeline).exclude(status='inactive').exclude(phone_normalized='')
    if region:
        active = active.filter(region=region)
    inactive_phones = Contact.objects.filter(status='inactive').exclude(phone_normalized='').values('phone_normalized')
    repeated_phones = (
        active.values('phone_normalized').annotate(n=Count('id')).filter(n__gt=1).values('phone_normalized')
    )
    return active.filter(Q(phone_normalized__in=inactive_phones) | Q(phone_normalized__in=repeated_phones))


def _merge_phone_duplicates(pipeline, region=None):
    """Merge the duplicates found by _active_phone_duplicates. If an inactive contact has the phone it
    survives (the lead was already ruled out); otherwise the oldest active contact does. Notes, meetings
    and history from the others move onto the survivor. Returns how many contacts were merged away."""
    groups = {}
    for contact in _active_phone_duplicates(pipeline, region).order_by('created_at', 'pk'):
        groups.setdefault(contact.phone_normalized, []).append(contact)
    inactive_by_phone = {}
    for contact in Contact.objects.filter(status='inactive', phone_normalized__in=groups).order_by('-created_at'):
        inactive_by_phone[contact.phone_normalized] = contact  # oldest wins
    merged = 0
    for phone, contacts in groups.items():
        survivor = inactive_by_phone.get(phone) or contacts[0]
        merged += merge_contacts(survivor, contacts)
    return merged


def _merged_message(request, merged):
    messages.success(request, f'Merged {merged} duplicate lead{"" if merged == 1 else "s"} — notes and history were kept.')


def _region_leads(request, region):
    url_name = f'{region}_leads'
    if request.method == 'POST' and request.POST.get('action') == 'dedup_phones':
        _merged_message(request, _merge_phone_duplicates('general', region))
        return redirect(url_name)

    base = Contact.objects.filter(region=region, pipeline='general').exclude(status='inactive')
    contacts, q, status = _filter_contacts(request, base.select_related('owner').annotate(deal_count=Count('deals')).order_by('-created_at'))
    if request.GET.get('export') == 'csv':
        return _contacts_csv(contacts, f'{region}-leads.csv')
    page, querystring = _paginate(request, contacts)
    return render(request, 'crm/region_leads.html', {
        'contacts': page,
        'page_obj': page,
        'querystring': querystring,
        'q': q,
        'status': status,
        'status_choices': [c for c in Contact.STATUS_CHOICES if c[0] != 'inactive'],
        'region': region,
        'region_label': f'{region.upper()} Leads',
        'clear_url': url_name,
        'duplicate_phone_ids': set(_active_phone_duplicates('general', region).values_list('pk', flat=True)),
    })


def us_leads(request):
    return _region_leads(request, 'us')


def sa_leads(request):
    return _region_leads(request, 'sa')


def inactive_leads(request):
    contacts, q, _ = _filter_contacts(request, Contact.objects.filter(status='inactive').select_related('owner'))
    if request.GET.get('export') == 'csv':
        return _contacts_csv(contacts, 'inactive-leads.csv')
    page, querystring = _paginate(request, contacts)
    return render(request, 'crm/inactive_leads.html', {
        'contacts': page,
        'page_obj': page,
        'querystring': querystring,
        'q': q,
    })


def contact_detail(request, pk):
    contact = get_object_or_404(Contact.objects.select_related('owner'), pk=pk)
    note_form = NoteForm()
    if request.method == 'POST':
        note_form = NoteForm(request.POST)
        if note_form.is_valid():
            note = note_form.save(commit=False)
            note.contact = contact
            note.created_by = current_rep(request)
            note.save()
            return redirect('contact_detail', pk=pk)

    # Unified activity timeline (HubSpot-style): notes, status changes, meetings and emails.
    timeline = []
    for note in contact.notes.select_related('created_by'):
        timeline.append({'kind': 'note', 'at': note.created_at, 'obj': note})
    for log in contact.status_logs.select_related('changed_by'):
        timeline.append({
            'kind': 'status', 'at': log.changed_at, 'obj': log,
            'from_label': dict(Contact.STATUS_CHOICES).get(log.from_status, log.from_status),
            'to_label': dict(Contact.STATUS_CHOICES).get(log.to_status, log.to_status),
        })
    for meeting in contact.meetings.all():
        timeline.append({'kind': 'meeting', 'at': meeting.scheduled_at, 'obj': meeting})
    for send in contact.email_sends.select_related('campaign').exclude(status='pending'):
        timeline.append({'kind': 'email', 'at': send.sent_at or send.campaign.created_at, 'obj': send})
    timeline.sort(key=lambda item: item['at'], reverse=True)

    deals = list(contact.deals.all())
    return render(request, 'crm/contact_detail.html', {
        'contact': contact,
        'note_form': note_form,
        'timeline': timeline,
        'deals': deals,
        'upcoming_meetings': contact.meetings.filter(completed=False).order_by('scheduled_at'),
        'needs_follow_up': contact.status in Contact.FOLLOW_UP_STATUSES,
        'now': timezone.now(),
    })


def contact_create(request):
    initial = {'owner': current_rep(request)}
    region = request.GET.get('region')
    if region in ('us', 'sa'):
        initial['region'] = region
    if request.GET.get('pipeline') in dict(Contact.PIPELINE_CHOICES):
        initial['pipeline'] = request.GET['pipeline']
    form = ContactForm(request.POST or None, initial=initial)
    if form.is_valid():
        contact = form.save(commit=False)
        contact._changed_by = current_rep(request)
        contact.save()
        return redirect('contact_detail', pk=contact.pk)
    return render(request, 'crm/contact_form.html', {'form': form, 'title': 'Add Lead'})


def contact_edit(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    form = ContactForm(request.POST or None, instance=contact)
    if form.is_valid():
        contact = form.save(commit=False)
        contact._changed_by = current_rep(request)
        contact.save()
        return redirect('contact_detail', pk=pk)
    return render(request, 'crm/contact_form.html', {'form': form, 'title': 'Edit Lead', 'contact': contact})


def contact_delete(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    if request.method == 'POST':
        next_url = _list_url_for(contact)
        contact.delete()
        return redirect(next_url)
    return render(request, 'crm/contact_confirm_delete.html', {'contact': contact})


# ── Deals ───────────────────────────────────────────────────────────────────

def deal_list(request):
    deals = Deal.objects.select_related('contact').all()
    stage = request.GET.get('stage', '')
    q = request.GET.get('q', '')
    if stage:
        deals = deals.filter(stage=stage)
    if q:
        deals = deals.filter(Q(title__icontains=q) | Q(contact__name__icontains=q))
    return render(request, 'crm/deal_list.html', {
        'deals': deals,
        'stage': stage,
        'q': q,
        'stage_choices': Deal.STAGE_CHOICES,
    })


def deal_detail(request, pk):
    deal = get_object_or_404(Deal.objects.select_related('contact'), pk=pk)
    note_form = NoteForm()
    if request.method == 'POST':
        note_form = NoteForm(request.POST)
        if note_form.is_valid():
            note = note_form.save(commit=False)
            note.deal = deal
            note.created_by = current_rep(request)
            note.save()
            return redirect('deal_detail', pk=pk)
    return render(request, 'crm/deal_detail.html', {
        'deal': deal,
        'note_form': note_form,
    })


def deal_create(request):
    initial = {}
    if request.GET.get('contact', '').isdigit():
        initial['contact'] = request.GET['contact']
    form = DealForm(request.POST or None, initial=initial)
    if form.is_valid():
        deal = form.save()
        return redirect('deal_detail', pk=deal.pk)
    return render(request, 'crm/deal_form.html', {'form': form, 'title': 'Add Closed Deal'})


def deal_edit(request, pk):
    deal = get_object_or_404(Deal, pk=pk)
    form = DealForm(request.POST or None, instance=deal)
    if form.is_valid():
        form.save()
        return redirect('deal_detail', pk=pk)
    return render(request, 'crm/deal_form.html', {'form': form, 'title': 'Edit Closed Deal', 'deal': deal})


def deal_delete(request, pk):
    deal = get_object_or_404(Deal, pk=pk)
    if request.method == 'POST':
        deal.delete()
        return redirect('deal_list')
    return render(request, 'crm/deal_confirm_delete.html', {'deal': deal})


# ── Calendar ────────────────────────────────────────────────────────────────

def calendar_view(request):
    today = timezone.localdate()
    days = [today + timedelta(days=i) for i in range(5)]
    meetings = Meeting.objects.filter(
        scheduled_at__date__gte=today,
        scheduled_at__date__lte=days[-1],
        completed=False,
    ).select_related('contact')
    day_meetings = {d: [] for d in days}
    for m in meetings:
        day_meetings[timezone.localtime(m.scheduled_at).date()].append(m)

    # Past meetings (last 7 days) that were never completed, for rescheduling
    past_meetings = Meeting.objects.filter(
        scheduled_at__date__gte=today - timedelta(days=7),
        scheduled_at__date__lt=today,
        completed=False,
    ).select_related('contact').order_by('scheduled_at')

    return render(request, 'crm/calendar.html', {
        'day_data': [(d, day_meetings[d]) for d in days],
        'today': today,
        'past_meetings': past_meetings,
    })


def meeting_create(request):
    initial = {}
    date_str = request.GET.get('date', '')
    try:
        initial['scheduled_at'] = datetime.combine(datetime.strptime(date_str, '%Y-%m-%d').date(), time(9, 0))
    except ValueError:
        pass
    if request.GET.get('contact', '').isdigit():
        initial['contact'] = request.GET['contact']
    form = MeetingForm(request.POST or None, initial=initial)
    if form.is_valid():
        meeting = form.save()
        if request.GET.get('next') == 'contact':
            return redirect('contact_detail', pk=meeting.contact_id)
        return redirect('calendar')
    return render(request, 'crm/meeting_form.html', {'form': form, 'title': 'Log Meeting'})


def meeting_edit(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    form = MeetingForm(request.POST or None, instance=meeting)
    if form.is_valid():
        form.save()
        return redirect('calendar')
    return render(request, 'crm/meeting_form.html', {'form': form, 'title': 'Edit Meeting', 'meeting': meeting})


def meeting_delete(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if request.method == 'POST':
        meeting.delete()
        return redirect('calendar')
    return render(request, 'crm/meeting_confirm_delete.html', {'meeting': meeting})


@require_POST
def meeting_complete(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    meeting.completed = not meeting.completed
    meeting.save(update_fields=['completed'])
    return JsonResponse({'ok': True, 'completed': meeting.completed})


@require_POST
def meeting_reschedule(request, pk):
    meeting = get_object_or_404(Meeting.objects.select_related('contact'), pk=pk)
    data, error = _json_body(request)
    if error:
        return error
    target_date_str = data.get('date')
    if not target_date_str:
        return JsonResponse({'error': 'Missing date'}, status=400)
    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    local_dt = timezone.localtime(meeting.scheduled_at)
    meeting.scheduled_at = local_dt.replace(year=target_date.year, month=target_date.month, day=target_date.day)
    meeting.save(update_fields=['scheduled_at'])
    return JsonResponse({
        'ok': True,
        'pk': meeting.pk,
        'title': meeting.title,
        'time': timezone.localtime(meeting.scheduled_at).strftime('%H:%M'),
        'contact': meeting.contact.name,
        'phone': meeting.contact.phone or '',
        'meeting_type': meeting.meeting_type,
        'edit_url': reverse('meeting_edit', args=[meeting.pk]),
        'delete_url': reverse('meeting_delete', args=[meeting.pk]),
    })


def note_delete(request, pk):
    note = get_object_or_404(Note, pk=pk)
    contact_pk = note.contact_id
    deal_pk = note.deal_id
    if request.method == 'POST':
        note.delete()
        if contact_pk:
            return redirect('contact_detail', pk=contact_pk)
        return redirect('deal_detail', pk=deal_pk)
    return render(request, 'crm/note_confirm_delete.html', {'note': note})


# ── DriveOps ────────────────────────────────────────────────────────────────

DRIVEOPS_SCOPES = [('mine', 'My leads'), ('unassigned', 'Unassigned'), ('all', 'Everyone')]


def driveops_view(request):
    if request.method == 'POST' and request.POST.get('action') == 'merge_duplicates':
        _merged_message(request, _merge_phone_duplicates('driveops'))
        return redirect(request.get_full_path())
    expire_one_week_prospects()

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', 'lead')  # default to unworked leads
    rep = current_rep(request)
    scope = request.GET.get('scope', 'mine' if rep else 'all')
    if scope not in dict(DRIVEOPS_SCOPES) or (scope == 'mine' and not rep):
        scope = 'all'  # "My leads" needs a rep picked in the sidebar

    base = Contact.objects.filter(pipeline='driveops').exclude(status='inactive')
    contacts = base
    if scope == 'mine':
        contacts = contacts.filter(owner=rep)
    elif scope == 'unassigned':
        contacts = contacts.filter(owner__isnull=True)
    if q:
        contacts = contacts.filter(Q(name__icontains=q) | Q(company__icontains=q) | Q(phone__icontains=q))
    if status:
        contacts = contacts.filter(status=status)

    if request.GET.get('export') == 'csv':
        return _contacts_csv(contacts.order_by('pk'), 'driveops-leads.csv')

    contacts = contacts.select_related('owner').annotate(
        next_meeting_at=Min('meetings__scheduled_at', filter=Q(meetings__completed=False)),
    ).order_by('pk')
    page, querystring = _paginate(request, contacts)

    return render(request, 'crm/driveops.html', {
        'contacts': page,
        'page_obj': page,
        'querystring': querystring,
        'q': q,
        'status': status,
        'scope': scope,
        'scopes': DRIVEOPS_SCOPES,
        'status_choices': [c for c in Contact.STATUS_CHOICES if c[0] != 'inactive'],
        'follow_up_statuses': Contact.FOLLOW_UP_STATUSES,
        'unassigned_count': base.filter(owner__isnull=True).count(),
        'duplicate_phone_ids': set(_active_phone_duplicates('driveops').values_list('pk', flat=True)),
        'lost_reasons': Contact.LOST_REASON_CHOICES,

        'now': timezone.now(),
    })


@require_POST
def driveops_bulk(request):
    """Apply one action to many selected DriveOps leads (Monday/HubSpot-style bulk edit)."""
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('driveops')
    ids = [i for i in request.POST.getlist('contact_ids') if i.isdigit()]
    contacts = Contact.objects.filter(pk__in=ids, pipeline='driveops')
    if not ids:
        messages.error(request, 'Select at least one lead.')
        return redirect(next_url)

    action = request.POST.get('action')
    if action == 'assign':
        owner_id = request.POST.get('owner', '')
        owner = get_object_or_404(get_user_model(), pk=owner_id, is_active=True) if owner_id else None
        updated = contacts.update(owner=owner, updated_at=timezone.now())
        who = owner.get_username() if owner else 'nobody'
        messages.success(request, f'Assigned {updated} lead{"" if updated == 1 else "s"} to {who}.')
    elif action == 'status':
        new_status = request.POST.get('status', '')
        lost_reason = request.POST.get('lost_reason', '')
        done, errors = 0, set()
        for contact in contacts:
            error = change_status(contact, new_status, current_rep(request), lost_reason)
            if error:
                errors.add(error)
            else:
                done += 1
        if done:
            messages.success(request, f'Updated {done} lead{"" if done == 1 else "s"}.')
        for error in errors:
            messages.error(request, f'Some leads were skipped: {error}')
    else:
        messages.error(request, 'Unknown bulk action.')
    return redirect(next_url)


# Scheduling moves a lead forward, never backwards: only these statuses get promoted.
_SCHEDULE_PROMOTIONS = {
    'call': ({'lead', 'call_back_no_answer'}, 'call_back'),
    'video': ({'lead', 'call_back', 'call_back_no_answer'}, 'prospect'),
}


@require_POST
def driveops_schedule(request, pk):
    """AJAX: create a calendar entry (Meeting) for a DriveOps contact."""
    contact = get_object_or_404(Contact, pk=pk)
    data, error = _json_body(request)
    if error:
        return error
    meeting_type = data.get('meeting_type', 'call')
    if meeting_type not in _SCHEDULE_PROMOTIONS:
        meeting_type = 'call'
    try:
        naive = datetime.strptime(f"{data.get('date', '')} {data.get('time', '')}", '%Y-%m-%d %H:%M')
    except ValueError:
        return JsonResponse({'error': 'Date and time are required'}, status=400)
    scheduled_at = timezone.make_aware(naive)

    promote_from, promote_to = _SCHEDULE_PROMOTIONS[meeting_type]
    if contact.status in promote_from:
        change_status(contact, promote_to, current_rep(request))
    elif contact.owner_id is None:
        contact.owner = current_rep(request)
        contact.save(update_fields=['owner', 'updated_at'])

    type_label = 'Call' if meeting_type == 'call' else 'Video Call'
    title = (data.get('title') or '').strip() or f'{type_label} with {contact.name}'
    meeting = Meeting.objects.create(
        title=title,
        contact=contact,
        meeting_type=meeting_type,
        scheduled_at=scheduled_at,
    )
    return JsonResponse({
        'ok': True,
        'meeting_id': meeting.pk,
        'title': meeting.title,
        'scheduled_at': naive.strftime('%Y-%m-%d %H:%M'),
        'status': contact.status,
        'status_display': contact.get_status_display(),
    })


def driveops_analytics(request):
    expire_one_week_prospects()
    today = timezone.localdate()
    now = timezone.now()
    start_of_today = timezone.make_aware(datetime.combine(today, time.min))
    week_start = start_of_today - timedelta(days=6)

    ds_contacts = Contact.objects.filter(pipeline='driveops')

    # ── Current status breakdown (one query) ────────────────────
    counts = dict(ds_contacts.values_list('status').annotate(n=Count('id')).order_by())
    total_active = sum(n for s, n in counts.items() if s != 'inactive')

    # ── Status change activity for the last 7 days (one query) ──
    week_logs = ContactStatusLog.objects.filter(contact__pipeline='driveops', changed_at__gte=week_start)
    per_day = {}
    for day, to_status, n in (
        week_logs.annotate(day=TruncDate('changed_at')).values_list('day', 'to_status').annotate(n=Count('id')).order_by()
    ):
        per_day.setdefault(day, {})[to_status] = n

    tracked = ['call_back', 'call_back_no_answer', 'prospect', 'prospect_1_week', 'inactive', 'customer']
    seven_days = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_counts = per_day.get(day, {})
        seven_days.append({
            'date': day,
            'label': 'Today' if day == today else day.strftime('%a %-d %b'),
            'to_callback': day_counts.get('call_back', 0),
            'to_callback_no_answer': day_counts.get('call_back_no_answer', 0),
            'to_prospect': day_counts.get('prospect', 0),
            'to_prospect_1_week': day_counts.get('prospect_1_week', 0),
            'to_inactive': day_counts.get('inactive', 0),
            'to_customer': day_counts.get('customer', 0),
        })
    today_counts = per_day.get(today, {})

    # Start-of-day leads = current leads + everything that moved OUT of lead today
    moved_out_of_lead_today = week_logs.filter(changed_at__gte=start_of_today, from_status='lead').count()

    # ── Per-rep activity (today and 7 days) ─────────────────────
    rep_rows = (
        week_logs.exclude(changed_by__isnull=True).filter(to_status__in=tracked)
        .values_list('changed_by__username')
        .annotate(
            today=Count('id', filter=Q(changed_at__gte=start_of_today)),
            week=Count('id'),
            prospects_week=Count('id', filter=Q(to_status__in=['prospect', 'prospect_1_week', 'customer'])),
        )
        .order_by('-today', '-week')
    )
    rep_stats = [
        {'username': u, 'today': t, 'week': w, 'prospects_week': p} for u, t, w, p in rep_rows
    ]

    # ── Why leads were lost (one query) ─────────────────────────
    reason_labels = dict(Contact.LOST_REASON_CHOICES)
    lost_reasons = [
        {'label': reason_labels.get(reason, reason), 'count': n}
        for reason, n in ds_contacts.filter(status='inactive').exclude(lost_reason='')
        .values_list('lost_reason').annotate(n=Count('id')).order_by('-n')
    ]

    # ── Queues with time-in-status (one query) ──────────────────
    queue_contacts = (
        ds_contacts.filter(status__in=['call_back', 'prospect', 'prospect_1_week'])
        .annotate(since=status_since_subquery(), next_meeting_at=Min(
            'meetings__scheduled_at', filter=Q(meetings__completed=False)))
        .order_by('updated_at')
    )
    callback_queue, prospect_queue, prospect_1_week_queue = [], [], []
    for c in queue_contacts:
        since = c.since or c.updated_at
        delta = now - since
        item = {
            'contact': c,
            'since': since,
            'days': delta.days,
            'duration': _format_duration(delta),
            'next_meeting_at': c.next_meeting_at,
        }
        if c.status == 'call_back':
            callback_queue.append(item)
        elif c.status == 'prospect':
            prospect_queue.append(item)
        else:
            item['days_remaining'] = max(0, Contact.LOCKED_STATUS_DAYS - delta.days)
            prospect_1_week_queue.append(item)

    return render(request, 'crm/driveops_analytics.html', {
        'today': today,
        'now': now,
        'start_of_day_leads': counts.get('lead', 0) + moved_out_of_lead_today,
        'current_leads': counts.get('lead', 0),
        'current_callbacks': counts.get('call_back', 0),
        'current_callback_no_answer': counts.get('call_back_no_answer', 0),
        'current_prospects': counts.get('prospect', 0),
        'current_prospect_1_week': counts.get('prospect_1_week', 0),
        'current_inactive': counts.get('inactive', 0),
        'current_customers': counts.get('customer', 0),
        'total_active': total_active,
        'converted_to_callback_today': today_counts.get('call_back', 0),
        'converted_to_callback_no_answer_today': today_counts.get('call_back_no_answer', 0),
        'converted_to_prospect_today': today_counts.get('prospect', 0),
        'converted_to_prospect_1_week_today': today_counts.get('prospect_1_week', 0),
        'converted_to_inactive_today': today_counts.get('inactive', 0),
        'callback_queue': callback_queue,
        'prospect_queue': prospect_queue,
        'prospect_1_week_queue': prospect_1_week_queue,
        'seven_days': seven_days,
        'rep_stats': rep_stats,
        'lost_reasons': lost_reasons,
        'lost_reasons_max': max((r['count'] for r in lost_reasons), default=0),
    })


def _month_start(day, months_back=0):
    """First day of the month months_back months before day's month."""
    index = day.year * 12 + day.month - 1 - months_back
    return day.replace(year=index // 12, month=index % 12 + 1, day=1)


def driveops_revenue(request):
    """Subscription income: MRR now, the last 12 months, new vs churned, and a per-plan split."""
    today = timezone.localdate()
    plan_form = PlanForm(request.POST or None, prefix='plan')
    if request.method == 'POST':
        if plan_form.is_valid():
            plan = plan_form.save()
            messages.success(request, f'Added plan "{plan.name}".')
            return redirect('driveops_revenue')

    subs = list(Subscription.objects.select_related('contact', 'plan'))
    active = [s for s in subs if s.is_active_on(today)]
    mrr = sum((s.monthly_amount for s in active), Decimal(0))

    # A month's MRR is what was active on its last day (today, for the current month).
    months = []
    for back in range(11, -1, -1):
        start = _month_start(today, back)
        next_start = _month_start(today, back - 1)
        as_of = min(next_start - timedelta(days=1), today)
        live = [s for s in subs if s.is_active_on(as_of)]
        months.append({
            'start': start,
            'mrr': sum((s.monthly_amount for s in live), Decimal(0)),
            'subscribers': len(live),
            'new': sum((s.monthly_amount for s in subs if start <= s.start_date < next_start), Decimal(0)),
            'churned': sum((s.monthly_amount for s in subs
                            if s.end_date and start <= s.end_date < next_start), Decimal(0)),
        })
    months_max = max((m['mrr'] for m in months), default=0)
    this_month, last_month = months[-1], months[-2]

    by_plan = {}
    for s in active:
        row = by_plan.setdefault(s.plan_id, {'plan': s.plan, 'subscribers': 0, 'mrr': Decimal(0)})
        row['subscribers'] += 1
        row['mrr'] += s.monthly_amount
    plan_rows = sorted(by_plan.values(), key=lambda r: r['mrr'], reverse=True)

    return render(request, 'crm/driveops_revenue.html', {
        'today': today,
        'mrr': mrr,
        'arr': mrr * 12,
        'active_count': len(active),
        'arpu': mrr / len(active) if active else 0,
        'this_month': this_month,
        'mrr_change': this_month['mrr'] - last_month['mrr'],
        'months': list(reversed(months)),
        'months_max': months_max,
        'plan_rows': plan_rows,
        'plans': Plan.objects.annotate(n=Count('subscriptions')),
        'plan_form': plan_form,
        'active_subs': active,
        'ended_subs': [s for s in subs if not s.is_active_on(today)],
    })


def subscription_create(request):
    initial = {'start_date': timezone.localdate()}
    if request.GET.get('contact', '').isdigit():
        initial['contact'] = request.GET['contact']
    form = SubscriptionForm(request.POST or None, initial=initial)
    if form.is_valid():
        sub = form.save()
        if sub.contact.status != 'customer' and sub.is_active_on(timezone.localdate()):
            change_status(sub.contact, 'customer', current_rep(request))
        messages.success(request, f'{sub.contact.name} is now on {sub.plan.name}.')
        return redirect('driveops_revenue')
    if not Plan.objects.filter(is_active=True).exists():
        messages.info(request, 'Add a plan on the Revenue page before adding subscriptions.')
    return render(request, 'crm/subscription_form.html', {'form': form, 'title': 'Add Subscription'})


def subscription_edit(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    form = SubscriptionForm(request.POST or None, instance=sub)
    if form.is_valid():
        form.save()
        return redirect('driveops_revenue')
    return render(request, 'crm/subscription_form.html', {'form': form, 'title': 'Edit Subscription', 'sub': sub})


@require_POST
def subscription_cancel(request, pk):
    sub = get_object_or_404(Subscription.objects.select_related('contact'), pk=pk)
    today = timezone.localdate()
    if sub.end_date is None or sub.end_date > today:
        sub.end_date = max(today, sub.start_date + timedelta(days=1))
        sub.save(update_fields=['end_date'])
        messages.success(request, f'Cancelled {sub.contact.name}\'s subscription.')
    return redirect('driveops_revenue')


@require_POST
def subscription_delete(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    sub.delete()
    messages.success(request, 'Subscription deleted.')
    return redirect('driveops_revenue')


def _format_duration(delta):
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if delta.days > 0:
        return f'{delta.days}d {hours}h'
    if hours > 0:
        return f'{hours}h {minutes}m'
    return f'{minutes}m'


@require_POST
def driveops_deactivate(request, pk):
    """AJAX: mark a DriveOps contact as inactive."""
    contact = get_object_or_404(Contact, pk=pk)
    data, error = _json_body(request)
    if error:
        return error
    error = change_status(contact, 'inactive', current_rep(request), data.get('lost_reason', ''))
    if error:
        return JsonResponse({'error': error}, status=400)
    return JsonResponse({'ok': True, 'contact_id': pk})


@require_POST
def driveops_update_status(request, pk):
    """AJAX: change a DriveOps contact's status, optionally logging a call note."""
    contact = get_object_or_404(Contact, pk=pk)
    data, error = _json_body(request)
    if error:
        return error

    new_status = data.get('status', '')
    error = change_status(contact, new_status, current_rep(request), data.get('lost_reason', ''))
    if error:
        return JsonResponse({'error': error}, status=400)

    note = (data.get('note') or '').strip()
    if note:
        Note.objects.create(contact=contact, body=note, created_by=current_rep(request))

    return JsonResponse({
        'ok': True,
        'status': new_status,
        'status_display': contact.get_status_display(),
    })


# ── Leads generator ─────────────────────────────────────────────────────────

def leads_generator(request):
    """
    Leads Generator: fetch businesses with no websites, then import as leads for the selected country.
    """
    session_key = 'leads_generator_last_results'
    session_country_key = 'leads_generator_last_country'
    results = request.session.get(session_key) or []
    last_country = request.session.get(session_country_key) or 'us'
    error = None
    imported_count = None

    if request.method == 'POST':
        action = request.POST.get('action', 'search')
        if action == 'import':
            region = last_country  # 'us' or 'sa'
            # Any existing contact (active or inactive, any region) with the same phone blocks import.
            known_phones = set(
                Contact.objects.exclude(phone_normalized='').values_list('phone_normalized', flat=True)
            )
            to_create = []
            for r in request.session.get(session_key) or []:
                name = (r.get('name') or '').strip()
                if not name:
                    continue
                phone = (r.get('phone') or '').strip()
                phone_key = normalize_phone(phone)
                if phone_key and phone_key in known_phones:
                    continue
                known_phones.add(phone_key)
                to_create.append(Contact(
                    name=name,
                    phone=phone,
                    phone_normalized=phone_key,
                    company=(r.get('company') or '').strip() or name,
                    region=region,
                    status='lead',
                    owner=current_rep(request),
                ))
            # bulk_create skips save()/signals, so write the initial status logs explicitly.
            created = Contact.objects.bulk_create(to_create)
            ContactStatusLog.objects.bulk_create([
                ContactStatusLog(contact=c, from_status='', to_status='lead', changed_by=current_rep(request))
                for c in created
            ])
            imported_count = len(to_create)
            request.session[session_key] = []
            results = []
            form = LeadsGeneratorForm()
        else:
            form = LeadsGeneratorForm(request.POST)
            if form.is_valid():
                cd = form.cleaned_data
                country = cd.get('country') or 'us'
                try:
                    fetched = _leads_generator_fetch(
                        keyword=cd['keyword'],
                        state=cd.get('state') or '',
                        city=cd.get('city') or '',
                        max_results=cd.get('max_results') or 25,
                        country=country,
                        website_filter=cd.get('website_filter') or 'no_website',
                    )
                    inactive_phones = set(
                        Contact.objects.filter(status='inactive').exclude(phone_normalized='')
                        .values_list('phone_normalized', flat=True)
                    )
                    results = []
                    for r in fetched[: (cd.get('max_results') or 25)]:
                        phone = (r.get('phone') or '').strip()
                        results.append({
                            'name': (r.get('name') or '').strip(),
                            'company': (r.get('company') or r.get('name') or '').strip(),
                            'phone': phone,
                            'website': (r.get('website') or '').strip(),
                            'address': (r.get('address') or '').strip(),
                            'source_id': (r.get('source_id') or '').strip(),
                            'is_inactive': normalize_phone(phone) in inactive_phones,
                        })
                    request.session[session_key] = results
                    request.session[session_country_key] = country
                    last_country = country
                except Exception as e:
                    error = str(e)
            else:
                error = 'Please fix the form errors.'
    else:
        form = LeadsGeneratorForm()

    country_label = _COUNTRY_CONFIG.get(last_country, _COUNTRY_CONFIG['us'])['label']

    return render(request, 'crm/leads_generator.html', {
        'form': form,
        'results': results,
        'error': error,
        'imported_count': imported_count,
        'token_configured': bool(os.environ.get('LEADS_GENERATOR_API_TOKEN', '').strip()),
        'country_label': country_label,
    })


# ── Mass email ──────────────────────────────────────────────────────────────

ALLOWED_FROM = (
    'simon@altitudeinteractiveweb.com',
    'tristan@altitudeinteractiveweb.com',
)


def mass_email(request):
    error = None

    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        contact_ids = [i for i in request.POST.getlist('contact_ids') if i.isdigit()]
        saved_emails = request.POST.getlist('saved_recipient_emails')
        extra_emails = [
            addr.strip() for addr in request.POST.get('extra_emails', '').replace(',', '\n').splitlines()
            if '@' in addr
        ]
        from_email = request.POST.get('from_email', '').strip()
        if from_email not in ALLOWED_FROM:
            from_email = ALLOWED_FROM[0]

        # (email, contact) pairs, de-duplicated case-insensitively, preserving order
        candidates = [(c.email, c) for c in Contact.objects.filter(pk__in=contact_ids).exclude(email='')]
        candidates += [(e.strip(), None) for e in saved_emails + extra_emails if e.strip()]
        seen = set()
        recipients = []
        for email, contact in candidates:
            if email.lower() not in seen:
                seen.add(email.lower())
                recipients.append((email, contact))

        if not subject:
            error = 'Subject is required.'
        elif not message:
            error = 'Message body is required.'
        elif not recipients:
            error = 'Add at least one recipient.'
        else:
            unsubscribed = set(Unsubscribe.objects.values_list('email', flat=True))
            allowed = [(e, c) for e, c in recipients if e.lower() not in unsubscribed]
            cap = settings.CRM_EMAIL_MAX_RECIPIENTS

            campaign = EmailCampaign.objects.create(
                subject=subject,
                body=message,
                from_email=from_email,
                skipped_unsubscribed=len(recipients) - len(allowed),
                over_cap=max(0, len(allowed) - cap),
                created_by=current_rep(request),
            )
            EmailSend.objects.bulk_create([
                EmailSend(campaign=campaign, email=e, contact=c) for e, c in allowed[:cap]
            ])
            for addr in extra_emails:
                SavedRecipient.objects.get_or_create(email=addr.lower())

            start_campaign(campaign, request.build_absolute_uri('/'))
            messages.success(
                request,
                f'Queued {min(len(allowed), cap)} email(s). They send in the background '
                f'(4–8s apart) — progress is shown below.',
            )
            return redirect('mass_email')

    elif request.GET.get('resume', '').isdigit():
        campaign = get_object_or_404(EmailCampaign, pk=request.GET['resume'])
        if campaign.sends.filter(status='pending').exists():
            start_campaign(campaign, request.build_absolute_uri('/'))
            messages.success(request, f'Resumed sending "{campaign.subject}".')
        return redirect('mass_email')

    rep = current_rep(request)
    default_from = rep.email if rep and rep.email in ALLOWED_FROM else ALLOWED_FROM[0]
    campaigns = EmailCampaign.objects.annotate(
        sent=Count('sends', filter=Q(sends__status='sent')),
        failed=Count('sends', filter=Q(sends__status='failed')),
        pending=Count('sends', filter=Q(sends__status='pending')),
    )[:10]
    stale_before = timezone.now() - timedelta(minutes=10)
    return render(request, 'crm/mass_email.html', {
        'contacts_with_email': Contact.objects.exclude(email='').order_by('name'),
        'saved_recipients': SavedRecipient.objects.all(),
        'error': error,
        'default_from': request.POST.get('from_email') or default_from,
        'campaigns': campaigns,
        'stale_before': stale_before,
        'any_sending': any(c.pending for c in campaigns),
    })


def unsubscribe(request, email):
    decoded = unquote(email).strip()
    # Only unsubscribe on POST: mail scanners pre-fetch links with GET.
    if request.method == 'POST':
        Unsubscribe.objects.get_or_create(email=decoded.lower())
        return render(request, 'crm/unsubscribed.html', {'email': decoded, 'done': True})
    return render(request, 'crm/unsubscribed.html', {'email': decoded, 'done': False})


@require_POST
def saved_recipient_delete(request, pk):
    get_object_or_404(SavedRecipient, pk=pk).delete()
    return JsonResponse({'ok': True})
