import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api is proxied to Flask so the auth cookie stays same-origin (no CORS needed).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    // xfwd adds X-Forwarded-For, so Flask sees each user's real IP (rate limits are per user).
    proxy: { "/api": { target: process.env.API_URL || "http://localhost:5000", xfwd: true } },
  },
});
