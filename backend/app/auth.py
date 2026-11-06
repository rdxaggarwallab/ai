import re

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import (create_access_token, decode_token, set_access_cookies,
                                unset_jwt_cookies)

from .extensions import db, limiter
from .models import User
from .security import DUMMY_HASH, check_password, hash_password, login_required
from .validate import body, get_str

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _login_key():
    """Count login attempts per client IP *and* email, so one person's typos (or an
    attacker) can't lock out a whole class that shares the same proxy or school network."""
    from flask_limiter.util import get_remote_address

    data = request.get_json(silent=True)
    email = data.get("email") if isinstance(data, dict) else None
    return f"{get_remote_address()}|{str(email).strip().lower()[:255]}"


@bp.post("/register")
@limiter.limit("30 per minute")  # per IP: a class registering at once fits
def register():
    data = body()
    email = get_str(data, "email", required=True, max_len=255).strip().lower()
    name = get_str(data, "name", required=True, max_len=120).strip()
    password = get_str(data, "password", required=True, max_len=200)
    # Self-registration is for students only. Teachers, TAs and admins get their role
    # from an admin (Users page), so strangers can't create courses.
    if data.get("role", "student") != "student":
        abort(400, "You can only sign up as a student. Ask an admin for a teacher account.")
    if not EMAIL_RE.match(email):
        abort(400, "Invalid email")
    if len(password) < 8:
        abort(400, "Password must be at least 8 characters")
    if db.session.query(User).filter_by(email=email).first():
        abort(409, "Email already registered")

    user = User(email=email, name=name, role="student", password_hash=hash_password(password))
    db.session.add(user)
    db.session.commit()
    return _login_response(user, 201)


@bp.post("/login")
@limiter.limit("10 per minute", key_func=_login_key)
@limiter.limit("100 per minute")  # per IP, all emails together
def login():
    data = body()
    email = get_str(data, "email", max_len=255).strip().lower()
    password = get_str(data, "password", max_len=200)
    user = db.session.query(User).filter_by(email=email).first()
    # Always run the password hash, so response time doesn't reveal which emails exist.
    ok = check_password(user.password_hash if user else DUMMY_HASH, password)
    if not user or not ok:
        abort(401, "Wrong email or password")
    return _login_response(user, 200)


@bp.post("/logout")
def logout():
    """End the session everywhere: tokens issued before now stop working.

    No CSRF header is required: the cookie is SameSite=Lax, so other sites can't send it
    on a POST, and the worst a forged logout could do is log the user out.
    """
    token = request.cookies.get("access_token_cookie")
    if token:
        try:
            claims = decode_token(token)
            user = db.session.get(User, int(claims["sub"]))
            if user and claims.get("tv", 0) == user.token_version:
                user.token_version += 1
                db.session.commit()
        except Exception:  # expired or invalid token: nothing to revoke
            db.session.rollback()
    resp = jsonify(ok=True)
    unset_jwt_cookies(resp)
    return resp


@bp.get("/me")
@login_required()
def me(user):
    return user.to_dict()


def _login_response(user, status):
    resp = jsonify(user.to_dict())
    token = create_access_token(identity=str(user.id), additional_claims={"tv": user.token_version})
    set_access_cookies(resp, token)
    return resp, status
