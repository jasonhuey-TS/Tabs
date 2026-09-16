import { useState } from "react";
import {
  useOktaSettings, useAzureSettings,
  useSaveOkta, useSaveAzure,
  useTestOkta, useTestAzure,
  useToggleOkta, useToggleAzure,
} from "../hooks/useSettings";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", accentText: "#3730A3",
  navy: "#1B2A4A",
  green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C",
  amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF",
  border: "#E2E8F0", borderStrong: "#CBD5E1", cardBg: "#FFFFFF", pageBg: "#F4F6FA",
};

function Toggle({ enabled, onChange, disabled }) {
  return (
    <button
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      aria-label={enabled ? "Disable" : "Enable"}
      style={{
        width: 44, height: 24, borderRadius: 100, border: "none", cursor: disabled ? "not-allowed" : "pointer",
        background: enabled ? Z.accent : "#D1D5DB", position: "relative", transition: "background 0.2s", flexShrink: 0,
      }}>
      <span style={{
        position: "absolute", top: 2, left: enabled ? 22 : 2,
        width: 20, height: 20, borderRadius: "50%", background: "#fff",
        transition: "left 0.2s", boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
      }} />
    </button>
  );
}

function StatusPill({ ok, testedAt }) {
  if (ok === null || ok === undefined) return null;
  const label = ok ? "Connected" : "Failed";
  const color = ok ? "green" : "red";
  const map = {
    green: { bg: Z.greenLight, text: Z.greenText, border: "#BBF7D0" },
    red: { bg: Z.redLight, text: Z.redText, border: "#FECACA" },
  };
  const s = map[color];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 100, fontSize: 12, fontWeight: 600, background: s.bg, color: s.text, border: `1px solid ${s.border}` }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: ok ? Z.green : Z.red }} />
      {label}
      {testedAt && <span style={{ fontWeight: 400, opacity: 0.7 }}>· {new Date(testedAt).toLocaleTimeString()}</span>}
    </span>
  );
}

function Field({ label, hint, children }) {
  return (
    <div style={{ marginBottom: "1.25rem" }}>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: Z.textPrimary, marginBottom: 4 }}>{label}</label>
      {hint && <p style={{ margin: "0 0 6px", fontSize: 12, color: Z.textMuted }}>{hint}</p>}
      {children}
    </div>
  );
}

function Input({ value, onChange, placeholder, type = "text", monospace }) {
  return (
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        width: "100%", padding: "8px 12px", borderRadius: 8,
        border: `1px solid ${Z.border}`, background: Z.cardBg,
        color: Z.textPrimary, fontSize: 13, boxSizing: "border-box", outline: "none",
        fontFamily: monospace ? "monospace" : "inherit",
      }}
    />
  );
}

function SaveBtn({ onClick, loading, saved }) {
  return (
    <button onClick={onClick} disabled={loading}
      style={{ padding: "8px 20px", borderRadius: 8, border: "none", background: Z.accent, color: "#fff", fontSize: 13, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.7 : 1 }}>
      {loading ? "Saving…" : saved ? "Saved ✓" : "Save"}
    </button>
  );
}

function TestBtn({ onClick, loading, result }) {
  const label = loading ? "Testing…" : "Test connection";
  return (
    <button onClick={onClick} disabled={loading}
      style={{ padding: "8px 16px", borderRadius: 8, border: `1px solid ${Z.borderStrong}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.7 : 1, display: "flex", alignItems: "center", gap: 6 }}>
      <i className={`ti ${loading ? "ti-loader-2" : "ti-plug-connected"}`} style={{ fontSize: 15 }} aria-hidden="true" />
      {label}
    </button>
  );
}

// ── Okta card ──────────────────────────────────────────────────────────────
function OktaCard() {
  const { data: setting, isLoading } = useOktaSettings();
  const saveOkta = useSaveOkta();
  const testOkta = useTestOkta();
  const toggleOkta = useToggleOkta();

  const [domain, setDomain] = useState("");
  const [token, setToken] = useState("");
  const [interval, setInterval] = useState(6);
  const [saved, setSaved] = useState(false);

  // Pre-fill domain when data loads (token is never returned from API)
  const currentDomain = setting?.okta_domain ?? "";
  const isConfigured = setting?.okta_configured ?? false;
  const isEnabled = setting?.is_enabled ?? false;

  async function handleSave() {
    await saveOkta.mutateAsync({ domain: domain || currentDomain, api_token: token, sync_interval_hours: interval });
    setToken(""); // clear token field after save
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  }

  async function handleTest() {
    testOkta.mutate();
  }

  return (
    <div style={{ background: Z.cardBg, borderRadius: 12, border: `1px solid ${Z.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginBottom: "1.5rem" }}>
      {/* Header */}
      <div style={{ padding: "1.25rem 1.5rem", borderBottom: `1px solid ${Z.border}`, display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ width: 42, height: 42, borderRadius: 10, background: Z.accentLight, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <i className="ti ti-shield-lock" style={{ fontSize: 22, color: Z.accent }} aria-hidden="true" />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: Z.textPrimary }}>Okta</h2>
            {isConfigured && <StatusPill ok={setting?.last_test_ok} testedAt={setting?.last_tested_at} />}
          </div>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: Z.textSecondary }}>
            {isConfigured ? `Connected to ${currentDomain}` : "Not configured"}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 13, color: Z.textSecondary }}>{isEnabled ? "Enabled" : "Disabled"}</span>
          <Toggle enabled={isEnabled} onChange={(val) => toggleOkta.mutate({ enabled: val })} disabled={!isConfigured} />
        </div>
      </div>

      {/* Form */}
      <div style={{ padding: "1.5rem" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
          <Field label="Okta domain" hint="e.g. yourorg.okta.com">
            <Input value={domain || currentDomain} onChange={setDomain} placeholder="yourorg.okta.com" />
          </Field>
          <Field label="API token" hint={isConfigured ? "Token saved — paste a new one to replace it" : "Okta Admin → Security → API → Tokens"}>
            <Input value={token} onChange={setToken} placeholder={isConfigured ? "••••••••••••  (saved)" : "Paste API token"} type="password" monospace />
          </Field>
        </div>

        <Field label="Sync frequency">
          <select value={interval} onChange={e => setInterval(Number(e.target.value))}
            style={{ padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, cursor: "pointer" }}>
            <option value={1}>Every hour</option>
            <option value={3}>Every 3 hours</option>
            <option value={6}>Every 6 hours</option>
            <option value={12}>Every 12 hours</option>
            <option value={24}>Once a day</option>
          </select>
        </Field>

        {/* Error from last test */}
        {setting?.last_test_ok === false && setting?.last_test_error && (
          <div style={{ background: Z.redLight, border: `1px solid #FECACA`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem", fontSize: 13, color: Z.redText }}>
            <strong>Last test failed:</strong> {setting.last_test_error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10 }}>
          <SaveBtn onClick={handleSave} loading={saveOkta.isPending} saved={saved} />
          {isConfigured && <TestBtn onClick={handleTest} loading={testOkta.isPending} />}
        </div>
      </div>
    </div>
  );
}

// ── Azure AD card ──────────────────────────────────────────────────────────
function AzureCard() {
  const { data: setting } = useAzureSettings();
  const saveAzure = useSaveAzure();
  const testAzure = useTestAzure();
  const toggleAzure = useToggleAzure();

  const [tenantId, setTenantId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [interval, setInterval] = useState(6);
  const [saved, setSaved] = useState(false);

  const isConfigured = setting?.azure_configured ?? false;
  const isEnabled = setting?.is_enabled ?? false;
  const currentTenantId = setting?.azure_tenant_id ?? "";
  const currentClientId = setting?.azure_client_id ?? "";

  async function handleSave() {
    await saveAzure.mutateAsync({
      tenant_id: tenantId || currentTenantId,
      client_id: clientId || currentClientId,
      client_secret: clientSecret,
      sync_interval_hours: interval,
    });
    setClientSecret("");
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  }

  return (
    <div style={{ background: Z.cardBg, borderRadius: 12, border: `1px solid ${Z.border}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginBottom: "1.5rem" }}>
      <div style={{ padding: "1.25rem 1.5rem", borderBottom: `1px solid ${Z.border}`, display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ width: 42, height: 42, borderRadius: 10, background: Z.accentLight, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <i className="ti ti-brand-azure" style={{ fontSize: 22, color: Z.accent }} aria-hidden="true" />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: Z.textPrimary }}>Azure AD</h2>
            {isConfigured && <StatusPill ok={setting?.last_test_ok} testedAt={setting?.last_tested_at} />}
          </div>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: Z.textSecondary }}>
            {isConfigured ? `Tenant: ${currentTenantId}` : "Not configured"}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 13, color: Z.textSecondary }}>{isEnabled ? "Enabled" : "Disabled"}</span>
          <Toggle enabled={isEnabled} onChange={(val) => toggleAzure.mutate({ enabled: val })} disabled={!isConfigured} />
        </div>
      </div>

      <div style={{ padding: "1.5rem" }}>
        <div style={{ background: Z.accentLight, border: `1px solid #C7D2FE`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1.25rem", fontSize: 12, color: Z.accentText, lineHeight: 1.5 }}>
          <strong>Azure setup:</strong> Create an App Registration in Azure Portal with <strong>Application.Read.All</strong> and <strong>User.Read.All</strong> application permissions, then generate a client secret.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
          <Field label="Tenant ID">
            <Input value={tenantId || currentTenantId} onChange={setTenantId} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" monospace />
          </Field>
          <Field label="Client ID">
            <Input value={clientId || currentClientId} onChange={setClientId} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" monospace />
          </Field>
        </div>

        <Field label="Client secret" hint={isConfigured ? "Secret saved — paste a new one to replace it" : "From App Registration → Certificates & secrets"}>
          <Input value={clientSecret} onChange={setClientSecret} placeholder={isConfigured ? "••••••••••••  (saved)" : "Paste client secret"} type="password" monospace />
        </Field>

        <Field label="Sync frequency">
          <select value={interval} onChange={e => setInterval(Number(e.target.value))}
            style={{ padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, background: Z.cardBg, color: Z.textPrimary, fontSize: 13, cursor: "pointer" }}>
            <option value={1}>Every hour</option>
            <option value={3}>Every 3 hours</option>
            <option value={6}>Every 6 hours</option>
            <option value={12}>Every 12 hours</option>
            <option value={24}>Once a day</option>
          </select>
        </Field>

        {setting?.last_test_ok === false && setting?.last_test_error && (
          <div style={{ background: Z.redLight, border: `1px solid #FECACA`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem", fontSize: 13, color: Z.redText }}>
            <strong>Last test failed:</strong> {setting.last_test_error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10 }}>
          <SaveBtn onClick={handleSave} loading={saveAzure.isPending} saved={saved} />
          {isConfigured && <TestBtn onClick={() => testAzure.mutate()} loading={testAzure.isPending} />}
        </div>
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────
export default function Settings() {
  return (
    <div>
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: Z.textPrimary }}>Settings</h1>
        <p style={{ margin: "4px 0 0", fontSize: 14, color: Z.textSecondary }}>
          Configure your identity provider integrations. Credentials are encrypted before being stored.
        </p>
      </div>

      <div style={{ background: Z.amberLight, border: `1px solid #FDE68A`, borderRadius: 10, padding: "0.875rem 1.25rem", marginBottom: "2rem", display: "flex", alignItems: "flex-start", gap: 10 }}>
        <i className="ti ti-lock" style={{ fontSize: 18, color: Z.amber, flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
        <p style={{ margin: 0, fontSize: 13, color: Z.amberText, lineHeight: 1.5 }}>
          API tokens and client secrets are encrypted at rest using AES-256 before being saved to the database. They are never returned in API responses.
        </p>
      </div>

      <OktaCard />
      <AzureCard />
    </div>
  );
}
