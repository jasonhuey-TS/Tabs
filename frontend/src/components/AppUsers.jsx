import { useState, useEffect, useMemo } from "react";
import { api } from "../api/client";

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
  { id: "last_activity", label: "Last Activity Date", kind: "date", align: "right" },
  { id: "days_since", label: "Days Since Activity", kind: "number", align: "right" },
  { id: "license", label: "License" },
  { id: "cost_center", label: "Cost Center" },
  { id: "division", label: "Division" },
  { id: "organization", label: "Organization", off: true },
  { id: "assigned_on", label: "Assigned On", kind: "date", align: "right", off: true },
];
const DEFAULT_COLS = COLUMNS.filter(c => !c.off).map(c => c.id);
const FILTERABLE = [["department", "Department"], ["cost_center", "Cost Center"], ["division", "Division"], ["license", "License"]];
const STORE_KEY = "tab.appUsers.columns";
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

export default function AppUsers({ app }) {
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

  useEffect(() => {
    let cancelled = false;
    setData(null); setError(null); setBands([]); setFilters({}); setSearch(""); setLimit(PAGE);
    api.get(`/app-activity/${app.id}`)
      .then(d => { if (!cancelled) setData(d); })
      .catch(e => { if (!cancelled) setError(e.message || "Could not load the users"); });
    return () => { cancelled = true; };
  }, [app.id]);

  useEffect(() => { setLimit(PAGE); }, [search, bands, filters, sort]);

  const users = data ? data.users || [] : [];
  const hasLicense = users.some(u => u.license);
  const visibleCols = COLUMNS.filter(c => (c.locked || cols.includes(c.id)) && (c.id !== "license" || hasLicense));

  const { base, counts, shown, sorted } = useMemo(() => {
    const q = search.trim().toLowerCase();
    const text = u => !q || [u.email, u.first_name, u.last_name, u.title, u.department, u.cost_center, u.division, u.license]
      .some(v => v && String(v).toLowerCase().includes(q));
    const facets = u => FILTERABLE.every(([f]) => !(filters[f] || []).length || filters[f].includes(u[f] || "(blank)"));
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
    users.forEach(u => { const v = u[f] || "(blank)"; m[v] = (m[v] || 0) + 1; });
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
    const cell = (c, u) => (c.kind === "date" ? (u[c.id] || "") : u[c.id] === null || u[c.id] === undefined ? "" : String(u[c.id]));
    const q = v => `"${String(v).replace(/"/g, '""')}"`;
    const lines = [visibleCols.map(c => q(c.label)).join(",")].concat(sorted.map(u => visibleCols.map(c => q(cell(c, u))).join(",")));
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url; a.download = `${app.name.replace(/[^a-z0-9]+/gi, "-")}-users.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
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
          <button onClick={() => setMenu(menu === "fields" ? null : "fields")} style={tbBtn(false)}>Fields</button>
          {menu === "fields" && (
            <Menu onClose={() => setMenu(null)} width={240}>
              {COLUMNS.filter(c => c.id !== "license" || hasLicense).map(c => (
                <label key={c.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "3px 0", cursor: c.locked ? "default" : "pointer", opacity: c.locked ? 0.6 : 1 }}>
                  <input type="checkbox" checked={c.locked || cols.includes(c.id)} disabled={c.locked} onChange={() => toggleCol(c.id)} />{c.label}
                </label>
              ))}
            </Menu>
          )}
        </div>
        <button onClick={() => setShowChart(s => !s)} style={tbBtn(false)}>{showChart ? "Hide Chart" : "Show Chart"}</button>
        <span style={{ marginLeft: "auto", fontSize: 13, fontWeight: 600, color: Z.textPrimary }}>{shown.length.toLocaleString()} Users</span>
        <button onClick={exportCsv} style={tbBtn(false)}>Export CSV</button>
      </div>

      {/* Activity breakdown */}
      {showChart && (
        <div style={{ border: `1px solid ${Z.border}`, borderRadius: 10, padding: "14px 18px 16px", marginBottom: 12, background: Z.cardBg }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", marginBottom: 12 }}>
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: Z.textPrimary }}>User Activity - Total {base.length.toLocaleString()} Users</h3>
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
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
        <span style={{ fontSize: 12, color: Z.textMuted }}>Showing {Math.min(limit, sorted.length).toLocaleString()} of {sorted.length.toLocaleString()}</span>
        {sorted.length > limit && <button onClick={() => setLimit(l => l + 200)} style={tbBtn(false)}>Show more</button>}
      </div>
    </div>
  );
}
