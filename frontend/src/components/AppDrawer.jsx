import { useState, useEffect } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", accentText: "#3730A3",
  navy: "#1B2A4A",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  orange: "#F97316", orangeLight: "#FFF7ED", orangeText: "#C2410C",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", cardBg: "#FFFFFF", pageBg: "#F4F6FA", tableHeader: "#F8FAFC",
};

function Badge({ children, color = "gray" }) {
  const map = {
    green: { bg: Z.greenLight, color: Z.greenText, border: "#BBF7D0" },
    red: { bg: Z.redLight, color: Z.redText, border: "#FECACA" },
    amber: { bg: Z.amberLight, color: Z.amberText, border: "#FDE68A" },
    blue: { bg: Z.accentLight, color: Z.accentText, border: "#C7D2FE" },
    gray: { bg: "#F9FAFB", color: Z.textSecondary, border: Z.border },
  };
  const s = map[color] || map.gray;
  return <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 100, fontSize: 11, fontWeight: 600, background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{children}</span>;
}

function StatBox({ label, value, valueColor }) {
  return (
    <div style={{ background: Z.pageBg, borderRadius: 8, padding: "12px 16px", border: `1px solid ${Z.border}` }}>
      <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>
      <p style={{ margin: "4px 0 0", fontSize: 20, fontWeight: 700, color: valueColor || Z.textPrimary, fontVariantNumeric: "tabular-nums" }}>{value ?? "—"}</p>
    </div>
  );
}

function ProgressBar({ value, max }) {
  const pct = max > 0 ? Math.round(Math.min(100, (value / max) * 100)) : 0;
  const color = pct < 50 ? Z.red : pct < 75 ? Z.amber : Z.green;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "#E2E8F0", borderRadius: 100, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 100 }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 600, color: Z.textSecondary, minWidth: 36 }}>{pct}%</span>
    </div>
  );
}

function fmtDate(iso) {
  if (!iso) return "Never";
  const d = new Date(iso);
  const daysAgo = Math.floor((Date.now() - d) / 86400000);
  if (daysAgo === 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  if (daysAgo < 30) return `${daysAgo}d ago`;
  if (daysAgo < 365) return `${Math.floor(daysAgo / 30)}mo ago`;
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function fmt(cents) {
  if (!cents) return "—";
  return "$" + (cents / 100).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export default function AppDrawer({ app, onClose }) {
  const [users, setUsers] = useState(null);
  const [usersLoading, setUsersLoading] = useState(true);
  const [tab, setTab] = useState("overview");

  useEffect(() => {
    if (!app) return;
    setUsersLoading(true);
    api.get(`/apps/${app.id}/users`)
      .then(data => setUsers(data))
      .catch(() => setUsers([]))
      .finally(() => setUsersLoading(false));
  }, [app?.id]);

  if (!app) return null;

  const license = app.licenses?.[0];
  const activeUsers = users?.filter(u => u.last_login_at) ?? [];
  const neverLoggedIn = users?.filter(u => !u.last_login_at) ?? [];

  return (
    <>
      {/* Backdrop */}
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.3)", zIndex: 100 }} />

      {/* Drawer */}
      <div style={{
        position: "fixed", right: 0, top: 0, bottom: 0, width: 560, maxWidth: "90vw",
        background: Z.cardBg, zIndex: 101, overflow: "hidden",
        display: "flex", flexDirection: "column",
        boxShadow: "-4px 0 24px rgba(0,0,0,0.12)",
      }}>
        {/* Header */}
        <div style={{ padding: "1.25rem 1.5rem", borderBottom: `1px solid ${Z.border}`, display: "flex", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: Z.textPrimary }}>{app.name}</h2>
              <Badge color={{ managed: "green", unmanaged: "red", under_review: "amber", sanctioned: "blue" }[app.status] || "gray"}>
                {app.status?.replace("_", " ")}
              </Badge>
            </div>
            <p style={{ margin: "4px 0 0", fontSize: 13, color: Z.textSecondary }}>{app.vendor}</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: Z.textMuted, padding: 4, borderRadius: 6, fontSize: 20, lineHeight: 1 }}>
            ×
          </button>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: `1px solid ${Z.border}`, padding: "0 1.5rem" }}>
          {[
            { id: "overview", label: "Overview" },
            { id: "users", label: `Users${users ? ` (${users.length})` : ""}` },
            { id: "license", label: "License" },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding: "10px 0", marginRight: 24, background: "none", border: "none",
              cursor: "pointer", fontSize: 13, fontWeight: tab === t.id ? 600 : 400,
              color: tab === t.id ? Z.accent : Z.textSecondary,
              borderBottom: `2px solid ${tab === t.id ? Z.accent : "transparent"}`,
              marginBottom: -1,
            }}>{t.label}</button>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1.5rem" }}>

          {/* Overview tab */}
          {tab === "overview" && (
            <div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: "1.5rem" }}>
                <StatBox label="Category" value={app.category} />
                <StatBox label="Department" value={app.department || "Unassigned"} />
                <StatBox label="Source" value={app.discovered_via?.replace("_", " ") || "—"} />
                <StatBox label="Owner" value={app.owner_email || "Unassigned"} />
              </div>

              {license && (
                <>
                  <h3 style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 700, color: Z.textPrimary }}>License summary</h3>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: "1rem" }}>
                    <StatBox label="Seats purchased" value={license.seats_purchased?.toLocaleString()} />
                    <StatBox label="Active seats" value={license.seats_active?.toLocaleString()} valueColor={Z.green} />
                    <StatBox label="Annual cost" value={fmt(license.total_annual_cost_cents)} />
                    <StatBox label="Wasted spend" value={fmt(license.waste_cost_cents)} valueColor={license.waste_cost_cents > 0 ? Z.red : undefined} />
                  </div>
                  {license.seats_purchased > 0 && (
                    <div style={{ background: Z.pageBg, borderRadius: 8, padding: "12px 16px", border: `1px solid ${Z.border}` }}>
                      <p style={{ margin: "0 0 8px", fontSize: 12, color: Z.textSecondary }}>Utilization</p>
                      <ProgressBar value={license.seats_active ?? 0} max={license.seats_purchased} />
                    </div>
                  )}
                </>
              )}

              {!license && (
                <div style={{ background: Z.pageBg, borderRadius: 8, padding: "1rem", border: `1px solid ${Z.border}`, textAlign: "center", color: Z.textMuted, fontSize: 13 }}>
                  No license data — import a CSV to add license information
                </div>
              )}
            </div>
          )}

          {/* Users tab */}
          {tab === "users" && (
            <div>
              {usersLoading ? (
                <div style={{ textAlign: "center", padding: "3rem", color: Z.textMuted }}>Loading users…</div>
              ) : users?.length === 0 ? (
                <div style={{ textAlign: "center", padding: "3rem", color: Z.textMuted, fontSize: 13 }}>
                  No users assigned to this app yet. Users are synced from Okta/Azure AD.
                </div>
              ) : (
                <>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: "1.25rem" }}>
                    <StatBox label="Total assigned" value={users.length} />
                    <StatBox label="Active (have logged in)" value={activeUsers.length} valueColor={Z.green} />
                    <StatBox label="Never logged in" value={neverLoggedIn.length} valueColor={neverLoggedIn.length > 0 ? Z.red : undefined} />
                  </div>

                  <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, overflow: "hidden" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` }}>
                          {["User", "Last login", "Status"].map(h => (
                            <th key={h} style={{ padding: "8px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {users.map((u, i) => (
                          <tr key={u.id} style={{ borderBottom: i < users.length - 1 ? `1px solid ${Z.border}` : "none" }}>
                            <td style={{ padding: "10px 14px" }}>
                              <p style={{ margin: 0, fontSize: 13, fontWeight: 500, color: Z.textPrimary }}>{u.full_name || u.email}</p>
                              {u.full_name && <p style={{ margin: 0, fontSize: 11, color: Z.textMuted }}>{u.email}</p>}
                            </td>
                            <td style={{ padding: "10px 14px" }}>
                              <span style={{
                                fontSize: 13,
                                color: !u.last_login_at ? Z.red : Z.textSecondary,
                                fontWeight: !u.last_login_at ? 600 : 400,
                              }}>
                                {fmtDate(u.last_login_at)}
                              </span>
                            </td>
                            <td style={{ padding: "10px 14px" }}>
                              <Badge color={u.last_login_at ? "green" : "red"}>
                                {u.last_login_at ? "Active" : "Idle"}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}

          {/* License tab */}
          {tab === "license" && (
            <div>
              {!license ? (
                <div style={{ textAlign: "center", padding: "3rem", color: Z.textMuted, fontSize: 13 }}>
                  No license data. Import a licenses CSV to add cost and seat information.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {[
                    ["License type", license.license_type?.replace("_", " ")],
                    ["Seats purchased", license.seats_purchased?.toLocaleString()],
                    ["Seats assigned", license.seats_assigned?.toLocaleString()],
                    ["Seats active (30d)", license.seats_active?.toLocaleString()],
                    ["Idle seats", ((license.seats_purchased ?? 0) - (license.seats_active ?? 0)).toLocaleString()],
                    ["Cost per seat", license.cost_per_seat_cents ? fmt(license.cost_per_seat_cents) + "/mo" : null],
                    ["Annual cost", fmt(license.total_annual_cost_cents)],
                    ["Annual waste", fmt(license.waste_cost_cents)],
                    ["Billing cycle", license.billing_cycle],
                    ["Next billing date", license.next_billing_date],
                  ].map(([label, value]) => (
                    <div key={label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", background: Z.pageBg, borderRadius: 8, border: `1px solid ${Z.border}` }}>
                      <span style={{ fontSize: 13, color: Z.textSecondary }}>{label}</span>
                      <span style={{ fontSize: 13, fontWeight: 600, color: Z.textPrimary }}>{value ?? "—"}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
