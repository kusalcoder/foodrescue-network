/**
 * FoodRescue Network — admin audit log (Phase 11)
 *
 * Drives templates/admin/audit_log.html. Matches the real backend
 * (app/routes/audit.py):
 *
 *   GET /api/audit-logs?user_id=&action=&resource_type=&start_date=&end_date=&page=&limit=
 *       -> { audit_logs: [...], pagination: { page, limit, total, total_pages } }
 *
 * Entry fields (AuditLog.to_dict()): id, user_id, action,
 * resource_type, resource_id, description, timestamp.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

(function () {
  const guestNotice = document.getElementById('guest-notice');
  const wrongRoleNotice = document.getElementById('wrong-role-notice');
  const pageEl = document.getElementById('audit-page');
  if (!pageEl) return;

  const user = Auth.isLoggedIn() ? Auth.getUser() : null;
  if (!user) { guestNotice.hidden = false; return; }
  if (user.role !== 'admin') { wrongRoleNotice.hidden = false; return; }

  pageEl.hidden = false;

  const LIMIT = 25;
  let currentPage = 1;

  function showAlert(message, type = 'error') {
    document.getElementById('page-alert').innerHTML =
      `<div class="alert alert--${type}">${escapeHtml(message)}</div>`;
  }

  function fieldTimestamp(e) {
    if (!e.timestamp) return '—';
    const d = new Date(e.timestamp);
    return isNaN(d) ? String(e.timestamp) : d.toLocaleString();
  }
  function fieldResource(e) {
    if (!e.resource_type) return '—';
    return e.resource_id != null ? `${e.resource_type} #${e.resource_id}` : e.resource_type;
  }

  function renderRow(e) {
    return `
      <tr>
        <td>${escapeHtml(fieldTimestamp(e))}</td>
        <td>${e.user_id != null ? escapeHtml(e.user_id) : '—'}</td>
        <td>${escapeHtml(e.action)}</td>
        <td>${escapeHtml(fieldResource(e))}</td>
        <td>${escapeHtml(e.description || '—')}</td>
      </tr>`;
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const action = document.getElementById('action-filter').value.trim();
    const resourceType = document.getElementById('resource-type-filter').value.trim();
    const startDate = document.getElementById('start-date-filter').value;
    const endDate = document.getElementById('end-date-filter').value;
    if (action) params.set('action', action);
    if (resourceType) params.set('resource_type', resourceType);
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    params.set('page', String(currentPage));
    params.set('limit', String(LIMIT));
    return params.toString();
  }

  async function load() {
    const loadingEl = document.getElementById('audit-loading');
    const wrapEl = document.getElementById('audit-table-wrap');
    const tbody = document.getElementById('audit-tbody');
    const emptyEl = document.getElementById('audit-empty');

    loadingEl.hidden = false;
    wrapEl.hidden = true;
    document.getElementById('page-alert').innerHTML = '';

    try {
      const result = await Api.get(`/api/audit-logs?${buildQuery()}`);
      const items = result.data.audit_logs || [];
      const pagination = result.data.pagination || {};

      tbody.innerHTML = items.map(renderRow).join('');
      emptyEl.hidden = items.length !== 0;

      const totalPages = pagination.total_pages || 1;
      document.getElementById('page-indicator').textContent =
        `Page ${pagination.page || currentPage} of ${totalPages} (${pagination.total ?? items.length} total)`;
      document.getElementById('prev-page').disabled = (pagination.page || currentPage) <= 1;
      document.getElementById('next-page').disabled = (pagination.page || currentPage) >= totalPages;
    } catch (err) {
      if (err.status === 401) { window.location.href = '/login'; return; }
      showAlert(err.message || 'Could not load the audit log.');
    } finally {
      loadingEl.hidden = true;
      wrapEl.hidden = false;
    }
  }

  document.getElementById('apply-filters').addEventListener('click', () => { currentPage = 1; load(); });
  document.getElementById('prev-page').addEventListener('click', () => { if (currentPage > 1) { currentPage--; load(); } });
  document.getElementById('next-page').addEventListener('click', () => { currentPage++; load(); });

  load();
})();
