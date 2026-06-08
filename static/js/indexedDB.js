// ============================================================
//  IndexedDB helper for Expense Tracker offline support
// ============================================================

const DB_NAME    = 'expense-tracker-db';
const DB_VERSION = 1;

// Open / create the database
function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = event => {
      const db = event.target.result;

      // Store for pending expenses
      if (!db.objectStoreNames.contains('pending-expenses')) {
        const expenseStore = db.createObjectStore('pending-expenses', {
          keyPath: 'id', autoIncrement: true
        });
        expenseStore.createIndex('synced', 'synced', { unique: false });
      }

      // Store for pending debts
      if (!db.objectStoreNames.contains('pending-debts')) {
        const debtStore = db.createObjectStore('pending-debts', {
          keyPath: 'id', autoIncrement: true
        });
        debtStore.createIndex('synced', 'synced', { unique: false });
      }

      // Store for cached expenses (read offline)
      if (!db.objectStoreNames.contains('cached-expenses')) {
        db.createObjectStore('cached-expenses', {
          keyPath: 'id'
        });
      }
    };

    request.onsuccess  = e => resolve(e.target.result);
    request.onerror    = e => reject(e.target.error);
  });
}

// ── Save a pending expense when offline ─────────────────────
async function savePendingExpense(expenseData) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction('pending-expenses', 'readwrite');
    const store = tx.objectStore('pending-expenses');
    const request = store.add({
      ...expenseData,
      synced:    false,
      createdAt: new Date().toISOString()
    });
    request.onsuccess = () => {
      console.log('[DB] Pending expense saved');
      resolve(request.result);
    };
    request.onerror = e => reject(e.target.error);
  });
}

// ── Get all unsynced pending expenses ────────────────────────
async function getPendingExpenses() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx      = db.transaction('pending-expenses', 'readonly');
    const store   = tx.objectStore('pending-expenses');
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result.filter(e => !e.synced));
    request.onerror   = e => reject(e.target.error);
  });
}

// ── Mark expense as synced ───────────────────────────────────
async function markExpenseSynced(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction('pending-expenses', 'readwrite');
    const store = tx.objectStore('pending-expenses');
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const record = getReq.result;
      if (record) {
        record.synced = true;
        store.put(record);
      }
      resolve();
    };
    getReq.onerror = e => reject(e.target.error);
  });
}

// ── Delete synced expense ────────────────────────────────────
async function deletePendingExpense(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction('pending-expenses', 'readwrite');
    const store = tx.objectStore('pending-expenses');
    const request = store.delete(id);
    request.onsuccess = () => resolve();
    request.onerror   = e => reject(e.target.error);
  });
}

// ── Save a pending debt when offline ────────────────────────
async function savePendingDebt(debtData) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction('pending-debts', 'readwrite');
    const store = tx.objectStore('pending-debts');
    const request = store.add({
      ...debtData,
      synced:    false,
      createdAt: new Date().toISOString()
    });
    request.onsuccess = () => {
      console.log('[DB] Pending debt saved');
      resolve(request.result);
    };
    request.onerror = e => reject(e.target.error);
  });
}

// ── Get all unsynced pending debts ───────────────────────────
async function getPendingDebts() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx      = db.transaction('pending-debts', 'readonly');
    const store   = tx.objectStore('pending-debts');
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result.filter(d => !d.synced));
    request.onerror   = e => reject(e.target.error);
  });
}

// ── Delete synced debt ───────────────────────────────────────
async function deletePendingDebt(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction('pending-debts', 'readwrite');
    const store = tx.objectStore('pending-debts');
    const request = store.delete(id);
    request.onsuccess = () => resolve();
    request.onerror   = e => reject(e.target.error);
  });
}

// ── Cache expenses for offline viewing ──────────────────────
async function cacheExpenses(expenses) {
  const db = await openDB();
  const tx    = db.transaction('cached-expenses', 'readwrite');
  const store = tx.objectStore('cached-expenses');
  store.clear();
  expenses.forEach(exp => store.add(exp));
  console.log('[DB] Expenses cached for offline viewing');
}

// ── Get cached expenses ──────────────────────────────────────
async function getCachedExpenses() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx      = db.transaction('cached-expenses', 'readonly');
    const store   = tx.objectStore('cached-expenses');
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror   = e => reject(e.target.error);
  });
}

// ── Check if online ──────────────────────────────────────────
function isOnline() {
  return navigator.onLine;
}