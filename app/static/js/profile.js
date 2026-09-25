/**
 * FoodRescue Network — organization profile (Phase 10)
 *
 * Drives templates/profile/mine.html for BOTH provider and recipient
 * accounts. The field set is identical between
 * ProviderProfile/RecipientProfile (see app/services/provider_service.py
 * and recipient_service.py — organization_name, contact_info, address,
 * city, latitude, longitude, description), so one form covers both;
 * only the API base path and a couple of recipient-only extras
 * (verification status, the profile-ID note) differ, switched on
 * `myRole`.
 *
 * ── Create vs. update ──────────────────────────────────────────────
 * There's no single "upsert" endpoint — POST creates (fails with
 * PROFILE_ALREADY_EXISTS if one exists), PUT updates (fails with
 * PROFILE_NOT_FOUND if one doesn't). So this always does a GET first
 * to find out which mode applies, then wires the form's submit to
 * POST or PUT accordingly, exactly like listing-form.js (Phase 4)
 * does for create-vs-edit.
 *
 * ── Why the profile ID is shown prominently for recipients ─────────
 * POST /api/recipients/<id>/verify (the only verification endpoint
 * that exists) takes a profile ID directly — there's no admin-facing
 * "list pending recipients" endpoint to pick one from (see
 * PHASE10_SETUP.md). So a recipient needs to be able to find and
 * share their own profile ID with an administrator; this page is
 * where that ID lives.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

(function () {
  const guestNotice = document.getElementById('guest-notice');
  const wrongRoleNotice = document.getElementById('wrong-role-notice');
  const pageEl = document.getElementById('profile-page');
  if (!pageEl) return;

  const user = Auth.isLoggedIn() ? Auth.getUser() : null;
  if (!user) {
    guestNotice.hidden = false;
    return;
  }
  if (user.role !== 'provider' && user.role !== 'recipient') {
    wrongRoleNotice.hidden = false;
    return;
  }

  const myRole = user.role;
  const basePath = myRole === 'provider' ? '/api/providers/profile' : '/api/recipients/profile';
  let isEditing = false;

  function showAlert(message, type = 'error') {
    document.getElementById('form-alert').innerHTML =
      `<div class="alert alert--${type}">${escapeHtml(message)}</div>`;
  }

  function clearErrors() {
    document.querySelectorAll('.field-error').forEach((el) => (el.textContent = ''));
    document.getElementById('form-alert').innerHTML = '';
  }

  function showFieldError(field, message) {
    const el = document.querySelector(`[data-error-for="${field}"]`);
    if (el) el.textContent = message;
  }

  function fillForm(profile) {
    document.getElementById('organization_name').value = profile.organization_name || '';
    document.getElementById('contact_info').value = profile.contact_info || '';
    document.getElementById('address').value = profile.address || '';
    document.getElementById('city').value = profile.city || '';
    document.getElementById('latitude').value = profile.latitude != null ? profile.latitude : '';
    document.getElementById('longitude').value = profile.longitude != null ? profile.longitude : '';
    document.getElementById('description').value = profile.description || '';
  }

  function renderVerificationBanner(profile) {
    if (myRole !== 'recipient') return;
    const banner = document.getElementById('verification-banner');
    const status = profile.verification_status;
    const alertType = status === 'verified' ? 'success' : 'info';
    const statusLabel = status === 'verified' ? 'Verified' : 'Pending Verification';

    let note = '';
    if (status !== 'verified') {
      note = `<p style="margin: var(--space-2) 0 0;">
        Your <strong>Profile ID is ${escapeHtml(profile.id)}</strong> — share this
        with an administrator so they can verify your organization. You can't
        request listings until this is done.
      </p>`;
    }

    banner.innerHTML = `<div class="alert alert--${alertType}">
      <strong>Status:</strong> ${escapeHtml(statusLabel)}
      ${note}
    </div>`;
    banner.hidden = false;
  }

  function readForm() {
    const latRaw = document.getElementById('latitude').value;
    const lngRaw = document.getElementById('longitude').value;

    const payload = {
      organization_name: document.getElementById('organization_name').value.trim(),
      contact_info: document.getElementById('contact_info').value.trim() || null,
      address: document.getElementById('address').value.trim() || null,
      city: document.getElementById('city').value.trim() || null,
      description: document.getElementById('description').value.trim() || null,
    };

    // Only send latitude/longitude at all when BOTH fields actually
    // have something in them — a lone value is left out of the
    // payload entirely (rather than paired with a null) so
    // validateClientSide below can still tell "only one filled in"
    // apart from "neither filled in" using the raw field values.
    if (latRaw !== '' && lngRaw !== '') {
      payload.latitude = parseFloat(latRaw);
      payload.longitude = parseFloat(lngRaw);
    }

    return payload;
  }

  function validateClientSide(payload) {
    let ok = true;
    if (!payload.organization_name) {
      showFieldError('organization_name', 'Organization name is required.');
      ok = false;
    }
    const latRaw = document.getElementById('latitude').value;
    const lngRaw = document.getElementById('longitude').value;
    if ((latRaw !== '') !== (lngRaw !== '')) {
      showFieldError('coordinates', 'Both latitude and longitude must be provided together.');
      ok = false;
    }
    return ok;
  }

  async function load() {
    const loadingEl = document.getElementById('form-loading');
    const formEl = document.getElementById('profile-form');

    try {
      const result = await Api.get(basePath);
      isEditing = true;
      document.getElementById('page-title').textContent = 'My Profile';
      document.getElementById('submit-btn').textContent = 'Save Changes';
      fillForm(result.data);
      renderVerificationBanner(result.data);
    } catch (err) {
      if (err.status === 401) {
        window.location.href = '/login';
        return;
      }
      if (err.code === 'PROFILE_NOT_FOUND') {
        isEditing = false;
        document.getElementById('page-title').textContent = 'Create My Profile';
        document.getElementById('submit-btn').textContent = 'Create Profile';
      } else {
        showAlert(err.message || 'Could not load your profile.');
      }
    } finally {
      loadingEl.hidden = true;
      formEl.hidden = false;
      pageEl.hidden = false;
    }
  }

  document.getElementById('profile-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    clearErrors();

    const payload = readForm();
    if (!validateClientSide(payload)) return;

    const submitBtn = document.getElementById('submit-btn');
    const idleLabel = isEditing ? 'Save Changes' : 'Create Profile';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving…';

    try {
      const result = isEditing
        ? await Api.put(basePath, payload)
        : await Api.post(basePath, payload);

      if (!isEditing) {
        isEditing = true;
        document.getElementById('page-title').textContent = 'My Profile';
        submitBtn.textContent = 'Save Changes';
      } else {
        submitBtn.textContent = idleLabel;
      }
      fillForm(result.data);
      renderVerificationBanner(result.data);
      showAlert('Profile saved.', 'success');
    } catch (err) {
      submitBtn.textContent = idleLabel;
      if (err.code === 'VALIDATION_ERROR') {
        showAlert(err.message);
      } else if (err.code === 'PROFILE_ALREADY_EXISTS') {
        // Only reachable via a stale page (e.g. two tabs) — recover
        // by switching straight to edit mode instead of leaving a
        // dead-end error.
        isEditing = true;
        document.getElementById('page-title').textContent = 'My Profile';
        submitBtn.textContent = 'Save Changes';
        showAlert('A profile already existed — showing it now. Save again to update it.');
        load();
      } else {
        showAlert(err.message || 'Could not save your profile. Please try again.');
      }
    } finally {
      submitBtn.disabled = false;
    }
  });

  load();
})();
