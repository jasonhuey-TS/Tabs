import { useDashboard } from "../hooks";
import { LoadingPage, ErrorBanner, Skeleton } from "../components/States";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", accentText: "#3730A3",
  orange: "#F97316", orangeLight: "#FFF7ED", orangeText: "#C2410C",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
};

const fmt = c => "$" + ((c ?? 0) / 100).toLocaleString("en-US", { maximumFractionDigits: 0 });
const daysUntil = d => Math.round((new Date(d) - new Date()) / 86400000);
const fmtDate = d => new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

function Badge({ children, color = "gray" }) {
  const map = {
    green: { bg: Z.greenLight, color: Z.greenText, border: "#BBF7D0" },
    red: { bg: Z.redLight, color: Z.redText, border: "#FECACA" },
    orange: { bg: Z.orangeLight, color: Z.orangeText, border: "#FED7AA" },
    amber: { bg: Z.amberLight, color: Z.amberText, border: "#FDE68A" },
    blue: { bg: Z.accentLight, color: Z.accentText, border: "#C7D2FE" },
    gray: { bg: "#F9FAFB", color: Z.textSecondary, border: Z.border },
  };
  const s = map[color] || map.gray;
  return <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 100, fontSize: 11, fontWeight: 600, background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{children}</span>;
}

function StatCard({ label, value, sub, icon, valueColor, loading }) {
  return (
    <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, padding: "1.25rem 1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>
        {icon && <div style={{ width: 32, height: 32, borderRadius: 8, background: Z.accentLight, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <i className={`ti ${icon}`} style={{ fontSize: 16, color: Z.accent }} aria-hidden="true" />
        </div>}
      </div>
      {loading ? <div style={{ height: 28, width: "60%", borderRadius: 4, background: "#E2E8F0", animation: "shimmer 1.2s infinite", backgroundSize: "200% 100%", backgroundImage: "linear-gradient(90deg,#F1F5F9 25%,#E2E8F0 50%,#F1F5F9 75%)" }} />
        : <p style={{ margin: 0, fontSize: 26, fontWeight: 700, color: valueColor || Z.textPrimary, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>{value}</p>}
      {sub && <p style={{ margin: "6px 0 0", fontSize: 12, color: Z.textMuted }}>{sub}</p>}
    </div>
  );
}

function ProgressBar({ value, max }) {
  const pct = Math.round(Math.min(100, (value / max) * 100));
  const color = pct < 50 ? Z.red : pct < 75 ? Z.amber : Z.green;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 5, background: "#E2E8F0", borderRadius: 100, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 100 }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 600, color: Z.textSecondary, minWidth: 36, textAlign: "right" }}>{pct}%</span>
    </div>
  );
}

export default function Dashboard() {
  const { data, isLoading, error, refetch } = useDashboard();

  if (isLoading) return <LoadingPage />;

  return (
    <div>
      <style>{`@keyframes shimmer { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }`}</style>
      <div style={{ marginBottom: "1.75rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Analytics</h1>
          <p style={{ margin: "4px 0 0", fontSize: 14, color: Z.textSecondary }}>Portfolio overview · live data</p>
        </div>
        <button onClick={refetch} style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, fontSize: 12, color: Z.textSecondary, cursor: "pointer" }}>
          <i className="ti ti-refresh" style={{ fontSize: 14 }} aria-hidden="true" /> Refresh
        </button>
      </div>

      {error && <ErrorBanner error={error} onRetry={refetch} />}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: "1.75rem" }}>
        <StatCard label="Annual spend" value={fmt(data?.total_annual_spend_cents)} icon="ti-currency-dollar" sub={`${data?.total_apps ?? "—"} applications`} loading={!data} />
        <StatCard label="License waste" value={fmt(data?.total_waste_cents)} valueColor={Z.red} icon="ti-alert-triangle" sub={`${data?.wasted_seats ?? "—"} idle seats`} loading={!data} />
        <StatCard label="Avg utilization" value={data ? `${Math.round(data.avg_utilization_pct ?? 0)}%` : "—"} valueColor={(data?.avg_utilization_pct ?? 0) > 75 ? Z.green : Z.amber} icon="ti-chart-bar" sub="active / purchased seats" loading={!data} />
        <StatCard label="Shadow IT" value={data?.shadow_it_apps ?? "—"} valueColor={Z.orange} icon="ti-eye-off" sub="applications need review" loading={!data} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: "1.25rem", marginBottom: "1.25rem" }}>
        {/* Upcoming renewals */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
            <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: Z.textPrimary }}>Upcoming renewals</h2>
            <span style={{ fontSize: 12, color: Z.accent, fontWeight: 600, cursor: "pointer" }}>View all →</span>
          </div>
          <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` }}>
                  {["Application", "Expires", "Value", "Auto-renew"].map(h => (
                    <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!data ? (
                  [1,2,3].map(i => (
                    <tr key={i} style={{ borderBottom: `1px solid ${Z.border}` }}>
                      {[1,2,3,4].map(j => <td key={j} style={{ padding: "12px 16px" }}><div style={{ height: 14, borderRadius: 3, background: "#E2E8F0", width: j === 1 ? "70%" : j === 2 ? "40%" : j === 3 ? "55%" : "35%" }} /></td>)}
                    </tr>
                  ))
                ) : data.upcoming_renewals?.slice(0, 5).map((c, i, arr) => {
                  const d = daysUntil(c.end_date);
                  return (
                    <tr key={c.contract_id} style={{ borderBottom: i < arr.length - 1 ? `1px solid ${Z.border}` : "none" }}>
                      <td style={{ padding: "12px 16px" }}><p style={{ margin: 0, fontWeight: 600, fontSize: 13 }}>{c.app_name}</p><p style={{ margin: 0, fontSize: 12, color: Z.textMuted }}>{c.vendor}</p></td>
                      <td style={{ padding: "12px 16px" }}><span style={{ fontWeight: 700, color: d <= 30 ? Z.red : d <= 60 ? Z.orange : Z.textPrimary, fontSize: 13 }}>{d}d</span></td>
                      <td style={{ padding: "12px 16px" }}><span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600, fontSize: 13 }}>{fmt(c.total_value_cents)}</span></td>
                      <td style={{ padding: "12px 16px" }}><Badge color="amber">Yes</Badge></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Spend by category */}
        <div>
          <h2 style={{ margin: "0 0 1rem", fontSize: 15, fontWeight: 700, color: Z.textPrimary }}>Spend by category</h2>
          <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, padding: "1.25rem", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            {!data ? [80, 60, 45, 35, 25].map((w, i) => (
              <div key={i} style={{ marginBottom: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                  <div style={{ height: 13, width: `${w}%`, borderRadius: 3, background: "#E2E8F0" }} />
                  <div style={{ height: 13, width: "20%", borderRadius: 3, background: "#E2E8F0" }} />
                </div>
                <div style={{ height: 5, borderRadius: 100, background: "#E2E8F0" }} />
              </div>
            )) : (() => {
              const cats = data.spend_by_category ?? [];
              const max = cats[0]?.total_annual_cost_cents ?? 1;
              return cats.map(cat => (
                <div key={cat.category} style={{ marginBottom: 14 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                    <span style={{ fontSize: 13, fontWeight: 500, color: Z.textPrimary }}>{cat.category}</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: Z.textSecondary, fontVariantNumeric: "tabular-nums" }}>{fmt(cat.total_annual_cost_cents)}</span>
                  </div>
                  <ProgressBar value={cat.total_annual_cost_cents} max={max} />
                </div>
              ));
            })()}
          </div>
        </div>
      </div>

      {/* Contracts alert */}
      {data && (data.contracts_expiring_30d > 0 || data.contracts_expiring_90d > 0) && (
        <div style={{ background: "#FFF7ED", border: `1px solid #FED7AA`, borderRadius: 10, padding: "0.875rem 1.25rem", marginBottom: "1.25rem", display: "flex", alignItems: "center", gap: 10 }}>
          <i className="ti ti-calendar-event" style={{ fontSize: 18, color: Z.orange, flexShrink: 0 }} aria-hidden="true" />
          <p style={{ margin: 0, fontSize: 13, color: Z.orangeText }}>
            <strong>{data.contracts_expiring_30d}</strong> contracts expire within 30 days · <strong>{data.contracts_expiring_90d}</strong> within 90 days. Review the Renewals tab.
          </p>
        </div>
      )}
    </div>
  );
}
