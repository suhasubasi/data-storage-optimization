// The single entry point the screens use: the real backend API (no mock mode).
import { liveApi } from "./live";
import type { Api } from "./types";

export const api: Api = liveApi;
export { ApiError } from "./errors";
