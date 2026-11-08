import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker, VITE_API_PROXY=http://backend:8000; locally it defaults to localhost.
const apiTarget = process.env.VITE_API_PROXY ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    watch: { usePolling: process.env.VITE_USE_POLLING === "true" },
    proxy: { "/api": { target: apiTarget, changeOrigin: true } },
  },
});
