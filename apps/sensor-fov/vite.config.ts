import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  base: '/sensor-fov/',
  build: { outDir: '.generated/static', emptyOutDir: true },
})
