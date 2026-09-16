export const APPS = [
  { id: 1, name: "Slack", vendor: "Salesforce", category: "Communication", status: "managed", seats: 320, active: 287, annual: 115200, shadow: false, dept: "All", discovered: "okta" },
  { id: 2, name: "Figma", vendor: "Figma Inc.", category: "Design", status: "managed", seats: 45, active: 38, annual: 27000, shadow: false, dept: "Design", discovered: "azure_ad" },
  { id: 3, name: "Notion", vendor: "Notion Labs", category: "Productivity", status: "managed", seats: 150, active: 102, annual: 36000, shadow: false, dept: "All", discovered: "okta" },
  { id: 4, name: "Zoom", vendor: "Zoom Video", category: "Communication", status: "managed", seats: 300, active: 241, annual: 54000, shadow: false, dept: "All", discovered: "azure_ad" },
  { id: 5, name: "Miro", vendor: "Miro", category: "Productivity", status: "unmanaged", seats: 0, active: 28, annual: 8400, shadow: true, dept: "Product", discovered: "csv" },
  { id: 6, name: "Loom", vendor: "Loom Inc.", category: "Communication", status: "unmanaged", seats: 0, active: 17, annual: 4080, shadow: true, dept: "Engineering", discovered: "csv" },
  { id: 7, name: "Datadog", vendor: "Datadog", category: "DevTools", status: "managed", seats: 40, active: 36, annual: 96000, shadow: false, dept: "Engineering", discovered: "okta" },
  { id: 8, name: "GitHub", vendor: "Microsoft", category: "DevTools", status: "managed", seats: 85, active: 79, annual: 30600, shadow: false, dept: "Engineering", discovered: "azure_ad" },
  { id: 9, name: "HubSpot", vendor: "HubSpot", category: "CRM", status: "managed", seats: 60, active: 41, annual: 48000, shadow: false, dept: "Sales", discovered: "okta" },
  { id: 10, name: "Canva", vendor: "Canva", category: "Design", status: "under_review", seats: 0, active: 22, annual: 5280, shadow: true, dept: "Marketing", discovered: "csv" },
  { id: 11, name: "Asana", vendor: "Asana", category: "Productivity", status: "managed", seats: 120, active: 88, annual: 28800, shadow: false, dept: "All", discovered: "okta" },
  { id: 12, name: "Jira", vendor: "Atlassian", category: "DevTools", status: "managed", seats: 90, active: 84, annual: 32400, shadow: false, dept: "Engineering", discovered: "azure_ad" },
];

export const CONTRACTS = [
  { id: 1, app: "Slack", vendor: "Salesforce", end_date: "2025-01-15", value: 115200, auto_renew: true, notice_days: 60, owner: "sarah@company.com", status: "active" },
  { id: 2, app: "Figma", vendor: "Figma Inc.", end_date: "2025-02-28", value: 27000, auto_renew: false, notice_days: 30, owner: "mike@company.com", status: "active" },
  { id: 3, app: "Datadog", vendor: "Datadog", end_date: "2025-03-31", value: 96000, auto_renew: true, notice_days: 90, owner: "alex@company.com", status: "active" },
  { id: 4, app: "Notion", vendor: "Notion Labs", end_date: "2025-04-15", value: 36000, auto_renew: false, notice_days: 30, owner: "sarah@company.com", status: "active" },
  { id: 5, app: "HubSpot", vendor: "HubSpot", end_date: "2025-06-30", value: 48000, auto_renew: true, notice_days: 60, owner: "james@company.com", status: "active" },
  { id: 6, app: "Zoom", vendor: "Zoom Video", end_date: "2025-08-01", value: 54000, auto_renew: true, notice_days: 30, owner: "sarah@company.com", status: "active" },
  { id: 7, app: "Asana", vendor: "Asana", end_date: "2025-09-15", value: 28800, auto_renew: false, notice_days: 45, owner: "mike@company.com", status: "active" },
  { id: 8, app: "GitHub", vendor: "Microsoft", end_date: "2026-01-01", value: 30600, auto_renew: true, notice_days: 90, owner: "alex@company.com", status: "active" },
];

export const SYNC_JOBS = [
  { id: 1, source: "okta", status: "completed", apps: 187, users: 1240, created: 4, updated: 183, errors: 0, duration: "1m 12s", ran_at: "2025-01-10 09:00" },
  { id: 2, source: "azure_ad", status: "completed", apps: 94, users: 1238, created: 1, updated: 93, errors: 0, duration: "0m 48s", ran_at: "2025-01-10 09:01" },
  { id: 3, source: "csv", status: "completed", apps: 5, users: 0, created: 3, updated: 2, errors: 1, duration: "0m 02s", ran_at: "2025-01-09 14:33" },
  { id: 4, source: "okta", status: "completed", apps: 185, users: 1236, created: 0, updated: 185, errors: 0, duration: "1m 08s", ran_at: "2025-01-09 03:00" },
  { id: 5, source: "azure_ad", status: "failed", apps: 0, users: 0, created: 0, updated: 0, errors: 1, duration: "0m 05s", ran_at: "2025-01-08 21:00" },
];
