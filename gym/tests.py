from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import LiftLog, LiftState, Workout
from .programme import DAYS_BY_SLUG
from .progression import next_weight, plates_per_side

D = Decimal
DAY1 = DAYS_BY_SLUG['day1']
BENCH = DAY1.slots[0]           # 4 x 5-6, barbell
INCLINE = DAY1.slots[2]         # 3 x 8-12, dumbbell
LATERAL = DAY1.slots[4]         # 4 x 12-15, stack


class ProgressionTests(TestCase):
    def test_all_sets_at_top_adds_one_increment_per_kit(self):
        self.assertEqual(next_weight(D('100'), [6, 6, 6, 6], BENCH, 0), (D('105'), 0, 'up'))
        self.assertEqual(next_weight(D('20'), [12, 12, 12], INCLINE, 0), (D('22'), 0, 'up'))
        self.assertEqual(next_weight(D('10'), [15, 15, 15, 15], LATERAL, 0), (D('12.5'), 0, 'up'))

    def test_inside_range_holds(self):
        self.assertEqual(next_weight(D('100'), [6, 6, 5, 5], BENCH, 1), (D('100'), 0, 'hold'))

    def test_below_range_twice_deloads_to_kit_increment(self):
        self.assertEqual(next_weight(D('100'), [6, 5, 4, 4], BENCH, 0), (D('100'), 1, 'miss'))
        self.assertEqual(next_weight(D('100'), [6, 5, 4, 4], BENCH, 1), (D('90'), 0, 'deload'))
        # 10% of 20 kg DBs is 18, already one 2 kg jump down.
        self.assertEqual(next_weight(D('20'), [7, 7, 7], INCLINE, 1), (D('18'), 0, 'deload'))
        # Small weights still drop at least one increment.
        self.assertEqual(next_weight(D('10'), [10, 10, 10, 10], LATERAL, 1), (D('7.5'), 0, 'deload'))

    def test_skipped_sets_count_as_a_miss(self):
        self.assertEqual(next_weight(D('100'), [6, 6, 6], BENCH, 0)[2], 'miss')

    def test_plate_calculator(self):
        # No 25s or 15s at this gym.
        self.assertEqual(plates_per_side(D('100')), [D('20'), D('20')])
        self.assertEqual(plates_per_side(D('85')), [D('20'), D('10'), D('2.5')])
        self.assertEqual(plates_per_side(D('20')), [])
        self.assertIsNone(plates_per_side(D('15')))


class GymViewTests(TestCase):
    def post_day(self, day, **fields):
        return self.client.post(reverse('gym:day', args=[day]), fields)

    def test_pages_render(self):
        for url in (reverse('gym:home'), reverse('gym:day', args=['day3']), reverse('gym:lift', args=['bench']),
                    reverse('gym:manifest')):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get(reverse('gym:day', args=['mon'])).status_code, 404)

    def test_crm_sidebar_links_to_gym(self):
        self.assertContains(self.client.get(reverse('dashboard')), reverse('gym:home'))

    def test_complete_day_progresses_and_undo_restores(self):
        reps = {f'r-bench-{n}': '6' for n in range(4)}
        self.post_day('day1', **{'w-bench': '100'}, **reps)
        self.assertEqual(LiftState.objects.get(slug='bench').weight, D('105'))
        self.post_day('day1', **{'w-bench': '105', 'r-bench-0': '6', 'r-bench-1': '5', 'r-bench-2': '4', 'r-bench-3': '4'})
        self.assertEqual(LiftState.objects.get(slug='bench').weight, D('105'))
        self.assertEqual(LiftState.objects.get(slug='bench').misses, 1)

        self.client.post(reverse('gym:undo'))
        state = LiftState.objects.get(slug='bench')
        self.assertEqual((state.weight, state.misses), (D('105'), 0))
        self.assertEqual(Workout.objects.count(), 1)

    def test_skipped_exercises_are_not_logged(self):
        response = self.post_day('day4', **{'w-deadlift': '120', 'r-deadlift-0': '5', 'r-leg_extension-0': '12'})
        self.assertRedirects(response, reverse('gym:home'))
        self.assertEqual(set(LiftLog.objects.values_list('slug', flat=True)), {'deadlift', 'leg_extension'})
        # No weight entered for leg extension, so there's nothing to progress from.
        self.assertFalse(LiftState.objects.filter(slug='leg_extension').exists())
