import { api, uploadFile } from "./client";

export const syncApi = {
  triggerOkta: () => api.post("/sync/okta"),
  triggerAzureAD: () => api.post("/sync/azure-ad"),
  listJobs: (params = {}) => api.get("/sync/jobs", { params }),

  /**
   * Import a CSV file.
   * @param {File} file
   * @param {"apps"|"licenses"|"contracts"} importType
   */
  importCsv: (file, importType) => {
    const form = new FormData();
    form.append("file", file);
    form.append("import_type", importType);
    return uploadFile("/sync/import/csv", form);
  },
};

export const dashboardApi = {
  getStats: () => api.get("/dashboard"),
};

export const authApi = {
  login: (email, password) =>
    api.post("/auth/login", { email, password }),

  refresh: (refreshToken) =>
    api.post("/auth/refresh", { refresh_token: refreshToken }),

  me: () => api.get("/auth/me"),
};
