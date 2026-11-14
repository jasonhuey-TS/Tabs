import { useState } from "react";

const Z = {
  navy: "#1B2A4A", navyHover: "#243761", navyActive: "#2E4785", navyText: "#A8B8D8", navyTextActive: "#FFFFFF",
  navyBorder: "rgba(255,255,255,0.08)", navyLabel: "rgba(168,184,216,0.55)", accent: "#4B5EDE",
};
const STORE_KEY = "tab.nav.collapsed";

// Icons are drawn here, not loaded from an icon font, so they appear even where a network or security policy blocks outside fonts.
const I = {
  dashboard: <><path d="M5 20v-8M12 20V5M19 20v-5" /></>,
  assistant: <><path d="M12 3l2.2 6.3L21 12l-6.8 2.7L12 21l-2.2-6.3L3 12l6.8-2.7z" /></>,
  health: <><path d="M3 12h4l2.5-6 4 12 2.5-6H21" /></>,
  reclamation: <><path d="M9 14L4 9l5-5" /><path d="M4 9h9a6 6 0 0 1 0 12h-3" /></>,
  contracts: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></>,
  licenses: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 14l2 2 4-4" /></>,
  payments: <><circle cx="12" cy="12" r="9" /><path d="M12 7v10M14.5 9.6c0-1-1.1-1.7-2.5-1.7s-2.5.7-2.5 1.7 1.1 1.4 2.5 1.8 2.5.8 2.5 1.8-1.1 1.8-2.5 1.8-2.5-.8-2.5-1.7" /></>,
  apps: <><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></>,
  categories: <><path d="M3 3h8l10 10-8 8L3 11z" /><circle cx="7.5" cy="7.5" r="1.2" /></>,
  shadow: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>,
  library: <><path d="M9 3v4M15 3v4M7 7h10v4a5 5 0 0 1-10 0zM12 16v5" /></>,
  zylo: <><path d="M7 7h13l-3-3M17 17H4l3 3" /></>,
  sync: <><path d="M20 11a8 8 0 0 0-14.9-3M4 5v3.5h3.5M4 13a8 8 0 0 0 14.9 3M20 19v-3.5h-3.5" /></>,
  settings: <><path d="M4 6h8M16 6h4M4 12h3M11 12h9M4 18h11M19 18h1" /><circle cx="14" cy="6" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="17" cy="18" r="2" /></>,
  logo: <><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></>,
  user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></>,
  chevron: <><path d="M9 6l6 6-6 6" /></>,
};
const Icon = ({ name, size = 17 }) => (
  <svg data-icon={name} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}>{I[name]}</svg>
);

// What each page is for, so related pages sit together.
export const GROUPS = [
  { id: "overview", label: "Overview", items: [{ id: "dashboard", icon: "dashboard", label: "Analytics" }, { id: "assistant", icon: "assistant", label: "Ask Tab" }, { id: "health", icon: "health", label: "Data Health" }] },
  { id: "savings", label: "Savings", items: [{ id: "reclamation", icon: "reclamation", label: "Reclamation" }, { id: "contracts", icon: "contracts", label: "Renewals" }, { id: "licenses", icon: "licenses", label: "Licenses" }, { id: "payments", icon: "payments", label: "Payments" }] },
  { id: "apps", label: "Apps", items: [{ id: "apps", icon: "apps", label: "Applications" }, { id: "categories", icon: "categories", label: "Categories" }, { id: "shadow", icon: "shadow", label: "Shadow IT" }] },
  { id: "sources", label: "Data sources", items: [{ id: "integration-library", icon: "library", label: "Integration Library" }, { id: "zylo", icon: "zylo", label: "Zylo Sync" }, { id: "sync", icon: "sync", label: "Sync" }] },
];
const PINNED = { id: "settings", icon: "settings", label: "Settings" };

function NavBtn({ item, isActive, onClick }) {
  return (
    <button
      onClick={() => onClick(item.id)} data-nav={item.id} aria-current={isActive ? "page" : undefined}
      style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "7px 12px", borderRadius: 8, border: "none", background: isActive ? Z.navyActive : "transparent",
               color: isActive ? Z.navyTextActive : Z.navyText, cursor: "pointer", fontSize: 13, fontWeight: isActive ? 600 : 400, marginBottom: 1, textAlign: "left", transition: "background 0.1s, color 0.1s" }}
      onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = Z.navyHover; e.currentTarget.style.color = "#fff"; } }}
      onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = Z.navyText; } }}
    >
      <Icon name={item.icon} />{item.label}
    </button>
  );
}

function readCollapsed() {
  try { const v = JSON.parse(window.localStorage.getItem(STORE_KEY) || "{}"); return v && typeof v === "object" ? v : {}; } catch { return {}; }
}

export default function Sidebar({ active, onNav }) {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = id => setCollapsed(c => {
    const next = { ...c, [id]: !c[id] };
    try { window.localStorage.setItem(STORE_KEY, JSON.stringify(next)); } catch { /* storage can be blocked: the choice just isn't remembered */ }
    return next;
  });
  return (
    <aside style={{ width: 228, minWidth: 228, background: Z.navy, display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div style={{ padding: "1.1rem 1.5rem 0.9rem", borderBottom: `1px solid ${Z.navyBorder}`, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: Z.accent, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff" }}><Icon name="logo" size={17} /></div>
          <div><p style={{ margin: 0, fontWeight: 700, fontSize: 14, color: "#FFFFFF" }}>Tab</p><p style={{ margin: 0, fontSize: 11, color: Z.navyText }}>Enterprise</p></div>
        </div>
      </div>

      <nav aria-label="Main" data-scroll style={{ padding: "0.5rem 0.75rem", flex: 1, overflowY: "auto", minHeight: 0 }}>
        {GROUPS.map(g => {
          const isCollapsed = !!collapsed[g.id];
          const shown = isCollapsed ? g.items.filter(i => i.id === active) : g.items;       // a collapsed group still shows the page you're on
          return (
            <div key={g.id} data-group={g.id} style={{ marginBottom: 6 }}>
              <button onClick={() => toggle(g.id)} aria-expanded={!isCollapsed} aria-label={`${g.label}, ${isCollapsed ? "collapsed" : "expanded"}`}
                      style={{ width: "100%", display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", padding: "8px 6px 4px", color: Z.navyLabel,
                               fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", textAlign: "left" }}>
                <span style={{ display: "inline-flex", transition: "transform 0.12s", transform: isCollapsed ? "rotate(0deg)" : "rotate(90deg)" }}><Icon name="chevron" size={11} /></span>{g.label}
              </button>
              {shown.map(item => <NavBtn key={item.id} item={item} isActive={active === item.id} onClick={onNav} />)}
            </div>
          );
        })}
      </nav>

      <div style={{ padding: "0.5rem 0.75rem 0.4rem", borderTop: `1px solid ${Z.navyBorder}`, flexShrink: 0 }}>
        <NavBtn item={PINNED} isActive={active === PINNED.id} onClick={onNav} />
      </div>
      <div style={{ padding: "0.7rem 1.25rem", borderTop: `1px solid ${Z.navyBorder}`, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 28, height: 28, borderRadius: "50%", background: "rgba(255,255,255,0.1)", display: "flex", alignItems: "center", justifyContent: "center", color: Z.navyText }}><Icon name="user" size={15} /></div>
          <div style={{ flex: 1, overflow: "hidden" }}>
            <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: "#FFFFFF" }}>IT Admin</p>
            <p style={{ margin: 0, fontSize: 11, color: Z.navyText }}>admin@company.com</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
