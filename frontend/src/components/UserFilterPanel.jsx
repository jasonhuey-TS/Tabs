import { useState, useMemo } from "react";
import { DATE_OPS, NUMBER_OPS, blankSpec, describe, distinctValues, isActive } from "./userFilters";

const Z = { accent: "#4B5EDE", accentLight: "#EEF0FD", textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF", heading: "#4A5878" };
const input = { width: "100%", boxSizing: "border-box", padding: "9px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 14, fontFamily: "inherit", outline: "none" };
const link = { background: "none", border: "none", padding: 0, color: Z.accent, fontWeight: 600, fontSize: 12.5, cursor: "pointer" };

function EnumEditor({ field, users, spec, onChange }) {
  const [q, setQ] = useState("");
  const all = useMemo(() => distinctValues(field, users), [field, users]);
  const shown = all.filter(([v]) => !q || v.toLowerCase().includes(q.toLowerCase()));
  const ticked = Array.isArray(spec) ? spec : [];
  const toggle = v => { const next = ticked.includes(v) ? ticked.filter(x => x !== v) : [...ticked, v]; onChange(next.length ? next : null); };
  return (
    <div data-editor="enum">
      {all.length > 8 && <input aria-label="Search values" value={q} onChange={e => setQ(e.target.value)} placeholder="Search values…" style={{ ...input, marginBottom: 8 }} />}
      <div style={{ display: "flex", gap: 14, marginBottom: 6 }}>
        <button type="button" style={link} onClick={() => onChange(shown.length ? [...new Set([...ticked, ...shown.map(([v]) => v)])] : null)}>Select all{q ? " shown" : ""}</button>
        <button type="button" style={link} onClick={() => onChange(null)}>Clear</button>
      </div>
      <div style={{ maxHeight: 280, overflowY: "auto" }}>
        {shown.map(([v, n]) => (
          <label key={v} data-value={v} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, padding: "6px 2px", cursor: "pointer" }}>
            <input type="checkbox" checked={ticked.includes(v)} onChange={() => toggle(v)} />
            <span style={{ flex: 1, color: v === "(blank)" ? Z.textMuted : Z.textPrimary }}>{v}</span><span style={{ color: Z.textMuted, fontSize: 12.5 }}>{n.toLocaleString()}</span>
          </label>))}
        {shown.length === 0 && <div style={{ fontSize: 13, color: Z.textMuted, padding: "8px 2px" }}>No values match.</div>}
      </div>
    </div>
  );
}

const Row = ({ children }) => <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>{children}</div>;

function TextEditor({ spec, onChange }) {
  return (
    <div data-editor="text">
      <input autoFocus aria-label="Contains" placeholder="Contains…" value={(spec && spec.value) || ""} onChange={e => onChange({ op: "contains", value: e.target.value })} style={input} />
      <Row><button type="button" style={link} onClick={() => onChange({ op: "blank" })}>Only people with no value</button></Row>
    </div>
  );
}

function NumberEditor({ spec, onChange }) {
  const s = spec && !Array.isArray(spec) ? spec : { op: "gte", value: "" };
  const set = patch => onChange({ ...s, ...patch });
  return (
    <div data-editor="number">
      <select aria-label="Number filter type" value={s.op} onChange={e => onChange({ op: e.target.value, value: s.value ?? "", value2: "" })} style={input}>{NUMBER_OPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
      {s.op !== "blank" && (
        <Row>
          <input type="number" aria-label="Value" value={s.value ?? ""} onChange={e => set({ value: e.target.value })} style={input} />
          {s.op === "between" && <><span style={{ color: Z.textMuted }}>and</span><input type="number" aria-label="Upper value" value={s.value2 ?? ""} onChange={e => set({ value2: e.target.value })} style={input} /></>}
        </Row>)}
    </div>
  );
}

function DateEditor({ spec, onChange }) {
  const s = spec && !Array.isArray(spec) ? spec : { op: "last_days", value: "" };
  const set = patch => onChange({ ...s, ...patch });
  const relative = s.op === "last_days" || s.op === "older_days";
  return (
    <div data-editor="date">
      <select aria-label="Date filter type" value={s.op} onChange={e => onChange({ op: e.target.value, value: "", value2: "" })} style={input}>{DATE_OPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
      {relative && <Row><input type="number" min="0" aria-label="Days" value={s.value ?? ""} onChange={e => set({ value: e.target.value })} style={{ ...input, width: 110 }} /><span style={{ color: Z.textSecondary }}>days{s.op === "last_days" ? "" : " ago"}</span></Row>}
      {(s.op === "before" || s.op === "after") && <Row><input type="date" aria-label="Date" value={s.value || ""} onChange={e => set({ value: e.target.value })} style={input} /></Row>}
      {s.op === "between" && <Row><input type="date" aria-label="From date" value={s.value || ""} onChange={e => set({ value: e.target.value })} style={input} /><span style={{ color: Z.textMuted }}>to</span><input type="date" aria-label="To date" value={s.value2 || ""} onChange={e => set({ value2: e.target.value })} style={input} /></Row>}
    </div>
  );
}

/** The Filters panel: a searchable list of every field people can be filtered on (each labelled with where its data comes from);
 *  pick one to set its filter. "Active" shows only the fields with a filter applied. */
export default function UserFilterPanel({ fields, users, filters, setFilter, onClearAll, onClose }) {
  const [query, setQuery] = useState("");
  const [onlyActive, setOnlyActive] = useState(false);
  const [openKey, setOpenKey] = useState(null);
  const sorted = useMemo(() => [...fields].sort((a, b) => a.label.localeCompare(b.label)), [fields]);
  const open = fields.find(f => f.key === openKey);
  const q = query.trim().toLowerCase();
  const list = sorted.filter(f => (!q || f.label.toLowerCase().includes(q) || f.source.toLowerCase().includes(q)) && (!onlyActive || isActive(filters[f.key])));
  const anyActive = fields.some(f => isActive(filters[f.key]));

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
      <div data-panel="filters" role="dialog" aria-label="Filters" style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, width: 400, maxHeight: 560, overflowY: "auto", zIndex: 41, background: Z.cardBg,
                                                                              border: `1px solid ${Z.border}`, borderRadius: 12, boxShadow: "0 12px 34px rgba(0,0,0,0.18)" }}>
        {!open ? (
          <div>
            <div style={{ position: "sticky", top: 0, background: Z.cardBg, padding: "14px 18px 10px", borderBottom: `1px solid ${Z.border}`, zIndex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
                <div style={{ flex: 1, fontSize: 19, fontWeight: 600, color: Z.heading }}>Search</div>
                <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 14, color: Z.textSecondary, cursor: "pointer" }}>
                  <input type="checkbox" aria-label="Show only fields with a filter" checked={onlyActive} onChange={e => setOnlyActive(e.target.checked)} /> Active
                </label>
              </div>
              <input autoFocus aria-label="Search filters" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search filters…" style={{ ...input, border: `2px solid ${Z.heading}`, borderRadius: 8 }} />
            </div>
            <div data-field-list>
              {list.map(f => {
                const spec = filters[f.key], active = isActive(spec);
                return (
                  <button key={f.key} data-field={f.key} data-active={active ? "true" : undefined} onClick={() => setOpenKey(f.key)} title={`${f.label} (${f.source})`}
                          style={{ display: "flex", alignItems: "center", width: "100%", textAlign: "left", padding: "11px 18px", background: Z.cardBg, border: "none", borderBottom: `1px solid ${Z.border}`, cursor: "pointer", fontFamily: "inherit" }}>
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ display: "block", fontSize: 15.5, color: Z.textPrimary }}>{f.label}</span>
                      <span style={{ display: "block", fontSize: 12.5, color: Z.textMuted, marginTop: 1 }}>{f.source}</span>
                      {active && <span data-summary style={{ display: "block", fontSize: 12.5, color: Z.accent, fontWeight: 600, marginTop: 2 }}>{describe(f, spec)}</span>}
                    </span>
                    {active && <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: "50%", background: Z.accent, marginRight: 10 }} />}
                    <span aria-hidden="true" style={{ color: Z.textSecondary, fontSize: 20 }}>›</span>
                  </button>);
              })}
              {list.length === 0 && <div style={{ padding: "22px 18px", fontSize: 13.5, color: Z.textMuted }}>{onlyActive ? "No filters are applied yet." : "No filters match that search."}</div>}
            </div>
            {anyActive && <div style={{ padding: "10px 18px", position: "sticky", bottom: 0, background: Z.cardBg, borderTop: `1px solid ${Z.border}` }}><button type="button" onClick={onClearAll} style={link}>Clear all filters</button></div>}
          </div>
        ) : (
          <div data-detail={open.key}>
            <div style={{ padding: "14px 18px", borderBottom: `1px solid ${Z.border}`, display: "flex", alignItems: "center", gap: 10, position: "sticky", top: 0, background: Z.cardBg, zIndex: 1 }}>
              <button type="button" aria-label="Back to all filters" onClick={() => setOpenKey(null)} style={{ background: "none", border: "none", fontSize: 24, lineHeight: 1, cursor: "pointer", color: Z.textSecondary, padding: "0 6px 2px 0" }}>‹</button>
              <div style={{ minWidth: 0 }}><div style={{ fontSize: 17, fontWeight: 600, color: Z.heading }}>{open.label}</div><div style={{ fontSize: 12.5, color: Z.textMuted }}>{open.source}</div></div>
            </div>
            <div style={{ padding: "14px 18px 18px" }}>
              {(open.type === "enum" || open.type === "bool") && <EnumEditor field={open} users={users} spec={filters[open.key]} onChange={spec => setFilter(open.key, spec)} />}
              {open.type === "text" && <TextEditor spec={filters[open.key]} onChange={spec => setFilter(open.key, spec.op === "contains" && !spec.value ? null : spec)} />}
              {open.type === "number" && <NumberEditor spec={filters[open.key] || blankSpec(open)} onChange={spec => setFilter(open.key, spec)} />}
              {open.type === "date" && <DateEditor spec={filters[open.key] || blankSpec(open)} onChange={spec => setFilter(open.key, spec)} />}
              {isActive(filters[open.key]) && <div style={{ marginTop: 16, fontSize: 13, color: Z.textSecondary }}>Showing people whose {open.label.toLowerCase()} is <strong style={{ color: Z.textPrimary }}>{describe(open, filters[open.key])}</strong>.
                {" "}<button type="button" style={link} onClick={() => setFilter(open.key, null)}>Clear this filter</button></div>}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
