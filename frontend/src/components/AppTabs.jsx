import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";

const Z = {
  accent: "#4B5EDE", accentLight: "#EEF0FD", green: "#16A34A", greenLight: "#F0FDF4", greenText: "#15803D",
  red: "#DC2626", redLight: "#FEF2F2", redText: "#B91C1C", amber: "#D97706", amberLight: "#FFFBEB", amberText: "#92400E",
  textPrimary: "#111827", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF", tableHeader: "#F8FAFC",
};

const money = c => (c === null || c === undefined ? "—" : "$" + Math.round(c / 100).toLocaleString("en-US"));
const fmtDate = iso => {
  if (!iso) return "—";
  const d = new Date(String(iso).length === 10 ? `${iso}T12:00:00` : iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};
const fmtDateTime = iso => {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
};

const card = { background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 10 };
const th = { padding: "9px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap", background: Z.tableHeader, borderBottom: `1px solid ${Z.border}` };
const td = { padding: "10px 14px", fontSize: 13, color: Z.textPrimary, borderBottom: `1px solid ${Z.border}` };
const input = { width: "100%", boxSizing: "border-box", padding: "8px 12px", borderRadius: 8, border: `1px solid ${Z.border}`, fontSize: 13, outline: "none", fontFamily: "inherit" };
const btn = (primary, disabled, danger) => ({
  padding: "7px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1,
  border: primary ? "none" : `1px solid ${danger ? "#FECACA" : Z.border}`, background: primary ? Z.accent : Z.cardBg, color: primary ? "#fff" : danger ? Z.red : Z.textPrimary,
});

function useLoad(path) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const reload = useCallback(() => {
    setError(null);
    return api.get(path).then(setData).catch(e => setError(e.message || "Could not load this"));
  }, [path]);
  useEffect(() => { setData(null); reload(); }, [reload]);
  return { data, error, reload };
}

function Loading({ data, error, children }) {
  if (error) return <div style={{ padding: "1.5rem", color: Z.redText, fontSize: 14 }}>{error}</div>;
  if (!data) return <div style={{ padding: "2rem", textAlign: "center", color: Z.textMuted }}>Loading…</div>;
  return children;
}

function Empty({ children }) {
  return <div style={{ padding: "2rem", textAlign: "center", color: Z.textMuted, fontSize: 13, lineHeight: 1.6 }}>{children}</div>;
}

function Note({ tone = "amber", children }) {
  const t = { amber: [Z.amberLight, "#FDE68A", Z.amberText], red: [Z.redLight, "#FECACA", Z.redText], green: [Z.greenLight, "#BBF7D0", Z.greenText], blue: [Z.accentLight, "#C7D2FE", "#3730A3"] }[tone];
  return <div style={{ background: t[0], border: `1px solid ${t[1]}`, color: t[2], borderRadius: 10, padding: "9px 14px", fontSize: 12.5, lineHeight: 1.5, marginBottom: 12 }}>{children}</div>;
}

function Stat({ label, value, sub, tone }) {
  return (
    <div style={{ ...card, padding: "14px 16px" }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, margin: "4px 0 2px", color: tone === "good" ? Z.green : Z.textPrimary }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: Z.textSecondary }}>{sub}</div>}
    </div>
  );
}

function Labeled({ label, hint, children }) {
  return (
    <label style={{ display: "block", marginBottom: 12 }}>
      <span style={{ display: "block", fontSize: 12, fontWeight: 600, color: Z.textSecondary, marginBottom: 4 }}>{label}</span>
      {children}
      {hint && <span style={{ display: "block", fontSize: 11, color: Z.textMuted, marginTop: 3 }}>{hint}</span>}
    </label>
  );
}

// POST helper: returns the error message, or null on success.
async function send(path, body) {
  try {
    const r = await api.post(path, body);
    return r && r.ok === false ? (r.message || "That didn't work") : null;
  } catch (e) { return e.message || "That didn't work"; }
}

// ───────────────────────────────────────────────────────────── Alerts
const SEVERITY = { high: [Z.redLight, Z.redText, "High"], medium: [Z.amberLight, Z.amberText, "Medium"], info: [Z.accentLight, "#3730A3", "Info"] };

export function AlertsTab({ app, onJump, onLoaded }) {
  const { data, error } = useLoad(`/app-details/${app.id}/alerts`);
  useEffect(() => { if (data && onLoaded) onLoaded(data.length); }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Loading data={data} error={error}>
      {data && data.length === 0 ? <Empty>No alerts. Nothing about this app needs attention right now.</Empty> : (
        <div style={{ display: "grid", gap: 10 }}>
          {(data || []).map(a => {
            const [bg, fg, label] = SEVERITY[a.severity] || SEVERITY.info;
            return (
              <div key={a.id} style={{ ...card, padding: "12px 16px", display: "flex", gap: 14, alignItems: "flex-start" }}>
                <span style={{ background: bg, color: fg, fontSize: 11, fontWeight: 700, padding: "3px 9px", borderRadius: 100, marginTop: 2 }}>{label}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{a.title}</div>
                  <div style={{ fontSize: 13, color: Z.textSecondary, marginTop: 2, lineHeight: 1.5 }}>{a.detail}</div>
                </div>
                <button onClick={() => onJump(a.tab)} style={btn(false)}>View</button>
              </div>
            );
          })}
        </div>
      )}
    </Loading>
  );
}

// ───────────────────────────────────────────────────────────── History
export function HistoryTab({ app }) {
  const { data, error } = useLoad(`/app-details/${app.id}/history`);
  return (
    <Loading data={data} error={error}>
      <Note tone="blue">History is recorded automatically from now on: assignment changes, syncs, reclamation decisions and edits. Earlier activity isn't available.</Note>
      {data && data.length === 0 ? <Empty>Nothing recorded yet.</Empty> : (
        <div style={{ ...card, overflow: "hidden" }}>
          {(data || []).map((e, i) => (
            <div key={e.id} style={{ display: "flex", gap: 14, padding: "11px 16px", borderTop: i ? `1px solid ${Z.border}` : "none", alignItems: "baseline" }}>
              <span style={{ width: 150, flexShrink: 0, fontSize: 12, color: Z.textMuted }}>{fmtDateTime(e.created_at)}</span>
              <span style={{ width: 110, flexShrink: 0, fontSize: 11, fontWeight: 700, color: Z.textSecondary, textTransform: "uppercase", letterSpacing: "0.04em" }}>{e.kind.replace(/_/g, " ")}</span>
              <span style={{ fontSize: 13 }}>{e.detail}</span>
            </div>
          ))}
        </div>
      )}
    </Loading>
  );
}

// ───────────────────────────────────────────────────────────── Contracts
export function ContractsTab({ app }) {
  const { data, error } = useLoad(`/app-details/${app.id}/contracts`);
  return (
    <Loading data={data} error={error}>
      {data && data.length === 0 ? <Empty>No contracts on file for this app. Add one on the Renewals page.</Empty> : (
        <div style={{ ...card, overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0, minWidth: 900 }}>
            <thead><tr>{["Status", "Start", "End", "Days left", "Auto-renews", "Cancel by", "Value", "Owner", "File"].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
            <tbody>
              {(data || []).map(c => (
                <tr key={c.id}>
                  <td style={{ ...td, textTransform: "capitalize" }}>{String(c.status).replace(/_/g, " ")}</td>
                  <td style={td}>{fmtDate(c.start_date)}</td>
                  <td style={td}>{fmtDate(c.end_date)}</td>
                  <td style={{ ...td, color: c.days_to_end !== null && c.days_to_end <= 30 ? Z.redText : Z.textPrimary, fontWeight: c.days_to_end !== null && c.days_to_end <= 30 ? 700 : 400 }}>
                    {c.days_to_end === null ? "—" : c.days_to_end < 0 ? `${-c.days_to_end} overdue` : c.days_to_end}
                  </td>
                  <td style={td}>{c.auto_renews ? "Yes" : "No"}</td>
                  <td style={td}>{fmtDate(c.cancel_by)}</td>
                  <td style={td}>{money(c.total_value_cents)}</td>
                  <td style={td}>{c.owner_email || "—"}</td>
                  <td style={td}>{c.file_name || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Loading>
  );
}

// ───────────────────────────────────────────────────────────── Savings
export function SavingsTab({ app, onStartWorkflow, onJump }) {
  const { data, error } = useLoad(`/app-details/${app.id}/savings`);
  return (
    <Loading data={data} error={error}>
      {data && (() => {
        const r = data.reclamation, lic = data.licenses[0];
        return (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12, marginBottom: 16 }}>
              <Stat label="Reclaim potential" value={r.potential_cents === null ? "—" : money(r.potential_cents)}
                    sub={r.counted ? `${(r.inactive ?? 0).toLocaleString()} people inactive ${r.inactive_days}+ days` : "Needs a usage source"} />
              <Stat label="In review" value={money(data.in_review.cents)} sub={`${data.in_review.count} people (${data.in_review.approved} approved)`} />
              <Stat label="Reclaimed" value={money(data.reclaimed.cents)} sub={`${data.reclaimed.count} confirmed removals`} tone="good" />
              <Stat label="Unused license cost" value={lic && lic.waste_cost_cents ? money(lic.waste_cost_cents) : "—"} sub={lic && lic.utilization_pct !== null ? `${Math.round(lic.utilization_pct)}% of seats in use` : "No license data"} />
            </div>

            <div style={{ ...card, padding: "16px 18px", marginBottom: 12 }}>
              <h3 style={{ margin: "0 0 6px", fontSize: 15 }}>Inactive people</h3>
              {!r.counted ? (
                <p style={{ margin: 0, fontSize: 13, color: Z.textSecondary, lineHeight: 1.6 }}>
                  Okta sign-ins alone can't show whether people use this app, so no savings estimate is made. Connect a usage source in the Integration Library,
                  or mark Okta sign-ins as trusted for this app on the Reclamation page.
                </p>
              ) : (
                <>
                  <p style={{ margin: "0 0 10px", fontSize: 13, color: Z.textSecondary, lineHeight: 1.6 }}>
                    {(r.inactive ?? 0).toLocaleString()} people haven't been active in {r.inactive_days}+ days (set by this app's activity threshold).
                    {r.per_seat_cents !== null ? ` At about ${money(r.per_seat_cents)} per seat per year, reclaiming them could save ${money(r.potential_cents)}.` : " Import this app's license cost to see the dollar estimate."}
                  </p>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => onJump("users")} style={btn(false)}>See who</button>
                    <button onClick={onStartWorkflow} style={btn(true)}>Start a reclamation workflow</button>
                  </div>
                </>
              )}
            </div>

            <div style={{ ...card, padding: "16px 18px" }}>
              <h3 style={{ margin: "0 0 6px", fontSize: 15 }}>License utilization</h3>
              {!lic ? <p style={{ margin: 0, fontSize: 13, color: Z.textMuted }}>No license on file for this app. Import it on the Licenses page.</p> : (
                <table style={{ borderCollapse: "collapse", fontSize: 13 }}>
                  <tbody>
                    {[["Seats purchased", lic.seats_purchased], ["Seats assigned", lic.seats_assigned], ["Seats active (30 days)", lic.seats_active],
                      ["Annual cost", money(lic.annual_cost_cents)], ["Unused seats", lic.waste_seats]].map(([k, v]) => (
                      <tr key={k}><td style={{ padding: "4px 24px 4px 0", color: Z.textSecondary }}>{k}</td><td style={{ fontWeight: 600 }}>{v === null || v === undefined ? "—" : typeof v === "number" ? v.toLocaleString() : v}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        );
      })()}
    </Loading>
  );
}

// ───────────────────────────────────────────────────────────── Payments
export function PaymentsTab({ app }) {
  const { data, error, reload } = useLoad(`/app-details/${app.id}/payments`);
  const [form, setForm] = useState({ paid_on: new Date().toISOString().slice(0, 10), amount_usd: "", currency: "USD", reference: "", notes: "" });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  async function add() {
    setBusy(true); setErr(null);
    const problem = await send(`/app-details/${app.id}/payments`, form);
    setBusy(false);
    if (problem) { setErr(problem); return; }
    setForm(f => ({ ...f, amount_usd: "", reference: "", notes: "" }));
    reload();
  }
  async function remove(p) {
    if (!window.confirm("Remove this payment record?")) return;
    await send(`/app-details/${app.id}/payments/${p.id}/delete`);
    reload();
  }

  return (
    <Loading data={data} error={error}>
      {data && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12, marginBottom: 16 }}>
            <Stat label="Annual cost" value={money(data.annual_cost_cents)} sub="From the license on file" />
            <Stat label="Paid, last 12 months" value={money(data.paid_last_12_months_cents)} sub="From the payments you've recorded" />
          </div>
          <Note tone="blue">Payments are recorded by hand here (there's no accounting connection yet). “Expected billing” is calculated from the license.</Note>

          {data.expected.length > 0 && (
            <div style={{ ...card, padding: "14px 18px", marginBottom: 12 }}>
              <h3 style={{ margin: "0 0 8px", fontSize: 15 }}>Expected billing</h3>
              {data.expected.map((e, i) => (
                <div key={i} style={{ fontSize: 13, padding: "3px 0" }}>
                  {money(e.amount_cents)} {e.currency} {e.billing_cycle === "monthly" ? "per month" : "per year"}{e.next_billing_date ? `, next on ${fmtDate(e.next_billing_date)}` : ""}
                </div>
              ))}
            </div>
          )}

          <div style={{ ...card, padding: "14px 18px", marginBottom: 12 }}>
            <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>Record a payment</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
              <Labeled label="Date"><input style={input} type="date" value={form.paid_on} onChange={set("paid_on")} /></Labeled>
              <Labeled label="Amount"><input style={input} type="number" min="0" step="0.01" value={form.amount_usd} onChange={set("amount_usd")} placeholder="0.00" /></Labeled>
              <Labeled label="Currency"><input style={input} value={form.currency} onChange={set("currency")} maxLength={3} /></Labeled>
              <Labeled label="Reference"><input style={input} value={form.reference} onChange={set("reference")} placeholder="Invoice number" /></Labeled>
            </div>
            {err && <Note tone="red">{err}</Note>}
            <button onClick={add} disabled={busy} style={btn(true, busy)}>{busy ? "Saving…" : "Add payment"}</button>
          </div>

          {data.payments.length === 0 ? <Empty>No payments recorded yet.</Empty> : (
            <div style={{ ...card, overflow: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
                <thead><tr>{["Date", "Amount", "Reference", ""].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
                <tbody>{data.payments.map(p => (
                  <tr key={p.id}><td style={td}>{fmtDate(p.paid_on)}</td><td style={td}>{money(p.amount_cents)} {p.currency}</td><td style={td}>{p.reference || "—"}</td>
                    <td style={{ ...td, textAlign: "right" }}><button onClick={() => remove(p)} style={btn(false, false, true)}>Remove</button></td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Loading>
  );
}

// ───────────────────────────────────────────────────────────── Documents
const DOC_TYPES = [["contract", "Contract"], ["invoice", "Invoice"], ["security", "Security review"], ["dpa", "DPA"], ["other", "Other"]];

export function DocumentsTab({ app }) {
  const { data, error, reload } = useLoad(`/app-details/${app.id}/documents`);
  const [form, setForm] = useState({ title: "", url: "", doc_type: "contract" });
  const [err, setErr] = useState(null);
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  async function add() {
    setErr(null);
    const problem = await send(`/app-details/${app.id}/documents`, form);
    if (problem) { setErr(problem); return; }
    setForm({ title: "", url: "", doc_type: form.doc_type });
    reload();
  }
  async function remove(d) {
    if (!window.confirm(`Remove “${d.title}”?`)) return;
    await send(`/app-details/${app.id}/documents/${d.id}/delete`);
    reload();
  }

  return (
    <Loading data={data} error={error}>
      <Note tone="blue">Documents are saved as links to where they already live (Google Drive, SharePoint, Notion…), so access stays under your existing permissions.</Note>
      <div style={{ ...card, padding: "14px 18px", marginBottom: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 3fr 1.2fr", gap: 10 }}>
          <Labeled label="Title"><input style={input} value={form.title} onChange={set("title")} placeholder="Master services agreement" /></Labeled>
          <Labeled label="Link"><input style={input} value={form.url} onChange={set("url")} placeholder="https://…" /></Labeled>
          <Labeled label="Type"><select style={input} value={form.doc_type} onChange={set("doc_type")}>{DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Labeled>
        </div>
        {err && <Note tone="red">{err}</Note>}
        <button onClick={add} style={btn(true)}>Add document</button>
      </div>
      {data && data.length === 0 ? <Empty>No documents yet.</Empty> : (
        <div style={{ ...card, overflow: "hidden" }}>
          {(data || []).map((d, i) => (
            <div key={d.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 16px", borderTop: i ? `1px solid ${Z.border}` : "none" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: Z.textSecondary, textTransform: "uppercase", width: 90 }}>{(DOC_TYPES.find(t => t[0] === d.doc_type) || [0, "Other"])[1]}</span>
              <a href={d.url} target="_blank" rel="noopener noreferrer" style={{ flex: 1, fontSize: 14, fontWeight: 600, color: Z.accent }}>{d.title}</a>
              <span style={{ fontSize: 12, color: Z.textMuted }}>{fmtDate(d.created_at)}</span>
              <button onClick={() => remove(d)} style={btn(false, false, true)}>Remove</button>
            </div>
          ))}
        </div>
      )}
    </Loading>
  );
}

// ───────────────────────────────────────────────────────────── Sentiment
export function SentimentTab({ app }) {
  const { data, error, reload } = useLoad(`/app-details/${app.id}/sentiment`);
  const [form, setForm] = useState({ rating: 0, person: "", comment: "" });
  const [err, setErr] = useState(null);

  async function add() {
    setErr(null);
    const problem = await send(`/app-details/${app.id}/sentiment`, form);
    if (problem) { setErr(problem); return; }
    setForm({ rating: 0, person: "", comment: "" });
    reload();
  }
  async function remove(e) {
    if (!window.confirm("Remove this feedback?")) return;
    await send(`/app-details/${app.id}/sentiment/${e.id}/delete`);
    reload();
  }
  const stars = n => "★".repeat(n) + "☆".repeat(5 - n);

  return (
    <Loading data={data} error={error}>
      {data && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(200px, 1fr) 2fr", gap: 12, marginBottom: 14 }}>
            <Stat label="Average rating" value={data.average === null ? "—" : `${data.average} / 5`} sub={`${data.count} piece${data.count === 1 ? "" : "s"} of feedback`} />
            <div style={{ ...card, padding: "12px 16px" }}>
              {[5, 4, 3, 2, 1].map(n => (
                <div key={n} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, marginBottom: 3 }}>
                  <span style={{ width: 14, color: Z.textSecondary }}>{n}</span>
                  <div style={{ flex: 1, background: "#EEF2F7", borderRadius: 4, height: 10 }}>
                    <div style={{ width: `${data.count ? (100 * data.distribution[n]) / data.count : 0}%`, height: 10, borderRadius: 4, background: n >= 4 ? Z.green : n === 3 ? Z.amber : Z.red }} />
                  </div>
                  <span style={{ width: 24, textAlign: "right", color: Z.textMuted }}>{data.distribution[n]}</span>
                </div>
              ))}
            </div>
          </div>
          <Note tone="blue">Feedback is logged by hand (for example from a survey, a Slack thread, or a conversation with the team).</Note>
          <div style={{ ...card, padding: "14px 18px", marginBottom: 12 }}>
            <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
              {[1, 2, 3, 4, 5].map(n => (
                <button key={n} onClick={() => setForm(f => ({ ...f, rating: n }))} aria-label={`${n} out of 5`}
                        style={{ width: 38, height: 34, borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: "pointer", border: `1px solid ${form.rating === n ? Z.accent : Z.border}`, background: form.rating === n ? Z.accentLight : Z.cardBg, color: form.rating === n ? Z.accent : Z.textPrimary }}>{n}</button>
              ))}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 10 }}>
              <Labeled label="From (optional)"><input style={input} value={form.person} onChange={e => setForm(f => ({ ...f, person: e.target.value }))} placeholder="Name or team" /></Labeled>
              <Labeled label="Comment (optional)"><input style={input} value={form.comment} onChange={e => setForm(f => ({ ...f, comment: e.target.value }))} /></Labeled>
            </div>
            {err && <Note tone="red">{err}</Note>}
            <button onClick={add} style={btn(true)}>Log feedback</button>
          </div>
          {data.entries.length === 0 ? <Empty>No feedback logged yet.</Empty> : (
            <div style={{ ...card, overflow: "hidden" }}>
              {data.entries.map((e, i) => (
                <div key={e.id} style={{ display: "flex", gap: 14, padding: "11px 16px", borderTop: i ? `1px solid ${Z.border}` : "none", alignItems: "baseline" }}>
                  <span style={{ color: e.rating >= 4 ? Z.green : e.rating === 3 ? Z.amber : Z.red, letterSpacing: 1 }}>{stars(e.rating)}</span>
                  <span style={{ flex: 1, fontSize: 13 }}>{e.comment || <span style={{ color: Z.textMuted }}>No comment</span>}{e.person ? <span style={{ color: Z.textMuted }}> — {e.person}</span> : null}</span>
                  <span style={{ fontSize: 12, color: Z.textMuted }}>{fmtDate(e.created_at)}</span>
                  <button onClick={() => remove(e)} style={btn(false, false, true)}>Remove</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Loading>
  );
}

// ───────────────────────────────────────────────────────────── App info
const CATEGORY_OPTIONS = [["productivity", "Productivity"], ["communication", "Communication"], ["security", "Security"], ["devtools", "Developer tools"], ["hr", "HR"], ["finance", "Finance"],
                          ["crm", "CRM & sales"], ["marketing", "Marketing"], ["analytics", "Analytics"], ["infrastructure", "Infrastructure"], ["design", "Design"], ["other", "Other"]];
const CATEGORY_LABEL = Object.fromEntries(CATEGORY_OPTIONS);

function CategorizationCard({ app, settings, onSaved }) {
  const info = settings.info, base = settings.base;
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ category: base.category, subcategory: info.subcategory || "", functions: (info.functions || []).join(", ") });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!editing) setForm({ category: base.category, subcategory: info.subcategory || "", functions: (info.functions || []).join(", ") }); }, [base.category, info.subcategory, info.functions, editing]);
  async function save() {
    setBusy(true); setErr(null);
    const problem = await send(`/app-details/${app.id}/settings`, { category: form.category, subcategory: form.subcategory, functions: String(form.functions || "").split(",").map(t => t.trim()).filter(Boolean) });
    setBusy(false);
    if (problem) { setErr(problem); return; }
    setEditing(false); onSaved();
  }
  const heading = text => <div style={{ fontSize: 12, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", margin: "12px 0 4px" }}>{text}</div>;
  return (
    <div style={{ ...card, padding: "14px 18px", gridColumn: "1 / -1" }} data-card="categorization">
      <div style={{ display: "flex", alignItems: "center" }}>
        <h3 style={{ margin: 0, flex: 1, fontSize: 15 }}>Categorization and function</h3>
        {!editing && <button onClick={() => setEditing(true)} aria-label="Edit categorization" title="Edit" style={{ border: "none", background: "none", cursor: "pointer", fontSize: 16, color: Z.textSecondary }}>✎</button>}
      </div>
      {!editing ? (
        <div>
          {heading("Category")}<div style={{ fontSize: 14 }} data-field="category">{CATEGORY_LABEL[base.category] || base.category || "—"}</div>
          {heading("Subcategory")}<div style={{ fontSize: 14 }} data-field="subcategory">{info.subcategory || "—"}</div>
          {heading("Functions")}
          {(info.functions || []).length === 0 ? <div style={{ fontSize: 14, color: Z.textMuted }} data-field="functions">None recorded</div> : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }} data-field="functions">{info.functions.map(f => <span key={f} style={{ background: "#4A5878", color: "#fff", borderRadius: 100, padding: "4px 14px", fontSize: 13, fontWeight: 600 }}>{f}</span>)}</div>)}
        </div>
      ) : (
        <div style={{ marginTop: 10 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <Labeled label="Category"><select aria-label="Category" style={input} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>{CATEGORY_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Labeled>
            <Labeled label="Subcategory"><input aria-label="Subcategory" style={input} value={form.subcategory} onChange={e => setForm(f => ({ ...f, subcategory: e.target.value }))} placeholder="e.g. Accounting & Finance" /></Labeled>
          </div>
          <Labeled label="Functions" hint="What the app is for. Separate several with commas, e.g. Expense Management, Accounting."><input aria-label="Functions" style={input} value={form.functions} onChange={e => setForm(f => ({ ...f, functions: e.target.value }))} /></Labeled>
          {err && <Note tone="red">{err}</Note>}
          <button onClick={save} disabled={busy} style={btn(true)}>{busy ? "Saving…" : "Save"}</button>{" "}<button onClick={() => { setEditing(false); setErr(null); }} style={btn(false)}>Cancel</button>
        </div>
      )}
    </div>
  );
}

export function AppInfoTab({ app, settings, onSaved }) {
  const [form, setForm] = useState(null);
  const [err, setErr] = useState(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (settings) setForm({ ...settings.info, tags: (settings.info.tags || []).join(", "), certifications: (settings.info.certifications || []).join(", ") });
  }, [settings]);
  if (!settings || !form) return <Loading data={null} error={null} />;
  const b = settings.base;
  const set = k => e => { setSaved(false); setForm(f => ({ ...f, [k]: e.target.value })); };

  async function save() {
    setErr(null);
    const payload = { owner_email: form.owner_email || "", business_owner: form.business_owner || "", department: form.department || "",
                      website: form.website || "", description: form.description || "",
                      tags: String(form.tags || "").split(",").map(t => t.trim()).filter(Boolean),
                      certifications: String(form.certifications || "").split(",").map(t => t.trim()).filter(Boolean) };
    const problem = await send(`/app-details/${app.id}/settings`, payload);
    if (problem) { setErr(problem); return; }
    setSaved(true); onSaved();
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(240px, 1fr) 2fr", gap: 14, alignItems: "start" }}>
      <div style={{ ...card, padding: "14px 18px" }}>
        <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>Details</h3>
        {[["Name", b.name], ["Vendor", b.vendor], ["Category", CATEGORY_LABEL[b.category] || b.category], ["Status", String(b.status || "").replace(/_/g, " ")],
          ["First seen", fmtDate(b.first_seen_at)], ["Discovered via", b.discovered_via], ["Shadow IT", b.is_shadow_it ? "Yes" : "No"]].map(([k, v]) => (
          <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 13, padding: "5px 0", borderBottom: `1px solid ${Z.border}` }}>
            <span style={{ color: Z.textSecondary }}>{k}</span><span style={{ fontWeight: 600, textTransform: k === "Status" ? "capitalize" : "none" }}>{v || "—"}</span>
          </div>
        ))}
      </div>
      <div style={{ ...card, padding: "14px 18px" }}>
        <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>Ownership and description</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <Labeled label="Owner (email)"><input style={input} value={form.owner_email || ""} onChange={set("owner_email")} /></Labeled>
          <Labeled label="Business owner"><input style={input} value={form.business_owner || ""} onChange={set("business_owner")} /></Labeled>
          <Labeled label="Department"><input style={input} value={form.department || ""} onChange={set("department")} /></Labeled>
          <Labeled label="Website"><input style={input} value={form.website || ""} onChange={set("website")} placeholder="https://" /></Labeled>
        </div>
        <Labeled label="Description"><textarea style={{ ...input, minHeight: 80, resize: "vertical" }} value={form.description || ""} onChange={set("description")} /></Labeled>
        <Labeled label="Tags" hint="Separate with commas"><input style={input} value={form.tags} onChange={set("tags")} /></Labeled>
        <Labeled label="Certifications / standards" hint="Separate with commas, e.g. SOC 2, ISO 27001, HIPAA. Shown on the Overview tab."><input style={input} value={form.certifications || ""} onChange={set("certifications")} placeholder="SOC 2, ISO 27001" /></Labeled>
        {err && <Note tone="red">{err}</Note>}
        {saved && <Note tone="green">Saved.</Note>}
        <button onClick={save} style={btn(true)}>Save</button>
      </div>
      <CategorizationCard app={app} settings={settings} onSaved={onSaved} />
    </div>
  );
}

// ───────────────────────────────────────────────────────────── Dialogs (header buttons)
function Modal({ title, onClose, children, width = 460 }) {
  useEffect(() => {
    const onKey = e => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(17,24,39,0.45)", zIndex: 300, display: "flex", justifyContent: "center", alignItems: "flex-start", overflowY: "auto", padding: "10vh 1rem" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: Z.cardBg, borderRadius: 14, width: "100%", maxWidth: width, boxShadow: "0 20px 50px rgba(0,0,0,0.25)" }}>
        <div style={{ display: "flex", alignItems: "center", padding: "1rem 1.4rem", borderBottom: `1px solid ${Z.border}` }}>
          <h2 style={{ margin: 0, flex: 1, fontSize: 16, fontWeight: 700 }}>{title}</h2>
          <button onClick={onClose} aria-label="Close" style={{ background: "none", border: "none", fontSize: 24, lineHeight: 1, color: Z.textMuted, cursor: "pointer" }}>×</button>
        </div>
        <div style={{ padding: "1.1rem 1.4rem 1.3rem" }}>{children}</div>
      </div>
    </div>
  );
}

export function ThresholdDialog({ app, settings, onClose, onSaved }) {
  const [days, setDays] = useState(settings ? settings.activity_threshold_days : 30);
  const [err, setErr] = useState(null);
  async function save() {
    setErr(null);
    const problem = await send(`/app-details/${app.id}/settings`, { activity_threshold_days: Number(days) });
    if (problem) { setErr(problem); return; }
    onSaved(); onClose();
  }
  return (
    <Modal title="Activity threshold" onClose={onClose}>
      <p style={{ margin: "0 0 12px", fontSize: 13, color: Z.textSecondary, lineHeight: 1.6 }}>
        A person counts as <strong>active</strong> on this app if they've had activity within this many days. It sets the Active column on the Users tab and the
        inactive count used for savings and alerts.
      </p>
      <Labeled label="Active if activity within (days)" hint="Between 7 and 365. Okta keeps 90 days of sign-ins, so activity beyond that comes only from connected usage sources.">
        <input style={input} type="number" min="7" max="365" value={days} onChange={e => setDays(e.target.value)} autoFocus />
      </Labeled>
      {err && <Note tone="red">{err}</Note>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onClose} style={btn(false)}>Cancel</button><button onClick={save} style={btn(true)}>Save</button>
      </div>
    </Modal>
  );
}

export function NotesDialog({ app, settings, onClose, onSaved }) {
  const [notes, setNotes] = useState(settings ? settings.notes : "");
  const [err, setErr] = useState(null);
  async function save() {
    setErr(null);
    const problem = await send(`/app-details/${app.id}/settings`, { notes });
    if (problem) { setErr(problem); return; }
    onSaved(); onClose();
  }
  return (
    <Modal title={`Notes: ${app.name}`} onClose={onClose} width={560}>
      <textarea value={notes} onChange={e => setNotes(e.target.value)} autoFocus placeholder="Anything the team should know about this app…"
                style={{ ...input, minHeight: 180, resize: "vertical", marginBottom: 12 }} />
      {err && <Note tone="red">{err}</Note>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onClose} style={btn(false)}>Cancel</button><button onClick={save} style={btn(true)}>Save notes</button>
      </div>
    </Modal>
  );
}

export { Modal, Labeled, Note, btn, input, send, Z as palette };
