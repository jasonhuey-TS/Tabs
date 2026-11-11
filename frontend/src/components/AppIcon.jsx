import { useState, useEffect } from "react";

const API_BASE = import.meta.env?.VITE_API_BASE_URL || "";
const COLORS = ["#4B5EDE", "#0EA5A4", "#D97706", "#9333EA", "#DB2777", "#16A34A", "#2563EB", "#B45309"];

const colorFor = name => {
  let h = 0;
  for (const ch of String(name || "?")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COLORS[h % COLORS.length];
};

/** An app's icon in a round frame. Uses the icon Tab has stored for the app; if there isn't one, a coloured initial
 *  (same colour for the same app every time) so rows still line up. `app` needs `id` and `name`. */
export default function AppIcon({ app, size = 28 }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => { setFailed(false); }, [app && app.id]);
  const frame = { width: size, height: size, borderRadius: "50%", flexShrink: 0, boxSizing: "border-box", display: "inline-flex", alignItems: "center", justifyContent: "center", verticalAlign: "middle", marginRight: Math.round(size * 0.35) };
  if (!app || !app.id || failed) {
    const initial = (String((app && app.name) || "?").trim()[0] || "?").toUpperCase();
    return <span aria-hidden="true" data-app-icon="fallback" style={{ ...frame, background: colorFor(app && app.name), color: "#fff", fontSize: Math.round(size * 0.46), fontWeight: 700 }}>{initial}</span>;
  }
  return (
    <img data-app-icon="image" src={`${API_BASE}/api/v1/app-icons/${app.id}`} alt="" loading="lazy" onError={() => setFailed(true)}
         style={{ ...frame, border: "1px solid #E2E8F0", background: "#fff", padding: Math.max(2, Math.round(size * 0.1)), objectFit: "contain" }} />
  );
}
