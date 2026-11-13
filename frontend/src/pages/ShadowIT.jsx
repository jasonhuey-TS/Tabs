import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
  greenLight: "#F0FDF4", greenText: "#15803D", amberLight: "#FFFBEB", amberText: "#92400E", redLight: "#FEF2F2", redText: "#B91C1C",
};
const card = { background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", padding: "16px 20px", marginBottom: 16 };
const input = { boxSizing: "border-box", padding: "7px 10px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, fontFamily: "inherit" };
const th = { padding: "9px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` };
const td = { padding: "10px 14px", fontSize: 13, borderBottom: `1px solid ${Z.border}`, color: Z.textPrimary, verticalAlign: "top" };
const btn = (primary, disabled) => ({ padding: "6px 12px", borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1,
  border: `1px solid ${primary ? Z.accent : Z.border}`, background: primary ? Z.accent : "#fff", color: primary ? "#fff" : Z.textPrimary, marginRight: 6 });
const link = { background: "none", border: "none", padding: 0, color: Z.accent, fontWeight: 600, fontSize: 12.5, cursor: "pointer" };
const RISK = { high: ["High access", "#FEF2F2", "#B91C1C"], medium: ["Medium access", "#FFFBEB", "#92400E"], low: ["Sign-in only", "#F0FDF4", "#15803D"] };
const STATUS_TABS = [["new", "Needs review"], ["known", "Already in Tab"], ["added", "Added to Tab"], ["ignored", "Ignored"]];

const n = v => Number(v || 0).toLocaleString("en-US");
const day = iso => (iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—");
const when = iso => (iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "never");

function Note({ tone = "amber", children }) {
  const t = { amber: [Z.amberLight, "#FDE68A", Z.amberText], red: [Z.redLight, "#FECACA", Z.redText], green: [Z.greenLight, "#BBF7D0", Z.greenText], blue: [Z.accentLight, "#C7D2FE", "#3730A3"] }[tone];
  return <div style={{ background: t[0], border: `1px solid ${t[1]}`, color: t[2], borderRadius: 10, padding: "9px 14px", fontSize: 13, lineHeight: 1.5, marginBottom: 12 }}>{children}</div>;
}
const Badge = ({ risk }) => <span data-risk={risk} style={{ display: "inline-block", padding: "2px 9px", borderRadius: 100, fontSize: 11.5, fontWeight: 700, background: RISK[risk][1], color: RISK[risk][2] }}>{RISK[risk][0]}</span>;

function PeopleModal({ item, onClose }) {
  const [data, setData] = useState(null);
  useEffect(() => { api.get(`/discovery/people?source=${item.source}&external_id=${encodeURIComponent(item.external_id)}`).then(setData).catch(() => setData({ people: [], scopes: [], error: true })); }, [item]);
  return (
    <div role="dialog" aria-label={`Details for ${item.name}`} onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(17,24,39,0.45)", zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, width: 560, maxWidth: "92vw", maxHeight: "82vh", overflow: "auto", padding: "20px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}><h3 style={{ margin: 0, flex: 1, fontSize: 17 }}>{item.name}</h3><button style={link} onClick={onClose}>Close</button></div>
        {!data ? <div style={{ color: Z.textMuted }}>Loading…</div> : (<>
          <div style={{ fontSize: 12, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>What it can do</div>
          <div data-scopes style={{ marginBottom: 16 }}>
            {data.scopes.length === 0 ? <div style={{ fontSize: 13, color: Z.textMuted }}>No access details were recorded.</div> : data.scopes.map(s => (
              <div key={s.scope} style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0", fontSize: 13 }}><Badge risk={s.risk} /><span>{s.label}</span></div>))}
          </div>
          <div style={{ fontSize: 12, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Who authorized it ({n(data.people.length)})</div>
          {data.all_users && <Note tone="blue">An admin approved this app for everyone in the organization, so individual people aren't listed.</Note>}
          <div data-people style={{ maxHeight: 240, overflow: "auto", fontSize: 13 }}>
            {data.people.map(p => <div key={p} style={{ padding: "3px 0" }}>{p}</div>)}
            {data.people.length === 0 && !data.all_users && <div style={{ color: Z.textMuted }}>No people recorded.</div>}
          </div>
        </>)}
      </div>
    </div>
  );
}

function Discovery({ conn, reload }) {
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const [showSteps, setShowSteps] = useState(false);
  const syncing = conn && conn.sync && conn.sync.status === "running";
  async function act(kind) {
    setBusy(kind); setMsg(null);
    try { const r = await api.post(`/connectors/app_discovery/${kind}`); setMsg({ tone: r.ok ? "green" : "red", text: r.message }); } catch (e) { setMsg({ tone: "red", text: e.message || "Something went wrong." }); }
    setBusy(null); reload();
  }
  const sync = conn && conn.sync;
  const notes = (sync && sync.summary && sync.summary.notes) || [];
  return (
    <div style={card} data-card="discovery">
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 15, flex: 1 }}>Finding apps</h3>
        <button style={btn(false, busy || !(conn && conn.configured))} disabled={!!busy || !(conn && conn.configured)} onClick={() => act("test")}>{busy === "test" ? "Checking…" : "Check access"}</button>
        <button style={btn(true, busy || syncing || !(conn && conn.configured))} disabled={!!busy || syncing || !(conn && conn.configured)} onClick={() => act("sync")}>{syncing ? "Looking…" : "Find apps now"}</button>
      </div>
      <div style={{ fontSize: 13, color: Z.textSecondary, margin: "6px 0 8px" }}>
        Looks at the apps people have connected to their Google and Microsoft work accounts, and how much access each was given. It reads only: nothing is revoked or changed.{" "}
        <button type="button" style={link} onClick={() => setShowSteps(s => !s)}>{showSteps ? "Hide" : "Permissions to add"}</button>
      </div>
      {showSteps && conn && <ol data-steps style={{ fontSize: 13, color: Z.textSecondary, lineHeight: 1.6, margin: "0 0 10px", paddingLeft: 20 }}>{conn.guide.steps.map(s => <li key={s}>{s}</li>)}</ol>}
      {conn && !conn.configured && <Note tone="amber">Set up <strong>Google Workspace</strong> or <strong>Microsoft 365</strong> in the Integration Library first. Discovery reuses their saved credentials, so there is nothing new to paste.</Note>}
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}
      {sync && sync.status === "error" && <Note tone="red">{sync.message}</Note>}
      {sync && sync.last_at && sync.status !== "error" && <div style={{ fontSize: 12.5, color: Z.textSecondary }}>Last checked {when(sync.last_at)}. {sync.summary && sync.summary.found !== undefined ? `${n(sync.summary.found)} apps found, ${n(sync.summary.found_new)} new.` : ""}</div>}
      {notes.map(t => <Note key={t} tone="amber">{t}</Note>)}
    </div>
  );
}

export default function ShadowIT() {
  const [conn, setConn] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState("new");
  const [source, setSource] = useState("");
  const [risk, setRisk] = useState("");
  const [q, setQ] = useState("");
  const [message, setMessage] = useState(null);
  const [details, setDetails] = useState(null);
  const [other, setOther] = useState({});
  const reloadConn = useCallback(() => api.get("/connectors").then(l => setConn((Array.isArray(l) ? l : []).find(c => c.key === "app_discovery") || null)).catch(() => setConn(null)), []);
  const reload = useCallback(() => {
    const qs = new URLSearchParams({ status, ...(source && { source }), ...(risk && { risk }), ...(q.trim() && { q: q.trim() }) }).toString();
    return api.get(`/discovery/apps?${qs}`).then(d => { setData(d); setError(null); }).catch(e => setError(e.message || "Could not load the apps"));
  }, [status, source, risk, q]);
  useEffect(() => { reloadConn(); }, [reloadConn]);
  useEffect(() => { const t = setTimeout(reload, q ? 250 : 0); return () => clearTimeout(t); }, [reload, q]);
  const running = conn && conn.sync && conn.sync.status === "running";
  useEffect(() => {
    if (!running) return undefined;
    const id = setInterval(reloadConn, 3000);
    return () => { clearInterval(id); reload(); };
  }, [running, reloadConn, reload]);

  async function act(item, action, appId) {
    const r = await api.post("/discovery/act", { source: item.source, external_id: item.external_id, action, app_id: appId });
    setMessage({ tone: r.ok ? "green" : "red", text: r.message });
    reload();
  }
  const c = (data && data.counts) || {}, rv = (data && data.review) || {};
  const stat = (label, value, hint) => <div key={label} style={{ minWidth: 150 }}><div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div><div style={{ fontSize: 12.5, color: Z.textSecondary }}>{label}</div>{hint && <div style={{ fontSize: 11, color: Z.textMuted }}>{hint}</div>}</div>;

  return (
    <div style={{ padding: "24px 32px", maxWidth: 1250 }}>
      <h2 style={{ margin: "0 0 4px", fontSize: 22 }}>Shadow IT</h2>
      <div style={{ fontSize: 13.5, color: Z.textSecondary, marginBottom: 18 }}>Apps people connected to their work accounts that IT may not know about, and how much access they were given.</div>
      <Discovery conn={conn} reload={reloadConn} />
      {error && <Note tone="red">{error}</Note>}
      {data && (
        <div style={card} data-card="summary">
          <div style={{ display: "flex", gap: 36, flexWrap: "wrap" }} data-stats>
            {stat("Apps to review", n(c.new))}
            {stat("With high access", n(rv.high), "can read or send mail, or use all files")}
            {stat("People involved", n(rv.people), "in the apps to review")}
            {stat("Added to Tab", n(c.added))}
          </div>
        </div>)}
      <div style={card} data-card="list">
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
          {STATUS_TABS.map(([id, label]) => (
            <button key={id} type="button" aria-pressed={status === id} onClick={() => { setStatus(id); setData(null); }} style={{ ...btn(status === id), padding: "6px 14px" }}>{label}{data ? ` (${n((data.counts || {})[id])})` : ""}</button>))}
          <span style={{ flex: 1 }} />
          <select aria-label="Filter by source" style={input} value={source} onChange={e => setSource(e.target.value)}><option value="">All sources</option><option value="google">Google</option><option value="microsoft">Microsoft</option></select>
          <select aria-label="Filter by access" style={input} value={risk} onChange={e => setRisk(e.target.value)}><option value="">Any access</option><option value="high">High access</option><option value="medium">Medium access</option><option value="low">Sign-in only</option></select>
          <input aria-label="Search apps" style={{ ...input, width: 200 }} placeholder="Search apps…" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        {message && <Note tone={message.tone}>{message.text}</Note>}
        {!data ? <div style={{ color: Z.textMuted }}>Loading…</div> : data.items.length === 0 ? (
          <div style={{ fontSize: 13, color: Z.textMuted, padding: "12px 0" }} data-empty>
            {status === "new" ? (c.new === 0 && !c.known && !c.added && !c.ignored ? "Nothing found yet. Click Find apps now once Google or Microsoft is set up." : "Nothing here: every app found has been reviewed.") : "Nothing in this list."}
          </div>) : (
          <div style={{ overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
              <thead><tr><th style={th}>App</th><th style={th}>Found in</th><th style={th}>People</th><th style={th}>Access</th><th style={th}>First seen</th><th style={th} /></tr></thead>
              <tbody>
                {data.items.map(it => (
                  <tr key={`${it.source}:${it.external_id}`} data-row={`${it.source}:${it.external_id}`}>
                    <td style={td}><div style={{ fontWeight: 600 }}>{it.name}{it.kind === "native" && <span style={{ fontWeight: 500, color: Z.textMuted, fontSize: 11.5 }}> · installed app</span>}{it.kind === "internal" && <span style={{ fontWeight: 500, color: Z.textMuted, fontSize: 11.5 }}> · built in your organization</span>}</div>
                      {it.publisher && <div style={{ fontSize: 12, color: Z.textMuted }}>{it.publisher}</div>}
                      {it.app_name && <div style={{ fontSize: 12, color: Z.accent }}>{status === "known" ? "Already in Tab as" : "In Tab as"} {it.app_name}</div>}</td>
                    <td style={td}>{it.source_name}</td>
                    <td style={td}>{it.all_users ? <span title="An admin approved it for everyone">Everyone</span> : <button type="button" style={link} aria-label={`People who authorized ${it.name}`} onClick={() => setDetails(it)}>{n(it.user_count)}</button>}</td>
                    <td style={td}><Badge risk={it.risk} /><div style={{ fontSize: 12, color: Z.textSecondary, marginTop: 4, maxWidth: 260 }}>{(it.highlights || []).join(" · ")}</div></td>
                    <td style={td}>{day(it.first_seen_at)}</td>
                    <td style={{ ...td, whiteSpace: "nowrap" }}>
                      {status === "new" && (<>
                        <button type="button" style={btn(true)} aria-label={`Add ${it.name} as shadow IT`} onClick={() => act(it, "add")}>Add as shadow IT</button>
                        <button type="button" style={btn(false)} aria-label={`Approve ${it.name}`} onClick={() => act(it, "approve")}>Approve</button>
                        <button type="button" style={btn(false)} aria-label={`Ignore ${it.name}`} onClick={() => act(it, "ignore")}>Ignore</button>
                        <div style={{ marginTop: 6 }}>
                          <select aria-label={`Match ${it.name} to`} style={{ ...input, width: 150, padding: "4px 6px" }} value={other[`${it.source}:${it.external_id}`] || ""} onChange={e => setOther(o => ({ ...o, [`${it.source}:${it.external_id}`]: e.target.value }))}>
                            <option value="">Already in Tab as…</option>{data.apps.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                          </select>{" "}
                          <button type="button" style={btn(false, !other[`${it.source}:${it.external_id}`])} disabled={!other[`${it.source}:${it.external_id}`]} aria-label={`Confirm match for ${it.name}`} onClick={() => act(it, "match", other[`${it.source}:${it.external_id}`])}>Match</button>
                        </div></>)}
                      {status === "ignored" && <button type="button" style={btn(false)} aria-label={`Bring back ${it.name}`} onClick={() => act(it, "restore")}>Bring back</button>}
                    </td>
                  </tr>))}
              </tbody>
            </table>
            {data.more > 0 && <div style={{ fontSize: 12, color: Z.textMuted, padding: "8px 14px" }}>Showing the first {n(data.items.length)} of {n(data.items.length + data.more)}. Narrow the list with the filters.</div>}
          </div>)}
        <div style={{ fontSize: 12, color: Z.textMuted, marginTop: 10 }}>
          <strong>Add as shadow IT</strong> creates the app in Tab, flagged for follow-up, with the people who connected it. <strong>Approve</strong> adds it as an approved app. <strong>Ignore</strong> hides it from review.
        </div>
      </div>
      {details && <PeopleModal item={details} onClose={() => setDetails(null)} />}
    </div>
  );
}
