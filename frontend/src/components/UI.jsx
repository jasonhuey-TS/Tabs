export function StatCard({ label, value, sub, accent, icon, trend }) {
  return (
    <div style={{
      background: "var(--surface-1)", borderRadius: 12,
      border: "0.5px solid var(--border)", padding: "1.25rem",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)", fontWeight: 400 }}>{label}</p>
        {icon && <i className={`ti ${icon}`} style={{ fontSize: 18, color: "var(--text-muted)" }} aria-hidden="true" />}
      </div>
      <p style={{
        margin: "0.5rem 0 0", fontSize: 28, fontWeight: 500,
        color: accent ? `var(--text-${accent})` : "var(--text-primary)",
        fontVariantNumeric: "tabular-nums", lineHeight: 1.1
      }}>{value}</p>
      {sub && <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--text-muted)" }}>{sub}</p>}
      {trend && (
        <p style={{ margin: "6px 0 0", fontSize: 12, color: trend > 0 ? "var(--text-danger)" : "var(--text-success)" }}>
          {trend > 0 ? "↑" : "↓"} {Math.abs(trend)}% vs last month
        </p>
      )}
    </div>
  );
}

export function Badge({ children, variant = "neutral" }) {
  const styles = {
    neutral: { bg: "var(--surface-0)", color: "var(--text-secondary)", border: "var(--border)" },
    accent: { bg: "var(--bg-accent)", color: "var(--text-accent)", border: "var(--border-accent)" },
    success: { bg: "var(--bg-success)", color: "var(--text-success)", border: "var(--border-success)" },
    warning: { bg: "var(--bg-warning)", color: "var(--text-warning)", border: "var(--border-warning)" },
    danger: { bg: "var(--bg-danger)", color: "var(--text-danger)", border: "var(--border-danger)" },
  };
  const s = styles[variant] || styles.neutral;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px",
      borderRadius: 100, fontSize: 11, fontWeight: 500,
      background: s.bg, color: s.color, border: `0.5px solid ${s.border}`
    }}>{children}</span>
  );
}

export function SectionHeader({ title, action }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
      <h2 style={{ margin: 0, fontSize: 16, fontWeight: 500 }}>{title}</h2>
      {action}
    </div>
  );
}

export function DataTable({ columns, rows, emptyText = "No data" }) {
  return (
    <div style={{ background: "var(--surface-1)", borderRadius: 12, border: "0.5px solid var(--border)", overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "0.5px solid var(--border)" }}>
            {columns.map(col => (
              <th key={col.key} style={{
                padding: "10px 16px", textAlign: "left", fontSize: 12,
                fontWeight: 500, color: "var(--text-muted)", whiteSpace: "nowrap"
              }}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={columns.length} style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>{emptyText}</td></tr>
          ) : rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: i < rows.length - 1 ? "0.5px solid var(--border)" : "none" }}>
              {columns.map(col => (
                <td key={col.key} style={{ padding: "12px 16px", fontSize: 13, color: "var(--text-primary)" }}>
                  {col.render ? col.render(row[col.key], row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PageHeader({ title, sub, action }) {
  return (
    <div style={{ marginBottom: "2rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 500 }}>{title}</h1>
        {sub && <p style={{ margin: "4px 0 0", fontSize: 14, color: "var(--text-secondary)" }}>{sub}</p>}
      </div>
      {action}
    </div>
  );
}

export function ProgressBar({ value, max, accent = "accent" }) {
  const pct = Math.round(Math.min(100, (value / max) * 100));
  const color = pct < 50 ? "var(--fill-danger)" : pct < 75 ? "var(--fill-warning)" : "var(--fill-success)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "var(--border)", borderRadius: 100, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 100 }} />
      </div>
      <span style={{ fontSize: 12, color: "var(--text-secondary)", minWidth: 32, textAlign: "right" }}>{pct}%</span>
    </div>
  );
}
