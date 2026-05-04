import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.js'],
    // Restrict the unit/component suite to ./tests so vitest doesn't try to
    // execute Playwright specs under ./e2e (their `*.spec.js` extension would
    // otherwise match vitest's default include glob).
    include: ['tests/**/*.{test,spec}.{js,jsx,ts,tsx}'],
    exclude: ['node_modules/**', 'dist/**', 'e2e/**', 'test-results/**', 'playwright-report/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/api/**', 'src/stores/**', 'src/components/**', 'src/views/**'],
    },
  },
})
