"""Putting categories and functions on apps from another tool's export (e.g. Zylo's Applications table).

Two labels per app:
  category  one of Tab's 12 broad categories (productivity, crm, devtools ...)
  function  a finer label such as 'Video conferencing' or 'Project management', kept as written; it is what lets Tab spot
            redundant tools (two apps doing the same job)

The other tool's category names won't match Tab's 12, so each distinct value gets a suggested Tab category that the person can change
before anything is saved. Existing choices are protected: by default only apps still on 'other' get a category, and only apps with no
function get one. Pure functions: rows in, plan out.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from app.services.payment_import import _similarity, index_headers, normalize_vendor

CATEGORIES = ["productivity", "communication", "security", "devtools", "hr", "finance", "crm", "marketing", "analytics", "infrastructure", "design", "other"]
LABELS = {"productivity": "Productivity", "communication": "Communication", "security": "Security", "devtools": "Developer tools", "hr": "HR", "finance": "Finance",
          "crm": "CRM & sales", "marketing": "Marketing", "analytics": "Analytics", "infrastructure": "Infrastructure", "design": "Design", "other": "Other"}
MAX_FUNCTION = 120
MAX_FUNCTIONS = 10

SYNONYMS = {
    "name": ("applicationname", "applicationlabel", "applabel", "appname", "application", "app", "label", "name", "productname", "product", "vendorname", "vendor"),
    "category": ("applicationcategory", "appcategory", "category", "categories", "primarycategory"),
    "subcategory": ("applicationsubcategory", "appsubcategory", "subcategory", "subcategories", "secondarycategory"),
    "function": ("applicationfunctions", "applicationfunction", "appfunctions", "appfunction", "primaryfunction", "functions", "function", "functionalcategory"),
}
# first match wins, so the more specific topics come first ('email marketing' is marketing, not communication)
RULES = (
    ("security", ("security", "identity", "iam", "sso", "password", "compliance", "grc", "vulnerab", "endpoint", "privacy", "threat", "siem")),
    ("crm", ("crm", "sales", "customer relationship", "revenue", "cpq", "customer success", "customer support", "customer service", "helpdesk", "help desk", "ticketing")),
    ("marketing", ("marketing", "advertis", "seo", "social media", "campaign", "brand", "public relations", "events", "webinar", "content management")),
    ("finance", ("financ", "account", "expense", "billing", "invoice", "procurement", "tax", "treasury", "payment", "spend", "budget", "payroll")),
    ("hr", ("human resource", "hr", "recruit", "talent", "benefit", "onboarding", "learning", "training", "employee", "workforce", "performance", "people")),
    ("devtools", ("develop", "engineering", "code", "devops", "ci/cd", "api", "testing", "version control", "git", "ide", "qa", "software", "programming", "repository")),
    ("infrastructure", ("infrastructure", "cloud", "hosting", "database", "network", "it operations", "monitoring", "observability", "storage", "server", "backup", "device management", "mdm")),
    ("analytics", ("analytic", "business intelligence", "reporting", "dashboard", "visualiz", "data warehouse", "data science", "research", "survey", "data")),
    ("design", ("design", "creative", "graphic", "photo", "video editing", "video production", "prototyp", "ux", "animation", "illustration", "media", "presentation")),
    ("communication", ("communicat", "collaborat", "messaging", "meeting", "chat", "email", "voip", "telephony", "conferenc", "webcast", "intranet")),
    ("productivity", ("productiv", "project", "task", "office", "document", "note", "calendar", "workflow", "automation", "file", "knowledge", "wiki", "scheduling", "management")),
)


def detect_columns(headers) -> dict:
    by_norm, out, used = index_headers(headers), {}, set()
    for field, names in SYNONYMS.items():
        for name in names:
            header = by_norm.get(name)
            if header and header not in used:
                out[field] = header
                used.add(header)
                break
    return out


def _pattern(word: str):
    """Match at the start of a word, so 'develop' finds 'developer' but 'ide' can't be found inside 'video'; short words must be whole words."""
    whole = len(word) <= 3 or "/" in word
    return re.compile(r"(?<![a-z0-9])" + re.escape(word) + (r"(?![a-z0-9])" if whole else ""))


_COMPILED = [(category, [_pattern(w) for w in words]) for category, words in RULES]


def suggest_category(value) -> str:
    """Tab's category for another tool's category/function name; 'other' when nothing fits."""
    text = str(value or "").lower().strip()
    if not text:
        return "other"
    for category, patterns in _COMPILED:
        if any(p.search(text) for p in patterns):
            return category
    return "other"


def clean_function(value):
    text = " ".join(str(value or "").split())[:MAX_FUNCTION]
    return text or None


def split_functions(value) -> list:
    """'Expense Management; Accounting' -> ['Expense Management', 'Accounting']. Commas, semicolons, pipes and new lines separate; repeats are dropped."""
    out, seen = [], set()
    for part in re.split(r"[;|,\n\r]+", str(value or "")):
        fn = clean_function(part)
        if fn and fn.lower() not in seen:
            seen.add(fn.lower())
            out.append(fn)
    return out[:MAX_FUNCTIONS]


def driving_value(subcategory, category, functions) -> str:
    """Which of the other tool's names should decide Tab's category: the most specific one that actually means something.
    ('Accounting & Finance' beats 'Office'.) If none of them does, the first one given."""
    candidates = [v for v in (subcategory, category, functions[0] if functions else "") if v]
    for v in candidates:
        if suggest_category(v) != "other":
            return v
    return candidates[0] if candidates else ""


def plan_categories(rows, mapping: dict, apps, aliases: dict, decisions: dict, value_map: dict, overwrite: bool = False) -> dict:
    """apps: [(id, name, vendor, category value, subcategory, [functions])]; aliases: {normalised name: app id}; decisions: {raw name: app id | 'skip'};
    value_map: {the other tool's name: Tab category | ''} (anything missing falls back to the suggestion)."""
    cat_col, sub_col, fn_col = mapping.get("category"), mapping.get("subcategory"), mapping.get("function")
    if not mapping.get("name") or not (cat_col or sub_col or fn_col):
        return {"error": "Choose the column with the app name, and at least one of the category, subcategory or function columns.", "updates": [], "unmatched": [], "values": [],
                "unchanged": 0, "blank": 0, "duplicates": 0, "skipped": 0, "value_sources": []}
    lookup, ambiguous = {}, set()
    for app_id, name, vendor, *_ in apps:
        for label in (name, vendor):
            key = normalize_vendor(label)
            if key:
                if key in lookup and lookup[key] != str(app_id):
                    ambiguous.add(key)
                lookup[key] = str(app_id)
    current = {str(a[0]): a for a in apps}

    blank, skipped, duplicates = 0, 0, 0
    per_app = {}
    unmatched = defaultdict(lambda: {"rows": 0})
    value_counts = Counter()
    get = lambda row, col: (row.get(col) or "").strip() if col else ""
    for row in rows:
        raw = (row.get(mapping["name"]) or "").strip()
        if not raw:
            blank += 1
            continue
        sub, cat, fns = clean_function(get(row, sub_col)), get(row, cat_col), split_functions(get(row, fn_col))
        driver = driving_value(sub or "", cat, fns)
        if driver:
            value_counts[driver] += 1
        decision = decisions.get(raw)
        if decision == "skip":
            skipped += 1
            continue
        key = normalize_vendor(raw)
        app_id = decision or aliases.get(key) or (lookup.get(key) if key not in ambiguous else None)
        if not app_id or app_id not in current:
            unmatched[raw]["rows"] += 1
            continue
        if app_id in per_app:
            duplicates += 1
        entry = per_app.setdefault(app_id, {"category": "", "subcategory": None, "functions": []})
        entry["category"] = entry["category"] or (value_map.get(driver, suggest_category(driver)) if driver else "")      # the first non-empty value for an app wins
        entry["subcategory"] = entry["subcategory"] or sub
        entry["functions"] = entry["functions"] or fns

    updates, unchanged = [], 0
    for app_id, want in per_app.items():
        _id, name, _vendor, old_cat, old_sub, old_fns = current[app_id]
        old_cat, old_fns = (old_cat or "other"), list(old_fns or [])
        new_cat = want["category"] if want["category"] in CATEGORIES else ""
        set_cat = new_cat if new_cat and new_cat != old_cat and (old_cat == "other" or overwrite) else None
        set_sub = want["subcategory"] if want["subcategory"] and want["subcategory"] != (old_sub or None) and (not old_sub or overwrite) else None
        same = {f.lower() for f in want["functions"]} == {f.lower() for f in old_fns}
        set_fns = want["functions"] if want["functions"] and not same and (not old_fns or overwrite) else None
        if set_cat or set_sub or set_fns:
            updates.append({"app_id": app_id, "name": name, "category": set_cat, "subcategory": set_sub, "functions": set_fns,
                            "old_category": old_cat, "old_subcategory": old_sub or None, "old_functions": old_fns})
        else:
            unchanged += 1

    names = [(str(a[0]), a[1], normalize_vendor(a[1])) for a in apps]
    unmatched_list = []
    for raw, d in sorted(unmatched.items(), key=lambda kv: (-kv[1]["rows"], kv[0]))[:200]:
        key = normalize_vendor(raw)
        scored = sorted(((_similarity(key, nn), i, n) for i, n, nn in names if nn), reverse=True)[:3]
        unmatched_list.append({"name": raw, "rows": d["rows"], "suggestions": [{"app_id": i, "name": n, "score": round(sc, 2)} for sc, i, n in scored if sc >= 0.6]})
    values = [{"value": v, "count": c, "suggested": suggest_category(v), "chosen": value_map.get(v, suggest_category(v))} for v, c in value_counts.most_common(300)]
    return {"error": None, "updates": updates, "unchanged": unchanged, "unmatched": unmatched_list, "values": values, "blank": blank, "duplicates": duplicates,
            "skipped": skipped, "value_sources": [label for label, col in (("Subcategory", sub_col), ("Category", cat_col), ("Function", fn_col)) if col]}
