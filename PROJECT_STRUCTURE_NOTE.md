# A note on this folder

This is your **one, single, consolidated project folder** — built by
merging everything from your 13 phase zips plus the Phase 1 frontend
work, so you don't have to do any manual copying yourself.

**What went into it, in order:**
1. `foodrescue_network_phase11.zip` — used as the base. Phases 1–11
   were each a full snapshot of the whole project, and phase 11 was
   the most complete/up to date one, so everything from phases 1–10
   is already included inside it.
2. `foodrescue_network_phase12.zip` — added the `tests/` folder,
   `pytest.ini`, and `requirements-test.txt` on top.
3. `foodrescue_network_phase13.zip` — added the `.github/workflows/`
   CI setup on top of that.
4. The Phase 1 frontend work from our chat — `app/routes/frontend.py`,
   `app/templates/`, `app/static/`, and the matching two-line edit in
   `app/__init__.py` that registers the new frontend blueprint.

**What to do with it:** replace your local `foodrescue_network`
folder with this one, entirely. You can now safely delete every
`foodrescue_network_phaseN` folder, the `frontend/` folder, and the
old `frontend_phase1` folder from your `project` directory — none of
that is needed anymore. This folder is the only copy of the project
going forward.

From here on, every new phase (backend or frontend) is a change made
*inside* this same folder — never a new sibling folder.
