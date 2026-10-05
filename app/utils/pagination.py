"""
Shared pagination helper (spec section 21).

Every list endpoint in the project should return the same pagination
metadata shape:

    {"page": 1, "limit": 10, "total": 35, "total_pages": 4}

`paginate_query` takes a SQLAlchemy query (not yet executed) plus raw
page/limit query-string values, clamps them to sane bounds using the
app's configured defaults, and returns both the page of results and
the metadata dict — so a list endpoint is never able to accidentally
return every row in the table (spec section 21 — "Do not retrieve
unlimited listings.").
"""

import math

from flask import current_app


def get_pagination_params(args):
    """
    Parse and clamp `page`/`limit` from a Flask `request.args`-like
    mapping. Invalid or missing values fall back to the configured
    defaults rather than raising an error — a malformed `page=abc`
    shouldn't break browsing, it should just behave like `page=1`.
    """
    default_limit = current_app.config["DEFAULT_PAGE_SIZE"]
    max_limit = current_app.config["MAX_PAGE_SIZE"]

    try:
        page = int(args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    page = max(page, 1)

    try:
        limit = int(args.get("limit", default_limit))
    except (TypeError, ValueError):
        limit = default_limit
    limit = min(max(limit, 1), max_limit)

    return page, limit


def paginate_query(query, page: int, limit: int):
    """
    Apply LIMIT/OFFSET to a SQLAlchemy query and return
    (items, pagination_metadata).
    """
    total = query.count()
    total_pages = math.ceil(total / limit) if total else 0

    items = query.offset((page - 1) * limit).limit(limit).all()

    metadata = {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
    }
    return items, metadata
