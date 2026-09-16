const Z = {
  border: "#E2E8F0",
  textMuted: "#9CA3AF",
  textSecondary: "#6B7280",
  red: "#DC2626",
  redLight: "#FEF2F2",
  redText: "#B91C1C",
  cardBg: "#FFFFFF",
};

export function Spinner({ size = 24 }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%",
      border: `2px solid #E2E8F0`,
      borderTopColor: "#4B5EDE",
      animation: "spin 0.7s linear infinite",
      display: "inline-block",
    }} />
  );
}

export function LoadingPage() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh", flexDirection: "column", gap: 16 }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
      <Spinner size={32} />
      <p style={{ margin: 0, fontSize: 14, color: Z.textMuted }}>Loading…</p>
    </div>
  );
}

export function ErrorBanner({ error, onRetry }) {
  const message = error?.detail ?? error?.message ?? "Something went wrong. Please try again.";
  return (
    <div style={{
      background: Z.redLight, border: `1px solid #FECACA`, borderRadius: 10,
      padding: "0.875rem 1.25rem", marginBottom: "1.5rem",
      display: "flex", alignItems: "flex-start", gap: 10,
    }}>
      <i className="ti ti-alert-circle" style={{ fontSize: 18, color: Z.red, flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
      <div style={{ flex: 1 }}>
        <p style={{ margin: 0, fontSize: 13, color: Z.redText, fontWeight: 600 }}>Failed to load data</p>
        <p style={{ margin: "2px 0 0", fontSize: 12, color: Z.redText }}>{message}</p>
      </div>
      {onRetry && (
        <button onClick={onRetry} style={{
          padding: "4px 10px", borderRadius: 6, border: `1px solid #FECACA`,
          background: "transparent", color: Z.redText, fontSize: 12, fontWeight: 600, cursor: "pointer",
        }}>Retry</button>
      )}
    </div>
  );
}

export function EmptyState({ icon = "ti-inbox", title, body, action }) {
  return (
    <div style={{
      background: Z.cardBg, borderRadius: 10, border: `1px solid ${Z.border}`,
      padding: "4rem 2rem", textAlign: "center",
    }}>
      <i className={`ti ${icon}`} style={{ fontSize: 36, color: Z.textMuted }} aria-hidden="true" />
      <p style={{ margin: "1rem 0 0.25rem", fontSize: 15, fontWeight: 600, color: "#374151" }}>{title}</p>
      {body && <p style={{ margin: 0, fontSize: 13, color: Z.textSecondary, maxWidth: 320, marginInline: "auto" }}>{body}</p>}
      {action && <div style={{ marginTop: "1.25rem" }}>{action}</div>}
    </div>
  );
}

/** Skeleton shimmer bar — drop in where a value is loading */
export function Skeleton({ width = "100%", height = 16, radius = 4 }) {
  return (
    <div style={{
      width, height, borderRadius: radius,
      background: "linear-gradient(90deg, #F1F5F9 25%, #E2E8F0 50%, #F1F5F9 75%)",
      backgroundSize: "200% 100%",
      animation: "shimmer 1.2s infinite",
      display: "inline-block",
    }}>
      <style>{`@keyframes shimmer { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }`}</style>
    </div>
  );
}
