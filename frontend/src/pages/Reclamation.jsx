import { Fragment, useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", accentText: "#3730A3",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", borderStrong: "#CBD5E1", cardBg: "#FFFFFF", pageBg: "#F4F6FA", tableHeader: "#F8FAFC",
};

const API_BASE = import.meta.env?.VITE_API_BASE_URL || "";
const DAY_OPTIONS = [30, 60, 90];

const usd = cents => (cents === null || cents === undefined ? "—" : "$" + Math.round(cents / 100).toLocaleString("en-US"));
const num = n => (typeof n === "number" ? n : 0).toLocaleString();
const fmtDate = iso => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

const btn = (primary, disabled, danger) => ({
  padding: "7px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600,
  cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1,
  border: primary ? "none" : `1px solid ${danger ? "#FECACA" : Z.borderStrong}`,
  background: primary ? Z.accent : Z.cardBg, color: primary ? "#fff" : danger ? Z.red : Z.textPrimary,
});

const th = { padding: "9px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap" };
const td = { padding: "10px 14px", fontSize: 13, color: Z.textPrimary };
const card = { background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" };

function Banner({ tone = "amber", children }) {
  const t = { amber: [Z.amberLight, "#FDE68A", Z.amberText], red: [Z.redLight, "#FECACA", Z.redText],
              green: [Z.greenLight, "#BBF7D0", Z.greenText], blue: [Z.accentLight, "#C7D2FE", Z.accentText] }[tone];
  return <div style={{ background: t[0], border: `1px solid ${t[1]}`, color: t[2], borderRadius: 10, padding: "10px 14px", fontSize: 13, lineHeight: 1.5, marginBottom: 16 }}>{children}</div>;
}

function Kpi({ label, value, sub, tone }) {
  return (
    <div style={{ ...card, padding: "1rem 1.25rem" }}>
      <p style={{ margin: 0, fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>
      <p style={{ margin: "6px 0 2px", fontSize: 26, fontWeight: 700, color: tone === "good" ? Z.green : Z.textPrimary }}>{value}</p>
      {sub && <p style={{ margin: 0, fontSize: 12, color: Z.textSecondary }}>{sub}</p>}
    </div>
  );
}

function Pills({ options, value, onChange }) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {options.map(o => (
        <button key={o.id} onClick={() => onChange(o.id)} style={{ padding: "5px 14px", borderRadius: 100, fontSize: 13, fontWeight: 600, cursor: "pointer", border: `1px solid ${value === o.id ? Z.accent : Z.border}`, background: value === o.id ? Z.accentLight : Z.cardBg, color: value === o.id ? Z.accent : Z.textSecondary }}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ───────────────────────────────────────────────────────────── opportunities (analytics)
function Opportunities({ onCreateWorkflow }) {
  const [days, setDays] = useState(60);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(null);       // app id whose people are shown
  const [drill, setDrill] = useState({});       // app id -> rows

  const load = useCallback(async () => {
    setData(null); setError(null); setOpen(null); setDrill({});
    try { setData(await api.get(`/reclamation/overview?days=${days}`)); }
    catch (e) { setError(e.message || "Could not load the analytics"); }
  }, [days]);
  useEffect(() => { load(); }, [load]);

  async function toggle(appId) {
    if (open === appId) { setOpen(null); return; }
    setOpen(appId);
    if (!drill[appId]) {
      try {
        const r = await api.get(`/reclamation/inactive?days=${days}&app_id=${appId}&limit=50`);
        setDrill(d => ({ ...d, [appId]: r }));
      } catch (e) { setDrill(d => ({ ...d, [appId]: { rows: [], total: 0, error: e.message } })); }
    }
  }

  if (error) return <Banner tone="red">{error}</Banner>;
  if (!data) return <p style={{ color: Z.textMuted, fontSize: 14 }}>Loading…</p>;

  const k = data.kpis;
  const stats = data.stats || { counts: {}, reclaimed_savings_cents: 0, pipeline_savings_cents: 0 };
  const maxBucket = Math.max(1, ...(data.buckets || []).map(b => b.count));

  return (
    <div>
      {!data.ready && (
        <Banner tone="amber">
          <strong>Sign-in history isn't available yet.</strong> Open <strong>Integration Library → Okta sign-in activity</strong> and run a sync.
          Until then every assignment would look inactive, so no numbers are shown.
        </Banner>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: Z.textSecondary }}>No sign-in for</span>
        <Pills options={DAY_OPTIONS.map(d => ({ id: d, label: `${d}+ days` }))} value={days} onChange={setDays} />
        {data.ready && <a href={`${API_BASE}/api/v1/reclamation/inactive.csv?days=${days}`} style={{ marginLeft: "auto", fontSize: 13, fontWeight: 600, color: Z.accent }}>Export all (CSV)</a>}
      </div>

      {k && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 14, marginBottom: 18 }}>
            <Kpi label="Inactive assignments" value={num(k.inactive)} sub={`${k.inactive_pct}% of ${num(k.assigned)} tracked assignments`} />
            <Kpi label="Est. annual savings" value={usd(k.est_annual_savings_cents)} sub={k.apps_missing_cost ? `${k.apps_missing_cost} app${k.apps_missing_cost === 1 ? "" : "s"} have no license cost on file` : "Based on your license costs"} />
            <Kpi label="In review" value={usd(stats.pipeline_savings_cents)} sub={`${num((stats.counts.open || 0) + (stats.counts.approved || 0))} items open or approved`} />
            <Kpi label="Reclaimed so far" value={usd(stats.reclaimed_savings_cents)} sub={`${num(stats.counts.reclaimed || 0)} confirmed removals`} tone="good" />
          </div>

          <div style={{ ...card, padding: "1rem 1.25rem", marginBottom: 18 }}>
            <p style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 700 }}>When did people last sign in?</p>
            {data.buckets.map(b => (
              <div key={b.label} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                <span style={{ width: 150, fontSize: 12, color: Z.textSecondary }}>{b.label}</span>
                <div style={{ flex: 1, background: "#EEF2F7", borderRadius: 6, height: 14 }}>
                  <div style={{ width: `${(100 * b.count) / maxBucket}%`, minWidth: b.count ? 3 : 0, height: 14, borderRadius: 6, background: b.label.startsWith("No sign-in") || b.label.startsWith("61") ? Z.red : Z.accent }} />
                </div>
                <span style={{ width: 70, textAlign: "right", fontSize: 12, fontWeight: 600 }}>{num(b.count)}</span>
              </div>
            ))}
            <p style={{ margin: "8px 0 0", fontSize: 12, color: Z.textMuted }}>
              Counts sign-ins made through Okta. Okta keeps 90 days of history, so "no sign-in on record" means none in the last 90 days.
            </p>
          </div>

          <div style={{ ...card, overflow: "hidden", marginBottom: 18 }}>
            <div style={{ padding: "1rem 1.25rem", borderBottom: `1px solid ${Z.border}` }}>
              <p style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>Deprovisioning opportunities by app</p>
              <p style={{ margin: "2px 0 0", fontSize: 12, color: Z.textSecondary }}>Apps with people who haven't signed in for {days}+ days. Click an app to see who.</p>
            </div>
            {data.by_app.length === 0 ? <p style={{ padding: "1rem 1.25rem", margin: 0, fontSize: 13, color: Z.textMuted }}>Nothing found at this threshold.</p> : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr style={{ background: Z.tableHeader }}>{["App", "Assigned", "Inactive", "% inactive", "Est. annual savings", ""].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
                <tbody>
                  {data.by_app.map(a => (
                    <Fragment key={a.app_id}>
                      <tr onClick={() => toggle(a.app_id)} style={{ borderTop: `1px solid ${Z.border}`, cursor: "pointer", background: open === a.app_id ? "#F5F7FF" : "transparent" }}>
                        <td style={{ ...td, fontWeight: 600 }}>{a.name}</td>
                        <td style={td}>{num(a.assigned)}</td>
                        <td style={td}>{num(a.inactive)}</td>
                        <td style={td}>{a.inactive_pct}%</td>
                        <td style={{ ...td, color: a.cost_known ? Z.textPrimary : Z.textMuted }}>{a.cost_known ? usd(a.est_annual_savings_cents) : "no cost data"}</td>
                        <td style={{ ...td, textAlign: "right", color: Z.accent, fontWeight: 600 }}>{open === a.app_id ? "Hide" : "Who?"}</td>
                      </tr>
                      {open === a.app_id && (
                        <tr><td colSpan={6} style={{ padding: 0, background: "#FAFBFF" }}>
                          <div style={{ padding: "10px 14px 14px" }}>
                            {!drill[a.app_id] ? <p style={{ margin: 0, fontSize: 13, color: Z.textMuted }}>Loading…</p> : (
                              <>
                                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                  <thead><tr>{["Person", "License", "Last sign-in", "Days inactive", "Est. savings"].map(h => <th key={h} style={{ ...th, padding: "6px 10px" }}>{h}</th>)}</tr></thead>
                                  <tbody>
                                    {drill[a.app_id].rows.map(r => (
                                      <tr key={r.email} style={{ borderTop: `1px solid ${Z.border}` }}>
                                        <td style={{ ...td, padding: "7px 10px" }}>{r.name && r.name !== r.email ? `${r.name} · ` : ""}<span style={{ color: Z.textSecondary }}>{r.email}</span></td>
                                        <td style={{ ...td, padding: "7px 10px" }}>{r.license || "—"}</td>
                                        <td style={{ ...td, padding: "7px 10px" }}>{r.last_active ? fmtDate(r.last_active) : "No sign-in on record"}</td>
                                        <td style={{ ...td, padding: "7px 10px" }}>{r.days_inactive ?? "—"}</td>
                                        <td style={{ ...td, padding: "7px 10px" }}>{usd(r.est_annual_savings_cents)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                                <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10 }}>
                                  <span style={{ fontSize: 12, color: Z.textMuted }}>Showing {drill[a.app_id].rows.length} of {num(drill[a.app_id].total)}</span>
                                  <a href={`${API_BASE}/api/v1/reclamation/inactive.csv?days=${days}&app_id=${a.app_id}`} style={{ fontSize: 12, fontWeight: 600, color: Z.accent }}>Export (CSV)</a>
                                  <button onClick={() => onCreateWorkflow({ app_id: a.app_id, app_name: a.name, inactivity_days: days })} style={{ ...btn(true), marginLeft: "auto" }}>Create workflow for this app</button>
                                </div>
                              </>
                            )}
                          </div>
                        </td></tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 14 }}>
            <div style={{ ...card, padding: "1rem 1.25rem" }}>
              <p style={{ margin: "0 0 4px", fontSize: 14, fontWeight: 700 }}>Apps with no recorded sign-ins</p>
              <p style={{ margin: "0 0 10px", fontSize: 12, color: Z.textSecondary }}>Nobody assigned to these has signed in through Okta. They're either unused (cancel or downsize) or reached some other way (so we can't judge).</p>
              {data.untracked_apps.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: Z.textMuted }}>None.</p> : data.untracked_apps.slice(0, 12).map(a => (
                <div key={a.app_id} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderTop: `1px solid ${Z.border}`, fontSize: 13 }}>
                  <span>{a.name}</span><span style={{ color: Z.textSecondary }}>{num(a.assigned)} assigned</span>
                </div>
              ))}
              {data.untracked_apps.length > 12 && <p style={{ margin: "8px 0 0", fontSize: 12, color: Z.textMuted }}>+ {data.untracked_apps.length - 12} more</p>}
            </div>
            <div style={{ ...card, padding: "1rem 1.25rem" }}>
              <p style={{ margin: "0 0 4px", fontSize: 14, fontWeight: 700 }}>People with the most idle access</p>
              <p style={{ margin: "0 0 10px", fontSize: 12, color: Z.textSecondary }}>Apps each person is assigned but hasn't opened in {days}+ days.</p>
              {data.top_people.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: Z.textMuted }}>None.</p> : data.top_people.map(p => (
                <div key={p.email} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderTop: `1px solid ${Z.border}`, fontSize: 13 }}>
                  <span>{p.name && p.name !== p.email ? p.name : p.email}</span><span style={{ color: Z.textSecondary }}>{num(p.idle_apps)} apps</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────── workflow form
function AppScope({ value, onChange }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const data = await api.get(`/apps?limit=8${q ? `&search=${encodeURIComponent(q)}` : ""}`);
        if (!cancelled) setItems(Array.isArray(data) ? data : []);
      } catch (e) { if (!cancelled) setItems([]); }
    }, q ? 300 : 0);
    return () => { cancelled = true; clearTimeout(t); };
  }, [open, q]);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: "#F9FAFB" }}>
        <span style={{ flex: 1, fontSize: 13, color: Z.textPrimary }}>{value ? value.name : "All apps"}</span>
        {value && <button onClick={() => onChange(null)} style={{ background: "none", border: "none", color: Z.textSecondary, fontSize: 12, cursor: "pointer" }}>Use all apps</button>}
        <button onClick={() => setOpen(o => !o)} style={{ background: "none", border: "none", color: Z.accent, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>{open ? "Done" : "Pick one app"}</button>
      </div>
      {open && (
        <div style={{ marginTop: 6, border: `1px solid ${Z.border}`, borderRadius: 8, overflow: "hidden" }}>
          <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Search your apps…" style={{ width: "100%", boxSizing: "border-box", padding: "8px 12px", border: "none", borderBottom: `1px solid ${Z.border}`, fontSize: 13, outline: "none" }} />
          <div style={{ maxHeight: 160, overflowY: "auto" }}>
            {items === null && <p style={{ margin: 0, padding: 10, fontSize: 12, color: Z.textMuted }}>Loading…</p>}
            {(items || []).map(a => (
              <button key={a.id} onClick={() => { onChange({ id: a.id, name: a.name }); setOpen(false); setQ(""); }} style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 12px", background: Z.cardBg, border: "none", borderBottom: `1px solid ${Z.border}`, fontSize: 13, cursor: "pointer" }}>{a.name}</button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function WorkflowForm({ initial, onClose, onSaved }) {
  const editing = Boolean(initial && initial.id);
  const [name, setName] = useState(initial?.name || "");
  const [app, setApp] = useState(initial?.app_id ? { id: initial.app_id, name: initial.app_name } : null);
  const [days, setDays] = useState(initial?.inactivity_days || 60);
  const [minUsd, setMinUsd] = useState(initial?.min_savings_usd || 0);
  const [slack, setSlack] = useState(Boolean(initial?.notify_slack));
  const [webhook, setWebhook] = useState("");
  const [clearHook, setClearHook] = useState(false);
  const [askSlack, setAskSlack] = useState(Boolean(initial?.ask_users_slack));
  const [perRun, setPerRun] = useState(initial?.ask_users_per_run || 25);
  const [auto, setAuto] = useState(initial?.auto_run ?? true);
  const [enabled, setEnabled] = useState(initial?.is_enabled ?? true);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);

  useEffect(() => {
    const onKey = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    setBusy(true); setNote(null);
    const body = { name, app_id: app ? app.id : null, inactivity_days: Number(days), min_savings_usd: Number(minUsd) || 0,
                   notify_slack: slack, webhook_url: webhook || null, clear_webhook: clearHook, auto_run: auto, is_enabled: enabled,
                   ask_users_slack: askSlack, ask_users_per_run: Number(perRun) || 25, public_base_url: window.location.origin };
    try {
      const r = await api.post(editing ? `/reclamation/workflows/${initial.id}` : "/reclamation/workflows", body);
      if (r.ok) onSaved(); else setNote(r.message);
    } catch (e) { setNote(e.message || "Could not save"); }
    finally { setBusy(false); }
  }

  const label = { display: "block", fontSize: 13, fontWeight: 600, color: Z.textPrimary, marginBottom: 4 };
  const input = { width: "100%", boxSizing: "border-box", padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, outline: "none" };
  const dayChoices = Array.from(new Set([30, 45, 60, 75, 90, Number(days)])).sort((a, b) => a - b);

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(17,24,39,0.45)", zIndex: 200, display: "flex", justifyContent: "center", alignItems: "flex-start", overflowY: "auto", padding: "4vh 1rem" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: Z.cardBg, borderRadius: 14, width: "100%", maxWidth: 580, boxShadow: "0 20px 50px rgba(0,0,0,0.25)" }}>
        <div style={{ display: "flex", alignItems: "center", padding: "1.1rem 1.5rem", borderBottom: `1px solid ${Z.border}` }}>
          <h2 style={{ margin: 0, flex: 1, fontSize: 17, fontWeight: 700 }}>{editing ? "Edit workflow" : "New reclamation workflow"}</h2>
          <button onClick={onClose} aria-label="Close" style={{ background: "none", border: "none", fontSize: 26, lineHeight: 1, color: Z.textMuted, cursor: "pointer" }}>×</button>
        </div>
        <div style={{ padding: "1.25rem 1.5rem" }}>
          <div style={{ marginBottom: 14 }}><label style={label}>Name</label>
            <input style={input} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Unused licenses, 60 days" /></div>
          <div style={{ marginBottom: 14 }}><label style={label}>Apps</label><AppScope value={app} onChange={setApp} /></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
            <div><label style={label}>Flag people with no sign-in for</label>
              <select style={input} value={days} onChange={e => setDays(e.target.value)}>{dayChoices.map(d => <option key={d} value={d}>{d} days</option>)}</select></div>
            <div><label style={label}>Only paid seats worth at least</label>
              <input style={input} type="number" min="0" value={minUsd} onChange={e => setMinUsd(e.target.value)} placeholder="0 = any" />
              <p style={{ margin: "3px 0 0", fontSize: 11, color: Z.textMuted }}>USD per year. Needs license costs on file.</p></div>
          </div>
          <div style={{ background: "#F9FAFB", border: `1px solid ${Z.border}`, borderRadius: 10, padding: "12px 14px", marginBottom: 14 }}>
            <p style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700 }}>When it finds candidates</p>
            <p style={{ margin: "0 0 10px", fontSize: 12, color: Z.textSecondary }}>They always go to the Review queue — nothing is removed automatically.</p>
            <label style={{ display: "flex", gap: 8, fontSize: 13, marginBottom: 6 }}>
              <input type="checkbox" checked={askSlack} onChange={e => setAskSlack(e.target.checked)} style={{ marginTop: 3 }} />
              <span><strong>Ask each person in Slack first.</strong> They get a message with <em>Yes, I still need it</em> and <em>Reclaim my license</em> buttons.</span>
            </label>
            {askSlack && (
              <div style={{ margin: "0 0 12px 24px", fontSize: 12, color: Z.textSecondary, lineHeight: 1.6 }}>
                Ask up to <input type="number" min="1" max="200" value={perRun} onChange={e => setPerRun(e.target.value)} style={{ width: 60, padding: "3px 6px", borderRadius: 6, border: `1px solid ${Z.border}`, fontSize: 12 }} /> people per run (the rest are asked on later runs).
                People who reclaim go to <strong>Approved for removal</strong>. Needs Slack connected with the <code>chat:write</code> scope.
              </div>
            )}
            <p style={{ margin: "0 0 8px", fontSize: 12, color: Z.textSecondary }}>You can also notify:</p>
            <label style={{ display: "flex", gap: 8, fontSize: 13, marginBottom: 10 }}><input type="checkbox" checked={slack} onChange={e => setSlack(e.target.checked)} />Post a summary to Slack <span style={{ color: Z.textMuted }}>(uses the SLACK_WEBHOOK_URL setting)</span></label>
            <label style={{ ...label, fontWeight: 600 }}>Send to a webhook <span style={{ color: Z.textMuted, fontWeight: 400 }}>(Okta Workflows, Jira, Zapier…)</span></label>
            <input style={input} value={webhook} onChange={e => setWebhook(e.target.value)} placeholder={initial?.has_webhook ? "•••• saved — paste a new https:// URL to replace" : "https://…"} />
            {initial?.has_webhook && <label style={{ display: "flex", gap: 8, fontSize: 12, marginTop: 6, color: Z.textSecondary }}><input type="checkbox" checked={clearHook} onChange={e => setClearHook(e.target.checked)} />Remove the saved webhook</label>}
          </div>
          <label style={{ display: "flex", gap: 8, fontSize: 13, marginBottom: 8 }}><input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)} />Run automatically every day</label>
          <label style={{ display: "flex", gap: 8, fontSize: 13, marginBottom: 14 }}><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />Enabled</label>
          {note && <Banner tone="red">{note}</Banner>}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button onClick={onClose} style={btn(false)}>Cancel</button>
            <button onClick={save} disabled={busy} style={btn(true, busy)}>{busy ? "Saving…" : "Save workflow"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────── workflows tab
function Workflows({ prefill, onPrefillUsed, onViewQueue }) {
  const [list, setList] = useState(null);
  const [error, setError] = useState(null);
  const [form, setForm] = useState(null);       // null | {} | workflow
  const [busy, setBusy] = useState(null);
  const [note, setNote] = useState({});

  const load = useCallback(async () => {
    try { setList(await api.get("/reclamation/workflows")); setError(null); }
    catch (e) { setError(e.message || "Could not load workflows"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (prefill) { setForm(prefill); onPrefillUsed(); } }, [prefill]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(w) {
    setBusy(w.id); setNote(n => ({ ...n, [w.id]: null }));
    try {
      const r = await api.post(`/reclamation/workflows/${w.id}/run`);
      setNote(n => ({ ...n, [w.id]: { ok: r.ok, text: r.message } }));
      await load();
    } catch (e) { setNote(n => ({ ...n, [w.id]: { ok: false, text: e.message || "Run failed" } })); }
    finally { setBusy(null); }
  }
  async function toggle(w) { try { await api.post(`/reclamation/workflows/${w.id}/enabled?enabled=${!w.is_enabled}`); await load(); } catch (e) { setError(e.message); } }
  async function remove(w) {
    if (!window.confirm(`Delete "${w.name}" and its review items?`)) return;
    try { await api.post(`/reclamation/workflows/${w.id}/delete`); await load(); } catch (e) { setError(e.message); }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 14 }}>
        <p style={{ margin: 0, flex: 1, fontSize: 13, color: Z.textSecondary }}>
          A workflow finds people who haven't used an app, queues them for review, and can notify Slack or a webhook. <strong>It never removes access itself.</strong>
        </p>
        <button onClick={() => setForm({})} style={btn(true)}>New workflow</button>
      </div>
      {error && <Banner tone="red">{error}</Banner>}
      {list === null ? <p style={{ color: Z.textMuted, fontSize: 14 }}>Loading…</p> : list.length === 0 ? (
        <div style={{ ...card, padding: "2rem", textAlign: "center", color: Z.textSecondary, fontSize: 14 }}>
          No workflows yet. Create one, or open an app on the Opportunities tab and choose “Create workflow for this app”.
        </div>
      ) : list.map(w => {
        const s = w.last_run_summary || {};
        const c = w.counts || {};
        return (
          <div key={w.id} style={{ ...card, padding: "1rem 1.25rem", marginBottom: 12, opacity: w.is_enabled ? 1 : 0.7 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>{w.name}</h3>
              {!w.is_enabled && <span style={{ fontSize: 11, fontWeight: 700, color: Z.textMuted }}>PAUSED</span>}
              <span style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button onClick={() => run(w)} disabled={busy === w.id} style={btn(true, busy === w.id)}>{busy === w.id ? "Running…" : "Run now"}</button>
                <button onClick={() => setForm(w)} style={btn(false)}>Edit</button>
                <button onClick={() => toggle(w)} style={btn(false)}>{w.is_enabled ? "Pause" : "Resume"}</button>
                <button onClick={() => remove(w)} style={btn(false, false, true)}>Delete</button>
              </span>
            </div>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: Z.textSecondary }}>
              {w.app_name || "All apps"} · no sign-in for {w.inactivity_days}+ days{w.min_savings_usd ? ` · seats worth $${w.min_savings_usd}+/yr` : ""}
              {w.auto_run ? " · runs daily" : " · manual only"}{w.ask_users_slack ? " · asks people in Slack" : ""}{w.notify_slack ? " · Slack summary" : ""}{w.has_webhook ? " · webhook" : ""}
            </p>
            <p style={{ margin: "6px 0 0", fontSize: 12, color: Z.textMuted }}>
              Queue: {num(c.open || 0)} open · {num(c.approved || 0)} approved · {num(c.reclaimed || 0)} reclaimed · {num((c.kept || 0) + (c.dismissed || 0))} kept/dismissed
              {" "}<button onClick={onViewQueue} style={{ background: "none", border: "none", color: Z.accent, fontWeight: 600, fontSize: 12, cursor: "pointer", padding: 0 }}>Open review queue</button>
            </p>
            {w.last_run_at && <p style={{ margin: "4px 0 0", fontSize: 12, color: Z.textMuted }}>Last run {fmtDate(w.last_run_at)}: {s.message}{s.notifications && Object.keys(s.notifications).length ? ` (${Object.entries(s.notifications).map(([k, v]) => `${k}: ${v}`).join(", ")})` : ""}</p>}
            {note[w.id] && <div style={{ marginTop: 8 }}><Banner tone={note[w.id].ok ? "green" : "red"}>{note[w.id].text}</Banner></div>}
          </div>
        );
      })}
      {form && <WorkflowForm initial={form} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
    </div>
  );
}

// ───────────────────────────────────────────────────────────── review queue
const STATUS_TABS = [
  { id: "open", label: "Needs review" }, { id: "approved", label: "Approved for removal" },
  { id: "reclaimed", label: "Reclaimed" }, { id: "kept", label: "Still needed" },
  { id: "dismissed", label: "Dismissed" }, { id: "closed", label: "Closed" },
];
const ACTIONS = {
  open: [["ask", "Ask in Slack", false], ["approve", "Approve removal", true], ["keep", "Still needed", false], ["dismiss", "Dismiss", false]],
  approved: [["reopen", "Move back to review", false], ["dismiss", "Dismiss", false]],
  kept: [["reopen", "Reopen", false], ["dismiss", "Dismiss", false]],
  dismissed: [["reopen", "Reopen", false]],
};

function Queue() {
  const [status, setStatus] = useState("open");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState({});
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setData(await api.get(`/reclamation/items?status=${status}&limit=200`)); setError(null); }
    catch (e) { setError(e.message || "Could not load the queue"); }
  }, [status]);
  useEffect(() => { setSelected({}); setNote(null); setData(null); load(); }, [load]);

  const ids = Object.keys(selected).filter(k => selected[k]);
  const items = data ? data.items : [];
  const allOn = items.length > 0 && ids.length === items.length;

  async function decide(action) {
    if (action === "ask" && !window.confirm(`Send a Slack message to ${ids.length} ${ids.length === 1 ? "person" : "people"} asking whether they still need this?`)) return;
    setBusy(true); setNote(null);
    try {
      const r = action === "ask" ? await api.post("/reclamation/items/ask", { ids }) : await api.post("/reclamation/items/decide", { ids, action });
      setNote({ ok: r.ok, text: r.message });
      setSelected({});
      await load();
    } catch (e) { setNote({ ok: false, text: e.message || "Failed" }); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        {STATUS_TABS.map(t => (
          <button key={t.id} onClick={() => setStatus(t.id)} style={{ padding: "6px 14px", borderRadius: 100, fontSize: 13, fontWeight: 600, cursor: "pointer", border: `1px solid ${status === t.id ? Z.accent : Z.border}`, background: status === t.id ? Z.accentLight : Z.cardBg, color: status === t.id ? Z.accent : Z.textSecondary }}>
            {t.label} ({num(data && data.counts ? data.counts[t.id] : 0)})
          </button>
        ))}
      </div>
      {status === "approved" && (
        <Banner tone="blue">
          These are approved for removal, including people who chose <strong>Reclaim my license</strong> in Slack. Remove the access in Okta (or send the list to whoever does), then run the Okta sync — items are marked <strong>Reclaimed</strong> automatically once the assignment disappears.
          {" "}<a href={`${API_BASE}/api/v1/reclamation/items.csv?status=approved`} style={{ fontWeight: 700, color: Z.accentText }}>Download the list (CSV)</a>
        </Banner>
      )}
      {status === "reclaimed" && <Banner tone="green">Confirmed removals: the assignment no longer exists in Okta after approval.</Banner>}
      {error && <Banner tone="red">{error}</Banner>}
      {note && <Banner tone={note.ok ? "green" : "red"}>{note.text}</Banner>}

      {ACTIONS[status] && ids.length > 0 && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: Z.textSecondary }}>{ids.length} selected</span>
          {ACTIONS[status].map(([action, label, primary]) => <button key={action} onClick={() => decide(action)} disabled={busy} style={btn(primary, busy)}>{label}</button>)}
        </div>
      )}

      <div style={{ ...card, overflow: "hidden" }}>
        {data === null ? <p style={{ margin: 0, padding: "1rem 1.25rem", color: Z.textMuted, fontSize: 14 }}>Loading…</p> : items.length === 0 ? (
          <p style={{ margin: 0, padding: "1.5rem", textAlign: "center", color: Z.textMuted, fontSize: 14 }}>Nothing here.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr style={{ background: Z.tableHeader }}>
              <th style={{ ...th, width: 34 }}>{ACTIONS[status] && <input type="checkbox" checked={allOn} onChange={e => setSelected(e.target.checked ? Object.fromEntries(items.map(i => [i.id, true])) : {})} />}</th>
              {["Person", "App", "Last sign-in", "Days inactive", "Est. savings", "Workflow"].map(h => <th key={h} style={th}>{h}</th>)}
            </tr></thead>
            <tbody>
              {items.map(i => (
                <tr key={i.id} style={{ borderTop: `1px solid ${Z.border}` }}>
                  <td style={td}>{ACTIONS[status] && <input type="checkbox" checked={Boolean(selected[i.id])} onChange={e => setSelected(s => ({ ...s, [i.id]: e.target.checked }))} />}</td>
                  <td style={td}><div style={{ fontWeight: 600 }}>{i.name && i.name !== i.email ? i.name : i.email}</div>{i.name && i.name !== i.email && <div style={{ fontSize: 12, color: Z.textMuted }}>{i.email}</div>}
                    {i.asked_at && i.status === "open" && <div style={{ fontSize: 11, color: Z.amberText, marginTop: 2 }}>Asked in Slack {fmtDate(i.asked_at)} · awaiting reply</div>}</td>
                  <td style={td}>{i.app}</td>
                  <td style={td}>{i.last_active ? fmtDate(i.last_active) : "No sign-in on record"}</td>
                  <td style={td}>{i.days_inactive ?? "—"}</td>
                  <td style={td}>{usd(i.est_annual_savings_cents)}</td>
                  <td style={{ ...td, color: Z.textSecondary }}>{i.workflow}{i.note ? <div style={{ fontSize: 11, color: Z.textMuted }}>{i.note}</div> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {data && data.total > items.length && <p style={{ fontSize: 12, color: Z.textMuted }}>Showing the first {items.length} of {num(data.total)}, highest savings first.</p>}
    </div>
  );
}

// ───────────────────────────────────────────────────────────── page
export default function Reclamation() {
  const [tab, setTab] = useState("opportunities");
  const [prefill, setPrefill] = useState(null);

  const tabs = [{ id: "opportunities", label: "Opportunities" }, { id: "workflows", label: "Workflows" }, { id: "queue", label: "Review queue" }];

  return (
    <div>
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>License reclamation</h1>
        <p style={{ margin: "4px 0 0", fontSize: 14, color: Z.textSecondary }}>
          Find access nobody is using, review it, and track the savings once it's removed.
        </p>
      </div>
      <div style={{ display: "flex", gap: 24, borderBottom: `1px solid ${Z.border}`, marginBottom: 20 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{ padding: "10px 0", background: "none", border: "none", cursor: "pointer", fontSize: 14, fontWeight: tab === t.id ? 700 : 500, color: tab === t.id ? Z.accent : Z.textSecondary, borderBottom: `2px solid ${tab === t.id ? Z.accent : "transparent"}`, marginBottom: -1 }}>{t.label}</button>
        ))}
      </div>
      {tab === "opportunities" && <Opportunities onCreateWorkflow={p => { setPrefill(p); setTab("workflows"); }} />}
      {tab === "workflows" && <Workflows prefill={prefill} onPrefillUsed={() => setPrefill(null)} onViewQueue={() => setTab("queue")} />}
      {tab === "queue" && <Queue />}
    </div>
  );
}
