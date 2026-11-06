import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", accentText: "#3730A3",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", borderStrong: "#CBD5E1", cardBg: "#FFFFFF", pageBg: "#F4F6FA",
};

const STATUS = {
  available:  { label: "Not connected",   bg: "#F9FAFB",     fg: Z.textSecondary, dot: Z.textMuted, bd: Z.border },
  configured: { label: "Configured",      bg: Z.amberLight,  fg: Z.amberText,     dot: Z.amber,     bd: "#FDE68A" },
  connected:  { label: "Connected",       bg: Z.greenLight,  fg: Z.greenText,     dot: Z.green,     bd: "#BBF7D0" },
  syncing:    { label: "Syncing…",        bg: Z.accentLight, fg: Z.accentText,    dot: Z.accent,    bd: "#C7D2FE" },
  error:      { label: "Needs attention", bg: Z.redLight,    fg: Z.redText,       dot: Z.red,       bd: "#FECACA" },
};

function fmtWhen(iso) {
  if (!iso) return "Never";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) +
    ", " + d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function num(n) {
  return typeof n === "number" ? n.toLocaleString() : "0";
}

function StatusPill({ status }) {
  const s = STATUS[status] || STATUS.available;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 10px", borderRadius: 100, fontSize: 12, fontWeight: 600, background: s.bg, color: s.fg, border: `1px solid ${s.bd}`, whiteSpace: "nowrap" }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.dot }} />
      {s.label}
    </span>
  );
}

function Tile({ c, size = 48 }) {
  return (
    <div style={{ width: size, height: size, borderRadius: Math.round(size * 0.25), background: c.color, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: Math.round(size * 0.36), flexShrink: 0 }}>
      {c.initials || c.name.slice(0, 2)}
    </div>
  );
}

function Chip({ children, tone = "gray" }) {
  const tones = {
    gray: { bg: "#F3F4F6", fg: Z.textSecondary },
    blue: { bg: Z.accentLight, fg: Z.accentText },
    green: { bg: Z.greenLight, fg: Z.greenText },
  };
  const t = tones[tone] || tones.gray;
  return <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 100, fontSize: 11, fontWeight: 600, background: t.bg, color: t.fg, marginRight: 6, marginBottom: 4 }}>{children}</span>;
}

const btn = (primary, disabled) => ({
  padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600,
  cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1,
  border: primary ? "none" : `1px solid ${Z.borderStrong}`,
  background: primary ? Z.accent : Z.cardBg, color: primary ? "#fff" : Z.textPrimary,
});

// ───────────────────────────────────────────────────────────── catalog card
function Card({ c, onOpen }) {
  const sum = c.sync?.summary || {};
  let detail = null;
  if (c.status === "syncing") detail = c.sync?.message || "Syncing…";
  else if (c.status === "error") detail = c.sync?.message || c.last_test?.message || "Something went wrong.";
  else if (sum.matched !== undefined) detail = `${num(sum.matched)} users enriched · ${num(sum.unmatched)} unmatched`;
  else if (sum.events !== undefined) detail = `${num(sum.events)} sign-ins read · ${num(sum.updated)} records updated`;

  return (
    <div style={{ background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, padding: "1.25rem", display: "flex", flexDirection: "column", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 12 }}>
        <Tile c={c} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: Z.textPrimary }}>{c.name}</h3>
          <p style={{ margin: "2px 0 0", fontSize: 12, color: Z.textMuted }}>
            {c.kind === "global" ? "Covers all apps" : c.vendor}
          </p>
        </div>
        <StatusPill status={c.status} />
      </div>

      <p style={{ margin: "0 0 10px", fontSize: 13, color: Z.textSecondary, lineHeight: 1.5, flex: 1 }}>{c.description}</p>

      <div style={{ marginBottom: 10 }}>
        {c.provides.map(p => <Chip key={p} tone="blue">{p}</Chip>)}
      </div>

      <div style={{ borderTop: `1px solid ${Z.border}`, paddingTop: 10, marginBottom: 12, minHeight: 38 }}>
        <p style={{ margin: 0, fontSize: 12, color: Z.textMuted }}>Last refresh: {fmtWhen(c.sync?.last_at)}</p>
        {detail && (
          <p style={{ margin: "3px 0 0", fontSize: 12, color: c.status === "error" ? Z.redText : Z.textSecondary }}>{detail}</p>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={() => onOpen(c.key, true)} style={btn(false)}>Guide</button>
        <button onClick={() => onOpen(c.key, false)} style={btn(!c.configured)}>{c.configured ? "Manage" : "Connect"}</button>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────── target app picker
function TargetPicker({ connectorKey, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [items, setItems] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const data = await api.get(`/connectors/${connectorKey}/apps${q ? `?q=${encodeURIComponent(q)}` : ""}`);
        if (!cancelled) setItems(Array.isArray(data) ? data : []);
      } catch (e) {
        if (!cancelled) setItems([]);
      }
    }, q ? 300 : 0);
    return () => { cancelled = true; clearTimeout(t); };
  }, [open, q, connectorKey]);

  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: Z.textPrimary, marginBottom: 4 }}>App this connector enriches</label>
      <p style={{ margin: "0 0 6px", fontSize: 12, color: Z.textMuted }}>License and activity data is written onto the people Okta has assigned to this app.</p>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: "#F9FAFB" }}>
        <span style={{ flex: 1, fontSize: 13, color: value ? Z.textPrimary : Z.textMuted }}>
          {value ? value.name : "Not chosen yet — save to auto-pick the best match, or choose below"}
        </span>
        <button onClick={() => setOpen(o => !o)} style={{ background: "none", border: "none", color: Z.accent, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
          {open ? "Done" : "Change"}
        </button>
      </div>
      {open && (
        <div style={{ marginTop: 8, border: `1px solid ${Z.border}`, borderRadius: 8, overflow: "hidden" }}>
          <input
            autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Search your apps…"
            style={{ width: "100%", boxSizing: "border-box", padding: "8px 12px", border: "none", borderBottom: `1px solid ${Z.border}`, fontSize: 13, outline: "none" }}
          />
          <div style={{ maxHeight: 180, overflowY: "auto" }}>
            {items === null && <p style={{ margin: 0, padding: 12, fontSize: 12, color: Z.textMuted }}>Loading…</p>}
            {items !== null && items.length === 0 && <p style={{ margin: 0, padding: 12, fontSize: 12, color: Z.textMuted }}>No matching apps.</p>}
            {(items || []).map(a => (
              <button key={a.id} onClick={() => { onChange({ id: a.id, name: a.name }); setOpen(false); setQ(""); }}
                style={{ display: "flex", justifyContent: "space-between", width: "100%", padding: "8px 12px", background: value && value.id === a.id ? Z.accentLight : Z.cardBg, border: "none", borderBottom: `1px solid ${Z.border}`, cursor: "pointer", fontSize: 13, textAlign: "left" }}>
                <span style={{ color: Z.textPrimary, fontWeight: 500 }}>{a.name}</span>
                <span style={{ color: Z.textMuted, fontSize: 12 }}>{num(a.assigned_users)} assigned</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────── manage panel
function ManagePanel({ c, startOnGuide, onClose, onUpdate }) {
  const [values, setValues] = useState(() => ({ ...c.values }));
  const [target, setTarget] = useState(c.target_app);
  const [busy, setBusy] = useState(null);
  const [note, setNote] = useState(null);
  const [showGuide, setShowGuide] = useState(Boolean(startOnGuide) || !c.configured);

  useEffect(() => {
    const onKey = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (!target && c.target_app) setTarget(c.target_app);
  }, [c.target_app]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(kind, path, body) {
    setBusy(kind);
    setNote(null);
    try {
      const r = await api.post(`/connectors/${c.key}/${path}`, body);
      setNote({ ok: Boolean(r.ok), text: r.message });
      if (r.connector) onUpdate(r.connector);
      return r;
    } catch (e) {
      setNote({ ok: false, text: e.message || "Request failed" });
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    const r = await act("save", "config", { values, target_app_id: target ? target.id : null });
    if (r && r.ok) {
      const blank = {};
      c.fields.filter(f => f.secret).forEach(f => { blank[f.key] = ""; });
      setValues(v => ({ ...v, ...blank }));
    }
  }

  async function disconnect() {
    if (!window.confirm(`Disconnect ${c.name}? Data already synced stays in place.`)) return;
    const r = await act("disconnect", "disconnect");
    if (r && r.ok) onClose();
  }

  const syncing = c.status === "syncing";
  const sum = c.sync?.summary || {};
  const licenseCounts = sum.license_counts || {};
  const isApp = c.kind === "app";
  const canSave = isApp && busy === null;

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(17,24,39,0.45)", zIndex: 200, display: "flex", alignItems: "flex-start", justifyContent: "center", overflowY: "auto", padding: "4vh 1rem" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: Z.cardBg, borderRadius: 14, width: "100%", maxWidth: 680, boxShadow: "0 20px 50px rgba(0,0,0,0.25)" }}>
        {/* header */}
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "1.25rem 1.5rem", borderBottom: `1px solid ${Z.border}` }}>
          <Tile c={c} size={44} />
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: Z.textPrimary }}>{c.name}</h2>
              <StatusPill status={c.status} />
            </div>
            <p style={{ margin: "3px 0 0", fontSize: 13, color: Z.textSecondary }}>{c.description}</p>
          </div>
          <button onClick={onClose} title="Close (Esc)" aria-label="Close" style={{ background: "none", border: "none", fontSize: 28, lineHeight: 1, color: Z.textMuted, cursor: "pointer" }}>×</button>
        </div>

        <div style={{ padding: "1.25rem 1.5rem" }}>
          {/* guide */}
          <div style={{ background: Z.accentLight, border: "1px solid #C7D2FE", borderRadius: 10, marginBottom: 18 }}>
            <button onClick={() => setShowGuide(s => !s)} style={{ width: "100%", display: "flex", justifyContent: "space-between", padding: "10px 14px", background: "none", border: "none", cursor: "pointer", fontSize: 13, fontWeight: 700, color: Z.accentText }}>
              <span>Setup guide</span><span>{showGuide ? "Hide" : "Show"}</span>
            </button>
            {showGuide && (
              <div style={{ padding: "0 14px 12px" }}>
                <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: Z.accentText, lineHeight: 1.7 }}>
                  {c.guide.steps.map((s, i) => <li key={i}>{s}</li>)}
                </ol>
                {c.guide.docs_url && (
                  <a href={c.guide.docs_url} target="_blank" rel="noreferrer" style={{ display: "inline-block", marginTop: 8, fontSize: 12, fontWeight: 600, color: Z.accent }}>Open vendor docs ↗</a>
                )}
              </div>
            )}
          </div>

          {/* credentials */}
          {isApp && c.fields.map(f => (
            <div key={f.key} style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: Z.textPrimary, marginBottom: 4 }}>
                {f.label}{f.required ? "" : " (optional)"}
              </label>
              {f.help && <p style={{ margin: "0 0 5px", fontSize: 12, color: Z.textMuted }}>{f.help}</p>}
              {f.type === "textarea" ? (
                <textarea
                  rows={5} value={values[f.key] || ""} onChange={e => setValues(v => ({ ...v, [f.key]: e.target.value }))}
                  placeholder={c.secrets_set[f.key] ? "•••••••• saved — leave blank to keep" : (f.placeholder || "")}
                  style={{ width: "100%", boxSizing: "border-box", padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 12, fontFamily: "monospace", outline: "none", resize: "vertical" }}
                />
              ) : (
                <input
                  type={f.type === "password" ? "password" : "text"} value={values[f.key] || ""}
                  onChange={e => setValues(v => ({ ...v, [f.key]: e.target.value }))}
                  placeholder={c.secrets_set[f.key] ? "•••••••• saved — leave blank to keep" : (f.placeholder || "")}
                  autoComplete="off"
                  style={{ width: "100%", boxSizing: "border-box", padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, outline: "none", fontFamily: f.secret ? "monospace" : "inherit" }}
                />
              )}
            </div>
          ))}

          {isApp && <TargetPicker connectorKey={c.key} value={target} onChange={setTarget} />}

          {/* message from the last action */}
          {note && (
            <div style={{ background: note.ok ? Z.greenLight : Z.redLight, border: `1px solid ${note.ok ? "#BBF7D0" : "#FECACA"}`, color: note.ok ? Z.greenText : Z.redText, borderRadius: 8, padding: "10px 14px", fontSize: 13, marginBottom: 14 }}>
              {note.text}
            </div>
          )}

          {/* actions */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            {isApp && <button onClick={save} disabled={!canSave} style={btn(true, !canSave)}>{busy === "save" ? "Saving…" : "Save"}</button>}
            {c.configured && <button onClick={() => act("test", "test")} disabled={busy !== null} style={btn(false, busy !== null)}>{busy === "test" ? "Testing…" : "Test connection"}</button>}
            {c.configured && <button onClick={() => act("sync", "sync")} disabled={busy !== null || syncing} style={btn(false, busy !== null || syncing)}>{syncing ? "Syncing…" : busy === "sync" ? "Starting…" : "Sync now"}</button>}
            {isApp && c.configured && <button onClick={disconnect} disabled={busy !== null} style={{ marginLeft: "auto", background: "none", border: "none", color: Z.red, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Disconnect</button>}
          </div>

          {/* last results */}
          {(c.last_test?.at || c.sync?.last_at || syncing || c.sync?.message) && (
            <div style={{ marginTop: 20, borderTop: `1px solid ${Z.border}`, paddingTop: 14, fontSize: 13 }}>
              {c.last_test?.at && (
                <p style={{ margin: "0 0 6px", color: c.last_test.ok ? Z.greenText : Z.redText }}>
                  <strong>Last test</strong> ({fmtWhen(c.last_test.at)}): {c.last_test.message}
                </p>
              )}
              {(syncing || c.sync?.message) && (
                <p style={{ margin: "0 0 6px", color: c.status === "error" ? Z.redText : Z.textSecondary }}>
                  <strong>{syncing ? "Sync in progress" : "Last sync"}</strong>
                  {c.sync?.last_at && !syncing ? ` (${fmtWhen(c.sync.last_at)})` : ""}: {c.sync?.message}
                </p>
              )}
              {Object.keys(licenseCounts).length > 0 && (
                <div style={{ margin: "8px 0" }}>
                  {Object.entries(licenseCounts).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <Chip key={k} tone="green">{k}: {num(v)}</Chip>
                  ))}
                </div>
              )}
              {sum.unmatched > 0 && sum.unmatched_sample && sum.unmatched_sample.length > 0 && (
                <details style={{ marginTop: 6 }}>
                  <summary style={{ cursor: "pointer", color: Z.textSecondary, fontWeight: 600 }}>
                    {num(sum.unmatched)} {c.name} accounts aren't assigned to this app in Okta (showing {sum.unmatched_sample.length})
                  </summary>
                  <p style={{ margin: "6px 0", fontSize: 12, color: Z.textMuted }}>
                    Often former employees, contractors or shared mailboxes that still hold a seat — worth a look for reclaiming licenses.
                  </p>
                  <div style={{ maxHeight: 140, overflowY: "auto", fontSize: 12, color: Z.textSecondary, lineHeight: 1.6 }}>
                    {sum.unmatched_sample.map(e => <div key={e}>{e}</div>)}
                  </div>
                </details>
              )}
              {sum.apps_not_in_library > 0 && (
                <p style={{ margin: "6px 0 0", fontSize: 12, color: Z.textMuted }}>
                  {num(sum.apps_not_in_library)} apps in the sign-in log aren't in your app list yet (they appear after the next Okta sync).
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────── page
export default function IntegrationLibrary() {
  const [connectors, setConnectors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState(null);   // { key, guide }

  const load = useCallback(async () => {
    try {
      const data = await api.get("/connectors");
      setConnectors(Array.isArray(data) ? data : []);
      setError(null);
    } catch (e) {
      setError(e.message || "Could not load the library");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // while anything is syncing, refresh every few seconds
  const anySyncing = connectors.some(c => c.status === "syncing");
  useEffect(() => {
    if (!anySyncing) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [anySyncing, load]);

  const update = useCallback(conn => {
    setConnectors(list => list.map(x => (x.key === conn.key ? conn : x)));
  }, []);

  const shown = connectors
    .filter(c => {
      const needle = q.trim().toLowerCase();
      if (needle && !(`${c.name} ${c.vendor} ${c.description}`.toLowerCase().includes(needle))) return false;
      if (filter === "connected") return c.configured;
      if (filter === "available") return !c.configured;
      return true;
    })
    .sort((a, b) => Number(b.configured) - Number(a.configured) || a.name.localeCompare(b.name));

  const connectedCount = connectors.filter(c => c.configured).length;
  const openConnector = open ? connectors.find(c => c.key === open.key) : null;

  const pill = (id, label) => (
    <button key={id} onClick={() => setFilter(id)} style={{ padding: "6px 14px", borderRadius: 100, fontSize: 13, fontWeight: 600, cursor: "pointer", border: `1px solid ${filter === id ? Z.accent : Z.border}`, background: filter === id ? Z.accentLight : Z.cardBg, color: filter === id ? Z.accent : Z.textSecondary }}>
      {label}
    </button>
  );

  return (
    <div>
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Integration Library</h1>
        <p style={{ margin: "4px 0 0", fontSize: 14, color: Z.textSecondary }}>
          Connect apps to see who holds which license and when they last used it. Okta decides who is assigned; connectors add the rest.
        </p>
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: "1.25rem" }}>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search integrations…"
          style={{ flex: "1 1 240px", maxWidth: 360, padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, outline: "none" }} />
        {pill("all", `All (${connectors.length})`)}
        {pill("connected", `Connected (${connectedCount})`)}
        {pill("available", `Available (${connectors.length - connectedCount})`)}
      </div>

      {error && (
        <div style={{ background: Z.redLight, border: "1px solid #FECACA", color: Z.redText, borderRadius: 8, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>
          {error} <button onClick={load} style={{ marginLeft: 8, background: "none", border: "none", color: Z.red, fontWeight: 700, cursor: "pointer" }}>Retry</button>
        </div>
      )}

      {loading ? (
        <p style={{ color: Z.textMuted, fontSize: 14 }}>Loading…</p>
      ) : shown.length === 0 ? (
        <p style={{ color: Z.textMuted, fontSize: 14 }}>No integrations match.</p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 16 }}>
          {shown.map(c => <Card key={c.key} c={c} onOpen={(key, guide) => setOpen({ key, guide })} />)}
        </div>
      )}

      {openConnector && (
        <ManagePanel key={openConnector.key} c={openConnector} startOnGuide={open.guide} onUpdate={update} onClose={() => setOpen(null)} />
      )}
    </div>
  );
}
