/**
 * FoodRescue Network — navbar unread-notifications badge (Phase 9)
 *
 * Loaded on every page (base.html), the same way auth.js is — this
 * is what keeps the 🔔 badge in the navbar up to date without the
 * person needing to visit /notifications first.
 *
 * GET /api/notifications already returns an `unread_count` field on
 * every response regardless of filters, so this asks for the
 * smallest possible page (limit=1) purely to read that count
 * cheaply, rather than fetching notifications it's going to throw
 * away.
 *
 * Polls every 30s while the tab is open, plus an immediate refresh
 * whenever the tab regains focus (catching up on anything that
 * happened while it was in the background, without polling a
 * backgrounded tab pointlessly in between).
 */

const NOTIFICATION_POLL_INTERVAL_MS = 30000;

async function refreshUnreadBadge() {
  const countEl = document.querySelector('[data-unread-count]');
  if (!countEl) return;

  if (!Auth.isLoggedIn()) {
    countEl.hidden = true;
    return;
  }

  try {
    const result = await Api.get('/api/notifications?limit=1');
    const count = result.data.unread_count;
    if (count > 0) {
      countEl.textContent = count > 99 ? '99+' : String(count);
      countEl.hidden = false;
    } else {
      countEl.hidden = true;
    }
  } catch (err) {
    // A failed badge refresh (401, network blip, etc.) shouldn't be
    // shown to the person as an error — it's a passive indicator,
    // not something they asked for right now. Just hide it and let
    // the next poll or page's own load() surface anything real.
    countEl.hidden = true;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  refreshUnreadBadge();
  setInterval(refreshUnreadBadge, NOTIFICATION_POLL_INTERVAL_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refreshUnreadBadge();
  });
});
