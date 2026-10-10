import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Contact, ContactStatusLog, EmailCampaign, Meeting, Note, Plan, Subscription, Unsubscribe
from .services import expire_one_week_prospects
from .utils import normalize_phone


class NormalizePhoneTests(TestCase):
    def test_formats_match(self):
        self.assertEqual(normalize_phone('+27 11 903 2602'), '0119032602')
        self.assertEqual(normalize_phone('011 903 2602'), '0119032602')
        self.assertEqual(normalize_phone('+1 972-677-9560'), '9726779560')
        self.assertEqual(normalize_phone('(972) 677-9560'), '9726779560')
        self.assertEqual(normalize_phone(''), '')


class CRMTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        # Migration 0017 creates the two reps; there are no logins, a browser just picks a rep.
        self.simon = User.objects.get(username='simon')
        self.tristan = User.objects.get(username='tristan')
        self.client.post(reverse('choose_rep'), {'rep': self.simon.pk})

    def post_json(self, url, data):
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def driving_school(self, **kwargs):
        defaults = {'name': 'Ace Driving', 'company': 'Driving School', 'phone': '011 000 0000',
                    'region': 'sa', 'pipeline': 'driveops'}
        defaults.update(kwargs)
        return Contact.objects.create(**defaults)


class RepPickerTests(CRMTestCase):
    def test_pages_open_without_login_or_rep(self):
        self.client = self.client_class()
        for name in ('dashboard', 'us_leads', 'driveops', 'driveops_analytics', 'mass_email', 'calendar'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        # With no rep picked, DriveOps shows everyone's leads and work is unattributed.
        self.assertEqual(self.client.get(reverse('driveops')).context['scope'], 'all')
        contact = self.driving_school()
        self.post_json(reverse('driveops_update_status', args=[contact.pk]), {'status': 'call_back', 'note': 'hi'})
        self.assertIsNone(ContactStatusLog.objects.filter(contact=contact).last().changed_by)
        self.assertIsNone(Note.objects.get(contact=contact).created_by)

    def test_switching_rep_and_safe_redirect(self):
        response = self.client.post(reverse('choose_rep'), {'rep': self.tristan.pk, 'next': '/driveops/'})
        self.assertRedirects(response, '/driveops/', fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('dashboard')).context['current_rep'], self.tristan)
        response = self.client.post(reverse('choose_rep'), {'rep': '', 'next': 'https://evil.example.com/'})
        self.assertEqual(response['Location'], reverse('dashboard'))
        self.assertIsNone(self.client.get(reverse('dashboard')).context['current_rep'])

    def test_unsubscribe_is_public_and_needs_post(self):
        url = reverse('unsubscribe', args=['Someone@Example.com'])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertFalse(Unsubscribe.objects.exists())
        self.client.post(url)
        self.assertTrue(Unsubscribe.objects.filter(email='someone@example.com').exists())

    def test_all_main_pages_render(self):
        contact = self.driving_school(owner=self.simon)
        Note.objects.create(contact=contact, body='hello')
        Meeting.objects.create(title='Call', contact=contact, scheduled_at=timezone.now())
        for url in (reverse('dashboard'), reverse('us_leads'), reverse('sa_leads'), reverse('inactive_leads'),
                    reverse('contact_list'), reverse('driveops'), reverse('driveops') + '?scope=all',
                    reverse('driveops_analytics'), reverse('calendar'), reverse('mass_email'),
                    reverse('contact_detail', args=[contact.pk]), reverse('deal_list'),
                    reverse('meeting_create') + '?date=2026-01-05&contact=%d' % contact.pk):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class StatusLogTests(CRMTestCase):
    def test_create_and_change_are_logged_with_user(self):
        contact = self.driving_school()
        contact.status = 'call_back'
        contact._changed_by = self.simon
        contact.save()
        logs = list(ContactStatusLog.objects.filter(contact=contact).values_list('from_status', 'to_status', 'changed_by'))
        self.assertEqual(logs, [('', 'lead', None), ('lead', 'call_back', self.simon.pk)])

    def test_saving_without_status_change_does_not_log(self):
        contact = self.driving_school()
        contact = Contact.objects.get(pk=contact.pk)
        contact.name = 'Renamed'
        contact.save()
        self.assertEqual(ContactStatusLog.objects.filter(contact=contact).count(), 1)

    def test_prospect_1_week_can_only_become_customer(self):
        contact = self.driving_school(status='prospect_1_week')
        url = reverse('driveops_update_status', args=[contact.pk])
        self.assertEqual(self.post_json(url, {'status': 'lead'}).status_code, 400)
        response = self.post_json(url, {'status': 'customer', 'note': 'Signed up!'})
        self.assertEqual(response.status_code, 200)
        contact.refresh_from_db()
        self.assertEqual(contact.status, 'customer')
        self.assertEqual(contact.owner, self.simon)  # working an unowned lead claims it
        self.assertTrue(Note.objects.filter(contact=contact, body='Signed up!').exists())

    def test_edit_form_enforces_prospect_1_week_rule(self):
        contact = self.driving_school(status='prospect_1_week')
        response = self.client.post(reverse('contact_edit', args=[contact.pk]), {
            'name': contact.name, 'phone': contact.phone, 'company': contact.company,
            'status': 'lead', 'region': 'sa', 'pipeline': 'driveops',
        })
        self.assertEqual(response.status_code, 200)
        contact.refresh_from_db()
        self.assertEqual(contact.status, 'prospect_1_week')


class ExpiryTests(CRMTestCase):
    def test_expires_after_seven_days_only(self):
        old = self.driving_school(name='Old', status='prospect_1_week')
        fresh = self.driving_school(name='Fresh', phone='011 111 1111', status='prospect_1_week')
        ContactStatusLog.objects.filter(contact=old).update(changed_at=timezone.now() - timedelta(days=8))
        expired = expire_one_week_prospects()
        self.assertEqual([c.pk for c in expired], [old.pk])
        old.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(old.status, 'inactive')
        self.assertEqual(old.lost_reason, 'expired')
        self.assertEqual(fresh.status, 'prospect_1_week')
        call_command('expire_prospect_1_week', stdout=mock.MagicMock())  # still runs cleanly


class DriveOpsTests(CRMTestCase):
    def test_scope_filters_by_owner(self):
        mine = self.driving_school(name='Mine', owner=self.simon)
        theirs = self.driving_school(name='Theirs', phone='011 222 2222', owner=self.tristan)
        unowned = self.driving_school(name='Nobody', phone='011 333 3333')
        names = lambda scope: {c.name for c in self.client.get(reverse('driveops'), {'scope': scope}).context['contacts']}
        self.assertEqual(names('mine'), {mine.name})
        self.assertEqual(names('unassigned'), {unowned.name})
        self.assertEqual(names('all'), {mine.name, theirs.name, unowned.name})

    def test_schedule_promotes_but_never_demotes(self):
        lead = self.driving_school()
        url = reverse('driveops_schedule', args=[lead.pk])
        data = self.post_json(url, {'meeting_type': 'call', 'date': '2026-09-20', 'time': '10:00'}).json()
        self.assertEqual(data['status'], 'call_back')

        prospect = self.driving_school(name='P', phone='011 444 4444', status='prospect')
        url = reverse('driveops_schedule', args=[prospect.pk])
        data = self.post_json(url, {'meeting_type': 'call', 'date': '2026-09-20', 'time': '11:00'}).json()
        self.assertEqual(data['status'], 'prospect')
        self.assertEqual(Meeting.objects.count(), 2)
        self.assertTrue(timezone.is_aware(Meeting.objects.first().scheduled_at))

    def test_schedule_rejects_bad_input(self):
        lead = self.driving_school()
        url = reverse('driveops_schedule', args=[lead.pk])
        self.assertEqual(self.client.post(url, 'nope', content_type='application/json').status_code, 400)
        self.assertEqual(self.post_json(url, {'date': ''}).status_code, 400)

    def test_analytics_query_count_does_not_grow_with_leads(self):
        for i in range(30):
            c = self.driving_school(name=f'S{i}', phone=f'011 555 {i:04d}', status='call_back')
            c.status = 'prospect'
            c._changed_by = self.simon
            c.save()
        with self.assertNumQueries(9):
            response = self.client.get(reverse('driveops_analytics'))
        self.assertEqual(response.context['current_prospects'], 30)
        self.assertEqual(response.context['converted_to_prospect_today'], 30)
        self.assertEqual(response.context['rep_stats'][0]['username'], 'simon')


class DuplicateTests(CRMTestCase):
    def test_dedup_matches_different_phone_formats(self):
        keep = Contact.objects.create(name='A', phone='+1 972-677-9560', region='us')
        dupe = Contact.objects.create(name='B', phone='(972) 677-9560', region='us')
        Contact.objects.create(name='C', phone='+1 214-000-0000', region='us', status='inactive')
        blocked = Contact.objects.create(name='D', phone='214 000 0000', region='us')
        other = Contact.objects.create(name='E', phone='555 123 4567', region='us')

        response = self.client.get(reverse('us_leads'))
        self.assertEqual(response.context['duplicate_phone_ids'], {keep.pk, dupe.pk, blocked.pk})

        self.client.post(reverse('us_leads'), {'action': 'dedup_phones'})
        remaining = set(Contact.objects.exclude(status='inactive').values_list('pk', flat=True))
        self.assertEqual(remaining, {keep.pk, other.pk})

    def test_merge_keeps_notes_meetings_and_fills_blanks(self):
        keep = self.driving_school(name='Old', email='')
        dupe = self.driving_school(name='New', phone='+27 11 000 0000', email='new@example.com', owner=self.tristan)
        Note.objects.create(contact=dupe, body='Spoke to the owner')
        Meeting.objects.create(title='Call', contact=dupe, scheduled_at=timezone.now())
        self.assertEqual(self.client.get(reverse('driveops'), {'scope': 'all'}).context['duplicate_phone_ids'],
                         {keep.pk, dupe.pk})

        self.client.post(reverse('driveops') + '?scope=all', {'action': 'merge_duplicates'})
        self.assertFalse(Contact.objects.filter(pk=dupe.pk).exists())
        keep.refresh_from_db()
        self.assertEqual(keep.email, 'new@example.com')
        self.assertEqual(keep.owner, self.tristan)
        self.assertEqual(keep.notes.get().body, 'Spoke to the owner')
        self.assertEqual(keep.meetings.count(), 1)
        self.assertEqual(keep.status_logs.count(), 2)

    def test_add_lead_form_blocks_existing_phone(self):
        existing = self.driving_school(status='inactive', lost_reason='not_interested')
        response = self.client.post(reverse('contact_create'), {
            'name': 'Again', 'phone': '+27 11 000 0000', 'status': 'lead', 'region': 'sa', 'pipeline': 'driveops',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'lead #{existing.pk}', str(response.context['form'].errors['phone']))
        self.assertEqual(Contact.objects.count(), 1)
        # Editing an existing lead without changing its number is still allowed.
        response = self.client.post(reverse('contact_edit', args=[existing.pk]), {
            'name': 'Renamed', 'phone': existing.phone, 'status': 'inactive', 'lost_reason': 'price',
            'region': 'sa', 'pipeline': 'driveops',
        })
        self.assertEqual(response.status_code, 302)


class LostReasonTests(CRMTestCase):
    def test_inactive_requires_reason_and_reactivating_clears_it(self):
        contact = self.driving_school()
        url = reverse('driveops_update_status', args=[contact.pk])
        self.assertEqual(self.post_json(url, {'status': 'inactive'}).status_code, 400)
        self.assertEqual(self.post_json(url, {'status': 'inactive', 'lost_reason': 'bogus'}).status_code, 400)
        self.assertEqual(self.post_json(url, {'status': 'inactive', 'lost_reason': 'has_system'}).status_code, 200)
        contact.refresh_from_db()
        self.assertEqual((contact.status, contact.lost_reason), ('inactive', 'has_system'))

        analytics = self.client.get(reverse('driveops_analytics')).context
        self.assertEqual(analytics['lost_reasons'], [{'label': 'Already uses a system', 'count': 1}])

        self.post_json(url, {'status': 'lead'})
        contact.refresh_from_db()
        self.assertEqual((contact.status, contact.lost_reason), ('lead', ''))

    def test_edit_form_requires_reason_for_inactive(self):
        contact = self.driving_school()
        data = {'name': contact.name, 'phone': contact.phone, 'status': 'inactive', 'region': 'sa', 'pipeline': 'driveops'}
        self.assertEqual(self.client.post(reverse('contact_edit', args=[contact.pk]), data).status_code, 200)
        data['lost_reason'] = 'closed'
        self.assertEqual(self.client.post(reverse('contact_edit', args=[contact.pk]), data).status_code, 302)


class BulkAndExportTests(CRMTestCase):
    def test_bulk_assign_and_status_respect_rules(self):
        a = self.driving_school(name='A')
        b = self.driving_school(name='B', phone='011 222 2222', status='prospect_1_week')
        url = reverse('driveops_bulk')
        response = self.client.post(url, {'contact_ids': [a.pk, b.pk], 'action': 'assign', 'owner': self.tristan.pk,
                                          'next': '/driveops/?scope=all'})
        self.assertRedirects(response, '/driveops/?scope=all', fetch_redirect_response=False)
        self.assertEqual(set(Contact.objects.values_list('owner', flat=True)), {self.tristan.pk})

        self.client.post(url, {'contact_ids': [a.pk, b.pk], 'action': 'status', 'status': 'inactive'})
        self.assertFalse(Contact.objects.filter(status='inactive').exists())  # no reason given

        self.client.post(url, {'contact_ids': [a.pk, b.pk], 'action': 'status', 'status': 'inactive',
                               'lost_reason': 'no_answer'})
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((a.status, a.lost_reason), ('inactive', 'no_answer'))
        self.assertEqual(b.status, 'prospect_1_week')  # locked status is skipped, not overridden

    def test_bulk_redirect_stays_on_site(self):
        a = self.driving_school()
        response = self.client.post(reverse('driveops_bulk'), {
            'contact_ids': [a.pk], 'action': 'assign', 'owner': '', 'next': 'https://evil.example.com/',
        })
        self.assertEqual(response['Location'], reverse('driveops'))

    def test_csv_export_follows_filters_and_escapes_formulas(self):
        self.driving_school(name='=HYPERLINK("x")', owner=self.simon)
        self.driving_school(name='Theirs', phone='011 222 2222', owner=self.tristan)
        response = self.client.get(reverse('driveops'), {'scope': 'mine', 'export': 'csv'})
        self.assertEqual(response['Content-Type'], 'text/csv')
        body = response.content.decode()
        self.assertIn('\'=HYPERLINK', body)
        self.assertNotIn('Theirs', body)
        self.assertEqual(self.client.get(reverse('sa_leads'), {'export': 'csv'}).status_code, 200)
        self.assertEqual(self.client.get(reverse('inactive_leads'), {'export': 'csv'}).status_code, 200)


@override_settings(CRM_EMAIL_ASYNC=False, CRM_EMAIL_DELAY_SECONDS=None,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class MassEmailTests(CRMTestCase):
    def test_send_personalises_skips_unsubscribed_and_links_unsubscribe(self):
        contact = Contact.objects.create(name='Jo', company='Jo Plumbing', email='jo@example.com', region='us')
        Unsubscribe.objects.create(email='gone@example.com')
        response = self.client.post(reverse('mass_email'), {
            'subject': 'Hi', 'message': 'Hello {name} at {company}',
            'contact_ids': [contact.pk], 'extra_emails': 'gone@example.com\nnew@example.com',
            'from_email': 'simon@altitudeinteractiveweb.com',
        })
        self.assertRedirects(response, reverse('mass_email'))
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['jo@example.com', 'new@example.com'])
        jo_mail = next(m for m in mail.outbox if m.to == ['jo@example.com'])
        self.assertIn('Hello Jo at Jo Plumbing', jo_mail.body)
        self.assertIn('http://testserver/unsubscribe/jo@example.com/', jo_mail.body)

        campaign = EmailCampaign.objects.get()
        self.assertEqual(campaign.status, 'done')
        self.assertEqual(campaign.skipped_unsubscribed, 1)
        self.assertTrue(contact.email_sends.filter(status='sent').exists())


class RevenueTests(CRMTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.starter = Plan.objects.create(name='Starter', price=500)
        self.annual = Plan.objects.create(name='Annual', price=12000, interval='yearly')

    def test_add_plan_from_revenue_page(self):
        self.client.post(reverse('driveops_revenue'), {'plan-name': 'Pro', 'plan-price': '900',
                                                       'plan-interval': 'monthly', 'plan-is_active': 'on'})
        self.assertTrue(Plan.objects.filter(name='Pro', price=900).exists())

    def test_create_subscription_copies_plan_price_and_marks_customer(self):
        contact = self.driving_school(status='prospect')
        response = self.client.post(reverse('subscription_create'), {
            'contact': contact.pk, 'plan': self.starter.pk, 'price': '', 'start_date': self.today.isoformat(),
        })
        self.assertRedirects(response, reverse('driveops_revenue'), fetch_redirect_response=False)
        sub = Subscription.objects.get()
        self.assertEqual((sub.price, sub.interval), (500, 'monthly'))
        contact.refresh_from_db()
        self.assertEqual(contact.status, 'customer')
        # Repricing the plan leaves the existing customer's price alone.
        self.starter.price = 700
        self.starter.save()
        sub.refresh_from_db()
        self.assertEqual(sub.price, 500)

    def test_mrr_months_and_churn(self):
        a = self.driving_school(name='A', phone='011 000 0001')
        b = self.driving_school(name='B', phone='011 000 0002')
        c = self.driving_school(name='C', phone='011 000 0003')
        long_ago = self.today - timedelta(days=400)
        Subscription.objects.create(contact=a, plan=self.starter, start_date=long_ago)
        Subscription.objects.create(contact=b, plan=self.annual, start_date=long_ago)  # R1000/mo
        cancelled = Subscription.objects.create(contact=c, plan=self.starter, price=300, start_date=long_ago)
        self.client.post(reverse('subscription_cancel', args=[cancelled.pk]))
        ctx = self.client.get(reverse('driveops_revenue')).context
        self.assertEqual(ctx['mrr'], 1500)
        self.assertEqual(ctx['arr'], 18000)
        self.assertEqual(ctx['active_count'], 2)
        self.assertEqual(ctx['this_month']['churned'], 300)
        self.assertEqual(ctx['months'][1]['mrr'], 1800)  # last month, before the cancellation
        self.assertEqual(len(ctx['months']), 12)

    def test_end_date_must_follow_start(self):
        contact = self.driving_school()
        response = self.client.post(reverse('subscription_create'), {
            'contact': contact.pk, 'plan': self.starter.pk, 'start_date': '2026-05-01', 'end_date': '2026-04-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Subscription.objects.exists())

    def test_pages_render(self):
        sub = Subscription.objects.create(contact=self.driving_school(), plan=self.starter, start_date=self.today)
        for url in (reverse('driveops_revenue'), reverse('subscription_create'),
                    reverse('subscription_edit', args=[sub.pk])):
            self.assertEqual(self.client.get(url).status_code, 200, url)
