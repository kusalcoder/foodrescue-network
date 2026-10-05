/**
 * Help With Food — Provider Search & Directory
 *
 * Drives templates/providers/index.html. Fetches GET /api/providers
 * with search and city filter parameters.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

(function () {
  const pageRoot = document.querySelector('[data-page="providers-directory"]');
  if (!pageRoot) return;

  const user = Auth.isLoggedIn() ? Auth.getUser() : null;
  if (user && user.role === 'provider') {
    window.location.href = '/listings';
    return;
  }

  const searchForm = document.getElementById('provider-search-form');
  const searchInput = document.getElementById('provider-search-input');
  const cityInput = document.getElementById('provider-city-input');
  const gridEl = document.getElementById('providers-grid');
  const loadingEl = document.getElementById('providers-loading');
  const emptyEl = document.getElementById('providers-empty');
  const alertEl = document.getElementById('providers-alert');
  const paginationEl = document.getElementById('providers-pagination');
  const prevBtn = document.getElementById('prev-page-btn');
  const nextBtn = document.getElementById('next-page-btn');
  const pageIndicator = document.getElementById('page-indicator');

  let currentPage = 1;
  const limit = 12;

  function showAlert(msg, type = 'error') {
    alertEl.innerHTML = `<div class="alert alert--${type}">${escapeHtml(msg)}</div>`;
  }

  function providerCardHtml(p) {
    const orgName = p.organization_name || 'Food Provider';
    const locParts = [p.address, p.city, p.state, p.pincode].filter(Boolean).map(escapeHtml);
    const location = locParts.join(', ') || 'Location on file';
    const desc = p.description ? `<p class="listing-card__desc">${escapeHtml(p.description)}</p>` : '';
    const phone = p.phone || p.contact_info;
    const email = p.email;

    let contactBlock = '';
    if (phone || email) {
      contactBlock = `
        <div class="contact-box" style="margin-top: var(--space-2); padding: var(--space-2) var(--space-3);">
          <div class="contact-links">
            ${phone ? `<a href="tel:${escapeHtml(phone)}" class="contact-link">📞 ${escapeHtml(phone)}</a>` : ''}
            ${email ? `<a href="mailto:${escapeHtml(email)}" class="contact-link">✉️ ${escapeHtml(email)}</a>` : ''}
          </div>
        </div>
      `;
    }

    const activeDonations = p.active_donations_count != null
      ? `<span class="badge badge--available">${p.active_donations_count} active donation${p.active_donations_count === 1 ? '' : 's'}</span>`
      : '';

    const mapLink = (p.latitude && p.longitude)
      ? `<a href="/map?lat=${p.latitude}&lng=${p.longitude}" class="btn btn--secondary btn--small">📍 View on Map</a>`
      : '';

    return `
      <article class="card listing-card" data-provider-id="${escapeHtml(p.id)}">
        <div class="listing-card__top">
          <span class="badge badge--available">Provider</span>
          ${activeDonations}
        </div>
        <h3 style="margin-bottom: 0.25rem;">${escapeHtml(orgName)}</h3>
        <p class="text-muted" style="margin-bottom: var(--space-2);">📍 ${escapeHtml(location)}</p>
        ${desc}
        ${contactBlock}
        <div class="listing-card__actions" style="margin-top: var(--space-3);">
          <a href="/listings?search=${encodeURIComponent(orgName)}" class="btn btn--primary btn--small">View Donations</a>
          ${mapLink}
        </div>
      </article>
    `;
  }

  async function loadProviders() {
    alertEl.innerHTML = '';
    loadingEl.hidden = false;
    gridEl.hidden = true;
    emptyEl.hidden = true;
    paginationEl.hidden = true;

    const search = searchInput.value.trim();
    const city = cityInput.value.trim();

    const params = new URLSearchParams({
      page: currentPage,
      limit: limit,
    });
    if (search) params.set('search', search);
    if (city) params.set('city', city);

    try {
      const res = await Api.get(`/api/providers?${params.toString()}`);
      loadingEl.hidden = true;

      const data = res.data || {};
      const providers = data.providers || [];
      const pagination = data.pagination || { total_pages: 1, page: 1 };

      if (!providers.length) {
        emptyEl.hidden = false;
        gridEl.innerHTML = '';
        return;
      }

      gridEl.innerHTML = providers.map(providerCardHtml).join('');
      gridEl.hidden = false;

      // Handle pagination
      if (pagination.total_pages > 1) {
        paginationEl.hidden = false;
        pageIndicator.textContent = `Page ${pagination.page} of ${pagination.total_pages}`;
        prevBtn.disabled = pagination.page <= 1;
        nextBtn.disabled = pagination.page >= pagination.total_pages;
      } else {
        paginationEl.hidden = true;
      }
    } catch (err) {
      loadingEl.hidden = true;
      showAlert(err.message || 'Could not load providers. Please try again.');
    }
  }

  searchForm.addEventListener('submit', (e) => {
    e.preventDefault();
    currentPage = 1;
    loadProviders();
  });

  prevBtn.addEventListener('click', () => {
    if (currentPage > 1) {
      currentPage--;
      loadProviders();
    }
  });

  nextBtn.addEventListener('click', () => {
    currentPage++;
    loadProviders();
  });

  // Initial load
  loadProviders();
})();
