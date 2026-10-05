/**
 * Help With Food — Orphanages & Receivers Search
 *
 * Drives templates/recipients/index.html. Fetches GET /api/recipients
 * with search, city, and verified_only filter parameters.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

(function () {
  const pageRoot = document.querySelector('[data-page="recipients-directory"]');
  if (!pageRoot) return;

  const user = Auth.isLoggedIn() ? Auth.getUser() : null;
  if (user && user.role === 'recipient') {
    window.location.href = '/listings';
    return;
  }

  const searchForm = document.getElementById('recipient-search-form');
  const searchInput = document.getElementById('recipient-search-input');
  const cityInput = document.getElementById('recipient-city-input');
  const verifiedFilter = document.getElementById('recipient-verified-filter');
  const gridEl = document.getElementById('recipients-grid');
  const loadingEl = document.getElementById('recipients-loading');
  const emptyEl = document.getElementById('recipients-empty');
  const alertEl = document.getElementById('recipients-alert');
  const paginationEl = document.getElementById('recipients-pagination');
  const prevBtn = document.getElementById('prev-page-btn');
  const nextBtn = document.getElementById('next-page-btn');
  const pageIndicator = document.getElementById('page-indicator');

  let currentPage = 1;
  const limit = 12;

  function showAlert(msg, type = 'error') {
    alertEl.innerHTML = `<div class="alert alert--${type}">${escapeHtml(msg)}</div>`;
  }

  function recipientCardHtml(r) {
    const orgName = r.organization_name || 'Orphanage / Receiver';
    const locParts = [r.address, r.city, r.state, r.pincode].filter(Boolean).map(escapeHtml);
    const location = locParts.join(', ') || 'Location on file';
    const desc = r.description ? `<p class="listing-card__desc">${escapeHtml(r.description)}</p>` : '';
    const phone = r.phone || r.contact_info;
    const email = r.email;

    const isVerified = r.verification_status === 'verified';
    const statusBadge = isVerified
      ? `<span class="badge badge--available">✓ Verified Organization</span>`
      : `<span class="badge badge--pending">Verification Pending</span>`;

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

    const mapLink = (r.latitude && r.longitude)
      ? `<a href="/map?lat=${r.latitude}&lng=${r.longitude}" class="btn btn--secondary btn--small">📍 View on Map</a>`
      : '';

    const donateLink = Auth.isLoggedIn() && Auth.getUser().role === 'provider'
      ? `<a href="/listings/new" class="btn btn--primary btn--small">Donate Food</a>`
      : '';

    return `
      <article class="card listing-card" data-recipient-id="${escapeHtml(r.id)}">
        <div class="listing-card__top">
          <span class="badge badge--collected">Orphanage / Shelter</span>
          ${statusBadge}
        </div>
        <h3 style="margin-bottom: 0.25rem;">${escapeHtml(orgName)}</h3>
        <p class="text-muted" style="margin-bottom: var(--space-2);">📍 ${escapeHtml(location)}</p>
        ${desc}
        ${contactBlock}
        <div class="listing-card__actions" style="margin-top: var(--space-3);">
          ${mapLink}
          ${donateLink}
        </div>
      </article>
    `;
  }

  async function loadRecipients() {
    alertEl.innerHTML = '';
    loadingEl.hidden = false;
    gridEl.hidden = true;
    emptyEl.hidden = true;
    paginationEl.hidden = true;

    const search = searchInput.value.trim();
    const city = cityInput.value.trim();
    const verifiedOnly = verifiedFilter.value;

    const params = new URLSearchParams({
      page: currentPage,
      limit: limit,
      verified_only: verifiedOnly,
    });
    if (search) params.set('search', search);
    if (city) params.set('city', city);

    try {
      const res = await Api.get(`/api/recipients?${params.toString()}`);
      loadingEl.hidden = true;

      const data = res.data || {};
      const recipients = data.recipients || [];
      const pagination = data.pagination || { total_pages: 1, page: 1 };

      if (!recipients.length) {
        emptyEl.hidden = false;
        gridEl.innerHTML = '';
        return;
      }

      gridEl.innerHTML = recipients.map(recipientCardHtml).join('');
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
      showAlert(err.message || 'Could not load orphanages. Please try again.');
    }
  }

  searchForm.addEventListener('submit', (e) => {
    e.preventDefault();
    currentPage = 1;
    loadRecipients();
  });

  verifiedFilter.addEventListener('change', () => {
    currentPage = 1;
    loadRecipients();
  });

  prevBtn.addEventListener('click', () => {
    if (currentPage > 1) {
      currentPage--;
      loadRecipients();
    }
  });

  nextBtn.addEventListener('click', () => {
    currentPage++;
    loadRecipients();
  });

  // Initial load
  loadRecipients();
})();
