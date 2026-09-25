/**
 * FoodRescue Network — API client (Phase 1)
 *
 * A thin wrapper around fetch() that every later frontend phase's
 * page script reuses, so token handling, JSON parsing, and error
 * shape live in exactly one place instead of being copy-pasted into
 * every page.
 *
 * The backend's JSON envelope (see app/utils/responses.py) is always:
 *   { "success": true,  "data": ... }
 *   { "success": false, "message": "...", "error": "SOME_CODE" }
 *
 * Usage from a page script:
 *   const { data } = await Api.get('/api/listings?category=bakery');
 *   await Api.post('/api/auth/login', { email, password });
 *
 * On a non-2xx response, Api.* throws an ApiError with .status,
 * .code (the "error" field) and .message (the "message" field) so
 * callers can branch on error codes exactly like the API docs do.
 */

const TOKEN_STORAGE_KEY = 'frn_token';
const USER_STORAGE_KEY = 'frn_user';

class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

const Auth = {
  getToken() {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  },
  getUser() {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  },
  isLoggedIn() {
    return !!this.getToken();
  },
  setSession(token, user) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  },
  clearSession() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(USER_STORAGE_KEY);
  },
};

async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const token = Auth.getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (networkError) {
    // fetch() itself throws on network failure (offline, CORS, etc.)
    // — not on 4xx/5xx, which is a normal resolved response.
    throw new ApiError(
      'Could not reach the server. Check your connection and try again.',
      0,
      'NETWORK_ERROR'
    );
  }

  // 204 No Content has no body to parse.
  const payload = response.status === 204 ? {} : await response.json().catch(() => ({}));

  if (!response.ok) {
    // A 401 almost always means the token is missing/expired/revoked,
    // or the account was deactivated — either way the session is no
    // longer valid, so clear it. We deliberately do NOT redirect from
    // here: that's a page-level decision (some pages, like the public
    // listings feed, may want to show a "please log in" message
    // inline rather than yanking the user away).
    if (response.status === 401) {
      Auth.clearSession();
    }
    throw new ApiError(
      payload.message || 'Something went wrong.',
      response.status,
      payload.error || 'UNKNOWN_ERROR'
    );
  }

  return payload; // { success: true, data: ... }
}

const Api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  put: (path, body) => request('PUT', path, body),
  delete: (path) => request('DELETE', path),
};
