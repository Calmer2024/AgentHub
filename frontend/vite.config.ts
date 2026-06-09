/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

declare const process: {
  argv: string[]
  cwd: () => string
  env: Record<string, string | undefined>
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const devPort = readCliPort()
  const proxyTarget = process.env.VITE_AGENTHUB_PROXY_TARGET
    || env.VITE_AGENTHUB_PROXY_TARGET
    || proxyTargetForMode(mode)
    || proxyTargetForDevPort(devPort)
    || 'http://127.0.0.1:8000'
  const wsProxyTarget = proxyTarget.replace(/^http/i, 'ws')

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: wsProxyTarget,
          ws: true,
          changeOrigin: true,
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/test-setup.ts',
    },
  }
})

function readCliPort(): number | null {
  for (let index = 0; index < process.argv.length; index += 1) {
    const arg = process.argv[index]
    if (arg.indexOf('--port=') === 0) {
      const parsed = Number(arg.slice('--port='.length))
      return isFinite(parsed) ? parsed : null
    }
    if (arg === '--port') {
      const parsed = Number(process.argv[index + 1])
      return isFinite(parsed) ? parsed : null
    }
  }
  return null
}

function proxyTargetForDevPort(port: number | null): string | null {
  if (port === 5174) return 'http://127.0.0.1:8010'
  if (port === 5175) return 'http://127.0.0.1:8020'
  return null
}

function proxyTargetForMode(mode: string): string | null {
  if (mode === 'saas') return 'http://127.0.0.1:8010'
  if (mode === 'mobile') return 'http://127.0.0.1:8020'
  return null
}
