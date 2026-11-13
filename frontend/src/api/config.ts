// The ONE switch between mock data and the real API (design Page: "switch by changing one base URL").
export const USE_MOCKS = (import.meta.env.VITE_USE_MOCKS ?? "true") !== "false";
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

/** URLs in API bodies are relative ("/files/..."); prefix them with this. */
export const absUrl = (path: string) => `${API_BASE_URL}${path}`;

/** Download links built on request by the backend from the real derived files (live mode only). */
export const exportUrls = (assetId: string) => {
  const id = encodeURIComponent(assetId);
  return {
    txt: absUrl(`/api/assets/${id}/transcript.txt`),
    txtPlain: absUrl(`/api/assets/${id}/transcript.txt?timestamps=false`),
    pptx: absUrl(`/api/assets/${id}/slides.pptx`),
    pdf: absUrl(`/api/assets/${id}/slides.pdf`),
    json: absUrl(`/api/assets/${id}/export`),
  };
};
