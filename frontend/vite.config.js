/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, process.cwd(), '');
    var devPort = readCliPort();
    var proxyTarget = process.env.VITE_AGENTHUB_PROXY_TARGET
        || env.VITE_AGENTHUB_PROXY_TARGET
        || proxyTargetForMode(mode)
        || proxyTargetForDevPort(devPort)
        || 'http://127.0.0.1:8000';
    var wsProxyTarget = proxyTarget.replace(/^http/i, 'ws');
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
    };
});
function readCliPort() {
    for (var index = 0; index < process.argv.length; index += 1) {
        var arg = process.argv[index];
        if (arg.indexOf('--port=') === 0) {
            var parsed = Number(arg.slice('--port='.length));
            return isFinite(parsed) ? parsed : null;
        }
        if (arg === '--port') {
            var parsed = Number(process.argv[index + 1]);
            return isFinite(parsed) ? parsed : null;
        }
    }
    return null;
}
function proxyTargetForDevPort(port) {
    if (port === 5174)
        return 'http://127.0.0.1:8010';
    if (port === 5175)
        return 'http://127.0.0.1:8020';
    return null;
}
function proxyTargetForMode(mode) {
    if (mode === 'saas')
        return 'http://127.0.0.1:8010';
    if (mode === 'mobile')
        return 'http://127.0.0.1:8020';
    return null;
}
