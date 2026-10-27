import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Fusion palette hosting wants relative assets.
export default defineConfig({
  base: './',
  plugins: [
    react({
      babel: {
        plugins: ['styled-jsx/babel'],
      },
    }),
  ],
  build: {
    outDir: 'dist',
    manifest: true,
    // Make the output as close to "single bundle" as possible (Fusion palette friendly).
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        // The palette loads this as a classic script beside Fusion's injected
        // bridge. Top-level minified names would land on `window` and can
        // replace Fusion's globals such as `qt`, which carries the web channel
        // that delivers fusionSendData replies.
        format: 'iife',
        inlineDynamicImports: true,
      },
    },
  },
});


