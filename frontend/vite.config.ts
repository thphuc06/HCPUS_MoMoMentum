import path from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import type { PluginOption } from 'vite'
import { defineConfig } from 'vitest/config'

// `npm run dev:mock` (mode=mock) nạp thêm máy chủ giả ở dev-mocks/. Chế độ khác (dev, build) không bao giờ import nó.
export default defineConfig(async ({ mode }) => {
  const plugins: PluginOption[] = [react(), tailwindcss()]
  // amazon-cognito-identity-js dùng `global` (Node); ở trình duyệt trỏ về globalThis.
  const define: Record<string, string> = { global: 'globalThis' }
  if (mode === 'mock') {
    const { mockPlugin, MOCK_ENV } = await import('./dev-mocks/server/plugin.ts')
    plugins.push(mockPlugin())
    for (const [k, v] of Object.entries(MOCK_ENV)) define[`import.meta.env.${k}`] = JSON.stringify(v)
  }
  return {
    plugins,
    define,
    resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
    build: { target: 'es2023' },
    // Test đọc contracts/ (openapi.yaml, fixtures) nằm ngoài thư mục frontend.
    server: { fs: { allow: [import.meta.dirname, path.resolve(import.meta.dirname, '../contracts')] } },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      css: false,
    },
  }
})
