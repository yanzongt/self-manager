import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
  base: "/checkins/",
  plugins: [vue()],
  build: { outDir: ".generated/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
