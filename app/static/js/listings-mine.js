/**
 * FoodRescue Network - "My Listings" provider dashboard (Phase 4)
 *
 * Renders GET /api/listings/mine (no pagination - it's just "every
 * listing owned by the current provider", per the API docs).
 *
 * Three things have to be true before this page can show anything
 * useful, checked in order:
 *   1. logged in at all
 *   2. logged in as a PROVIDER (not a recipient or admin)
 *   3. that provider has already completed a provider profile
 *      (POST /api/providers/profile) - the API 404s with
 *      PROFILE_NOT_FOUND otherwise, since a profile UI doesn't exist
 *      yet (that's a later phase)
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

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatTime(dateTimeStr) {
  if (!dateTimeStr) return '';
  const d = new Date(dateTimeStr);
  if (Number.isNaN(d.getTime())) return dateTimeStr;
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function listingCardHtml(listing) {
  const categoryLabel = CATEGORY_LABELS[listing.category] || listing.category;
  const statusLabel = STATUS_LABELS[listing.status] || listing.status;
  const canManage = listing.status === 'available';

  const editBtn = canManage
    ? `<a class="btn btn--secondary" href="/listings/${listing.id}/edit">Edit</a>`
    : '';
  const cancelBtn = canManage
    ? `<button type="button" class="btn btn--danger" data-cancel-id="${listing.id}">Cancel</button>`
    : '';

  return `
    <article class="card listing-card" data-listing-card="${listing.id}">
      <div class="listing-card__top">
        <span class="badge badge--${listing.status}">${escapeHtml(statusLabel)}</span>
        <span class="text-muted listing-card__category">${escapeHtml(categoryLabel)}</span>
      </div>
      <h3>${escapeHtml(listing.food_name)}</h3>
      <ul class="listing-card__meta">
        <li>${listing.quantity} ${escapeHtml(listing.quantity_unit)}</li>
        <li>Pickup ${formatDate(listing.available_date)}, ${formatTime(listing.pickup_start_time)}–${formatTime(listing.pickup_end_time)}</li>
        <li>${escapeHtml(listing.pickup_location)}</li>
      </ul>
      <div class="listing-card__actions">
        <a class="btn btn--secondary" href="/listings/${listing.id}">View</a>
        ${editBtn}
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
    const { data } = await Api.get('/api/listings/mine');
    loadingEl.hidden = true;

    if (!data.length) {
      emptyEl.hidden = false;
      return;
    }

    gridEl.innerHTML = data.map(listingCardHtml).join('');
    gridEl.hidden = false;
    gridEl.querySelectorAll('[data-cancel-id]').forEach((btn) => {
      btn.addEventListener('click', () => handleCancel(btn.dataset.cancelId));
    });
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
    alertEl.innerHTML = `<div class="alert alert--error">${escapeHtml(err.message || 'Could not load your listings. Please try again.')}</div>`;
  }
}

async function handleCancel(listingId) {
  if (!confirm('Cancel this listing? This cannot be undone.')) return;

  const card = document.querySelector(`[data-listing-card="${listingId}"]`);
  const alertEl = document.getElementById('mine-alert');

  try {
    await Api.post(`/api/listings/${listingId}/cancel`);
    await loadMine();
    alertEl.innerHTML = '<div class="alert alert--success">Listing cancelled.</div>';
  } catch (err) {
    const message = err.message || 'Could not cancel this listing. Please try again.';
    alertEl.innerHTML = `<div class="alert alert--error">${escapeHtml(message)}</div>`;
    if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function showGate() {
  document.getElementById('guest-notice').hidden = Auth.isLoggedIn();
  const user = Auth.isLoggedIn() ? Auth.getUser() : null;
  document.getElementById('wrong-role-notice').hidden = !user || user.role === 'provider';
  document.getElementById('dashboard').hidden = true;
  document.getElementById('no-profile-notice').hidden = true;
}

document.addEventListener('DOMContentLoaded', () => {
  if (!document.querySelector('[data-page="my-listings"]')) return;

  const user = Auth.isLoggedIn() ? Auth.getUser() : null;

  if (!user || user.role !== 'provider') {
    showGate();
    return;
  }

  document.getElementById('dashboard').hidden = false;
  loadMine();
});