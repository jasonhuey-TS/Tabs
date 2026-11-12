"""Zoom - license type, last login, deactivated accounts; plus (each optional, each needing its own Zoom permission or plan)
role and group names, sign-in history, and what each person does in meetings they host."""
from collections import Counter
from datetime import datetime, timedelta, timezone

from .base import AttributeField, Connector, ConnectorError, Field, Guide, UserRecord, parse_dt, send
from .registry import register

# Zoom "type": 1 Basic, 2 Licensed, 4 Unassigned without Meetings Basic (no license).
_LICENSE = {1: "basic", 2: "licensed", 3: "on-prem", 4: "unassigned", 99: "none"}
WINDOWS = 3                  # Zoom's reports cover at most a month at a time, so 90 days is three back-to-back 30-day windows
WINDOW_DAYS = 30
MAX_PAGES = 400              # per window and per report: a guard so a huge account can't make a sync run forever
GROUP_MEETING_MIN_PEOPLE = 3  # a "group" meeting has three or more people (not a one-to-one call)


def _license_kind(user_type):
    """'Licensed', 'Basic', 'Licensed|Webinar500' ... -> 'licensed' | 'basic' | None (the add-ons after '|' don't change what the host is)."""
    t = str(user_type or "").lower().split("|")[0]
    if "basic" in t:
        return "basic"
    if any(w in t for w in ("licensed", "pro", "on-prem", "onprem")):
        return "licensed"
    return None


def _minutes(meeting) -> float:
    """How long a meeting ran, from its start and end times (the 'duration' text mixes mm:ss and hh:mm:ss, so it is only a fallback)."""
    start, end = parse_dt(meeting.get("start_time")), parse_dt(meeting.get("end_time"))
    if start and end and end >= start:
        return (end - start).total_seconds() / 60.0
    parts = str(meeting.get("duration") or "").split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return 0.0
    if len(nums) == 3:
        return nums[0] * 60 + nums[1] + nums[2] / 60.0
    if len(nums) == 2:
        return nums[0] + nums[1] / 60.0
    return 0.0


@register
class ZoomConnector(Connector):
    key = "zoom"
    name = "Zoom"
    vendor = "Zoom"
    description = "Which Zoom accounts hold a paid license, when each person last logged in, and (with extra permissions) how they use Zoom."
    color = "#2D8CFF"
    initials = "Zm"
    provides = ("License type", "Last login", "Deactivated accounts", "Account details", "Role and group names", "Sign-in history",
                "Meetings hosted, by license type", "Group-meeting averages and feature use")
    app_aliases = ("zoom",)
    fields = (
        Field("account_id", "Account ID"),
        Field("client_id", "Client ID"),
        Field("client_secret", "Client Secret", type="password", secret=True),
    )
    attribute_fields = (
        AttributeField("created_at", "Created At", "date"),
        AttributeField("status", "Account Status", "enum"),
        AttributeField("dept", "Department (in Zoom)", "enum"),
        AttributeField("role", "Role", "enum"),
        AttributeField("groups", "Groups", "text"),
        AttributeField("last_client_version", "Last Client Version", "enum"),
        AttributeField("verified", "Email Verified", "bool"),
        AttributeField("timezone", "Time Zone", "enum"),
        AttributeField("language", "Language", "enum"),
        AttributeField("days_signed_in", "Days Signed In (of last 90)", "number"),
        AttributeField("signins_90d", "Sign-ins (last 90 days)", "number"),
        AttributeField("last_sign_in", "Last Sign-in", "date"),
        AttributeField("primary_client", "Most Used Zoom Client", "enum"),
        AttributeField("clients_used", "Zoom Clients Used", "text"),
        AttributeField("meetings_90d", "Meetings Hosted (last 90 days)", "number"),
        AttributeField("participants_90d", "Participants in Hosted Meetings (last 90 days)", "number"),
        AttributeField("minutes_90d", "Meeting Minutes Hosted (last 90 days)", "number"),
        AttributeField("avg_minutes", "Average Meeting Minutes", "number"),
        AttributeField("avg_participants", "Average Participants per Meeting", "number"),
        AttributeField("days_hosted", "Days Hosted a Meeting (of last 90)", "number"),
        AttributeField("days_hosted_licensed", "Days Hosted Licensed Meeting (of last 90)", "number"),
        AttributeField("days_hosted_basic", "Days Hosted Basic Meeting (of last 90)", "number"),
        AttributeField("last_hosted", "Last Meeting Hosted", "date"),
        AttributeField("group_meetings_90d", "Group Meetings Hosted (last 90 days)", "number"),
        AttributeField("avg_group_minutes", "Average Group Meeting Minutes", "number"),
        AttributeField("avg_group_participants", "Average Group Meeting Participant Count", "number"),
        AttributeField("video_meetings_90d", "Meetings with Video (last 90 days)", "number"),
        AttributeField("screen_share_meetings_90d", "Meetings with Screen Share (last 90 days)", "number"),
        AttributeField("recorded_meetings_90d", "Meetings Recorded (last 90 days)", "number"),
        AttributeField("phone_audio_meetings_90d", "Meetings with Phone Audio (last 90 days)", "number"),
    )
    guide = Guide(
        steps=(
            "Sign in at marketplace.zoom.us as a Zoom admin and choose Develop > Build App > Server-to-Server OAuth > Create.",
            "On App Credentials, copy the Account ID, Client ID and Client Secret.",
            "On Information, add a short description, company name and a developer contact (Zoom requires these to activate).",
            "On Scopes, add 'View all user information' (user:read:admin), or user:read:list_users:admin.",
            "Optional, for role and group names: add 'View all roles' (role:read:admin) and 'View all groups' (group:read:admin).",
            "Optional, for sign-in history: add 'View all user reports' (report:read:admin). Needs a Pro or higher Zoom plan, and the Zoom user who owns the app needs the Sign In/Sign Out report permission.",
            "Optional, for days hosted by license type, group-meeting averages and feature use: add 'View all Dashboard data' (dashboard:read:admin). Needs a Business or higher plan with the Dashboard turned on.",
            "On Activation, click Activate your app, then paste the three values here. Anything optional you skip is simply left out; the sync still works.",
        ),
        docs_url="https://developers.zoom.us/docs/internal-apps/create/",
    )

    async def _token(self, client, cfg) -> str:
        resp = await send(
            client, "POST", "https://zoom.us/oauth/token",
            params={"grant_type": "account_credentials", "account_id": cfg["account_id"]},
            auth=(cfg["client_id"], cfg["client_secret"]),
        )
        token = resp.json().get("access_token")
        if not token:
            raise ConnectorError("Zoom did not return an access token - check the three credentials.")
        return token

    async def _list(self, client, token, status):
        users, page_token = [], None
        while True:
            params = {"status": status, "page_size": 300, "include_fields": "custom_attributes"}
            if page_token:
                params["next_page_token"] = page_token
            resp = await send(client, "GET", "https://api.zoom.us/v2/users",
                              params=params, headers={"Authorization": f"Bearer {token}"})
            data = resp.json()
            users.extend(data.get("users", []))
            page_token = data.get("next_page_token")
            if not page_token:
                return users

    async def _pages(self, client, token, url, list_key, params):
        """Every item of a paged Zoom list, a page at a time (so a big report never has to be held in memory)."""
        page_token, pages = None, 0
        while True:
            p = {**params, "page_size": 300}
            if page_token:
                p["next_page_token"] = page_token
            data = (await send(client, "GET", url, params=p, headers={"Authorization": f"Bearer {token}"})).json()
            for item in data.get(list_key) or []:
                yield item
            page_token, pages = data.get("next_page_token"), pages + 1
            if not page_token or pages >= MAX_PAGES:
                return

    @staticmethod
    def _windows():
        """(from, to) date strings for three back-to-back 30-day windows ending today: together, the last 90 days."""
        today = datetime.now(timezone.utc).date()
        out = []
        for i in range(WINDOWS):
            to = today - timedelta(days=WINDOW_DAYS * i)
            out.append(((to - timedelta(days=WINDOW_DAYS - 1)).isoformat(), to.isoformat()))
        return out

    async def _names(self, client, token, url, list_key, notes, label, scope):
        """id -> name for roles or groups; {} (with a note) if Zoom refuses."""
        try:
            items = [x async for x in self._pages(client, token, url, list_key, {})]
        except ConnectorError:
            notes.append(f"{label} names weren't collected. Add the '{scope[1]}' ({scope[0]}) scope to the Zoom app to see them.")
            return {}
        return {str(i.get("id")): i.get("name") for i in items if i.get("id") is not None and i.get("name")}

    async def _usage(self, client, token, notes):
        """email -> [meetings, participants, minutes] hosted over the last 90 days, from Zoom's Active Hosts report (Pro or higher plan).
        None, with a note, if Zoom refuses. Only used when the richer Dashboard data isn't available."""
        totals = {}
        try:
            for frm, to in self._windows():
                async for r in self._pages(client, token, "https://api.zoom.us/v2/report/users", "users", {"type": "active", "from": frm, "to": to}):
                    email = (r.get("email") or "").strip().lower()
                    if email:
                        t = totals.setdefault(email, [0, 0, 0])
                        t[0] += int(r.get("meetings") or 0)
                        t[1] += int(r.get("participants") or 0)
                        t[2] += int(r.get("meeting_minutes") or 0)
        except ConnectorError:
            notes.append("Meeting totals weren't collected because Zoom refused the Reports request. Add the 'View all user reports' (report:read:admin) scope to the Zoom app "
                         "(Zoom's Reports need a Pro or higher plan), then sync again.")
            return None
        return totals

    async def _hosting(self, client, token, notes):
        """email -> what they did as a meeting host over the last 90 days, from the Dashboard's list of past meetings.
        None, with a note, if Zoom refuses (needs a Business or higher plan with the Dashboard on)."""
        hosts = {}
        try:
            for frm, to in self._windows():
                async for m in self._pages(client, token, "https://api.zoom.us/v2/metrics/meetings", "meetings", {"type": "past", "from": frm, "to": to}):
                    email = (m.get("email") or "").strip().lower()
                    start = parse_dt(m.get("start_time"))
                    if not email or start is None:
                        continue
                    h = hosts.setdefault(email, {"days": set(), "licensed": set(), "basic": set(), "meetings": 0, "participants": 0, "minutes": 0.0, "group": 0, "group_minutes": 0.0,
                                                 "group_people": 0, "video": 0, "share": 0, "record": 0, "phone": 0, "last": None})
                    day, people, minutes = start.date(), int(m.get("participants") or 0), _minutes(m)
                    h["days"].add(day)
                    kind = _license_kind(m.get("user_type"))
                    if kind:
                        h[kind].add(day)
                    h["meetings"] += 1
                    h["participants"] += people
                    h["minutes"] += minutes
                    if people >= GROUP_MEETING_MIN_PEOPLE:
                        h["group"] += 1
                        h["group_minutes"] += minutes
                        h["group_people"] += people
                    h["video"] += 1 if m.get("has_video") else 0
                    h["share"] += 1 if m.get("has_screen_share") else 0
                    h["record"] += 1 if m.get("has_recording") else 0
                    h["phone"] += 1 if (m.get("has_pstn") or m.get("has_3rd_party_audio") or m.get("has_sip")) else 0
                    if h["last"] is None or start > h["last"]:
                        h["last"] = start
        except ConnectorError:
            notes.append("Meeting details (days hosted by license type, group-meeting averages, feature use) weren't collected because Zoom refused the Dashboard request. Add the "
                         "'View all Dashboard data' (dashboard:read:admin) scope; it needs a Business or higher Zoom plan with the Dashboard turned on.")
            return None
        return hosts

    async def _signins(self, client, token, notes):
        """email -> sign-in history over the last 90 days (days, count, last time, which Zoom clients), from the Sign In/Sign Out report.
        None, with a note, if Zoom refuses."""
        people = {}
        try:
            for frm, to in self._windows():
                async for r in self._pages(client, token, "https://api.zoom.us/v2/report/activities", "activity_logs", {"from": frm, "to": to}):
                    if str(r.get("type") or "").lower() != "sign in":
                        continue
                    email, when = (r.get("email") or "").strip().lower(), parse_dt(r.get("time"))
                    if not email or when is None:
                        continue
                    p = people.setdefault(email, {"days": set(), "count": 0, "last": None, "clients": Counter()})
                    p["days"].add(when.date())
                    p["count"] += 1
                    if r.get("client_type"):
                        p["clients"][str(r["client_type"]).strip()] += 1
                    if p["last"] is None or when > p["last"]:
                        p["last"] = when
        except ConnectorError:
            notes.append("Sign-in history wasn't collected because Zoom refused the Sign In/Sign Out report. Add the 'View all user reports' (report:read:admin) scope "
                         "(needs a Pro or higher plan, and the Zoom user who owns the app needs the Sign In/Sign Out report permission), then sync again.")
            return None
        return people

    async def test(self, cfg, db=None) -> str:
        async with self.make_client() as client:
            token = await self._token(client, cfg)
            resp = await send(client, "GET", "https://api.zoom.us/v2/users",
                              params={"status": "active", "page_size": 1},
                              headers={"Authorization": f"Bearer {token}"})
        total = resp.json().get("total_records")
        return "Connected to Zoom" + (f" - {total:,} active users visible" if isinstance(total, int) else "")

    async def fetch_users(self, cfg) -> list:
        notes = []
        async with self.make_client() as client:
            token = await self._token(client, cfg)
            raw = await self._list(client, token, "active") + await self._list(client, token, "inactive")
            roles = await self._names(client, token, "https://api.zoom.us/v2/roles", "roles", notes, "Role", ("role:read:admin", "View all roles"))
            groups = await self._names(client, token, "https://api.zoom.us/v2/groups", "groups", notes, "Group", ("group:read:admin", "View all groups"))
            hosting = await self._hosting(client, token, notes)
            usage = await self._usage(client, token, notes) if hosting is None else None       # the simpler report is only needed if the Dashboard isn't available
            signins = await self._signins(client, token, notes)

        records = []
        for u in raw:
            email = (u.get("email") or "").strip()
            if not email:
                continue
            key = email.lower()
            label = _LICENSE.get(u.get("type"), "unknown")
            if u.get("status") == "inactive":
                label = "inactive"               # a deactivated account holds no license seat
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("display_name")
            attrs = {"created_at": (u.get("created_at") or u.get("user_created_at")), "status": u.get("status"), "dept": (u.get("dept") or "").strip() or None,
                     "last_client_version": (u.get("last_client_version") or "").strip() or None, "timezone": (u.get("timezone") or "").strip() or None,
                     "language": (u.get("language") or "").strip() or None, "role": roles.get(str(u.get("role_id"))) if u.get("role_id") is not None else None}
            if u.get("verified") is not None:
                attrs["verified"] = bool(u.get("verified"))
            group_names = [groups[str(g)] for g in (u.get("group_ids") or []) if str(g) in groups]
            if group_names:
                attrs["groups"] = ", ".join(sorted(group_names))
            for ca in u.get("custom_attributes") or []:                     # attributes your Zoom admins defined themselves
                if isinstance(ca, dict) and ca.get("key") and str(ca.get("value") or "").strip():
                    attrs[f"custom_{str(ca['key']).lower()[:40]}"] = str(ca["value"]).strip()[:120]

            last_active, active_days = parse_dt(u.get("last_login_time")), set()
            if signins is not None:
                s = signins.get(key)
                attrs.update(days_signed_in=len(s["days"]) if s else 0, signins_90d=s["count"] if s else 0)
                if s:
                    attrs["last_sign_in"] = s["last"].isoformat()
                    if s["clients"]:
                        attrs["primary_client"] = s["clients"].most_common(1)[0][0]
                        attrs["clients_used"] = ", ".join(sorted(s["clients"]))
                    active_days |= s["days"]
                    last_active = max(filter(None, [last_active, s["last"]]))
            if hosting is not None:                                       # people who hosted nothing get zeros (the Dashboard only lists meetings that happened)
                h = hosting.get(key)
                n = h["meetings"] if h else 0
                attrs.update(meetings_90d=n, participants_90d=h["participants"] if h else 0, minutes_90d=round(h["minutes"]) if h else 0,
                             days_hosted=len(h["days"]) if h else 0, days_hosted_licensed=len(h["licensed"]) if h else 0, days_hosted_basic=len(h["basic"]) if h else 0,
                             group_meetings_90d=h["group"] if h else 0, video_meetings_90d=h["video"] if h else 0, screen_share_meetings_90d=h["share"] if h else 0,
                             recorded_meetings_90d=h["record"] if h else 0, phone_audio_meetings_90d=h["phone"] if h else 0)
                if h:
                    attrs.update(avg_minutes=round(h["minutes"] / n, 1), avg_participants=round(h["participants"] / n, 1), last_hosted=h["last"].isoformat())
                    if h["group"]:
                        attrs.update(avg_group_minutes=round(h["group_minutes"] / h["group"], 1), avg_group_participants=round(h["group_people"] / h["group"], 1))
                    active_days |= h["days"]
                    last_active = max(filter(None, [last_active, h["last"]]))
            elif usage is not None:
                meetings, participants, minutes = usage.get(key, [0, 0, 0])
                attrs.update(meetings_90d=meetings, participants_90d=participants, minutes_90d=minutes)
                if meetings:
                    attrs.update(avg_minutes=round(minutes / meetings, 1), avg_participants=round(participants / meetings, 1))
            records.append(UserRecord(email=email, license_type=label, last_active_at=last_active, full_name=name,
                                      active_days=sorted(active_days) or None, attributes={k: v for k, v in attrs.items() if v is not None}))
        return (records, notes) if notes else records
