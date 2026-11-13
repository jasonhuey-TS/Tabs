"""How a record from Zylo's API becomes a field in Tab. Pure functions: no database, no network."""
import hashlib
import json
import re
from datetime import date

INT_MAX = 2_147_483_647          # Tab stores money as whole cents in a 32-bit column


def clean(value, limit=255):
    text = " ".join(str(value or "").split())
    return text[:limit] or None


def day(value):
    """'2026-03-01' or '2026-03-01 10:00:00' -> a date; anything else -> None."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def cents(value):
    """'12,500.50' -> 1250050. None for blanks, junk, or an amount too big for Tab to store."""
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None
    if n != n or abs(n * 100) > INT_MAX:
        return None
    return int(round(n * 100))


def notice_days(end, deadline, text):
    """Days of notice needed to cancel. The cancel-by date Zylo works out is the most reliable; otherwise read '60 days', '3 months' ..."""
    if end and deadline and deadline < end:
        return (end - deadline).days
    m = re.search(r"(\d+)\s*(day|week|month|year)?", str(text or "").lower())
    if not m:
        return None
    total = int(m[1]) * {"day": 1, "week": 7, "month": 30, "year": 365}[m[2] or "day"]
    return total if 0 < total <= 3650 else None


def fingerprint(obj) -> str:
    """A short fingerprint of what was last synced, so unchanged records are skipped next time."""
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def contract_fields(zc, company_currency="USD") -> dict:
    """A Zylo contract -> the fields of a Tab contract. 'Inactive' in Zylo only means it hasn't started yet, which Tab shows as active."""
    start, end = day(zc.get("start_date")), day(zc.get("end_date"))
    native = str(zc.get("native_currency") or "").upper()
    if len(native) == 3 and zc.get("native_total_contract_value") not in (None, ""):
        value, currency = cents(zc.get("native_total_contract_value")), native
    else:
        value, currency = cents(zc.get("total_contract_value")), (str(company_currency or "USD").upper()[:3] or "USD")
    bits = [f"Synced from Zylo (source: {clean(zc.get('source')) or 'unknown'})."]
    for label, key in (("Contract", "name"), ("Number", "number"), ("Supplier", "supplier_name"), ("Reseller", "reseller"), ("Owner in Zylo", "owner"),
                       ("Billing", "billing_frequency"), ("Renewal", "renewal_state")):
        if clean(zc.get(key)):
            bits.append(f"{label}: {clean(zc.get(key))}.")
    return {
        "status": "expired" if str(zc.get("status") or "").lower() == "expired" else "active",
        "start_date": start, "end_date": end,
        "auto_renews": bool(zc.get("month_to_month")),
        "cancellation_notice_days": notice_days(end, day(zc.get("notification_deadline_date")), zc.get("notification_period")),
        "total_value_cents": value, "currency": currency,
        "notes": " ".join(bits)[:2000],
    }


def payment_fields(zp):
    """A Zylo payment -> the fields of a Tab payment, or None if it has no usable date or amount."""
    paid_on, amount = day(zp.get("payment_date")), cents(zp.get("amount"))
    if paid_on is None or amount is None:
        return None
    kind = "ap" if str(zp.get("payment_type") or "").strip().lower() in ("ap", "reseller") else "expense"
    po = clean(zp.get("external_po_number"), 60)
    reference = " · ".join(x for x in (clean(zp.get("supplier_name"), 120), clean(zp.get("expense_type"), 80), f"PO {po}" if po else None) if x)[:255] or None
    return {"paid_on": paid_on, "amount_cents": amount, "payment_type": kind, "reference": reference}


def function_names(stats_row) -> list:
    """The function names from an application's stats row (a list of strings, or of {name: ...})."""
    out, seen = [], set()
    for item in (stats_row or {}).get("active_functionalities") or []:
        name = clean(item.get("name") if isinstance(item, dict) else item, 120)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out[:10]
