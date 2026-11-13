const Z = {
  navy: "#1B2A4A",
  navyHover: "#243761",
  navyActive: "#2E4785",
  navyText: "#A8B8D8",
  navyTextActive: "#FFFFFF",
  navyBorder: "rgba(255,255,255,0.08)",
  accent: "#4B5EDE",
};

const NAV = [
  { id: "dashboard", icon: "ti-layout-dashboard", label: "Analytics" },
  { id: "assistant", icon: "ti-sparkles", label: "Ask Tab" },
  { id: "reclamation", icon: "ti-recycle", label: "Reclamation" },
  { id: "apps", icon: "ti-apps", label: "Applications" },
  { id: "categories", icon: "ti-tags", label: "Categories" },
  { id: "zylo", icon: "ti-refresh", label: "Zylo Sync" },
  { id: "shadow", icon: "ti-eye", label: "Shadow IT" },
  { id: "contracts", icon: "ti-calendar-event", label: "Renewals" },
  { id: "licenses", icon: "ti-license", label: "Licenses" },
  { id: "payments", icon: "ti-currency-dollar", label: "Payments" },
  { id: "sync", icon: "ti-refresh", label: "Sync" },
  { id: "settings", icon: "ti-settings", label: "Settings" },
];

const CONNECTORS = [
  { id: "integration-library", icon: "ti-plug-connected", label: "Integration Library", color: "#4B5EDE" },
];

function NavBtn({ item, isActive, onClick }) {
  return (
    <button
      onClick={() => onClick(item.id)}
      style={{
        width: "100%", display: "flex", alignItems: "center", gap: 10,
        padding: "8px 12px", borderRadius: 8, border: "none",
        background: isActive ? Z.navyActive : "transparent",
        color: isActive ? Z.navyTextActive : Z.navyText,
        cursor: "pointer", fontSize: 13, fontWeight: isActive ? 600 : 400,
        marginBottom: 2, textAlign: "left", transition: "background 0.1s, color 0.1s",
      }}
      onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = Z.navyHover; e.currentTarget.style.color = "#fff"; } }}
      onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = Z.navyText; } }}
    >
      <i className={`ti ${item.icon}`} style={{ fontSize: 17, flexShrink: 0 }} aria-hidden="true" />
      {item.label}
    </button>
  );
}

export default function Sidebar({ active, onNav }) {
  return (
    <aside style={{ width: 228, minWidth: 228, background: Z.navy, display: "flex", flexDirection: "column" }}>
      {/* Logo */}
      <div style={{ padding: "1.25rem 1.5rem 1rem", borderBottom: `1px solid ${Z.navyBorder}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: Z.accent, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <i className="ti ti-stack-2" style={{ fontSize: 16, color: "#fff" }} aria-hidden="true" />
          </div>
          <div>
            <p style={{ margin: 0, fontWeight: 700, fontSize: 14, color: "#FFFFFF" }}>Tab</p>
            <p style={{ margin: 0, fontSize: 11, color: Z.navyText }}>Enterprise</p>
          </div>
        </div>
      </div>

      {/* Main nav */}
      <nav style={{ padding: "0.75rem" }}>
        <p style={{ margin: "0.5rem 0.5rem 0.4rem", fontSize: 10, fontWeight: 700, color: "rgba(168,184,216,0.5)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
          Main menu
        </p>
        {NAV.map(item => (
          <NavBtn key={item.id} item={item} isActive={active === item.id} onClick={onNav} />
        ))}
      </nav>

      {/* Divider */}
      <div style={{ margin: "0 0.75rem", borderTop: `1px solid ${Z.navyBorder}` }} />

      {/* Connectors section */}
      <nav style={{ padding: "0.75rem", flex: 1 }}>
        <p style={{ margin: "0.5rem 0.5rem 0.4rem", fontSize: 10, fontWeight: 700, color: "rgba(168,184,216,0.5)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
          Connectors
        </p>
        {CONNECTORS.map(item => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNav(item.id)}
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: 10,
                padding: "8px 12px", borderRadius: 8, border: "none",
                background: isActive ? Z.navyActive : "transparent",
                color: isActive ? Z.navyTextActive : Z.navyText,
                cursor: "pointer", fontSize: 13, fontWeight: isActive ? 600 : 400,
                marginBottom: 2, textAlign: "left", transition: "background 0.1s, color 0.1s",
              }}
              onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = Z.navyHover; e.currentTarget.style.color = "#fff"; } }}
              onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = Z.navyText; } }}
            >
              <div style={{ width: 20, height: 20, borderRadius: 5, background: item.color, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <i className={`ti ${item.icon}`} style={{ fontSize: 12, color: "#fff" }} aria-hidden="true" />
              </div>
              {item.label}
              {/* Show connected dot if configured */}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div style={{ padding: "0.875rem 1.25rem", borderTop: `1px solid ${Z.navyBorder}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 28, height: 28, borderRadius: "50%", background: "rgba(255,255,255,0.1)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <i className="ti ti-user" style={{ fontSize: 14, color: Z.navyText }} aria-hidden="true" />
          </div>
          <div style={{ flex: 1, overflow: "hidden" }}>
            <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: "#FFFFFF" }}>IT Admin</p>
            <p style={{ margin: 0, fontSize: 11, color: Z.navyText }}>admin@company.com</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
