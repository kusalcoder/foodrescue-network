/**
 * FoodRescue Network — single listing detail page (Phase 3, updated Phase 5)
 *
 * Renders GET /api/listings/<id>, same as Phase 3.
 *
 * Phase 5 adds the actual request flow where the old "Request Pickup"
 * stub button used to be: if the viewer is logged in as a RECIPIENT
 * and the listing is still `available`, we check whether they already
 * have an active (pending/accepted) request against it — and either
 * show that status, or show the request form. Submitting posts to
 * POST /api/requests and sends them to /requests/mine on success.
 *
 * Requesting also requires a *verified* recipient profile
 * (`RECIPIENT_NOT_VERIFIED` from the API otherwise) — there's no
 * proactive check for that here, it's just surfaced as a submit
 * error, since profile verification itself has no UI yet (see
 * PHASE5_SETUP.md for the manual admin-verification workaround).
 */

const CATEGORY_LABELS = {
  prepared_food: 'Prepared Food',
  packaged_food: 'Packaged Food',
  bakery: 'Bakery',
  fruits: 'Fruits',
  vegetables: 'Vegetables',
  other: 'Other',
};

const STATUS_LABELS = {
  available: 'Available',
  reserved: 'Reserved',
  pickup_pending: 'Pickup Pending',
  collected: 'Collected',
  expired: 'Expired',
  cancelled: 'Cancelled',
};

const REQUEST_STATUS_LABELS = {
  pending: 'Pending',
  accepted: 'Accepted',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
  pickup_pending: 'Pickup Pending',
  completed: 'Completed',
};

let currentListing = null;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

function formatDateTime(dateTimeStr) {
  if (!dateTimeStr) return '—';
  const d = new Date(dateTimeStr);
  if (Number.isNaN(d.getTime())) return dateTimeStr;
  return d.toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

function renderListing(listing) {
  const categoryLabel = CATEGORY_LABELS[listing.category] || listing.category;
  const statusLabel = STATUS_LABELS[listing.status] || listing.status;
  const canRequest = listing.status === 'available';

  const mapLink = listing.latitude !== null && listing.longitude !== null
    ? ` &middot; <a href="https://www.google.com/maps/search/?api=1&query=${listing.latitude},${listing.longitude}" target="_blank" rel="noopener">View on map</a>`
    : '';

  const description = listing.description
    ? `<div class="listing-detail__section"><h3>Description</h3><p>${escapeHtml(listing.description)}</p></div>`
    : '';

  const conditions = listing.conditions
    ? `<div class="listing-detail__section"><h3>Pickup conditions</h3><p>${escapeHtml(listing.conditions)}</p></div>`
    : '';

  const content = document.getElementById('detail-content');
  content.innerHTML = `
    <div class="listing-detail__header">
      <span class="badge badge--${listing.status}">${escapeHtml(statusLabel)}</span>
      <span class="text-muted">${escapeHtml(categoryLabel)}</span>
    </div>
    <h1>${escapeHtml(listing.food_name)}</h1>

    <dl class="listing-detail__facts">
      <dt>Quantity</dt><dd>${listing.quantity} ${escapeHtml(listing.quantity_unit)}</dd>
      <dt>Available date</dt><dd>${formatDate(listing.available_date)}</dd>
      <dt>Pickup window</dt><dd>${formatDateTime(listing.pickup_start_time)} &ndash; ${formatDateTime(listing.pickup_end_time)}</dd>
      <dt>Pickup location</dt><dd>${escapeHtml(listing.pickup_location)}${mapLink}</dd>
      <dt>Posted by</dt><dd>Provider #${listing.provider_id}</dd>
    </dl>

    ${description}
    ${conditions}

    ${canRequest ? '' : '<p class="text-muted listing-detail__unavailable-note">This listing is no longer available.</p>'}
  `;
}

function showAlreadyRequested(existingRequest) {
  const note = document.getElementById('already-requested-note');
  const statusLabel = REQUEST_STATUS_LABELS[existingRequest.status] || existingRequest.status;
  note.hidden = false;
  note.innerHTML = `You already have a request for this listing (status: <strong>${escapeHtml(statusLabel)}</strong>).
    <a href="/requests/mine">View your requests</a>.`;
  document.getElementById('request-form').hidden = true;
}

async function checkExistingRequestAndShowForm(listing) {
  const section = document.getElementById('request-section');
  section.hidden = false;

  const qtyInput = document.getElementById('requested_quantity');
  qtyInput.max = listing.quantity;

  try {
    const { data: myRequests } = await Api.get('/api/requests');
    const active = myRequests.find(
      (r) => r.listing_id === listing.id && (r.status === 'pending' || r.status === 'accepted')
    );
    if (active) {
      showAlreadyRequested(active);
    }
  } catch (err) {
    // If we can't check (e.g. no recipient profile yet), just leave
    // the form visible — submitting will surface the real error
    // (PROFILE_NOT_FOUND, RECIPIENT_NOT_VERIFIED, etc.) instead.
  }
}

function wireRequestForm(listingId) {
  const form = document.getElementById('request-form');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const alertEl = document.getElementById('request-alert');
    const submitBtn = document.getElementById('request-submit-btn');
    alertEl.innerHTML = '';
    submitBtn.disabled = true;

    const payload = {
      listing_id: listingId,
      requested_quantity: form.requested_quantity.value ? Number(form.requested_quantity.value) : null,
      request_message: form.request_message.value.trim() || null,
    };

    try {
      await Api.post('/api/requests', payload);
      window.location.href = '/requests/mine';
    } catch (err) {
      submitBtn.disabled = false;
      alertEl.innerHTML = `<div class="alert alert--error">${escapeHtml(err.message || 'Could not submit your request. Please try again.')}</div>`;
    }
  });
}

async function loadListing() {
  const section = document.querySelector('.listing-detail');
  const listingId = Number(section.dataset.listingId);

  const alertEl = document.getElementById('detail-alert');
  const loadingEl = document.getElementById('detail-loading');
  const contentEl = document.getElementById('detail-content');

  try {
    const { data: listing } = await Api.get(`/api/listings/${listingId}`);
    currentListing = listing;
    loadingEl.hidden = true;
    contentEl.hidden = false;
    renderListing(listing);

    const user = Auth.isLoggedIn() ? Auth.getUser() : null;
    if (user && user.role === 'recipient' && listing.status === 'available') {
      wireRequestForm(listingId);
      await checkExistingRequestAndShowForm(listing);
    }
  } catch (err) {
    loadingEl.hidden = true;
    if (err.status === 401) {
      if (typeof renderAuthArea === 'function') renderAuthArea();
      return;
    }
    const message = err.code === 'LISTING_NOT_FOUND'
      ? "This listing doesn't exist or may have been removed."
      : (err.message || 'Could not load this listing. Please try again.');
    alertEl.innerHTML = `<div class="alert alert--error">${escapeHtml(message)}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const section = document.querySelector('.listing-detail');
  if (!section || !Auth.isLoggedIn()) return;
  loadListing();
});
