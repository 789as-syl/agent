import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@shared': path.resolve(__dirname, '../shared'),
        },
    },
    build: {
        rollupOptions: {
            output: {
                manualChunks(id) {
                    if (!id.includes('node_modules'))
                        return;
                    if (id.includes('/node_modules/react/') ||
                        id.includes('/node_modules/react-dom/') ||
                        id.includes('/node_modules/scheduler/')) {
                        return 'vendor-react';
                    }
                    if (id.includes('/node_modules/react-router/') ||
                        id.includes('/node_modules/react-router-dom/')) {
                        return 'vendor-router';
                    }
                    if (id.includes('react-markdown') || id.includes('remark-gfm'))
                        return 'vendor-markdown';
                    if (id.includes('framer-motion'))
                        return 'vendor-motion';
                    if (id.includes('lucide-react'))
                        return 'vendor-icons';
                    return 'vendor';
                },
            },
        },
    },
    server: {
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
        },
    },
});
