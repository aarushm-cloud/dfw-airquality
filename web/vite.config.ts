import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// `strictPort` makes the dev server fail loudly when 5173 is taken instead
// of silently falling back to 5174 — important because the backend's CORS
// allowlist is pinned to 5173.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    strictPort: true,
  },
});
