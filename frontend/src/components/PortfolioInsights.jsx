import { Fragment, useState, useEffect, useMemo } from "react";
import { api } from "../api/client";
import AppIcon from "./AppIcon";
import { LineChart, aggregatePayments } from "./AppOverview";

const Z = {
  accent: "#4B5EDE", textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
  amberLight: "#FFFBEB", amberText: "#92400E", redLight: "#FEF2F2", redText: "#B91C1C", green: "#16A34A",
};
const card = { background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" };
const dollars = c => (c === null || c === undefined ? "—" : (c < 0 ? "-$" : "$") + Math.abs(Math.round(c / 100)).toLocaleString("en-US"));
const fmtDate = iso => {
  if (!iso) return "—";
  const d = new Date(String(iso).length === 10 ? `${iso}T12:00:00` : iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};
const go = page => window.dispatchEvent(new CustomEvent("tab:navigate", { detail: { page } }));
const linkBtn = { background: "none", border: `1px solid ${Z.border}`, borderRadius: 8, padding: "6px 12px", fontSize: 13, fontWeight: 600, color: Z.textPrimary, cursor: "pointer" };

function download(name, rows) {
  const q = v => `"${String(v).replace(/"/g, '""')}"`;
  const url = URL.createObjectURL(new Blob([rows.map(r => r.map(q).join(",")).join("\n")], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Section({ title, children }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={{ ...card, marginBottom: 20 }} data-section={title}>
      <div style={{ display: "flex", alignItems: "center", padding: "16px 24px", borderBottom: open ? `1px solid ${Z.border}` : "none" }}>
        <h2 style={{ margin: 0, flex: 1, fontSize: 16, fontWeight: 600, color: "#3F4F6B" }}>{title}</h2>
        <button onClick={() => setOpen(o => !o)} aria-expanded={open} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 14, fontWeight: 600, color: "#3F4F6B" }}>{open ? "Hide ︿" : "Show ﹀"}</button>
      </div>
      {open && <div style={{ padding: "20px 24px 24px" }}>{children}</div>}
    </div>
  );
}

function Metric({ label, value, desc, action, onAction, id }) {
  return (
    <div style={{ ...card, padding: "18px 20px", display: "flex", flexDirection: "column" }} data-metric={id}>
      <div style={{ fontSize: 14, fontWeight: 600, color: "#3F4F6B", minHeight: 38 }}>{label}</div>
      <div style={{ fontSize: 30, fontWeight: 500, margin: "6px 0 10px", color: "#1F2937" }}>{value}</div>
      <div style={{ fontSize: 13, color: Z.textSecondary, lineHeight: 1.5, flex: 1 }}>{desc}</div>
      {action && <div style={{ marginTop: 12 }}><button onClick={onAction} style={linkBtn}>{action}</button></div>}
    </div>
  );
}

// Half-circle gauge: green 0-15%, amber 15-35%, red 35-100%.
function Gauge({ pct, count }) {
  const cx = 150, cy = 150, r = 108;
  const pt = p => [cx + r * Math.cos(Math.PI * (1 - p / 100)), cy - r * Math.sin(Math.PI * (1 - p / 100))];
  const arc = (a, b) => { const [x1, y1] = pt(a), [x2, y2] = pt(b); return `M${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2}`; };
  const [mx, my] = pt(Math.min(100, Math.max(0, pct)));
  const tone = pct < 15 ? "#3F8F2F" : pct < 35 ? "#B8860B" : "#D4501E";
  return (
    <svg viewBox="0 0 300 190" role="img" aria-label={`${pct}% of applications have no owner`} style={{ width: "100%", maxWidth: 340, display: "block", margin: "0 auto" }}>
      <path d={arc(0, 15)} stroke="#6AAE4F" strokeWidth="26" fill="none" /><path d={arc(15, 35)} stroke="#F6D365" strokeWidth="26" fill="none" /><path d={arc(35, 100)} stroke="#E8622C" strokeWidth="26" fill="none" />
      <circle cx={mx} cy={my} r="9" fill="#E8622C" stroke="#fff" strokeWidth="3" />
      <text x={cx} y={cy - 28} textAnchor="middle" fontSize="34" fontWeight="500" fill={tone}>{pct}%</text>
      <text x={cx - r - 4} y={cy + 24} textAnchor="middle" fontSize="13" fill={Z.textSecondary}>0</text>
      <text x={cx + r + 4} y={cy + 24} textAnchor="middle" fontSize="13" fill={Z.textSecondary}>{count.toLocaleString()}</text>
    </svg>
  );
}

const monthLabel = ym => new Date(`${ym}T12:00:00`).toLocaleDateString("en-US", { month: "short", year: "2-digit" });
function savingsSeries(monthly) {
  if (!monthly.length) return null;
  const byMonth = Object.fromEntries(monthly.map(m => [m.month.slice(0, 7), m.cents]));
  const first = monthly[0].month.slice(0, 7), now = new Date(), last = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const labels = [];
  let [y, m] = first.split("-").map(Number);
  const [ly, lm] = last.split("-").map(Number);
  while (y < ly || (y === ly && m <= lm)) { labels.push(`${y}-${String(m).padStart(2, "0")}`); m += 1; if (m > 12) { m = 1; y += 1; } }
  return { labels: labels.map(l => monthLabel(`${l}-01`)), points: labels.map((l, i) => ({ label: l, value: (byMonth[l] || 0) / 100 })) };
}

export default function PortfolioInsights() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [mode, setMode] = useState("monthly");
  const [showOwners, setShowOwners] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get("/analytics/portfolio").then(d => { if (!cancelled) setData(d); }).catch(e => { if (!cancelled) setError(e.message || "Could not load the portfolio metrics"); });
    return () => { cancelled = true; };
  }, []);

  const payments = useMemo(() => (data ? aggregatePayments(data.payments.monthly.map(m => ({ paid_on: m.month, amount_cents: m.cents })), mode) : null), [data, mode]);
  const savings = useMemo(() => (data ? savingsSeries(data.savings.monthly) : null), [data]);

  if (error) return <div style={{ ...card, padding: "1rem 1.25rem", marginBottom: 20, color: Z.redText, fontSize: 14 }}>{error}</div>;
  if (!data) return <div style={{ padding: "1.5rem", color: Z.textMuted, fontSize: 14 }}>Loading portfolio metrics…</div>;
  const p = data.payments, none = !p.has_data;
  const dash = v => (none ? "—" : v);

  return (
    <div style={{ marginTop: 28 }}>
      <Section title="Portfolio Metrics and Trends">
        {none && (
          <div style={{ background: Z.amberLight, border: "1px solid #FDE68A", color: Z.amberText, borderRadius: 10, padding: "10px 14px", fontSize: 13, marginBottom: 16 }} data-note="no-payments">
            No payments loaded yet, so the payment figures are blank. Upload a Zylo export or Spendflo transactions on the Payments page.{" "}
            <button onClick={() => go("payments")} style={{ background: "none", border: "none", color: Z.accent, fontWeight: 700, cursor: "pointer", fontSize: 13 }}>Go to Payments</button>
          </div>
        )}
        {p.non_usd_excluded > 0 && <div style={{ background: Z.amberLight, border: "1px solid #FDE68A", color: Z.amberText, borderRadius: 10, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>{p.non_usd_excluded.toLocaleString()} payment{p.non_usd_excluded === 1 ? "" : "s"} in the last 12 months aren't in US dollars and are left out (no currency conversion).</div>}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 16, marginBottom: 20 }}>
          <Metric id="annual" label="Annual Payments" value={dash(dollars(p.annual_cents))} desc="Total software spend in the last 12 months, AP and expense payments together." action="View payments" onAction={() => go("payments")} />
          <Metric id="ap" label="Accounts Payable Payments" value={dash(dollars(p.ap_cents))} desc="Total value of AP payments in the last 12 months." action="View payments" onAction={() => go("payments")} />
          <Metric id="expense" label="Employee Expense Payments" value={dash(dollars(p.expense_cents))} desc="Total spend of employee expense payments in the last 12 months." action="View payments" onAction={() => go("payments")} />
          <Metric id="apps" label="App Count" value={data.app_count.toLocaleString()} desc="Count of applications in Tab, from Okta and any other source." action="View applications" onAction={() => go("apps")} />
          <Metric id="apps-expense" label="Apps with Annual Expense Payments" value={dash(p.apps_with_expense.toLocaleString())} desc="Count of applications with expense payments in the last 12 months." action="View payments" onAction={() => go("payments")} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 20 }}>
          <div style={{ ...card, overflow: "hidden" }} data-chart="payments-over-time">
            <div style={{ display: "flex", alignItems: "center", padding: "12px 20px", borderBottom: `1px solid ${Z.border}` }}>
              <div style={{ flex: 1, fontSize: 15, fontWeight: 600, color: "#3F4F6B" }}>Total Payments Over Time</div>
              <select aria-label="Group payments over time by" value={mode} onChange={e => setMode(e.target.value)} style={{ border: "none", background: "none", fontSize: 14, color: Z.textSecondary, cursor: "pointer" }}>
                <option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option>
              </select>
            </div>
            <div style={{ padding: "14px 18px 16px" }}>
              {payments.series.length === 0 ? <div style={{ padding: "2.5rem 1rem", textAlign: "center", color: Z.textMuted, fontSize: 13 }}>No payments to chart yet.</div> : (
                <>
                  <LineChart labels={payments.labels} series={payments.series} yFormat={v => (v >= 1e6 ? `$${+(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${+(v / 1e3).toFixed(0)}K` : `$${v}`)} label="Portfolio payments over time" />
                  <div style={{ display: "flex", justifyContent: "center", gap: 26, marginTop: 6 }}>
                    {payments.series.map(s => <span key={s.name} style={{ display: "inline-flex", alignItems: "center", fontSize: 14 }}><span style={{ width: 11, height: 11, borderRadius: "50%", background: s.color, marginRight: 8 }} />{s.name}</span>)}
                  </div>
                </>
              )}
            </div>
          </div>
          <div style={{ ...card, overflow: "hidden" }} data-chart="savings-over-time">
            <div style={{ display: "flex", alignItems: "center", padding: "12px 20px", borderBottom: `1px solid ${Z.border}` }}>
              <div style={{ flex: 1, fontSize: 15, fontWeight: 600, color: "#3F4F6B" }}>Savings Over Time</div>
              <span style={{ fontSize: 13, color: Z.textMuted }}>Reclaimed licenses, per year</span>
            </div>
            <div style={{ padding: "14px 18px 16px" }}>
              {!savings ? (
                <div style={{ padding: "2.5rem 1rem", textAlign: "center", color: Z.textMuted, fontSize: 13, lineHeight: 1.6 }}>
                  Nothing reclaimed yet. When access you approved for removal is removed in Okta, the savings are counted here by month.{" "}
                  <button onClick={() => go("reclamation")} style={{ background: "none", border: "none", color: Z.accent, fontWeight: 600, cursor: "pointer", fontSize: 13 }}>Go to Reclamation</button>
                </div>
              ) : (
                <>
                  <LineChart labels={savings.labels} series={[{ name: "Reclaimed", color: "#7ACB5A", points: savings.points }]} yFormat={v => (v >= 1e3 ? `$${+(v / 1e3).toFixed(1)}K` : `$${Math.round(v)}`)} label="Reclaimed savings over time" />
                  <div style={{ textAlign: "center", fontSize: 14, color: Z.textSecondary, marginTop: 4 }}>Total reclaimed so far: <strong style={{ color: Z.textPrimary }}>{dollars(data.savings.total_cents)}</strong> a year</div>
                </>
              )}
            </div>
          </div>
        </div>
      </Section>

      <Section title="Inventory">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 20, alignItems: "start" }}>
          <div style={{ ...card, overflow: "hidden" }} data-card="added">
            <div style={{ display: "flex", alignItems: "flex-start", padding: "14px 20px", borderBottom: `1px solid ${Z.border}` }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: "#3F4F6B" }}>Applications Added in the Last {data.added.days} Days</div>
                <div style={{ fontSize: 13, color: Z.textSecondary, marginTop: 2 }}>Applications Tab first discovered recently. Consider adding an owner and checking they were approved.</div>
              </div>
              {data.added.rows.length > 0 && <button onClick={() => download("applications-added.csv", [["Application", "First seen", "Source", "Annual payments (USD)"], ...data.added.rows.map(r => [r.name, r.first_seen || "", r.source, r.annual_cents / 100])])} aria-label="Export applications added" title="Export CSV" style={{ border: "none", background: "none", cursor: "pointer", fontSize: 16, color: Z.textSecondary }}>⤓</button>}
            </div>
            {data.added.initial_import_date && <div style={{ padding: "8px 20px", fontSize: 12, color: Z.textMuted, background: Z.tableHeader }} data-note="initial-import">Apps first seen on {fmtDate(data.added.initial_import_date)}, when Tab was first set up, aren't counted as new.</div>}
            {data.added.rows.length === 0 ? <div style={{ padding: "2rem", textAlign: "center", color: Z.textMuted, fontSize: 13 }}>No new applications in the last {data.added.days} days.</div> : (
              <div style={{ overflow: "auto", maxHeight: 440 }}>
                <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
                  <thead><tr>{[["App label", "left"], ["First seen", "left"], ["Source", "left"], ["Annual payments", "right"]].map(([h, a]) => <th key={h} style={{ position: "sticky", top: 0, background: Z.tableHeader, padding: "10px 16px", textAlign: a, fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: `1px solid ${Z.border}` }}>{h}</th>)}</tr></thead>
                  <tbody>{data.added.rows.map(r => (
                    <tr key={r.app_id} data-added={r.name}>
                      <td style={{ padding: "10px 16px", fontSize: 14, borderBottom: `1px solid ${Z.border}`, whiteSpace: "nowrap" }}><AppIcon app={{ id: r.app_id, name: r.name }} size={28} />{r.name}</td>
                      <td style={{ padding: "10px 16px", fontSize: 13, borderBottom: `1px solid ${Z.border}`, whiteSpace: "nowrap" }}>{fmtDate(r.first_seen)}</td>
                      <td style={{ padding: "10px 16px", borderBottom: `1px solid ${Z.border}` }}><span style={{ border: `1.5px solid #5B6B8A`, borderRadius: 100, padding: "2px 12px", fontSize: 12, fontWeight: 500, color: "#3F4F6B", textTransform: "capitalize" }}>{String(r.source).replace(/_/g, " ")}</span></td>
                      <td style={{ padding: "10px 16px", fontSize: 14, textAlign: "right", borderBottom: `1px solid ${Z.border}` }}>{dollars(r.annual_cents)}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            {data.added.total > data.added.rows.length && <div style={{ padding: "8px 20px", fontSize: 12, color: Z.textMuted }}>Showing {data.added.rows.length} of {data.added.total.toLocaleString()}.</div>}
          </div>

          <div style={{ display: "grid", gap: 20 }}>
            <div style={{ ...card, padding: "16px 20px" }} data-card="owners">
              <div style={{ display: "flex", alignItems: "center" }}>
                <div style={{ flex: 1, fontSize: 15, fontWeight: 600, color: "#3F4F6B" }}>Applications Without Owners</div>
                <button onClick={() => download("applications-without-owners.csv", [["Application"], ...data.no_owner.apps.map(a => [a.name])])} aria-label="Export applications without owners" title="Export CSV" style={{ border: "none", background: "none", cursor: "pointer", fontSize: 16, color: Z.textSecondary }}>⤓</button>
              </div>
              <Gauge pct={data.no_owner.pct} count={data.no_owner.count} />
              <div style={{ display: "flex", justifyContent: "center", gap: 18, fontSize: 12.5, color: Z.textSecondary, margin: "4px 0 10px" }}>
                {[["#6AAE4F", "0–15%"], ["#F6D365", "15–35%"], ["#E8622C", "35–100%"]].map(([c, l]) => <span key={l}><span style={{ display: "inline-block", width: 11, height: 11, background: c, borderRadius: 3, marginRight: 6 }} />{l}</span>)}
              </div>
              <div style={{ fontSize: 13, color: Z.textSecondary, lineHeight: 1.5 }}>
                <strong style={{ color: Z.textPrimary }}>{data.no_owner.count.toLocaleString()}</strong> of {data.no_owner.total.toLocaleString()} applications have no owner, business owner or IT owner. Add owners on each app's App Info tab.{" "}
                {data.no_owner.apps.length > 0 && <button onClick={() => setShowOwners(s => !s)} style={{ background: "none", border: "none", padding: 0, color: Z.accent, fontWeight: 600, cursor: "pointer", fontSize: 13 }}>{showOwners ? "Hide the list" : "Show the list"}</button>}
              </div>
              {showOwners && (
                <div style={{ marginTop: 10, maxHeight: 200, overflowY: "auto", border: `1px solid ${Z.border}`, borderRadius: 8 }} data-list="no-owner">
                  {data.no_owner.apps.map(a => <div key={a.app_id} style={{ padding: "6px 12px", fontSize: 13, borderBottom: `1px solid ${Z.border}` }}><AppIcon app={a} size={20} />{a.name}</div>)}
                  {data.no_owner.count > data.no_owner.apps.length && <div style={{ padding: "6px 12px", fontSize: 12, color: Z.textMuted }}>Showing the first {data.no_owner.apps.length.toLocaleString()}.</div>}
                </div>
              )}
            </div>
            <div style={{ ...card, padding: "16px 20px" }} data-card="no-payment">
              <div style={{ fontSize: 15, fontWeight: 600, color: "#3F4F6B" }}>No Payment Applications</div>
              <div style={{ fontSize: 32, fontWeight: 500, margin: "14px 0 8px" }}>{data.no_payment.payments_loaded ? data.no_payment.count.toLocaleString() : "—"}</div>
              <div style={{ fontSize: 13, color: Z.textSecondary, lineHeight: 1.5 }}>
                {data.no_payment.payments_loaded
                  ? `Count of applications without any payment activity in the past ${data.no_payment.months} months (to allow for late payments or changes in billing).`
                  : "Load payments on the Payments page to see which applications have no payment activity."}
              </div>
            </div>
          </div>
        </div>
      </Section>
    </div>
  );
}
