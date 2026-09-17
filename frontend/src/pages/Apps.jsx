import { useState } from "react";
import { useApps, useUpdateApp } from "../hooks";
import { LoadingPage, ErrorBanner, EmptyState } from "../components/States";
import ImportModal from "../components/ImportModal";

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
const STATUS_COLOR = { managed: "green", unmanaged: "red", sanctioned: "blue", under_review: "amber", blocked: "gray" };
const SOURCE_ICON = { okta: "ti-shield-lock", azure_ad: "ti-brand-azure", csv: "ti-table-import" };

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

export default function Apps() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [shadowFilter, setShadowFilter] = useState("");
  const [showImport, setShowImport] = useState(false);

  const { data: apps, isLoading, error, refetch } = useApps({
    search: search || undefined,
    status: statusFilter || undefined,
    shadow_it: shadowFilter === "shadow" ? true : shadowFilter === "managed" ? false : undefined,
    limit: 500,
  });

  const updateApp = useUpdateApp();

  function handleStatusChange(app, newStatus) {
    updateApp.mutate({ id: app.id, data: { status: newStatus } });
  }

  return (
    <div>
      {showImport && <ImportModal onClose={() => { setShowImport(false); refetch(); }} />}

      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1.75rem" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Applications</h1>
          <p style={{ margin: "4px 0 0", fontSize: 14, color: Z.textSecondary }}>
            {apps ? `${apps.length} apps discovered · ${apps.filter(a => a.is_shadow_it).length} unmanaged` : "Loading…"}
          </p>
        </div>
        <button onClick={() => setShowImport(true)} style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 8, border: `1px solid ${Z.borderStrong}`, background: Z.cardBg, color: Z.textPrimary, cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
          <i className="ti ti-table-import" aria-hidden="true" /> Import CSV
        </button>
      </div>

      {error && <ErrorBanner error={error} onRetry={refetch} />}

      <div style={{ display: "flex", gap: 10, marginBottom: "1.25rem" }}>
        <div style={{ position: "relative", flex: 1 }}>
          <i className="ti ti-search" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", fontSize: 14, color: Z.textMuted }} aria-hidden="true" />
          <input placeholder="Search applications…" value={search} onChange={e => setSearch(e.target.value)}
            style={{ width: "100%", padding: "8px 12px 8px 32px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, boxSizing: "border-box", outline: "none" }} />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          style={{ padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, cursor: "pointer" }}>
          <option value="">All statuses</option>
          <option value="managed">Managed</option>
          <option value="unmanaged">Unmanaged</option>
          <option value="under_review">Under review</option>
          <option value="sanctioned">Sanctioned</option>
        </select>
        <select value={shadowFilter} onChange={e => setShadowFilter(e.target.value)}
          style={{ padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, cursor: "pointer" }}>
          <option value="">All sources</option>
          <option value="managed">IdP-managed</option>
          <option value="shadow">Shadow IT</option>
        </select>
      </div>

      {isLoading ? <LoadingPage /> : apps?.length === 0 ? (
        <EmptyState icon="ti-apps" title="No applications found" body="Try adjusting your filters, or import a CSV to get started." action={<button onClick={() => setShowImport(true)} style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: Z.accent, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Import CSV</button>} />
      ) : (
        <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` }}>
                {["Application", "Category", "Department", "Status", "Source", "Utilization", "Annual cost", ""].map(h => (
                  <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {apps.map((app, i) => (
                <tr key={app.id} style={{ borderBottom: i < apps.length - 1 ? `1px solid ${Z.border}` : "none" }}
                  onMouseEnter={e => e.currentTarget.style.background = "#F8FAFC"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                  <td style={{ padding: "12px 16px" }}>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: 13, color: Z.textPrimary }}>{app.name}</p>
                    <p style={{ margin: 0, fontSize: 12, color: Z.textMuted }}>{app.vendor}</p>
                  </td>
                  <td style={{ padding: "12px 16px", fontSize: 13, color: Z.textSecondary }}>{app.category}</td>
                  <td style={{ padding: "12px 16px", fontSize: 13, color: Z.textSecondary }}>{app.department ?? "—"}</td>
                  <td style={{ padding: "12px 16px" }}><Badge color={STATUS_COLOR[app.status] || "gray"}>{app.status.replace("_", " ")}</Badge></td>
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: Z.textSecondary }}>
                      <i className={`ti ${SOURCE_ICON[app.discovered_via] || "ti-dots"}`} style={{ fontSize: 14 }} aria-hidden="true" />
                      {app.discovered_via?.replace("_", " ") ?? "—"}
                    </span>
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    {app.licenses?.length > 0 && app.licenses[0].seats_purchased ? (
                      <div style={{ minWidth: 110 }}>
                        <p style={{ margin: "0 0 4px", fontSize: 11, color: Z.textMuted }}>{app.licenses[0].seats_active ?? "?"} / {app.licenses[0].seats_purchased} seats</p>
                        <ProgressBar value={app.licenses[0].seats_active ?? 0} max={app.licenses[0].seats_purchased} />
                      </div>
                    ) : <span style={{ fontSize: 12, color: Z.textMuted }}>No license</span>}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    {app.licenses?.length > 0
                      ? <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600, fontSize: 13 }}>{fmt((app.licenses[0].total_annual_cost_cents ?? 0) * 100)}</span>
                      : <span style={{ color: Z.textMuted, fontSize: 13 }}>—</span>}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    {app.status === "unmanaged" && (
                      <button onClick={() => handleStatusChange(app, "under_review")}
                        style={{ padding: "4px 10px", borderRadius: 6, border: `1px solid ${Z.border}`, background: "transparent", color: Z.accent, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
                        Review
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
