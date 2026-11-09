import { useState, useEffect, useMemo } from "react";
import { api } from "../api/client";
import { Modal, Note, btn as dlgBtn, send } from "./AppTabs";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", navy: "#1B2A4A",
  amberLight: "#FFFBEB", amberText: "#92400E", red: "#DC2626", redText: "#B91C1C",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
};

// Colour bands, left to right: most recent -> never.
const BAND_ORDER = [
  ["d30", "0 - 30 days", "linear-gradient(90deg,#3B9EFF,#BBE3FF)", "#3B9EFF"],
  ["d60", "31 - 60 days", "linear-gradient(90deg,#4CC55F,#B9EBA6)", "#4CC55F"],
  ["d90", "61 - 90 days", "linear-gradient(90deg,#FB923C,#FDC892)", "#FB923C"],
  ["d91", "91+ days", "linear-gradient(90deg,#8B5CCF,#D9BDF2)", "#8B5CCF"],
  ["none", "No activity", "linear-gradient(90deg,#2563C9,#6FA2EA)", "#2563C9"],
];
const BAND = Object.fromEntries(BAND_ORDER.map(([id, label, grad, dot]) => [id, { label, grad, dot }]));
const bandOf = days => (days === null || days === undefined ? "none" : days <= 30 ? "d30" : days <= 60 ? "d60" : days <= 90 ? "d90" : "d91");

const COLUMNS = [
  { id: "email", label: "Login Email", locked: true },
  { id: "first_name", label: "First Name" },
  { id: "last_name", label: "Last Name" },
  { id: "department", label: "Department" },
  { id: "title", label: "Title", off: true },
  { id: "in_roster", label: "In Employee Roster", kind: "bool", needs: "roster" },
  { id: "external_status", label: "External Status" },
  { id: "last_activity", label: "Last Activity Date", kind: "date", align: "right" },
  { id: "days_since", label: "Days Since Activity", kind: "number", align: "right" },
  { id: "days_active", label: "Days Active (of last 90)", kind: "number", align: "right", needs: "days" },
  { id: "active", label: "Active", kind: "bool" },
  { id: "license", label: "License", needs: "license" },
  { id: "cost_center", label: "Cost Center" },
  { id: "division", label: "Division" },
  { id: "employee_type", label: "Employee Type", off: true },
  { id: "organization", label: "Organization", off: true },
  { id: "external_user_id", label: "External User ID", off: true },
  { id: "source", label: "Source", off: true },
  { id: "assigned_on", label: "Assigned On", kind: "date", align: "right", off: true },
];
const DEFAULT_COLS = COLUMNS.filter(c => !c.off).map(c => c.id);
const FILTERABLE = [["department", "Department"], ["cost_center", "Cost Center"], ["division", "Division"], ["license", "License"],
                    ["external_status", "External Status"], ["employee_type", "Employee Type"], ["active", "Active"], ["in_roster", "In Employee Roster"]];
const BOOLEAN_FIELDS = ["active", "in_roster"];
const facetValue = (u, f) => (BOOLEAN_FIELDS.includes(f) ? (u[f] === true ? "Yes" : u[f] === false ? "No" : "(blank)") : (u[f] || "(blank)"));
const STORE_KEY = "tab.appUsers.columns.v2";
const PAGE = 100;

const fmtDate = iso => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};
const loadCols = () => {
  try { const v = JSON.parse(window.localStorage.getItem(STORE_KEY)); if (Array.isArray(v) && v.length) return v; } catch (e) { /* storage unavailable */ }
  return null;
};

function sortValue(col, u) {
  if (col.kind === "bool") return u[col.id] === null || u[col.id] === undefined ? null : (u[col.id] ? 1 : 0);
  if (col.kind === "date") return u[col.id] ? new Date(u[col.id]).getTime() : -Infinity;      // never = oldest
  if (col.kind === "number") return u[col.id] === null || u[col.id] === undefined ? Infinity : u[col.id];   // never = most idle
  return u[col.id] ? String(u[col.id]).toLowerCase() : null;
}

function Menu({ onClose, children, width = 300, right }) {
  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
      <div style={{ position: "absolute", top: "calc(100% + 6px)", [right ? "right" : "left"]: 0, width, maxHeight: 440, overflowY: "auto", zIndex: 41,
                    background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 10, boxShadow: "0 10px 30px rgba(0,0,0,0.16)", padding: "10px 14px" }}>
        {children}
      </div>
    </>
  );
}

const tbBtn = active => ({
  display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 12px", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer",
  border: `1px solid ${active ? Z.accent : Z.border}`, background: active ? Z.accentLight : Z.cardBg, color: active ? Z.accent : Z.textPrimary,
});

function RosterDialog({ onClose, onSaved }) {
  const [text, setText] = useState("");
  const [count, setCount] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  useEffect(() => { api.get("/employee-roster").then(r => setCount(r.count)).catch(() => setCount(null)); }, []);
  const readFile = e => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setText(String(reader.result || ""));
    reader.readAsText(file);
  };
  async function save() {
    setBusy(true); setErr(null);
    try {
      const r = await api.post("/employee-roster", { text });
      if (!r.ok) { setErr(r.message); return; }
      onSaved(); onClose();
    } catch (e) { setErr(e.message || "Could not save the roster"); }
    finally { setBusy(false); }
  }
  return (
    <Modal title="Employee roster" onClose={onClose} width={560}>
      <p style={{ margin: "0 0 10px", fontSize: 13, color: Z.textSecondary, lineHeight: 1.6 }}>
        Paste the email addresses from your HR system, or upload a CSV. The Users tab then shows whether each person is on the roster.
        This replaces the current roster{count ? ` (${count.toLocaleString()} people)` : ""}.
      </p>
      <input type="file" accept=".csv,.txt,text/csv,text/plain" onChange={readFile} style={{ marginBottom: 8, fontSize: 13 }} />
      <textarea value={text} onChange={e => setText(e.target.value)} placeholder="ann@company.com, bob@company.com…" aria-label="Roster emails"
                style={{ width: "100%", boxSizing: "border-box", minHeight: 150, padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, fontFamily: "inherit", marginBottom: 10 }} />
      {err && <Note tone="red">{err}</Note>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onClose} style={dlgBtn(false)}>Cancel</button>
        <button onClick={save} disabled={busy || !text.trim()} style={dlgBtn(true, busy || !text.trim())}>{busy ? "Saving…" : "Replace roster"}</button>
      </div>
    </Modal>
  );
}

export default function AppUsers({ app, refreshKey = 0, onStartWorkflow, onEditThreshold }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [bands, setBands] = useState([]);
  const [filters, setFilters] = useState({});
  const [showChart, setShowChart] = useState(true);
  const [sort, setSort] = useState({ col: "email", dir: "asc" });
  const [cols, setCols] = useState(() => loadCols() || DEFAULT_COLS);
  const [menu, setMenu] = useState(null);
  const [limit, setLimit] = useState(PAGE);
  const [saved, setSaved] = useState([]);
  const [saveName, setSaveName] = useState("");
  const [saveShared, setSaveShared] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [rosterOpen, setRosterOpen] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (reloadTick === 0) { setBands([]); setFilters({}); setSearch(""); setLimit(PAGE); }
    setError(null);
    api.get(`/app-activity/${app.id}`)
      .then(d => { if (!cancelled) setData(d); })
      .catch(e => { if (!cancelled) setError(e.message || "Could not load the users"); });
    return () => { cancelled = true; };
  }, [app.id, refreshKey, reloadTick]);

  const loadSaved = () => api.get(`/app-details/${app.id}/filters`).then(setSaved).catch(() => setSaved([]));
  useEffect(() => { loadSaved(); }, [app.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setLimit(PAGE); }, [search, bands, filters, sort]);

  const users = data ? data.users || [] : [];
  const hasLicense = users.some(u => u.license);
  const applies = c => !c.needs || (c.needs === "license" ? hasLicense : c.needs === "days" ? data && data.has_days : c.needs === "roster" ? data && data.roster_loaded : true);
  const usable = COLUMNS.filter(applies);
  const visibleCols = usable.filter(c => c.locked || cols.includes(c.id));

  const { base, counts, shown, sorted } = useMemo(() => {
    const q = search.trim().toLowerCase();
    const text = u => !q || [u.email, u.first_name, u.last_name, u.title, u.department, u.cost_center, u.division, u.license]
      .some(v => v && String(v).toLowerCase().includes(q));
    const facets = u => FILTERABLE.every(([f]) => !(filters[f] || []).length || filters[f].includes(facetValue(u, f)));
    const base = users.filter(u => text(u) && facets(u));                       // the chart reflects search + filters
    const counts = Object.fromEntries(BAND_ORDER.map(([id]) => [id, 0]));
    base.forEach(u => { counts[bandOf(u.days_since)] += 1; });
    const shown = bands.length ? base.filter(u => bands.includes(bandOf(u.days_since))) : base;
    const col = COLUMNS.find(c => c.id === sort.col) || COLUMNS[0];
    const dir = sort.dir === "asc" ? 1 : -1;
    const sorted = [...shown].sort((a, b) => {
      const x = sortValue(col, a), y = sortValue(col, b);
      if (x === null && y === null) return 0;
      if (x === null) return 1;                                                 // blanks always last
      if (y === null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * dir;
    });
    return { base, counts, shown, sorted };
  }, [users, search, filters, bands, sort]);

  const options = useMemo(() => Object.fromEntries(FILTERABLE.map(([f]) => {
    const m = {};
    users.forEach(u => { const v = facetValue(u, f); m[v] = (m[v] || 0) + 1; });
    return [f, Object.entries(m).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))];
  })), [users]);

  const activeFilterCount = Object.values(filters).reduce((n, v) => n + v.length, 0);
  const toggleBand = id => setBands(b => (b.includes(id) ? b.filter(x => x !== id) : [...b, id]));
  const toggleFilter = (f, v) => setFilters(cur => {
    const list = cur[f] || [];
    return { ...cur, [f]: list.includes(v) ? list.filter(x => x !== v) : [...list, v] };
  });
  const toggleCol = id => setCols(cur => {
    const next = cur.includes(id) ? cur.filter(x => x !== id) : [...cur, id];
    try { window.localStorage.setItem(STORE_KEY, JSON.stringify(next)); } catch (e) { /* ignore */ }
    return next;
  });
  const setSortCol = id => setSort(s => (s.col === id ? { col: id, dir: s.dir === "asc" ? "desc" : "asc" } : { col: id, dir: "asc" }));

  function exportCsv() {
    const cell = (c, u) => (c.kind === "bool" ? (u[c.id] === true ? "Yes" : u[c.id] === false ? "No" : "")
      : c.kind === "date" ? (u[c.id] || "") : u[c.id] === null || u[c.id] === undefined ? "" : String(u[c.id]));
    const q = v => `"${String(v).replace(/"/g, '""')}"`;
    const lines = [visibleCols.map(c => q(c.label)).join(",")].concat(sorted.map(u => visibleCols.map(c => q(cell(c, u))).join(",")));
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url; a.download = `${app.name.replace(/[^a-z0-9]+/gi, "-")}-users.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const anyView = search.trim() || bands.length || activeFilterCount > 0;
  const applySaved = f => {
    const c = f.config || {};
    setSearch(c.search || ""); setBands(c.bands || []); setFilters(c.filters || {});
    if (c.sort) setSort(c.sort);
    setMenu(null);
  };
  async function saveCurrent() {
    setSaveError(null);
    const problem = await send(`/app-details/${app.id}/filters`, { name: saveName, all_apps: saveShared, config: { search, bands, filters, sort } });
    if (problem) { setSaveError(problem); return; }
    setSaveName(""); setSaveShared(false); setMenu(null); loadSaved();
  }
  async function deleteSaved(f, e) {
    e.stopPropagation();
    if (!window.confirm(`Delete the saved filter “${f.name}”?`)) return;
    await send(`/app-details/filters/${f.id}/delete`);
    loadSaved();
  }

  if (error) return <div style={{ padding: "2rem", color: Z.redText, fontSize: 14 }}>{error}</div>;
  if (!data) return <div style={{ textAlign: "center", padding: "3rem", color: Z.textMuted }}>Loading users…</div>;
  if (users.length === 0) {
    return <div style={{ textAlign: "center", padding: "3rem", color: Z.textMuted, fontSize: 13 }}>No users assigned to this app yet. Users are synced from Okta.</div>;
  }

  const renderCell = (c, u) => {
    if (c.id === "days_since") {
      return u.days_since === null || u.days_since === undefined ? <span style={{ color: Z.textMuted }}>—</span> : (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: BAND[bandOf(u.days_since)].dot }} />{u.days_since}
        </span>
      );
    }
    if (c.kind === "bool") {
      const v = u[c.id];
      return v === null || v === undefined ? <span style={{ color: Z.textMuted }}>—</span>
        : <span style={{ fontWeight: 600, color: v ? "#15803D" : Z.textSecondary }}>{v ? "Yes" : "No"}</span>;
    }
    if (c.id === "last_activity" && !u.last_activity) return <span style={{ color: Z.redText }}>No activity</span>;
    const v = u[c.id];
    if (v === null || v === undefined || v === "") return <span style={{ color: Z.textMuted }}>—</span>;
    return c.kind === "date" ? fmtDate(v) : String(v);
  };

  return (
    <div>
      <div style={{ fontSize: 13, color: Z.textSecondary, lineHeight: 1.6, marginBottom: 12 }}>
        <div>Data source: <strong style={{ color: Z.textPrimary }}>{(data.sources || []).join(", ") || "Okta"}</strong></div>
        <div>Last refresh: {data.last_refreshed ? fmtDate(data.last_refreshed) : "—"}</div>
      </div>

      {data.signal === "okta" && (
        <div style={{ background: Z.amberLight, border: "1px solid #FDE68A", color: Z.amberText, borderRadius: 10, padding: "9px 14px", fontSize: 12.5, lineHeight: 1.5, marginBottom: 12 }}>
          <strong>Activity here is the latest Okta sign-in.</strong> Apps that keep people signed in (Slack, Zoom, Google…) show little Okta activity even when
          they're used daily, so treat “No activity” as unconfirmed unless a connector is feeding this app.
        </div>
      )}

      {data.profile_people === 0 && users.length > 0 && (
        <Note tone="amber">
          <strong>Names, department, cost center, division and external status aren't filled in.</strong>{" "}
          {data.profile_diag ? (
            <>
              The last Okta sync ({fmtDate(data.profile_diag.at)}) read {(data.profile_diag.people || 0).toLocaleString()} profiles but none had these fields to save.
              {data.profile_diag.attributes && data.profile_diag.attributes.length > 0 && <> Attributes found in your Okta profiles: {data.profile_diag.attributes.slice(0, 16).map(a => a[0]).join(", ")}. If cost center or division use a different name, tell us which and we'll map it.</>}
            </>
          ) : (
            <>They come from your Okta profiles and none have been saved yet. Run the Okta sync from the Sync page to fill them in.</>
          )}
        </Note>
      )}

      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "10px 12px", border: `1px solid ${Z.border}`, borderRadius: 10, marginBottom: 12, background: Z.cardBg }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…" aria-label="Search users"
               style={{ flex: "0 1 260px", minWidth: 160, padding: "7px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, outline: "none" }} />
        <div style={{ position: "relative" }}>
          <button onClick={() => setMenu(menu === "filters" ? null : "filters")} style={tbBtn(activeFilterCount > 0)}>
            Filters{activeFilterCount > 0 ? ` (${activeFilterCount})` : ""}
          </button>
          {menu === "filters" && (
            <Menu onClose={() => setMenu(null)} width={320}>
              {FILTERABLE.filter(([f]) => f !== "license" || hasLicense).map(([f, label]) => (
                <div key={f} style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
                  <div style={{ maxHeight: 150, overflowY: "auto" }}>
                    {options[f].map(([v, n]) => (
                      <label key={v} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "2px 0", cursor: "pointer" }}>
                        <input type="checkbox" checked={(filters[f] || []).includes(v)} onChange={() => toggleFilter(f, v)} />
                        <span style={{ flex: 1 }}>{v}</span><span style={{ color: Z.textMuted, fontSize: 12 }}>{n}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
              {activeFilterCount > 0 && <button onClick={() => setFilters({})} style={{ ...tbBtn(false), width: "100%", justifyContent: "center" }}>Clear filters</button>}
            </Menu>
          )}
        </div>
        <div style={{ position: "relative" }}>
          <button onClick={() => setMenu(menu === "saved" ? null : "saved")} style={tbBtn(false)}>Saved Filters{saved.length ? ` (${saved.length})` : ""}</button>
          {menu === "saved" && (
            <Menu onClose={() => setMenu(null)} width={320}>
              {saved.length === 0 && <div style={{ fontSize: 13, color: Z.textMuted, padding: "4px 0 10px" }}>No saved filters yet.</div>}
              {saved.map(f => (
                <div key={f.id} onClick={() => applySaved(f)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: 8, cursor: "pointer", fontSize: 13 }}
                     onMouseEnter={e => { e.currentTarget.style.background = Z.accentLight; }} onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}>
                  <span style={{ flex: 1, fontWeight: 600 }}>{f.name}</span>
                  {f.shared && <span style={{ fontSize: 10, color: Z.textMuted, fontWeight: 700 }}>ALL APPS</span>}
                  <button onClick={e => deleteSaved(f, e)} aria-label={`Delete ${f.name}`} style={{ background: "none", border: "none", color: Z.textMuted, cursor: "pointer", fontSize: 16 }}>×</button>
                </div>
              ))}
              <div style={{ borderTop: `1px solid ${Z.border}`, marginTop: 8, paddingTop: 10 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Save the current view</div>
                <input value={saveName} onChange={e => setSaveName(e.target.value)} placeholder="Name this filter" aria-label="Filter name"
                       style={{ width: "100%", boxSizing: "border-box", padding: "7px 10px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, outline: "none", marginBottom: 6 }} />
                <label style={{ display: "flex", gap: 8, fontSize: 12, color: Z.textSecondary, marginBottom: 8 }}><input type="checkbox" checked={saveShared} onChange={e => setSaveShared(e.target.checked)} />Make available on every app</label>
                {saveError && <div style={{ fontSize: 12, color: Z.redText, marginBottom: 6 }}>{saveError}</div>}
                <button onClick={saveCurrent} style={{ ...tbBtn(true), width: "100%", justifyContent: "center" }}>Save filter</button>
              </div>
            </Menu>
          )}
        </div>
        <div style={{ position: "relative" }}>
          <button onClick={() => setMenu(menu === "fields" ? null : "fields")} style={tbBtn(false)}>Fields</button>
          {menu === "fields" && (
            <Menu onClose={() => setMenu(null)} width={240}>
              {usable.map(c => (
                <label key={c.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "3px 0", cursor: c.locked ? "default" : "pointer", opacity: c.locked ? 0.6 : 1 }}>
                  <input type="checkbox" checked={c.locked || cols.includes(c.id)} disabled={c.locked} onChange={() => toggleCol(c.id)} />{c.label}
                </label>
              ))}
              <div style={{ borderTop: `1px solid ${Z.border}`, marginTop: 8, paddingTop: 8, fontSize: 12, color: Z.textSecondary, lineHeight: 1.5 }}>
                {data.roster_loaded ? "" : "“In Employee Roster” needs your HR list. "}
                <button onClick={() => { setMenu(null); setRosterOpen(true); }} style={{ background: "none", border: "none", padding: 0, color: Z.accent, fontWeight: 600, cursor: "pointer", fontSize: 12 }}>
                  {data.roster_loaded ? "Update the employee roster" : "Upload the employee roster"}
                </button>
              </div>
            </Menu>
          )}
        </div>
        <button onClick={() => setShowChart(s => !s)} style={tbBtn(false)}>{showChart ? "Hide Chart" : "Show Chart"}</button>
        <span style={{ marginLeft: "auto", fontSize: 13, fontWeight: 600, color: Z.textPrimary }}>{shown.length.toLocaleString()} Users</span>
        <button onClick={exportCsv} style={tbBtn(false)}>Export CSV</button>
        {onStartWorkflow && <button onClick={onStartWorkflow} style={{ ...tbBtn(false), background: Z.navy, borderColor: Z.navy, color: "#fff" }}>Start Workflow</button>}
      </div>

      {anyView && (
        <div style={{ textAlign: "right", marginBottom: 6 }}>
          <button onClick={() => setMenu("saved")} style={{ background: "none", border: "none", color: Z.accent, fontWeight: 700, fontSize: 12.5, cursor: "pointer" }}>Save As New Filter</button>
        </div>
      )}

      {/* Activity breakdown */}
      {showChart && (
        <div style={{ border: `1px solid ${Z.border}`, borderRadius: 10, padding: "14px 18px 16px", marginBottom: 12, background: Z.cardBg }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", marginBottom: 12 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: Z.textPrimary }}>User Activity - Total {base.length.toLocaleString()} Users</h3>
              <div style={{ fontSize: 12, color: Z.textMuted, marginTop: 2 }}>
                Active = activity within {data.activity_threshold_days} days
                {onEditThreshold && <> · <button onClick={onEditThreshold} style={{ background: "none", border: "none", padding: 0, color: Z.accent, fontWeight: 600, cursor: "pointer", fontSize: 12 }}>change</button></>}
              </div>
            </div>
            <div style={{ marginLeft: "auto", display: "flex", gap: 14, flexWrap: "wrap" }}>
              {BAND_ORDER.map(([id, label]) => (
                <label key={id} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, color: Z.textSecondary, cursor: "pointer" }}>
                  <input type="checkbox" checked={bands.includes(id)} onChange={() => toggleBand(id)} />
                  {label} <span style={{ color: Z.textMuted }}>({counts[id]})</span>
                </label>
              ))}
            </div>
          </div>
          {base.length === 0 ? <div style={{ fontSize: 13, color: Z.textMuted }}>No one matches the current search and filters.</div> : (
            <div style={{ display: "flex", height: 26, borderRadius: 4, overflow: "hidden", background: "#EEF2F7" }}>
              {BAND_ORDER.filter(([id]) => counts[id] > 0).map(([id, label, grad]) => (
                <button key={id} onClick={() => toggleBand(id)} title={`${label}: ${counts[id]} (click to filter)`} aria-label={`${label}: ${counts[id]} users`}
                        style={{ flex: counts[id], minWidth: 4, border: "none", padding: 0, margin: 0, cursor: "pointer", background: grad,
                                 opacity: bands.length && !bands.includes(id) ? 0.3 : 1, transition: "opacity .15s" }} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Table */}
      <div style={{ border: `1px solid ${Z.border}`, borderRadius: 10, overflow: "auto", background: Z.cardBg,
                    maxHeight: showChart ? "calc(100vh - 500px)" : "calc(100vh - 300px)", minHeight: 260 }}>
        <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0, minWidth: 900 }}>
          <thead>
            <tr>
              {visibleCols.map((c, i) => (
                <th key={c.id} onClick={() => setSortCol(c.id)} style={{
                  position: "sticky", top: 0, left: i === 0 ? 0 : undefined, zIndex: i === 0 ? 3 : 2, background: Z.tableHeader,
                  padding: "10px 14px", textAlign: c.align || "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase",
                  letterSpacing: "0.05em", whiteSpace: "nowrap", cursor: "pointer", userSelect: "none", borderBottom: `1px solid ${Z.border}`,
                  borderRight: i === 0 ? `1px solid ${Z.border}` : undefined }}>
                  {c.label}{sort.col === c.id ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, limit).map(u => (
              <tr key={u.email}>
                {visibleCols.map((c, i) => (
                  <td key={c.id} style={{
                    padding: "10px 14px", fontSize: 13, color: Z.textPrimary, textAlign: c.align || "left", whiteSpace: "nowrap",
                    borderBottom: `1px solid ${Z.border}`, position: i === 0 ? "sticky" : undefined, left: i === 0 ? 0 : undefined,
                    background: Z.cardBg, borderRight: i === 0 ? `1px solid ${Z.border}` : undefined }}>
                    {renderCell(c, u)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && <div style={{ padding: "2rem", textAlign: "center", color: Z.textMuted, fontSize: 13 }}>No users match.</div>}
      </div>
      {rosterOpen && <RosterDialog onClose={() => setRosterOpen(false)} onSaved={() => setReloadTick(t => t + 1)} />}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
        <span style={{ fontSize: 12, color: Z.textMuted }}>Showing {Math.min(limit, sorted.length).toLocaleString()} of {sorted.length.toLocaleString()}</span>
        {sorted.length > limit && <button onClick={() => setLimit(l => l + 200)} style={tbBtn(false)}>Show more</button>}
      </div>
    </div>
  );
}
