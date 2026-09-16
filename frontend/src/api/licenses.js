import { api } from "./client";

export const licensesApi = {
  list: (params = {}) => api.get("/licenses", { params }),
  get: (id) => api.get(`/licenses/${id}`),
  create: (data) => api.post("/licenses", data),
  update: (id, data) => api.patch(`/licenses/${id}`, data),
};
