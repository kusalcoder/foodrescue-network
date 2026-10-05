"""
TokenBlocklist model — `token_blocklist` table.

JWTs are stateless by design — the server doesn't normally "remember"
which tokens it has issued, so there's nothing to delete on logout.
To still support a real logout (spec section 4 — "Logout/token
invalidation where applicable"), we record the unique ID (`jti`) of
any token that has been explicitly logged out. The `token_required`
decorator (app/auth/decorators.py) checks this table on every request
and rejects any token whose `jti` appears here, even if it hasn't
expired yet.

This table is expected to be small and short-lived in practice
(entries become irrelevant once the token would have expired anyway),
but we don't auto-delete rows here — an academic project doesn't need
a cleanup cron job, and keeping the row is harmless.
"""

from app.extensions import db
from app.models.base import utcnow


class TokenBlocklist(db.Model):
    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    revoked_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<TokenBlocklist jti={self.jti}>"
