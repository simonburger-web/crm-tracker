from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import LiftLog, LiftState, WeightEdit, Workout
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
    def complete(self, day, **fields):
        return self.client.post(reverse('gym:day', args=[day]), fields)

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
        self.assertContains(self.client.get(response.url), 'Bench press 80 → 85 kg')

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
