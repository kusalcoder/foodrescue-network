/**
 * FoodRescue Network — listings feed page (Phase 3)
 *
 * Drives templates/listings/index.html: filters (category, city,
 * near-me), pagination, and rendering the card grid. Built on top of
 * the Api/Auth helpers from api.js (Phase 1).
 *
 * GET /api/listings requires a token (any logged-in role can
 * browse), so the first thing this does is bounce signed-out
 * visitors to /login rather than showing a broken, empty page.
 */

(function () {
  if (!Auth.isLoggedIn()) {
    document.getElementById('login-required').hidden = false;
    document.getElementById('listings-page').hidden = true;
    return;
  }

  const STATUS_LABELS = {
    available: 'Available',
    reserved: 'Reserved',
    pickup_pending: 'Pickup Pending',
    collected: 'Collected',
    expired: 'Expired',
    cancelled: 'Cancelled',
  };

  const CATEGORY_LABELS = {
    prepared_food: 'Prepared Food',
    packaged_food: 'Packaged Food',
    bakery: 'Bakery',
    fruits: 'Fruits',
    vegetables: 'Vegetables',
    other: 'Other',
  };

  let currentPage = 1;
  let currentPagination = null;

  const grid = document.getElementById('listings-grid');
  const loadingEl = document.getElementById('listings-loading');
  const emptyEl = document.getElementById('listings-empty');
  const alertEl = document.getElementById('listings-alert');
  const paginationEl = document.getElementById('pagination');
  const pageInfoEl = document.getElementById('page-info');

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }

  function formatDateTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    });
  }

  function buildQuery() {
    const params = new URLSearchParams();
    params.set('page', currentPage);

    const category = document.getElementById('filter-category').value;
    const city = document.getElementById('filter-city').value.trim();
    const nearMe = document.getElementById('filter-near-me').checked;

    if (category) params.set('category', category);
    if (city) params.set('city', city);
    if (nearMe) params.set('near_me', 'true');

    return params.toString();
  }

  function renderCard(listing) {
    const badgeClass = `badge badge--${listing.status}`;
    const statusLabel = STATUS_LABELS[listing.status] || listing.status;
    const categoryLabel = CATEGORY_LABELS[listing.category] || listing.category;
    const distance = listing.distance_km != null
      ? `<p class="text-muted listing-card__distance">${listing.distance_km} km away</p>`
      : '';

    const card = document.createElement('a');
    card.className = 'card listing-card';
    card.href = `/listings/${listing.id}`;
    card.innerHTML = `
      <div class="listing-card__top">
        <h3>${escapeHtml(listing.food_name)}</h3>
        <span class="${badgeClass}">${escapeHtml(statusLabel)}</span>
      </div>
      <p class="text-muted">${escapeHtml(categoryLabel)} &middot; ${escapeHtml(listing.quantity)} ${escapeHtml(listing.quantity_unit)}</p>
      <p class="listing-card__pickup">Pickup: ${escapeHtml(formatDateTime(listing.pickup_start_time))} – ${escapeHtml(formatDateTime(listing.pickup_end_time))}</p>
      <p class="text-muted">${escapeHtml(listing.pickup_location)}</p>
      ${distance}
    `;
    return card;
  }

  async function loadListings() {
    loadingEl.hidden = false;
    emptyEl.hidden = true;
    alertEl.innerHTML = '';
    grid.innerHTML = '';
    paginationEl.hidden = true;

    try {
      const query = buildQuery();
      const result = await Api.get(`/api/listings?${query}`);
      const { listings, pagination } = result.data;
      currentPagination = pagination;

      if (listings.length === 0) {
        emptyEl.hidden = false;
      } else {
        listings.forEach((listing) => grid.appendChild(renderCard(listing)));
      }

      if (pagination.total_pages > 1) {
        paginationEl.hidden = false;
        pageInfoEl.textContent = `Page ${pagination.page} of ${pagination.total_pages} (${pagination.total} total)`;
        document.getElementById('prev-page').disabled = pagination.page <= 1;
        document.getElementById('next-page').disabled = pagination.page >= pagination.total_pages;
      }
    } catch (err) {
      if (err.status === 401) {
        window.location.href = '/login';
        return;
      }
      alertEl.innerHTML = `<div class="alert alert--error">${escapeHtml(err.message || 'Could not load listings.')}</div>`;
    } finally {
      loadingEl.hidden = true;
    }
  }

  document.getElementById('filter-form').addEventListener('submit', (event) => {
    event.preventDefault();
    currentPage = 1;
    loadListings();
  });

  document.getElementById('clear-filters').addEventListener('click', () => {
    document.getElementById('filter-category').value = '';
    document.getElementById('filter-city').value = '';
    document.getElementById('filter-near-me').checked = false;
    currentPage = 1;
    loadListings();
  });

  document.getElementById('prev-page').addEventListener('click', () => {
    if (currentPage > 1) {
      currentPage -= 1;
      loadListings();
    }
  });

  document.getElementById('next-page').addEventListener('click', () => {
    if (currentPagination && currentPage < currentPagination.total_pages) {
      currentPage += 1;
      loadListings();
    }
  });

  loadListings();
})();