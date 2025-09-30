import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Allow importing from the sdk-ts root (../../..) so we can import from ../../../src
export default defineConfig({
  plugins: [react()],
  server: {
    fs: {
      allow: [
        resolve(__dirname, '../../..'), // sdk-ts root
      ],
    },
  },
  resolve: {
    alias: {
      '@sdk': resolve(__dirname, '../../../src'),
    },
  },
});
