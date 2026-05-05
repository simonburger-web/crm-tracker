from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Sum, Count
from .models import Contact, Deal, Note
from .forms import ContactForm, DealForm, NoteForm


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
    contacts, q, status = _filter_contacts(request, Contact.objects.filter(region='us'))
    return render(request, 'crm/region_leads.html', {
        'contacts': contacts,
        'q': q,
        'status': status,
        'status_choices': Contact.STATUS_CHOICES,
        'region': 'us',
        'region_label': 'US Leads',
        'clear_url': 'us_leads',
    })


def sa_leads(request):
    contacts, q, status = _filter_contacts(request, Contact.objects.filter(region='sa'))
    return render(request, 'crm/region_leads.html', {
        'contacts': contacts,
        'q': q,
        'status': status,
        'status_choices': Contact.STATUS_CHOICES,
        'region': 'sa',
        'region_label': 'SA Leads',
        'clear_url': 'sa_leads',
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
