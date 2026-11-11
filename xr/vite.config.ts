// Reachoreo 3D rehearsal. `npm run build` writes into the dashboard's static folder, served at /rehearse.
// `npm run dev` runs Vite with the dashboard (port 8080) behind it for /static, /api and /library.
import { defineConfig } from "vite";

const dashboard = "http://localhost:8080";
export default defineConfig({
  base: "/static/rehearse/",
  build: {
    outDir: "../reachy_dance/dashboard/static/rehearse",
    emptyOutDir: true,
    target: "es2022",
    rollupOptions: {
      // the choreography stays one generated module (tools/build_stage_js.py), loaded at run time, not bundled
      external: [/^\/static\/(encendido-stage|nav)\.mjs$/],
    },
  },
  server: { proxy: { "/static/encendido-stage.mjs": dashboard, "/api": dashboard, "/library": dashboard } },
});
