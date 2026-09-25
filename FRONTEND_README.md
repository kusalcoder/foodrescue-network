# FoodRescue Network — Frontend

Server-rendered pages (Jinja2 templates via Flask) + vanilla JS that
calls the existing JSON API under `/api/*`. No build step, no
frontend framework — just templates, CSS, and plain `<script>` files.

## Phase 1 — Project Setup & Base Layout

**What's included:**

- `app/routes/frontend.py` — new blueprint, registered at the site
  root (`/`), separate from the `/api/*` blueprints. Currently just
  serves the landing page; every later phase adds its routes here.
- `app/templates/base.html` — the shared layout every page extends:
  header/nav (with a `[data-auth-area]` slot auth.js fills in),
  footer, and the two shared `<script>` includes.
- `app/templates/index.html` — the public landing page.
- `app/static/css/base.css` — design tokens (colors, spacing, type
  scale, status-badge colors) as CSS custom properties, plus shared
  layout/button/card/form/badge styles every later page reuses.
- `app/static/js/api.js` — the `Api` client (`Api.get/post/put/delete`)
  and `Auth` helper (token storage in `localStorage`, session
  clearing on 401). Every later phase's page script is built on top
  of this — it's the one place that knows about the JSON envelope
  (`{success, data}` / `{success, message, error}`) and attaches the
  JWT to outgoing requests.
- `app/static/js/auth.js` — fills in the navbar's login/register vs.
  user-name/logout state on every page load. The Login/Register links
  are placeholders (`href="#"` with a `data-nav` attribute and an
  alert) until Phase 2 builds the real pages.

**How it's wired in:** `app/__init__.py`'s `_register_blueprints()`
now also registers `frontend_bp` (no `url_prefix`, so its routes sit
at the site root, alongside — not inside — `/api/*`).

**Try it:** run the app as usual (`python run.py` or `flask run`)
and visit `/` in a browser. Nothing calls the API yet — Phase 2 does.

## Coming up

- **Phase 2** — Register/login/logout pages, wired to `Api` + `Auth`.
- **Phase 3** — Public listings feed + detail page.
- **Phase 4** — Provider listing management (create/edit/cancel).
- **Phase 5** — Recipient request flow.
- **Phase 6** — Provider incoming-requests dashboard.
- **Phase 7** — Pickup scheduling/confirm/complete/fail/cancel.
- **Phase 8** — Distribution history.
- **Phase 9** — Notifications.
- **Phase 10** — Provider/recipient profile forms + admin verification.
- **Phase 11** — Admin dashboard (users, audit log, reports).
- **Phase 12** — Responsive/accessibility/error-state polish pass.
