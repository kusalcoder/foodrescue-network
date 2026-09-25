"""
Consistent JSON response helpers (spec section 29).

Using these everywhere guarantees every endpoint in the project
returns the same envelope shape, whether it succeeds or fails:

    {"success": true,  "message": "...", "data": {...}}
    {"success": false, "message": "...", "error": "SOME_CODE"}
"""

from flask import jsonify


def success_response(message: str, data=None, status_code: int = 200):
    payload = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status_code


def error_response(message: str, error_code: str, status_code: int = 400):
    return (
        jsonify(success=False, message=message, error=error_code),
        status_code,
    )
