/**
 * FoodRescue Network — admin recipient verification (Phase 10)
 *
 * Drives templates/admin/verify_recipient.html: a single form
 * (profile ID) submitting POST /api/recipients/<id>/verify.
 *
 * This asks for the ID directly rather than offering a list to pick
 * from because no such list exists on the backend yet — see
 * PHASE10_SETUP.md for the reasoning and what a proper fix would
 * look like (a GET /api/admin/recipients?verification_status=pending
 * endpoint, which doesn't exist today). Phase 11's fuller admin
 * dashboard is the natural place to add that, once it does.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

(function () {
  const guestNotice = document.getElementById('guest-notice');
  const wrongRoleNotice = document.getElementById('wrong-role-notice');
  const pageEl = document.getElementById('verify-page');
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

  function showAlert(message, type = 'error') {
    document.getElementById('form-alert').innerHTML =
      `<div class="alert alert--${type}">${escapeHtml(message)}</div>`;
  }

  document.getElementById('verify-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    document.getElementById('form-alert').innerHTML = '';
    document.querySelectorAll('.field-error').forEach((el) => (el.textContent = ''));
    document.getElementById('result-card').hidden = true;

    const profileIdInput = document.getElementById('profile-id');
    const profileId = profileIdInput.value.trim();
    if (!profileId) {
      document.querySelector('[data-error-for="profile-id"]').textContent = 'Enter a profile ID.';
      return;
    }

    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Verifying…';

    try {
      const result = await Api.post(`/api/recipients/${profileId}/verify`);
      const profile = result.data;

      const resultCard = document.getElementById('result-card');
      resultCard.innerHTML = `
        <div class="alert alert--success">
          <strong>${escapeHtml(profile.organization_name)}</strong> (Profile #${escapeHtml(profile.id)})
          is now <strong>${escapeHtml(profile.verification_status)}</strong>.
        </div>
      `;
      resultCard.hidden = false;
      profileIdInput.value = '';
    } catch (err) {
      if (err.status === 401) {
        window.location.href = '/login';
        return;
      }
      showAlert(err.message || 'Could not verify that profile. Please check the ID and try again.');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Verify';
    }
  });
})();
