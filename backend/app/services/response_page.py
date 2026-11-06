"""The small web page a person lands on after clicking a button in the Slack message."""
from html import escape
from urllib.parse import quote

_CSS = ("body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#F4F6FA;"
        "color:#111827;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:1rem}"
        ".card{background:#fff;border:1px solid #E2E8F0;border-radius:14px;max-width:460px;width:100%;padding:2rem;"
        "box-shadow:0 4px 18px rgba(0,0,0,.06);text-align:center}h1{font-size:20px;margin:0 0 .6rem}"
        "p{font-size:14px;line-height:1.55;color:#4B5563;margin:.4rem 0}.row{margin-top:1.4rem;display:flex;gap:10px;"
        "justify-content:center;flex-wrap:wrap}a.b{display:inline-block;padding:10px 18px;border-radius:9px;font-size:14px;"
        "font-weight:600;text-decoration:none;border:1px solid #CBD5E1;color:#111827;background:#fff}"
        "a.p{background:#4B5EDE;border-color:#4B5EDE;color:#fff}.i{font-size:34px;margin-bottom:.4rem}")


def _page(icon: str, title: str, body: str, buttons: str = "") -> str:
    row = f'<div class="row">{buttons}</div>' if buttons else ""
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title><style>{_CSS}</style></head><body><div class="card">'
            f'<div class="i">{icon}</div><h1>{escape(title)}</h1>{body}{row}</div></body></html>')


def render(result: dict, token: str = "") -> tuple[int, str]:
    """Return (http status, html) for a respond() result."""
    state, app = result.get("state"), escape(result.get("app") or "this app")
    t = quote(token or "", safe=".-_")
    if state == "kept":
        return 200, _page("✅", "Thanks, you're all set",
                          f"<p>We've noted that you still need <strong>{app}</strong>. Nothing changes for you.</p>")
    if state == "confirm_release":
        return 200, _page("♻️", f"Give up your {result.get('app') or 'license'}?",
                          "<p>IT will remove your access so the license can be used by someone else. "
                          "You can always request access again later.</p>",
                          f'<a class="b p" href="?token={t}&amp;answer=release&amp;confirm=1">Yes, reclaim my license</a>'
                          f'<a class="b" href="?token={t}&amp;answer=keep">No, I still need it</a>')
    if state == "released":
        return 200, _page("👍", "Done, thank you",
                          f"<p>Your <strong>{app}</strong> license has been released. IT has been notified and will remove the access.</p>"
                          "<p>If you change your mind, just ask IT for access again.</p>")
    if state == "inactive":
        return 200, _page("ℹ️", "This request is no longer active",
                          f"<p>There's nothing more to do for <strong>{app}</strong>. Thanks for responding.</p>")
    if state == "expired":
        return 410, _page("⌛", "This link has expired",
                          "<p>Please contact IT if you'd like to confirm or release a license.</p>")
    return 400, _page("⚠️", "This link isn't valid",
                      "<p>The link may have been copied incorrectly. Please use the buttons in the Slack message.</p>")
