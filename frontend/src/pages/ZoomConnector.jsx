import { useState, useEffect } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", accentText: "#3730A3",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", borderStrong: "#CBD5E1", cardBg: "#FFFFFF", pageBg: "#F4F6FA",
};

function StatusPill({ ok }) {
  if (ok === null || ok === undefined) return <span style={{ fontSize: 12, color: Z.textMuted }}>Not tested</span>;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 100, fontSize: 12, fontWeight: 600, background: ok ? Z.greenLight : Z.redLight, color: ok ? Z.greenText : Z.redText, border: `1px solid ${ok ? "#BBF7D0" : "#FECACA"}` }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: ok ? Z.green : Z.red }} />
      {ok ? "Connected" : "Failed"}
    </span>
  );
}

export default function ZoomConnector() {
  const [status, setStatus] = useState(null);
  const [accountId, setAccountId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState(null);
  const [syncResult, setSyncResult] = useState(null);

  async function load() {
    try {
      const data = await api.get("/integrations");
      const zoom = data.find(d => d.provider === "zoom") || null;
      setStatus(zoom);
      if (zoom?.meta?.account_id) setAccountId(zoom.meta.account_id);
      if (zoom?.meta?.client_id) setClientId(zoom.meta.client_id);
    } catch (e) {}
  }

  useEffect(() => { load(); }, []);

  async function handleSave() {
    if (!accountId || !clientId || !clientSecret) return;
    setSaving(true); setMessage(null);
    try {
      await api.post("/integrations/zoom", { account_id: accountId, client_id: clientId, client_secret: clientSecret });
      setClientSecret("");
      setMessage({ ok: true, text: "Credentials saved." });
      load();
    } catch (e) { setMessage({ ok: false, text: e.message }); }
    finally { setSaving(false); }
  }

  async function handleTest() {
    setTesting(true); setMessage(null);
    try {
      const r = await api.post("/integrations/zoom/test");
      setMessage({ ok: r.ok, text: r.message });
      load();
    } catch (e) { setMessage({ ok: false, text: e.message }); }
    finally { setTesting(false); }
  }

  async function handleSync() {
    setSyncing(true); setSyncResult(null);
    try {
      const r = await api.post("/integrations/zoom/sync");
      setSyncResult(r);
    } catch (e) { setSyncResult({ ok: false, message: e.message }); }
    finally { setSyncing(false); }
  }

  const canSave = accountId && clientId && clientSecret && !saving;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: "2rem" }}>
        <div style={{ width: 52, height: 52, borderRadius: 14, background: "#2D8CFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <i className="ti ti-video" style={{ fontSize: 26, color: "#fff" }} aria-hidden="true" />
        </div>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Zoom</h1>
            <StatusPill ok={status?.last_test_ok} />
          </div>
          <p style={{ margin: "3px 0 0", fontSize: 14, color: Z.textSecondary }}>Sync last meeting dates and license types for Zoom users</p>
        </div>
      </div>

      {/* What you get */}
      <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, padding: "1.25rem 1.5rem", marginBottom: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
        <h3 style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 700, color: Z.textPrimary }}>What this connector adds</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {[
            ["Last login date", "When each user last signed into Zoom"],
            ["License type", "Licensed, Basic, or On-Prem"],
            ["User status", "Active or inactive account"],
            ["Department", "User's department from Zoom profile"],
          ].map(([title, desc]) => (
            <div key={title} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <div style={{ width: 20, height: 20, borderRadius: "50%", background: Z.greenLight, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>
                <i className="ti ti-check" style={{ fontSize: 11, color: Z.green }} />
              </div>
              <div>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: Z.textPrimary }}>{title}</p>
                <p style={{ margin: 0, fontSize: 12, color: Z.textMuted }}>{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Config */}
      <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, padding: "1.25rem 1.5rem", marginBottom: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 700, color: Z.textPrimary }}>Configuration</h3>

        <div style={{ background: Z.accentLight, border: `1px solid #C7D2FE`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1.25rem", fontSize: 12, color: Z.accentText, lineHeight: 1.7 }}>
          <strong>How to get Server-to-Server OAuth credentials:</strong><br />
          1. Go to <strong>marketplace.zoom.us</strong> → Develop → Build App → Server-to-Server OAuth<br />
          2. Add scopes: <code>user:read:admin</code>, <code>user:read:list_users:admin</code><br />
          3. Activate the app → copy <strong>Account ID</strong>, <strong>Client ID</strong>, and <strong>Client Secret</strong>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: Z.textPrimary, marginBottom: 4 }}>Account ID</label>
            <input value={accountId} onChange={e => setAccountId(e.target.value)} placeholder="Your Zoom Account ID"
              style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, boxSizing: "border-box", outline: "none" }} />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: Z.textPrimary, marginBottom: 4 }}>Client ID</label>
            <input value={clientId} onChange={e => setClientId(e.target.value)} placeholder="OAuth Client ID"
              style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, boxSizing: "border-box", outline: "none" }} />
          </div>
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: Z.textPrimary, marginBottom: 4 }}>Client Secret</label>
          <p style={{ margin: "0 0 6px", fontSize: 12, color: Z.textMuted }}>
            {status?.is_configured ? "Secret saved — paste a new one to replace" : "From your Server-to-Server OAuth app"}
          </p>
          <input type="password" value={clientSecret} onChange={e => setClientSecret(e.target.value)}
            placeholder={status?.is_configured ? "•••••••••  (saved)" : "Paste client secret"}
            style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, boxSizing: "border-box", outline: "none", fontFamily: "monospace" }} />
        </div>

        {message && (
          <div style={{ background: message.ok ? Z.greenLight : Z.redLight, border: `1px solid ${message.ok ? "#BBF7D0" : "#FECACA"}`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem", fontSize: 13, color: message.ok ? Z.greenText : Z.redText }}>
            {message.text}
          </div>
        )}

        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={handleSave} disabled={!canSave}
            style={{ padding: "8px 20px", borderRadius: 8, border: "none", background: canSave ? Z.accent : "#A5B4FC", color: "#fff", fontSize: 13, fontWeight: 600, cursor: canSave ? "pointer" : "not-allowed" }}>
            {saving ? "Saving…" : "Save"}
          </button>
          {status?.is_configured && (
            <button onClick={handleTest} disabled={testing}
              style={{ padding: "8px 16px", borderRadius: 8, border: `1px solid ${Z.borderStrong}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, fontWeight: 600, cursor: testing ? "not-allowed" : "pointer" }}>
              {testing ? "Testing…" : "Test connection"}
            </button>
          )}
        </div>
      </div>

      {status?.is_configured && (
        <div style={{ background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`, padding: "1.25rem 1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <h3 style={{ margin: "0 0 6px", fontSize: 14, fontWeight: 700, color: Z.textPrimary }}>Sync data</h3>
          <p style={{ margin: "0 0 14px", fontSize: 13, color: Z.textSecondary }}>Pull latest user data from Zoom and update the app drawer.</p>

          {syncResult && (
            <div style={{ background: syncResult.ok ? Z.greenLight : Z.redLight, border: `1px solid ${syncResult.ok ? "#BBF7D0" : "#FECACA"}`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem", fontSize: 13, color: syncResult.ok ? Z.greenText : Z.redText }}>
              {syncResult.message}
            </div>
          )}

          <button onClick={handleSync} disabled={syncing}
            style={{ padding: "8px 20px", borderRadius: 8, border: "none", background: syncing ? "#A5B4FC" : Z.accent, color: "#fff", fontSize: 13, fontWeight: 600, cursor: syncing ? "not-allowed" : "pointer", display: "flex", alignItems: "center", gap: 6 }}>
            <i className={`ti ${syncing ? "ti-loader-2" : "ti-refresh"}`} style={{ fontSize: 15 }} />
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        </div>
      )}
    </div>
  );
}
