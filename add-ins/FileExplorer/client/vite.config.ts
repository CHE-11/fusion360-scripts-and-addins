import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Fusion palette hosting wants relative assets and one JS bundle.
export default defineConfig({
  base: './',
  plugins: [
    react({
      babel: {
        plugins: ['styled-jsx/babel'],
      },
    }),
  ],
  server: {
    port: 5176,
  },
  build: {
    outDir: 'dist',
    manifest: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});
