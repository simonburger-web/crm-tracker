from datetime import date, timedelta
import os
import json
import urllib.parse
import urllib.request
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Sum, Count
from .models import Contact, Deal, Note, Meeting
from .forms import ContactForm, DealForm, NoteForm, MeetingForm, LeadsGeneratorForm


def _leads_generator_fetch(*, keyword: str, state: str = '', city: str = '', max_results: int = 25):
    """
    Fetch businesses matching filters, ideally restricted to "no website".

    This is intentionally implemented as a provider hook. You need to decide which
    provider/API this project uses (the token must NOT be committed).

    Expected return format: list[dict] with keys:
      - name (str)
      - phone (str|None)
      - website (str|None)  (should be None/'' for "no website")
      - address (str|None)
      - source_id (str|None) (provider id)
    """
    token = os.environ.get('LEADS_GENERATOR_API_TOKEN', '').strip()
    if not token:
        raise RuntimeError('LEADS_GENERATOR_API_TOKEN is not set')

    q_parts = [keyword.strip()]
    if city.strip():
        q_parts.append(city.strip())
    if state.strip():
        q_parts.append(state.strip())
    q_parts.append('United States')
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
            'gl': 'us',
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
            if website:
                continue  # we only want "no website" leads

            source_id = str(r.get('data_id') or r.get('place_id') or r.get('data_cid') or '').strip()
            if source_id and source_id in seen:
                continue
            if source_id:
                seen.add(source_id)

            title = (r.get('title') or '').strip()
            if not title:
                continue
            out.append({
                'name': title,
                'company': title,
                'phone': (r.get('phone') or '').strip(),
                'website': '',
                'address': (r.get('address') or '').strip(),
                'source_id': source_id,
            })

    return out


def dashboard(request):
    contacts = Contact.objects.all()
    deals = Deal.objects.all()
    total_contacts = contacts.count()
    total_deals = deals.count()
    pipeline_value = deals.filter(stage__in=['prospecting', 'proposal', 'negotiation']).aggregate(total=Sum('value'))['total'] or 0
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
    return queryset, q, status


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


def us_leads(request):
    contacts, q, status = _filter_contacts(request, Contact.objects.filter(region='us').exclude(status='inactive'))
    return render(request, 'crm/region_leads.html', {
        'contacts': contacts,
        'q': q,
        'status': status,
        'status_choices': [c for c in Contact.STATUS_CHOICES if c[0] != 'inactive'],
        'region': 'us',
        'region_label': 'US Leads',
        'clear_url': 'us_leads',
    })


def sa_leads(request):
    contacts, q, status = _filter_contacts(request, Contact.objects.filter(region='sa').exclude(status='inactive'))
    return render(request, 'crm/region_leads.html', {
        'contacts': contacts,
        'q': q,
        'status': status,
        'status_choices': [c for c in Contact.STATUS_CHOICES if c[0] != 'inactive'],
        'region': 'sa',
        'region_label': 'SA Leads',
        'clear_url': 'sa_leads',
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
    day_data = [(d, day_meetings[d]) for d in days]
    return render(request, 'crm/calendar.html', {'day_data': day_data, 'today': today})


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


def leads_generator(request):
    """
    Leads Generator: scrape/fetch US businesses with no websites, then import as US leads.
    """
    session_key = 'leads_generator_last_results'
    results = request.session.get(session_key) or []
    error = None
    imported_count = None

    if request.method == 'POST':
        action = request.POST.get('action', 'search')
        if action == 'import':
            to_import = request.session.get(session_key) or []
            created = 0
            for r in to_import:
                name = (r.get('name') or '').strip()
                if not name:
                    continue
                phone = (r.get('phone') or '').strip()
                company = (r.get('company') or '').strip()
                if not company:
                    company = name
                exists = Contact.objects.filter(
                    name=name,
                    phone=phone,
                    company=company,
                    region='us',
                ).exists()
                if not exists:
                    Contact.objects.create(
                        name=name,
                        phone=phone,
                        company=company,
                        region='us',
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
                try:
                    fetched = _leads_generator_fetch(
                        keyword=cd['keyword'],
                        state=cd.get('state') or '',
                        city=cd.get('city') or '',
                        max_results=cd.get('max_results') or 25,
                    )
                    # Defensive normalization for the template/session
                    results = []
                    for r in fetched[: (cd.get('max_results') or 25)]:
                        results.append({
                            'name': (r.get('name') or '').strip(),
                            'company': (r.get('company') or r.get('name') or '').strip(),
                            'phone': (r.get('phone') or '').strip(),
                            'website': (r.get('website') or '').strip(),
                            'address': (r.get('address') or '').strip(),
                            'source_id': (r.get('source_id') or '').strip(),
                        })
                    request.session[session_key] = results
                except Exception as e:
                    error = str(e)
            else:
                error = 'Please fix the form errors.'
    else:
        form = LeadsGeneratorForm()

    return render(request, 'crm/leads_generator.html', {
        'form': form,
        'results': results,
        'error': error,
        'imported_count': imported_count,
        'token_configured': bool(os.environ.get('LEADS_GENERATOR_API_TOKEN', '').strip()),
    })
