"""Time-blocking logic: capacity maths and the auto-scheduler."""
import math
from datetime import time

from .models import Category

FOCUS_STRETCH = 90  # minutes of back-to-back work before a forced break
BREAK_MINUTES = 10


def to_min(t):
    return t.hour * 60 + t.minute


def to_time(minutes):
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return time(minutes // 60, minutes % 60)


def _overlaps(a_start, a_end, blocks):
    return next((b for b in blocks if b[0] < a_end and a_start < b[1]), None)


def _run_ending_at(end, blocks):
    """Length of the contiguous chain of blocks finishing exactly at `end`."""
    total, cursor = 0, end
    while True:
        prev = next((b for b in blocks if b[1] == cursor and b[2]), None)
        if not prev:
            return total
        total += prev[1] - prev[0]
        cursor = prev[0]


def auto_schedule(tasks, day_start, day_end, earliest=None):
    """Assign start times to unscheduled, unfinished tasks.

    Fixed items (anything that already has a start time) are treated as busy.
    Order: frog first, then priority, deep work before shallow work (do the hard
    thinking while energy is highest), then manual order. Each task takes the
    earliest gap it fits, and a short break is inserted after ~90 minutes of
    back-to-back work. Returns (placed, overflow) lists.
    """
    start_bound = to_min(day_start)
    if earliest is not None:
        start_bound = max(start_bound, math.ceil(earliest / 15) * 15)
    end_bound = to_min(day_end)

    # (start, end, counts_as_work)
    busy = [
        (to_min(t.start_time), to_min(t.start_time) + t.duration_minutes, t.category != Category.PERSONAL)
        for t in tasks if t.start_time is not None and t.duration_minutes is not None
    ]
    pending = sorted(
        (t for t in tasks if t.start_time is None and not t.done and t.duration_minutes is not None),
        key=lambda t: (not t.is_frog, t.priority, t.category != Category.DEEP, t.order, t.id or 0),
    )

    placed, overflow = [], []
    for task in pending:
        dur = task.duration_minutes
        start = start_bound
        while True:
            clash = _overlaps(start, start + dur, busy)
            if not clash:
                break
            start = clash[1]
        if start + dur > end_bound:
            overflow.append(task)
            continue
        task.start_time = to_time(start)
        end = start + dur
        busy.append((start, end, True))
        if _run_ending_at(end, busy) >= FOCUS_STRETCH:
            busy.append((end, end + BREAK_MINUTES, False))  # reserved breather
        placed.append(task)
    return placed, overflow


def reorder(tasks, new_ids, moved_id):
    """Re-time scheduled tasks after one was dragged to a new spot on the timeline.

    `tasks` are the scheduled tasks in current timeline order, `new_ids` the same
    ids in their dropped order and `moved_id` the one that was dragged. The moved
    task starts when the one above it ends (or where the one below it started, if
    dropped at the top). Tasks after it are pushed later only as far as needed to
    stop overlapping; everything else keeps its time. Returns the changed tasks.
    """
    by_id = {t.id: t for t in tasks}
    if sorted(by_id) != sorted(new_ids) or len(new_ids) != len(set(new_ids)) or moved_id not in by_id:
        raise ValueError("order must list every scheduled task exactly once")
    pos = new_ids.index(moved_id)
    moved = by_id[moved_id]

    if pos > 0:
        above = by_id[new_ids[pos - 1]]
        start = to_min(above.start_time) + (above.duration_minutes or 0)
    elif len(new_ids) > 1:
        start = to_min(by_id[new_ids[1]].start_time)
    else:
        return []

    changed = []
    if to_min(moved.start_time) != start:
        moved.start_time = to_time(start)
        changed.append(moved)
    cursor = start + (moved.duration_minutes or 0)
    for tid in new_ids[pos + 1:]:
        t = by_id[tid]
        if to_min(t.start_time) >= cursor:
            break  # no overlap from here on, so the rest of the day keeps its times
        t.start_time = to_time(cursor)
        changed.append(t)
        cursor += t.duration_minutes or 0
    return changed


def timeline_order(tasks):
    """Scheduled tasks in the order the timeline shows them."""
    return sorted(
        (t for t in tasks if t.start_time is not None),
        key=lambda t: (t.start_time, t.duration_minutes is not None, t.priority, t.order, t.id or 0),
    )


def capacity(plan, tasks):
    """Minutes available vs. minutes committed for the day."""
    window = max(0, to_min(plan.day_end) - to_min(plan.day_start))
    timed = [t for t in tasks if t.duration_minutes is not None]
    committed = sum(t.duration_minutes for t in timed if not t.done)
    done = sum(t.duration_minutes for t in timed if t.done)
    load = committed + done
    pct = round(100 * load / window) if window else 0
    return {
        "window": window,
        "committed": committed,
        "load": load,
        "pct": pct,
        "bar_pct": min(pct, 100),
        "over": load > window,
        "tight": 85 <= pct <= 100,
        "free": max(0, window - load),
        "untimed": sum(1 for t in tasks if t.duration_minutes is None and not t.done),
        "over_by": max(0, load - window),
    }


def timeline(plan, tasks, now_minutes=None):
    """Scheduled items in order, with free gaps between them."""
    items = timeline_order(tasks)
    rows, cursor = [], to_min(plan.day_start)
    for t in items:
        s, e = to_min(t.start_time), t.end_minutes
        if s - cursor >= 15:
            rows.append({"gap": True, "minutes": s - cursor, "start": to_time(cursor)})
        if t.duration_minutes is None:  # checkpoint: a moment, takes no room
            rows.append({"gap": False, "marker": True, "task": t,
                         "past": now_minutes is not None and s <= now_minutes})
            cursor = max(cursor, s)
            continue
        rows.append({
            "gap": False,
            "task": t,
            "end": to_time(e),
            "now": now_minutes is not None and s <= now_minutes < e,
            "past": now_minutes is not None and e <= now_minutes,
            "clash": s < cursor,
            "outside": s < to_min(plan.day_start) or e > to_min(plan.day_end),
        })
        cursor = max(cursor, e)
    end = to_min(plan.day_end)
    if items and end - cursor >= 15:
        rows.append({"gap": True, "minutes": end - cursor, "start": to_time(cursor)})
    return rows
