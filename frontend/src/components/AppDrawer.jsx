import { useState, useEffect } from "react";
import { api } from "../api/client";
import AppUsers from "./AppUsers";
import AppOverview from "./AppOverview";
import { AlertsTab, AppInfoTab, ContractsTab, DocumentsTab, HistoryTab, NotesDialog, PaymentsTab, SavingsTab, SentimentTab, ThresholdDialog } from "./AppTabs";

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
  if (!iso) return "No activity on record";
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
  const [licenseFilter, setLicenseFilter] = useState("all");
  const [settings, setSettings] = useState(null);          // threshold, notes, app info
  const [dialog, setDialog] = useState(null);              // "threshold" | "notes" | null
  const [usersRefresh, setUsersRefresh] = useState(0);
  const [alertCount, setAlertCount] = useState(null);

  const loadSettings = () => api.get(`/app-details/${app.id}/settings`).then(setSettings).catch(() => setSettings(null));
  useEffect(() => {
    if (!app) return;
    setSettings(null); setAlertCount(null);
    loadSettings();
    api.get(`/app-details/${app.id}/alerts`).then(a => setAlertCount(a.length)).catch(() => setAlertCount(null));
  }, [app?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Hand off to the Reclamation page with a workflow form pre-filled for this app.
  const startWorkflow = () => {
    const days = Math.min(Math.max(settings ? settings.activity_threshold_days : 60, 14), 90);
    window.dispatchEvent(new CustomEvent("tab:start-workflow", { detail: { app_id: app.id, app_name: app.name, inactivity_days: days } }));
    onClose();
  };

  useEffect(() => {
    if (!app) return;
    setUsersLoading(true);
    api.get(`/apps/${app.id}/users`)
      .then(data => {
        setUsers(data);
        // If a connector has reported license types, default to licensed users only.
        const types = new Set(data.map(u => u.role_in_app).filter(Boolean));
        setLicenseFilter(types.has("licensed") ? "licensed" : "all");
      })
      .catch(() => setUsers([]))
      .finally(() => setUsersLoading(false));
  }, [app?.id]);

  useEffect(() => {
    const onKey = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!app) return null;

  // Keep content in a centered column (max 1100px) on wide screens.
  const sidePad = "max(1.5rem, calc((100% - 1100px) / 2))";

  const license = app.licenses?.[0];

  // License types reported by a connector (Zoom: licensed / basic; Slack: full / guest ...)
  const licenseCounts = {};
  (users ?? []).forEach(u => {
    if (u.role_in_app) licenseCounts[u.role_in_app] = (licenseCounts[u.role_in_app] || 0) + 1;
  });
  const licenseTypes = Object.keys(licenseCounts).sort((a, b) =>
    a === "licensed" ? -1 : b === "licensed" ? 1 : a.localeCompare(b));
  const hasLicenseData = licenseTypes.length > 0;

  const visibleUsers = !users ? [] :
    licenseFilter === "all" ? users : users.filter(u => u.role_in_app === licenseFilter);
  const activeUsers = visibleUsers.filter(u => u.last_login_at);
  const neverLoggedIn = visibleUsers.filter(u => !u.last_login_at);

  return (
    <>
      {dialog === "threshold" && <ThresholdDialog app={app} settings={settings} onClose={() => setDialog(null)} onSaved={() => { loadSettings(); setUsersRefresh(n => n + 1); }} />}
      {dialog === "notes" && <NotesDialog app={app} settings={settings} onClose={() => setDialog(null)} onSaved={loadSettings} />}
      {/* Full-screen view */}
      <div style={{
        position: "fixed", inset: 0,
        background: Z.cardBg, zIndex: 101, overflow: "hidden",
        display: "flex", flexDirection: "column",
      }}>
        {/* Header */}
        <div style={{ padding: `1.25rem ${sidePad}`, borderBottom: `1px solid ${Z.border}`, display: "flex", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: Z.textPrimary }}>{app.name}</h2>
              <Badge color={{ managed: "green", unmanaged: "red", under_review: "amber", sanctioned: "blue" }[app.status] || "gray"}>
                {app.status?.replace("_", " ")}
              </Badge>
            </div>
            <p style={{ margin: "4px 0 0", fontSize: 13, color: Z.textSecondary }}>{app.vendor}</p>
          </div>
          <button onClick={() => setDialog("threshold")} style={{ padding: "7px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, fontSize: 13, fontWeight: 600, cursor: "pointer", color: Z.textPrimary }}>Activity Threshold</button>
          <button onClick={() => setDialog("notes")} style={{ padding: "7px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: settings && settings.notes ? Z.accentLight : Z.cardBg, fontSize: 13, fontWeight: 600, cursor: "pointer", color: settings && settings.notes ? Z.accent : Z.textPrimary }}>Notes{settings && settings.notes ? " •" : ""}</button>
          <button onClick={onClose} title="Close (Esc)" aria-label="Close" style={{ background: "none", border: "none", cursor: "pointer", color: Z.textMuted, padding: 4, borderRadius: 6, fontSize: 28, lineHeight: 1 }}>
            ×
          </button>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: `1px solid ${Z.border}`, padding: `0 ${sidePad}`, overflowX: "auto" }}>
          {[
            { id: "overview", label: "Overview" },
            { id: "info", label: "App Info" },
            { id: "history", label: "History" },
            { id: "contracts", label: "Contracts" },
            { id: "savings", label: "Savings" },
            { id: "payments", label: "Payments" },
            { id: "users", label: `Users${users ? ` (${users.length})` : ""}` },
            { id: "documents", label: "Documents" },
            { id: "sentiment", label: "Sentiment" },
            { id: "alerts", label: `Alerts${alertCount ? ` (${alertCount})` : ""}` },
            { id: "license", label: "License" },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding: "10px 0", marginRight: 20, background: "none", border: "none", whiteSpace: "nowrap",
              cursor: "pointer", fontSize: 13, fontWeight: tab === t.id ? 600 : 400,
              color: tab === t.id ? Z.accent : Z.textSecondary,
              borderBottom: `2px solid ${tab === t.id ? Z.accent : "transparent"}`,
              marginBottom: -1,
            }}>{t.label}</button>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", overscrollBehavior: "contain", padding: tab === "users" ? "1.25rem 1.5rem" : `1.5rem ${sidePad}` }}>

          {/* Overview tab */}
          {tab === "overview" && (
            <div>
              <AppOverview app={app} onJump={setTab} />
              <h3 style={{ margin: "2rem 0 10px", fontSize: 14, fontWeight: 700, color: Z.textPrimary }}>Details</h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: "1.5rem" }}>
                <StatBox label="Category" value={app.category} />
                <StatBox label="Department" value={app.department || "Unassigned"} />
                <StatBox label="Source" value={app.discovered_via?.replace("_", " ") || "—"} />
                <StatBox label="Owner" value={app.owner_email || "Unassigned"} />
              </div>

              {users && users.length > 0 && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: "1.5rem" }}>
                  <StatBox label="Assigned users" value={users.length.toLocaleString()} />
                  {licenseCounts.licensed !== undefined && (
                    <StatBox label="Licensed users" value={licenseCounts.licensed.toLocaleString()} valueColor={Z.accent} />
                  )}
                </div>
              )}

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
          {/* Users tab: activity breakdown + searchable table */}
          {tab === "users" && <AppUsers app={app} refreshKey={usersRefresh} onStartWorkflow={startWorkflow} onEditThreshold={() => setDialog("threshold")} />}
          {tab === "info" && <AppInfoTab app={app} settings={settings} onSaved={loadSettings} />}
          {tab === "history" && <HistoryTab app={app} />}
          {tab === "contracts" && <ContractsTab app={app} />}
          {tab === "savings" && <SavingsTab app={app} onStartWorkflow={startWorkflow} onJump={setTab} />}
          {tab === "payments" && <PaymentsTab app={app} />}
          {tab === "documents" && <DocumentsTab app={app} />}
          {tab === "sentiment" && <SentimentTab app={app} />}
          {tab === "alerts" && <AlertsTab app={app} onJump={setTab} onLoaded={setAlertCount} />}

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
