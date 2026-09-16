import { api, uploadFile } from "./client";

export const contractsApi = {
  /**
   * @param {{ app_id?, status?, expiring_within_days? }} params
   */
  list: (params = {}) => api.get("/contracts", { params }),

  get: (id) => api.get(`/contracts/${id}`),

  create: (data) => api.post("/contracts", data),

  update: (id, data) => api.patch(`/contracts/${id}`, data),

  /**
   * Upload a PDF file and attach it to a contract.
   * @param {string} contractId
   * @param {File} file
   */
  uploadFile: (contractId, file) => {
    const form = new FormData();
    form.append("file", file);
    return uploadFile(`/contracts/${contractId}/upload`, form);
  },
};
