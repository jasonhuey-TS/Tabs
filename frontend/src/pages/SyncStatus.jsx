import { useSyncJobs, useTriggerOktaSync, useTriggerAzureSync } from "../hooks";
import { LoadingPage, ErrorBanner } from "../components/States";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", accentText: "#3730A3",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", borderStrong: "#CBD5E1", cardBg: "#FFFFFF",
  pageBg: "#F4F6FA", tableHeader: "#F8FAFC",
};

const SOURCE_ICON = { okta: "ti-shield-lock", azure_ad: "ti-brand-azure", csv: "ti-table-import" };
const SOURCE_LABEL = { okta: "Okta", azure_ad: "Azure AD", csv: "CSV import" };

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

function ConnectorCard({ source, label, schedule, onSync, isSyncing, lastJob }) {
  const isRunning = lastJob?.status === "running" || isSyncing;
  return (
    <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, padding: "1.25rem 1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: Z.accentLight, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <i className={`ti ${SOURCE_ICON[source]}`} style={{ fontSize: 20, color: Z.accent }} aria-hidden="true" />
        </div>
        <div style={{ flex: 1 }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: Z.textPrimary }}>{label}</p>
          <p style={{ margin: 0, fontSize: 12, color: Z.textMuted }}>{schedule}</p>
        </div>
        <Badge color="green">Connected</Badge>
      </div>

      {lastJob && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
          {[
            ["Apps found", lastJob.apps_discovered ?? "—"],
            ["Users synced", lastJob.users_synced?.toLocaleString() ?? "—"],
            ["New apps", lastJob.apps_created ?? "—"],
            ["Status", lastJob.status],
          ].map(([lbl, val]) => (
            <div key={lbl} style={{ background: Z.pageBg, borderRadius: 8, padding: "8px 12px", border: `1px solid ${Z.border}` }}>
              <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>{lbl}</p>
              <p style={{ margin: "3px 0 0", fontSize: 16, fontWeight: 700, color: Z.textPrimary }}>{String(val)}</p>
            </div>
          ))}
        </div>
      )}

      <button onClick={onSync} disabled={isRunning}
        style={{ width: "100%", padding: "8px", borderRadius: 8, border: `1px solid ${Z.borderStrong}`, background: isRunning ? Z.pageBg : "transparent", color: isRunning ? Z.textMuted : Z.accent, fontSize: 13, fontWeight: 600, cursor: isRunning ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
        <i className={`ti ${isRunning ? "ti-loader-2" : "ti-refresh"}`} style={{ fontSize: 15 }} aria-hidden="true" />
        {isRunning ? "Syncing…" : "Sync now"}
      </button>
    </div>
  );
}

export default function SyncStatus() {
  const { data: jobs, isLoading, error, refetch } = useSyncJobs({ limit: 20 });
  const triggerOkta = useTriggerOktaSync();
  const triggerAzure = useTriggerAzureSync();

  const lastOktaJob = jobs?.find(j => j.source === "okta");
  const lastAzureJob = jobs?.find(j => j.source === "azure_ad");

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1.75rem" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Integrations</h1>
          <p style={{ margin: "4px 0 0", fontSize: 14, color: Z.textSecondary }}>Data source connections and sync history</p>
        </div>
      </div>

      {error && <ErrorBanner error={error} onRetry={refetch} />}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "2rem" }}>
        <ConnectorCard source="okta" label="Okta" schedule="Every 6 hours" onSync={() => { triggerOkta.mutate(); refetch(); }} isSyncing={triggerOkta.isPending} lastJob={lastOktaJob} />
        <ConnectorCard source="azure_ad" label="Azure AD" schedule="Every 6 hours" onSync={() => { triggerAzure.mutate(); refetch(); }} isSyncing={triggerAzure.isPending} lastJob={lastAzureJob} />
      </div>

      <h2 style={{ fontSize: 15, fontWeight: 700, margin: "0 0 1rem", color: Z.textPrimary }}>Sync history</h2>

      {isLoading ? <LoadingPage /> : (
        <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` }}>
                {["Source", "Ran at", "Status", "Apps", "Users", "New", "Errors", "Duration"].map(h => (
                  <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(!jobs || jobs.length === 0) ? (
                <tr><td colSpan={8} style={{ padding: "3rem", textAlign: "center", color: Z.textMuted, fontSize: 14 }}>No sync jobs yet. Click "Sync now" above to start.</td></tr>
              ) : jobs.map((job, i) => (
                <tr key={job.id} style={{ borderBottom: i < jobs.length - 1 ? `1px solid ${Z.border}` : "none" }}
                  onMouseEnter={e => e.currentTarget.style.background = "#F8FAFC"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 7, fontWeight: 600, fontSize: 13 }}>
                      <i className={`ti ${SOURCE_ICON[job.source]}`} style={{ fontSize: 16, color: Z.accent }} aria-hidden="true" />
                      {SOURCE_LABEL[job.source] ?? job.source}
                    </span>
                  </td>
                  <td style={{ padding: "12px 16px", fontSize: 13, color: Z.textSecondary }}>{new Date(job.created_at).toLocaleString()}</td>
                  <td style={{ padding: "12px 16px" }}><Badge color={job.status === "completed" ? "green" : job.status === "running" ? "blue" : "red"}>{job.status}</Badge></td>
                  <td style={{ padding: "12px 16px", fontSize: 13 }}>{job.apps_discovered ?? "—"}</td>
                  <td style={{ padding: "12px 16px", fontSize: 13 }}>{job.users_synced?.toLocaleString() ?? "—"}</td>
                  <td style={{ padding: "12px 16px" }}>{job.apps_created > 0 ? <Badge color="blue">+{job.apps_created}</Badge> : <span style={{ color: Z.textMuted, fontSize: 13 }}>—</span>}</td>
                  <td style={{ padding: "12px 16px" }}>{job.errors > 0 ? <Badge color="red">{job.errors}</Badge> : <span style={{ color: Z.textMuted, fontSize: 13 }}>0</span>}</td>
                  <td style={{ padding: "12px 16px", fontSize: 13, color: Z.textSecondary }}>
                    {job.started_at && job.completed_at
                      ? `${Math.round((new Date(job.completed_at) - new Date(job.started_at)) / 1000)}s`
                      : "—"}
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
