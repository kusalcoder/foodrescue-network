/**
 * FoodRescue Network — "My Requests" recipient dashboard (Phase 5)
 *
 * Renders GET /api/requests (no pagination — every request the
 * current recipient has ever made).
 *
 * FoodRequest.to_dict() only returns listing_id, not the listing's
 * details (food name, pickup info, etc.) — there's no embedding on
 * the API side — so each card just links to the listing's own detail
 * page (/listings/<id>) for that context, rather than guessing at
 * fields that aren't there.
 *
 * Two things have to be true before this page shows anything useful:
 *   1. logged in as a RECIPIENT (not a provider or admin)
 *   2. that recipient has already completed a recipient profile
 *      (POST /api/recipients/profile) — the API 404s with
 *      PROFILE_NOT_FOUND otherwise
 */

const REQUEST_STATUS_LABELS = {
  pending: 'Pending',
  accepted: 'Accepted',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
  pickup_pending: 'Pickup Pending',
  completed: 'Completed',
};

// Request statuses reuse the same badge color set as listing statuses
// (see .badge--* in base.css) — map the ones whose names don't match
// a listing status onto the closest equivalent color.
const REQUEST_BADGE_CLASS = {
  pending: 'pending',
  accepted: 'available',
  rejected: 'cancelled',
  cancelled: 'cancelled',
  pickup_pending: 'pickup_pending',
  completed: 'collected',
};

let requestStatusRefreshInFlight = false;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatDateTime(dateTimeStr) {
  if (!dateTimeStr) return '';
  const d = new Date(dateTimeStr);
  if (Number.isNaN(d.getTime())) return dateTimeStr;
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function requestCardHtml(req) {
  const statusLabel = REQUEST_STATUS_LABELS[req.status] || req.status;
  const badgeClass = REQUEST_BADGE_CLASS[req.status] || req.status;
  const canCancel = req.status === 'pending' || req.status === 'accepted';
  // Phase 7: once a pickup exists for this request, its own
  // lifecycle (confirm/cancel/etc.) lives on /pickups, not here.
  const hasPickup = req.status === 'pickup_pending' || req.status === 'completed';
  const message = req.request_message
    ? `<p class="listing-card__desc">"${escapeHtml(req.request_message)}"</p>`
    : '';

  const cancelBtn = canCancel
    ? `<button type="button" class="btn btn--danger" data-cancel-id="${req.id}">Cancel Request</button>`
    : '';
  const pickupLink = hasPickup
    ? `<a class="btn btn--primary" href="/pickups">View Pickup</a>`
    : '';

  return `
    <article class="card listing-card" data-request-card="${req.id}" data-request-status="${escapeHtml(req.status)}">
      <div class="listing-card__top">
        <span class="badge badge--${badgeClass}">${escapeHtml(statusLabel)}</span>
        <span class="text-muted listing-card__category">Requested ${formatDateTime(req.requested_at)}</span>
      </div>
      <h3><a href="/listings/${req.listing_id}">Listing #${req.listing_id}</a></h3>
      ${message}
      <ul class="listing-card__meta">
        <li>${req.requested_quantity} requested</li>
      </ul>
      <div class="listing-card__actions">
        <a class="btn btn--secondary" href="/listings/${req.listing_id}">View Listing</a>
        ${pickupLink}
        ${cancelBtn}
      </div>
    </article>
  `;
}

async function loadMine() {
  const alertEl = document.getElementById('mine-alert');
  const loadingEl = document.getElementById('mine-loading');
  const gridEl = document.getElementById('mine-grid');
  const emptyEl = document.getElementById('mine-empty');
  const noProfileNotice = document.getElementById('no-profile-notice');
  const dashboard = document.getElementById('dashboard');

  alertEl.innerHTML = '';
  emptyEl.hidden = true;
  gridEl.hidden = true;
  loadingEl.hidden = false;

  try {
    const { data } = await Api.get('/api/requests');
    loadingEl.hidden = true;

    if (!data.length) {
      emptyEl.hidden = false;
      return;
    }

    gridEl.innerHTML = data.map(requestCardHtml).join('');
    gridEl.hidden = false;
    bindCancelButtons(gridEl);
  } catch (err) {
    loadingEl.hidden = true;
    if (err.status === 401) {
      if (typeof renderAuthArea === 'function') renderAuthArea();
      showGate();
      return;
    }
    if (err.code === 'PROFILE_NOT_FOUND') {
      dashboard.hidden = true;
      noProfileNotice.hidden = false;
      return;
    }
    alertEl.innerHTML = `<div class="alert alert--error">${escapeHtml(err.message || 'Could not load your requests. Please try again.')}</div>`;
  }
}

function bindCancelButtons(gridEl) {
  if (gridEl.dataset.cancelHandlerBound) return;
  gridEl.dataset.cancelHandlerBound = 'true';
  gridEl.addEventListener('click', (event) => {
    const button = event.target.closest('[data-cancel-id]');
    if (button && gridEl.contains(button)) handleCancel(button.dataset.cancelId);
  });
}

async function refreshRequestStatuses() {
  if (document.visibilityState !== 'visible' || requestStatusRefreshInFlight) return;

  requestStatusRefreshInFlight = true;
  try {
    const { data } = await Api.get('/api/requests');
    const gridEl = document.getElementById('mine-grid');
    const cardsById = new Map(
      Array.from(gridEl.querySelectorAll('[data-request-card]'))
        .map((card) => [card.dataset.requestCard, card])
    );
    let changed = false;

    data.forEach((request) => {
      const card = cardsById.get(String(request.id));
      if (!card || card.dataset.requestStatus === request.status) return;
      card.outerHTML = requestCardHtml(request);
      changed = true;
    });

    if (changed) bindCancelButtons(gridEl);
  } catch (err) {
    // Status polling is best-effort; the next poll retries without an alert.
  } finally {
    requestStatusRefreshInFlight = false;
  }
}

async function handleCancel(requestId) {
  if (!confirm('Cancel this request?')) return;

  const card = document.querySelector(`[data-request-card="${requestId}"]`);
  const alertEl = document.getElementById('mine-alert');

  try {
    await Api.post(`/api/requests/${requestId}/cancel`);
    await loadMine();
    alertEl.innerHTML = `<div class='alert alert--success'>Request cancelled.</div>`;
  } catch (err) {
    const message = err.message || 'Could not cancel this request. Please try again.';
    alertEl.innerHTML = `<div class="alert alert--error">${escapeHtml(message)}</div>`;
    if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function showGate() {
  const user = Auth.isLoggedIn() ? Auth.getUser() : null;
  document.getElementById('guest-notice').hidden = !!user;
  document.getElementById('wrong-role-notice').hidden = !user || user.role === 'recipient';
  document.getElementById('dashboard').hidden = true;
  document.getElementById('no-profile-notice').hidden = true;
}

document.addEventListener('DOMContentLoaded', () => {
  if (!document.querySelector('[data-page="my-requests"]')) return;

  const user = Auth.isLoggedIn() ? Auth.getUser() : null;

  if (!user || user.role !== 'recipient') {
    showGate();
    return;
  }

  document.getElementById('dashboard').hidden = false;
  loadMine();

  if (!window.__frnMyRequestsPollingInitialized) {
    window.__frnMyRequestsPollingInitialized = true;
    let pollTimer = null;
    const startPolling = () => {
      if (pollTimer || document.visibilityState !== 'visible') return;
      pollTimer = window.setInterval(refreshRequestStatuses, 3000);
    };
    const stopPolling = () => {
      if (!pollTimer) return;
      window.clearInterval(pollTimer);
      pollTimer = null;
    };

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        refreshRequestStatuses();
        startPolling();
      } else {
        stopPolling();
      }
    });
    startPolling();
  }
});
