"""Editorial calendar: fixed slots, filled in order of strength."""

from datetime import date, datetime, timedelta

from . import store

# Weekday (0=Monday) and time. Evening slots: a technical audience scrolls
# after dinner.
DEFAULT_SLOTS = [(1, "19:30"), (3, "19:30"), (5, "11:00")]


def _slots_from(start: datetime, count: int, slots=DEFAULT_SLOTS) -> list[datetime]:
    out, day = [], start.date()
    guard = 0
    while len(out) < count and guard < 120:
        guard += 1
        for weekday, hhmm in slots:
            if day.weekday() != weekday:
                continue
            h, m = (int(x) for x in hhmm.split(":"))
            when = datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m)
            if when > start:
                out.append(when)
        day += timedelta(days=1)
    return out[:count]


def taken() -> set[str]:
    return {
        p["schedule"]["at"] for p in store.all_posts()
        if p.get("schedule", {}).get("at")
    }


def autoschedule(posts: list[dict], start: datetime | None = None) -> list[dict]:
    """Give each post the first free slot, strongest first."""
    start = start or datetime.now()
    busy = taken()
    ordered = sorted(posts, key=lambda p: -(p.get("strength") or 0))
    slots = [s for s in _slots_from(start, len(ordered) + len(busy) + 6)
             if s.isoformat(timespec="minutes") not in busy]

    scheduled = []
    for post, when in zip(ordered, slots):
        post["schedule"] = {"at": when.isoformat(timespec="minutes")}
        if post.get("status") in ("draft", "ready"):
            post["status"] = "scheduled"
        store.save_post(post)
        scheduled.append(post)
    return scheduled


def schedule_one(post: dict, when: str) -> dict:
    post["schedule"] = {"at": _parse(when).isoformat(timespec="minutes")}
    if post.get("status") in ("draft", "ready", "idea"):
        post["status"] = "scheduled"
    store.save_post(post)
    return post


def _parse(when: str) -> datetime:
    when = when.strip().lower()
    now = datetime.now()
    if when in ("oggi", "today"):
        return now.replace(hour=19, minute=30, second=0, microsecond=0)
    if when in ("domani", "tomorrow"):
        return (now + timedelta(days=1)).replace(hour=19, minute=30, second=0, microsecond=0)
    # Year-less forms get the current year appended before parsing: strptime
    # alone would land on 1900 (and choke on February 29).
    attempts = [(when, "%Y-%m-%dT%H:%M"), (when, "%Y-%m-%d %H:%M"), (when, "%Y-%m-%d"),
                (f"{when}/{now.year}", "%d/%m %H:%M/%Y"), (f"{when}/{now.year}", "%d/%m/%Y")]
    for text, fmt in attempts:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.hour == 0 and parsed.minute == 0:
            parsed = parsed.replace(hour=19, minute=30)
        return parsed
    raise SystemExit(f"Can't parse the date {when!r}. Use 2026-08-12 19:30, 12/08 (day/month), today, tomorrow.")


def upcoming(limit: int = 20) -> list[dict]:
    posts = [p for p in store.all_posts() if p.get("schedule", {}).get("at")]
    posts.sort(key=lambda p: p["schedule"]["at"])
    return posts[:limit]


def due(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    return [
        p for p in store.all_posts()
        if p.get("status") == "scheduled"
        and p.get("schedule", {}).get("at", "9999") <= now.isoformat(timespec="minutes")
    ]


def render_calendar(limit: int = 20) -> str:
    posts = upcoming(limit)
    if not posts:
        return "Calendar is empty. `igforge auto` fills it."
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    lines, current = [], None
    today = date.today()
    for p in posts:
        when = datetime.fromisoformat(p["schedule"]["at"])
        if when.date() != current:
            current = when.date()
            delta = (current - today).days
            rel = "today" if delta == 0 else ("tomorrow" if delta == 1 else f"in {delta}d")
            lines.append(f"\n{weekdays[current.weekday()]} {current.strftime('%d/%m')}  ({rel})")
        mark = {"published": "✓", "scheduled": "·", "ready": "·"}.get(p.get("status"), "○")
        lines.append(f"  {when:%H:%M} {mark} [{p.get('format','')[:8]:<8}] {p['hook'][:62]}")
        lines.append(f"          {p['id']}")
    return "\n".join(lines).lstrip("\n")
