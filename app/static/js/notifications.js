/**
 * FoodRescue Network — notifications page (Phase 9)
 *
 * Drives templates/notifications/mine.html: list, unread-only
 * filter, mark-one-as-read, mark-all-as-read, and a best-effort
 * "jump to what this is about" link built from
 * notification.related_resource_type/id.
 *
 * ── Where a notification links to ─────────────────────────────────
 * Notification.to_dict() gives a resource type/id but there's no
 * generic "resolve this resource" endpoint, and most of this app's
 * pages are dashboards (a list), not per-item detail pages. So links
 * point at the dashboard where that resource would appear, not a
 * page scoped to that one item specifically:
 *
 *   food_request      -> /requests/incoming (provider) or
 *                         /requests/mine (recipient), by the viewer's
 *                         own role — a request notification is only
 *                         ever sent to one side of it, so this is
 *                         always the *right* dashboard, just not
 *                         scrolled to the exact card
 *   pickup_record     -> /pickups (same reasoning)
 *   recipient_profile -> no page yet (profile management is Phase 10)
 *   anything else (e.g. account_deactivated) -> no link; it's
 *                         informational, not something to "go to"
 *
 * "Mark all as read" is a client-side loop over this page's own
 * unread items — there's no bulk-read endpoint on the API, only
 * POST /api/notifications/<id>/read one at a time.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function formatDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

function resolveLink(notification, myRole) {
  if (notification.related_resource_type === 'food_request') {
    return myRole === 'provider' ? '/requests/incoming' : '/requests/mine';
  }
  if (notification.related_resource_type === 'pickup_record') {
    return '/pickups';
  }
  return null;
}

(function () {
  const root = document.querySelector('[data-page="notifications"]');
  if (!root) return;

  let currentPage = 1;
  let currentPagination = null;
  let myRole = null;

  function el(id) { return document.getElementById(id); }

  function showGate() {
    // Only ever called when we already know the user isn't (or is no
    // longer) logged in — an initial check, or a 401 from the API.
    el('guest-notice').hidden = false;
    el('dashboard').hidden = true;
  }

  function showError(message) {
    el('notif-alert').innerHTML =
      `<div class="alert alert--error">${escapeHtml(message)}</div>`;
  }

  function itemHtml(n) {
    const link = resolveLink(n, myRole);
    const titleHtml = link
      ? `<a href="${link}">${escapeHtml(n.title)}</a>`
      : escapeHtml(n.title);

    return `
      <article class="notif-item ${n.is_read ? '' : 'notif-item--unread'}" data-notif-item="${n.id}">
        <div>
          <p class="notif-item__title">${titleHtml}</p>
          <p class="notif-item__message">${escapeHtml(n.message)}</p>
          <p class="notif-item__meta">${escapeHtml(formatDateTime(n.created_at))}</p>
        </div>
        <div class="notif-item__actions">
          ${n.is_read
            ? '<span class="text-muted">Read</span>'
            : `<button type="button" class="btn btn--secondary" data-read-id="${n.id}">Mark read</button>`}
        </div>
      </article>
    `;
  }

  async function load() {
    const loadingEl = el('notif-loading');
    const listEl = el('notif-list');
    const emptyEl = el('notif-empty');
    const paginationEl = el('pagination');

    loadingEl.hidden = false;
    listEl.hidden = true;
    emptyEl.hidden = true;
    paginationEl.hidden = true;
    el('notif-alert').innerHTML = '';

    try {
      const unreadOnly = el('unread-only').checked;
      const result = await Api.get(
        `/api/notifications?page=${currentPage}&limit=20${unreadOnly ? '&unread_only=true' : ''}`
      );
      const { notifications, pagination, unread_count } = result.data;
      currentPagination = pagination;

      loadingEl.hidden = true;
      el('mark-all-read').hidden = unread_count === 0;

      if (!notifications.length) {
        emptyEl.hidden = false;
        emptyEl.textContent = unreadOnly
          ? 'No unread notifications.'
          : 'No notifications yet.';
      } else {
        listEl.innerHTML = notifications.map(itemHtml).join('');
        listEl.hidden = false;
        listEl.querySelectorAll('[data-read-id]').forEach((btn) => {
          btn.addEventListener('click', () => markRead(btn.dataset.readId, btn));
        });
      }

      if (pagination.total_pages > 1) {
        paginationEl.hidden = false;
        el('page-info').textContent =
          `Page ${pagination.page} of ${pagination.total_pages} (${pagination.total} total)`;
        el('prev-page').disabled = pagination.page <= 1;
        el('next-page').disabled = pagination.page >= pagination.total_pages;
      }

      if (typeof refreshUnreadBadge === 'function') refreshUnreadBadge();
    } catch (err) {
      loadingEl.hidden = true;
      if (err.status === 401) {
        if (typeof renderAuthArea === 'function') renderAuthArea();
        showGate();
        return;
      }
      showError(err.message || 'Could not load notifications. Please try again.');
    }
  }

  async function markRead(notificationId, btn) {
    btn.disabled = true;
    btn.textContent = 'Marking…';
    try {
      await Api.post(`/api/notifications/${notificationId}/read`);
      await load();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'Mark read';
      showError(err.message || 'Could not mark this as read. Please try again.');
    }
  }

  async function markAllRead() {
    const button = el('mark-all-read');
    const unreadIds = Array.from(document.querySelectorAll('[data-read-id]'))
      .map((btn) => btn.dataset.readId);

    if (!unreadIds.length) return;

    button.disabled = true;
    button.textContent = 'Marking…';
    try {
      // No bulk endpoint — this page only ever has one page's worth
      // of items on screen at a time, so marking each one we can
      // currently see is a bounded, reasonable number of calls.
      await Promise.all(unreadIds.map((id) => Api.post(`/api/notifications/${id}/read`)));
      await load();
    } catch (err) {
      showError(err.message || 'Could not mark everything as read. Please try again.');
    } finally {
      button.disabled = false;
      button.textContent = 'Mark all as read';
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!Auth.isLoggedIn()) {
      showGate();
      return;
    }

    myRole = Auth.getUser().role;
    el('dashboard').hidden = false;
    el('unread-only').addEventListener('change', () => { currentPage = 1; load(); });
    el('mark-all-read').addEventListener('click', markAllRead);
    el('prev-page').addEventListener('click', () => {
      if (currentPage > 1) { currentPage -= 1; load(); }
    });
    el('next-page').addEventListener('click', () => {
      if (currentPagination && currentPage < currentPagination.total_pages) {
        currentPage += 1; load();
      }
    });

    load();
  });
})();
