/**
 * FoodRescue Network — admin user management (Phase 11)
 *
 * Drives templates/admin/users.html. Matches the real backend
 * (app/routes/admin.py):
 *
 *   GET  /api/admin/users?role=&status=&search=&page=&limit=
 *        -> { users: [...], pagination: { page, limit, total, total_pages } }
 *   POST /api/admin/users/<id>/activate
 *   POST /api/admin/users/<id>/deactivate
 *        both -> { ...user }  (updated user object)
 *
 * User fields (User.to_dict()): id, name, email, role, status,
 * created_at, updated_at. `status` is the string "active"/"inactive".
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

(function () {
  const guestNotice = document.getElementById('guest-notice');
  const wrongRoleNotice = document.getElementById('wrong-role-notice');
  const pageEl = document.getElementById('users-page');
  if (!pageEl) return;

  const user = Auth.isLoggedIn() ? Auth.getUser() : null;
  if (!user) {
    guestNotice.hidden = false;
    return;
  }
  if (user.role !== 'admin') {
    wrongRoleNotice.hidden = false;
    return;
  }

  pageEl.hidden = false;

  const LIMIT = 20;
  let currentPage = 1;

  function showAlert(message, type = 'error') {
    document.getElementById('page-alert').innerHTML =
      `<div class="alert alert--${type}">${escapeHtml(message)}</div>`;
  }

  function fieldJoined(u) {
    if (!u.created_at) return '—';
    const d = new Date(u.created_at);
    return isNaN(d) ? String(u.created_at) : d.toLocaleDateString();
  }

  const tabBtns = document.querySelectorAll('[data-admin-tab]');
  let activeTabRole = '';

  tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      tabBtns.forEach((b) => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      const tabVal = btn.dataset.adminTab;
      activeTabRole = tabVal === 'all' ? '' : tabVal;
      document.getElementById('role-filter').value = activeTabRole;
      currentPage = 1;
      load();
    });
  });

  function renderRow(u) {
    const status = u.status; // "active" | "inactive"
    const badgeClass = status === 'active' ? 'badge--success' : 'badge--muted';
    const nextAction = status === 'active' ? 'deactivate' : 'activate';
    const actionLabel = status === 'active' ? 'Deactivate' : 'Activate';

    const profile = u.provider_profile || u.recipient_profile;
    const orgName = profile && profile.organization_name ? profile.organization_name : u.name;
    const phone = profile ? (profile.phone || profile.contact_info) : '';
    const email = u.email;
    const address = profile ? [profile.address, profile.city].filter(Boolean).join(', ') : '—';

    let vBadge = '';
    let verifyBtn = '';
    if (u.role === 'recipient') {
      const vStatus = (profile && profile.verification_status) || 'pending';
      const vClass = vStatus === 'verified' ? 'badge--available' : (vStatus === 'rejected' ? 'badge--cancelled' : 'badge--pending');
      vBadge = `<div><span class="badge ${vClass}" style="font-size:0.75rem; margin-top: 0.2rem;">${vStatus}</span></div>`;

      if (vStatus === 'pending' && profile && profile.id) {
        verifyBtn = `<button type="button" class="btn btn--primary btn--small" data-verify-recipient="${profile.id}">Verify</button>`;
      }
    }

    const contactHtml = `
      <div style="font-size:0.88rem;">
        ${phone ? `<div>📞 <a href="tel:${escapeHtml(phone)}">${escapeHtml(phone)}</a></div>` : ''}
        <div>✉️ <a href="mailto:${escapeHtml(email)}">${escapeHtml(email)}</a></div>
      </div>
    `;

    return `
      <tr data-user-id="${escapeHtml(u.id)}">
        <td>${escapeHtml(u.id)}</td>
        <td>
          <strong>${escapeHtml(orgName)}</strong>
          ${u.name !== orgName ? `<div class="text-muted" style="font-size:0.82rem;">Owner: ${escapeHtml(u.name)}</div>` : ''}
          ${vBadge}
        </td>
        <td>${contactHtml}</td>
        <td><span class="badge badge--collected">${escapeHtml(u.role)}</span></td>
        <td style="font-size:0.88rem;">${escapeHtml(address)}</td>
        <td><span class="badge ${badgeClass}">${escapeHtml(status)}</span></td>
        <td style="font-size:0.85rem;">${escapeHtml(fieldJoined(u))}</td>
        <td>
          <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
            ${verifyBtn}
            <button type="button" class="btn btn--secondary btn--small" data-toggle-action="${nextAction}">${actionLabel}</button>
          </div>
        </td>
      </tr>`;
  }

  async function toggleUser(userId, action) {
    const row = document.querySelector(`tr[data-user-id="${userId}"]`);
    const btn = row ? row.querySelector('[data-toggle-action]') : null;
    if (btn) { btn.disabled = true; btn.textContent = '…'; }

    try {
      await Api.post(`/api/admin/users/${userId}/${action}`);
      showAlert(`User #${userId} ${action}d successfully.`, 'success');
      load();
    } catch (err) {
      if (err.status === 401) { window.location.href = '/login'; return; }
      showAlert(err.message || `Could not ${action} that user.`);
      if (btn) {
        btn.disabled = false;
        btn.textContent = action === 'activate' ? 'Activate' : 'Deactivate';
      }
    }
  }

  async function verifyRecipient(recipientProfileId, btn) {
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
      await Api.post(`/api/recipients/${recipientProfileId}/verify`);
      showAlert(`Recipient profile #${recipientProfileId} verified successfully.`, 'success');
      load();
    } catch (err) {
      showAlert(err.message || 'Could not verify recipient profile.');
      if (btn) { btn.disabled = false; btn.textContent = 'Verify'; }
    }
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const role = document.getElementById('role-filter').value;
    const status = document.getElementById('status-filter').value;
    const search = document.getElementById('search-filter').value.trim();
    if (role) params.set('role', role);
    if (status) params.set('status', status);
    if (search) params.set('search', search);
    params.set('page', String(currentPage));
    params.set('limit', String(LIMIT));
    return params.toString();
  }

  async function load() {
    const loadingEl = document.getElementById('users-loading');
    const wrapEl = document.getElementById('users-table-wrap');
    const tbody = document.getElementById('users-tbody');
    const emptyEl = document.getElementById('users-empty');

    loadingEl.hidden = false;
    wrapEl.hidden = true;
    document.getElementById('page-alert').innerHTML = '';

    try {
      const result = await Api.get(`/api/admin/users?${buildQuery()}`);
      const items = result.data.users || [];
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
      showAlert(err.message || 'Could not load users.');
    } finally {
      loadingEl.hidden = true;
      wrapEl.hidden = false;
    }
  }

  document.getElementById('role-filter').addEventListener('change', () => { currentPage = 1; load(); });
  document.getElementById('status-filter').addEventListener('change', () => { currentPage = 1; load(); });
  document.getElementById('search-filter').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { currentPage = 1; load(); }
  });
  document.getElementById('prev-page').addEventListener('click', () => { if (currentPage > 1) { currentPage--; load(); } });
  document.getElementById('next-page').addEventListener('click', () => { currentPage++; load(); });

  document.getElementById('users-tbody').addEventListener('click', (event) => {
    const toggleBtn = event.target.closest('[data-toggle-action]');
    if (toggleBtn) {
      const row = toggleBtn.closest('tr');
      const userId = row.getAttribute('data-user-id');
      toggleUser(userId, toggleBtn.getAttribute('data-toggle-action'));
      return;
    }

    const verifyBtn = event.target.closest('[data-verify-recipient]');
    if (verifyBtn) {
      const recipientId = verifyBtn.getAttribute('data-verify-recipient');
      verifyRecipient(recipientId, verifyBtn);
    }
  });

  load();
})();
