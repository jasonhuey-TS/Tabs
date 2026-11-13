import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
  good: "#15803D", goodLight: "#F0FDF4", fair: "#B45309", fairLight: "#FFFBEB", poor: "#B91C1C", poorLight: "#FEF2F2",
};
const card = { background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", padding: "16px 20px", marginBottom: 16 };
const btn = primary => ({ padding: "6px 12px", borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: "pointer", border: `1px solid ${primary ? Z.accent : Z.border}`, background: primary ? Z.accent : "#fff", color: primary ? "#fff" : Z.textPrimary });
const link = { background: "none", border: "none", padding: 0, color: Z.accent, fontWeight: 600, fontSize: 12.5, cursor: "pointer" };
const TONE = { good: [Z.good, Z.goodLight], fair: [Z.fair, Z.fairLight], poor: [Z.poor, Z.poorLight] };
const go = page => window.dispatchEvent(new CustomEvent("tab:navigate", { detail: { page } }));
const n = v => Number(v || 0).toLocaleString("en-US");
const usd = cents => "$" + Math.round((cents || 0) / 100).toLocaleString("en-US");
const when = iso => (iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "never");
const scoreTone = s => (s >= 85 ? "good" : s >= 65 ? "fair" : "poor");

function Check({ c }) {
  const [open, setOpen] = useState(false);
  const [all, setAll] = useState(null);
  const tone = c.status ? TONE[c.status] : [Z.textMuted, Z.tableHeader];
  async function showAll() { setAll(await api.get(`/health/missing?check=${c.id}&limit=200`).catch(() => ({ rows: [], missing_count: 0 }))); }
  const list = all ? all.rows : c.missing;
  return (
    <div data-check={c.id} data-status={c.status || "none"} style={{ borderTop: `1px solid ${Z.border}`, padding: "12px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 280px", minWidth: 240 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{c.label}</div>
          <div style={{ fontSize: 12.5, color: Z.textSecondary }}>{c.why}</div>
        </div>
        <div style={{ width: 210 }}>
          {c.total === 0 ? <div data-none style={{ fontSize: 12.5, color: Z.textMuted }}>Nothing to check yet ({c.applies_to})</div> : (<>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 3 }}><span data-count>{n(c.ok)} of {n(c.total)} {c.applies_to}</span><strong data-pct style={{ color: tone[0] }}>{c.pct}%</strong></div>
            <div style={{ background: "#EEF2F7", borderRadius: 6, height: 8 }}><div data-bar style={{ width: `${c.pct}%`, minWidth: c.pct ? 3 : 0, height: 8, borderRadius: 6, background: tone[0] }} /></div>
          </>)}
        </div>
        <div style={{ display: "flex", gap: 8, width: 330, flexShrink: 0, justifyContent: "flex-end" }}>
          {c.missing_count > 0 && <button style={btn(false)} aria-label={`Show apps missing ${c.label}`} onClick={() => setOpen(o => !o)}>{open ? "Hide apps" : `Show ${n(c.missing_count)} app${c.missing_count === 1 ? "" : "s"}`}</button>}
          {c.missing_count > 0 && <button style={btn(true)} aria-label={`${c.fix.label} (${c.label})`} onClick={() => go(c.fix.page)}>{c.fix.label}</button>}
        </div>
      </div>
      {open && (
        <div data-missing style={{ background: Z.tableHeader, borderRadius: 8, padding: "8px 12px", marginTop: 10 }}>
          {list.map(a => (
            <div key={a.app_id} style={{ display: "flex", gap: 12, fontSize: 13, padding: "3px 0" }}>
              <span style={{ flex: 1, fontWeight: 600 }}>{a.name}</span><span style={{ color: Z.textSecondary }}>{n(a.users)} people</span><span style={{ color: Z.textSecondary, width: 90, textAlign: "right" }}>{a.spend_cents ? `${usd(a.spend_cents)} paid` : "no spend"}</span>
            </div>))}
          {!all && c.missing_count > c.missing.length && <button style={{ ...link, marginTop: 6 }} onClick={showAll}>Show all {n(c.missing_count)}</button>}
          {all && all.missing_count > all.rows.length && <div style={{ fontSize: 12, color: Z.textMuted, marginTop: 6 }}>Showing the first {n(all.rows.length)} of {n(all.missing_count)}.</div>}
        </div>)}
    </div>
  );
}

export default function DataHealth() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => api.get("/health/overview").then(d => { setData(d); setError(null); }).catch(e => setError(e.message || "Could not load the health check")), []);
  useEffect(() => { load(); }, [load]);
  if (error) return <div style={{ padding: "24px 32px", color: Z.poor }}>{error}</div>;
  if (!data) return <div style={{ padding: "24px 32px", color: Z.textMuted }}>Checking your data…</div>;
  const tone = data.score === null ? [Z.textMuted, Z.tableHeader] : TONE[scoreTone(data.score)];
  const t = data.savings_trust || { ready: false };
  return (
    <div style={{ padding: "24px 32px", maxWidth: 1100 }}>
      <h2 style={{ margin: "0 0 4px", fontSize: 22 }}>Data Health</h2>
      <div style={{ fontSize: 13.5, color: Z.textSecondary, marginBottom: 18 }}>How complete the information about your apps is, and so how far to trust the savings and spend numbers.</div>

      <div style={{ ...card, display: "flex", gap: 28, flexWrap: "wrap", alignItems: "center" }} data-card="score">
        <div style={{ textAlign: "center", minWidth: 150 }}>
          <div data-score style={{ fontSize: 54, fontWeight: 800, color: tone[0], lineHeight: 1 }}>{data.score === null ? "—" : data.score}</div>
          <div data-grade style={{ fontSize: 14, fontWeight: 700, color: tone[0], marginTop: 4 }}>{data.grade || "No data yet"}</div>
          <div style={{ fontSize: 11.5, color: Z.textMuted, marginTop: 4 }}>{n(data.in_use_apps)} apps in use · {n(data.paid_apps)} you pay for</div>
        </div>
        <div style={{ flex: 1, minWidth: 300 }} data-fix-first>
          <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.05em", textTransform: "uppercase", color: Z.textMuted, marginBottom: 6 }}>Fix these first</div>
          {data.fix_first.length === 0 ? <div style={{ fontSize: 13, color: Z.textSecondary }}>{data.score === null ? "Add apps, payments and contracts to get a score." : "Nothing urgent: every check is in good shape."}</div> : data.fix_first.map(f => (
            <div key={f.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0" }}>
              <span style={{ flex: 1, fontSize: 13.5 }}><strong>{f.label}</strong>: {n(f.missing_count)} app{f.missing_count === 1 ? "" : "s"} missing it ({f.pct}% done)</span>
              <button style={btn(true)} aria-label={`${f.fix.label} first`} onClick={() => go(f.fix.page)}>{f.fix.label}</button>
            </div>))}
        </div>
      </div>

      <div style={card} data-card="trust">
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>How far to trust the savings numbers</div>
        {!t.ready ? <div style={{ fontSize: 13, color: Z.textSecondary }}>Savings aren't calculated yet. Run the Okta sign-in sync so Tab knows who is idle.</div> : (
          <div style={{ fontSize: 13.5, color: Z.textSecondary, lineHeight: 1.6 }}>
            Reclamation estimates <strong style={{ color: Z.textPrimary }}>{usd(t.est_annual_savings_cents)}</strong> a year across {n(t.apps_counted)} apps with reliable activity.
            {t.reliable_pct !== null && <> <strong data-reliable style={{ color: Z.textPrimary }}>{t.reliable_pct}%</strong> of that is priced from license records or contracts.</>}
            {t.rough_cents > 0 && <> <span data-rough>{usd(t.rough_cents)} rests on only a few months of payments.</span></>}
            {t.unpriced_apps > 0 && <> <span data-unpriced>{n(t.unpriced_apps)} app{t.unpriced_apps === 1 ? " with idle people has" : "s with idle people have"} no price yet, so {t.unpriced_apps === 1 ? "it isn't" : "they aren't"} in the estimate.</span></>}
            {" "}<button style={link} onClick={() => go("reclamation")}>Open Reclamation</button>
          </div>)}
      </div>

      <div style={card} data-card="checks">
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 2 }}>What's complete, and what isn't</div>
        <div style={{ fontSize: 12.5, color: Z.textMuted, marginBottom: 6 }}>Each check looks at the apps it applies to. The score weighs them by how much they matter to the numbers.</div>
        {data.checks.map(c => <Check key={c.id} c={c} />)}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 16 }}>
        <div style={card} data-card="setup">
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8 }}>Set up</div>
          {data.setup.map(s => (
            <div key={s.id} data-setup={s.id} data-ok={s.ok ? "yes" : "no"} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderTop: `1px solid ${Z.border}` }}>
              <span aria-hidden="true" style={{ width: 20, height: 20, borderRadius: "50%", background: s.ok ? Z.good : "#fff", border: `2px solid ${s.ok ? Z.good : Z.border}`, color: "#fff", fontSize: 12, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>{s.ok ? "✓" : ""}</span>
              <div style={{ flex: 1 }}><div style={{ fontSize: 13.5, fontWeight: 600 }}>{s.label}</div>{!s.ok && <div style={{ fontSize: 12, color: Z.textMuted }}>{s.why}</div>}</div>
              {!s.ok && <button style={btn(false)} onClick={() => go(s.fix.page)}>{s.fix.label}</button>}
            </div>))}
          <div style={{ fontWeight: 700, fontSize: 14, margin: "14px 0 6px" }}>Waiting for you</div>
          {[["zylo", data.pending.zylo_unmatched, "Zylo apps to match to Tab apps", "Match them"], ["shadow", data.pending.shadow_review, "apps found in Google and Microsoft to review", "Review them"]].map(([page, count, label, action]) => (
            <div key={page} data-pending={page} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderTop: `1px solid ${Z.border}` }}>
              <span style={{ flex: 1, fontSize: 13.5 }}><strong>{n(count)}</strong> {label}</span>
              {count > 0 ? <button style={btn(false)} onClick={() => go(page)}>{action}</button> : <span style={{ fontSize: 12, color: Z.good, fontWeight: 600 }}>All clear</span>}
            </div>))}
        </div>

        <div style={card} data-card="syncs">
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8 }}>How fresh the data is</div>
          {data.syncs.length === 0 ? <div style={{ fontSize: 13, color: Z.textMuted }}>No syncs have run yet.</div> : data.syncs.map(s => {
            const [color, bg] = s.status === "ok" ? TONE.good : s.status === "stale" ? TONE.fair : TONE.poor;
            return (
              <div key={s.key} data-sync={s.key} data-status={s.status} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderTop: `1px solid ${Z.border}` }}>
                <span style={{ flex: 1, fontSize: 13.5, fontWeight: 600 }}>{s.name}</span>
                <span style={{ fontSize: 12.5, color: Z.textSecondary }}>{s.last_sync_at ? `${when(s.last_sync_at)} (${s.age_days === 0 ? "today" : `${s.age_days} day${s.age_days === 1 ? "" : "s"} ago`})` : "never"}</span>
                <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 100, color, background: bg }}>{s.status === "ok" ? "Up to date" : s.status === "stale" ? "Out of date" : s.status === "error" ? "Failed" : "Never ran"}</span>
              </div>);
          })}
          <div style={{ fontSize: 12, color: Z.textMuted, marginTop: 8 }}>Anything older than 3 days is flagged. Open the Sync page or the Integration Library to run one.</div>
        </div>
      </div>
    </div>
  );
}
