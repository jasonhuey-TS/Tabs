import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

const API_BASE = import.meta.env?.VITE_API_BASE_URL || "";
const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D", amberLight: "#FFFBEB", amberText: "#92400E", redLight: "#FEF2F2", redText: "#B91C1C",
};
const card = { background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" };
const input = { width: "100%", boxSizing: "border-box", padding: "8px 10px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, fontFamily: "inherit" };
const th = { padding: "9px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` };
const td = { padding: "9px 14px", fontSize: 13, borderBottom: `1px solid ${Z.border}`, color: Z.textPrimary };
const btn = (primary, disabled) => ({ padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1, border: primary ? "none" : `1px solid ${Z.border}`, background: primary ? Z.accent : Z.cardBg, color: primary ? "#fff" : Z.textPrimary });
const FIELD_LABELS = [["name", "App name", true], ["category", "Category"], ["subcategory", "Subcategory"], ["function", "Function(s)"]];

function Note({ tone = "amber", children }) {
  const t = { amber: [Z.amberLight, "#FDE68A", Z.amberText], red: [Z.redLight, "#FECACA", Z.redText], green: [Z.greenLight, "#BBF7D0", Z.greenText], blue: [Z.accentLight, "#C7D2FE", "#3730A3"] }[tone];
  return <div style={{ background: t[0], border: `1px solid ${t[1]}`, color: t[2], borderRadius: 10, padding: "9px 14px", fontSize: 13, lineHeight: 1.5, marginBottom: 14 }}>{children}</div>;
}

function Importer({ onDone }) {
  const [file, setFile] = useState(null);
  const [mapping, setMapping] = useState(null);
  const [valueMap, setValueMap] = useState({});
  const [decisions, setDecisions] = useState({});
  const [overwrite, setOverwrite] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [apps, setApps] = useState([]);

  useEffect(() => { api.get("/apps?limit=1000").then(d => setApps(Array.isArray(d) ? d : [])).catch(() => setApps([])); }, []);
  useEffect(() => {
    if (!file) return undefined;
    let cancelled = false;
    setBusy(true); setError(null);
    api.post("/categories/import/preview", { text: file.text, mapping, value_map: valueMap, decisions, overwrite })
      .then(p => {
        if (cancelled) return;
        if (!p.headers) { setError(p.error); setPreview(null); return; }
        setPreview(p);
        if (!mapping) setMapping(p.mapping);
      })
      .catch(e => { if (!cancelled) setError(e.message || "Could not read that file"); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [file, mapping, valueMap, decisions, overwrite]);

  function pick(e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    if (f.size > 15 * 1024 * 1024) { setError("That file is larger than 15 MB."); return; }
    const reader = new FileReader();
    reader.onload = () => { setResult(null); setPreview(null); setMapping(null); setValueMap({}); setDecisions({}); setFile({ name: f.name, text: String(reader.result || "") }); };
    reader.readAsText(f);
  }
  async function apply() {
    setBusy(true); setError(null);
    try {
      const r = await api.post("/categories/import/commit", { text: file.text, mapping, value_map: valueMap, decisions, overwrite, file_name: file.name });
      if (!r.ok) { setError(r.error || "Nothing was changed."); return; }
      setResult(r); setFile(null); setPreview(null); onDone();
    } catch (e) { setError(e.message || "The import failed"); } finally { setBusy(false); }
  }
  const decide = (name, value) => setDecisions(d => { const n = { ...d }; if (value) n[name] = value; else delete n[name]; return n; });

  return (
    <div style={{ ...card, padding: "20px 24px" }} data-importer>
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Import categories from Zylo</div>
      <div style={{ fontSize: 13, color: Z.textSecondary, lineHeight: 1.6, marginBottom: 14 }}>
        In Zylo, open the Applications table, use <strong>Fields</strong> to show the <strong>Category</strong>, <strong>Subcategory</strong> and <strong>Functions</strong> columns, then download it. Upload that file here. Apps are matched by name, and you'll see exactly what will change before anything is saved.
      </div>
      {result && (
        <div data-result="categories-import"><Note tone="green"><strong>Updated {result.updated.toLocaleString()} {result.updated === 1 ? "app" : "apps"}</strong> ({result.category_changes.toLocaleString()} {result.category_changes === 1 ? "category" : "categories"}, {result.subcategory_changes.toLocaleString()} {result.subcategory_changes === 1 ? "subcategory" : "subcategories"}, {result.function_changes.toLocaleString()} with functions).
          {result.unchanged > 0 && <> {result.unchanged.toLocaleString()} already had what the file says.</>}{result.unmatched_rows > 0 && <> {result.unmatched_rows.toLocaleString()} rows didn't match an app.</>}</Note></div>
      )}
      <input type="file" accept=".csv,.txt,text/csv,text/plain" onChange={pick} aria-label="Choose a categories file" style={{ fontSize: 13, marginBottom: 14 }} />
      {error && <Note tone="red">{error}</Note>}
      {preview && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12, marginBottom: 6 }} data-step="mapping">
            {FIELD_LABELS.map(([field, label, required]) => (
              <label key={field} style={{ display: "block" }}>
                <span style={{ display: "block", fontSize: 12, fontWeight: 600, color: Z.textSecondary, marginBottom: 4 }}>{label}{required ? " *" : ""} column</span>
                <select aria-label={`${label} column`} style={input} value={(mapping || {})[field] || ""} onChange={e => setMapping(m => { const n = { ...(m || preview.mapping) }; if (e.target.value) n[field] = e.target.value; else delete n[field]; return n; })}>
                  <option value="">{required ? "Choose a column…" : "— none —"}</option>
                  {preview.headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </label>))}
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: Z.textSecondary, margin: "10px 0 14px" }}>
            <input type="checkbox" checked={overwrite} onChange={e => setOverwrite(e.target.checked)} /> Also replace categories and functions that are already set (otherwise only apps still on “Other”, or with no function, are filled in)
          </label>
          {preview.error ? <Note tone="red">{preview.error}</Note> : (
            <>
              <div data-step="summary" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12, marginBottom: 16 }}>
                {[["Will be updated", preview.will_update.toLocaleString(), `${preview.category_changes} categories · ${preview.subcategory_changes} subcategories · ${preview.function_changes} with functions`], ["Already correct", preview.unchanged.toLocaleString(), "left alone"],
                  ["Didn't match an app", preview.unmatched_rows.toLocaleString(), `${preview.unmatched.length} ${preview.unmatched.length === 1 ? "name" : "names"}`], ["Skipped or blank", (preview.skipped + preview.blank).toLocaleString(), "rows"]].map(([l, v, sub]) => (
                  <div key={l} style={{ border: `1px solid ${Z.border}`, borderRadius: 10, padding: "12px 14px" }}>
                    <div style={{ fontSize: 12, color: Z.textSecondary }}>{l}</div><div style={{ fontSize: 22, fontWeight: 600, margin: "2px 0" }}>{v}</div><div style={{ fontSize: 12, color: Z.textMuted }}>{sub}</div>
                  </div>))}
              </div>

              {preview.values.length > 0 && (
                <div data-step="values" style={{ border: `1px solid ${Z.border}`, borderRadius: 10, overflow: "hidden", marginBottom: 16 }}>
                  <div style={{ padding: "10px 14px", fontSize: 14, fontWeight: 600 }}>Match their names to Tab's categories</div>
                  <div style={{ fontSize: 12.5, color: Z.textSecondary, padding: "0 14px 10px" }}>For each app Tab uses the most specific name it understands ({preview.value_sources.join(", then ")}), so “Accounting &amp; Finance” wins over a broad “Office”. Tab suggested a category for each; change any that look wrong, or choose “Leave as is” to keep an app's current category.</div>
                  <div style={{ maxHeight: 300, overflowY: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
                      <thead><tr><th style={th}>Their name</th><th style={{ ...th, textAlign: "right" }}>Rows</th><th style={th}>Tab category</th></tr></thead>
                      <tbody>{preview.values.map(v => (
                        <tr key={v.value} data-value={v.value}>
                          <td style={td}>{v.value}</td><td style={{ ...td, textAlign: "right" }}>{v.count.toLocaleString()}</td>
                          <td style={td}><select aria-label={`Category for ${v.value}`} style={{ ...input, maxWidth: 220 }} value={v.chosen} onChange={e => setValueMap(m => ({ ...m, [v.value]: e.target.value }))}>
                            <option value="">Leave as is</option>{preview.categories.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                          </select></td>
                        </tr>))}</tbody>
                    </table>
                  </div>
                </div>
              )}

              {preview.unmatched.length > 0 && (
                <div data-step="unmatched" style={{ border: `1px solid ${Z.border}`, borderRadius: 10, overflow: "hidden", marginBottom: 16 }}>
                  <div style={{ padding: "10px 14px", fontSize: 14, fontWeight: 600 }}>Names that didn't match an app</div>
                  <div style={{ fontSize: 12.5, color: Z.textSecondary, padding: "0 14px 10px" }}>Pick the app each one is, or skip it. Your choices are remembered for next time.</div>
                  <div style={{ maxHeight: 260, overflowY: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
                      <thead><tr><th style={th}>Name in the file</th><th style={{ ...th, textAlign: "right" }}>Rows</th><th style={th}>App</th></tr></thead>
                      <tbody>{preview.unmatched.map(u => (
                        <tr key={u.name}>
                          <td style={{ ...td, fontWeight: 600 }}>{u.name}</td><td style={{ ...td, textAlign: "right" }}>{u.rows}</td>
                          <td style={td}>
                            {u.suggestions.length > 0 && <div style={{ marginBottom: 6, fontSize: 12, color: Z.textSecondary }}>Did you mean {u.suggestions.map(s => <button key={s.app_id} onClick={() => decide(u.name, s.app_id)} style={{ ...btn(false), padding: "2px 10px", marginLeft: 6 }}>{s.name}</button>)}</div>}
                            <select aria-label={`App for ${u.name}`} style={{ ...input, maxWidth: 260 }} value="" onChange={e => decide(u.name, e.target.value)}>
                              <option value="">Choose an app…</option><option value="skip">Skip these rows</option>{apps.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                            </select>
                          </td>
                        </tr>))}</tbody>
                    </table>
                  </div>
                </div>
              )}
              <button onClick={apply} disabled={busy || preview.will_update === 0} style={btn(true, busy || preview.will_update === 0)}>
                {busy ? "Working…" : preview.will_update === 0 ? "Nothing to update" : `Apply to ${preview.will_update.toLocaleString()} ${preview.will_update === 1 ? "app" : "apps"}`}
              </button>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default function Categories() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => { api.get("/categories/summary").then(setData).catch(e => setError(e.message || "Could not load categories")); }, []);
  useEffect(() => { load(); }, [load]);

  if (error) return <Note tone="red">{error}</Note>;
  if (!data) return <p style={{ color: Z.textMuted }}>Loading…</p>;
  const pct = n => (data.total ? Math.round((100 * n) / data.total) : 0);
  const max = Math.max(1, ...data.by_category.map(c => c.count));
  return (
    <div style={{ maxWidth: 1000 }}>
      <h1 style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 700 }}>App categories</h1>
      <p style={{ margin: "0 0 20px", fontSize: 14, color: Z.textSecondary, lineHeight: 1.6 }}>A <strong>category</strong> is one of 12 broad groups, a <strong>subcategory</strong> is a finer label (like “Accounting &amp; Finance”), and <strong>functions</strong> say what an app is for (like “Expense Management”). Functions are what let Ask Tab spot overlapping apps.</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 20 }}>
        {[["Apps", data.total, "in Tab"], ["With a category", data.with_category, `${pct(data.with_category)}% (not “Other”)`], ["With a subcategory", data.with_subcategory, `${pct(data.with_subcategory)}%`], ["With a function", data.with_function, `${pct(data.with_function)}%`]].map(([l, v, s]) => (
          <div key={l} style={{ ...card, padding: "16px 20px" }} data-stat={l}><div style={{ fontSize: 13, color: Z.textSecondary }}>{l}</div><div style={{ fontSize: 30, fontWeight: 500, margin: "6px 0 2px" }}>{v.toLocaleString()}</div><div style={{ fontSize: 12.5, color: Z.textMuted }}>{s}</div></div>))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 20, marginBottom: 20 }}>
        <div style={{ ...card, padding: "16px 20px" }} data-card="by-category">
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>By category</div>
          {data.by_category.map(c => (
            <div key={c.category} data-category={c.category} style={{ display: "flex", alignItems: "center", margin: "6px 0", fontSize: 13 }}>
              <div style={{ width: 130, color: Z.textPrimary }}>{c.label}</div>
              <div style={{ flex: 1, background: "#F1F5F9", borderRadius: 4, height: 10, overflow: "hidden" }}><div style={{ width: `${(100 * c.count) / max}%`, height: "100%", background: c.category === "other" ? "#CBD5E1" : Z.accent }} /></div>
              <div style={{ width: 54, textAlign: "right", color: Z.textSecondary }}>{c.count.toLocaleString()}</div>
            </div>))}
        </div>
        <div style={{ ...card, padding: "16px 20px" }} data-card="functions">
          <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}><div style={{ flex: 1, fontSize: 15, fontWeight: 600 }}>Most common functions</div>
            <a href={`${API_BASE}/api/v1/categories/export.csv`} style={{ fontSize: 13, fontWeight: 600, color: Z.accent, textDecoration: "none" }}>Download current list (CSV)</a></div>
          {data.top_functions.length === 0 ? <div style={{ fontSize: 13, color: Z.textMuted, lineHeight: 1.6 }}>No functions recorded yet. Import them below.</div>
            : data.top_functions.map(f => <div key={f.function} style={{ display: "flex", fontSize: 13, margin: "6px 0" }}><div style={{ flex: 1 }}>{f.function}</div><div style={{ color: Z.textSecondary }}>{f.apps} {f.apps === 1 ? "app" : "apps"}</div></div>)}
        </div>
      </div>
      <Importer onDone={load} />
    </div>
  );
}
