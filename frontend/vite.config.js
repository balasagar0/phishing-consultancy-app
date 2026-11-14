import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run build` writes frontend/dist, which the server serves (one address for the website, the app and the API).
// `npm run dev` serves on http://localhost:5173 and forwards /api to the server on :8080.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "dist", emptyOutDir: true, assetsInlineLimit: 0, sourcemap: false },
  server: { port: 5173, strictPort: true, proxy: { "/api": "http://127.0.0.1:8080" } },
});
