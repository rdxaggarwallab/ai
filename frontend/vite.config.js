import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api is proxied to Flask so the auth cookie stays same-origin (no CORS needed).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    proxy: { "/api": process.env.API_URL || "http://localhost:5000" },
  },
});
