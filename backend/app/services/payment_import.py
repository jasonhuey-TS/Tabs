"""Reading a payments file (a Zylo export, Spendflo transactions, any CSV) and deciding what to import.

Everything here is pure: text in, plan out. Nothing touches the database, so every rule can be tested.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from difflib import SequenceMatcher

MAX_ROWS = 100_000
MAX_CENTS = 100_000_000_000                      # $1 billion in one payment is a typo, not a payment
FIELDS = ("date", "amount", "vendor", "type", "reference", "currency", "external_id")
REQUIRED = ("date", "amount", "vendor")

# header (letters and digits only, lower-case) -> field, most likely first
SYNONYMS = {
    "date": ("paymentdate", "paiddate", "paidon", "transactiondate", "posteddate", "date", "invoicedate", "settlementdate"),
    "amount": ("paymentamount", "amountusd", "amount", "totalamount", "paidamount", "total", "value"),
    "vendor": ("applicationname", "application", "appname", "app", "vendorname", "vendor", "suppliername", "supplier",
               "productname", "product", "payee", "merchant"),
    "type": ("paymenttype", "type", "paymentsource", "kind", "category"),
    "reference": ("referencenumber", "reference", "invoicenumber", "invoiceno", "invoice", "ref", "memo", "description"),
    "currency": ("currencycode", "currency", "ccy"),
    "external_id": ("paymentid", "transactionid", "txnid", "externalid", "id", "uuid"),
}
COMPANY_WORDS = {"inc", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "gmbh", "plc", "sa", "ag", "bv", "pty", "pte", "lp", "llp"}
EXPENSE_HINTS = ("expense", "card", "reimburs", "concur", "brex", "ramp", "amex", "pcard")
AP_HINTS = ("ap", "accountspayable", "payable", "bill", "invoice", "wire", "ach", "check", "cheque")
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%d %b %Y", "%m-%d-%Y",
                "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p")


def norm_header(header) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header or "").lower())


def header_keys(header) -> list:
    """Names a header can be recognised by: the header itself, plus what follows a source prefix such as 'okta_'
    (so 'okta_lastActivityDate' is also read as 'lastActivityDate')."""
    keys = [norm_header(header)]
    if "_" in str(header or ""):
        rest = norm_header(str(header).split("_", 1)[1])
        if rest and rest not in keys:
            keys.append(rest)
    return keys


def index_headers(headers) -> dict:
    """normalised name -> header. Exact names always beat prefix-stripped ones."""
    by_norm = {}
    for h in headers:
        by_norm.setdefault(header_keys(h)[0], h)
    for h in headers:
        for key in header_keys(h)[1:]:
            by_norm.setdefault(key, h)
    return by_norm


def parse_csv(text: str):
    """(headers, rows as dicts). Handles a UTF-8 BOM, quotes, and Excel-style delimiters."""
    text = (text or "").lstrip("\ufeff")
    if not text.strip():
        return [], []
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return [], []
    headers = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:MAX_ROWS + 1]:
        out.append({h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(headers) if h})
    return [h for h in headers if h], out


def detect_mapping(headers) -> dict:
    """Guess which column is which. Each column is used at most once."""
    by_norm, mapping, used = index_headers(headers), {}, set()
    for field in FIELDS:
        for synonym in SYNONYMS[field]:
            header = by_norm.get(synonym)
            if header and header not in used:
                mapping[field] = header
                used.add(header)
                break
    return mapping


def parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text, text.replace("T", " ").split(".")[0].rstrip("Z"), text[:10]]
    for candidate in candidates:
        for fmt in DATE_FORMATS:
            try:
                parsed = datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
            if 1990 <= parsed.year <= 2100:
                return parsed
    return None


def parse_amount(value):
    """Cents as an int, or None. Handles $1,234.50, (1,234.50) as negative, 1234.5-, 'USD 12'."""
    text = str(value or "").strip()
    if not text:
        return None
    negative = (text.startswith("(") and text.endswith(")")) or text.endswith("-") or text.startswith("-")
    cleaned = re.sub(r"[^0-9.]", "", text.replace(",", ""))
    if cleaned.count(".") > 1 or not re.search(r"\d", cleaned):
        return None
    try:
        cents = int((Decimal(cleaned) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return None
    if cents > MAX_CENTS:
        return None
    return -cents if negative else cents


def classify_type(value, default="ap") -> str:
    text = norm_header(value)
    if not text:
        return default
    if any(h in text for h in EXPENSE_HINTS):
        return "expense"
    if text in AP_HINTS or text.startswith(("appayment", "accountspayable")) or any(h in text for h in ("payable", "invoice", "bill")):
        return "ap"
    return default


def normalize_vendor(name) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", str(name or "").lower().replace("&", " and "))
    words = [w for w in text.split() if w not in COMPANY_WORDS]
    return " ".join(words)


def _external_id(explicit, app_id, paid_on, cents, ptype, reference, seen: Counter) -> str:
    if explicit:
        return f"csv:{explicit.strip()}"[:255]
    base = hashlib.sha1(f"{app_id}|{paid_on}|{cents}|{ptype}|{(reference or '').lower()}".encode()).hexdigest()[:30]
    n = seen[base]
    seen[base] += 1
    return f"h:{base}:{n}"                           # identical rows in one file stay distinct, and re-importing the file reproduces the same ids


def _similarity(a: str, b: str) -> float:
    """How alike two normalised names are. All the words of the shorter one appearing in the longer one counts as a
    strong (but still only suggested) match: 'gong' vs 'gong technologies'."""
    ratio = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    return max(ratio, 0.85) if ta and tb and (ta <= tb or tb <= ta) else ratio


def plan_import(rows, mapping: dict, default_type: str, apps, aliases: dict, decisions: dict) -> dict:
    """What would happen if we imported these rows?

    apps: [(id, name, vendor)]; aliases: {normalised vendor: app id}; decisions: {raw vendor: app id | "skip"}.
    Returns ready rows, invalid rows (with reasons), unmatched vendors (with suggestions) and counts.
    """
    missing = [f for f in REQUIRED if not mapping.get(f)]
    if missing:
        return {"error": f"Choose a column for: {', '.join(missing)}.", "ready": [], "invalid": [], "unmatched": [], "skipped": 0}

    lookup, ambiguous = {}, set()
    for app_id, name, vendor in apps:
        for label in (name, vendor):
            key = normalize_vendor(label)
            if not key:
                continue
            if key in lookup and lookup[key] != str(app_id):
                ambiguous.add(key)
            lookup[key] = str(app_id)
    names = {str(i): n for i, n, _v in apps}

    ready, invalid, skipped, seen = [], [], 0, Counter()
    unmatched = defaultdict(lambda: {"rows": 0, "total_cents": 0})
    for index, row in enumerate(rows, start=2):                      # row 1 is the header
        vendor_raw = (row.get(mapping["vendor"]) or "").strip()
        paid_on, cents = parse_date(row.get(mapping["date"])), parse_amount(row.get(mapping["amount"]))
        if not vendor_raw:
            invalid.append({"row": index, "reason": "No application / vendor"}); continue
        if paid_on is None:
            invalid.append({"row": index, "reason": f"Can't read the date “{row.get(mapping['date'], '')}”"}); continue
        if cents is None or cents == 0:
            invalid.append({"row": index, "reason": f"Can't read the amount “{row.get(mapping['amount'], '')}”" if cents is None else "The amount is zero"}); continue

        key = normalize_vendor(vendor_raw)
        decision = decisions.get(vendor_raw)
        if decision == "skip":
            skipped += 1; continue
        app_id = decision or aliases.get(key) or (lookup.get(key) if key not in ambiguous else None)
        if not app_id:
            u = unmatched[vendor_raw]; u["rows"] += 1; u["total_cents"] += cents
            continue
        ptype = classify_type(row.get(mapping.get("type", ""), ""), default_type)
        currency = (row.get(mapping.get("currency", ""), "") or "USD").strip().upper()
        currency = currency if re.fullmatch(r"[A-Z]{3}", currency) else "USD"
        reference = (row.get(mapping.get("reference", ""), "") or "").strip()[:255] or None
        explicit = (row.get(mapping.get("external_id", ""), "") or "").strip()
        ready.append({"app_id": app_id, "app": names.get(app_id), "paid_on": paid_on, "amount_cents": cents, "currency": currency,
                      "payment_type": ptype, "reference": reference, "vendor_raw": vendor_raw, "row": index,
                      "external_id": _external_id(explicit, app_id, paid_on, cents, ptype, reference, seen)})

    suggestions = {}
    norm_names = [(str(i), n, normalize_vendor(n)) for i, n, _v in apps]
    for vendor_raw in list(unmatched)[:200]:
        key = normalize_vendor(vendor_raw)
        scored = sorted(((_similarity(key, nn), i, n) for i, n, nn in norm_names if nn), reverse=True)[:3]
        suggestions[vendor_raw] = [{"app_id": i, "name": n, "score": round(s, 2)} for s, i, n in scored if s >= 0.6]
    unmatched_list = sorted(({"vendor": v, "rows": d["rows"], "total_cents": d["total_cents"], "suggestions": suggestions.get(v, [])}
                             for v, d in unmatched.items()), key=lambda u: -abs(u["total_cents"]))
    return {"error": None, "ready": ready, "invalid": invalid, "unmatched": unmatched_list, "skipped": skipped}
