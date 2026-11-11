from datetime import date, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Category, DayPlan, Priority, Routine, Task
from .parsing import parse_line
from .scheduling import auto_schedule, capacity


class ParseTests(TestCase):
    def test_full_syntax(self):
        p = parse_line("!Send Acme proposal 90m #deep #frog")
        self.assertEqual(p["title"], "Send Acme proposal")
        self.assertEqual(p["priority"], Priority.MUST)
        self.assertEqual(p["duration_minutes"], 90)
        self.assertEqual(p["category"], Category.DEEP)
        self.assertTrue(p["is_frog"])

    def test_time_and_hours(self):
        p = parse_line("Call Sarah @2pm 1.5h")
        self.assertEqual(p["start_time"], time(14, 0))
        self.assertEqual(p["duration_minutes"], 90)
        self.assertEqual(p["category"], Category.MEETING)
        self.assertEqual(parse_line("Standup @9:30")["start_time"], time(9, 30))
        self.assertEqual(parse_line("Gym @3")["start_time"], time(15, 0))

    def test_could_and_defaults(self):
        p = parse_line("?tidy notes")
        self.assertEqual(p["priority"], Priority.COULD)
        self.assertEqual(p["duration_minutes"], 30)   # no length given = 30 minutes
        self.assertIsNone(parse_line("   "))
        self.assertIsNone(parse_line("!"))

    def test_unknown_hashtag_kept(self):
        self.assertEqual(parse_line("Fix bug #42")["title"], "Fix bug #42")


class ScheduleTests(TestCase):
    def setUp(self):
        self.plan = DayPlan.objects.create(date=date(2026, 1, 5),
                                           day_start=time(9), day_end=time(12))

    def t(self, title, **kw):
        return Task.objects.create(plan=self.plan, title=title, **kw)

    def test_frog_first_and_fixed_blocks_respected(self):
        self.t("meeting", start_time=time(9, 30), duration_minutes=30, category=Category.MEETING)
        small = self.t("email", priority=Priority.COULD, duration_minutes=30)
        frog = self.t("frog", priority=Priority.SHOULD, duration_minutes=60, is_frog=True, category=Category.DEEP)
        placed, overflow = auto_schedule(list(self.plan.tasks.all()), self.plan.day_start, self.plan.day_end)
        by = {t.title: t.start_time for t in placed}
        self.assertEqual(by["frog"], time(10, 0))   # first 60-min slot after the 9:30 meeting
        self.assertEqual(by["email"], time(9, 0))   # fills the gap before the meeting
        self.assertEqual(overflow, [])

    def test_break_after_long_stretch_and_overflow(self):
        self.t("a", duration_minutes=90, priority=Priority.MUST)
        self.t("b", duration_minutes=60)
        self.t("c", duration_minutes=60)
        placed, overflow = auto_schedule(list(self.plan.tasks.all()), self.plan.day_start, self.plan.day_end)
        by = {t.title: t.start_time for t in placed}
        self.assertEqual(by["a"], time(9, 0))
        self.assertEqual(by["b"], time(10, 40))      # 10-minute break after 90 minutes
        self.assertEqual([t.title for t in overflow], ["c"])

    def test_earliest_rounds_to_quarter(self):
        self.t("a", duration_minutes=30)
        placed, _ = auto_schedule(list(self.plan.tasks.all()), self.plan.day_start, self.plan.day_end, earliest=9 * 60 + 52)
        self.assertEqual(placed[0].start_time, time(10, 0))

    def test_checkpoints_and_anytime_are_not_scheduled_or_blocking(self):
        wake = self.t("Out of bed", start_time=time(9, 0))           # checkpoint, no length
        self.t("Call 30 people", priority=Priority.MUST)             # anytime
        self.t("a", duration_minutes=30)
        placed, overflow = auto_schedule(list(self.plan.tasks.all()), self.plan.day_start, self.plan.day_end)
        self.assertEqual([(t.title, t.start_time) for t in placed], [("a", time(9, 0))])
        self.assertEqual(overflow, [])
        cap = capacity(self.plan, list(self.plan.tasks.all()))
        self.assertEqual((cap["load"], cap["untimed"]), (30, 2))
        self.assertTrue(wake.is_checkpoint)

    def test_capacity(self):
        self.t("a", duration_minutes=200)
        cap = capacity(self.plan, list(self.plan.tasks.all()))
        self.assertTrue(cap["over"])
        self.assertEqual(cap["over_by"], 20)


class ViewTests(TestCase):
    def setUp(self):
        # Two days out so it's never "today" on the planner's Johannesburg clock (auto-schedule
        # would then start from the current time).
        self.day = timezone.localdate() + timedelta(days=2)
        self.url = reverse("planner:day", args=[self.day])

    def test_full_flow(self):
        Routine.objects.create(title="Lunch", start_time=time(12), duration_minutes=45, weekdays="0123456")
        r = self.client.get(self.url)
        self.assertContains(r, "Brain dump")
        self.assertContains(r, "Lunch")
        self.assertContains(r, "Tomorrow")

        self.client.post(reverse("planner:add_tasks", args=[self.day]),
                         {"lines": "!Write proposal 2h #frog\nCall Bob @3pm\n?Inbox 30m\n\n"})
        plan = DayPlan.objects.get(date=self.day)
        self.assertEqual(plan.tasks.count(), 4)
        self.assertEqual(plan.tasks.get(is_frog=True).title, "Write proposal")

        self.client.post(reverse("planner:schedule", args=[self.day]), {"action": "auto"})
        self.assertFalse(plan.tasks.filter(start_time=None).exists())
        self.assertEqual(plan.tasks.get(title="Write proposal").start_time, time(8))

        r = self.client.get(self.url)
        self.assertContains(r, "8:00 AM")

        inbox = plan.tasks.get(title="Inbox")
        self.client.post(reverse("planner:task_action", args=[inbox.pk, "toggle"]))
        inbox.refresh_from_db()
        self.assertTrue(inbox.done)

        bob = plan.tasks.get(title="Call Bob")
        self.client.post(reverse("planner:task_action", args=[bob.pk, "defer"]))
        bob.refresh_from_db()
        self.assertEqual(bob.plan.date, self.day + timedelta(days=1))
        self.assertEqual(bob.carried_count, 1)
        # Next day got the routine too.
        self.assertTrue(bob.plan.tasks.filter(title="Lunch").exists())

        self.client.post(reverse("planner:task_action", args=[bob.pk, "edit"]),
                         {"title": "Call Bob re renewal", "priority": 1, "category": "meeting",
                          "duration_minutes": 20, "start_time": "16:00"})
        bob.refresh_from_db()
        self.assertEqual((bob.title, bob.start_time), ("Call Bob re renewal", time(16)))

        self.client.post(reverse("planner:update_plan", args=[self.day]), {"intention": "Proposal sent"})
        self.client.post(reverse("planner:review", args=[self.day]), {"wins": "Shipped", "improve": "", "rating": 4})
        plan.refresh_from_db()
        self.assertEqual((plan.intention, plan.rating, plan.day_start), ("Proposal sent", 4, time(8)))

    def test_carry_over_moves_unfinished_only(self):
        prev = DayPlan.objects.create(date=self.day - timedelta(days=1))
        Task.objects.create(plan=prev, title="left", done=False)
        Task.objects.create(plan=prev, title="finished", done=True)
        r = self.client.get(self.url)
        self.assertContains(r, "1 unfinished")
        self.client.post(reverse("planner:carry_over", args=[self.day]), {"from": prev.pk})
        self.assertEqual(list(DayPlan.objects.get(date=self.day).tasks.values_list("title", flat=True)), ["left"])

    def test_bad_hours_rejected(self):
        self.client.post(reverse("planner:update_plan", args=[self.day]), {"day_start": "18:00", "day_end": "09:00"})
        self.assertEqual(DayPlan.objects.get(date=self.day).day_start, time(8))

    def test_untimed_routine_and_task_render(self):
        Routine.objects.create(title="Out of bed", start_time=time(7), weekdays="0123456")
        Routine.objects.create(title="Drink water", weekdays="0123456")
        self.client.post(reverse("planner:add_tasks", args=[self.day]), {"lines": "Call 30 people"})
        r = self.client.get(self.url)
        self.assertContains(r, 'class="marker')
        self.assertContains(r, "Anytime today")
        self.assertContains(r, "Call 30 people")
        self.assertContains(r, "Drink water")
        r = self.client.post(reverse("planner:routines"), {
            "title": "Make bed", "start_time": "", "duration_minutes": "", "category": "personal",
            "days": ["0"], "active": "on"})
        self.assertEqual(r.status_code, 302)

    def test_routines_page(self):
        r = self.client.post(reverse("planner:routines"), {
            "title": "Gym", "start_time": "07:00", "duration_minutes": 60, "category": "personal",
            "days": ["0", "2", "4"], "active": "on"})
        self.assertEqual(r.status_code, 302)
        g = Routine.objects.get(title="Gym")
        self.assertEqual(g.weekdays, "024")
        self.assertContains(self.client.get(reverse("planner:routines")), "Mon, Wed, Fri")


class RoutineToggleTests(TestCase):
    def setUp(self):
        self.day = timezone.localdate() + timedelta(days=2)
        self.url = reverse("planner:day", args=[self.day])
        Routine.objects.create(title="Gym", start_time=time(7), duration_minutes=60, weekdays="0123456")

    def test_toggle_off_only_affects_that_day(self):
        self.client.get(self.url)
        plan = DayPlan.objects.get(date=self.day)
        self.assertTrue(plan.tasks.filter(routine__isnull=False).exists())
        self.assertContains(self.client.get(self.url), "Switch off for this day")

        self.client.post(reverse("planner:toggle_routines", args=[self.day]))
        plan.refresh_from_db()
        self.assertTrue(plan.routines_off)
        self.assertFalse(plan.tasks.filter(routine__isnull=False).exists())

        # The same weekday next week is untouched.
        next_week = self.day + timedelta(days=7)
        self.client.get(reverse("planner:day", args=[next_week]))
        next_plan = DayPlan.objects.get(date=next_week)
        self.assertFalse(next_plan.routines_off)
        self.assertTrue(next_plan.tasks.filter(title="Gym").exists())

        # "Add routines" can't sneak them back while they're switched off.
        self.client.post(reverse("planner:apply_routines", args=[self.day]))
        self.assertFalse(plan.tasks.filter(routine__isnull=False).exists())

    def test_toggle_back_on_restores_routines(self):
        self.client.get(self.url)
        self.client.post(reverse("planner:toggle_routines", args=[self.day]))
        self.client.post(reverse("planner:toggle_routines", args=[self.day]))
        plan = DayPlan.objects.get(date=self.day)
        self.assertFalse(plan.routines_off)
        self.assertEqual(plan.tasks.filter(title="Gym").count(), 1)

    def test_custom_tasks_survive_toggle_off(self):
        self.client.post(reverse("planner:add_tasks", args=[self.day]), {"lines": "Call Bob"})
        self.client.post(reverse("planner:toggle_routines", args=[self.day]))
        plan = DayPlan.objects.get(date=self.day)
        self.assertFalse(plan.tasks.filter(routine__isnull=False).exists())
        self.assertTrue(plan.tasks.filter(title="Call Bob", routine=None).exists())

    def test_no_switch_when_no_routine_runs_that_day(self):
        Routine.objects.all().delete()
        other_days = "".join(str(i) for i in range(7) if i != self.day.weekday())
        Routine.objects.create(title="Gym", weekdays=other_days)
        self.assertNotContains(self.client.get(self.url), "Switch off for this day")

    def test_double_tap_does_not_flip_back(self):
        self.client.get(self.url)
        url = reverse("planner:toggle_routines", args=[self.day])
        self.client.post(url, {"state": "off"})
        self.client.post(url, {"state": "off"})
        plan = DayPlan.objects.get(date=self.day)
        self.assertTrue(plan.routines_off)
        self.assertFalse(plan.tasks.filter(routine__isnull=False).exists())

    def test_done_routine_blocks_are_kept(self):
        self.client.get(self.url)
        plan = DayPlan.objects.get(date=self.day)
        plan.tasks.filter(title="Gym").update(done=True)
        self.client.post(reverse("planner:toggle_routines", args=[self.day]), {"state": "off"})
        self.assertTrue(plan.tasks.filter(title="Gym", done=True).exists())
        self.client.post(reverse("planner:toggle_routines", args=[self.day]), {"state": "on"})
        self.assertEqual(plan.tasks.filter(title="Gym").count(), 1)
