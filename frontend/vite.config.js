import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve('src'),
      "@@": path.resolve(''),
    },
  },
  // base: '/LR-fisica/prueba', 
  base: './',
  plugins: [react()],

})
