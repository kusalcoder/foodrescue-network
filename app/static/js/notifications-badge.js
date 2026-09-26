/**
 * FoodRescue Network — global notification polling (Phase 9)
 *
 * Keeps the navbar unread count current and shows new unread
 * notifications without requiring a page refresh.
 */

(function () {
  if (window.__frnNotificationPollingInitialized) return;
  window.__frnNotificationPollingInitialized = true;

  const NOTIFICATION_POLL_INTERVAL_MS = 3000;
  const NOTIFICATION_IDS_STORAGE_PREFIX = 'frn_displayed_notification_ids:';
  const displayedIdsByUser = new Map();
  const initializedUsers = new Set();
  let pollTimer = null;
  let pollInFlight = false;

  function storageKeyForCurrentUser() {
    const user = Auth.getUser();
    return `${NOTIFICATION_IDS_STORAGE_PREFIX}${user && user.id ? user.id : 'current'}`;
  }

  function displayedIdsFor(storageKey) {
    if (!displayedIdsByUser.has(storageKey)) {
      let storedIds = [];
      let hasStoredState = false;
      try {
        const raw = sessionStorage.getItem(storageKey);
        hasStoredState = raw !== null;
        storedIds = raw ? JSON.parse(raw) : [];
      } catch (err) {
        // In-memory state still prevents repeats if sessionStorage is unavailable.
      }
      displayedIdsByUser.set(storageKey, new Set(Array.isArray(storedIds) ? storedIds.map(String) : []));
      if (hasStoredState) initializedUsers.add(storageKey);
    }
    return displayedIdsByUser.get(storageKey);
  }

  function saveDisplayedIds(storageKey, displayedIds) {
    const recentIds = Array.from(displayedIds).slice(-200);
    displayedIds.clear();
    recentIds.forEach((id) => displayedIds.add(id));
    initializedUsers.add(storageKey);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(recentIds));
    } catch (err) {
      // The in-memory set remains the fallback for this page session.
    }
  }

  function showNotificationToast(notification) {
    let container = document.getElementById('notification-toasts');
    if (!container) {
      container = document.createElement('div');
      container.id = 'notification-toasts';
      container.className = 'notification-toasts';
      container.setAttribute('aria-live', 'polite');
      container.setAttribute('aria-label', 'New notifications');
      document.body.appendChild(container);
    }

    const toast = document.createElement('section');
    toast.className = 'notification-toast';
    toast.setAttribute('role', 'status');

    const icon = document.createElement('span');
    icon.className = 'notification-toast__icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '🔔';

    const content = document.createElement('div');
    content.className = 'notification-toast__content';
    const title = document.createElement('p');
    title.className = 'notification-toast__title';
    title.textContent = notification.title || 'New notification';
    const message = document.createElement('p');
    message.className = 'notification-toast__message';
    message.textContent = notification.message || '';
    content.append(title, message);

    const closeButton = document.createElement('button');
    closeButton.className = 'notification-toast__close';
    closeButton.type = 'button';
    closeButton.setAttribute('aria-label', 'Close notification');
    closeButton.textContent = '×';

    let dismissTimer;
    const dismiss = () => {
      window.clearTimeout(dismissTimer);
      toast.remove();
    };
    closeButton.addEventListener('click', dismiss);
    toast.append(icon, content, closeButton);
    container.appendChild(toast);
    dismissTimer = window.setTimeout(dismiss, 7000);
  }

  async function refreshUnreadBadge() {
    const countEl = document.querySelector('[data-unread-count]');
    if (!Auth.isLoggedIn()) {
      if (countEl) countEl.hidden = true;
      return;
    }

    if (pollInFlight) return;
    pollInFlight = true;
    try {
      const result = await Api.get('/api/notifications?limit=10');
      const { notifications, unread_count: count } = result.data;
      if (countEl) {
        if (count > 0) {
          countEl.textContent = count > 99 ? '99+' : String(count);
          countEl.hidden = false;
        } else {
          countEl.hidden = true;
        }
      }

      const storageKey = storageKeyForCurrentUser();
      const displayedIds = displayedIdsFor(storageKey);
      if (!initializedUsers.has(storageKey)) {
        notifications.forEach((notification) => displayedIds.add(String(notification.id)));
        saveDisplayedIds(storageKey, displayedIds);
        return;
      }

      notifications.forEach((notification) => {
        const id = String(notification.id);
        if (displayedIds.has(id)) return;
        displayedIds.add(id);
        if (!notification.is_read) showNotificationToast(notification);
      });
      saveDisplayedIds(storageKey, displayedIds);
    } catch (err) {
      // Polling is passive; retry quietly on the next interval.
    } finally {
      pollInFlight = false;
    }
  }

  window.refreshUnreadBadge = refreshUnreadBadge;

  function startPolling() {
    if (pollTimer || document.visibilityState !== 'visible') return;
    refreshUnreadBadge();
    pollTimer = window.setInterval(refreshUnreadBadge, NOTIFICATION_POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (!pollTimer) return;
    window.clearInterval(pollTimer);
    pollTimer = null;
  }

  document.addEventListener('DOMContentLoaded', startPolling);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') startPolling();
    else stopPolling();
  });
})();
