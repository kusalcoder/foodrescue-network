/**
 * FoodRescue Network — admin reports (Phase 11)
 *
 * Drives templates/admin/reports.html. Calls the real backend
 * endpoint, GET /api/reports/platform-summary (app/routes/reports.py
 * -> app/reports/service.py: platform_summary()), which returns:
 *
 *   {
 *     users_by_role: {provider: N, recipient: N, admin: N},
 *     listings_by_status: {...},
 *     recipients_by_verification: {...},
 *     total_distributions: N,
 *     total_quantity_distributed: N
 *   }
 *
 * Rendered generically rather than hard-coded to those exact keys:
 * any top-level number/string becomes a stat card, any nested object
 * becomes a labeled breakdown table, any array of objects becomes a
 * table with columns inferred from its first item. This means it
 * keeps working even if platform_summary() grows new fields later.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function titleCase(key) {
  return String(key).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

(function () {
  const guestNotice = document.getElementById('guest-notice');
  const wrongRoleNotice = document.getElementById('wrong-role-notice');
  const pageEl = document.getElementById('reports-page');
  if (!pageEl) return;

  const user = Auth.isLoggedIn() ? Auth.getUser() : null;
  if (!user) { guestNotice.hidden = false; return; }
  if (user.role !== 'admin') { wrongRoleNotice.hidden = false; return; }

  pageEl.hidden = false;

  function showAlert(message, type = 'error') {
    document.getElementById('page-alert').innerHTML =
      `<div class="alert alert--${type}">${escapeHtml(message)}</div>`;
  }

  function renderStatCard(key, value) {
    return `
      <div class="stat-card">
        <div class="stat-card__value">${escapeHtml(value)}</div>
        <div class="stat-card__label">${escapeHtml(titleCase(key))}</div>
      </div>`;
  }

  function renderBreakdown(key, obj) {
    const rows = Object.entries(obj)
      .map(([k, v]) => `<tr><td>${escapeHtml(titleCase(k))}</td><td>${escapeHtml(v)}</td></tr>`)
      .join('');
    return `
      <div class="breakdown">
        <h2>${escapeHtml(titleCase(key))}</h2>
        <table class="data-table">
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function renderList(key, arr) {
    if (arr.length === 0) return '';
    if (typeof arr[0] === 'object' && arr[0] !== null) {
      const cols = Object.keys(arr[0]);
      const head = cols.map((c) => `<th>${escapeHtml(titleCase(c))}</th>`).join('');
      const body = arr.map((row) =>
        `<tr>${cols.map((c) => `<td>${escapeHtml(row[c])}</td>`).join('')}</tr>`
      ).join('');
      return `
        <div class="breakdown">
          <h2>${escapeHtml(titleCase(key))}</h2>
          <table class="data-table">
            <thead><tr>${head}</tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>`;
    }
    return `
      <div class="breakdown">
        <h2>${escapeHtml(titleCase(key))}</h2>
        <p>${arr.map((v) => escapeHtml(v)).join(', ')}</p>
      </div>`;
  }

  async function load() {
    const loadingEl = document.getElementById('reports-loading');
    const contentEl = document.getElementById('reports-content');
    const statCardsEl = document.getElementById('stat-cards');
    const breakdownsEl = document.getElementById('breakdowns');

    try {
      const result = await Api.get('/api/reports/platform-summary');
      const data = result.data || {};

      const statCards = [];
      const breakdowns = [];

      Object.entries(data).forEach(([key, value]) => {
        if (typeof value === 'number' || typeof value === 'string') {
          statCards.push(renderStatCard(key, value));
        } else if (Array.isArray(value)) {
          breakdowns.push(renderList(key, value));
        } else if (value && typeof value === 'object') {
          breakdowns.push(renderBreakdown(key, value));
        }
      });

      if (statCards.length === 0 && breakdowns.length === 0) {
        showAlert('The reports endpoint returned no recognizable data.', 'info');
      }

      statCardsEl.innerHTML = statCards.join('');
      breakdownsEl.innerHTML = breakdowns.join('');
      contentEl.hidden = false;
    } catch (err) {
      if (err.status === 401) { window.location.href = '/login'; return; }
      if (err.status === 404) {
        showAlert('The /api/reports/platform-summary endpoint was not found.');
      } else {
        showAlert(err.message || 'Could not load reports.');
      }
    } finally {
      loadingEl.hidden = true;
    }
  }

  load();
})();
