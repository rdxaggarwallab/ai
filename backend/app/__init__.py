import os
from datetime import timedelta

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from .extensions import db, jwt, migrate


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", "postgresql://lms:lms@localhost:5432/lms"
        ),
        JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY", "dev-only-insecure-key-change-me-in-production-0000"),
        JWT_TOKEN_LOCATION=["cookies"],
        JWT_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false") == "true",
        JWT_COOKIE_SAMESITE="Lax",
        JWT_COOKIE_CSRF_PROTECT=True,
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=8),
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR", os.path.abspath("uploads")),
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,  # 20 MB upload limit
    )
    if config:
        app.config.update(config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    from . import models  # noqa: F401  (register models for migrations)
    from .auth import bp as auth_bp
    from .courses import bp as courses_bp
    from .assignments import bp as assignments_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(courses_bp, url_prefix="/api/courses")
    app.register_blueprint(assignments_bp, url_prefix="/api")

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify(error=e.description), e.code

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
