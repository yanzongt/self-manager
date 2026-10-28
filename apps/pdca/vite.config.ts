import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  base: '/pdca/',
  plugins: [vue()],
  build: { outDir: '.generated/static', emptyOutDir: true },
})
