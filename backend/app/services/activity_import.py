"""Filling in older 'last activity' dates from another tool's export (e.g. Zylo's Users table).

Okta only keeps 90 days of sign-ins, so people whose last activity was longer ago show 'No activity'. Another tool
that has watched longer can supply those dates. The rules keep that safe:

  * a date only ever moves FORWARD (or fills a gap) - never back, so real sign-ins always win
  * only people already assigned to the app are touched, nobody is added
  * the same day counts as unchanged, so re-importing a file changes nothing
  * dates in the future, unreadable dates and rows with no email are reported, not guessed at

Pure functions: text in, plan out.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from app.services.payment_import import norm_header, parse_date

SYNONYMS = {
    "email": ("loginemail", "email", "emailaddress", "useremail", "workemail", "username", "login"),
    "date": ("lastactivitydate", "lastactivity", "lastactive", "lastlogin", "lastlogindate", "lastsignin", "lastseen", "lastaccessed", "lastused"),
}


def detect_columns(headers) -> dict:
    by_norm = {}
    for h in headers:
        by_norm.setdefault(norm_header(h), h)
    out = {}
    for field, names in SYNONYMS.items():
        for name in names:
            if name in by_norm:
                out[field] = by_norm[name]
                break
    return out


def _noon(day: date) -> datetime:
    return datetime.combine(day, time(12, 0), tzinfo=timezone.utc)


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def plan_activity_import(rows, mapping: dict, assigned: dict, today: date) -> dict:
    """assigned: {lower-case email: current last activity (datetime or None)} for people assigned to the app."""
    missing = [f for f in ("email", "date") if not mapping.get(f)]
    if missing:
        return {"error": "Choose a column for: " + ", ".join("email" if f == "email" else "last activity date" for f in missing) + ".",
                "updates": [], "unchanged": 0, "no_date": 0, "not_assigned": [], "invalid": [], "merged": 0, "rows": len(rows)}
    invalid, no_date, merged = [], 0, 0
    best = {}                                              # email -> (date, row number): the latest date in the file wins
    for index, row in enumerate(rows, start=2):
        email = (row.get(mapping["email"]) or "").strip().lower()
        raw = (row.get(mapping["date"]) or "").strip()
        if "@" not in email:
            invalid.append({"row": index, "reason": "No email address"}); continue
        if raw in ("", "-", "—", "n/a", "N/A", "none", "None"):
            no_date += 1; continue
        day = parse_date(raw)
        if day is None:
            invalid.append({"row": index, "reason": f"Can't read the date “{raw}”"}); continue
        if day > today + timedelta(days=1):
            invalid.append({"row": index, "reason": f"The date {day.isoformat()} is in the future"}); continue
        if email in best:
            merged += 1
        if email not in best or day > best[email][0]:
            best[email] = (day, index)

    updates, unchanged, not_assigned = [], 0, []
    for email, (day, index) in best.items():
        if email not in assigned:
            not_assigned.append({"email": email, "row": index}); continue
        current = _aware(assigned[email])
        if current is None or day > current.date():
            updates.append({"email": email, "new": _noon(day), "old": current, "row": index})
        else:
            unchanged += 1
    return {"error": None, "updates": updates, "unchanged": unchanged, "no_date": no_date, "not_assigned": not_assigned,
            "invalid": invalid, "merged": merged, "rows": len(rows)}
