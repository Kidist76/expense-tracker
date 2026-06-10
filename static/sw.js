const SW_VERSION = 'v2.2';
const STATIC_CACHE = `expense-static-${SW_VERSION}`;
const DYNAMIC_CACHE = `expense-dynamic-${SW_VERSION}`;
const CDN_CACHE    = `expense-cdn-${SW_VERSION}`;

// ── App shell – cached at install time ──────────────────────
const STATIC_ASSETS = [
  '/',
  '/login',
  '/register',
  '/dashboard',
  '/transactions',
  '/debts',
  '/add_expense_page',
  '/offline',
  '/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

// ── CDN assets – stale-while-revalidate ─────────────────────
const CDN_ASSETS = [
  'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
];

// ── Routes that MUST NOT be cached (mutations / file uploads) ─
const NEVER_CACHE = [
  '/upload_ocr',
  '/confirm_ocr',
  '/delete_expense',
  '/toggle_debt',
  '/logout',
  '/export_data',
];

// Page routes – network first
const PAGE_ROUTES = [
  '/dashboard',
  '/transactions',
  '/debts',
  '/search',
  '/add_expense_page',
];


//  INSTALL – pre-cache app shell

self.addEventListener('install', event => {
  console.log(`[SW ${SW_VERSION}] Installing…`);

  event.waitUntil(
    Promise.all([
      // Cache static pages
      caches.open(STATIC_CACHE).then(cache => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS).catch(err => {
          console.warn('[SW] Some static assets failed to cache:', err);
        });
      }),
      // Cache CDN assets
      caches.open(CDN_CACHE).then(cache => {
        console.log('[SW] Caching CDN assets');
        return cache.addAll(CDN_ASSETS).catch(err => {
          console.warn('[SW] Some CDN assets failed to cache:', err);
        });
      }),
    ]).then(() => self.skipWaiting())  // activate immediately
  );
});

//  ACTIVATE – clean up old caches, take control
self.addEventListener('activate', event => {
  console.log(`[SW ${SW_VERSION}] Activating…`);

  const allowedCaches = [STATIC_CACHE, DYNAMIC_CACHE, CDN_CACHE];

  event.waitUntil(
    caches.keys()
      .then(names =>
        Promise.all(
          names
            .filter(name => !allowedCaches.includes(name))
            .map(name => {
              console.log('[SW] Deleting stale cache:', name);
              return caches.delete(name);
            })
        )
      )
      .then(() => self.clients.claim())  // take control of all open tabs
  );
});


//  FETCH – route to correct strategy

self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // ── Ignore non-GET & non-HTTP(S) ──────────────────────────
  if (request.method !== 'GET') return;
  if (!url.protocol.startsWith('http')) return;

  // ── Never cache mutation routes ───────────────────────────
  if (NEVER_CACHE.some(path => url.pathname.startsWith(path))) return;

  // ── CDN assets → Stale-While-Revalidate ──────────────────
  if (CDN_ASSETS.includes(request.url)) {
    event.respondWith(staleWhileRevalidate(request, CDN_CACHE));
    return;
  }

  // ── Local static files (/static/*) → Cache First
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

// ── Page routes → Stale-While-Revalidate
// Serves cached page instantly, updates cache in background.
// bustPageCache() in the forms deletes stale entries after mutations.
if (PAGE_ROUTES.some(route => url.pathname === route || url.pathname.startsWith(route))) {
    event.respondWith(staleWhileRevalidate(request, DYNAMIC_CACHE));
    return;
}
  // ── Everything else → Stale-While-Revalidate ─────────────
  event.respondWith(staleWhileRevalidate(request, DYNAMIC_CACHE));
});

//  STRATEGIES

/**
 * Cache First
 * Serve from cache; fetch & store only if not cached.
 * Best for: versioned static assets, icons, fonts.
 */
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    await putInCache(cacheName, request, response.clone());
    return response;
  } catch {
    return offlineFallback(request);
  }
}

/**
 * Network First
 * Always try network; fall back to cache if offline.
 * Best for: HTML pages, dashboard data.
 */
async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    // Only cache successful same-origin responses
    if (response.ok) {
      await putInCache(cacheName, request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || offlineFallback(request);
  }
}

/**
 * Stale-While-Revalidate
 * Serve cache instantly; update cache from network in background.
 * Best for: CDN assets, semi-static resources.
 */
async function staleWhileRevalidate(request, cacheName) {
  const cached = await caches.match(request);

  const networkFetch = fetch(request)
    .then(response => {
      if (response.ok) putInCache(cacheName, request, response.clone());
      return response;
    })
    .catch(() => null);

  return cached || (await networkFetch) || offlineFallback(request);
}

//  HELPERS


/**
 * Save a response to a named cache.
 * Skips opaque responses (cross-origin without CORS) to avoid
 * storing bad cached responses.
 */
async function putInCache(cacheName, request, response) {
  // Don't cache error responses or opaque responses
  if (!response || response.status !== 200) return;
  // Allow caching CDN (opaque) responses carefully
  if (response.type === 'opaque' && cacheName !== CDN_CACHE) return;

  try {
    const cache = await caches.open(cacheName);
    await cache.put(request, response);
  } catch (err) {
    console.warn('[SW] Cache put failed:', err);
  }
}

/**
 * Offline fallback handler.
 * - Navigation requests → /offline HTML page
 * - API / JSON requests → JSON error object
 * - Other             → empty 503 response
 */
async function offlineFallback(request) {
  // HTML page navigation
  if (request.mode === 'navigate') {
    const offlinePage = await caches.match('/offline');
    if (offlinePage) return offlinePage;

    // Inline fallback if /offline page isn't cached yet
    return new Response(
      `<!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Offline – Expense Tracker</title>
        <style>
          * { box-sizing: border-box; margin: 0; padding: 0; }
          body {
            font-family: -apple-system, sans-serif;
            background: #f0f4f0;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; padding: 2rem;
            color: #1a2e1a;
          }
          .card {
            background: white;
            border-radius: 1.5rem;
            padding: 3rem 2rem;
            text-align: center;
            max-width: 400px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
          }
          .icon { font-size: 4rem; margin-bottom: 1rem; }
          h1 { font-size: 1.5rem; color: #2e7d32; margin-bottom: 0.75rem; }
          p  { color: #555; line-height: 1.6; margin-bottom: 1.5rem; }
          button {
            background: #2e7d32; color: white;
            border: none; border-radius: 0.75rem;
            padding: 0.75rem 2rem; font-size: 1rem;
            cursor: pointer;
          }
          button:hover { background: #1b5e20; }
        </style>
      </head>
      <body>
        <div class="card">
          <div class="icon">📵</div>
          <h1>You're Offline</h1>
          <p>No internet connection right now.<br>
             Your data is safe and will sync when you're back online.</p>
          <button onclick="location.reload()">Try Again</button>
        </div>
      </body>
      </html>`,
      {
        status: 503,
        headers: { 'Content-Type': 'text/html; charset=utf-8' }
      }
    );
  }

  // JSON API fallback
  if (request.headers.get('Accept')?.includes('application/json')) {
    return new Response(
      JSON.stringify({ error: 'You are offline', offline: true }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }

  // Generic fallback
  return new Response('Offline', { status: 503 });
}

// ============================================================
//  BACKGROUND SYNC
//  Retries failed expense submissions when back online.
//  Call navigator.serviceWorker.ready.then(sw =>
//    sw.sync.register('sync-expenses')) from your JS when saving
//  a pending expense to IndexedDB while offline.
// ============================================================
self.addEventListener('sync', event => {
  console.log('[SW] Background sync triggered:', event.tag);

  if (event.tag === 'sync-expenses') {
    event.waitUntil(syncPendingExpenses());
  }

  if (event.tag === 'sync-debts') {
    event.waitUntil(syncPendingDebts());
  }
});

async function syncPendingExpenses() {
  console.log('[SW] Syncing pending expenses…');
  const db = await openIDB();
  const pending = await getAllPending(db, 'pending-expenses');

  for (const expense of pending) {
    try {
      const formData = new FormData();
      Object.entries(expense).forEach(([key, val]) => {
        if (!['id', 'synced', 'createdAt'].includes(key)) {
          formData.append(key, val);
        }
      });

      const response = await fetch('/add_expense', {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        await deleteFromIDB(db, 'pending-expenses', expense.id);
        console.log('[SW] Expense synced and removed:', expense.id);
      }
    } catch (err) {
      console.warn('[SW] Failed to sync expense:', err);
    }
  }
}

async function syncPendingDebts() {
  console.log('[SW] Syncing pending debts…');
  const db = await openIDB();
  const pending = await getAllPending(db, 'pending-debts');

  for (const debt of pending) {
    try {
      const formData = new FormData();
      Object.entries(debt).forEach(([key, val]) => {
        if (!['id', 'synced', 'createdAt'].includes(key)) {
          formData.append(key, val);
        }
      });

      const response = await fetch('/add_debt', {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        await deleteFromIDB(db, 'pending-debts', debt.id);
        console.log('[SW] Debt synced and removed:', debt.id);
      }
    } catch (err) {
      console.warn('[SW] Failed to sync debt:', err);
    }
  }
}

//   IDB helpers used by sync functions

function openIDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('expense-tracker-db', 2);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('pending-expenses'))
        db.createObjectStore('pending-expenses', { keyPath: 'id', autoIncrement: true });
      if (!db.objectStoreNames.contains('pending-debts'))
        db.createObjectStore('pending-debts', { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}
function getAllPending(db, storeName) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(storeName, 'readonly');
    const req = tx.objectStore(storeName).getAll();
    req.onsuccess = () => resolve(req.result.filter(r => !r.synced));
    req.onerror   = e => reject(e.target.error);
  });
}

function deleteFromIDB(db, storeName, id) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(storeName, 'readwrite');
    const req = tx.objectStore(storeName).delete(id);
    req.onsuccess = () => resolve();
    req.onerror   = e => reject(e.target.error);
  });
}


//  PUSH NOTIFICATIONS
//  Send reminders for overdue debts from your Flask backend.
// ============================================================
self.addEventListener('push', event => {
  const data = event.data?.json() ?? {
    title: 'Expense Tracker',
    body:  'You have a new notification',
    url:   '/dashboard'
  };

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body:    data.body,
      icon:    '/static/icons/icon-192.png',
      badge:   '/static/icons/icon-72.png',
      vibrate: [200, 100, 200],
      data:    { url: data.url || '/dashboard' },
      actions: [
        { action: 'view',    title: '👁 View'   },
        { action: 'dismiss', title: '✕ Dismiss' }
      ]
    })
  );
});

// Handle notification click → open the right page
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const targetUrl = event.notification.data?.url || '/dashboard';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(windowClients => {
        // Focus existing tab if open
        for (const client of windowClients) {
          if (client.url.includes(targetUrl) && 'focus' in client) {
            return client.focus();
          }
        }
        // Otherwise open new tab
        if (clients.openWindow) return clients.openWindow(targetUrl);
      })
  );
 // Allow pages to activate waiting SW immediately
self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});
