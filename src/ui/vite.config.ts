import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',   // Expose on all interfaces for LAN access
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:3777',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:3777',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        // Code-split vendor chunks for better caching
        manualChunks: {
          vendor: ['react', 'react-dom'],
        },
      },
    },
  },
});
