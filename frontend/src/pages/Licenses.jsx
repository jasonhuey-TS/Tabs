import { useLicenses } from "../hooks";
import { LoadingPage, ErrorBanner, EmptyState } from "../components/States";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD",
  orange: "#F97316", orangeLight: "#FFF7ED", orangeText: "#C2410C",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
};

const fmt = c => "$" + ((c ?? 0) / 100).toLocaleString("en-US", { maximumFractionDigits: 0 });

function Badge({ children, color = "gray" }) {
  const map = {
    green: { bg: Z.greenLight, color: Z.greenText, border: "#BBF7D0" },
    red: { bg: Z.redLight, color: Z.redText, border: "#FECACA" },
    amber: { bg: Z.amberLight, color: Z.amberText, border: "#FDE68A" },
    gray: { bg: "#F9FAFB", color: Z.textSecondary, border: Z.border },
  };
  const s = map[color] || map.gray;
  return <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 100, fontSize: 11, fontWeight: 600, background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{children}</span>;
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

function StatCard({ label, value, sub, icon, valueColor }) {
  return (
    <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, padding: "1.25rem 1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>
        {icon && <div style={{ width: 32, height: 32, borderRadius: 8, background: Z.accentLight, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <i className={`ti ${icon}`} style={{ fontSize: 16, color: Z.accent }} aria-hidden="true" />
        </div>}
      </div>
      <p style={{ margin: 0, fontSize: 26, fontWeight: 700, color: valueColor || Z.textPrimary, fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>{value ?? "—"}</p>
      {sub && <p style={{ margin: "6px 0 0", fontSize: 12, color: Z.textMuted }}>{sub}</p>}
    </div>
  );
}

export default function Licenses() {
  const { data: licenses, isLoading, error, refetch } = useLicenses();

  const totalSeats = licenses?.reduce((s, l) => s + (l.seats_purchased ?? 0), 0) ?? 0;
  const totalActive = licenses?.reduce((s, l) => s + (l.seats_active ?? 0), 0) ?? 0;
  const totalWaste = licenses?.reduce((s, l) => s + (l.waste_seats ?? 0), 0) ?? 0;
  const totalWasteCost = licenses?.reduce((s, l) => s + (l.waste_cost_cents ?? 0), 0) ?? 0;
  const avgUtil = totalSeats > 0 ? Math.round(totalActive / totalSeats * 100) : 0;

  const sorted = [...(licenses ?? [])].sort((a, b) => (b.waste_cost_cents ?? 0) - (a.waste_cost_cents ?? 0));

  return (
    <div>
      <div style={{ marginBottom: "1.75rem" }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Licenses</h1>
        <p style={{ margin: "4px 0 0", fontSize: 14, color: Z.textSecondary }}>Seat utilization and waste across managed applications</p>
      </div>

      {error && <ErrorBanner error={error} onRetry={refetch} />}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: "1.5rem" }}>
        <StatCard label="Seats purchased" value={totalSeats.toLocaleString()} icon="ti-users" />
        <StatCard label="Active seats" value={totalActive.toLocaleString()} valueColor={Z.green} sub={`${avgUtil}% utilization`} icon="ti-user-check" />
        <StatCard label="Idle seats" value={totalWaste.toLocaleString()} valueColor={Z.red} icon="ti-user-x" />
        <StatCard label="Annual waste" value={fmt(totalWasteCost)} valueColor={Z.red} icon="ti-currency-dollar" />
      </div>

      {totalWaste > 0 && (
        <div style={{ background: "#FFF7ED", border: `1px solid #FED7AA`, borderRadius: 10, padding: "0.875rem 1.25rem", marginBottom: "1.5rem", display: "flex", alignItems: "flex-start", gap: 10 }}>
          <i className="ti ti-alert-triangle" style={{ fontSize: 18, color: Z.orange, flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
          <p style={{ margin: 0, fontSize: 13, color: Z.orangeText, lineHeight: 1.5 }}>
            <strong>{totalWaste} seats</strong> across {sorted.filter(l => (l.waste_seats ?? 0) > 0).length} applications haven't been used in 30 days. Reclaiming them saves approximately <strong>{fmt(totalWasteCost)}</strong> annually.
          </p>
        </div>
      )}

      {isLoading ? <LoadingPage /> : sorted.length === 0 ? (
        <EmptyState icon="ti-license" title="No license data yet" body="Sync from Okta or Azure AD, or import a CSV to populate license data." />
      ) : (
        <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` }}>
                {["Application", "Purchased", "Active (30d)", "Utilization", "Idle seats", "Waste / yr"].map(h => (
                  <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((lic, i) => {
                const idle = lic.waste_seats ?? 0;
                return (
                  <tr key={lic.id} style={{ borderBottom: i < sorted.length - 1 ? `1px solid ${Z.border}` : "none" }}
                    onMouseEnter={e => e.currentTarget.style.background = "#F8FAFC"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                    <td style={{ padding: "12px 16px" }}>
                      <p style={{ margin: 0, fontWeight: 600, fontSize: 13, color: Z.textPrimary }}>{lic.app?.name ?? "—"}</p>
                      <p style={{ margin: 0, fontSize: 12, color: Z.textMuted }}>{lic.app?.department ?? lic.license_type}</p>
                    </td>
                    <td style={{ padding: "12px 16px", fontSize: 13, fontVariantNumeric: "tabular-nums" }}>{lic.seats_purchased?.toLocaleString() ?? "—"}</td>
                    <td style={{ padding: "12px 16px", fontSize: 13, fontVariantNumeric: "tabular-nums" }}>{lic.seats_active?.toLocaleString() ?? "—"}</td>
                    <td style={{ padding: "12px 16px" }}>
                      {lic.seats_purchased ? <div style={{ minWidth: 120 }}><ProgressBar value={lic.seats_active ?? 0} max={lic.seats_purchased} /></div> : <span style={{ color: Z.textMuted, fontSize: 13 }}>—</span>}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      {idle > 0 ? <Badge color="red">{idle} idle</Badge> : <Badge color="green">Fully used</Badge>}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      {(lic.waste_cost_cents ?? 0) > 0
                        ? <span style={{ color: Z.red, fontWeight: 700, fontVariantNumeric: "tabular-nums", fontSize: 13 }}>{fmt(lic.waste_cost_cents)}</span>
                        : <span style={{ color: Z.textMuted, fontSize: 13 }}>—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
