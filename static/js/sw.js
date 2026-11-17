/**
 * OSM Microcrédito v5 — Service Worker
 * Propósito: habilitar instalação PWA na homescreen (iOS + Android)
 * Sem armazenamento offline — todas as páginas vão sempre à rede.
 */

const CACHE_NAME = 'osm-pwa-v5';

// Apenas assets mínimos para o PWA funcionar (ícones + offline básico)
const INSTALL_ASSETS = [
  '/static/images/logo/icon-192.png',
  '/static/images/logo/icon-512.png',
];

// ── INSTALL ──────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(INSTALL_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

// ── ACTIVATE ─────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// ── FETCH — sempre vai à rede, sem cache de páginas ──────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Só interceta o mesmo origin
  if (url.origin !== self.location.origin) return;

  // Ícones e assets estáticos: cache-first (não mudam)
  if (url.pathname.startsWith('/static/images/logo/')) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
    return;
  }

  // Tudo o resto (páginas, API, etc.): sempre vai à rede
  // Se não houver rede, mostra erro nativo do browser — sem fallback offline
});

// ── PUSH NOTIFICATIONS (para alertas de cobrança) ────────────────────
self.addEventListener('push', event => {
  if (!event.data) return;
  try {
    const data = event.data.json();
    event.waitUntil(
      self.registration.showNotification(data.title || 'OSM Microcrédito', {
        body:    data.body  || '',
        icon:    '/static/images/logo/icon-192.png',
        badge:   '/static/images/logo/icon-72.png',
        vibrate: [200, 100, 200],
        tag:     data.tag   || 'osm',
        data:    { url: data.url || '/painel/' },
      })
    );
  } catch(e) {}
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data?.url || '/painel/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(clients => {
        for (const c of clients) {
          if ('focus' in c) { c.navigate(url); return c.focus(); }
        }
        if (self.clients.openWindow) return self.clients.openWindow(url);
      })
  );
});

// ── MENSAGENS ────────────────────────────────────────────────────────
self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});
