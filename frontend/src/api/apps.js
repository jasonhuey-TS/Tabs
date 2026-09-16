import { api } from "./client";

/**
 * Apps API
 * Mirrors GET/POST/PATCH/DELETE /api/v1/apps
 */

export const appsApi = {
  /**
   * List apps with optional filters.
   * @param {{ status?, category?, shadow_it?, department?, search?, skip?, limit? }} params
   */
  list: (params = {}) => api.get("/apps", { params }),

  get: (id) => api.get(`/apps/${id}`),

  create: (data) => api.post("/apps", data),

  update: (id, data) => api.patch(`/apps/${id}`, data),

  delete: (id) => api.delete(`/apps/${id}`),
};
