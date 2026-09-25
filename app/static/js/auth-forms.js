/**
 * FoodRescue Network — register/login form handling (Phase 2)
 *
 * Shared by both auth/register.html and auth/login.html (only one of
 * #register-form / #login-form exists on any given page, so each
 * block below just no-ops if its form isn't present).
 *
 * Client-side checks here mirror the backend's real rules
 * (app/utils/validation.py) so people get instant feedback, but the
 * backend is still the source of truth — every server-side
 * VALIDATION_ERROR is also shown, in case the two ever drift.
 */

function clearFormErrors(form) {
  form.querySelectorAll('.field-error').forEach((el) => (el.textContent = ''));
  document.getElementById('form-alert').innerHTML = '';
}

function showAlert(message, type = 'error') {
  document.getElementById('form-alert').innerHTML =
    `<div class="alert alert--${type}">${escapeHtml(message)}</div>`;
}

function showFieldError(fieldName, message) {
  const el = document.querySelector(`[data-error-for="${fieldName}"]`);
  if (el) el.textContent = message;
}

function setSubmitting(button, isSubmitting, idleLabel) {
  button.disabled = isSubmitting;
  button.textContent = isSubmitting ? 'Please wait…' : idleLabel;
}

// ---------- Register ----------

const registerForm = document.getElementById('register-form');
if (registerForm) {
  registerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFormErrors(registerForm);

    const name = document.getElementById('name').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    const role = document.getElementById('role').value;

    let hasError = false;
    if (!name) { showFieldError('name', 'Name is required.'); hasError = true; }
    if (!email) { showFieldError('email', 'Email is required.'); hasError = true; }
    if (password.length < 8 || !/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
      showFieldError('password', 'Password must be at least 8 characters with both letters and numbers.');
      hasError = true;
    }
    if (!role) { showFieldError('role', 'Please select a role.'); hasError = true; }
    if (hasError) return;

    const submitBtn = document.getElementById('submit-btn');
    setSubmitting(submitBtn, true, 'Create Account');

    try {
      await Api.post('/api/auth/register', { name, email, password, role });
      showAlert('Account created! Logging you in…', 'success');

      // Registration doesn't return a token, so log in immediately
      // afterward for a one-step signup experience.
      const loginResult = await Api.post('/api/auth/login', { email, password });
      Auth.setSession(loginResult.data.token, loginResult.data.user);
      window.location.href = '/';
    } catch (err) {
      if (err.code === 'VALIDATION_ERROR') {
        showAlert(err.message);
      } else if (err.code === 'EMAIL_ALREADY_REGISTERED') {
        showFieldError('email', err.message);
      } else if (err.code === 'RATE_LIMITED') {
        showAlert('Too many attempts. Please wait a few minutes and try again.');
      } else {
        showAlert(err.message || 'Something went wrong. Please try again.');
      }
    } finally {
      setSubmitting(submitBtn, false, 'Create Account');
    }
  });
}

// ---------- Login ----------

const loginForm = document.getElementById('login-form');
if (loginForm) {
  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFormErrors(loginForm);

    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    let hasError = false;
    if (!email) { showFieldError('email', 'Email is required.'); hasError = true; }
    if (!password) { showFieldError('password', 'Password is required.'); hasError = true; }
    if (hasError) return;

    const submitBtn = document.getElementById('submit-btn');
    setSubmitting(submitBtn, true, 'Log In');

    try {
      const result = await Api.post('/api/auth/login', { email, password });
      Auth.setSession(result.data.token, result.data.user);
      window.location.href = '/';
    } catch (err) {
      if (err.code === 'INVALID_CREDENTIALS') {
        showAlert('Incorrect email or password.');
      } else if (err.code === 'ACCOUNT_INACTIVE') {
        showAlert('This account has been deactivated. Contact an administrator.');
      } else if (err.code === 'RATE_LIMITED') {
        showAlert('Too many attempts. Please wait a few minutes and try again.');
      } else {
        showAlert(err.message || 'Something went wrong. Please try again.');
      }
    } finally {
      setSubmitting(submitBtn, false, 'Log In');
    }
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
