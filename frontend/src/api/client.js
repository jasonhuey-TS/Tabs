/**
 * Base API client
 *
 * - Reads VITE_API_BASE_URL from env (default: http://localhost:8000)
 * - Attaches JWT Bearer token from localStorage on every request
 * - Throws ApiError with status + message on non-2xx responses
 * - Exposes get / post / patch / delete helpers
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  constructor(status, message, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function getToken() {
  return localStorage.getItem("access_token");
}

async function request(method, path, { body, params, signal } = {}) {
  const url = new URL(`${BASE_URL}${API_PREFIX}${path}`);

  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") {
        url.searchParams.set(k, v);
      }
    });
  }

  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url.toString(), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (!res.ok) {
    let detail = null;
    try {
      const json = await res.json();
      detail = json.detail ?? json.message ?? null;
    } catch (_) {}
    throw new ApiError(res.status, detail ?? `HTTP ${res.status}`, detail);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (path, options) => request("GET", path, options),
  post: (path, body, options) => request("POST", path, { body, ...options }),
  patch: (path, body, options) => request("PATCH", path, { body, ...options }),
  delete: (path, options) => request("DELETE", path, options),
};

/**
 * Multipart form upload (for CSV import and contract file upload).
 * Does NOT set Content-Type — browser sets it with the correct boundary.
 */
export async function uploadFile(path, formData) {
  const url = `${BASE_URL}${API_PREFIX}${path}`;
  const token = getToken();
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, { method: "POST", headers, body: formData });
  if (!res.ok) {
    let detail = null;
    try {
      const json = await res.json();
      detail = json.detail ?? null;
    } catch (_) {}
    throw new ApiError(res.status, detail ?? `HTTP ${res.status}`, detail);
  }
  return res.json();
}
