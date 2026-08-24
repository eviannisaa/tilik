// @ts-check
import { defineConfig } from "astro/config";
import solid from "@astrojs/solid-js";
import tailwindcss from "@tailwindcss/vite";

// Tilik ships as a static frontend. The API lives beside it as a Python
// serverless function (see `api/` + `vercel.json`), so no Astro adapter is
// needed and the whole site can be served from the edge.
export default defineConfig({
  output: "static",
  integrations: [solid()],
  vite: {
    plugins: [tailwindcss()],
    // MapLibre spawns its worker with `{ type: "module" }`, so emit ESM.
    worker: { format: "es" },
    server: {
      // During `astro dev`, forward /api/* to the locally running FastAPI
      // process so the frontend talks to the same-origin paths it uses in prod.
      proxy: {
        "/api": {
          target: process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  },
});
