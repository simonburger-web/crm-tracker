from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AUTO_COMPLETE, ActiveSession, LiftLog, LiftState, WeightEdit, Workout
from .programme import LIFTS
from .progression import after_session, plates_per_side, sessions_needed

D = Decimal


class CalculatorTests(TestCase):
    def test_sessions_needed_differs_per_lift(self):
        self.assertEqual(sessions_needed(LIFTS['bench'], D('80')), 3)       # 5 kg is 6% of 80
        self.assertEqual(sessions_needed(LIFTS['bench'], D('100')), 2)      # heavier -> jumps come sooner
        self.assertEqual(sessions_needed(LIFTS['deadlift'], D('140')), 2)
        self.assertEqual(sessions_needed(LIFTS['ohp'], D('50')), 4)
        self.assertEqual(sessions_needed(LIFTS['incline_db_press'], D('26')), 4)
        self.assertEqual(sessions_needed(LIFTS['cable_lateral_raise'], D('10')), 8)  # capped

    def test_weight_goes_up_by_kit_increment_once_sessions_are_done(self):
        bench = LIFTS['bench']
        self.assertEqual(after_session(bench, D('80'), 0), (D('80'), 1, False))
        self.assertEqual(after_session(bench, D('80'), 1), (D('80'), 2, False))
        self.assertEqual(after_session(bench, D('80'), 2), (D('85'), 0, True))
        self.assertEqual(after_session(LIFTS['incline_db_press'], D('26'), 3), (D('28'), 0, True))
        self.assertEqual(after_session(LIFTS['cable_lateral_raise'], D('10'), 7), (D('12.5'), 0, True))

    def test_plate_calculator(self):
        # No 25s or 15s at this gym.
        self.assertEqual(plates_per_side(D('100')), [D('20'), D('20')])
        self.assertEqual(plates_per_side(D('85')), [D('20'), D('10'), D('2.5')])
        self.assertEqual(plates_per_side(D('20')), [])
        self.assertIsNone(plates_per_side(D('15')))


class GymViewTests(TestCase):
    def start(self, day, **fields):
        return self.client.post(reverse('gym:day', args=[day]), fields)

    def run_out_the_clock(self, extra=timedelta()):
        ActiveSession.objects.update(started_at=timezone.now() - AUTO_COMPLETE - extra)

    def complete(self, day, **fields):
        """Start a day, let its time pass and open a page, returning that page."""
        self.start(day, **fields)
        self.run_out_the_clock()
        return self.client.get(reverse('gym:home'))

    def state(self, slug):
        return LiftState.objects.get(slug=slug)

    def test_pages_render(self):
        for url in (reverse('gym:home'), reverse('gym:day', args=['day3']), reverse('gym:lift', args=['bench']),
                    reverse('gym:weights'), reverse('gym:manifest')):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get(reverse('gym:day', args=['mon'])).status_code, 404)

    def test_crm_sidebar_links_to_gym(self):
        self.assertContains(self.client.get(reverse('dashboard')), reverse('gym:home'))

    def test_first_session_locks_weights_then_raises_them_automatically(self):
        self.complete('day1', **{'w-bench': '80'})
        self.assertEqual((self.state('bench').weight, self.state('bench').sessions), (D('80'), 1))
        self.assertFalse(LiftState.objects.filter(slug='rope_pushdown').exists())  # no weight entered: skipped

        # Locked: a posted weight is ignored once one is set.
        self.complete('day1', **{'w-bench': '200'})
        self.assertEqual((self.state('bench').weight, self.state('bench').sessions), (D('80'), 2))
        response = self.complete('day1')
        self.assertEqual((self.state('bench').weight, self.state('bench').sessions), (D('85'), 0))
        self.assertEqual(LiftLog.objects.filter(slug='bench', outcome='up').count(), 1)
        self.assertContains(response, 'Bench press 80 → 85 kg')

    def test_viewing_a_day_does_not_start_it(self):
        self.client.get(reverse('gym:day', args=['day1']))
        self.assertFalse(ActiveSession.objects.exists())

    def test_started_day_only_counts_once_its_time_is_up(self):
        LiftState.objects.create(slug='bench', weight=D('80'), sessions=0)
        response = self.start('day1')
        self.assertRedirects(response, reverse('gym:day', args=['day1']))

        ActiveSession.objects.update(started_at=timezone.now() - AUTO_COMPLETE + timedelta(minutes=1))
        self.assertContains(self.client.get(reverse('gym:home')), 'In progress')
        self.assertFalse(Workout.objects.exists())
        self.assertEqual(self.state('bench').sessions, 0)

        self.run_out_the_clock()
        self.assertContains(self.client.get(reverse('gym:home')), 'Day 1 counted')
        self.assertEqual(Workout.objects.filter(day='day1').count(), 1)
        self.assertEqual(self.state('bench').sessions, 1)
        self.assertFalse(ActiveSession.objects.exists())

        # Counted once, however many pages open afterwards.
        self.client.get(reverse('gym:home'))
        self.assertEqual(Workout.objects.count(), 1)

    def test_any_gym_page_counts_a_finished_session(self):
        for name, args in (('gym:weights', []), ('gym:lift', ['bench']), ('gym:day', ['day2'])):
            Workout.objects.all().delete()
            self.start('day1')
            self.run_out_the_clock()
            self.client.get(reverse(name, args=args))
            self.assertEqual(Workout.objects.count(), 1, name)

    def test_session_is_dated_by_when_it_ran_not_when_the_app_next_opened(self):
        self.start('day1')
        self.run_out_the_clock(extra=timedelta(days=3))
        started_at = ActiveSession.objects.get().started_at
        response = self.client.get(reverse('gym:home'))
        self.assertEqual(Workout.objects.get().completed_at, started_at + AUTO_COMPLETE)
        self.assertEqual(response.context['week_count'], 1)

    def test_starting_again_keeps_the_original_start_time(self):
        self.start('day1')
        self.run_out_the_clock(extra=-timedelta(minutes=30))
        started_at = ActiveSession.objects.get().started_at
        self.start('day1')
        self.assertEqual(ActiveSession.objects.get().started_at, started_at)

    def test_cancel_counts_nothing(self):
        LiftState.objects.create(slug='bench', weight=D('80'), sessions=0)
        self.start('day1')
        self.client.post(reverse('gym:cancel'))
        self.assertFalse(ActiveSession.objects.exists())
        self.assertFalse(Workout.objects.exists())
        self.assertEqual(self.state('bench').sessions, 0)

    def test_starting_another_day_replaces_the_one_in_progress(self):
        self.start('day1')
        self.assertContains(self.client.get(reverse('gym:day', args=['day2'])), 'Switch to')
        self.start('day2')
        self.assertEqual(ActiveSession.objects.get().day, 'day2')
        self.run_out_the_clock()
        self.client.get(reverse('gym:home'))
        self.assertEqual(list(Workout.objects.values_list('day', flat=True)), ['day2'])

    def test_weights_entered_during_a_session_lock_in_when_it_counts(self):
        url = reverse('gym:day', args=['day1'])
        self.start('day1')
        self.assertEqual(self.client.post(url, {'autosave': '1', 'w-bench': '800'}).status_code, 204)
        self.client.post(url, {'autosave': '1', 'w-bench': '80'})  # typo corrected
        self.assertFalse(LiftState.objects.filter(slug='bench').exists())
        self.assertContains(self.client.get(url), 'value="80"')

        self.run_out_the_clock()
        self.client.get(reverse('gym:home'))
        self.assertEqual((self.state('bench').weight, self.state('bench').sessions), (D('80'), 1))

    def test_autosave_from_a_stale_page_never_starts_a_session(self):
        url = reverse('gym:day', args=['day1'])
        self.assertEqual(self.client.post(url, {'autosave': '1', 'w-bench': '80'}).status_code, 204)
        self.assertFalse(ActiveSession.objects.exists())

        self.start('day2')
        self.client.post(url, {'autosave': '1', 'w-bench': '80'})
        session = ActiveSession.objects.get()
        self.assertEqual((session.day, session.pending_weights), ('day2', {}))

    def test_undo_restores_weight_and_count(self):
        LiftState.objects.create(slug='bench', weight=D('80'), sessions=2)
        self.complete('day1')
        self.assertEqual(self.state('bench').weight, D('85'))
        self.client.post(reverse('gym:undo'))
        self.assertEqual((self.state('bench').weight, self.state('bench').sessions), (D('80'), 2))
        self.assertFalse(Workout.objects.exists())

    def test_edit_weights_overrides_and_restarts_count(self):
        LiftState.objects.create(slug='bench', weight=D('80'), sessions=2)
        LiftState.objects.create(slug='ohp', weight=D('50'), sessions=3)
        self.client.post(reverse('gym:weights'), {'w-bench': '75', 'w-ohp': '50', 'w-deadlift': '140', 'w-rdl': ''})
        self.assertEqual((self.state('bench').weight, self.state('bench').sessions), (D('75'), 0))
        self.assertEqual((self.state('ohp').weight, self.state('ohp').sessions), (D('50'), 3))  # unchanged
        self.assertEqual(self.state('deadlift').weight, D('140'))
        self.assertFalse(LiftState.objects.filter(slug='rdl').exists())

    def test_edits_are_logged_and_flag_whether_the_app_had_just_raised_the_weight(self):
        LiftState.objects.create(slug='bench', weight=D('80'), sessions=2)
        self.complete('day1')                                    # app raises bench to 85
        self.complete('day1')                                    # one session at 85
        self.client.post(reverse('gym:weights'), {'w-bench': '80', 'w-deadlift': '140'})
        self.client.post(reverse('gym:weights'), {'w-bench': '82.5'})

        second, first = WeightEdit.objects.filter(slug='bench')
        self.assertEqual((first.old_weight, first.new_weight, first.after_increase), (D('85'), D('80'), True))
        self.assertEqual((first.sessions_at_weight, first.sessions_needed), (1, 3))
        self.assertEqual((second.old_weight, second.new_weight, second.after_increase), (D('80'), D('82.5'), False))
        self.assertFalse(WeightEdit.objects.filter(slug='deadlift').exists())  # first-time set, not an edit
        self.assertContains(self.client.get(reverse('gym:lift', args=['bench'])), '1 after an increase')
