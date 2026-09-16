import { useState, useRef } from "react";
import { useImportCsv } from "../hooks";

const Z = {
  navy: "#1B2A4A",
  accent: "#4B5EDE",
  accentLight: "#EEF0FD",
  border: "#E2E8F0",
  borderStrong: "#CBD5E1",
  cardBg: "#FFFFFF",
  pageBg: "#F4F6FA",
  textPrimary: "#111827",
  textSecondary: "#6B7280",
  textMuted: "#9CA3AF",
  green: "#16A34A",
  greenLight: "#F0FDF4",
  red: "#DC2626",
  redLight: "#FEF2F2",
  redText: "#B91C1C",
};

const IMPORT_TYPES = [
  { value: "apps", label: "Applications", desc: "name, vendor, category, status, owner_email, department, website" },
  { value: "licenses", label: "Licenses", desc: "app_name, license_type, seats_purchased, cost_per_seat_cents, total_annual_cost_cents, currency" },
  { value: "contracts", label: "Contracts", desc: "app_name, start_date, end_date, auto_renews, cancellation_notice_days, total_value_cents, owner_email" },
];

export default function ImportModal({ onClose }) {
  const [importType, setImportType] = useState("apps");
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef();
  const { mutate, isPending, data, error, reset } = useImportCsv();

  function handleFile(f) {
    if (f && f.name.endsWith(".csv")) setFile(f);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    handleFile(e.dataTransfer.files[0]);
  }

  function handleSubmit() {
    if (!file) return;
    mutate({ file, importType });
  }

  const selectedType = IMPORT_TYPES.find(t => t.value === importType);

  return (
    // Backdrop
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: Z.cardBg, borderRadius: 12, border: `1px solid ${Z.border}`,
        width: 520, maxWidth: "90vw", boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
        overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{ padding: "1.25rem 1.5rem", borderBottom: `1px solid ${Z.border}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: Z.textPrimary }}>Import CSV</h2>
            <p style={{ margin: "2px 0 0", fontSize: 12, color: Z.textMuted }}>Bulk-import apps, licenses, or contracts</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: Z.textMuted, padding: 4, borderRadius: 6 }}>
            <i className="ti ti-x" style={{ fontSize: 18 }} aria-hidden="true" />
          </button>
        </div>

        <div style={{ padding: "1.5rem" }}>
          {data ? (
            // Success state
            <div style={{ textAlign: "center", padding: "1rem 0" }}>
              <div style={{ width: 48, height: 48, borderRadius: "50%", background: Z.greenLight, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1rem" }}>
                <i className="ti ti-check" style={{ fontSize: 24, color: Z.green }} aria-hidden="true" />
              </div>
              <p style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 700, color: Z.textPrimary }}>Import complete</p>
              <p style={{ margin: "0 0 1.5rem", fontSize: 13, color: Z.textSecondary }}>
                {data.rows_imported} rows imported · {data.rows_skipped} skipped · {data.rows_errored} errors
              </p>
              {data.errors?.length > 0 && (
                <div style={{ background: Z.redLight, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem", textAlign: "left" }}>
                  <p style={{ margin: "0 0 6px", fontSize: 12, fontWeight: 700, color: Z.redText }}>Row errors</p>
                  {data.errors.slice(0, 5).map((e, i) => (
                    <p key={i} style={{ margin: "2px 0", fontSize: 12, color: Z.redText }}>Row {e.row}: {e.message}</p>
                  ))}
                </div>
              )}
              <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
                <button onClick={() => { reset(); setFile(null); }} style={{ padding: "8px 16px", borderRadius: 8, border: `1px solid ${Z.borderStrong}`, background: "transparent", color: Z.textPrimary, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Import another</button>
                <button onClick={onClose} style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: Z.accent, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Done</button>
              </div>
            </div>
          ) : (
            <>
              {/* Import type selector */}
              <div style={{ marginBottom: "1.25rem" }}>
                <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: Z.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Import type</label>
                <div style={{ display: "flex", gap: 8 }}>
                  {IMPORT_TYPES.map(t => (
                    <button key={t.value} onClick={() => setImportType(t.value)} style={{
                      flex: 1, padding: "8px 12px", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600,
                      border: `1.5px solid ${importType === t.value ? Z.accent : Z.border}`,
                      background: importType === t.value ? Z.accentLight : "transparent",
                      color: importType === t.value ? Z.accent : Z.textSecondary,
                      transition: "all 0.1s",
                    }}>{t.label}</button>
                  ))}
                </div>
                <p style={{ margin: "8px 0 0", fontSize: 11, color: Z.textMuted, fontFamily: "monospace" }}>
                  Columns: {selectedType.desc}
                </p>
              </div>

              {/* File drop zone */}
              <div
                onClick={() => fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                style={{
                  border: `2px dashed ${dragOver ? Z.accent : file ? Z.green : Z.borderStrong}`,
                  borderRadius: 10, padding: "2rem", textAlign: "center", cursor: "pointer",
                  background: dragOver ? Z.accentLight : file ? Z.greenLight : Z.pageBg,
                  transition: "all 0.15s", marginBottom: "1.25rem",
                }}>
                <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={e => handleFile(e.target.files[0])} />
                {file ? (
                  <>
                    <i className="ti ti-file-check" style={{ fontSize: 28, color: Z.green }} aria-hidden="true" />
                    <p style={{ margin: "8px 0 0", fontSize: 14, fontWeight: 600, color: Z.textPrimary }}>{file.name}</p>
                    <p style={{ margin: "2px 0 0", fontSize: 12, color: Z.textMuted }}>{(file.size / 1024).toFixed(1)} KB · click to replace</p>
                  </>
                ) : (
                  <>
                    <i className="ti ti-upload" style={{ fontSize: 28, color: Z.textMuted }} aria-hidden="true" />
                    <p style={{ margin: "8px 0 0", fontSize: 14, fontWeight: 600, color: Z.textSecondary }}>Drop a CSV file here</p>
                    <p style={{ margin: "2px 0 0", fontSize: 12, color: Z.textMuted }}>or click to browse</p>
                  </>
                )}
              </div>

              {/* Error */}
              {error && (
                <div style={{ background: Z.redLight, border: `1px solid #FECACA`, borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem" }}>
                  <p style={{ margin: 0, fontSize: 13, color: Z.redText }}>{error.detail ?? error.message}</p>
                </div>
              )}

              {/* Actions */}
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button onClick={onClose} style={{ padding: "8px 16px", borderRadius: 8, border: `1px solid ${Z.borderStrong}`, background: "transparent", color: Z.textPrimary, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Cancel</button>
                <button
                  onClick={handleSubmit}
                  disabled={!file || isPending}
                  style={{
                    padding: "8px 20px", borderRadius: 8, border: "none",
                    background: file && !isPending ? Z.accent : "#A5B4FC",
                    color: "#fff", fontSize: 13, fontWeight: 600,
                    cursor: file && !isPending ? "pointer" : "not-allowed",
                  }}>
                  {isPending ? "Importing…" : "Import"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
