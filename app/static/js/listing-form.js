/**
 * FoodRescue Network — create/edit listing form (Phase 4)
 *
 * Shared by listings/new.html and listings/edit.html; which one it's
 * on is read from the section's `data-mode` ("create" or "edit") and
 * `data-listing-id` attributes.
 *
 * Datetime handling: HTML `datetime-local` inputs have no timezone
 * concept — the value is just local wall-clock time. The API wants
 * full ISO-8601 with an explicit UTC offset (e.g.
 * "2026-09-10T17:00:00+00:00"), and Python's `datetime.fromisoformat`
 * on the backend doesn't reliably accept a trailing "Z" depending on
 * Python version, so we build the "+HH:MM"/"-HH:MM" offset by hand
 * instead of using `Date.prototype.toISOString()`.
 *
 * Phase 12: added client-side field validation (mirrors the
 * required attributes already on these inputs) and a "Saving…"
 * button state, matching the pattern used in auth-forms.js.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

function clearFieldErrors(form) {
  form.querySelectorAll('.field-error').forEach((el) => (el.textContent = ''));
}

function showFieldError(fieldName, message) {
  const el = document.querySelector(`[data-error-for="${fieldName}"]`);
  if (el) el.textContent = message;
}

function setSubmitting(button, isSubmitting, idleLabel) {
  button.disabled = isSubmitting;
  button.textContent = isSubmitting ? 'Saving…' : idleLabel;
}

function validateForm(form) {
  let hasError = false;

  if (!form.food_name.value.trim()) {
    showFieldError('food_name', 'Food name is required.');
    hasError = true;
  }
  if (!form.category.value) {
    showFieldError('category', 'Please select a category.');
    hasError = true;
  }
  if (!form.quantity.value || Number(form.quantity.value) <= 0) {
    showFieldError('quantity', 'Enter a quantity greater than 0.');
    hasError = true;
  }
  if (!form.quantity_unit.value.trim()) {
    showFieldError('quantity_unit', 'Unit is required (e.g. meals, kg, boxes).');
    hasError = true;
  }
  if (!form.available_date.value) {
    showFieldError('available_date', 'Available date is required.');
    hasError = true;
  }
  if (!form.pickup_start_time.value) {
    showFieldError('pickup_start_time', 'Pickup start time is required.');
    hasError = true;
  }
  if (!form.pickup_end_time.value) {
    showFieldError('pickup_end_time', 'Pickup end time is required.');
    hasError = true;
  }
  if (
    form.pickup_start_time.value &&
    form.pickup_end_time.value &&
    new Date(form.pickup_end_time.value) <= new Date(form.pickup_start_time.value)
  ) {
    showFieldError('pickup_end_time', 'Pickup end time must be after the start time.');
    hasError = true;
  }
  if (!form.pickup_location.value.trim()) {
    showFieldError('pickup_location', 'Pickup location is required.');
    hasError = true;
  }

  return !hasError;
}

// "2026-09-10T17:00" (local wall-clock, from a datetime-local input)
// -> "2026-09-10T17:00:00+05:30" (or whatever the browser's offset is)
function localInputToIso(localValue) {
  if (!localValue) return null;
  const d = new Date(localValue);
  if (Number.isNaN(d.getTime())) return null;

  const offsetMin = -d.getTimezoneOffset();
  const sign = offsetMin >= 0 ? '+' : '-';
  const abs = Math.abs(offsetMin);

  const datePart = `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  const timePart = `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  const offsetPart = `${sign}${pad2(Math.floor(abs / 60))}:${pad2(abs % 60)}`;

  return `${datePart}T${timePart}${offsetPart}`;
}

// ISO-8601 (with any offset, e.g. from the API) -> "2026-09-10T17:00"
// for a datetime-local input, in the browser's local time.
function isoToLocalInputValue(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function readForm(form) {
  const data = {
    food_name: form.food_name.value.trim(),
    description: form.description.value.trim() || null,
    category: form.category.value,
    quantity: form.quantity.value ? Number(form.quantity.value) : null,
    quantity_unit: form.quantity_unit.value.trim(),
    available_date: form.available_date.value || null,
    pickup_start_time: localInputToIso(form.pickup_start_time.value),
    pickup_end_time: localInputToIso(form.pickup_end_time.value),
    pickup_location: form.pickup_location.value.trim(),
    conditions: form.conditions.value.trim() || null,
  };

  const latRaw = form.latitude.value.trim();
  const lngRaw = form.longitude.value.trim();
  data.latitude = latRaw ? Number(latRaw) : null;
  data.longitude = lngRaw ? Number(lngRaw) : null;

  return data;
}

function fillForm(form, listing) {
  form.food_name.value = listing.food_name || '';
  form.description.value = listing.description || '';
  form.category.value = listing.category || '';
  form.quantity.value = listing.quantity != null ? listing.quantity : '';
  form.quantity_unit.value = listing.quantity_unit || '';
  form.available_date.value = listing.available_date || '';
  form.pickup_start_time.value = isoToLocalInputValue(listing.pickup_start_time);
  form.pickup_end_time.value = isoToLocalInputValue(listing.pickup_end_time);
  form.pickup_location.value = listing.pickup_location || '';
  form.latitude.value = listing.latitude != null ? listing.latitude : '';
  form.longitude.value = listing.longitude != null ? listing.longitude : '';
  form.conditions.value = listing.conditions || '';
}

function showGate(section) {
  const user = Auth.isLoggedIn() ? Auth.getUser() : null;
  document.getElementById('guest-notice').hidden = !!user;
  document.getElementById('wrong-role-notice').hidden = !user || user.role === 'provider';
  document.getElementById('form-wrapper').hidden = true;
  const loadingEl = document.getElementById('form-loading');
  if (loadingEl) loadingEl.hidden = true;
}

async function initCreate() {
  const form = document.getElementById('listing-form');
  document.getElementById('form-wrapper').hidden = false;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitBtn = document.getElementById('submit-btn');
    const alertEl = document.getElementById('form-alert');
    alertEl.innerHTML = '';
    clearFieldErrors(form);

    if (!validateForm(form)) return;

    setSubmitting(submitBtn, true, 'Create Listing');

    try {
      const { data } = await Api.post('/api/listings', readForm(form));
      window.location.href = `/listings/${data.id}`;
    } catch (err) {
      setSubmitting(submitBtn, false, 'Create Listing');
      alertEl.innerHTML = `<div class="alert alert--error">${escapeHtml(err.message || 'Could not create this listing. Please check the form and try again.')}</div>`;
    }
  });
}

async function initEdit(listingId) {
  const loadingEl = document.getElementById('form-loading');
  const loadErrorEl = document.getElementById('load-error-notice');
  const wrapper = document.getElementById('form-wrapper');
  const form = document.getElementById('listing-form');

  loadingEl.hidden = false;

  try {
    const { data: listing } = await Api.get(`/api/listings/${listingId}`);
    loadingEl.hidden = true;

    if (listing.status !== 'available') {
      loadErrorEl.hidden = false;
      loadErrorEl.textContent = 'This listing can no longer be edited — only listings with status "available" can be changed. Cancel and create a new one instead if details need to change.';
      return;
    }

    fillForm(form, listing);
    wrapper.hidden = false;

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submitBtn = document.getElementById('submit-btn');
      const alertEl = document.getElementById('form-alert');
      alertEl.innerHTML = '';
      clearFieldErrors(form);

      if (!validateForm(form)) return;

      setSubmitting(submitBtn, true, 'Save Changes');

      try {
        await Api.put(`/api/listings/${listingId}`, readForm(form));
        window.location.href = `/listings/${listingId}`;
      } catch (err) {
        setSubmitting(submitBtn, false, 'Save Changes');
        alertEl.innerHTML = `<div class="alert alert--error">${escapeHtml(err.message || 'Could not save changes. Please check the form and try again.')}</div>`;
      }
    });
  } catch (err) {
    loadingEl.hidden = true;
    if (err.status === 401) {
      if (typeof renderAuthArea === 'function') renderAuthArea();
      showGate();
      return;
    }
    loadErrorEl.hidden = false;
    loadErrorEl.textContent = err.code === 'LISTING_NOT_FOUND'
      ? "This listing doesn't exist or may have been removed."
      : (err.message || 'Could not load this listing. Please try again.');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const section = document.querySelector('[data-page="listing-form"]');
  if (!section) return;

  const mode = section.dataset.mode;
  const user = Auth.isLoggedIn() ? Auth.getUser() : null;

  if (!user || user.role !== 'provider') {
    showGate(section);
    return;
  }

  if (mode === 'create') {
    initCreate();
  } else if (mode === 'edit') {
    initEdit(section.dataset.listingId);
  }
});