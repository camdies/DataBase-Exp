import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  css: { preprocessorOptions: { scss: { api: 'modern-compiler' } } },
  server: { proxy: { '/api': 'http://127.0.0.1:5001' } },
  build: { rollupOptions: { output: { manualChunks: { 'element-plus': ['element-plus'], vue: ['vue', 'pinia', 'vue-router'] } } } },
})
