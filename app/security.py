"""Authentication and browser security protections for Blue Ribbon BSC."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from flask import abort, current_app, request, session
from sqlalchemy import or_
from .extensions import db
from .models import LoginAttempt


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf_token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(400, description="Security token missing or expired. Refresh the page and try again.")


def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Existing Bootstrap/Plotly inline scripts need a future nonce-based CSP migration.
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'"
    if request.is_secure and current_app.config.get("SESSION_COOKIE_SECURE"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.path.startswith(("/login", "/setup")):
        response.headers["Cache-Control"] = "no-store"
    return response


def _ip_key():
    # Do not trust user-supplied X-Forwarded-For; ProxyFix can be configured only for known proxies.
    return (request.remote_addr or "unknown")[:80]


def _identity_key(identity):
    normalized = (identity or "").strip().casefold()[:180]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def login_throttled(identity, *, setup=False):
    after = datetime.utcnow() - timedelta(minutes=15)
    ip = _ip_key()
    identity_hash = _identity_key(identity)
    action = "setup" if setup else "login"
    attempts = LoginAttempt.query.filter(
        LoginAttempt.created_at >= after,
        LoginAttempt.action == action,
        or_(LoginAttempt.ip_address == ip, LoginAttempt.identity_hash == identity_hash),
    ).all()
    return (sum(row.ip_address == ip for row in attempts) >= 20 or
            sum(row.identity_hash == identity_hash for row in attempts) >= 8)


def record_failed_login(identity, *, setup=False):
    # Keep the new audit table small while preserving the active throttle window.
    LoginAttempt.query.filter(
        LoginAttempt.created_at < datetime.utcnow() - timedelta(days=1)
    ).delete(synchronize_session=False)
    db.session.add(LoginAttempt(
        ip_address=_ip_key(), identity_hash=_identity_key(identity),
        action="setup" if setup else "login"))
    db.session.commit()


def clear_successful_login(identity):
    # Clear the successful identity's failed attempts; IP attacks remain counted.
    LoginAttempt.query.filter_by(identity_hash=_identity_key(identity), action="login").delete()
    db.session.commit()
