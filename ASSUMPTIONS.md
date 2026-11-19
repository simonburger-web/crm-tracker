# Assumptions — leg day rework (2026-11-19)

## How the app stores things (from the audit)
- The programme lives in code (`gym/programme.py`), not the database: `LIFTS` (name, equipment, kind),
  `DAYS` (ordered slots with sets, rep range, rest text + seconds, A1/A2 group, per-side).
- Weight and history are keyed by **track** = a lift at one rep range. The first range a lift appears at
  (walking Day 1→4) keeps the plain slug; extra ranges get `slug_low_high` (e.g. `back_squat_8_8`).
  `LiftState`, `LiftLog` and `WeightEdit` all store that track key as `slug`.
- So "preserve history" means: keep every existing track key unchanged. Verified: all 21 old keys are
  unchanged; only `seated_leg_curl`, `seated_calf_raise` and `bulgarian_split_squat` were added.
  No migration or data change was needed, and nothing is deleted.

## Which day is which
- "Current Leg Day 1" (trap-bar, squat 3×8, leg press, A1/A2 ext/calf) is the app's **Day 4**.
  "Current Leg Day 2" (squat 4×5–6, RDL, leg press, calf, leg curl) is **Day 2**.
- The slugs `day2` / `day4` and their place in the Day 1→2→3→4 rotation are kept, so past workouts, "last
  done" dates and "up next" carry on. Titles changed to "Lower — Quads" (Day 4) and
  "Lower — Strength & Hinge" (Day 2).

## Rep ranges — the "upper limit 10" instruction overrides the listed ranges
Your closing note ("upper limit of any given exercise is 10, most 6–8, some 8–10") conflicts with the
ranges in the spec (10–12, 10–15, 12–15, 12–20). I applied the cap to the **leg days only**, since the
upper-body days must not change. Compounds and hamstring curls went to 6–8, calves/leg extension/BSS to 8–10.
Squat 3×8, squat 4×5–6, trap-bar 3×5 and RDL 3×8 were already under 10 and stay as written.

| Exercise | Spec | Used |
|---|---|---|
| Seated leg curl | 3 × 10–12 | 3 × 6–8 |
| Leg press | 3 × 10–15 | 3 × 6–8 |
| Standing calf raise | 4 × 10–15 | 4 × 8–10 |
| Bulgarian split squat | 3 × 8–12/leg | 3 × 8–10/leg (its old range — see below) |
| Leg extension (both days) | 3 × 12–15 / 10–12 | 3 × 8–10 |
| Standing leg curl | 3 × 10–12 | 3 × 6–8 |
| Seated calf raise | 4 × 12–20 | 4 × 8–10 |

- Changing a lift's only rep range keeps its track key, so the old weight becomes the starting weight at
  the new range. A weight from 10–15 reps is light for 6–8, so expect a few quick "↑" sessions; the
  double progression handles that by itself. Adjust on Edit weights if you'd rather jump straight there.
- Leg extension is now 8–10 on both days, so both days share one weight (same rule as lat pulldown).
- The leg extension note says "5–8 half reps" — that's extra partials after the set, not the logged reps.

## New exercises
- Seated leg curl and seated calf raise: weight stack (2.5 kg jumps), isolation. No saved weight, so the
  "First time" prompt shows.
- Bulgarian split squat already existed under slug `bulgarian_split_squat` (dumbbells, 8–10/leg) before
  it was dropped from Day 4, and its state/logs were never deleted. I reused that slug so any old history
  comes back. If a weight was saved for it, it won't show "First time" — that's intended.
- Leg press: plate-loaded; removed from Day 2 only, history kept (it's the same `leg_press` track).

## Alternating hinge (new — the app had no rotation feature)
- A new `Alternating` entry in a day holds the options (trap-bar 3×5 first, then RDL 3×8). Each option is a
  normal slot with its own track, so each keeps its own weight, history and "Next time set 1" logic.
- Whose turn: the option after whichever hinge was logged in the most recent completed **Day 2** that
  logged one; trap-bar if Day 2 never logged either. Old Day 2 sessions logged RDL, so the first new
  Day 2 should be trap-bar. Trap-bar sessions from the old Day 4 don't count.
- A Day 2 where the hinge wasn't logged doesn't flip the turn (you didn't do it, so it comes up again).
- Undoing a Day 2 also undoes the turn, because the turn comes from the logs.
- Once a running session has sets for one option, that option stays on screen for the session.
- "Weekly" is taken as "every Day 2 session", since Day 2 comes round once per rotation.
- Rest for both hinge options is 2.5 min, as specified (trap-bar used to be 3 min on Day 4).

## Other
- No supersets on either leg day; A1/A2 support stays in the code for the upper days.
- Rest times as specified: squat 2.5 min (Day 4) / 3 min (Day 2), hinge 2.5 min, leg press 2 min, curls /
  extension / BSS 60 s, calves 45 s.
- The plate-per-side calculator still shows for barbell lifts (squat, RDL), not trap-bar (unchanged rule).
- Small fix: a card's "History" link now opens that card's track (e.g. Day 4 squat → the 3×8 history)
  instead of always the lift's first track.
- Tests ran in a throwaway virtualenv without `psycopg2-binary` (it didn't build on Python 3.14 here); the
  tests use SQLite, so it isn't needed for them.
- Nothing is committed; the changes are left in the working tree for you to review.
