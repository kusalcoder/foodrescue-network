"""
Frontend Blueprint

Serves server-rendered Jinja2 pages (as opposed to the JSON API
under /api/*). These routes just render templates; all real data
comes from the browser calling the existing JSON API with
JavaScript (see app/static/js/api.js), the same way any external
client would.

Phase 1 wired up the base layout and the public landing page.
Phase 2 added the register/login pages.
Phase 3 added the listings feed (/listings) and detail
(/listings/<id>) pages.
Phase 4 added provider-facing listing management (/listings/mine,
/listings/new, /listings/<id>/edit).
Phase 5 added the recipient-facing request flow (/requests/mine,
plus the request form embedded on /listings/<id>).
Phase 6 added the provider-facing request flow (/requests/incoming,
/listings/<id>/requests, plus accept/reject).
Phase 7 added the pickup lifecycle (/pickups, plus scheduling a
pickup from an accepted request).
Phase 8 added distribution history (/distributions).
Phase 9 added notifications (/notifications, plus the navbar bell).
Phase 10 added:
    /profile                    — create/view/edit MY OWN provider
                                   or recipient profile (same page,
                                   different fields fetched/sent
                                   depending on role — see
                                   app/static/js/profile.js)
    /admin/verify-recipient      — the one admin action that exists
                                   so far (POST /api/recipients/<id>/
                                   verify)

Phase 11 adds the fuller admin dashboard:
    /admin/users        — list platform users, filter by role/status,
                           and (if the backend supports it) activate
                           or deactivate an account
    /admin/audit-log     — browse the audit trail of admin/system
                           actions
    /admin/reports       — platform-wide summary stats

See PHASE11_SETUP.md for what's assumed about the backend contract
for these three (paths, field names, pagination) since it hadn't
been pinned down yet when this phase was built, and what to check
first if something doesn't line up with your actual API.
"""

from flask import Blueprint, current_app, render_template, send_from_directory

frontend_bp = Blueprint("frontend", __name__)


@frontend_bp.route("/")
def index():
    return render_template("index.html")


@frontend_bp.route("/favicon.ico")
def favicon():
    return send_from_directory(
        current_app.static_folder + "/img",
        "favicon.svg",
        mimetype="image/svg+xml",
    )


@frontend_bp.route("/register")
def register_page():
    return render_template("auth/register.html")


@frontend_bp.route("/login")
def login_page():
    return render_template("auth/login.html")


@frontend_bp.route("/listings")
def listings_page():
    return render_template("listings/index.html")


@frontend_bp.route("/listings/mine")
def my_listings_page():
    return render_template("listings/mine.html")


@frontend_bp.route("/listings/new")
def new_listing_page():
    return render_template("listings/new.html")


@frontend_bp.route("/listings/<int:listing_id>/edit")
def edit_listing_page(listing_id):
    return render_template("listings/edit.html", listing_id=listing_id)


@frontend_bp.route("/listings/<int:listing_id>/requests")
def listing_requests_page(listing_id):
    return render_template("requests/listing.html", listing_id=listing_id)


@frontend_bp.route("/listings/<int:listing_id>")
def listing_detail_page(listing_id):
    return render_template("listings/detail.html", listing_id=listing_id)


@frontend_bp.route("/requests/mine")
def my_requests_page():
    return render_template("requests/mine.html")


@frontend_bp.route("/requests/incoming")
def incoming_requests_page():
    return render_template("requests/incoming.html")


@frontend_bp.route("/pickups")
def my_pickups_page():
    return render_template("pickups/mine.html")


@frontend_bp.route("/distributions")
def my_distributions_page():
    return render_template("distributions/mine.html")


@frontend_bp.route("/notifications")
def notifications_page():
    return render_template("notifications/mine.html")


@frontend_bp.route("/profile")
def my_profile_page():
    return render_template("profile/mine.html")


@frontend_bp.route("/admin/verify-recipient")
def admin_verify_recipient_page():
    return render_template("admin/verify_recipient.html")


@frontend_bp.route("/admin/users")
def admin_users_page():
    return render_template("admin/users.html")


@frontend_bp.route("/admin/audit-log")
def admin_audit_log_page():
    return render_template("admin/audit_log.html")


@frontend_bp.route("/admin/reports")
def admin_reports_page():
    return render_template("admin/reports.html")
