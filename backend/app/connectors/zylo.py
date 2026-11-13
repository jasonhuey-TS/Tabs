"""
Zylo - keeps Tab's apps, contracts and spend current from Zylo's Enterprise API, every night, with no uploads.

Zylo already receives contracts and spend from Spendflo, so this is also how Spendflo's data reaches Tab.
Read-only: nothing is written back to Zylo. It needs a Zylo token (Admin > Company Tokens) with the
applications:read, contracts:read and spend:read scopes. Each part works on its own: a missing scope only
leaves that part out, and the sync says so.
"""
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from .base import ConnectorError, Field, GlobalConnector, Guide, send
from .registry import register
from .zylo_map import day

BASE = "https://api.zylo.com"
PAGE = 1000
MAX_PAGES = 300                    # a guard, per list: 300,000 records


def auth_headers(cfg) -> dict:
    return {"Authorization": f"Bearer {str(cfg.get('token_id', '')).strip()}:{str(cfg.get('token_secret', '')).strip()}", "Accept": "application/json"}


def as_rows(data) -> list:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("data", "results", "items", "records"):
            if isinstance(data.get(key), list):
                return [r for r in data[key] if isinstance(r, dict)]
    return []


async def pages(client, cfg, path, params=None):
    """One page (a list of records) at a time. Zylo's cursor paging needs sort=id, and hands the next cursor back in the x-cursor header."""
    cursor, n = None, 0
    while True:
        p = {"sort": "id", "limit": PAGE, **(params or {})}
        if cursor:
            p["cursor"] = cursor
        resp = await send(client, "GET", BASE + path, params=p, headers=auth_headers(cfg))
        rows = as_rows(resp.json())
        if rows:
            yield rows
        cursor, n = resp.headers.get("x-cursor"), n + 1
        if len(rows) < PAGE or not cursor or n >= MAX_PAGES:
            return


async def fetch_all(client, cfg, path, params=None) -> list:
    out = []
    async for page in pages(client, cfg, path, params):
        out.extend(page)
    return out


async def load_cfg(db) -> dict:
    from sqlalchemy import select                        # database pieces load only when a sync runs
    from app.core.encryption import decrypt
    from app.models.connector_config import ConnectorConfig
    row = (await db.execute(select(ConnectorConfig).where(ConnectorConfig.key == "zylo"))).scalar_one_or_none()
    if not row or not row.config_encrypted:
        return {}
    try:
        return json.loads(decrypt(row.config_encrypted))
    except Exception:
        return {}


@register
class ZyloConnector(GlobalConnector):
    key = "zylo"
    name = "Zylo"
    vendor = "Zylo"
    description = ("Keeps every app's category, owners, contracts and spend current from Zylo's API each night. Includes whatever Spendflo feeds into Zylo. Read-only.")
    color = "#1F3B73"
    initials = "Zy"
    provides = ("App category, subcategory and functions", "App owners and department", "Contracts (dates, auto-renew, notice, value)", "Spend (payments)")
    not_ready_message = "Save your Zylo token first (Zylo Sync page)."
    fields = (
        Field("token_id", "Token ID"),
        Field("token_secret", "Token Secret", type="password", secret=True),
        Field("payments_from", "Sync spend from (optional)", required=False, placeholder="2026-01-01",
              help="The first date to load spend from, as YYYY-MM-DD. Set it to the first month Tab does not already hold, so nothing is counted twice."),
    )
    guide = Guide(
        steps=(
            "In Zylo, open Admin and the Company Tokens tab (you need Zylo admin permission), then choose Request Token.",
            "Give the token read access to applications, contracts and spend (applications:read, contracts:read, spend:read).",
            "Copy the Token ID and Token Secret straight away: the secret is shown only once.",
            "Paste both here. Leave 'Sync spend from' empty unless Tab already holds uploaded payments (then enter the first month it does not).",
        ),
        docs_url="https://developer.zylo.com/reference/api-key",
    )

    async def is_ready(self, db) -> bool:
        cfg = await load_cfg(db)
        return bool(cfg.get("token_id") and cfg.get("token_secret"))

    async def test(self, cfg, db=None) -> str:
        if not (cfg.get("token_id") and cfg.get("token_secret")):
            raise ConnectorError("Add your Zylo Token ID and Token Secret first.")
        async with self.make_client() as client:
            company = await self._company(client, cfg)
            access = {}
            for label, path in (("apps", "/v2/applications"), ("contracts", "/v2/contracts"), ("spend", "/v2/payments")):
                try:
                    await send(client, "GET", BASE + path, params={"limit": 1}, headers=auth_headers(cfg))
                    access[label] = True
                except ConnectorError:
                    access[label] = False
        name = company.get("name")
        message = "Connected to Zylo" + (f" ({name})" if name else "") + "."
        missing = [k for k, ok in access.items() if not ok]
        if len(missing) == 3:
            raise ConnectorError("Zylo accepted the token but it can't read apps, contracts or spend. Give it the applications:read, contracts:read and spend:read scopes.")
        if missing:
            message += f" The token can't read {', '.join(missing)} yet: add the matching read scope to get that data."
        return message

    async def _company(self, client, cfg) -> dict:
        data = (await send(client, "GET", BASE + "/v2/company", headers=auth_headers(cfg))).json()
        rows = as_rows(data)
        return rows[0] if rows else (data if isinstance(data, dict) else {})

    async def run(self, db, state, progress):
        from . import zylo_apply
        cfg = await load_cfg(db)
        if not (cfg.get("token_id") and cfg.get("token_secret")):
            raise ConnectorError(self.not_ready_message)
        state, notes, new_state = dict(state or {}), [], {}
        today = datetime.now(timezone.utc).date()
        summary = {}

        async with self.make_client() as client:
            currency = str((await self._company(client, cfg)).get("currency") or "USD").upper()
            await progress("Reading apps from Zylo...")
            zapps = await fetch_all(client, cfg, "/v2/applications")                 # a refused token fails the sync here, with Zylo's own message
            stats = {}
            try:
                stats = {str(r.get("id")): r for r in await fetch_all(client, cfg, "/v2/applicationStats")}
            except ConnectorError:
                notes.append("App functions weren't collected: the Zylo token also needs the spend and contracts read scopes.")

            await progress(f"Matching {len(zapps):,} Zylo apps to Tab apps...")
            matched = await zylo_apply.match_apps(db, zapps)
            details = await zylo_apply.apply_app_details(db, zapps, stats, matched["app_map"])
            await progress("Reading contracts from Zylo...")
            contracts = {}
            try:
                zcontracts = await fetch_all(client, cfg, "/v2/contracts")
                contracts = await zylo_apply.apply_contracts(db, zcontracts, matched["app_map"], currency)
            except ConnectorError:
                notes.append("Contracts weren't collected: add the contracts:read scope to the Zylo token.")
            await progress("Reading spend from Zylo...")
            payments = await self._payments(db, client, cfg, state, matched["app_map"], currency, notes, new_state, today)

        summary.update(apps=matched["total"], apps_matched=matched["matched"], apps_new_matches=matched["new_matches"], apps_unmatched=matched["unmatched"], apps_ignored=matched["ignored"],
                       **details, contracts=contracts, payments=payments, notes=notes)
        if matched["unmatched"]:
            notes.append(f"{matched['unmatched']:,} Zylo apps couldn't be matched to a Tab app by name. Match them once on the Zylo Sync page.")
        if contracts.get("skipped_several_apps"):
            notes.append(f"{contracts['skipped_several_apps']:,} Zylo contracts cover several apps through line items and weren't imported.")
        parts = [f"{matched['matched']:,} of {matched['total']:,} Zylo apps matched", f"{details.get('categories_set', 0):,} categories and {details.get('apps_filled', 0):,} apps filled in"]
        if contracts:
            parts.append(f"contracts: {contracts.get('created', 0):,} new, {contracts.get('updated', 0):,} updated")
        if payments:
            parts.append(f"spend: {payments.get('added', 0):,} new payments")
        summary["message"] = "Zylo sync: " + "; ".join(parts) + "." + (f" Note: {' '.join(notes)}" if notes else "")
        new_state["last_run"] = today.isoformat()
        return summary, new_state

    async def _payments(self, db, client, cfg, state, app_map, currency, notes, new_state, today):
        """Spend, guarded so it can never count the same money twice: the first run waits for a start date if Tab already holds uploads."""
        from . import zylo_apply
        if currency != "USD":
            notes.append(f"Spend wasn't synced: Zylo reports in {currency}, and Tab's spend totals are in US dollars.")
            return None
        first = not state.get("payments_ready")
        start = day(cfg.get("payments_from"))
        if first and start is None:
            held = await zylo_apply.count_other_payments(db)
            if held:
                notes.append(f"Spend wasn't synced yet: Tab already holds {held:,} uploaded payments, and loading Zylo's copy too would count them twice. "
                             "Enter 'Sync spend from' (the first month Tab does not already hold) on the Zylo Sync page, then sync again.")
                return None
        params = {}
        if start:
            params["payment_date"] = f"{start.isoformat()},gte"
        if not first and state.get("payments_since"):
            params["zylo_modified_at"] = f"{state['payments_since']},gte"            # later runs only look at what changed
        existing = await zylo_apply.load_synced_payments(db)
        out, batch = {"added": 0, "corrected": 0, "unmatched": 0, "unmatched_cents": 0, "skipped_unreadable": 0}, f"zylo-{today.isoformat()}"
        counter = Counter()
        try:
            async for page in pages(client, cfg, "/v2/payments", params):
                await zylo_apply.apply_payments_page(db, page, app_map, existing, counter, batch)
        except ConnectorError:
            notes.append("Spend wasn't synced: add the spend:read scope to the Zylo token.")
            return None
        out.update({k: counter[k] for k in out})
        new_state["payments_ready"] = True
        new_state["payments_since"] = (today - timedelta(days=2)).isoformat()
        if out["unmatched"]:
            notes.append(f"{out['unmatched']:,} Zylo payments (${out['unmatched_cents'] / 100:,.0f}) belong to apps not matched to Tab yet.")
        return out
