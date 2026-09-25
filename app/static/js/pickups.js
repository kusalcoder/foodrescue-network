/**
 * FoodRescue Network — "My Pickups" dashboard (Phase 7)
 *
 * Drives templates/pickups/mine.html. Shared by both roles — a
 * provider and a recipient see the exact same list (GET /api/pickups
 * returns pickups scoped to whichever profile(s) the current user
 * has), just with different action buttons per card.
 *
 * ── Status filtering is client-side, on the current page only ──
 * GET /api/pickups only supports page/limit, not a status filter —
 * so this fetches a page (limit=50, the same ceiling the API already
 * clamps everything to) and filters what's already loaded, rather
 * than trying to fake server-side filtering. For the volume a single
 * provider/recipient deals with, one page covers everything in
 * practice; if that stops being true, the right fix is a `status`
 * query param on the API, not more cleverness here. The pagination
 * controls below page through the SERVER's pages (unfiltered) — the
 * status dropdown then narrows whatever's on the current page.
 *
 * ── Why we fetch listings/requests separately ──────────────────
 * PickupRecord.to_dict() only returns listing_id and request_id, not
 * the listing's food name or the request's quantity — so each is
 * fetched once per unique id (not once per pickup) and cached in a
 * map, the same N+1-but-bounded approach as Phase 6's dashboard.
 *
 * ── Phase 12 addition: success feedback ─────────────────────────
 * confirm/cancel/complete/fail previously only surfaced errors; a
 * successful action just silently re-rendered the list. showSuccess()
 * now gives the same treatment errors already had.
 */

const PICKUP_STATUS_LABELS = {
  scheduled: 'Scheduled',
  confirmed: 'Confirmed',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

// Reuse listing-status badge colors — nothing pickup-specific needed.
const PICKUP_BADGE_CLASS = {
  scheduled: 'pending',
  confirmed: 'reserved',
  completed: 'collected',
  failed: 'cancelled',
  cancelled: 'cancelled',
};

const ACTIVE_PICKUP_STATUSES = ['scheduled', 'confirmed'];

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function formatDateTime(iso) {
  if (!iso) return 'Not yet set';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

(function () {
  const root = document.querySelector('[data-page="my-pickups"]');
  if (!root) return;

  let currentPage = 1;
  let currentPagination = null;
  let currentPickups = [];
  let listingCache = {};  // listing_id -> listing dict
  let requestCache = {};  // request_id  -> request dict
  let myRole = null;      // 'provider' | 'recipient'

  function el(id) { return document.getElementById(id); }

  function showGate() {
    const user = Auth.isLoggedIn() ? Auth.getUser() : null;
    el('guest-notice').hidden = !!user;
    el('dashboard').hidden = true;
    el('no-profile-notice').hidden = true;
  }

  function showNoProfile() {
    el('dashboard').hidden = true;
    el('no-profile-notice').hidden = false;
  }

  function showError(message) {
    el('pk-alert').innerHTML =
      `<div class="alert alert--error">${escapeHtml(message)}</div>`;
  }

  function showSuccess(message) {
    el('pk-alert').innerHTML =
      `<div class="alert alert--success">${escapeHtml(message)}</div>`;
  }

  async function fetchUncached(ids, cache, fetchOne) {
    const missing = [...new Set(ids)].filter((id) => id != null && !(id in cache));
    if (!missing.length) return;
    const results = await Promise.all(missing.map(fetchOne));
    missing.forEach((id, i) => { cache[id] = results[i]; });
  }

  function cardHtml(pickup) {
    const statusLabel = PICKUP_STATUS_LABELS[pickup.status] || pickup.status;
    const badgeClass = PICKUP_BADGE_CLASS[pickup.status] || pickup.status;
    const listing = listingCache[pickup.listing_id];
    const req = requestCache[pickup.request_id];

    const title = listing ? escapeHtml(listing.food_name) : `Listing #${pickup.listing_id}`;
    const quantityLine = (req && listing)
      ? `<p class="text-muted">${escapeHtml(req.requested_quantity)} ${escapeHtml(listing.quantity_unit)}</p>`
      : '';
    const infoLine = pickup.confirmation_info
      ? `<p class="listing-card__desc">${escapeHtml(pickup.confirmation_info)}</p>`
      : '';

    let actions = '';
    if (myRole === 'recipient') {
      if (pickup.status === 'scheduled') {
        actions = `
          <button type="button" class="btn btn--primary" data-confirm-id="${pickup.id}">Confirm</button>
          <button type="button" class="btn btn--danger" data-cancel-id="${pickup.id}">Cancel</button>
        `;
      } else if (pickup.status === 'confirmed') {
        actions = `<button type="button" class="btn btn--danger" data-cancel-id="${pickup.id}">Cancel</button>`;
      }
    } else if (myRole === 'provider') {
      if (pickup.status === 'scheduled' || pickup.status === 'confirmed') {
        actions = `
          <button type="button" class="btn btn--primary" data-complete-id="${pickup.id}">Mark Completed</button>
          <button type="button" class="btn btn--danger" data-fail-id="${pickup.id}">Mark Failed</button>
        `;
      }
    }

    // Phase 8: a completed pickup has a permanent DistributionRecord
    // sitting on /distributions — point at it rather than leaving a
    // dead end once there's nothing left to action here.
    if (pickup.status === 'completed') {
      actions = `<a class="btn btn--secondary" href="/distributions">View in History</a>`;
    }

    return `
      <article class="card listing-card" data-pickup-card="${pickup.id}">
        <div class="listing-card__top">
          <span class="badge badge--${badgeClass}">${escapeHtml(statusLabel)}</span>
          <span class="text-muted listing-card__category">Pickup #${pickup.id}</span>
        </div>
        <h3><a href="/listings/${pickup.listing_id}">${title}</a></h3>
        ${quantityLine}
        <p class="text-muted">Pickup time: ${escapeHtml(formatDateTime(pickup.pickup_time))}</p>
        ${infoLine}
        <div class="listing-card__actions">${actions}</div>
      </article>
    `;
  }

  function render() {
    const filter = el('status-filter').value;
    const gridEl = el('pk-grid');
    const emptyEl = el('pk-empty');

    const shown = filter === 'active'
      ? currentPickups.filter((p) => ACTIVE_PICKUP_STATUSES.includes(p.status))
      : filter
        ? currentPickups.filter((p) => p.status === filter)
        : currentPickups;

    if (!shown.length) {
      gridEl.hidden = true;
      gridEl.innerHTML = '';
      emptyEl.hidden = false;
      emptyEl.textContent = filter
        ? `No pickups with that status on this page.`
        : 'No pickups yet.';
      return;
    }

    emptyEl.hidden = true;
    gridEl.innerHTML = shown.map(cardHtml).join('');
    gridEl.hidden = false;

    gridEl.querySelectorAll('[data-confirm-id]').forEach((btn) => {
      btn.addEventListener('click', () => act(btn.dataset.confirmId, 'confirm', btn, 'Confirm'));
    });
    gridEl.querySelectorAll('[data-cancel-id]').forEach((btn) => {
      btn.addEventListener('click', () => act(btn.dataset.cancelId, 'cancel', btn, 'Cancel'));
    });
    gridEl.querySelectorAll('[data-complete-id]').forEach((btn) => {
      btn.addEventListener('click', () => act(btn.dataset.completeId, 'complete', btn, 'Mark Completed'));
    });
    gridEl.querySelectorAll('[data-fail-id]').forEach((btn) => {
      btn.addEventListener('click', () => act(btn.dataset.failId, 'fail', btn, 'Mark Failed'));
    });
  }

  const ACT_SUCCESS_MESSAGES = {
    confirm: 'Pickup confirmed.',
    cancel: 'Pickup cancelled.',
    complete: 'Pickup marked as completed.',
    fail: 'Pickup marked as failed.',
  };

  async function act(pickupId, action, btn, label) {
    const verbs = {
      confirm: 'Confirm this pickup time?',
      cancel: 'Cancel this pickup? The request will revert to accepted so it can be rescheduled.',
      complete: 'Mark this pickup as completed? This records the handover permanently.',
      fail: 'Mark this pickup as failed (e.g. a no-show)? The request will revert to accepted.',
    };
    if (!confirm(verbs[action] || `${label}?`)) return;

    el('pk-alert').innerHTML = '';
    btn.disabled = true;
    btn.textContent = 'Working…';

    try {
      await Api.post(`/api/pickups/${pickupId}/${action}`);
      await load({ silent: true });
      showSuccess(ACT_SUCCESS_MESSAGES[action] || `${label} done.`);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = label;

      if (err.status === 401) {
        if (typeof renderAuthArea === 'function') renderAuthArea();
        showGate();
        return;
      }
      showError(err.message || `Could not ${label.toLowerCase()}. Please try again.`);
      const card = document.querySelector(`[data-pickup-card="${pickupId}"]`);
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  async function load(options = {}) {
    const loadingEl = el('pk-loading');
    const gridEl = el('pk-grid');
    const paginationEl = el('pagination');

    if (!options.silent) {
      loadingEl.hidden = false;
      gridEl.hidden = true;
      el('pk-empty').hidden = true;
      paginationEl.hidden = true;
    }

    try {
      const result = await Api.get(`/api/pickups?page=${currentPage}&limit=50`);
      currentPickups = result.data.pickups;
      currentPagination = result.data.pagination;

      await Promise.all([
        fetchUncached(
          currentPickups.map((p) => p.listing_id),
          listingCache,
          (id) => Api.get(`/api/listings/${id}`).then((r) => r.data).catch(() => null)
        ),
        fetchUncached(
          currentPickups.map((p) => p.request_id),
          requestCache,
          (id) => Api.get(`/api/requests/${id}`).then((r) => r.data).catch(() => null)
        ),
      ]);

      loadingEl.hidden = true;
      render();

      if (currentPagination.total_pages > 1) {
        paginationEl.hidden = false;
        el('page-info').textContent =
          `Page ${currentPagination.page} of ${currentPagination.total_pages} (${currentPagination.total} total)`;
        el('prev-page').disabled = currentPagination.page <= 1;
        el('next-page').disabled = currentPagination.page >= currentPagination.total_pages;
      }
    } catch (err) {
      loadingEl.hidden = true;
      if (err.status === 401) {
        if (typeof renderAuthArea === 'function') renderAuthArea();
        showGate();
        return;
      }
      if (err.code === 'PROFILE_NOT_FOUND') {
        showNoProfile();
        return;
      }
      showError(err.message || 'Could not load your pickups. Please try again.');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const user = Auth.isLoggedIn() ? Auth.getUser() : null;
    if (!user) {
      showGate();
      return;
    }
    if (user.role !== 'provider' && user.role !== 'recipient') {
      showNoProfile();
      return;
    }

    myRole = user.role;
    el('dashboard').hidden = false;
    el('status-filter').addEventListener('change', render);
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