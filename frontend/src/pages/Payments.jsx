import { Fragment, useState, useEffect, useCallback, useMemo } from "react";
import { api } from "../api/client";
import AppIcon from "../components/AppIcon";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", navy: "#1B2A4A", green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C", amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF", pageBg: "#F4F6FA", tableHeader: "#F8FAFC",
  ap: "#5BA8F5", expense: "#7ACB5A",
};
const API_BASE = import.meta.env?.VITE_API_BASE_URL || "";
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const PAGE_SIZE = 5;

const money = c => (c === null || c === undefined ? "—" : (c < 0 ? "-$" : "$") + Math.abs(Math.round(c / 100)).toLocaleString("en-US"));
const compact = c => {
  const d = Math.abs(c) / 100, sign = c < 0 ? "-" : "";
  if (d >= 1e6) return `${sign}$${(d / 1e6).toFixed(d >= 1e7 ? 1 : 2).replace(/\.?0+$/, "")}M`;
  if (d >= 1e3) return `${sign}$${(d / 1e3).toFixed(d >= 1e4 ? 0 : 1).replace(/\.0$/, "")}K`;
  return `${sign}$${Math.round(d)}`;
};
const fmtDate = iso => {
  if (!iso) return "—";
  const d = new Date(String(iso).length === 10 ? `${iso}T12:00:00` : iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};
const qs = o => Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
const niceCeil = v => { const p = Math.pow(10, Math.floor(Math.log10(Math.max(v, 1)))); const f = v / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; };

const card = { background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" };
const th = { padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap", background: Z.tableHeader, borderBottom: `1px solid ${Z.border}`, cursor: "pointer", userSelect: "none" };
const td = { padding: "10px 14px", fontSize: 13, color: Z.textPrimary, borderBottom: `1px solid ${Z.border}`, whiteSpace: "nowrap" };
const input = { width: "100%", boxSizing: "border-box", padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, outline: "none", fontFamily: "inherit" };
const btn = (primary, disabled, danger) => ({
  display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1,
  border: primary ? "none" : `1px solid ${danger ? "#FECACA" : Z.border}`, background: primary ? Z.accent : Z.cardBg, color: primary ? "#fff" : danger ? Z.red : Z.textPrimary,
});

function Note({ tone = "amber", children }) {
  const t = { amber: [Z.amberLight, "#FDE68A", Z.amberText], red: [Z.redLight, "#FECACA", Z.redText], green: [Z.greenLight, "#BBF7D0", Z.greenText], blue: [Z.accentLight, "#C7D2FE", "#3730A3"] }[tone];
  return <div style={{ background: t[0], border: `1px solid ${t[1]}`, color: t[2], borderRadius: 10, padding: "9px 14px", fontSize: 13, lineHeight: 1.5, marginBottom: 14 }}>{children}</div>;
}

function Menu({ onClose, children, width = 320, right }) {
  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
      <div style={{ position: "absolute", top: "calc(100% + 6px)", [right ? "right" : "left"]: 0, width, maxHeight: 460, overflowY: "auto", zIndex: 41, background: Z.cardBg,
                    border: `1px solid ${Z.border}`, borderRadius: 10, boxShadow: "0 10px 30px rgba(0,0,0,0.16)", padding: "12px 14px" }}>{children}</div>
    </>
  );
}

function Modal({ title, onClose, children, width = 480 }) {
  useEffect(() => {
    const onKey = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(17,24,39,0.45)", zIndex: 200, display: "flex", justifyContent: "center", alignItems: "flex-start", overflowY: "auto", padding: "8vh 1rem" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: Z.cardBg, borderRadius: 14, width: "100%", maxWidth: width, boxShadow: "0 20px 50px rgba(0,0,0,0.25)" }}>
        <div style={{ display: "flex", alignItems: "center", padding: "1rem 1.4rem", borderBottom: `1px solid ${Z.border}` }}>
          <h2 style={{ margin: 0, flex: 1, fontSize: 16, fontWeight: 700 }}>{title}</h2>
          <button onClick={onClose} aria-label="Close" style={{ background: "none", border: "none", fontSize: 24, lineHeight: 1, color: Z.textMuted, cursor: "pointer" }}>×</button>
        </div>
        <div style={{ padding: "1.1rem 1.4rem 1.3rem" }}>{children}</div>
      </div>
    </div>
  );
}

function Labeled({ label, children }) {
  return <label style={{ display: "block", marginBottom: 12 }}><span style={{ display: "block", fontSize: 12, fontWeight: 600, color: Z.textSecondary, marginBottom: 4 }}>{label}</span>{children}</label>;
}

// Find an app by typing (same idea as the workflow form).
function AppPicker({ value, onChange }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    const t = setTimeout(async () => {
      try { const d = await api.get(`/apps?limit=8${q ? `&search=${encodeURIComponent(q)}` : ""}`); if (!cancelled) setItems(Array.isArray(d) ? d : []); }
      catch (e) { if (!cancelled) setItems([]); }
    }, q ? 250 : 0);
    return () => { cancelled = true; clearTimeout(t); };
  }, [open, q]);
  return (
    <div>
      <button type="button" onClick={() => setOpen(o => !o)} aria-label={value ? `Application: ${value.name}` : "Choose an application"} style={{ ...input, textAlign: "left", cursor: "pointer", background: "#F9FAFB", color: value ? Z.textPrimary : Z.textMuted }}>{value ? value.name : "Choose an application…"}</button>
      {open && (
        <div style={{ marginTop: 6, border: `1px solid ${Z.border}`, borderRadius: 8, overflow: "hidden" }}>
          <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Search your applications…" aria-label="Search applications" style={{ ...input, border: "none", borderBottom: `1px solid ${Z.border}`, borderRadius: 0 }} />
          <div style={{ maxHeight: 170, overflowY: "auto" }}>
            {items === null && <div style={{ padding: 10, fontSize: 12, color: Z.textMuted }}>Loading…</div>}
            {(items || []).map(a => <button key={a.id} type="button" onClick={() => { onChange({ id: a.id, name: a.name }); setOpen(false); setQ(""); }} style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 12px", background: Z.cardBg, border: "none", borderBottom: `1px solid ${Z.border}`, fontSize: 13, cursor: "pointer" }}><AppIcon app={a} size={22} />{a.name}</button>)}
          </div>
        </div>
      )}
    </div>
  );
}

function AddPaymentModal({ onClose, onSaved }) {
  const [app, setApp] = useState(null);
  const [form, setForm] = useState({ paid_on: new Date().toISOString().slice(0, 10), amount_usd: "", currency: "USD", payment_type: "ap", reference: "" });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));
  async function save() {
    if (!app) { setErr("Choose an application."); return; }
    setBusy(true); setErr(null);
    try {
      const r = await api.post("/payments/add", { ...form, app_id: app.id });
      if (!r.ok) { setErr(r.message); return; }
      onSaved();
    } catch (e) { setErr(e.message || "Could not save"); } finally { setBusy(false); }
  }
  return (
    <Modal title="Add a payment" onClose={onClose}>
      <Labeled label="Application"><AppPicker value={app} onChange={setApp} /></Labeled>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <Labeled label="Date"><input style={input} type="date" value={form.paid_on} onChange={set("paid_on")} /></Labeled>
        <Labeled label="Amount"><input style={input} type="number" min="0" step="0.01" value={form.amount_usd} onChange={set("amount_usd")} placeholder="0.00" /></Labeled>
        <Labeled label="Type"><select style={input} value={form.payment_type} onChange={set("payment_type")}><option value="ap">AP payment</option><option value="expense">Expense payment</option></select></Labeled>
        <Labeled label="Currency"><input style={input} value={form.currency} onChange={set("currency")} maxLength={3} /></Labeled>
      </div>
      <Labeled label="Reference (optional)"><input style={input} value={form.reference} onChange={set("reference")} placeholder="Invoice number" /></Labeled>
      {err && <Note tone="red">{err}</Note>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onClose} style={btn(false)}>Cancel</button><button onClick={save} disabled={busy} style={btn(true, busy)}>{busy ? "Saving…" : "Add payment"}</button>
      </div>
    </Modal>
  );
}

const SORTS = [["total", "Total Payments"], ["ap", "AP Payments"], ["expense", "Expense Payments"], ["name", "Application"]];
const sortValue = (a, key) => (key === "ap" ? a.ap_cents : key === "expense" ? a.expense_cents : key === "name" ? a.name.toLowerCase() : a.total_cents);

// ───────────────────────────────────────────────────────────── the Payments tab
function PaymentsTab({ onGoUpload }) {
  const [filters, setFilters] = useState({ q: "", type: "", date_from: "", date_to: "", source: "" });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [showChart, setShowChart] = useState(true);
  const [sortKey, setSortKey] = useState("total");
  const [page, setPage] = useState(0);
  const [tableSort, setTableSort] = useState({ col: "total_cents", dir: "desc" });
  const [menu, setMenu] = useState(null);
  const [saved, setSaved] = useState([]);
  const [saveName, setSaveName] = useState("");
  const [saveErr, setSaveErr] = useState(null);
  const [open, setOpen] = useState(null);          // app id whose payments are shown
  const [detail, setDetail] = useState({});
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try { setData(await api.get(`/payments/summary?${qs(filters)}`)); }
    catch (e) { setError(e.message || "Could not load payments"); }
  }, [filters]);
  useEffect(() => { const t = setTimeout(load, filters.q ? 300 : 0); return () => clearTimeout(t); }, [load, filters.q]);
  useEffect(() => { setPage(0); setOpen(null); setDetail({}); }, [filters, sortKey]);
  const loadSaved = () => api.get("/payments/filters").then(setSaved).catch(() => setSaved([]));
  useEffect(() => { loadSaved(); }, []);

  const set = k => v => setFilters(f => ({ ...f, [k]: v }));
  const active = Boolean(filters.q || filters.type || filters.date_from || filters.date_to || filters.source);
  const apps = data ? data.apps : [];
  const chartApps = useMemo(() => [...apps].sort((a, b) => {
    const x = sortValue(a, sortKey), y = sortValue(b, sortKey);
    return sortKey === "name" ? (x < y ? -1 : 1) : y - x;
  }), [apps, sortKey]);
  const pages = Math.max(1, Math.ceil(chartApps.length / PAGE_SIZE));
  const pageApps = chartApps.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
  const axisMax = niceCeil(Math.max(1, ...apps.map(a => Math.max(a.total_cents, 0)))) ;
  const tableRows = useMemo(() => [...apps].sort((a, b) => {
    const x = tableSort.col === "name" ? a.name.toLowerCase() : tableSort.col === "last_paid" ? a.last_paid || "" : a[tableSort.col];
    const y = tableSort.col === "name" ? b.name.toLowerCase() : tableSort.col === "last_paid" ? b.last_paid || "" : b[tableSort.col];
    return (x < y ? -1 : x > y ? 1 : 0) * (tableSort.dir === "asc" ? 1 : -1);
  }), [apps, tableSort]);

  async function toggle(app) {
    if (open === app.app_id) { setOpen(null); return; }
    setOpen(app.app_id);
    if (!detail[app.app_id]) {
      try { const rows = await api.get(`/payments/app/${app.app_id}?${qs(filters)}`); setDetail(d => ({ ...d, [app.app_id]: rows })); }
      catch (e) { setDetail(d => ({ ...d, [app.app_id]: [] })); }
    }
  }
  async function removePayment(p, app) {
    if (!window.confirm("Remove this payment?")) return;
    try { await api.post(`/payments/${p.id}/delete`); } catch (e) { setError(e.message); return; }
    setDetail(d => ({ ...d, [app.app_id]: (d[app.app_id] || []).filter(x => x.id !== p.id) }));
    load();
  }
  async function saveFilter() {
    setSaveErr(null);
    try {
      const r = await api.post("/payments/filters", { name: saveName, config: filters });
      if (!r.ok) { setSaveErr(r.message); return; }
      setSaveName(""); setMenu(null); loadSaved();
    } catch (e) { setSaveErr(e.message || "Could not save"); }
  }
  async function deleteSaved(f, e) {
    e.stopPropagation();
    if (!window.confirm(`Delete the saved filter “${f.name}”?`)) return;
    await api.post(`/payments/filters/${f.id}/delete`); loadSaved();
  }
  async function changeFiscal(month) {
    try { await api.post("/payments/settings", { fiscal_year_start_month: Number(month) }); load(); } catch (e) { setError(e.message); }
  }
  function exportApps() {
    const q = v => `"${String(v).replace(/"/g, '""')}"`;
    const rows = [["Application", "Total", "AP", "Expense", "YTD", "Fiscal YTD", "Payments", "Last payment"], ...chartApps.map(a => [a.name, a.total_cents / 100, a.ap_cents / 100, a.expense_cents / 100, a.ytd_cents / 100, a.fiscal_ytd_cents / 100, a.count, a.last_paid || ""])];
    const url = URL.createObjectURL(new Blob([rows.map(r => r.map(q).join(",")).join("\n")], { type: "text/csv" }));
    const a = document.createElement("a"); a.href = url; a.download = "payments-by-application.csv"; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  if (error && !data) return <Note tone="red">{error}</Note>;
  if (!data) return <p style={{ color: Z.textMuted }}>Loading…</p>;
  const k = data.kpis;
  const kpis = [["Total Payments", money(k.total_cents), "Everything recorded, in USD, for the filters above."], ["Total AP Payments", money(k.ap_cents), "Paid through accounts payable."],
                ["Total Expense Payments", money(k.expense_cents), "Paid on cards or through expense reports."], ["YTD Payments", money(k.ytd_cents), "Since January 1."],
                ["Fiscal YTD Payments", money(k.fiscal_ytd_cents), `Since the fiscal year began on ${fmtDate(data.fiscal_year_start)}.`], ["Total Applications", k.applications.toLocaleString(), "Applications with at least one payment."]];

  return (
    <div>
      {data.payments_in_system === 0 && (
        <div style={{ ...card, padding: "2rem", textAlign: "center", marginBottom: 16 }}>
          <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 6 }}>No payments yet</div>
          <p style={{ margin: "0 auto 14px", maxWidth: 560, fontSize: 14, color: Z.textSecondary, lineHeight: 1.6 }}>Upload a payments file (a Zylo export or Spendflo transactions), or add payments one at a time.</p>
          <button onClick={onGoUpload} style={btn(true)}>Upload payments</button>{" "}<button onClick={() => setAdding(true)} style={btn(false)}>Add a payment</button>
        </div>
      )}

      <div style={{ ...card, padding: "12px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
        <input value={filters.q} onChange={e => set("q")(e.target.value)} placeholder="Search applications or references…" aria-label="Search payments" style={{ ...input, width: 300 }} />
        <div style={{ position: "relative" }}>
          <button onClick={() => setMenu(menu === "filters" ? null : "filters")} style={btn(false)}>Filters{active ? " •" : ""}</button>
          {menu === "filters" && (
            <Menu onClose={() => setMenu(null)}>
              <Labeled label="Payment type"><select style={input} value={filters.type} onChange={e => set("type")(e.target.value)}><option value="">All</option><option value="ap">AP payments</option><option value="expense">Expense payments</option></select></Labeled>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <Labeled label="From"><input style={input} type="date" value={filters.date_from} onChange={e => set("date_from")(e.target.value)} aria-label="From date" /></Labeled>
                <Labeled label="To"><input style={input} type="date" value={filters.date_to} onChange={e => set("date_to")(e.target.value)} aria-label="To date" /></Labeled>
              </div>
              <Labeled label="Source"><select style={input} value={filters.source} onChange={e => set("source")(e.target.value)}><option value="">All</option><option value="manual">Added by hand</option><option value="csv">Uploaded</option></select></Labeled>
              {active && <button onClick={() => setFilters({ q: "", type: "", date_from: "", date_to: "", source: "" })} style={{ ...btn(false), width: "100%", justifyContent: "center" }}>Clear filters</button>}
            </Menu>
          )}
        </div>
        <div style={{ position: "relative" }}>
          <button onClick={() => setMenu(menu === "saved" ? null : "saved")} style={btn(false)}>Saved Filters{saved.length ? ` (${saved.length})` : ""}</button>
          {menu === "saved" && (
            <Menu onClose={() => setMenu(null)}>
              {saved.length === 0 && <div style={{ fontSize: 13, color: Z.textMuted, paddingBottom: 8 }}>No saved filters yet.</div>}
              {saved.map(f => (
                <div key={f.id} onClick={() => { setFilters({ q: "", type: "", date_from: "", date_to: "", source: "", ...f.config }); setMenu(null); }} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: 8, cursor: "pointer", fontSize: 13 }}>
                  <span style={{ flex: 1, fontWeight: 600 }}>{f.name}</span>
                  <button onClick={e => deleteSaved(f, e)} aria-label={`Delete ${f.name}`} style={{ background: "none", border: "none", color: Z.textMuted, cursor: "pointer", fontSize: 16 }}>×</button>
                </div>
              ))}
              <div style={{ borderTop: `1px solid ${Z.border}`, marginTop: 8, paddingTop: 10 }}>
                <input value={saveName} onChange={e => setSaveName(e.target.value)} placeholder="Name this filter" aria-label="Filter name" style={{ ...input, marginBottom: 8 }} />
                {saveErr && <div style={{ fontSize: 12, color: Z.redText, marginBottom: 6 }}>{saveErr}</div>}
                <button onClick={saveFilter} style={{ ...btn(true), width: "100%", justifyContent: "center" }}>Save current filters</button>
              </div>
            </Menu>
          )}
        </div>
        <button onClick={() => setShowChart(s => !s)} style={btn(false)}>{showChart ? "Hide Chart" : "Show Chart"}</button>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: Z.textSecondary }}>
          Fiscal year starts
          <select aria-label="Fiscal year starts" value={data.fiscal_year_start_month} onChange={e => changeFiscal(e.target.value)} style={{ ...input, width: 130 }}>{MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select>
        </div>
      </div>
      {active && <div style={{ textAlign: "right", marginBottom: 8 }}><button onClick={() => setMenu("saved")} style={{ background: "none", border: "none", color: Z.accent, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>Save As New Filter</button></div>}
      {error && <Note tone="red">{error}</Note>}
      {data.non_usd_excluded > 0 && <Note tone="amber">{data.non_usd_excluded.toLocaleString()} payment{data.non_usd_excluded === 1 ? " isn't" : "s aren't"} in US dollars and {data.non_usd_excluded === 1 ? "is" : "are"} left out of these totals (no currency conversion).</Note>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 14, margin: "10px 0 16px" }}>
        {kpis.map(([label, value, tip]) => (
          <div key={label} style={{ ...card, padding: "16px 18px" }} data-kpi={label}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: Z.textSecondary }}><span>{label}</span><span title={tip} style={{ cursor: "help", color: Z.textMuted }}>ⓘ</span></div>
            <div style={{ fontSize: 28, fontWeight: 600, marginTop: 8 }}>{value}</div>
          </div>
        ))}
      </div>

      {showChart && (
        <div style={{ ...card, marginBottom: 16, overflow: "hidden" }} data-chart="payments">
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 20px", borderBottom: `1px solid ${Z.border}` }}>
            <div style={{ flex: 1, fontSize: 15, fontWeight: 600 }}>Payments by application</div>
            <span style={{ fontSize: 13, color: Z.textSecondary }}>Sort By:</span>
            <select value={sortKey} onChange={e => setSortKey(e.target.value)} aria-label="Sort chart by" style={{ ...input, width: 170 }}>{SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <button onClick={exportApps} aria-label="Export payments by application" title="Export CSV" style={{ border: "none", background: "none", cursor: "pointer", color: Z.textSecondary, fontSize: 16 }}>⤓</button>
          </div>
          {chartApps.length === 0 ? <div style={{ padding: "2.5rem", textAlign: "center", color: Z.textMuted, fontSize: 13 }}>No payments match.</div> : (
            <div style={{ padding: "14px 20px 8px" }}>
              {pageApps.map((a, i) => {
                const ap = Math.max(a.ap_cents, 0), ex = Math.max(a.expense_cents, 0);
                return (
                  <div key={a.app_id} data-bar={a.name} onClick={() => toggle(a)} style={{ display: "flex", alignItems: "center", height: 46, cursor: "pointer" }}>
                    <div style={{ width: 260, fontSize: 14, color: Z.textPrimary, paddingRight: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}><AppIcon app={{ id: a.app_id, name: a.name }} size={26} />{page * PAGE_SIZE + i + 1}. {a.name}</div>
                    <div style={{ flex: 1, display: "flex", alignItems: "center" }}>
                      <div style={{ display: "flex", width: `${(100 * (ap + ex)) / axisMax}%`, minWidth: ap + ex > 0 ? 3 : 0, height: 22, borderRadius: 3, overflow: "hidden" }}>
                        <div title={`AP ${money(a.ap_cents)}`} style={{ flex: ap, background: `linear-gradient(90deg, ${Z.ap}, #A9D3FA)` }} />
                        <div title={`Expense ${money(a.expense_cents)}`} style={{ flex: ex, background: Z.expense }} />
                      </div>
                      <span style={{ marginLeft: 10, fontSize: 14, color: Z.textPrimary }}>{compact(a.total_cents)}</span>
                    </div>
                  </div>
                );
              })}
              <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 8, paddingBottom: 12 }}>
                <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} aria-label="Previous page" style={{ ...btn(false, page === 0), padding: "5px 12px" }}>‹</button>
                <button onClick={() => setPage(p => Math.min(pages - 1, p + 1))} disabled={page >= pages - 1} aria-label="Next page" style={{ ...btn(false, page >= pages - 1), padding: "5px 12px" }}>›</button>
                <span style={{ fontSize: 14, color: Z.textSecondary }}>{page + 1} of {pages}</span>
                <span style={{ marginLeft: "auto", marginRight: "auto", display: "flex", gap: 22, fontSize: 14 }}>
                  <span><span style={{ display: "inline-block", width: 11, height: 11, borderRadius: "50%", background: Z.ap, marginRight: 8 }} />AP Payments</span>
                  <span><span style={{ display: "inline-block", width: 11, height: 11, borderRadius: "50%", background: Z.expense, marginRight: 8 }} />Expense Payments</span>
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      <div style={{ ...card, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderBottom: `1px solid ${Z.border}` }}>
          <div style={{ flex: 1, fontSize: 15, fontWeight: 600 }}>Applications</div>
          <button onClick={() => setAdding(true)} style={btn(true)}>Add payment</button>
          <a href={`${API_BASE}/api/v1/payments/export.csv?${qs(filters)}`} style={{ ...btn(false), textDecoration: "none" }}>Export all payments (CSV)</a>
        </div>
        <div style={{ overflow: "auto", maxHeight: 560 }}>
          <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0, minWidth: 900 }}>
            <thead><tr>
              {[["name", "Application"], ["total_cents", "Total"], ["ap_cents", "AP"], ["expense_cents", "Expense"], ["ytd_cents", "YTD"], ["fiscal_ytd_cents", "Fiscal YTD"], ["count", "Payments"], ["last_paid", "Last payment"]].map(([col, label]) => (
                <th key={col} onClick={() => setTableSort(s => (s.col === col ? { col, dir: s.dir === "asc" ? "desc" : "asc" } : { col, dir: col === "name" ? "asc" : "desc" }))} style={{ ...th, position: "sticky", top: 0, zIndex: 2, textAlign: col === "name" || col === "last_paid" ? "left" : "right" }}>
                  {label}{tableSort.col === col ? (tableSort.dir === "asc" ? " ↑" : " ↓") : ""}
                </th>
              ))}
            </tr></thead>
            <tbody>
              {tableRows.map(a => (
                <Fragment key={a.app_id}>
                  <tr onClick={() => toggle(a)} style={{ cursor: "pointer", background: open === a.app_id ? "#F5F7FF" : "transparent" }} data-row={a.name}>
                    <td style={{ ...td, fontWeight: 600 }}><AppIcon app={{ id: a.app_id, name: a.name }} size={24} />{a.name}</td>
                    {[a.total_cents, a.ap_cents, a.expense_cents, a.ytd_cents, a.fiscal_ytd_cents].map((v, i) => <td key={i} style={{ ...td, textAlign: "right" }}>{money(v)}</td>)}
                    <td style={{ ...td, textAlign: "right" }}>{a.count.toLocaleString()}</td>
                    <td style={td}>{fmtDate(a.last_paid)}</td>
                  </tr>
                  {open === a.app_id && (
                    <tr><td colSpan={8} style={{ padding: 0, background: "#FAFBFF", borderBottom: `1px solid ${Z.border}` }}>
                      <div style={{ padding: "8px 16px 14px" }}>
                        {!detail[a.app_id] ? <div style={{ fontSize: 13, color: Z.textMuted }}>Loading…</div> : (
                          <table style={{ width: "100%", borderCollapse: "collapse" }}>
                            <thead><tr>{["Date", "Amount", "Type", "Reference", "Source", ""].map(h => <th key={h} style={{ ...th, cursor: "default", background: "transparent" }}>{h}</th>)}</tr></thead>
                            <tbody>{detail[a.app_id].map(p => (
                              <tr key={p.id}><td style={td}>{fmtDate(p.paid_on)}</td><td style={td}>{money(p.amount_cents)} {p.currency !== "USD" ? p.currency : ""}</td>
                                <td style={td}>{p.payment_type === "expense" ? "Expense" : "AP"}</td><td style={td}>{p.reference || "—"}</td><td style={td}>{p.source === "csv" ? "Uploaded" : "Added by hand"}</td>
                                <td style={{ ...td, textAlign: "right" }}><button onClick={e => { e.stopPropagation(); removePayment(p, a); }} style={btn(false, false, true)}>Remove</button></td></tr>
                            ))}</tbody>
                          </table>
                        )}
                        {detail[a.app_id] && detail[a.app_id].length >= 1000 && <div style={{ fontSize: 12, color: Z.textMuted, marginTop: 6 }}>Showing the 1,000 most recent payments.</div>}
                      </div>
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {tableRows.length === 0 && <div style={{ padding: "2rem", textAlign: "center", color: Z.textMuted, fontSize: 13 }}>No applications match.</div>}
        </div>
      </div>
      {adding && <AddPaymentModal onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setDetail({}); setOpen(null); load(); }} />}
    </div>
  );
}

// ───────────────────────────────────────────────────────────── the Uploads tab
const FIELD_LABELS = [["vendor", "Application / vendor", true], ["date", "Payment date", true], ["amount", "Amount", true], ["type", "Payment type"], ["reference", "Reference"], ["currency", "Currency"], ["external_id", "Transaction ID"]];

function UploadsTab({ onDone }) {
  const [file, setFile] = useState(null);                 // {name, text}
  const [mapping, setMapping] = useState(null);           // null = let the server guess
  const [defaultType, setDefaultType] = useState("ap");
  const [decisions, setDecisions] = useState({});
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [apps, setApps] = useState([]);
  const [showInvalid, setShowInvalid] = useState(false);

  useEffect(() => { api.get("/apps?limit=1000").then(d => setApps(Array.isArray(d) ? d : [])).catch(() => setApps([])); }, []);

  useEffect(() => {
    if (!file) return undefined;
    let cancelled = false;
    setBusy(true); setError(null);
    api.post("/payments/import/preview", { text: file.text, mapping, default_type: defaultType, decisions })
      .then(p => { if (cancelled) return; if (p.error && !p.headers) { setError(p.error); setPreview(null); } else { setPreview(p); if (!mapping) setMapping(p.mapping); } })
      .catch(e => { if (!cancelled) setError(e.message || "Could not read that file"); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [file, mapping, defaultType, decisions]);

  function pick(e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    if (f.size > 15 * 1024 * 1024) { setError("That file is larger than 15 MB."); return; }
    const reader = new FileReader();
    reader.onload = () => { setResult(null); setPreview(null); setMapping(null); setDecisions({}); setFile({ name: f.name, text: String(reader.result || "") }); };
    reader.readAsText(f);
  }
  async function commit() {
    setBusy(true); setError(null);
    try {
      const r = await api.post("/payments/import/commit", { text: file.text, mapping, default_type: defaultType, decisions, file_name: file.name });
      if (!r.ok) { setError(r.error || "The import didn't run."); return; }
      setResult(r); setFile(null); setPreview(null);
    } catch (e) { setError(e.message || "The import failed"); } finally { setBusy(false); }
  }
  const decide = (vendor, value) => setDecisions(d => { const n = { ...d }; if (value) n[vendor] = value; else delete n[vendor]; return n; });

  return (
    <div>
      <Note tone="blue">Upload a payments file from Zylo (the download icon on its Payments page), Spendflo transactions, or any CSV with an application, a date and an amount. You'll see exactly what will happen before anything is saved, and uploading the same file twice never creates duplicates.</Note>
      {result && (
        <div style={{ ...card, padding: "18px 22px", marginBottom: 16, borderColor: "#BBF7D0", background: Z.greenLight }} data-result="import">
          <div style={{ fontSize: 16, fontWeight: 700, color: Z.greenText }}>Imported {result.imported.toLocaleString()} payment{result.imported === 1 ? "" : "s"} ({money(result.imported_cents)}) across {result.apps.toLocaleString()} application{result.apps === 1 ? "" : "s"}</div>
          <div style={{ fontSize: 13, color: Z.greenText, marginTop: 6, lineHeight: 1.7 }}>
            {result.already_imported > 0 && <div>{result.already_imported.toLocaleString()} were already imported earlier and were left alone.</div>}
            {result.skipped > 0 && <div>{result.skipped.toLocaleString()} rows were skipped as you chose.</div>}
            {result.unmatched_rows > 0 && <div>{result.unmatched_rows.toLocaleString()} rows weren't imported because their application wasn't matched.</div>}
            {result.invalid > 0 && <div>{result.invalid.toLocaleString()} rows couldn't be read.</div>}
          </div>
          <button onClick={onDone} style={{ ...btn(true), marginTop: 12 }}>View payments</button>
        </div>
      )}

      <div style={{ ...card, padding: "18px 22px", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <input type="file" accept=".csv,.txt,text/csv,text/plain" onChange={pick} aria-label="Choose a payments file" />
          {file && <span style={{ fontSize: 13, color: Z.textSecondary }}>{file.name}</span>}
          <span style={{ marginLeft: "auto", fontSize: 13, color: Z.textSecondary }}>Rows with no type are
            <select aria-label="Default payment type" value={defaultType} onChange={e => setDefaultType(e.target.value)} style={{ ...input, width: 150, marginLeft: 8 }}><option value="ap">AP payments</option><option value="expense">Expense payments</option></select>
          </span>
        </div>
      </div>

      {error && <Note tone="red">{error}</Note>}
      {preview && (
        <>
          <div style={{ ...card, padding: "18px 22px", marginBottom: 16 }} data-step="mapping">
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>1. Check the columns</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
              {FIELD_LABELS.map(([field, label, required]) => (
                <Labeled key={field} label={`${label}${required ? " *" : ""}`}>
                  <select aria-label={label} style={input} value={(mapping || {})[field] || ""} onChange={e => setMapping(m => { const n = { ...(m || preview.mapping) }; if (e.target.value) n[field] = e.target.value; else delete n[field]; return n; })}>
                    <option value="">{required ? "Choose a column…" : "— none —"}</option>
                    {preview.headers.map(h => <option key={h} value={h}>{h}</option>)}
                  </select>
                </Labeled>
              ))}
            </div>
            {preview.error && <Note tone="red">{preview.error}</Note>}
          </div>

          {!preview.error && (
            <div style={{ ...card, padding: "18px 22px", marginBottom: 16 }} data-step="summary">
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>2. What will be imported</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
                {[["Ready to import", `${preview.ready.toLocaleString()} payments`, `${money(preview.ready_total_cents)} across ${preview.apps} apps`],
                  ["Already imported", preview.already_imported.toLocaleString(), "left alone"],
                  ["Need an application", preview.unmatched_rows.toLocaleString(), `${preview.unmatched.length} vendors`],
                  ["Can't be read", preview.invalid.count.toLocaleString(), "rows with a bad date or amount"]].map(([l, v, s]) => (
                  <div key={l} style={{ border: `1px solid ${Z.border}`, borderRadius: 10, padding: "12px 14px" }}>
                    <div style={{ fontSize: 12, color: Z.textSecondary }}>{l}</div><div style={{ fontSize: 20, fontWeight: 600, margin: "2px 0" }}>{v}</div><div style={{ fontSize: 12, color: Z.textMuted }}>{s}</div>
                  </div>
                ))}
              </div>
              {preview.invalid.count > 0 && (
                <div style={{ marginTop: 10 }}>
                  <button onClick={() => setShowInvalid(s => !s)} style={{ background: "none", border: "none", color: Z.accent, fontWeight: 600, fontSize: 13, cursor: "pointer", padding: 0 }}>{showInvalid ? "Hide" : "Show"} rows that can't be read</button>
                  {showInvalid && <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13, color: Z.textSecondary }}>{preview.invalid.sample.map(i => <li key={i.row}>Row {i.row}: {i.reason}</li>)}{preview.invalid.count > preview.invalid.sample.length && <li>…and {preview.invalid.count - preview.invalid.sample.length} more</li>}</ul>}
                </div>
              )}
            </div>
          )}

          {!preview.error && preview.unmatched.length > 0 && (
            <div style={{ ...card, overflow: "hidden", marginBottom: 16 }} data-step="unmatched">
              <div style={{ padding: "14px 22px", borderBottom: `1px solid ${Z.border}` }}>
                <div style={{ fontSize: 15, fontWeight: 600 }}>3. Match these vendors to applications</div>
                <div style={{ fontSize: 13, color: Z.textSecondary, marginTop: 2 }}>Your choices are remembered, so the next file matches automatically. Anything you leave unmatched is not imported.</div>
              </div>
              <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
                <thead><tr>{["Vendor in the file", "Rows", "Total", "Application"].map(h => <th key={h} style={{ ...th, cursor: "default" }}>{h}</th>)}</tr></thead>
                <tbody>{preview.unmatched.map(u => (
                  <tr key={u.vendor}>
                    <td style={{ ...td, fontWeight: 600 }}>{u.vendor}</td><td style={td}>{u.rows.toLocaleString()}</td><td style={td}>{money(u.total_cents)}</td>
                    <td style={{ ...td, whiteSpace: "normal" }}>
                      {u.suggestions.length > 0 && <div style={{ marginBottom: 6, fontSize: 12, color: Z.textSecondary }}>Did you mean {u.suggestions.map(s => <button key={s.app_id} onClick={() => decide(u.vendor, s.app_id)} style={{ ...btn(false), padding: "2px 10px", marginLeft: 6 }}>{s.name}</button>)}</div>}
                      <select aria-label={`Application for ${u.vendor}`} style={{ ...input, maxWidth: 280 }} value="" onChange={e => decide(u.vendor, e.target.value)}>
                        <option value="">Choose an application…</option><option value="skip">Skip these rows</option>
                        {apps.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}

          {Object.keys(decisions).length > 0 && (
            <Note tone="blue">Your choices: {Object.entries(decisions).map(([v, a]) => `${v} → ${a === "skip" ? "skipped" : (apps.find(x => x.id === a) || { name: "chosen app" }).name}`).join(" · ")} <button onClick={() => setDecisions({})} style={{ background: "none", border: "none", color: Z.accent, fontWeight: 600, cursor: "pointer", fontSize: 13 }}>Undo all</button></Note>
          )}
          {!preview.error && (
            <button onClick={commit} disabled={busy || preview.ready === 0} style={btn(true, busy || preview.ready === 0)}>
              {busy ? "Working…" : preview.ready === 0 ? "Nothing new to import" : `Import ${preview.ready.toLocaleString()} payments`}
            </button>
          )}
        </>
      )}
    </div>
  );
}

export default function Payments() {
  const [tab, setTab] = useState("payments");
  const [refresh, setRefresh] = useState(0);
  return (
    <div>
      <div style={{ marginBottom: "1.25rem" }}>
        <div style={{ fontSize: 13, color: Z.textMuted, marginBottom: 4 }}>Financial Data</div>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Payments</h1>
      </div>
      <div style={{ display: "flex", gap: 24, borderBottom: `1px solid ${Z.border}`, marginBottom: 20 }}>
        {[["payments", "Payments"], ["uploads", "Payment Uploads"]].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{ padding: "10px 0", background: "none", border: "none", cursor: "pointer", fontSize: 14, fontWeight: tab === id ? 700 : 500, color: tab === id ? Z.accent : Z.textSecondary, borderBottom: `2px solid ${tab === id ? Z.accent : "transparent"}`, marginBottom: -1 }}>{label}</button>
        ))}
      </div>
      {tab === "payments" && <PaymentsTab key={refresh} onGoUpload={() => setTab("uploads")} />}
      {tab === "uploads" && <UploadsTab onDone={() => { setRefresh(r => r + 1); setTab("payments"); }} />}
    </div>
  );
}
