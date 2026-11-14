import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const contracts = fileURLToPath(new URL("../contracts", import.meta.url));
const proxy = {
  "/api": "http://127.0.0.1:8000",
  "/files": "http://127.0.0.1:8000",
  "/health": "http://127.0.0.1:8000",
};

// Stream 1 reads shared types from ../contracts (read-only for Stream 1).
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@contracts": contracts } },
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: [".", contracts] },
    // /api, /files and /health are proxied to the FastAPI backend.
    proxy,
  },
  preview: { port: 5173, strictPort: true, proxy },
});
