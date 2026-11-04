import re

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import create_access_token, set_access_cookies, unset_jwt_cookies

from .extensions import db
from .models import User
from .security import check_password, hash_password, login_required

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Only students and teachers may self-register; admins/TAs are assigned by an admin.
SELF_REGISTER_ROLES = ("student", "teacher")


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    role = data.get("role", "student")

    if not EMAIL_RE.match(email):
        abort(400, "Invalid email")
    if not name:
        abort(400, "Name is required")
    if len(password) < 8:
        abort(400, "Password must be at least 8 characters")
    if role not in SELF_REGISTER_ROLES:
        abort(400, "Invalid role")
    if db.session.query(User).filter_by(email=email).first():
        abort(409, "Email already registered")

    user = User(email=email, name=name, role=role, password_hash=hash_password(password))
    db.session.add(user)
    db.session.commit()
    return _login_response(user, 201)


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    user = db.session.query(User).filter_by(email=email).first()
    if not user or not check_password(user.password_hash, data.get("password") or ""):
        abort(401, "Wrong email or password")
    return _login_response(user, 200)


@bp.post("/logout")
def logout():
    resp = jsonify(ok=True)
    unset_jwt_cookies(resp)
    return resp


@bp.get("/me")
@login_required()
def me(user):
    return user.to_dict()


def _login_response(user, status):
    resp = jsonify(user.to_dict())
    set_access_cookies(resp, create_access_token(identity=str(user.id)))
    return resp, status
