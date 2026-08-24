from datetime import date, datetime, timedelta
import os
import json
import time
import random
import urllib.parse
import urllib.request
from urllib.parse import quote, unquote
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.db.models import Q, Sum, Count
from .models import Contact, Deal, Note, Meeting, TodoBlock, SavedRecipient, Unsubscribe
from .forms import ContactForm, DealForm, NoteForm, MeetingForm, LeadsGeneratorForm


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


def dashboard(request):
    contacts = Contact.objects.all()
    deals = Deal.objects.all()
    total_contacts = contacts.exclude(status='inactive').count()
    total_deals = deals.count()
    pipeline_value = deals.filter(stage__in=['prospecting', 'proposal', 'negotiation']).aggregate(total=Sum('value'))['total'] or 0
    pipeline_value += Contact.objects.filter(status='prospect').aggregate(total=Sum('estimated_value'))['total'] or 0
    won_value = deals.filter(stage='won').aggregate(total=Sum('value'))['total'] or 0
    stage_data = [(stage, deals.filter(stage=stage).count(), label) for stage, label in Deal.STAGE_CHOICES]
    recent_contacts = contacts[:5]
    recent_deals = deals[:5]
    context = {
        'total_contacts': total_contacts,
        'total_deals': total_deals,
        'pipeline_value': pipeline_value,
        'won_value': won_value,
        'stage_data': stage_data,
        'recent_contacts': recent_contacts,
        'recent_deals': recent_deals,
    }
    return render(request, 'crm/dashboard.html', context)


def _filter_contacts(request, queryset):
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(company__icontains=q))
    if status:
        queryset = queryset.filter(status=status)
    return queryset.prefetch_related('deals'), q, status


def contact_list(request):
    contacts = Contact.objects.all()
    contacts, q, status = _filter_contacts(request, contacts)
    return render(request, 'crm/contact_list.html', {
        'us_contacts': contacts.filter(region='us'),
        'sa_contacts': contacts.filter(region='sa'),
        'q': q,
        'status': status,
        'status_choices': Contact.STATUS_CHOICES,
    })


def _duplicate_phone_ids(region):
    """Return a set of Contact PKs that are active but share a phone with:
    - another active contact in the same region, OR
    - any inactive contact (any region).
    """
    from django.db.models import Count

    # Phones that appear more than once among active contacts in this region
    active_dup_phones = set(
        Contact.objects.filter(region=region)
        .exclude(status='inactive')
        .exclude(phone='')
        .values('phone')
        .annotate(n=Count('id'))
        .filter(n__gt=1)
        .values_list('phone', flat=True)
    )

    # Phones belonging to any inactive contact
    inactive_phones = set(
        Contact.objects.filter(status='inactive')
        .exclude(phone='')
        .values_list('phone', flat=True)
    )

    all_flagged_phones = active_dup_phones | inactive_phones

    if not all_flagged_phones:
        return set()

    return set(
        Contact.objects.filter(region=region, phone__in=all_flagged_phones)
        .exclude(status='inactive')
        .values_list('id', flat=True)
    )


def _dedup_phones(region):
    """Delete active contacts in the region whose phone matches:
    - an inactive contact (any region) — always deleted, inactive takes precedence, OR
    - another active contact in the same region — keep oldest, delete the rest.
    Returns count of deleted contacts.
    """
    from django.db.models import Count

    inactive_phones = set(
        Contact.objects.filter(status='inactive')
        .exclude(phone='')
        .values_list('phone', flat=True)
    )

    deleted = 0

    # Delete active contacts that share a phone with an inactive contact
    if inactive_phones:
        to_delete = Contact.objects.filter(region=region, phone__in=inactive_phones).exclude(status='inactive')
        deleted += to_delete.count()
        to_delete.delete()

    # Among remaining active contacts, deduplicate by phone (keep oldest)
    active_dup_phones = (
        Contact.objects.filter(region=region)
        .exclude(status='inactive')
        .exclude(phone='')
        .values('phone')
        .annotate(n=Count('id'))
        .filter(n__gt=1)
        .values_list('phone', flat=True)
    )
    for phone in active_dup_phones:
        dupes = list(
            Contact.objects.filter(region=region, phone=phone)
            .exclude(status='inactive')
            .order_by('created_at')
        )
        for contact in dupes[1:]:
            contact.delete()
            deleted += 1

    return deleted


def us_leads(request):
    if request.method == 'POST' and request.POST.get('action') == 'dedup_phones':
        deleted = _dedup_phones('us')
        from django.contrib import messages
        messages.success(request, f'Removed {deleted} duplicate phone entr{"y" if deleted == 1 else "ies"}.')
        return redirect('us_leads')

    contacts, q, status = _filter_contacts(request, Contact.objects.filter(region='us').exclude(status='inactive'))
    return render(request, 'crm/region_leads.html', {
        'contacts': contacts,
        'q': q,
        'status': status,
        'status_choices': [c for c in Contact.STATUS_CHOICES if c[0] != 'inactive'],
        'region': 'us',
        'region_label': 'US Leads',
        'clear_url': 'us_leads',
        'duplicate_phone_ids': _duplicate_phone_ids('us'),
    })


def sa_leads(request):
    if request.method == 'POST' and request.POST.get('action') == 'dedup_phones':
        deleted = _dedup_phones('sa')
        from django.contrib import messages
        messages.success(request, f'Removed {deleted} duplicate phone entr{"y" if deleted == 1 else "ies"}.')
        return redirect('sa_leads')

    contacts, q, status = _filter_contacts(request, Contact.objects.filter(region='sa').exclude(status='inactive'))
    return render(request, 'crm/region_leads.html', {
        'contacts': contacts,
        'q': q,
        'status': status,
        'status_choices': [c for c in Contact.STATUS_CHOICES if c[0] != 'inactive'],
        'region': 'sa',
        'region_label': 'SA Leads',
        'clear_url': 'sa_leads',
        'duplicate_phone_ids': _duplicate_phone_ids('sa'),
    })


def inactive_leads(request):
    contacts, q, _ = _filter_contacts(request, Contact.objects.filter(status='inactive'))
    return render(request, 'crm/inactive_leads.html', {
        'contacts': contacts,
        'q': q,
    })


def contact_detail(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    note_form = NoteForm()
    if request.method == 'POST':
        note_form = NoteForm(request.POST)
        if note_form.is_valid():
            note = note_form.save(commit=False)
            note.contact = contact
            note.save()
            return redirect('contact_detail', pk=pk)
    return render(request, 'crm/contact_detail.html', {
        'contact': contact,
        'note_form': note_form,
    })


def contact_create(request):
    initial = {}
    region = request.GET.get('region')
    if region in ('us', 'sa'):
        initial['region'] = region
    form = ContactForm(request.POST or None, initial=initial)
    if form.is_valid():
        contact = form.save()
        return redirect('contact_detail', pk=contact.pk)
    return render(request, 'crm/contact_form.html', {'form': form, 'title': 'Add Lead'})


def contact_edit(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    form = ContactForm(request.POST or None, instance=contact)
    if form.is_valid():
        form.save()
        return redirect('contact_detail', pk=pk)
    return render(request, 'crm/contact_form.html', {'form': form, 'title': 'Edit Lead', 'contact': contact})


def contact_delete(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    if request.method == 'POST':
        contact.delete()
        return redirect('contact_list')
    return render(request, 'crm/contact_confirm_delete.html', {'contact': contact})


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
    deal = get_object_or_404(Deal, pk=pk)
    note_form = NoteForm()
    if request.method == 'POST':
        note_form = NoteForm(request.POST)
        if note_form.is_valid():
            note = note_form.save(commit=False)
            note.deal = deal
            note.save()
            return redirect('deal_detail', pk=pk)
    return render(request, 'crm/deal_detail.html', {
        'deal': deal,
        'note_form': note_form,
    })


def deal_create(request):
    form = DealForm(request.POST or None)
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


def calendar_view(request):
    today = date.today()
    days = [today + timedelta(days=i) for i in range(5)]
    meetings = Meeting.objects.filter(
        scheduled_at__date__gte=today,
        scheduled_at__date__lte=today + timedelta(days=4),
    ).select_related('contact')
    day_meetings = {d: [] for d in days}
    for m in meetings:
        d = m.scheduled_at.date()
        if d in day_meetings:
            day_meetings[d].append(m)

    todo_blocks = TodoBlock.objects.filter(date__gte=today, date__lte=today + timedelta(days=4))
    day_todos = {d: [] for d in days}
    for tb in todo_blocks:
        if tb.date in day_todos:
            day_todos[tb.date].append(tb)

    # Build meeting times per day as JSON for conflict checking in JS
    meeting_times_by_day = {}
    for d in days:
        meeting_times_by_day[d.isoformat()] = [
            m.scheduled_at.strftime('%H:%M') for m in day_meetings[d]
        ]

    # Fetch past meetings (last 7 days) for drag-to-reschedule
    past_meetings = Meeting.objects.filter(
        scheduled_at__date__gte=today - timedelta(days=7),
        scheduled_at__date__lt=today,
    ).select_related('contact').order_by('scheduled_at')

    day_data = [(d, day_meetings[d], day_todos[d]) for d in days]
    return render(request, 'crm/calendar.html', {
        'day_data': day_data,
        'today': today,
        'meeting_times_json': json.dumps(meeting_times_by_day),
        'past_meetings': past_meetings,
    })


def meeting_create(request):
    form = MeetingForm(request.POST or None)
    if form.is_valid():
        form.save()
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


def meeting_reschedule(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    meeting = get_object_or_404(Meeting, pk=pk)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    target_date_str = data.get('date')
    if not target_date_str:
        return JsonResponse({'error': 'Missing date'}, status=400)
    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    old_dt = meeting.scheduled_at
    meeting.scheduled_at = old_dt.replace(year=target_date.year, month=target_date.month, day=target_date.day)
    meeting.save()
    return JsonResponse({
        'ok': True,
        'pk': meeting.pk,
        'title': meeting.title,
        'time': meeting.scheduled_at.strftime('%H:%M'),
        'contact': meeting.contact.name,
        'phone': meeting.contact.phone or '',
        'meeting_type': meeting.meeting_type,
        'edit_url': reverse('meeting_edit', args=[meeting.pk]),
        'delete_url': reverse('meeting_delete', args=[meeting.pk]),
    })


def todo_block_create(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    data = json.loads(request.body)
    date_str = data.get('date')
    start_str = data.get('start_time')
    end_str = data.get('end_time')
    title = (data.get('title') or '').strip()
    color = data.get('color', 'blue')

    if not all([date_str, start_str, end_str, title]):
        return JsonResponse({'error': 'Missing fields'}, status=400)

    block_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    start_t = datetime.strptime(start_str, '%H:%M').time()
    end_t = datetime.strptime(end_str, '%H:%M').time()

    if end_t <= start_t:
        return JsonResponse({'error': 'End time must be after start time'}, status=400)

    # Check meeting conflicts: cannot start within 30 min of any meeting start on that day
    for m in Meeting.objects.filter(scheduled_at__date=block_date):
        meeting_start = m.scheduled_at.time().replace(second=0, microsecond=0)
        m_start_dt = datetime.combine(block_date, meeting_start)
        s_start_dt = datetime.combine(block_date, start_t)
        if m_start_dt <= s_start_dt < m_start_dt + timedelta(minutes=30):
            return JsonResponse({
                'error': f'Blocked: meeting "{m.title}" at {meeting_start.strftime("%H:%M")} (30 min buffer)'
            }, status=400)

    valid_colors = [c[0] for c in TodoBlock.COLOR_CHOICES]
    if color not in valid_colors:
        color = 'blue'

    block = TodoBlock.objects.create(
        date=block_date, start_time=start_t, end_time=end_t, title=title, color=color
    )
    return JsonResponse({
        'id': block.pk,
        'title': block.title,
        'start_time': block.start_time.strftime('%H:%M'),
        'end_time': block.end_time.strftime('%H:%M'),
        'color': block.color,
    })


def todo_block_delete(request, pk):
    block = get_object_or_404(TodoBlock, pk=pk)
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    block.delete()
    return JsonResponse({'ok': True})


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


def driveops_view(request):
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    contacts = Contact.objects.filter(
        company__icontains='driving school'
    ).exclude(status='inactive')
    if q:
        contacts = contacts.filter(Q(name__icontains=q) | Q(company__icontains=q) | Q(phone__icontains=q))
    if status:
        contacts = contacts.filter(status=status)
    return render(request, 'crm/driveops.html', {
        'contacts': contacts,
        'q': q,
        'status': status,
        'status_choices': [c for c in Contact.STATUS_CHOICES if c[0] != 'inactive'],
    })


def driveops_schedule(request, pk):
    """AJAX: create a calendar entry (Meeting) for a DriveOps contact."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    contact = get_object_or_404(Contact, pk=pk)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    meeting_type = data.get('meeting_type', 'call')
    date_str = data.get('date', '')
    time_str = data.get('time', '')
    if not date_str or not time_str:
        return JsonResponse({'error': 'Date and time are required'}, status=400)
    if meeting_type not in ('call', 'video'):
        meeting_type = 'call'
    try:
        scheduled_at = datetime.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M')
    except ValueError:
        return JsonResponse({'error': 'Invalid date/time format'}, status=400)
    type_label = 'Call' if meeting_type == 'call' else 'Video Call'
    meeting = Meeting.objects.create(
        title=f'{type_label} with {contact.name}',
        contact=contact,
        meeting_type=meeting_type,
        scheduled_at=scheduled_at,
    )
    return JsonResponse({
        'ok': True,
        'meeting_id': meeting.pk,
        'title': meeting.title,
        'scheduled_at': meeting.scheduled_at.strftime('%Y-%m-%d %H:%M'),
    })


def driveops_deactivate(request, pk):
    """AJAX: mark a DriveOps contact as inactive."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    contact = get_object_or_404(Contact, pk=pk)
    contact.status = 'inactive'
    contact.save()
    return JsonResponse({'ok': True, 'contact_id': pk})


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
            to_import = request.session.get(session_key) or []
            region = last_country  # 'us' or 'sa'
            created = 0
            for r in to_import:
                name = (r.get('name') or '').strip()
                if not name:
                    continue
                phone = (r.get('phone') or '').strip()
                company = (r.get('company') or '').strip()
                if not company:
                    company = name
                # Skip if already exists as inactive (any region)
                if phone and Contact.objects.filter(phone=phone, status='inactive').exists():
                    continue
                # Skip if any active lead already has this phone number
                if phone and Contact.objects.filter(phone=phone).exclude(status='inactive').exists():
                    continue
                # Skip if an active duplicate already exists (same name/company/region)
                exists = Contact.objects.filter(
                    name=name,
                    phone=phone,
                    company=company,
                    region=region,
                ).exists()
                if not exists:
                    Contact.objects.create(
                        name=name,
                        phone=phone,
                        company=company,
                        region=region,
                        status='lead',
                    )
                    created += 1
            imported_count = created
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
                    # Defensive normalization for the template/session
                    inactive_phones = set(
                        Contact.objects.filter(status='inactive').exclude(phone='').values_list('phone', flat=True)
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
                            'is_inactive': phone in inactive_phones,
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


def mass_email(request):
    contacts_with_email = Contact.objects.exclude(email='').exclude(email__isnull=True).order_by('name')
    saved_recipients = SavedRecipient.objects.all()

    success_count = 0
    failed_recipients = []
    error = None
    sent = False
    skipped_count = 0
    remaining_count = 0

    ALLOWED_FROM = {
        'simon@altitudeinteractiveweb.com',
        'tristan@altitudeinteractiveweb.com',
    }

    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        contact_ids = request.POST.getlist('contact_ids')
        saved_emails = request.POST.getlist('saved_recipient_emails')
        extra_emails_raw = request.POST.get('extra_emails', '').strip()
        from_email = request.POST.get('from_email', '').strip()
        if from_email not in ALLOWED_FROM:
            from_email = 'simon@altitudeinteractiveweb.com'

        # Build recipient list and contact lookup for personalisation
        recipients = []
        email_to_contact = {}
        if contact_ids:
            selected = Contact.objects.filter(pk__in=contact_ids).exclude(email='').exclude(email__isnull=True)
            for c in selected:
                recipients.append(c.email)
                email_to_contact[c.email.lower()] = c
        recipients += [e.strip() for e in saved_emails if e.strip()]
        if extra_emails_raw:
            for addr in extra_emails_raw.replace(',', '\n').splitlines():
                addr = addr.strip()
                if addr and '@' in addr:
                    recipients.append(addr)

        # Deduplicate while preserving order
        seen = set()
        unique_recipients = []
        for r in recipients:
            if r.lower() not in seen:
                seen.add(r.lower())
                unique_recipients.append(r)

        if not subject:
            error = 'Subject is required.'
        elif not message:
            error = 'Message body is required.'
        elif not unique_recipients:
            error = 'Add at least one recipient.'
        else:
            # Filter unsubscribed
            unsubscribed_emails = set(Unsubscribe.objects.values_list('email', flat=True))
            filtered = [r for r in unique_recipients if r.lower() not in unsubscribed_emails]
            skipped_count = len(unique_recipients) - len(filtered)
            unique_recipients = filtered

            # Hard cap at 40
            if len(unique_recipients) > 40:
                remaining_count = len(unique_recipients) - 40
                unique_recipients = unique_recipients[:40]

            for i, recipient in enumerate(unique_recipients):
                contact = email_to_contact.get(recipient.lower())
                if contact:
                    name = contact.name or 'there'
                    company = contact.company or 'your business'
                else:
                    name = 'there'
                    company = 'your business'

                personalised = message.replace('{name}', name).replace('{company}', company)
                footer = (
                    f"\n\n---\n"
                    f"Altitude Interactive (Pty) Ltd, 8 Jamaican Music Avenue, "
                    f"Pretoria, 0081, South Africa\n"
                    f"Don't want these emails? Unsubscribe here: "
                    f"https://yoursite.com/unsubscribe/{quote(recipient)}/"
                )
                full_message = personalised + footer

                try:
                    send_mail(subject, full_message, from_email, [recipient], fail_silently=False)
                    success_count += 1
                except Exception:
                    failed_recipients.append(recipient)

                if i < len(unique_recipients) - 1:
                    time.sleep(random.uniform(4, 8))

            sent = True

            # Save any new external emails (from extra_emails field) for future use
            if extra_emails_raw:
                for addr in extra_emails_raw.replace(',', '\n').splitlines():
                    addr = addr.strip().lower()
                    if addr and '@' in addr:
                        SavedRecipient.objects.get_or_create(email=addr)
            saved_recipients = SavedRecipient.objects.all()

    return render(request, 'crm/mass_email.html', {
        'contacts_with_email': contacts_with_email,
        'saved_recipients': saved_recipients,
        'success_count': success_count,
        'failed_recipients': failed_recipients,
        'error': error,
        'sent': sent,
        'skipped_count': skipped_count,
        'remaining_count': remaining_count,
    })


def unsubscribe(request, email):
    decoded = unquote(email)
    Unsubscribe.objects.get_or_create(email=decoded.lower())
    return render(request, 'crm/unsubscribed.html', {'email': decoded})


def saved_recipient_delete(request, pk):
    recipient = get_object_or_404(SavedRecipient, pk=pk)
    if request.method == 'POST':
        recipient.delete()
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=405)
