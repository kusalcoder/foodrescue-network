/**
 * FoodRescue Network - provider-facing request management (Phase 6)
 *
 * Drives BOTH provider request pages, which share all of their
 * rendering and accept/reject logic and differ only in scope:
 *
 *   /requests/incoming        data-scope="all"     - every listing I own
 *   /listings/<id>/requests   data-scope="listing" - just that one listing
 *
 * -- Why the "all" page makes several API calls --
 * The backend has no "all requests across all my listings" endpoint,
 * only GET /api/listings/<id>/requests, scoped to one listing at a
 * time. So the aggregate view fetches GET /api/listings/mine first,
 * then fans out one request-fetch per listing and groups the results.
 * That is N+1 calls; if a provider ever has hundreds of listings, the
 * right fix is a new aggregate endpoint on the API side.
 *
 * -- Remaining quantity --
 * Derived client-side: listing.quantity minus the sum of every
 * accepted / pickup-pending request's quantity. The server still does
 * its own authoritative check when you click Accept; this display is a
 * convenience, never the thing being trusted.
 *
 * -- What we can't show --
 * FoodRequest.to_dict() returns recipient_id but not the recipient's
 * name, so cards identify recipients as "Recipient #<id>".
 *
 * -- Phase 7: scheduling a pickup --
 * An ACCEPTED request gets a "Schedule Pickup" button that reveals an
 * inline form, submitting to POST /api/requests/<id>/schedule-pickup.
 * Once scheduled, the card switches to a "View Pickup" link to /pickups.
 *
 * -- Phase 12: success feedback --
 * showSuccess() gives accept/reject/schedule the same banner treatment
 * errors already had.
 */

const PROVIDER_REQUEST_STATUS_LABELS = {
  pending: 'Pending',
  accepted: 'Accepted',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
  pickup_pending: 'Pickup Pending',
  completed: 'Completed',
};

// Reuse the listing-status badge colors from base.css for request
// statuses whose names don't have their own badge class.
const PROVIDER_REQUEST_BADGE_CLASS = {
  pending: 'pending',
  accepted: 'available',
  rejected: 'cancelled',
  cancelled: 'cancelled',
  pickup_pending: 'pickup_pending',
  completed: 'collected',
};

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function formatDateTime(dateTimeStr) {
  if (!dateTimeStr) return '';
  const d = new Date(dateTimeStr);
  if (Number.isNaN(d.getTime())) return dateTimeStr;
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

/** Sum of every request quantity that is already spoken for. */
function acceptedQuantity(requests) {
  return requests
    .filter((r) => r.status === 'accepted' || r.status === 'pickup_pending')
    .reduce((sum, r) => sum + (Number(r.requested_quantity) || 0), 0);
}

/** Pull an array out of an API response, whatever key it lives under. */
function listFrom(result, key) {
  const data = result && result.data;
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data[key])) return data[key];
  if (data && typeof data === 'object') {
    const firstArray = Object.values(data).find((v) => Array.isArray(v));
    if (firstArray) return firstArray;
  }
  return [];
}

/** Fetch every page of a list endpoint (limit=50 per page). */
async function fetchAllPages(path, key) {
  const sep = path.includes('?') ? '&' : '?';
  let page = 1;
  let all = [];
  while (true) {
    const result = await Api.get(`${path}${sep}page=${page}&limit=50`);
    all = all.concat(listFrom(result, key));
    const pg = result && result.data && result.data.pagination;
    if (!pg || page >= pg.total_pages || page >= 20) break;
    page += 1;
  }
  return all;
}

(function () {
  const root = document.querySelector('[data-page="provider-requests"]');
  if (!root) return;

  const scope = root.dataset.scope; // 'all' | 'listing'
  let groups = []; // [{ listing, requests }]

  function el(id) { return document.getElementById(id); }

  function hideAllNotices() {
    ['guest-notice', 'wrong-role-notice', 'no-profile-notice'].forEach((id) => {
      const n = el(id);
      if (n) n.hidden = true;
    });
  }

  function showGate(which) {
    hideAllNotices();
    el('dashboard').hidden = true;
    el(which).hidden = false;
  }

  function showError(message) {
    el('req-alert').innerHTML =
      `<div class="alert alert--error">${escapeHtml(message)}</div>`;
  }

  function showSuccess(message) {
    el('req-alert').innerHTML =
      `<div class="alert alert--success">${escapeHtml(message)}</div>`;
  }

  function clearAlert() { el('req-alert').innerHTML = ''; }

  // ---------- rendering ----------

  function requestCardHtml(listing, r) {
    const statusLabel = PROVIDER_REQUEST_STATUS_LABELS[r.status] || r.status;
    const badgeClass = PROVIDER_REQUEST_BADGE_CLASS[r.status] || r.status;
    const unit = listing && listing.quantity_unit ? listing.quantity_unit : '';
    const note = r.message || r.notes || '';
    const noteLine = note
      ? `<p class="listing-card__desc">${escapeHtml(note)}</p>` : '';
    const created = r.created_at
      ? `<p class="text-muted">Requested ${escapeHtml(formatDateTime(r.created_at))}</p>` : '';

    let actions = '';
    let scheduleForm = '';

    if (r.status === 'pending') {
      actions = `
        <button type="button" class="btn btn--primary" data-accept-id="${r.id}">Accept</button>
        <button type="button" class="btn btn--danger" data-reject-id="${r.id}">Reject</button>
      `;
    } else if (r.status === 'accepted') {
      actions = `
        <button type="button" class="btn btn--primary" data-schedule-toggle="${r.id}">Schedule Pickup</button>
      `;
      scheduleForm = `
        <form class="pickup-form" data-schedule-form="${r.id}" hidden novalidate>
          <div class="form-field">
            <label for="pickup-time-${r.id}">Pickup time (optional)</label>
            <input type="datetime-local" id="pickup-time-${r.id}" name="pickup_time">
          </div>
          <div class="form-field">
            <label for="pickup-note-${r.id}">Note for the recipient (optional)</label>
            <textarea id="pickup-note-${r.id}" name="confirmation_info" rows="2" maxlength="500"></textarea>
          </div>
          <div class="listing-card__actions">
            <button type="submit" class="btn btn--primary">Confirm Schedule</button>
            <button type="button" class="btn btn--secondary" data-schedule-cancel="${r.id}">Close</button>
          </div>
        </form>
      `;
    } else if (r.status === 'pickup_pending') {
      actions = `<a class="btn btn--secondary" href="/pickups">View Pickup</a>`;
    }

    return `
      <article class="card listing-card" data-request-card="${r.id}">
        <div class="listing-card__top">
          <span class="badge badge--${badgeClass}">${escapeHtml(statusLabel)}</span>
          <span class="text-muted listing-card__category">Request #${r.id}</span>
        </div>
        <h3>Recipient #${escapeHtml(r.recipient_id)}</h3>
        <p class="text-muted">Requested: ${escapeHtml(r.requested_quantity)} ${escapeHtml(unit)}</p>
        ${created}
        ${noteLine}
        <div class="listing-card__actions">${actions}</div>
        ${scheduleForm}
      </article>
    `;
  }

  function groupHtml(group, shown) {
    const { listing, requests } = group;
    const total = Number(listing.quantity) || 0;
    const remaining = Math.max(total - acceptedQuantity(requests), 0);
    const unit = listing.quantity_unit || '';
    const title = scope === 'all'
      ? `<h2><a href="/listings/${listing.id}">${escapeHtml(listing.food_name)}</a></h2>`
      : '';

    return `
      <section class="request-group" data-listing-group="${listing.id}">
        ${title}
        <p class="text-muted">
          Remaining: <strong>${escapeHtml(remaining)}</strong> of
          ${escapeHtml(total)} ${escapeHtml(unit)}
        </p>
        <div class="listings-grid">
          ${shown.map((r) => requestCardHtml(listing, r)).join('')}
        </div>
      </section>
    `;
  }

  function render() {
    const filter = el('status-filter').value;
    const groupsEl = el('req-groups');
    const emptyEl = el('req-empty');

    let html = '';
    let totalShown = 0;
    groups.forEach((g) => {
      const shown = filter
        ? g.requests.filter((r) => r.status === filter)
        : g.requests;
      if (!shown.length) return;
      totalShown += shown.length;
      html += groupHtml(g, shown);
    });

    if (!totalShown) {
      groupsEl.hidden = true;
      groupsEl.innerHTML = '';
      emptyEl.hidden = false;
      const anyRequests = groups.some((g) => g.requests.length);
      emptyEl.textContent = filter && anyRequests
        ? 'No requests with that status.'
        : 'No requests yet.';
      return;
    }

    emptyEl.hidden = true;
    groupsEl.innerHTML = html;
    groupsEl.hidden = false;
    wireActions(groupsEl);
  }

  function wireActions(container) {
    container.querySelectorAll('[data-accept-id]').forEach((btn) => {
      btn.addEventListener('click', () => act(btn.dataset.acceptId, 'accept', btn, 'Accept'));
    });
    container.querySelectorAll('[data-reject-id]').forEach((btn) => {
      btn.addEventListener('click', () => act(btn.dataset.rejectId, 'reject', btn, 'Reject'));
    });
    container.querySelectorAll('[data-schedule-toggle]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const form = container.querySelector(`[data-schedule-form="${btn.dataset.scheduleToggle}"]`);
        if (form) form.hidden = !form.hidden;
      });
    });
    container.querySelectorAll('[data-schedule-cancel]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const form = container.querySelector(`[data-schedule-form="${btn.dataset.scheduleCancel}"]`);
        if (form) form.hidden = true;
      });
    });
    container.querySelectorAll('[data-schedule-form]').forEach((form) => {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        submitSchedule(form.dataset.scheduleForm, form);
      });
    });
  }

  // ---------- actions ----------

  const ACT_SUCCESS_MESSAGES = {
    accept: 'Request accepted.',
    reject: 'Request rejected.',
  };

  async function handleAuthOrShow(err, fallback) {
    if (err.status === 401) {
      if (typeof renderAuthArea === 'function') renderAuthArea();
      showGate('guest-notice');
      return;
    }
    showError(err.message || fallback);
  }

  async function act(requestId, action, btn, label) {
    if (action === 'reject' &&
        !confirm('Reject this request? The recipient will be notified.')) {
      return;
    }

    clearAlert();
    btn.disabled = true;
    btn.textContent = 'Working...';

    try {
      await Api.post(`/api/requests/${requestId}/${action}`);
      await load({ silent: true });
      showSuccess(ACT_SUCCESS_MESSAGES[action] || `${label} done.`);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = label;
      await handleAuthOrShow(err, `Could not ${label.toLowerCase()}. Please try again.`);
      const card = document.querySelector(`[data-request-card="${requestId}"]`);
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  async function submitSchedule(requestId, form) {
    clearAlert();
    const submitBtn = form.querySelector('button[type="submit"]');
    const body = {};
    const time = form.elements.pickup_time.value;
    const info = form.elements.confirmation_info.value.trim();
    if (time) body.pickup_time = time;
    if (info) body.confirmation_info = info;

    submitBtn.disabled = true;
    submitBtn.textContent = 'Scheduling...';

    try {
      await Api.post(`/api/requests/${requestId}/schedule-pickup`, body);
      await load({ silent: true });
      showSuccess('Pickup scheduled.');
    } catch (err) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Confirm Schedule';
      await handleAuthOrShow(err, 'Could not schedule the pickup. Please try again.');
    }
  }

  // ---------- loading ----------

  async function fetchGroups() {
    if (scope === 'listing') {
      const listingRes = await Api.get(`/api/listings/${LISTING_ID}`);
      const listing = listingRes.data.listing || listingRes.data;
      const requests = await fetchAllPages(`/api/listings/${LISTING_ID}/requests`, 'requests');
      const summary = el('listing-summary');
      if (summary) {
        summary.textContent =
          `${listing.food_name} - ${listing.quantity} ${listing.quantity_unit || ''}`.trim();
      }
      return [{ listing, requests }];
    }

    const listings = await fetchAllPages('/api/listings/mine', 'listings');
    const results = await Promise.all(
      listings.map((l) =>
        fetchAllPages(`/api/listings/${l.id}/requests`, 'requests').catch(() => [])
      )
    );
    return listings
      .map((listing, i) => ({ listing, requests: results[i] }))
      .filter((g) => g.requests.length);
  }

  async function load(options = {}) {
    const loadingEl = el('req-loading');

    if (!options.silent) {
      loadingEl.hidden = false;
      el('req-groups').hidden = true;
      el('req-empty').hidden = true;
    }

    try {
      groups = await fetchGroups();
      loadingEl.hidden = true;
      el('filter-bar').hidden = false;
      render();
    } catch (err) {
      loadingEl.hidden = true;
      if (err.status === 401) {
        if (typeof renderAuthArea === 'function') renderAuthArea();
        showGate('guest-notice');
        return;
      }
      if (err.code === 'PROFILE_NOT_FOUND') {
        showGate('no-profile-notice');
        return;
      }
      showError(err.message || 'Could not load requests. Please try again.');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const user = Auth.isLoggedIn() ? Auth.getUser() : null;
    if (!user) {
      showGate('guest-notice');
      return;
    }
    if (user.role !== 'provider') {
      showGate('wrong-role-notice');
      return;
    }

    hideAllNotices();
    el('dashboard').hidden = false;
    el('status-filter').addEventListener('change', render);
    load();
  });
})();
