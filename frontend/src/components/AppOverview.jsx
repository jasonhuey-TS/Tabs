import { useState, useEffect, useMemo } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF",
  red: "#B91C1C", amber: "#B45309", blue: "#4DA3FF", green: "#7ACB5A", orange: "#F0913A", purple: "#A97BDC", grey: "#E5E7EB",
};
const YEAR_COLORS = ["#4DA3FF", "#7ACB5A", "#F0913A", "#A97BDC", "#EC6A8B", "#33B6B0"];
const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

const compact = cents => {
  if (cents === null || cents === undefined) return "—";
  const d = cents / 100;
  if (d >= 1e6) return "$" + (d / 1e6).toFixed(d >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (d >= 1e3) return "$" + Math.round(d / 1e3) + "K";
  return "$" + Math.round(d).toLocaleString("en-US");
};
const full = cents => (cents === null || cents === undefined ? "—" : "$" + Math.round(cents / 100).toLocaleString("en-US"));
const fmtDate = iso => {
  const d = new Date(String(iso).length === 10 ? `${iso}T12:00:00` : iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};
const pct = (n, total) => (total ? Math.round((100 * n) / total) : 0);

// ───────────────────────────────────────────────────────────── payments aggregation (pure)
/** ledger: [{paid_on: 'YYYY-MM-DD', amount_cents}] -> {labels, series:[{name,color,points:[{label,value|null}]}]} */
export function aggregatePayments(ledger, mode, today = new Date()) {
  const years = [...new Set(ledger.map(p => Number(p.paid_on.slice(0, 4))))].sort();
  const thisYear = today.getFullYear(), thisMonth = today.getMonth();      // 0-based
  if (mode === "yearly") {
    const totals = Object.fromEntries(years.map(y => [y, 0]));
    ledger.forEach(p => { totals[Number(p.paid_on.slice(0, 4))] += p.amount_cents; });
    return { labels: years.map(String), series: [{ name: "Total", color: YEAR_COLORS[0], points: years.map(y => ({ label: String(y), value: totals[y] / 100 })) }] };
  }
  const buckets = mode === "quarterly" ? 4 : 12;
  const labels = mode === "quarterly" ? ["Q1", "Q2", "Q3", "Q4"] : MONTHS;
  const slot = p => (mode === "quarterly" ? Math.floor((Number(p.paid_on.slice(5, 7)) - 1) / 3) : Number(p.paid_on.slice(5, 7)) - 1);
  const series = years.map((y, i) => {
    const sums = new Array(buckets).fill(0);
    ledger.filter(p => Number(p.paid_on.slice(0, 4)) === y).forEach(p => { sums[slot(p)] += p.amount_cents; });
    const lastSlot = y < thisYear ? buckets - 1 : y === thisYear ? (mode === "quarterly" ? Math.floor(thisMonth / 3) : thisMonth) : -1;
    return { name: String(y), color: YEAR_COLORS[i % YEAR_COLORS.length],
             points: sums.map((v, k) => ({ label: labels[k], value: k <= lastSlot ? v / 100 : null })) };     // no line into the future
  });
  return { labels, series };
}

// ───────────────────────────────────────────────────────────── SVG line chart
const niceCeil = v => { const p = Math.pow(10, Math.floor(Math.log10(v))); const f = v / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; };

function smoothPath(pts, lo, hi) {
  if (pts.length === 1) return `M${pts[0][0]},${pts[0][1]}`;
  const clamp = v => Math.min(hi, Math.max(lo, v));
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    d += ` C${p1[0] + (p2[0] - p0[0]) / 6},${clamp(p1[1] + (p2[1] - p0[1]) / 6)} ${p2[0] - (p3[0] - p1[0]) / 6},${clamp(p2[1] - (p3[1] - p1[1]) / 6)} ${p2[0]},${p2[1]}`;
  }
  return d;
}

export function LineChart({ labels, series, yFormat, label }) {
  const W = 640, H = 270, m = { l: 62, r: 18, t: 14, b: 32 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const max = niceCeil(Math.max(1, ...series.flatMap(s => s.points.map(p => p.value || 0))));
  const x = i => m.l + (labels.length === 1 ? iw / 2 : (iw * i) / (labels.length - 1));
  const y = v => m.t + ih - (ih * v) / max;
  const step = Math.ceil(labels.length / 12);                      // at most ~12 labels (all 12 months), counted back from the last point so they never collide
  const dots = labels.length <= 40;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} style={{ width: "100%", height: "auto", display: "block" }}>
      {[0, 1, 2, 3, 4].map(t => {
        const v = (max * t) / 4;
        return <g key={t}><line x1={m.l} x2={W - m.r} y1={y(v)} y2={y(v)} stroke={Z.grey} strokeWidth="1" /><text x={m.l - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill={Z.textSecondary}>{yFormat(v)}</text></g>;
      })}
      {labels.map((l, i) => (labels.length - 1 - i) % step === 0 && (
        <text key={l + i} x={x(i)} y={H - 10} textAnchor="middle" fontSize="11" fill={Z.textSecondary}>{l}</text>
      ))}
      {series.map(s => {
        const runs = [];                                              // consecutive known points
        s.points.forEach((p, i) => {
          if (p.value === null || p.value === undefined) { runs.push(null); return; }
          if (!runs.length || runs[runs.length - 1] === null) runs.push([]);
          runs[runs.length - 1].push([x(i), y(p.value), p, i]);
        });
        return (
          <g key={s.name} data-series={s.name}>
            {runs.filter(Boolean).map((run, k) => <path key={k} d={smoothPath(run.map(r => [r[0], r[1]]), m.t, m.t + ih)} fill="none" stroke={s.color} strokeWidth="3" strokeLinecap="round" />)}
            {dots && runs.filter(Boolean).flat().map(r => (
              <circle key={r[3]} cx={r[0]} cy={r[1]} r="3.5" fill={s.color}><title>{`${s.name}: ${labels[r[3]]} - ${yFormat(r[2].value)}`}</title></circle>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

// ───────────────────────────────────────────────────────────── cards
const card = { background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" };

function Bar({ parts }) {
  const total = parts.reduce((a, p) => a + p.value, 0);
  return (
    <div style={{ display: "flex", height: 14, borderRadius: 4, overflow: "hidden", background: Z.grey, marginTop: 14 }}>
      {total > 0 && parts.filter(p => p.value > 0).map((p, i) => <div key={i} title={p.title} style={{ flex: p.value, background: p.color }} />)}
    </div>
  );
}

function Dot({ color }) { return <span style={{ width: 11, height: 11, borderRadius: "50%", background: color, display: "inline-block", marginRight: 9, flexShrink: 0, marginTop: 4 }} />; }

function CarouselCard({ title, info, slides, testId }) {
  const [i, setI] = useState(0);
  const slide = slides[i];
  const arrow = (dir, label) => (
    <button onClick={() => setI((i + dir + slides.length) % slides.length)} aria-label={label} disabled={slides.length < 2}
            style={{ width: 34, height: 30, borderRadius: 6, border: `1px solid ${Z.border}`, background: Z.cardBg, cursor: slides.length < 2 ? "default" : "pointer", color: Z.textSecondary, fontSize: 16, opacity: slides.length < 2 ? 0.4 : 1 }}>{dir < 0 ? "‹" : "›"}</button>
  );
  return (
    <div style={{ ...card, padding: "18px 22px", minHeight: 210 }} data-card={testId}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ flex: 1, fontSize: 15, fontWeight: 600, color: Z.textPrimary }}>{slide.title || title}{info && <span title={info} style={{ marginLeft: 8, color: Z.textMuted, cursor: "help", fontSize: 13 }}>ⓘ</span>}</div>
        {arrow(-1, `Previous ${title}`)}{arrow(1, `Next ${title}`)}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginTop: 6 }}>
        <div style={{ fontSize: 34, fontWeight: 600, color: Z.textPrimary }}>{slide.value}</div>
        <div style={{ fontSize: 13, color: Z.textSecondary }}>{i + 1} of {slides.length}</div>
      </div>
      <div style={{ marginTop: 6 }}>
        {slide.lines.map((l, k) => (
          <div key={k} style={{ display: "flex", fontSize: 14, color: Z.textPrimary, marginBottom: 6, lineHeight: 1.35 }}>{l.color && <Dot color={l.color} />}<span>{l.text}</span></div>
        ))}
      </div>
      {slide.bar && <Bar parts={slide.bar} />}
    </div>
  );
}

function ChartCard({ title, controls, children, onExport }) {
  return (
    <div style={{ ...card, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 20px", borderBottom: `1px solid ${Z.border}`, flexWrap: "wrap" }}>
        <div style={{ flex: 1, fontSize: 15, fontWeight: 600, color: Z.textPrimary }}>{title}</div>
        {controls}
        {onExport && <button onClick={onExport} aria-label={`Export ${title}`} title="Export CSV" style={{ border: "none", background: "none", cursor: "pointer", color: Z.textSecondary, fontSize: 16 }}>⤓</button>}
      </div>
      <div style={{ padding: "14px 18px 16px" }}>{children}</div>
    </div>
  );
}

function download(name, rows) {
  const q = v => `"${String(v).replace(/"/g, '""')}"`;
  const url = URL.createObjectURL(new Blob([rows.map(r => r.map(q).join(",")).join("\n")], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function AppOverview({ app, onJump }) {
  const [m, setM] = useState(null);
  const [error, setError] = useState(null);
  const [mode, setMode] = useState("monthly");

  useEffect(() => {
    let cancelled = false;
    setM(null); setError(null);
    api.get(`/app-details/${app.id}/metrics`).then(d => { if (!cancelled) setM(d); }).catch(e => { if (!cancelled) setError(e.message || "Could not load the metrics"); });
    return () => { cancelled = true; };
  }, [app.id]);

  const payments = useMemo(() => (m ? aggregatePayments(m.payments.ledger, mode) : null), [m, mode]);
  if (error) return <div style={{ padding: "1.5rem", color: Z.red, fontSize: 14 }}>{error}</div>;
  if (!m) return <div style={{ padding: "2rem", textAlign: "center", color: Z.textMuted }}>Loading metrics…</div>;

  const p = m.provisioned, pay = m.payments, seats = m.seats, r = m.renewal;
  const paidBar = [{ value: pay.paid_last_12_months_cents, color: Z.blue, title: "Paid" }, { value: Math.max(0, pay.annual_cost_cents - pay.paid_last_12_months_cents), color: "#CFE6FF", title: "Not yet paid" }];

  const paymentSlides = [
    { title: "Annual Payments", value: compact(pay.paid_last_12_months_cents),
      lines: [{ color: Z.blue, text: `Paid, last 12 months: ${full(pay.paid_last_12_months_cents)}` }, { color: "#CFE6FF", text: `Annual license cost: ${full(pay.annual_cost_cents)}` }],
      bar: pay.annual_cost_cents || pay.paid_last_12_months_cents ? paidBar : null },
    { title: "Contracted Spend", value: compact(pay.contract_value_cents),
      lines: [{ color: Z.green, text: `Active contracts: ${full(pay.contract_value_cents)}` },
              ...(pay.expected[0] ? [{ color: Z.orange, text: `Next bill: ${full(pay.expected[0].amount_cents)}${pay.expected[0].next_billing_date ? ` on ${fmtDate(pay.expected[0].next_billing_date)}` : ""}` }] : [])] },
  ];
  const userSlides = [
    { title: "Provisioned Users", value: p.total.toLocaleString(),
      lines: [{ color: Z.orange, text: `Active Users: ${pct(p.active, p.total)}% (${p.active.toLocaleString()} out of ${p.total.toLocaleString()})` },
              { color: Z.purple, text: `Inactive Users: ${pct(p.inactive, p.total)}% (${p.inactive.toLocaleString()} out of ${p.total.toLocaleString()})` }],
      bar: [{ value: p.active, color: `linear-gradient(90deg, ${Z.orange}, #F7C99B)`, title: "Active" }, { value: p.inactive, color: `linear-gradient(90deg, ${Z.purple}, #D2B8EE)`, title: "Inactive" }] },
    seats ? { title: "Seat Utilization", value: (seats.purchased || 0).toLocaleString(),
              lines: [{ color: Z.blue, text: `Assigned: ${seats.assigned.toLocaleString()} of ${seats.purchased.toLocaleString()} purchased` },
                      { color: Z.green, text: `Active: ${seats.active.toLocaleString()}${seats.utilization_pct !== null ? ` (${Math.round(seats.utilization_pct)}% utilization)` : ""}` },
                      ...(seats.waste_cost_cents ? [{ color: Z.red, text: `Unused seats cost about ${full(seats.waste_cost_cents)} a year` }] : [])],
              bar: [{ value: seats.active, color: Z.green, title: "Active" }, { value: Math.max(0, seats.purchased - seats.active), color: Z.grey, title: "Unused" }] }
          : { title: "Seat Utilization", value: "—", lines: [{ text: "No license on file. Import one on the Licenses page to see seat utilization." }] },
  ];

  const renewalText = r.date
    ? `Upcoming renewal: ${fmtDate(r.date)} (${r.days === 0 ? "today" : `in ${r.days} day${r.days === 1 ? "" : "s"}`})${r.auto_renews ? " · renews automatically" : ""}`
    : "Upcoming renewal date not available";
  const renewalColor = !r.date ? Z.red : r.days <= 30 ? Z.red : r.days <= 90 ? Z.amber : Z.textSecondary;

  const money = v => (v >= 1e6 ? `$${v / 1e6}M` : v >= 1e3 ? `$${v / 1e3}K` : `$${v}`);
  const series = m.active_series;
  const seriesLabels = series ? series.points.map(pt => fmtDate(pt.day).replace(/, \d{4}$/, "")) : [];

  return (
    <div>
      <div style={{ textAlign: "right", marginBottom: 14 }}>
        <button onClick={() => onJump("contracts")} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 17, fontWeight: 500, color: renewalColor }}>
          {renewalText}<span title={r.source === "license" ? "From the license's next billing date" : r.source === "contract" ? "From the soonest active contract" : "Add a contract with an end date, or a license with a billing date"} style={{ marginLeft: 6, fontSize: 13 }}>ⓘ</span>
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 20, alignItems: "start" }}>
        <div style={{ display: "grid", gap: 20 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 20 }}>
            <CarouselCard title="Annual Payments" info="Payments you've recorded on the Payments tab, and the annual cost from the license." slides={paymentSlides} testId="payments" />
            <CarouselCard title="Provisioned Users" info={`People assigned in Okta. Active means activity within ${m.threshold} days (change it with Activity Threshold).`} slides={userSlides} testId="users" />
          </div>

          <div style={{ ...card, padding: "18px 22px" }} data-card="security">
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>Security</div>
            <div style={{ fontSize: 11, fontWeight: 700, color: Z.textSecondary, letterSpacing: "0.06em", marginBottom: 8 }}>CERTIFICATIONS / STANDARDS</div>
            {m.certifications.length === 0 ? (
              <div style={{ fontSize: 13, color: Z.textMuted, lineHeight: 1.6 }}>None recorded yet.</div>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {m.certifications.map(c => <span key={c} style={{ border: `1.5px solid ${Z.textSecondary}`, borderRadius: 100, padding: "4px 14px", fontSize: 13, fontWeight: 500, color: Z.textSecondary }}>{c}</span>)}
              </div>
            )}
            <div style={{ fontSize: 12, color: Z.textMuted, marginTop: 12, lineHeight: 1.5 }}>
              Certifications are entered by hand. Cloud Confidence scores come from a third-party risk database that isn't connected here.{" "}
              <button onClick={() => onJump("info")} style={{ background: "none", border: "none", padding: 0, color: Z.accent, fontWeight: 600, cursor: "pointer", fontSize: 12 }}>Edit on App Info</button>
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gap: 20 }}>
          <ChartCard title="Total Payments Over Time"
            controls={<select value={mode} onChange={e => setMode(e.target.value)} aria-label="Group payments by" style={{ border: "none", background: "none", fontSize: 14, color: Z.textSecondary, cursor: "pointer" }}>
              <option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select>}
            onExport={payments && payments.series.length ? () => download(`${app.name}-payments-${mode}.csv`, [["Period", ...payments.series.map(s => s.name)], ...payments.labels.map((l, i) => [l, ...payments.series.map(s => s.points[i].value ?? "")])]) : null}>
            {payments.series.length === 0 ? (
              <div style={{ padding: "2.5rem 1rem", textAlign: "center", color: Z.textMuted, fontSize: 13, lineHeight: 1.6 }}>
                No payments recorded yet.{" "}
                <button onClick={() => onJump("payments")} style={{ background: "none", border: "none", padding: 0, color: Z.accent, fontWeight: 600, cursor: "pointer", fontSize: 13 }}>Record one on the Payments tab</button>
              </div>
            ) : (
              <>
                <LineChart labels={payments.labels} series={payments.series} yFormat={money} label="Total payments over time" />
                <div style={{ display: "flex", justifyContent: "center", gap: 28, marginTop: 6 }}>
                  {payments.series.map(s => <span key={s.name} style={{ display: "inline-flex", alignItems: "center", fontSize: 14, color: Z.textPrimary }}><Dot color={s.color} />{s.name}</span>)}
                </div>
              </>
            )}
          </ChartCard>

          <ChartCard title="Active Users Over Time"
            controls={series ? <span style={{ fontSize: 12, color: Z.textMuted }}>People active in the previous {series.window_days} days</span> : null}
            onExport={series ? () => download(`${app.name}-active-users.csv`, [["Day", "Active users"], ...series.points.map(pt => [pt.day, pt.active])]) : null}>
            {!series ? (
              <div style={{ padding: "2.5rem 1rem", textAlign: "center", color: Z.textMuted, fontSize: 13, lineHeight: 1.6 }}>
                Per-day activity isn't available for this app yet. It builds up from Okta sign-ins or a usage connector that reports daily activity, and a chart needs
                {" "}{Math.min(Math.max(m.threshold, 7), 60)} days of history to be accurate.
              </div>
            ) : (
              <LineChart labels={seriesLabels} series={[{ name: "Active users", color: Z.green, points: series.points.map((pt, i) => ({ label: seriesLabels[i], value: pt.active })) }]} yFormat={v => Math.round(v).toLocaleString()} label="Active users over time" />
            )}
          </ChartCard>
        </div>
      </div>
    </div>
  );
}
