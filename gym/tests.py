from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AUTO_COMPLETE, ActiveSession, LiftLog, LiftState, WeightEdit, Workout
from .programme import DAYS_BY_SLUG, TRACKS, Alternating
from .progression import next_set_weight, next_start, plates_per_side, top_weight

D = Decimal


class ProgressionTests(TestCase):
    def test_next_set_follows_the_set_before(self):
        rows = TRACKS['lat_pulldown']  # 3 × 6–8, stack, 2.5 kg jumps
        self.assertEqual(next_set_weight(rows, D('60'), 8), D('62.5'))   # top of range: up
        self.assertEqual(next_set_weight(rows, D('60'), 7), D('60'))     # in range: same
        self.assertEqual(next_set_weight(rows, D('60'), 6), D('60'))
        self.assertEqual(next_set_weight(rows, D('60'), 5), D('57.5'))   # under: drop
        self.assertEqual(next_set_weight(rows, D('60'), None), D('60'))  # reps not in yet

    def test_next_session_starts_at_heaviest_that_held(self):
        t = TRACKS['lat_pulldown']
        self.assertEqual(next_start(t, [(D('60'), 8), (D('62.5'), 6), (D('62.5'), 6)]), D('62.5'))
        self.assertEqual(next_start(t, [(D('62.5'), 8), (D('62.5'), 8), (D('62.5'), 8)]), D('65'))
        self.assertEqual(next_start(t, [(D('60'), 8), (D('62.5'), 5), (D('60'), 7)]), D('60'))
        self.assertEqual(next_start(t, [(D('60'), 5), (D('60'), 4)]), D('57.5'))    # nothing held: drop
        self.assertEqual(top_weight(t, [(D('60'), 8), (D('62.5'), 5)]), D('60'))

    def test_a_lift_at_two_rep_ranges_gets_two_weights(self):
        day2 = next(s for s in DAYS_BY_SLUG['day2'].slots if s.lift.slug == 'back_squat')
        day4 = next(s for s in DAYS_BY_SLUG['day4'].slots if s.lift.slug == 'back_squat')
        self.assertEqual((day2.track.key, day4.track.key), ('back_squat', 'back_squat_8_8'))
        self.assertEqual((day2.track.name, day4.track.name), ('Belt back squat (5–6)', 'Belt back squat (8)'))
        # Same range on both days: one shared weight.
        pulldowns = [s.track.key for d in ('day1', 'day3') for s in DAYS_BY_SLUG[d].slots
                     if s.lift.slug == 'lat_pulldown']
        self.assertEqual(pulldowns, ['lat_pulldown', 'lat_pulldown'])

    def test_plate_calculator(self):
        # No 25s or 15s at this gym.
        self.assertEqual(plates_per_side(D('100')), [D('20'), D('20')])
        self.assertEqual(plates_per_side(D('85')), [D('20'), D('10'), D('2.5')])
        self.assertEqual(plates_per_side(D('20')), [])
        self.assertIsNone(plates_per_side(D('15')))


def sets(key, *pairs):
    """POST fields for a track's sets: sets('bench', ('80', 6), ('80', 5))."""
    fields = {}
    for i, (w, r) in enumerate(pairs):
        fields[f's-{key}-{i}-w'] = w
        fields[f's-{key}-{i}-r'] = '' if r is None else str(r)
    return fields


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

    def test_logged_sets_set_next_sessions_start(self):
        LiftState.objects.create(slug='lat_pulldown', weight=D('60'))
        response = self.complete('day1', **sets('lat_pulldown', ('60', 8), ('62.5', 6), ('62.5', 6)),
                                 **sets('bench', ('80', 6), ('80', 6), ('80', 6), ('80', 6)))
        self.assertEqual(self.state('lat_pulldown').weight, D('62.5'))
        self.assertEqual(self.state('bench').weight, D('85'))  # first time, every set at the top of 5–6
        self.assertFalse(LiftState.objects.filter(slug='rope_pushdown').exists())  # nothing logged: skipped
        self.assertContains(response, 'Lat pulldown 60 → 62.5 kg')
        log = LiftLog.objects.get(slug='lat_pulldown')
        self.assertEqual((log.weight, log.outcome, log.next_weight), (D('62.5'), 'up', D('62.5')))
        self.assertEqual(log.sets, [{'w': '60', 'r': 8}, {'w': '62.5', 'r': 6}, {'w': '62.5', 'r': 6}])

        self.complete('day1', **sets('lat_pulldown', ('62.5', 7), ('62.5', 6), ('62.5', 6)))
        self.assertEqual((self.state('lat_pulldown').weight, self.state('lat_pulldown').sessions), (D('62.5'), 1))
        self.assertEqual(LiftLog.objects.filter(slug='lat_pulldown').last().outcome, 'hold')
        self.complete('day1', **sets('lat_pulldown', ('62.5', 5), ('60', 6)))  # only the drop set held
        self.assertEqual(self.state('lat_pulldown').weight, D('60'))
        self.assertEqual(LiftLog.objects.filter(slug='lat_pulldown').last().outcome, 'down')

    def test_day_page_fills_each_set_from_the_one_before(self):
        LiftState.objects.create(slug='lat_pulldown', weight=D('60'))
        url = reverse('gym:day', args=['day1'])
        self.start('day1', **sets('lat_pulldown', ('60', 8)))
        rows = next(c for c in self.client.get(url).context['cards'] if c['key'] == 'lat_pulldown')['rows']
        self.assertEqual([(r['weight'], r['reps'], r['chosen']) for r in rows],
                         [('60', 8, True), ('62.5', '', False), ('62.5', '', False)])

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
        self.assertEqual(self.state('bench').weight, D('80'))  # nothing logged: unchanged
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

    def test_sets_autosave_during_a_session(self):
        url = reverse('gym:day', args=['day1'])
        self.start('day1')
        self.assertEqual(self.client.post(url, {'autosave': '1', **sets('bench', ('800', 6))}).status_code, 204)
        self.client.post(url, {'autosave': '1', **sets('bench', ('80', 6), ('', None))})  # typo corrected
        self.assertEqual(ActiveSession.objects.get().sets, {'bench': [{'w': '80', 'r': 6}]})
        self.assertFalse(LiftState.objects.filter(slug='bench').exists())
        self.assertContains(self.client.get(url), 'value="80"')

        self.run_out_the_clock()
        self.client.get(reverse('gym:home'))
        self.assertEqual(self.state('bench').weight, D('85'))

    def test_autosave_from_a_stale_page_never_starts_a_session(self):
        url = reverse('gym:day', args=['day1'])
        self.assertEqual(self.client.post(url, {'autosave': '1', **sets('bench', ('80', 6))}).status_code, 204)
        self.assertFalse(ActiveSession.objects.exists())

        self.start('day2')
        self.client.post(url, {'autosave': '1', **sets('bench', ('80', 6))})
        session = ActiveSession.objects.get()
        self.assertEqual((session.day, session.sets), ('day2', {}))

    def test_undo_restores_weight_and_count(self):
        LiftState.objects.create(slug='bench', weight=D('80'), sessions=2)
        self.complete('day1', **sets('bench', ('80', 6), ('80', 6), ('80', 6), ('80', 6)))
        self.assertEqual(self.state('bench').weight, D('85'))
        self.client.post(reverse('gym:undo'))
        self.assertEqual((self.state('bench').weight, self.state('bench').sessions), (D('80'), 2))
        self.assertFalse(Workout.objects.exists())

    def test_edit_weights_overrides_and_restarts_count(self):
        LiftState.objects.create(slug='bench', weight=D('80'), sessions=2)
        LiftState.objects.create(slug='ohp', weight=D('50'), sessions=3)
        self.client.post(reverse('gym:weights'), {'w-bench': '75', 'w-ohp': '50', 'w-trap_bar_deadlift': '140', 'w-rdl': ''})
        self.assertEqual((self.state('bench').weight, self.state('bench').sessions), (D('75'), 0))
        self.assertEqual((self.state('ohp').weight, self.state('ohp').sessions), (D('50'), 3))  # unchanged
        self.assertEqual(self.state('trap_bar_deadlift').weight, D('140'))
        self.assertFalse(LiftState.objects.filter(slug='rdl').exists())

    def test_edits_are_logged_and_flag_whether_the_app_had_just_raised_the_weight(self):
        LiftState.objects.create(slug='bench', weight=D('80'), sessions=2)
        top = sets('bench', ('80', 6), ('80', 6), ('80', 6), ('80', 6))
        self.complete('day1', **top)                             # all at the top: bench goes to 85
        self.complete('day1', **sets('bench', ('85', 5), ('85', 5), ('85', 5), ('85', 5)))  # held at 85
        self.client.post(reverse('gym:weights'), {'w-bench': '80', 'w-trap_bar_deadlift': '140'})
        self.client.post(reverse('gym:weights'), {'w-bench': '82.5'})

        second, first = WeightEdit.objects.filter(slug='bench')
        self.assertEqual((first.old_weight, first.new_weight, first.after_increase), (D('85'), D('80'), True))
        self.assertEqual(first.sessions_at_weight, 1)
        self.assertEqual((second.old_weight, second.new_weight, second.after_increase), (D('80'), D('82.5'), False))
        self.assertFalse(WeightEdit.objects.filter(slug='trap_bar_deadlift').exists())  # first-time set, not an edit
        self.assertContains(self.client.get(reverse('gym:lift', args=['bench'])), '1 after an increase')


def spec(entry):
    return (entry.lift.slug, entry.sets, entry.low, entry.high, entry.rest_seconds, entry.lift.equipment,
            entry.group, entry.per, entry.note)


CALF = '2 s pause in the bottom stretch, last set to failure'


class LegDayTests(TestCase):
    def test_leg_day_1_quad_focus_in_order(self):
        self.assertEqual(DAYS_BY_SLUG['day4'].title, 'Lower — Quads')
        self.assertEqual([spec(s) for s in DAYS_BY_SLUG['day4'].slots], [
            ('back_squat', 3, 8, 8, 150, 'barbell', '', '', ''),
            ('seated_leg_curl', 3, 6, 8, 60, 'stack', '', '', ''),
            ('leg_press', 3, 6, 8, 120, 'plates', '', '', 'Feet low and narrow, full depth'),
            ('standing_calf_raise', 4, 8, 10, 45, 'stack', '', '', CALF),
            ('bulgarian_split_squat', 3, 8, 10, 60, 'dumbbell', '', 'leg', ''),
            ('leg_extension', 3, 8, 10, 60, 'stack', '', '', 'Last set: add 5–8 half reps in the bottom range'),
        ])

    def test_leg_day_2_strength_and_hinge_in_order(self):
        slots = DAYS_BY_SLUG['day2'].slots
        self.assertIsInstance(slots[1], Alternating)
        self.assertEqual([spec(o) for o in slots[1].options], [
            ('trap_bar_deadlift', 3, 5, 5, 150, 'trap_bar', '', '', ''),
            ('rdl', 3, 8, 8, 150, 'barbell', '', '', ''),
        ])
        self.assertEqual([spec(s) for i, s in enumerate(slots) if i != 1], [
            ('back_squat', 4, 5, 6, 180, 'barbell', '', '', ''),
            ('leg_extension', 3, 8, 10, 60, 'stack', '', '', ''),
            ('standing_leg_curl', 3, 6, 8, 60, 'stack', '', '', ''),
            ('seated_calf_raise', 4, 8, 10, 45, 'stack', '', '', CALF),
        ])
        self.assertNotIn('leg_press', [s.lift.slug for s in DAYS_BY_SLUG['day2'].all_slots])

    def test_leg_day_reps_top_out_at_10(self):
        for day in ('day2', 'day4'):
            for s in DAYS_BY_SLUG[day].all_slots:
                self.assertLessEqual(s.high, 10, (day, s.lift.slug))

    def test_existing_lifts_keep_their_track_keys_so_history_carries_over(self):
        for key in ('back_squat', 'back_squat_8_8', 'trap_bar_deadlift', 'rdl', 'leg_press', 'leg_extension',
                    'standing_calf_raise', 'standing_leg_curl', 'bulgarian_split_squat'):
            self.assertIn(key, TRACKS)
        # Leg extension is 8–10 on both leg days now: one shared weight.
        self.assertEqual({s.track.key for d in ('day2', 'day4') for s in DAYS_BY_SLUG[d].all_slots
                          if s.lift.slug == 'leg_extension'}, {'leg_extension'})

    def test_upper_days_untouched(self):
        self.assertEqual([(s.lift.slug, s.sets, s.low, s.high, s.group) for s in DAYS_BY_SLUG['day1'].slots], [
            ('bench', 4, 5, 6, ''), ('lat_pulldown', 3, 6, 8, ''), ('incline_db_press', 3, 8, 12, 'A1'),
            ('incline_db_row', 3, 8, 12, 'A2'), ('cable_lateral_raise', 4, 12, 15, 'B1'),
            ('rope_pushdown', 4, 12, 15, 'B2'), ('incline_db_curl', 3, 8, 12, '')])
        self.assertEqual([s.lift.slug for s in DAYS_BY_SLUG['day3'].slots], [
            'ohp', 'lat_pulldown', 'single_arm_row_machine', 'cable_fly', 'cable_lateral_raise',
            'bayesian_cable_curl', 'db_oh_triceps'])


class LegDayPageTests(TestCase):
    # GymViewTests' helpers, without rerunning its tests.
    start = GymViewTests.start
    run_out_the_clock = GymViewTests.run_out_the_clock
    complete = GymViewTests.complete

    def hinge(self):
        return next(c for c in self.client.get(reverse('gym:day', args=['day2'])).context['cards'] if c['alt'])

    def test_day_pages_show_order_rest_timers_notes_and_no_pairs(self):
        response = self.client.get(reverse('gym:day', args=['day4']))
        self.assertEqual([c['key'] for c in response.context['cards']], [
            'back_squat_8_8', 'seated_leg_curl', 'leg_press', 'standing_calf_raise', 'bulgarian_split_squat',
            'leg_extension'])
        self.assertNotContains(response, 'class="group"')
        self.assertNotContains(response, 'card paired')
        for seconds in (150, 60, 120, 45):
            self.assertContains(response, f'data-seconds="{seconds}"')
        self.assertContains(response, 'Feet low and narrow, full depth')
        self.assertContains(response, '3 × 8–10/leg')
        self.assertContains(response, reverse('gym:lift', args=['back_squat_8_8']))  # history of this track
        self.assertContains(response, 'data-plates-out')  # barbell squat keeps the plate calculator

        response = self.client.get(reverse('gym:day', args=['day2']))
        self.assertEqual([c['key'] for c in response.context['cards']], [
            'back_squat', 'trap_bar_deadlift', 'leg_extension', 'standing_leg_curl', 'seated_calf_raise'])
        self.assertContains(response, 'data-seconds="180"')
        self.assertContains(response, 'next time: Romanian deadlift 3 × 8')

    def test_new_lifts_show_the_first_time_prompt(self):
        LiftState.objects.create(slug='standing_calf_raise', weight=D('80'))
        for day, key in (('day4', 'seated_leg_curl'), ('day2', 'seated_calf_raise')):
            card = next(c for c in self.client.get(reverse('gym:day', args=[day])).context['cards'] if c['key'] == key)
            self.assertFalse(card['set'])
        self.assertContains(self.client.get(reverse('gym:day', args=['day4'])), 'First time')
        card = next(c for c in self.client.get(reverse('gym:day', args=['day4'])).context['cards']
                    if c['key'] == 'standing_calf_raise')
        self.assertTrue(card['set'])

    def test_old_leg_press_history_shows_on_day_4(self):
        old = Workout.objects.create(day='day2', completed_at=timezone.now() - timedelta(days=10))
        LiftLog.objects.create(workout=old, slug='leg_press', weight=D('160'), next_weight=D('160'),
                               sets=[{'w': '160', 'r': 11}])
        LiftState.objects.create(slug='leg_press', weight=D('160'))
        card = next(c for c in self.client.get(reverse('gym:day', args=['day4'])).context['cards']
                    if c['key'] == 'leg_press')
        self.assertEqual((card['weight'], card['last']), ('160', '160×11'))
        self.assertContains(self.client.get(reverse('gym:lift', args=['leg_press'])), '160×11')

    def test_hinge_alternates_from_the_last_day_2_and_each_tracks_its_own_weight(self):
        # Trap-bar logged on the old Day 4 doesn't count toward Day 2's turn.
        old = Workout.objects.create(day='day4', completed_at=timezone.now() - timedelta(days=3))
        LiftLog.objects.create(workout=old, slug='trap_bar_deadlift', weight=D('140'), sets=[{'w': '140', 'r': 5}])
        LiftState.objects.create(slug='trap_bar_deadlift', weight=D('140'))
        LiftState.objects.create(slug='rdl', weight=D('100'))
        self.assertEqual(self.hinge()['key'], 'trap_bar_deadlift')

        response = self.complete('day2', **sets('trap_bar_deadlift', ('140', 5), ('140', 5), ('140', 5)))
        self.assertContains(response, 'Trap-bar deadlift 140 → 145 kg')
        self.assertEqual(self.hinge()['key'], 'rdl')
        self.assertEqual(self.hinge()['weight'], '100')  # RDL untouched by the trap-bar session

        self.complete('day2', **sets('rdl', ('100', 8), ('100', 7), ('100', 7)))
        self.assertEqual((LiftState.objects.get(slug='rdl').weight, LiftState.objects.get(slug='trap_bar_deadlift').weight),
                         (D('100'), D('145')))
        self.assertEqual(self.hinge()['key'], 'trap_bar_deadlift')
        self.assertEqual(self.hinge()['weight'], '145')

        # A Day 2 with no hinge logged doesn't flip the turn; undo puts it back.
        self.complete('day2', **sets('back_squat', ('100', 6)))
        self.assertEqual(self.hinge()['key'], 'trap_bar_deadlift')
        self.client.post(reverse('gym:undo'))
        self.client.post(reverse('gym:undo'))
        self.assertEqual(self.hinge()['key'], 'rdl')

    def test_hinge_turn_holds_for_the_session_in_progress(self):
        self.start('day2', **sets('trap_bar_deadlift', ('140', 5)))
        self.assertEqual(self.hinge()['key'], 'trap_bar_deadlift')
        self.run_out_the_clock()
        self.client.get(reverse('gym:home'))
        self.assertEqual(LiftLog.objects.get(slug='trap_bar_deadlift').sets, [{'w': '140', 'r': 5}])
        self.assertEqual(self.hinge()['key'], 'rdl')
