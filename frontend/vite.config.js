import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  const parseAllowedHosts = (raw) =>
    (raw || "")
      .split(",")
      .map((h) => h.trim())
      .filter(Boolean);

  const allowedHosts = parseAllowedHosts(env.VITE_ALLOWED_HOSTS);
  const devHost = env.VITE_DEV_HOST || "0.0.0.0";
  const devPort = Number(env.VITE_DEV_PORT || 5173);
  const previewHost = env.VITE_PREVIEW_HOST || "0.0.0.0";
  const previewPort = Number(env.VITE_PREVIEW_PORT || 4173);
  const mineradioTarget = env.VITE_MINERADIO_PROXY_TARGET || "http://127.0.0.1:18181";
  const backendTarget = env.VITE_BACKEND_PROXY_TARGET || "http://127.0.0.1:8000";
  const liveMediaTarget = env.VITE_LIVE_MEDIA_PROXY_TARGET || "http://127.0.0.1:8888";

  return {
    plugins: [react()],
    server: {
      host: devHost,
      port: devPort,
      allowedHosts: allowedHosts.length ? allowedHosts : true,
      proxy: {
        '/api/content': {
          target: env.VITE_ARTICLE_PROXY_TARGET || 'http://127.0.0.1:3100',
          changeOrigin: true,
          secure: false,
        },
        '/api/articles': {
          target: env.VITE_ARTICLE_PROXY_TARGET || 'http://127.0.0.1:3100',
          changeOrigin: true,
          secure: false,
        },
        '/media': {
          target: env.VITE_ARTICLE_PROXY_TARGET || 'http://127.0.0.1:3100',
          changeOrigin: true,
          secure: false,
        },
        '/mineradio-api': {
          target: mineradioTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/mineradio-api/, '/api'),
        },
        '/mineradio': {
          target: mineradioTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/mineradio/, ''),
        },
        '/api': {
          target: backendTarget,
          changeOrigin: true,
          secure: false,
        },
        '/live-media': {
          target: liveMediaTarget,
          changeOrigin: true,
          rewrite: (requestPath) => requestPath.replace(/^\/live-media/, ''),
        },
        '/uploads': {
          target: backendTarget,
          changeOrigin: true,
          secure: false,
        },
        '/socket.io': {
          target: backendTarget,
          ws: true,
          changeOrigin: true,
        },
        '/ws/socket.io': {
          target: backendTarget,
          ws: true,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: previewHost,
      port: previewPort,
      allowedHosts: allowedHosts.length ? allowedHosts : true,
    },
  };
});
