import { useState, useEffect } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", accentText: "#3730A3",
  navy: "#1B2A4A",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", borderStrong: "#CBD5E1", cardBg: "#FFFFFF", pageBg: "#F4F6FA",
};

function Field({ label, hint, children }) {
  return (
    <div style={{ marginBottom: "1rem" }}>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: Z.textPrimary, marginBottom: 4 }}>{label}</label>
      {hint && <p style={{ margin: "0 0 5px", fontSize: 12, color: Z.textMuted }}>{hint}</p>}
      {children}
    </div>
  );
}

function Input({ value, onChange, placeholder, type = "text" }) {
  return (
    <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, boxSizing: "border-box", outline: "none", fontFamily: type === "password" ? "monospace" : "inherit" }} />
  );
}

function StatusPill({ ok, label }) {
  const color = ok === true ? "green" : ok === false ? "red" : "gray";
  const map = {
    green: { bg: Z.greenLight, text: Z.greenText, dot: Z.green, border: "#BBF7D0" },
    red: { bg: Z.redLight, text: Z.redText, dot: Z.red, border: "#FECACA" },
    gray: { bg: "#F9FAFB", text: Z.textMuted, dot: Z.textMuted, border: Z.border },
  };
  const s = map[color];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 100, fontSize: 12, fontWeight: 600, background: s.bg, color: s.text, border: `1px solid ${s.border}` }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.dot }} />
      {label}
    </span>
  );
}

// ── Slack Card ─────────────────────────────────────────────────────────────
function SlackCard({ status, onRefresh }) {
  const [token, setToken] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState(null);

  async function handleSave() {
    if (!token) return;
    setSaving(true);
    try {
      await api.post("/integrations/slack", { bot_token: token });
      setToken("");
      setMessage({ ok: true, text: "Credentials saved." });
      onRefresh();
    } catch (e) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setMessage(null);
    try {
      const r = await api.post("/integrations/slack/test");
      setMessage({ ok: r.ok, text: r.message });
      onRefresh();
    } catch (e) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setTesting(false);
    }
  }

  async function handleSync() {
    setSyncing(true);
    setMessage(null);
    try {
      const r = await api.post("/integrations/slack/sync");
      setMessage({ ok: r.ok, text: r.message });
    } catch (e) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div style={{ background: Z.cardBg, borderRadius: 12, border: `1px solid ${Z.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginBottom: "1.5rem" }}>
      {/* Header */}
      <div style={{ padding: "1.25rem 1.5rem", borderBottom: `1px solid ${Z.border}`, display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: "#4A154B", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <span style={{ fontSize: 24 }}>💬</span>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: Z.textPrimary }}>Slack</h2>
            <StatusPill ok={status?.last_test_ok} label={status?.is_configured ? (status?.last_test_ok ? "Connected" : "Configured") : "Not configured"} />
          </div>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: Z.textSecondary }}>Last active dates · license type per user</p>
        </div>
        {status?.is_configured && (
          <button onClick={handleSync} disabled={syncing}
            style={{ padding: "7px 14px", borderRadius: 8, border: `1px solid ${Z.border}`, background: syncing ? Z.pageBg : Z.cardBg, color: syncing ? Z.textMuted : Z.accent, fontSize: 13, fontWeight: 600, cursor: syncing ? "not-allowed" : "pointer" }}>
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        )}
      </div>

      <div style={{ padding: "1.5rem" }}>
        {/* Setup instructions */}
        <div style={{ background: Z.accentLight, border: `1px solid #C7D2FE`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1.25rem", fontSize: 12, color: Z.accentText, lineHeight: 1.6 }}>
          <strong>Setup:</strong> In Slack, go to <strong>api.slack.com/apps</strong> → Create App → OAuth & Permissions → add scopes: <code>users:read</code>, <code>users:read.email</code>, <code>users.profile:read</code> → Install to workspace → copy the Bot User OAuth Token.
        </div>

        <Field label="Bot User OAuth Token" hint={status?.is_configured ? "Token saved — paste a new one to replace" : "Starts with xoxb-"}>
          <Input value={token} onChange={setToken} placeholder={status?.is_configured ? "••••  (saved)" : "xoxb-..."} type="password" />
        </Field>

        {message && (
          <div style={{ background: message.ok ? Z.greenLight : Z.redLight, border: `1px solid ${message.ok ? "#BBF7D0" : "#FECACA"}`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem", fontSize: 13, color: message.ok ? Z.greenText : Z.redText }}>
            {message.text}
          </div>
        )}

        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={handleSave} disabled={!token || saving}
            style={{ padding: "8px 20px", borderRadius: 8, border: "none", background: token && !saving ? Z.accent : "#A5B4FC", color: "#fff", fontSize: 13, fontWeight: 600, cursor: token && !saving ? "pointer" : "not-allowed" }}>
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
    </div>
  );
}

// ── Zoom Card ──────────────────────────────────────────────────────────────
function ZoomCard({ status, onRefresh }) {
  const [accountId, setAccountId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState(null);

  async function handleSave() {
    if (!accountId || !clientId || !clientSecret) return;
    setSaving(true);
    try {
      await api.post("/integrations/zoom", { account_id: accountId, client_id: clientId, client_secret: clientSecret });
      setClientSecret("");
      setMessage({ ok: true, text: "Credentials saved." });
      onRefresh();
    } catch (e) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setMessage(null);
    try {
      const r = await api.post("/integrations/zoom/test");
      setMessage({ ok: r.ok, text: r.message });
      onRefresh();
    } catch (e) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setTesting(false);
    }
  }

  async function handleSync() {
    setSyncing(true);
    setMessage(null);
    try {
      const r = await api.post("/integrations/zoom/sync");
      setMessage({ ok: r.ok, text: r.message });
    } catch (e) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setSyncing(false);
    }
  }

  const isConfigured = status?.is_configured;

  return (
    <div style={{ background: Z.cardBg, borderRadius: 12, border: `1px solid ${Z.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginBottom: "1.5rem" }}>
      <div style={{ padding: "1.25rem 1.5rem", borderBottom: `1px solid ${Z.border}`, display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: "#2D8CFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <span style={{ fontSize: 24 }}>📹</span>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: Z.textPrimary }}>Zoom</h2>
            <StatusPill ok={status?.last_test_ok} label={isConfigured ? (status?.last_test_ok ? "Connected" : "Configured") : "Not configured"} />
          </div>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: Z.textSecondary }}>Last meeting date · license type per user</p>
        </div>
        {isConfigured && (
          <button onClick={handleSync} disabled={syncing}
            style={{ padding: "7px 14px", borderRadius: 8, border: `1px solid ${Z.border}`, background: syncing ? Z.pageBg : Z.cardBg, color: syncing ? Z.textMuted : Z.accent, fontSize: 13, fontWeight: 600, cursor: syncing ? "not-allowed" : "pointer" }}>
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        )}
      </div>

      <div style={{ padding: "1.5rem" }}>
        <div style={{ background: Z.accentLight, border: `1px solid #C7D2FE`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1.25rem", fontSize: 12, color: Z.accentText, lineHeight: 1.6 }}>
          <strong>Setup:</strong> In Zoom Marketplace, create a <strong>Server-to-Server OAuth</strong> app → add scopes: <code>user:read:admin</code>, <code>user:read:list_users:admin</code> → Activate → copy Account ID, Client ID, and Client Secret.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <Field label="Account ID">
            <Input value={accountId || status?.meta?.account_id || ""} onChange={setAccountId} placeholder="Your Zoom Account ID" />
          </Field>
          <Field label="Client ID">
            <Input value={clientId || status?.meta?.client_id || ""} onChange={setClientId} placeholder="Your OAuth Client ID" />
          </Field>
        </div>

        <Field label="Client Secret" hint={isConfigured ? "Secret saved — paste a new one to replace" : "From your Server-to-Server OAuth app"}>
          <Input value={clientSecret} onChange={setClientSecret} placeholder={isConfigured ? "••••  (saved)" : "Paste client secret"} type="password" />
        </Field>

        {message && (
          <div style={{ background: message.ok ? Z.greenLight : Z.redLight, border: `1px solid ${message.ok ? "#BBF7D0" : "#FECACA"}`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem", fontSize: 13, color: message.ok ? Z.greenText : Z.redText }}>
            {message.text}
          </div>
        )}

        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={handleSave} disabled={!accountId || !clientId || !clientSecret || saving}
            style={{ padding: "8px 20px", borderRadius: 8, border: "none", background: accountId && clientId && clientSecret && !saving ? Z.accent : "#A5B4FC", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            {saving ? "Saving…" : "Save"}
          </button>
          {isConfigured && (
            <button onClick={handleTest} disabled={testing}
              style={{ padding: "8px 16px", borderRadius: 8, border: `1px solid ${Z.borderStrong}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, fontWeight: 600, cursor: testing ? "not-allowed" : "pointer" }}>
              {testing ? "Testing…" : "Test connection"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────
export default function IntegrationLibrary() {
  const [statuses, setStatuses] = useState({});
  const [loading, setLoading] = useState(true);

  async function loadStatuses() {
    try {
      const data = await api.get("/integrations");
      const map = {};
      data.forEach(s => { map[s.provider] = s; });
      setStatuses(map);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadStatuses(); }, []);

  return (
    <div>
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Integration Library</h1>
        <p style={{ margin: "4px 0 0", fontSize: 14, color: Z.textSecondary }}>
          Connect apps directly to get richer usage data — last active dates, license types, and more.
        </p>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem", color: Z.textMuted }}>Loading…</div>
      ) : (
        <>
          <SlackCard status={statuses.slack} onRefresh={loadStatuses} />
          <ZoomCard status={statuses.zoom} onRefresh={loadStatuses} />
        </>
      )}
    </div>
  );
}
