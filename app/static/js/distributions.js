/**
 * FoodRescue Network — distribution history (Phase 8)
 *
 * Drives templates/distributions/mine.html. Read-only by design —
 * app/models/distribution_record.py's own docstring says these rows
 * are permanent and never edited once created (spec section 17 /
 * rule #6), so unlike every other dashboard so far, there are no
 * action buttons here at all.
 *
 * Shared by both roles, same as /pickups: GET /api/distributions
 * returns records scoped to whichever profile(s) the current user
 * has. A card shows "You provided" or "You received" based on the
 * viewer's role — since every record returned by this endpoint is
 * already guaranteed to have the current user on one side or the
 * other, role alone is enough to know which, with no need to
 * compare profile ids client-side.
 *
 * No running totals are shown here (e.g. "12kg distributed total")
 * because that would only be honest if computed across every page,
 * and this endpoint paginates — a client-side sum would silently be
 * wrong past the first page. That aggregate math already exists,
 * correctly, on the backend's reporting endpoints
 * (GET /api/reports/distributions/summary), which is a later phase's
 * job to surface, not this one's to approximate.
 *
 * Same N+1-but-cached listing lookup as Phase 6/7's dashboards:
 * DistributionRecord.to_dict() only returns listing_id, not the
 * listing's food name, so each unique listing is fetched once.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function formatDateTime(iso) {
  if (!iso) return 'Not recorded';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

const CATEGORY_LABELS = {
  prepared_food: 'Prepared Food',
  packaged_food: 'Packaged Food',
  bakery: 'Bakery',
  fruits: 'Fruits',
  vegetables: 'Vegetables',
  other: 'Other',
};

(function () {
  const root = document.querySelector('[data-page="my-distributions"]');
  if (!root) return;

  let currentPage = 1;
  let currentPagination = null;
  let myRole = null;
  const listingCache = {}; // listing_id -> listing dict (or null on failure)

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
    el('dist-alert').innerHTML =
      `<div class="alert alert--error">${escapeHtml(message)}</div>`;
  }

  async function fetchUncachedListings(ids) {
    const missing = [...new Set(ids)].filter((id) => id != null && !(id in listingCache));
    if (!missing.length) return;
    const results = await Promise.all(
      missing.map((id) => Api.get(`/api/listings/${id}`).then((r) => r.data).catch(() => null))
    );
    missing.forEach((id, i) => { listingCache[id] = results[i]; });
  }

function cardHtml(record, myRole) {
  const listing = listingCache[record.listing_id];
  const title = listing ? escapeHtml(listing.food_name) : `Listing #${record.listing_id}`;
  const categoryLabel = record.food_category
    ? (CATEGORY_LABELS[record.food_category] || record.food_category)
    : null;

  // GET /api/distributions already scopes results to records where
  // the current user's profile is on one side or the other (see
  // list_distributions_query) — so which side is "mine" follows
  // directly from role, with no need to compare profile ids here.
  const roleLine = myRole === 'provider' ? 'You provided this' : 'You received this';

  const quantityUnit = listing ? listing.quantity_unit : '';

  return `
    <article class="card listing-card">
      <div class="listing-card__top">
        <span class="badge badge--collected">Completed</span>
        <span class="text-muted listing-card__category">${escapeHtml(formatDateTime(record.pickup_datetime))}</span>
      </div>
      <h3><a href="/listings/${record.listing_id}">${title}</a></h3>
      <p class="text-muted">${escapeHtml(roleLine)}</p>
      <ul class="listing-card__meta">
        <li>${escapeHtml(record.quantity)} ${escapeHtml(quantityUnit)}</li>
        ${categoryLabel ? `<li>${escapeHtml(categoryLabel)}</li>` : ''}
      </ul>
    </article>
  `;
}

  async function load() {
    const loadingEl = el('dist-loading');
    const gridEl = el('dist-grid');
    const emptyEl = el('dist-empty');
    const paginationEl = el('pagination');

    loadingEl.hidden = false;
    gridEl.hidden = true;
    emptyEl.hidden = true;
    paginationEl.hidden = true;
    el('dist-alert').innerHTML = '';

    try {
      const result = await Api.get(`/api/distributions?page=${currentPage}&limit=20`);
      const { distributions, pagination } = result.data;
      currentPagination = pagination;

      await fetchUncachedListings(distributions.map((d) => d.listing_id));

      loadingEl.hidden = true;

      if (!distributions.length) {
        emptyEl.hidden = false;
      } else {
        gridEl.innerHTML = distributions.map((d) => cardHtml(d, myRole)).join('');
        gridEl.hidden = false;
      }

      if (pagination.total_pages > 1) {
        paginationEl.hidden = false;
        el('page-info').textContent =
          `Page ${pagination.page} of ${pagination.total_pages} (${pagination.total} total)`;
        el('prev-page').disabled = pagination.page <= 1;
        el('next-page').disabled = pagination.page >= pagination.total_pages;
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
      showError(err.message || 'Could not load your distribution history. Please try again.');
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
