// The Users tab's filter engine: which fields can be filtered, how each kind of filter is applied, and how to describe one in words.
// No React in here, so every rule can be tested on its own.
//
// A filter on a field is either
//   - a list of ticked values      ["Sales", "(blank)"]            for fields with a set of values (and yes/no)
//   - or {op, value, value2}       {op: "gte", value: 5}           for text, numbers and dates
// Saved filters from before this existed are lists, and still work.

const DAY = 86400000;
const BLANK = "(blank)";

export const NUMBER_OPS = [["gte", "At least"], ["lte", "At most"], ["eq", "Exactly"], ["between", "Between"], ["blank", "Has no value"]];
export const DATE_OPS = [["last_days", "In the last"], ["older_days", "More than … ago"], ["before", "Before"], ["after", "After"], ["between", "Between"], ["blank", "Has no date"]];

const isBlank = v => v === null || v === undefined || v === "";

// What each built-in column is, where its data comes from, and how it can be filtered.
const BUILT_IN = {
  email: { type: "text", from: "okta" }, first_name: { type: "text", from: "roster" }, last_name: { type: "text", from: "roster" },
  title: { type: "enum", from: "roster" }, department: { type: "enum", from: "roster" }, division: { type: "enum", from: "roster" },
  cost_center: { type: "enum", from: "roster" }, employee_type: { type: "enum", from: "roster" }, organization: { type: "enum", from: "roster" },
  external_status: { type: "enum", from: "okta" }, external_user_id: { type: "text", from: "okta" }, assigned_on: { type: "date", from: "okta" },
  in_roster: { type: "bool", from: "hr" }, last_activity: { type: "date", from: "activity" }, days_since: { type: "number", from: "activity" },
  days_active: { type: "number", from: "activity" }, active: { type: "bool", from: "activity" }, license: { type: "enum", from: "license" },
};

/** The fields this app's people can be filtered on, in a sensible order, each with its source label.
 *  columns: the Users tab's column definitions ({id, label, needs?}); data: the activity payload (attribute_fields, attribute_source, signal ...). */
export function buildFields(columns, data) {
  const integration = (data && data.attribute_source) || null;
  const activitySource = data && data.signal && data.signal !== "okta" && integration ? integration : "Okta";
  const sources = { okta: "Okta", roster: "Employee Roster (Okta)", hr: "Employee Roster (uploaded)", activity: activitySource, license: integration || "Okta" };
  const out = [];
  for (const c of columns) {
    const meta = BUILT_IN[c.id];
    if (!meta) continue;
    out.push({ key: c.id, label: c.label, source: sources[meta.from], type: meta.type, get: u => u[c.id] });
  }
  for (const f of (data && data.attribute_fields) || []) {
    const type = ["text", "enum", "number", "date", "bool"].includes(f.type) ? f.type : "text";
    out.push({ key: `attr_${f.key}`, label: f.label, source: integration || "Direct Integration", type, get: u => u[`attr_${f.key}`] });
  }
  return out;
}

/** The text used to tick a value in a list: Yes / No for yes-no fields, "(blank)" for nothing. */
export function facet(field, value) {
  if (field.type === "bool") return value === true ? "Yes" : value === false ? "No" : BLANK;
  return isBlank(value) ? BLANK : String(value);
}

/** Every value a list field takes among these people, most common first, with how many people have it. */
export function distinctValues(field, users) {
  const m = {};
  users.forEach(u => { const v = facet(field, field.get(u)); m[v] = (m[v] || 0) + 1; });
  return Object.entries(m).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

const num = v => (isBlank(v) ? NaN : Number(v));
const dayStart = s => new Date(`${s}T00:00:00`).getTime();

/** Is this filter complete enough to apply? (A half-filled editor shouldn't hide everyone.) */
export function isActive(spec) {
  if (Array.isArray(spec)) return spec.length > 0;
  if (!spec || typeof spec !== "object") return false;
  if (spec.op === "blank") return true;
  if (spec.op === "contains") return String(spec.value || "").trim() !== "";
  if (spec.op === "between") return spec.value !== "" && spec.value !== undefined && spec.value2 !== "" && spec.value2 !== undefined && spec.value !== null && spec.value2 !== null;
  if (["last_days", "older_days", "gte", "lte", "eq"].includes(spec.op)) return !Number.isNaN(num(spec.value));
  if (["before", "after"].includes(spec.op)) return Boolean(spec.value);
  return false;
}

/** Does this person pass this filter? */
export function matches(field, spec, user, now = Date.now()) {
  if (!isActive(spec)) return true;
  const v = field.get(user);
  if (Array.isArray(spec)) return spec.includes(facet(field, v));
  if (spec.op === "blank") return isBlank(v);
  if (field.type === "text" || spec.op === "contains") return String(v ?? "").toLowerCase().includes(String(spec.value).trim().toLowerCase());
  if (isBlank(v)) return false;
  if (field.type === "number") {
    const n = Number(v), a = num(spec.value), b = num(spec.value2);
    if (spec.op === "gte") return n >= a;
    if (spec.op === "lte") return n <= a;
    if (spec.op === "eq") return n === a;
    if (spec.op === "between") return n >= Math.min(a, b) && n <= Math.max(a, b);
    return true;
  }
  if (field.type === "date") {
    const t = new Date(v).getTime();
    if (Number.isNaN(t)) return false;
    if (spec.op === "last_days") return now - t <= num(spec.value) * DAY && t <= now + DAY;
    if (spec.op === "older_days") return now - t > num(spec.value) * DAY;
    if (spec.op === "before") return t < dayStart(spec.value);
    if (spec.op === "after") return t >= dayStart(spec.value) + DAY;
    if (spec.op === "between") { const lo = Math.min(dayStart(spec.value), dayStart(spec.value2)), hi = Math.max(dayStart(spec.value), dayStart(spec.value2)); return t >= lo && t < hi + DAY; }
  }
  return true;
}

const fmtDay = s => new Date(`${s}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

/** A filter in words, for the chips and the list: "Sales, Marketing", "at least 5", "in the last 30 days". */
export function describe(field, spec) {
  if (Array.isArray(spec)) return spec.length <= 3 ? spec.join(", ") : `${spec.slice(0, 2).join(", ")} +${spec.length - 2} more`;
  if (!spec) return "";
  const n = x => Number(x).toLocaleString("en-US");
  switch (spec.op) {
    case "blank": return field.type === "date" ? "no date" : "no value";
    case "contains": return `contains “${String(spec.value).trim()}”`;
    case "gte": return `at least ${n(spec.value)}`;
    case "lte": return `at most ${n(spec.value)}`;
    case "eq": return `exactly ${n(spec.value)}`;
    case "between": return field.type === "date" ? `${fmtDay(spec.value)} – ${fmtDay(spec.value2)}` : `${n(spec.value)} – ${n(spec.value2)}`;
    case "last_days": return `in the last ${n(spec.value)} days`;
    case "older_days": return `more than ${n(spec.value)} days ago`;
    case "before": return `before ${fmtDay(spec.value)}`;
    case "after": return `after ${fmtDay(spec.value)}`;
    default: return "";
  }
}

/** The filters that actually do something, as [field, spec] pairs (filters on fields this app doesn't have are ignored). */
export function activeFilters(fields, filters) {
  const byKey = Object.fromEntries(fields.map(f => [f.key, f]));
  return Object.entries(filters || {}).filter(([k, spec]) => byKey[k] && isActive(spec)).map(([k, spec]) => [byKey[k], spec]);
}

/** Apply every active filter. */
export function applyFilters(fields, filters, users, now = Date.now()) {
  const active = activeFilters(fields, filters);
  return active.length ? users.filter(u => active.every(([f, spec]) => matches(f, spec, u, now))) : users;
}

/** A sensible empty filter to start editing a field with. */
export function blankSpec(field) {
  if (field.type === "text") return { op: "contains", value: "" };
  if (field.type === "number") return { op: "gte", value: "" };
  if (field.type === "date") return { op: "last_days", value: "" };
  return [];
}
