import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      // The browser only ever talks to this origin; /api is forwarded to the backend,
      // exactly like the reverse proxy does in production (no CORS needed).
      proxy: {
        '/api': { target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000' },
      },
    },
    preview: {
      proxy: {
        '/api': { target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000' },
      },
    },
    build: {
      sourcemap: false,
    },
    test: {
      environment: 'jsdom',
      // Worker threads start reliably everywhere (forked workers time out on some Windows setups).
      pool: 'threads',
      setupFiles: ['./src/test/setup.js'],
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{js,jsx}'],
        exclude: ['src/test/**', 'src/main.jsx'],
        reporter: ['text', 'html'],
        // Enforced by `npm run test:coverage` (and CI).
        thresholds: { statements: 90, branches: 85, functions: 85, lines: 90 },
      },
    },
  }
})
