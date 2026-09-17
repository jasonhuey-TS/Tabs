const NAV = [
  { id: "dashboard", icon: "ti-layout-dashboard", label: "Dashboard" },
  { id: "apps", icon: "ti-apps", label: "Apps" },
  { id: "contracts", icon: "ti-file-description", label: "Contracts" },
  { id: "licenses", icon: "ti-license", label: "Licenses" },
  { id: "sync", icon: "ti-refresh", label: "Sync" },
  { id: "settings", icon: "ti-settings", label: "Settings" },
];

export default function Sidebar({ active, onNav }) {
  return (
    <aside style={{
      width: 220, minWidth: 220, background: "var(--surface-1)",
      borderRight: "0.5px solid var(--border)", display: "flex",
      flexDirection: "column", padding: "1.5rem 0"
    }}>
      <div style={{ padding: "0 1.25rem 1.5rem", borderBottom: "0.5px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, background: "var(--fill-accent)",
            display: "flex", alignItems: "center", justifyContent: "center"
          }}>
            <i className="ti ti-stack-2" style={{ fontSize: 16, color: "var(--on-accent)" }} aria-hidden="true" />
          </div>
          <div>
            <p style={{ margin: 0, fontWeight: 500, fontSize: 14 }}>Tab</p>
            <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)" }}>Enterprise</p>
          </div>
        </div>
      </div>

      <nav style={{ flex: 1, padding: "1rem 0.75rem" }}>
        {NAV.map(item => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNav(item.id)}
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: 10,
                padding: "8px 12px", borderRadius: "var(--radius)", border: "none",
                background: isActive ? "var(--fill-ghost-selected)" : "transparent",
                color: isActive ? "var(--text-accent)" : "var(--text-secondary)",
                cursor: "pointer", fontSize: 14, fontWeight: isActive ? 500 : 400,
                marginBottom: 2, transition: "background 0.1s"
              }}
            >
              <i className={`ti ${item.icon}`} style={{ fontSize: 18 }} aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
      </nav>

      <div style={{ padding: "1rem 1.25rem", borderTop: "0.5px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%", background: "var(--fill-success)"
          }} />
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Last sync 4m ago</span>
        </div>
      </div>
    </aside>
  );
}
