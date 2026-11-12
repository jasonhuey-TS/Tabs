import { useState, useEffect, useRef } from "react";
import { api } from "../api/client";
import AppIcon from "../components/AppIcon";

const Z = {
  accent: "#4B5EDE", orange: "#E8622C", textPrimary: "#1F2937", textSecondary: "#6B7280", textMuted: "#9CA3AF", border: "#E2E8F0", cardBg: "#FFFFFF",
  tableHeader: "#F8FAFC", amberLight: "#FFFBEB", amberText: "#92400E", redLight: "#FEF2F2", redText: "#B91C1C", userBg: "#EEF0FD",
};
const dollars = c => (c === null || c === undefined ? "—" : (c < 0 ? "-$" : "$") + Math.abs(Math.round(c / 100)).toLocaleString("en-US"));
const fmtDate = iso => {
  if (!iso) return "—";
  const d = new Date(String(iso).length === 10 ? `${iso}T12:00:00` : iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};
const cell = (row, c) => {
  const v = row[c.key];
  if (c.type === "money") return dollars(v);
  if (c.type === "int") return v === null || v === undefined ? "—" : Number(v).toLocaleString("en-US");
  if (c.type === "pct") return v === null || v === undefined ? "—" : `${v}%`;
  if (c.type === "date") return fmtDate(v);
  return v === null || v === undefined || v === "" ? "—" : String(v);
};
const rawCell = (row, c) => (c.type === "money" ? (row[c.key] === null || row[c.key] === undefined ? "" : row[c.key] / 100) : row[c.key] ?? "");

function download(name, columns, rows) {
  const q = v => `"${String(v).replace(/"/g, '""')}"`;
  const lines = [columns.map(c => q(c.label)).join(","), ...rows.map(r => columns.map(c => q(rawCell(r, c))).join(","))];
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Plain text only: line breaks, "- " bullets and **bold**. Nothing the assistant says is ever treated as HTML.
function Prose({ text }) {
  const inline = line => String(line).split(/(\*\*[^*]+\*\*)/g).map((part, i) => (/^\*\*[^*]+\*\*$/.test(part) ? <strong key={i}>{part.slice(2, -2)}</strong> : part));
  const lines = String(text || "").split("\n");
  return (
    <div style={{ fontSize: 15, lineHeight: 1.65, color: Z.textPrimary }}>
      {lines.map((l, i) => (/^\s*[-•]\s+/.test(l)
        ? <div key={i} style={{ paddingLeft: 18, textIndent: -14 }}>• {inline(l.replace(/^\s*[-•]\s+/, ""))}</div>
        : l.trim() === "" ? <div key={i} style={{ height: 8 }} /> : <div key={i}>{inline(l)}</div>))}
    </div>
  );
}

function ResultTable({ t }) {
  const [all, setAll] = useState(false);
  const rows = all ? t.rows : t.rows.slice(0, 25);
  return (
    <div data-table={t.title} style={{ border: `1px solid ${Z.border}`, borderRadius: 12, overflow: "hidden", marginTop: 12, background: Z.cardBg }}>
      <div style={{ display: "flex", alignItems: "center", padding: "10px 16px", borderBottom: `1px solid ${Z.border}` }}>
        <div style={{ flex: 1, fontSize: 14, fontWeight: 600, color: "#3F4F6B" }}>{t.title}</div>
        <button onClick={() => download(`${t.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.csv`, t.columns, t.rows)} aria-label={`Export ${t.title}`} title="Export CSV" style={{ border: "none", background: "none", cursor: "pointer", fontSize: 16, color: Z.textSecondary }}>⤓</button>
      </div>
      <div style={{ overflow: "auto", maxHeight: 420 }}>
        <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
          <thead><tr>{t.columns.map(c => (
            <th key={c.key} style={{ position: "sticky", top: 0, background: Z.tableHeader, padding: "9px 16px", textAlign: ["int", "money", "pct"].includes(c.type) ? "right" : "left", fontSize: 11, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: `1px solid ${Z.border}`, whiteSpace: "nowrap" }}>{c.label}</th>))}</tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={i}>{t.columns.map(c => (
              <td key={c.key} style={{ padding: "9px 16px", fontSize: 13.5, borderBottom: `1px solid ${Z.border}`, whiteSpace: "nowrap", textAlign: ["int", "money", "pct"].includes(c.type) ? "right" : "left", color: Z.textPrimary }}>
                {c.type === "app" ? <><AppIcon app={{ id: r.app_id, name: r.name }} size={22} />{r.name}</> : cell(r, c)}
              </td>))}</tr>))}</tbody>
        </table>
      </div>
      <div style={{ padding: "8px 16px", fontSize: 12, color: Z.textMuted, display: "flex", gap: 12 }}>
        <span>{t.total > t.rows.length ? `Showing ${t.rows.length.toLocaleString()} of ${t.total.toLocaleString()}` : `${t.rows.length.toLocaleString()} ${t.rows.length === 1 ? "row" : "rows"}`}{!all && t.rows.length > 25 ? ` · first 25 shown` : ""}</span>
        {t.rows.length > 25 && <button onClick={() => setAll(a => !a)} style={{ background: "none", border: "none", color: Z.accent, fontWeight: 600, cursor: "pointer", fontSize: 12, padding: 0 }}>{all ? "Show fewer" : "Show all"}</button>}
      </div>
    </div>
  );
}

function Message({ m }) {
  if (m.role === "user") {
    return <div style={{ display: "flex", justifyContent: "flex-end", margin: "18px 0 6px" }}><div data-msg="user" style={{ background: Z.userBg, borderRadius: 16, padding: "10px 16px", maxWidth: "75%", fontSize: 15, lineHeight: 1.5, color: Z.textPrimary }}>{m.text}</div></div>;
  }
  return (
    <div data-msg="assistant" style={{ margin: "6px 0 18px" }}>
      {m.error ? <div style={{ background: Z.redLight, border: "1px solid #FECACA", color: Z.redText, borderRadius: 10, padding: "10px 14px", fontSize: 14 }}>{m.text}</div> : (
        <>
          {m.notice && <div data-notice style={{ background: Z.amberLight, border: "1px solid #FDE68A", color: Z.amberText, borderRadius: 10, padding: "8px 14px", fontSize: 13, marginBottom: 8 }}>{m.notice}</div>}
          <Prose text={m.text} />
          {(m.tables || []).map(t => <ResultTable key={t.title} t={t} />)}
          {m.tools && m.tools.length > 0 && <div data-tools style={{ marginTop: 8, fontSize: 12, color: Z.textMuted }}>Looked at: {m.tools.join(", ")}</div>}
        </>
      )}
    </div>
  );
}

function PromptBrowser({ status, onPick, onClose }) {
  const [filter, setFilter] = useState({ kind: "all", value: "" });
  useEffect(() => {
    const onKey = e => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const topics = status.topics || [], outcomes = status.outcomes || [], prompts = status.prompts || [];
  const shown = prompts.filter(p => filter.kind === "all" || (filter.kind === "topic" ? p.topic === filter.value : (p.outcomes || []).includes(filter.value)));
  const navItem = (kind, value, label) => {
    const on = filter.kind === kind && filter.value === value;
    return <button key={`${kind}:${value}`} data-filter={`${kind}:${value}`} aria-pressed={on} onClick={() => setFilter({ kind, value })}
                   style={{ display: "block", width: "100%", textAlign: "left", padding: "10px 16px", margin: "2px 0", borderRadius: 8, border: "none", fontSize: 15, cursor: "pointer", fontFamily: "inherit", background: on ? "#EEF1F6" : "transparent", color: Z.textPrimary, fontWeight: on ? 600 : 400 }}>{label}</button>;
  };
  const heading = t => <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: Z.textSecondary, padding: "0 16px", margin: "22px 0 6px" }}>{t}</div>;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(17,24,39,0.45)", zIndex: 200, display: "flex", justifyContent: "center", alignItems: "flex-start", padding: "5vh 2rem", overflowY: "auto" }}>
      <div data-modal="prompts" role="dialog" aria-label="Prompts" onClick={e => e.stopPropagation()} style={{ background: Z.cardBg, borderRadius: 14, width: "100%", maxWidth: 1100, minHeight: 520, boxShadow: "0 20px 50px rgba(0,0,0,0.25)", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "18px 28px 14px", borderBottom: `1px solid ${Z.border}`, display: "flex", alignItems: "flex-start" }}>
          <div style={{ flex: 1 }}>
            <div><span style={{ fontSize: 24, fontFamily: "Georgia, serif", color: Z.orange }}>✦ Ask Tab</span> <span style={{ fontSize: 20, fontWeight: 600, marginLeft: 8 }}>Prompts</span></div>
            <div style={{ fontSize: 15, color: Z.textSecondary, marginTop: 4 }}>Browse curated prompts designed to help you get started or find inspiration</div>
          </div>
          <button onClick={onClose} aria-label="Close" style={{ background: "none", border: "none", fontSize: 28, lineHeight: 1, color: Z.textSecondary, cursor: "pointer" }}>×</button>
        </div>
        <div style={{ display: "flex", flex: 1 }}>
          <div style={{ width: 250, borderRight: `1px solid ${Z.border}`, padding: "18px 12px", flexShrink: 0 }}>
            {navItem("all", "", "All")}{heading("Outcomes")}{outcomes.map(o => navItem("outcome", o, o))}{heading("Topics")}{topics.map(t => navItem("topic", t, t))}
          </div>
          <div style={{ flex: 1, padding: "18px 28px 28px", maxHeight: "70vh", overflowY: "auto" }}>
            {topics.map(t => {
              const group = shown.filter(p => p.topic === t);
              if (!group.length) return null;
              return (
                <div key={t} data-topic={t} style={{ marginBottom: 26 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: Z.textSecondary, margin: "6px 0 12px" }}>{t}</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                    {group.map(p => (
                      <button key={p.id} data-browse-item={p.id} data-unavailable={p.available ? undefined : "true"} disabled={!p.available} onClick={() => onPick(p)}
                              style={{ display: "flex", flexDirection: "column", justifyContent: "flex-start", textAlign: "left", background: p.available ? Z.cardBg : "#F9FAFB", border: `1px solid ${Z.border}`, borderRadius: 12, padding: "16px 18px", cursor: p.available ? "pointer" : "not-allowed", fontFamily: "inherit", opacity: p.available ? 1 : 0.75 }}>
                        <div style={{ fontSize: 16, fontWeight: 600, color: Z.textPrimary }}>{p.title}</div>
                        <div style={{ fontSize: 14, color: Z.textSecondary, marginTop: 4, lineHeight: 1.45 }}>{p.description}</div>
                        {!p.available && <div style={{ fontSize: 12.5, color: Z.amberText, marginTop: 8, lineHeight: 1.4 }}>Not available yet: {p.reason}</div>}
                      </button>))}
                  </div>
                </div>);
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Assistant() {
  const [status, setStatus] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [browse, setBrowse] = useState(false);          // the prompt browser is open
  const bottom = useRef(null);

  useEffect(() => { api.get("/assistant/status").then(setStatus).catch(() => setStatus({ ai_enabled: false, prompts: [] })); }, []);
  useEffect(() => { if (bottom.current && bottom.current.scrollIntoView) bottom.current.scrollIntoView({ block: "end" }); }, [messages, busy]);

  const history = list => list.map(m => ({ role: m.role, content: m.text })).filter(m => m.content);
  const push = (...ms) => setMessages(prev => [...prev, ...ms]);
  const reply = r => ({ role: "assistant", text: r.ok === false ? r.error || "Something went wrong." : r.answer, error: r.ok === false, tables: r.tables || [], tools: r.tools_used || [], notice: r.notice });

  async function send(text) {
    const q = String(text || "").trim();
    if (!q || busy) return;
    const next = [...messages, { role: "user", text: q }];
    setMessages(next); setInput(""); setBrowse(false); setBusy(true);
    try { push(reply(await api.post("/assistant/chat", { messages: history(next) }))); }
    catch (e) { push({ role: "assistant", text: e.message || "I couldn't reach Tab just now.", error: true }); }
    finally { setBusy(false); }
  }
  async function runPrompt(p) {
    if (busy || p.available === false) return;
    setMessages(prev => [...prev, { role: "user", text: p.title }]); setBrowse(false); setBusy(true);
    try { push(reply(await api.post("/assistant/run", { tool: p.tool, args: p.args || {} }))); }
    catch (e) { push({ role: "assistant", text: e.message || "I couldn't reach Tab just now.", error: true }); }
    finally { setBusy(false); }
  }

  const prompts = (status && status.prompts) || [];
  const starters = prompts.filter(p => p.starter).sort((a, b) => a.starter - b.starter);
  const started = messages.length > 0;
  const box = (
    <div style={{ display: "flex", alignItems: "center", gap: 10, border: `2px solid #4A5878`, borderRadius: 40, padding: "6px 8px 6px 22px", background: Z.cardBg }}>
      <input aria-label="Ask Tab" value={input} maxLength={1500} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); send(input); } }}
             placeholder="Ask Tab…" disabled={busy} style={{ flex: 1, border: "none", outline: "none", fontSize: 16, padding: "12px 0", background: "transparent", fontFamily: "inherit" }} />
      <button onClick={() => send(input)} disabled={busy || !input.trim()} style={{ border: "none", background: "none", fontSize: 15, fontWeight: 700, color: busy || !input.trim() ? Z.textMuted : "#3F4F6B", cursor: busy || !input.trim() ? "default" : "pointer", padding: "10px 16px" }}>Submit ›</button>
    </div>
  );
  const modeNote = status && (
    <div data-mode={status.ai_enabled ? "ai" : "basic"} style={{ fontSize: 12.5, color: Z.textMuted, textAlign: "center", marginTop: 10, lineHeight: 1.6 }}>
      {status.ai_enabled
        ? "Answers come from your Tab data. Questions are answered by AI using summaries only — never people's names or emails."
        : "Basic mode: I understand questions about unused licenses, ex-employees, contracts, spend, renewals and owners. An admin can turn on AI for any question by setting ANTHROPIC_API_KEY."}
    </div>
  );

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: started ? "0 0 24px" : "0" }}>
      {!started ? (
        <div style={{ paddingTop: "7vh" }}>
          <div style={{ textAlign: "center", marginBottom: 36 }}>
            <div style={{ fontSize: 52, fontFamily: "Georgia, 'Times New Roman', serif", color: Z.orange, letterSpacing: "-0.02em" }}><span style={{ fontSize: 34, marginRight: 10 }}>✦</span>Ask Tab</div>
            <h1 style={{ margin: "34px auto 0", maxWidth: 640, fontSize: 32, fontWeight: 400, lineHeight: 1.35, color: Z.textPrimary }}>Let's get more value out of your SaaS stack. What's first?</h1>
          </div>
          <div style={{ maxWidth: 760, margin: "0 auto" }}>
            {box}{modeNote}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 34 }}>
              {starters.map(p => (
                <button key={p.id} data-prompt={p.id} onClick={() => runPrompt(p)} style={{ textAlign: "left", background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, padding: "18px 20px", cursor: "pointer", fontFamily: "inherit" }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: Z.textPrimary }}>{p.title}</div>
                  <div style={{ fontSize: 14, color: Z.textSecondary, marginTop: 6, lineHeight: 1.45 }}>{p.description}</div>
                </button>))}
              <button data-prompt="browse" onClick={() => setBrowse(true)} aria-haspopup="dialog" style={{ textAlign: "left", background: Z.cardBg, border: `1px solid ${Z.border}`, borderRadius: 12, padding: "18px 20px", cursor: "pointer", fontFamily: "inherit" }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: Z.textPrimary }}>Browse all prompts</div>
                <div style={{ fontSize: 14, color: Z.textSecondary, marginTop: 6 }}>Ready-made questions to ask.</div>
              </button>
            </div>
          </div>
        </div>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "center", padding: "4px 0 10px" }}>
            <div style={{ flex: 1, fontSize: 20, fontFamily: "Georgia, serif", color: Z.orange }}>✦ Ask Tab</div>
            <button onClick={() => setBrowse(true)} style={{ border: `1px solid ${Z.border}`, background: Z.cardBg, borderRadius: 8, padding: "6px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer", marginRight: 8 }}>Prompts</button>
            <button onClick={() => { setMessages([]); setInput(""); }} style={{ border: `1px solid ${Z.border}`, background: Z.cardBg, borderRadius: 8, padding: "6px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>New chat</button>
          </div>
          <div data-thread>{messages.map((m, i) => <Message key={i} m={m} />)}
            {busy && <div data-busy style={{ fontSize: 14, color: Z.textMuted, margin: "6px 0 18px" }}>Looking at your data…</div>}
            <div ref={bottom} />
          </div>
          <div style={{ position: "sticky", bottom: 12, background: "#F4F6FA", paddingTop: 8 }}>{box}{modeNote}</div>
        </>
      )}
      {browse && status && <PromptBrowser status={status} onPick={runPrompt} onClose={() => setBrowse(false)} />}
    </div>
  );
}
