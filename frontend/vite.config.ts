import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const contracts = fileURLToPath(new URL("../contracts", import.meta.url));

// Stream 1 reads shared types + fixtures from ../contracts (read-only for Stream 1).
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@contracts": contracts } },
  server: {
    port: 5173,
    fs: { allow: [".", contracts] },
    // When VITE_USE_MOCKS=false, /api and /files are proxied to the FastAPI backend.
    proxy: { "/api": "http://localhost:8000", "/files": "http://localhost:8000", "/health": "http://localhost:8000" },
  },
});
