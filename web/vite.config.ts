import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

export default defineConfig({
  plugins: [
    preact(),
    {
      name: "offline-shell",
      generateBundle(_, bundle) {
        const paths = [
          "/",
          "/icon.svg",
          "/icon-180.png",
          "/icon-192.png",
          "/icon-512.png",
          "/manifest.webmanifest",
          ...Object.keys(bundle).map((p) => "/" + p),
        ];
        this.emitFile({
          type: "asset",
          fileName: "sw.js",
          source: `
const CACHE = 'puppypi-shell-' + ${JSON.stringify(Object.keys(bundle).join("-"))};
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(${JSON.stringify(paths)}))));
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('puppypi-shell-') && k !== CACHE).map(k => caches.delete(k))))));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== self.location.origin || u.pathname.startsWith('/api/')) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request).then(r => r || Response.error())));
});`,
        });
      },
    },
  ],
  build: { outDir: "../teach_and_find/mobile/static", emptyOutDir: true },
  server: { proxy: { "/api": { target: "http://127.0.0.1:8080", ws: true } } },
});
