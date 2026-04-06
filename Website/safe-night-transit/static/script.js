/**
 * Safe-Night Transit — Shared JavaScript
 * Utilities: API calls, clock, toast notifications
 */

// ─────────────────────────────────────────────
// CLOCK
// ─────────────────────────────────────────────
function updateClock() {
  const el = document.getElementById('navTime');
  if (!el) return;
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const s = String(now.getSeconds()).padStart(2, '0');
  el.textContent = `${h}:${m}:${s}`;
}


// ─────────────────────────────────────────────
// API HELPER
// ─────────────────────────────────────────────
/**
 * Make an API request to the Flask backend.
 * @param {string} url - Endpoint path
 * @param {object|null} body - Request body (null for GET)
 * @param {string} method - 'GET' | 'POST'
 */
async function api(url, body = null, method = 'POST') {
  try {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== null) {
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    return await res.json();
  } catch (err) {
    console.error('API Error:', err);
    showToast('Connection error. Is the server running?', 'danger');
    return { success: false, error: 'Network error' };
  }
}


// ─────────────────────────────────────────────
// TOAST NOTIFICATIONS
// ─────────────────────────────────────────────
let toastTimeout = null;

/**
 * Show a toast notification.
 * @param {string} msg - Message to show
 * @param {string} type - 'success' | 'warn' | 'danger'
 */
function showToast(msg, type = 'success') {
  const el = document.getElementById('toast');
  if (!el) return;

  el.textContent = msg;
  el.className = `toast ${type} show`;

  if (toastTimeout) clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    el.className = 'toast';
  }, 4000);
}
