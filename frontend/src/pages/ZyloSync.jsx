import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
  greenLight: "#F0FDF4", greenText: "#15803D", amberLight: "#FFFBEB", amberText: "#92400E", redLight: "#FEF2F2", redText: "#B91C1C",
};
const card = { background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", padding: "16px 20px", marginBottom: 16 };
const input = { width: "100%", boxSizing: "border-box", padding: "8px 10px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, fontFamily: "inherit" };
const th = { padding: "9px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` };
const td = { padding: "9px 14px", fontSize: 13, borderBottom: `1px solid ${Z.border}`, color: Z.textPrimary, verticalAlign: "middle" };
const btn = (primary, disabled) => ({ padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1,
  border: `1px solid ${primary ? Z.accent : Z.border}`, background: primary ? Z.accent : "#fff", color: primary ? "#fff" : Z.textPrimary });
const chip = { padding: "4px 10px", borderRadius: 100, fontSize: 12, fontWeight: 600, cursor: "pointer", border: `1px solid ${Z.accent}`, background: Z.accentLight, color: "#3730A3", marginRight: 6 };
const link = { background: "none", border: "none", padding: 0, color: Z.accent, fontWeight: 600, fontSize: 12.5, cursor: "pointer" };

function Note({ tone = "amber", children }) {
  const t = { amber: [Z.amberLight, "#FDE68A", Z.amberText], red: [Z.redLight, "#FECACA", Z.redText], green: [Z.greenLight, "#BBF7D0", Z.greenText], blue: [Z.accentLight, "#C7D2FE", "#3730A3"] }[tone];
  return <div style={{ background: t[0], border: `1px solid ${t[1]}`, color: t[2], borderRadius: 10, padding: "9px 14px", fontSize: 13, lineHeight: 1.5, marginBottom: 12 }}>{children}</div>;
}
const when = iso => (iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "never");
const n = v => Number(v || 0).toLocaleString("en-US");

function Connection({ conn, reload }) {
  const [form, setForm] = useState({ token_id: "", token_secret: "", payments_from: "" });
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const [showSteps, setShowSteps] = useState(false);
  useEffect(() => { if (conn) setForm(f => ({ ...f, token_id: conn.values.token_id || "", payments_from: conn.values.payments_from || "" })); }, [conn && conn.values.token_id, conn && conn.values.payments_from]); // eslint-disable-line react-hooks/exhaustive-deps
  const secretSaved = conn && conn.secrets_set && conn.secrets_set.token_secret;
  const syncing = conn && conn.sync && conn.sync.status === "running";

  async function act(kind) {
    setBusy(kind); setMsg(null);
    try {
      const r = kind === "save" ? await api.post("/connectors/zylo/config", { values: form, target_app_id: null })
        : kind === "test" ? await api.post("/connectors/zylo/test")
        : kind === "sync" ? await api.post("/connectors/zylo/sync")
        : await api.post("/connectors/zylo/disconnect");
      setMsg({ tone: r.ok ? "green" : "red", text: r.message });
      if (kind === "save") setForm(f => ({ ...f, token_secret: "" }));
    } catch (e) { setMsg({ tone: "red", text: e.message || "Something went wrong." }); }
    setBusy(null); reload();
  }

  return (
    <div style={card} data-card="connection">
      <h3 style={{ margin: "0 0 4px", fontSize: 15 }}>Connection</h3>
      <div style={{ fontSize: 13, color: Z.textSecondary, marginBottom: 12 }}>
        Tab reads your apps, contracts and spend from Zylo's API each night. It is read-only, and it includes whatever Spendflo feeds into Zylo.{" "}
        <button type="button" style={link} onClick={() => setShowSteps(s => !s)}>{showSteps ? "Hide" : "How to create the token"}</button>
      </div>
      {showSteps && conn && (
        <ol data-steps style={{ fontSize: 13, color: Z.textSecondary, lineHeight: 1.6, margin: "0 0 12px", paddingLeft: 20 }}>
          {conn.guide.steps.map(s => <li key={s}>{s}</li>)}
          {conn.guide.docs_url && <li><a href={conn.guide.docs_url} target="_blank" rel="noreferrer" style={{ color: Z.accent }}>Zylo's guide to API tokens</a></li>}
        </ol>)}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: Z.textSecondary }}>Token ID
          <input aria-label="Zylo token ID" style={input} value={form.token_id} onChange={e => setForm(f => ({ ...f, token_id: e.target.value }))} autoComplete="off" /></label>
        <label style={{ fontSize: 12, fontWeight: 600, color: Z.textSecondary }}>Token Secret
          <input aria-label="Zylo token secret" type="password" style={input} value={form.token_secret} onChange={e => setForm(f => ({ ...f, token_secret: e.target.value }))} autoComplete="new-password"
                 placeholder={secretSaved ? "Saved. Leave blank to keep it." : ""} /></label>
        <label style={{ fontSize: 12, fontWeight: 600, color: Z.textSecondary }}>Sync spend from (optional)
          <input aria-label="Sync spend from" style={input} value={form.payments_from} onChange={e => setForm(f => ({ ...f, payments_from: e.target.value }))} placeholder="2026-01-01" /></label>
      </div>
      <div style={{ fontSize: 12, color: Z.textMuted, margin: "6px 0 12px" }}>
        Leave the date empty unless Tab already holds uploaded payments. Then enter the first month it does not, so nothing is counted twice.
      </div>
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <button style={btn(true, busy)} disabled={!!busy} onClick={() => act("save")}>{busy === "save" ? "Saving…" : "Save"}</button>
        <button style={btn(false, busy || !(conn && conn.configured))} disabled={!!busy || !(conn && conn.configured)} onClick={() => act("test")}>{busy === "test" ? "Testing…" : "Test connection"}</button>
        <button style={btn(false, busy || syncing || !(conn && conn.configured))} disabled={!!busy || syncing || !(conn && conn.configured)} onClick={() => act("sync")}>{syncing ? "Syncing…" : "Sync now"}</button>
        {conn && conn.configured && <button type="button" style={{ ...link, marginLeft: "auto", color: Z.redText }} onClick={() => { if (window.confirm("Remove the saved Zylo token? Data already synced stays in Tab.")) act("disconnect"); }}>Disconnect</button>}
      </div>
    </div>
  );
}

function Results({ conn }) {
  const sync = conn && conn.sync;
  const s = (sync && sync.summary) || {};
  if (!sync || (!sync.last_at && sync.status !== "running" && sync.status !== "error")) {
    return <div style={card}><h3 style={{ margin: "0 0 4px", fontSize: 15 }}>Last sync</h3><div style={{ fontSize: 13, color: Z.textMuted }}>No sync has run yet. Save the token, then click Sync now. After that it runs by itself every night.</div></div>;
  }
  const c = s.contracts || {}, p = s.payments || null;
  const stat = (label, value, hint) => <div key={label} style={{ minWidth: 150 }}><div style={{ fontSize: 22, fontWeight: 700 }}>{value}</div><div style={{ fontSize: 12, color: Z.textSecondary }}>{label}</div>{hint && <div style={{ fontSize: 11, color: Z.textMuted }}>{hint}</div>}</div>;
  return (
    <div style={card} data-card="results">
      <h3 style={{ margin: "0 0 4px", fontSize: 15 }}>Last sync</h3>
      <div style={{ fontSize: 12.5, color: Z.textSecondary, marginBottom: 10 }}>
        {sync.status === "running" ? "Running now…" : sync.status === "error" ? "Failed" : `Finished ${when(sync.last_at)}`}
        {sync.message && sync.status !== "ok" ? ` — ${sync.message}` : ""}
      </div>
      {sync.status === "error" && <Note tone="red">{sync.message}</Note>}
      {sync.status !== "error" && s.apps !== undefined && (
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginBottom: 8 }} data-stats>
          {stat("Zylo apps matched", `${n(s.apps_matched)} of ${n(s.apps)}`, s.apps_unmatched ? `${n(s.apps_unmatched)} need matching` : null)}
          {stat("Categories filled in", n(s.categories_set), `${n(s.apps_filled)} apps got owners, functions or details`)}
          {stat("Contracts", `${n(c.created)} new`, `${n(c.updated)} updated, ${n(c.adopted)} already in Tab`)}
          {stat("Spend", p ? `${n(p.added)} new` : "not synced", p ? `${n(p.corrected)} corrected` : null)}
        </div>)}
      {(s.notes || []).map(t => <Note key={t} tone="amber">{t}</Note>)}
    </div>
  );
}

function Matching({ refreshKey, onChanged }) {
  const [view, setView] = useState("unmatched");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [other, setOther] = useState({});
  const load = useCallback(() => { api.get(`/zylo/matches?status=${view}`).then(setData).catch(e => setError(e.message || "Could not load the matches")); }, [view]);
  useEffect(() => { load(); }, [load, refreshKey]);

  async function post(path, body) {
    const r = await api.post(path, body);
    setMessage({ tone: r.ok ? "green" : "red", text: r.message });
    load(); if (r.ok && onChanged) onChanged();
  }
  if (error) return <div style={card}><Note tone="red">{error}</Note></div>;
  if (!data) return <div style={card}>Loading…</div>;
  const total = data.counts.matched + data.counts.unmatched + data.counts.ignored;
  return (
    <div style={card} data-card="matching">
      <h3 style={{ margin: "0 0 4px", fontSize: 15 }}>Match Zylo apps to Tab apps</h3>
      <div style={{ fontSize: 13, color: Z.textSecondary, marginBottom: 10 }} data-counts>
        {total === 0 ? "Nothing to match yet: run a sync first." : <>{n(data.counts.matched)} matched · <strong>{n(data.counts.unmatched)} need matching</strong> · {n(data.counts.ignored)} left out</>}
      </div>
      {message && <Note tone={message.tone}>{message.text}</Note>}
      <div style={{ marginBottom: 10 }}>
        {[["unmatched", "Needs matching"], ["ignored", "Left out"]].map(([id, label]) => (
          <button key={id} type="button" onClick={() => { setView(id); setData(null); }} style={{ ...btn(view === id), marginRight: 8, padding: "5px 12px" }}>{label}</button>))}
      </div>
      {data.items.length === 0 ? <div style={{ fontSize: 13, color: Z.textMuted }}>{view === "unmatched" ? (total ? "Every Zylo app is matched or left out. Nice." : "") : "No apps are being left out."}</div> : (
        <div style={{ overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
            <thead><tr><th style={th}>Zylo app</th><th style={th}>{view === "unmatched" ? "Which Tab app is it?" : ""}</th><th style={th} /></tr></thead>
            <tbody>
              {data.items.map(it => (
                <tr key={it.zylo_id} data-row={it.zylo_id}>
                  <td style={{ ...td, fontWeight: 600 }}>{it.name}</td>
                  <td style={td}>
                    {view === "unmatched" && (<>
                      {it.suggestions.map(s => <button key={s.app_id} type="button" style={chip} title={`Closeness ${Math.round(s.score * 100)}%`} onClick={() => post("/zylo/match", { zylo_id: it.zylo_id, app_id: s.app_id })}>{s.name}</button>)}
                      <select aria-label={`Match ${it.name} to`} style={{ ...input, width: 190, display: "inline-block" }} value={other[it.zylo_id] || ""} onChange={e => setOther(o => ({ ...o, [it.zylo_id]: e.target.value }))}>
                        <option value="">Another Tab app…</option>
                        {data.apps.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                      </select>{" "}
                      <button type="button" style={btn(false, !other[it.zylo_id])} disabled={!other[it.zylo_id]} aria-label={`Confirm match for ${it.name}`} onClick={() => post("/zylo/match", { zylo_id: it.zylo_id, app_id: other[it.zylo_id] })}>Match</button>
                    </>)}
                  </td>
                  <td style={{ ...td, textAlign: "right", whiteSpace: "nowrap" }}>
                    <button type="button" style={link} onClick={() => post("/zylo/status", { zylo_id: it.zylo_id, status: view === "unmatched" ? "ignored" : "unmatched" })}>{view === "unmatched" ? "Leave out" : "Bring back"}</button>
                  </td>
                </tr>))}
            </tbody>
          </table>
          {data.more > 0 && <div style={{ fontSize: 12, color: Z.textMuted, padding: "8px 14px" }}>Showing the first {n(data.items.length)}. {n(data.more)} more appear as you match these.</div>}
        </div>)}
      <div style={{ fontSize: 12, color: Z.textMuted, marginTop: 10 }}>Matched apps get their category, contracts and spend on the next sync. Apps you leave out are skipped every time.</div>
    </div>
  );
}

export default function ZyloSync() {
  const [conn, setConn] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => api.get("/connectors").then(list => { setConn((Array.isArray(list) ? list : []).find(c => c.key === "zylo") || null); setError(null); }).catch(e => setError(e.message || "Could not load Zylo's status")), []);
  useEffect(() => { reload(); }, [reload]);
  const running = conn && conn.sync && conn.sync.status === "running";
  useEffect(() => {                                                     // while a sync runs, keep checking on it, and refresh the match list when it ends
    if (!running) return undefined;
    const id = setInterval(reload, 3000);
    return () => { clearInterval(id); setTick(t => t + 1); };
  }, [running, reload]);

  return (
    <div style={{ padding: "24px 32px", maxWidth: 1100 }}>
      <h2 style={{ margin: "0 0 4px", fontSize: 22 }}>Zylo Sync</h2>
      <div style={{ fontSize: 13.5, color: Z.textSecondary, marginBottom: 18 }}>Keep categories, owners, contracts and spend up to date automatically, with no uploads.</div>
      {error && <Note tone="red">{error}</Note>}
      {!conn && !error && <div style={card}>Loading…</div>}
      {conn && (<>
        <Connection conn={conn} reload={reload} />
        <Results conn={conn} />
        <Matching refreshKey={tick} onChanged={reload} />
      </>)}
    </div>
  );
}
