"""Quick-add syntax for the brain dump box.

One task per line. Optional markers, in any order:
  !Title          must-do        ?Title   could-do (default: should-do)
  45m / 1.5h      duration       @9:30 / @2pm   fixed start time
  (no length = anytime task, or a checkpoint if it has a time)
  #deep #admin #call #personal   category       #frog   hardest task first
"""
import re
from datetime import time

from .models import Category, Priority

DURATION_RE = re.compile(r"(?<!\S)(\d+(?:\.\d+)?)\s?(h|hr|hrs|hours?|m|mins?|minutes?)(?!\S)", re.I)
TIME_RE = re.compile(r"(?<!\S)@(\d{1,2})(?::(\d{2}))?\s?(am|pm|a|p)?(?!\S)", re.I)
TAG_RE = re.compile(r"(?<!\S)#(\w+)")

TAGS = {
    "deep": Category.DEEP, "focus": Category.DEEP,
    "admin": Category.ADMIN, "email": Category.ADMIN,
    "call": Category.MEETING, "meet": Category.MEETING, "meeting": Category.MEETING,
    "personal": Category.PERSONAL, "life": Category.PERSONAL,
}
MEETING_WORDS = {"call", "meeting", "meet", "zoom", "interview", "1:1", "sync", "standup"}
ADMIN_WORDS = {"email", "emails", "inbox", "invoice", "invoices", "reply", "pay", "book", "schedule", "update"}
DEEP_WORDS = {"write", "build", "design", "plan", "draft", "proposal", "strategy", "research", "code", "study", "prep", "deck", "finish", "analyse", "analyze"}


def parse_line(line):
    text = line.strip().lstrip("-*• ").strip()
    if not text:
        return None

    priority = Priority.SHOULD
    if text.startswith("!"):
        priority, text = Priority.MUST, text.lstrip("!").strip()
    elif text.startswith("?"):
        priority, text = Priority.COULD, text.lstrip("?").strip()

    duration, start, category, frog = None, None, None, False

    m = DURATION_RE.search(text)
    if m:
        value, unit = float(m.group(1)), m.group(2).lower()
        duration = int(round(value * 60)) if unit.startswith("h") else int(value)
        text = text[: m.start()] + text[m.end():]

    m = TIME_RE.search(text)
    if m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if ampm.startswith("p") and hour < 12:
            hour += 12
        elif ampm.startswith("a") and hour == 12:
            hour = 0
        elif not ampm and 1 <= hour <= 6:
            hour += 12  # "@3" almost always means 3pm
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            start = time(hour, minute)
            text = text[: m.start()] + text[m.end():]

    for tag in TAG_RE.findall(text):
        key = tag.lower()
        if key == "frog":
            frog = True
        elif key in TAGS:
            category = TAGS[key]
    text = TAG_RE.sub(lambda m: "" if m.group(1).lower() in TAGS or m.group(1).lower() == "frog" else m.group(0), text)

    title = re.sub(r"\s{2,}", " ", text).strip(" ,-")
    if not title:
        return None

    if category is None:
        words = set(re.findall(r"[\w:]+", title.lower()))
        if words & MEETING_WORDS:
            category = Category.MEETING
        elif words & DEEP_WORDS:
            category = Category.DEEP
        elif words & ADMIN_WORDS:
            category = Category.ADMIN
        else:
            category = Category.ADMIN

    return {
        "title": title[:200],
        "priority": priority,
        "category": category,
        "duration_minutes": None if duration is None else max(5, min(duration, 600)),
        "start_time": start,
        "is_frog": frog,
    }
