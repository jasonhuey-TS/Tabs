import { api } from "./client";

export const settingsApi = {
  list: () => api.get("/settings"),

  // Okta
  getOkta: () => api.get("/settings/okta"),
  saveOkta: (data) => api.post("/settings/okta", data),
  testOkta: () => api.post("/settings/okta/test"),
  enableOkta: () => api.post("/settings/okta/enable"),
  disableOkta: () => api.post("/settings/okta/disable"),

  // Azure AD
  getAzure: () => api.get("/settings/azure-ad"),
  saveAzure: (data) => api.post("/settings/azure-ad", data),
  testAzure: () => api.post("/settings/azure-ad/test"),
  enableAzure: () => api.post("/settings/azure-ad/enable"),
  disableAzure: () => api.post("/settings/azure-ad/disable"),
};
