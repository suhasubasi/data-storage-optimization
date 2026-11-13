// The ONE switch between mock data and the real API (design Page: "switch by changing one base URL").
export const USE_MOCKS = (import.meta.env.VITE_USE_MOCKS ?? "true") !== "false";
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

/** URLs in API bodies are relative ("/files/..."); prefix them with this. */
export const absUrl = (path: string) => `${API_BASE_URL}${path}`;
