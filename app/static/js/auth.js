/**
 * FoodRescue Network — shared auth-state UI (Phase 1, updated Phase 2/4)
 *
 * Runs on every page (included in base.html) and fills in the
 * `[data-auth-area]` slot in the navbar: either Login/Register links
 * (signed out) or the user's name + a Logout button (signed in).
 *
 * Depends on api.js being loaded first (for the Auth helper).
 *
 * Phase 2 adds the real /login and /register pages, so the links
 * below now point at real URLs instead of Phase 1's "#" placeholders.
 *
 * Phase 4 adds `[data-role-only="provider"]` (comma-separate for
 * multiple roles, e.g. `data-role-only="provider,admin"`) so nav
 * links like "My Listings" only show for the roles that can use
 * them — signed out, or signed in as the wrong role, both hide it.
 */

function renderAuthArea() {
  const area = document.querySelector('[data-auth-area]');
  if (!area) return;

  const guestOnlyEls = document.querySelectorAll('[data-guest-only]');
  const authOnlyEls = document.querySelectorAll('[data-auth-only]');
  const user = Auth.isLoggedIn() ? Auth.getUser() : null;

  if (user) {
    area.innerHTML = `
      <span class="text-muted">Hi, ${escapeHtml(user.name)}</span>
      <button type="button" class="btn btn--secondary" data-action="logout">Log Out</button>
    `;
    guestOnlyEls.forEach((el) => (el.hidden = true));
    authOnlyEls.forEach((el) => (el.hidden = false));

    area.querySelector('[data-action="logout"]').addEventListener('click', handleLogout);
  } else {
    area.innerHTML = `
      <a href="/login">Log In</a>
      <a class="btn btn--primary" href="/register">Register</a>
    `;
    guestOnlyEls.forEach((el) => (el.hidden = false));
    authOnlyEls.forEach((el) => (el.hidden = true));
  }

  applyRoleVisibility(user);

  // The landing page's hero buttons use data-nav instead of real
  // hrefs so they keep working even on pages where [data-auth-area]
  // wouldn't otherwise touch them.
  document.querySelectorAll('[data-nav="login"]').forEach((el) => (el.href = '/login'));
  document.querySelectorAll('[data-nav="register"]').forEach((el) => (el.href = '/register'));
}

function applyRoleVisibility(user) {
  document.querySelectorAll('[data-role-only]').forEach((el) => {
    const allowedRoles = el.dataset.roleOnly.split(',').map((r) => r.trim());
    el.hidden = !(user && allowedRoles.includes(user.role));
  });
}

async function handleLogout() {
  try {
    await Api.post('/api/auth/logout');
  } catch (err) {
    // Even if the network call fails, clear the local session so the
    // user isn't stuck "logged in" on a token that no longer works.
  } finally {
    Auth.clearSession();
    window.location.href = '/';
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', renderAuthArea);
