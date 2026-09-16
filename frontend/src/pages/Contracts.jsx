import { useState } from "react";
import { useContracts } from "../hooks";
import { LoadingPage, ErrorBanner, EmptyState } from "../components/States";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", accentText: "#3730A3",
  orange: "#F97316", orangeLight: "#FFF7ED", orangeText: "#C2410C",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", borderStrong: "#CBD5E1", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
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

function StatCard({ label, value, sub, icon, valueColor }) {
  return (
    <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, padding: "1.25rem 1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>
        {icon && <div style={{ width: 32, height: 32, borderRadius: 8, background: Z.accentLight, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <i className={`ti ${icon}`} style={{ fontSize: 16, color: Z.accent }} aria-hidden="true" />
        </div>}
      </div>
      <p style={{ margin: 0, fontSize: 26, fontWeight: 700, color: valueColor || Z.textPrimary, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>{value}</p>
      {sub && <p style={{ margin: "6px 0 0", fontSize: 12, color: Z.textMuted }}>{sub}</p>}
    </div>
  );
}

export default function Contracts() {
  const [view, setView] = useState("list");
  const { data: contracts, isLoading, error, refetch } = useContracts();

  const sorted = [...(contracts ?? [])].sort((a, b) => daysUntil(a.end_date) - daysUntil(b.end_date));
  const totalValue = sorted.reduce((s, c) => s + (c.total_value_cents ?? 0), 0);
  const exp90 = sorted.filter(c => c.end_date && daysUntil(c.end_date) <= 90).length;
  const autoRenew = sorted.filter(c => c.auto_renews).length;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1.75rem" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Renewals</h1>
          <p style={{ margin: "4px 0 0", fontSize: 14, color: Z.textSecondary }}>Track contracts, renewals, and spending commitments</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setView(v => v === "list" ? "timeline" : "list")} style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 8, border: `1px solid ${Z.borderStrong}`, background: Z.cardBg, color: Z.textPrimary, cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
            <i className={`ti ${view === "list" ? "ti-timeline" : "ti-list"}`} aria-hidden="true" /> {view === "list" ? "Timeline" : "List"}
          </button>
          <button style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 8, border: "none", background: Z.accent, color: "#fff", cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
            <i className="ti ti-plus" aria-hidden="true" /> Add contract
          </button>
        </div>
      </div>

      {error && <ErrorBanner error={error} onRetry={refetch} />}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: "1.75rem" }}>
        <StatCard label="Total committed" value={fmt(totalValue)} icon="ti-currency-dollar" />
        <StatCard label="Expiring in 90 days" value={exp90} valueColor={exp90 > 2 ? Z.orange : Z.green} icon="ti-calendar-event" />
        <StatCard label="Auto-renewing" value={autoRenew} valueColor={Z.amber} icon="ti-refresh" sub="review before deadline" />
        <StatCard label="Total contracts" value={sorted.length} icon="ti-file-description" />
      </div>

      {isLoading ? <LoadingPage /> : sorted.length === 0 ? (
        <EmptyState icon="ti-file-description" title="No contracts yet" body="Add contracts to track renewals and get alerts before deadlines." />
      ) : view === "list" ? (
        <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` }}>
                {["Application", "Renewal date", "Contract value", "Auto-renew", "Notice period", "Owner"].map(h => (
                  <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((c, i) => {
                const d = c.end_date ? daysUntil(c.end_date) : null;
                return (
                  <tr key={c.id} style={{ borderBottom: i < sorted.length - 1 ? `1px solid ${Z.border}` : "none" }}
                    onMouseEnter={e => e.currentTarget.style.background = "#F8FAFC"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                    <td style={{ padding: "12px 16px" }}><p style={{ margin: 0, fontWeight: 600, fontSize: 13 }}>{c.app?.name ?? "—"}</p><p style={{ margin: 0, fontSize: 12, color: Z.textMuted }}>{c.app?.vendor ?? ""}</p></td>
                    <td style={{ padding: "12px 16px" }}>
                      {c.end_date ? <div><p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: d <= 30 ? Z.red : d <= 60 ? Z.orange : Z.textPrimary }}>{fmtDate(c.end_date)}</p><p style={{ margin: 0, fontSize: 11, color: Z.textMuted }}>{d} days away</p></div> : <span style={{ color: Z.textMuted }}>—</span>}
                    </td>
                    <td style={{ padding: "12px 16px" }}><span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600, fontSize: 13 }}>{fmt(c.total_value_cents)}</span></td>
                    <td style={{ padding: "12px 16px" }}><Badge color={c.auto_renews ? "amber" : "gray"}>{c.auto_renews ? "Yes — check deadline" : "Manual"}</Badge></td>
                    <td style={{ padding: "12px 16px", fontSize: 13, color: Z.textSecondary }}>{c.cancellation_notice_days ? `${c.cancellation_notice_days} days` : "—"}</td>
                    <td style={{ padding: "12px 16px", fontSize: 12, color: Z.textMuted }}>{c.owner_email ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, padding: "1.5rem 2rem", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          {sorted.map((c, i) => {
            const d = c.end_date ? daysUntil(c.end_date) : null;
            const dotColor = d === null ? Z.textMuted : d <= 30 ? Z.red : d <= 60 ? Z.orange : Z.green;
            return (
              <div key={c.id} style={{ display: "flex", gap: 20, marginBottom: i < sorted.length - 1 ? 22 : 0 }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, width: 12 }}>
                  <div style={{ width: 12, height: 12, borderRadius: "50%", background: dotColor, marginTop: 3, flexShrink: 0 }} />
                  {i < sorted.length - 1 && <div style={{ width: 2, flex: 1, minHeight: 28, background: Z.border, marginTop: 4, borderRadius: 1 }} />}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 700, fontSize: 14, color: Z.textPrimary }}>{c.app?.name ?? "—"}</span>
                    {d !== null && <Badge color={d <= 30 ? "red" : d <= 60 ? "orange" : "green"}>{d}d</Badge>}
                    {c.auto_renews && <Badge color="amber">Auto-renews</Badge>}
                  </div>
                  <p style={{ margin: "4px 0 0", fontSize: 12, color: Z.textMuted }}>
                    {c.end_date ? fmtDate(c.end_date) : "No end date"} · {fmt(c.total_value_cents)} · {c.cancellation_notice_days ?? "?"}d notice · {c.owner_email ?? "unassigned"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
