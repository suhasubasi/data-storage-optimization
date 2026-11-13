// Real API (contracts/openapi.yaml). Used when VITE_USE_MOCKS=false.
import type { Api } from "./types";
import { ApiError } from "./errors";
import { absUrl } from "./config";

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(absUrl(path), init);
  } catch {
    throw new ApiError("network_error", "Cannot reach the backend on port 8000. Is it running?", 0);
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    if (body === null && res.status >= 500) {
      throw new ApiError("network_error", `The backend did not answer (HTTP ${res.status}). Is it running on port 8000?`, res.status);
    }
    const err = (body as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    throw new ApiError(
      (err?.code as ApiError["code"]) ?? "internal_error",
      err?.message ?? `Request failed with status ${res.status}.`,
      res.status,
      err?.details ?? null,
    );
  }
  return res;
}

const json = async <T>(path: string, init?: RequestInit): Promise<T> => (await request(path, init)).json() as Promise<T>;
const enc = encodeURIComponent;

export const liveApi: Api = {
  health: () => json("/health"),
  listAssets: (owner) => json(`/api/assets${owner ? `?owner=${enc(owner)}` : ""}`),
  getAsset: (id) => json(`/api/assets/${enc(id)}`),
  uploadAsset: (file, sourceSystem, owner) => {
    const form = new FormData();
    form.append("file", file);
    form.append("source_system", sourceSystem);
    form.append("owner", owner);
    return json("/api/assets", { method: "POST", body: form });
  },
  processAsset: (id) => json(`/api/assets/${enc(id)}/process`, { method: "POST" }),
  getJob: (id) => json(`/api/jobs/${enc(id)}`),
  getTimeline: (id) => json(`/api/assets/${enc(id)}/timeline`),
  getSlides: (id) => json(`/api/assets/${enc(id)}/slides`),
  search: (q, limit = 20) => json(`/api/search?q=${enc(q)}&limit=${limit}`),
  getDuplicates: (type) => json(`/api/duplicates${type ? `?type=${type}` : ""}`),
  getStorageReport: () => json("/api/storage/report"),
  getOffboarding: (owner) => json(`/api/offboarding?owner=${enc(owner)}`),
  exportAsset: (id) => json(`/api/assets/${enc(id)}/export`),
  exportJsonl: async () => (await request("/api/export.jsonl")).text(),
};
