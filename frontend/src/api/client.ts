// The single entry point the screens use. VITE_USE_MOCKS decides mock vs live (src/api/config.ts).
import { USE_MOCKS } from "./config";
import { liveApi } from "./live";
import { mockApi } from "../mocks/mockApi";
import type { Api } from "./types";

export const api: Api = USE_MOCKS ? mockApi : liveApi;
export { ApiError } from "./errors";
