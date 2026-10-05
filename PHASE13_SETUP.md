# Phase 13 Setup — Continuous Integration (CI)

This adds a GitHub Actions workflow that automatically runs your
Phase 12 `pytest` suite every time you push code or open a pull
request — against a real, disposable PostgreSQL container, not a
mock — so a regression gets caught within a couple of minutes instead
of whenever someone next happens to run `pytest` locally.

## 1. Copy this file into your project

Unzip this package's contents directly into your project's **root**
folder — the one that contains `.git` (this is one level ABOVE
`foodrescue_network/`, at
`...\foodrescue_network_phase11\`), so you end up with:

```
foodrescue_network_phase11/          <- your git repo root
├── .github/
│   └── workflows/
│       └── tests.yml                <- NEW
├── foodrescue_network/
│   ├── app/
│   ├── tests/
│   ├── requirements.txt
│   ├── requirements-test.txt
│   └── ...
└── CI_BADGE_SNIPPET.md              <- NEW (optional, for your README)
```

**If your repo root is actually the `foodrescue_network/` folder
itself** (i.e. that's where `.git` lives, not its parent), then put
`.github/` directly inside `foodrescue_network/` instead, and remove
the `foodrescue_network/` prefixes from the two `run:` steps in
`tests.yml` (the ones that do `pip install -r requirements.txt` etc.)
so they point at the right relative paths. Run this to check which
case you're in:

```
git rev-parse --show-toplevel
```

Whatever path that prints is your repo root — that's where `.github/`
belongs.

## 2. Adjust paths if requirements files aren't at the repo root

The workflow assumes `requirements.txt` and `requirements-test.txt`
sit in the same folder pytest runs from. If your repo root is one
level above `foodrescue_network/` (the common case per the setup
notes above), add a `working-directory` and a `defaults` block, or
simplest: add this line right after the `jobs: test:` line in
`tests.yml`:

```yaml
    defaults:
      run:
        working-directory: foodrescue_network
```

This tells every `run:` step in the job to execute from inside
`foodrescue_network/` instead of the repo root — matching where your
`requirements.txt`, `requirements-test.txt`, and `tests/` folder
actually live.

## 3. Push to GitHub

If this project isn't already a GitHub repo, create one first (via
github.com's "New repository" button, without a README so it stays
empty), then:

```
git init
git add .
git commit -m "Add Phase 13: CI workflow"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

If it's already a repo, just:
```
git add .
git commit -m "Add Phase 13: CI workflow"
git push
```

## 4. Watch it run

On GitHub, open your repository, click the **Actions** tab, and you
should see a run in progress (or already finished) called
"FoodRescue Network — Tests". Click it to see the same `pytest`
output you've been seeing locally — including the coverage summary.

## 5. Add the status badge (optional but recommended)

See `CI_BADGE_SNIPPET.md` — paste the one line it shows near the top
of your `README.md`, filling in your actual GitHub username and repo
name.

## What this does NOT do

- It does not deploy your app anywhere — this is testing only, not a
  deployment pipeline. (A natural Phase 14 would add a deploy step
  here, e.g. to Render or Railway, gated on the tests passing.)
- It does not run against your real development or production
  database — the workflow spins up a brand-new, throwaway Postgres
  container every single run and throws it away afterward, so it can
  never touch real data, matching the same safety principle
  `tests/conftest.py` already enforces locally.
- It intentionally does NOT install `pytest-timeout` as a required
  step failure — if a test hangs in CI the same way we saw locally
  during Phase 12 debugging, GitHub Actions will eventually time out
  the whole job (default 6 hours, but you can add a `timeout-minutes:
  10` line under `jobs: test:` to fail fast instead, which is
  recommended given what we ran into).

## Troubleshooting

**"requirements.txt not found"** — your repo root doesn't match what
the workflow assumes. See step 2 above.

**Tests fail in CI but pass locally** — almost always an environment
difference. Compare the `env:` block in `tests.yml` against your
local `.env`; a missing `SECRET_KEY` or wrong `TEST_DATABASE_URL`
format is the usual cause.

**"database does not exist"** — the `POSTGRES_DB` value in the
`services.postgres.env` block of `tests.yml` must exactly match the
database name in `TEST_DATABASE_URL` below it (`foodrescue_test_db`
in both, by default).
