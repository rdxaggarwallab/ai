import os
from datetime import timedelta

import click
from flask import Flask, jsonify
from sqlalchemy.exc import DataError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .extensions import db, jwt, limiter, migrate

DEV_SECRET = "dev-only-insecure-key-change-me-in-production-0000"


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    production = os.environ.get("LMS_ENV") == "production"
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", "postgresql://lms:lms@localhost:5432/lms"
        ),
        JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY", DEV_SECRET),
        JWT_TOKEN_LOCATION=["cookies"],
        JWT_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true" if production else "false") == "true",
        JWT_COOKIE_SAMESITE="Lax",
        JWT_COOKIE_CSRF_PROTECT=True,
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=8),
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR", os.path.abspath("uploads")),
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,  # 20 MB upload limit
        RATELIMIT_ENABLED=True,
        RATELIMIT_STORAGE_URI=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
        AUTOGRADER=os.environ.get("AUTOGRADER", "docker"),  # docker | local-unsafe | off
        GRADER_IMAGE=os.environ.get("GRADER_IMAGE", "lms-grader:latest"),
        GRADER_TIMEOUT=int(os.environ.get("GRADER_TIMEOUT", "30")),
        GRADE_INLINE=False,  # tests only: grade during the request instead of in the worker
    )
    if config:
        app.config.update(config)

    if production:
        key = app.config["JWT_SECRET_KEY"]
        if key == DEV_SECRET or len(key) < 32:
            raise RuntimeError(
                "LMS_ENV=production needs JWT_SECRET_KEY set to a random string of 32+ characters"
            )
        if app.config["AUTOGRADER"] == "local-unsafe":
            raise RuntimeError("AUTOGRADER=local-unsafe is not allowed in production")

    # The app always sits behind one proxy (Vite in development, the web server in Docker),
    # so take the client's IP from X-Forwarded-For. Without this every user looks like the
    # proxy and they all share one login rate limit. Set TRUSTED_PROXIES=0 if Flask is
    # reachable directly, or 2 behind an extra load balancer.
    hops = int(os.environ.get("TRUSTED_PROXIES", "1"))
    if hops:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)

    from . import models  # noqa: F401  (register models for migrations)
    from .admin import bp as admin_bp
    from .assignments import bp as assignments_bp
    from .auth import bp as auth_bp
    from .courses import bp as courses_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(courses_bp, url_prefix="/api/courses")
    app.register_blueprint(assignments_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify(error=e.description), e.code

    @app.errorhandler(429)
    def too_many(e):
        return jsonify(error="Too many attempts. Wait a minute and try again."), 429

    @app.errorhandler(413)
    def too_large(e):
        return jsonify(error="File is too large (max 20 MB)."), 413

    @app.errorhandler(DataError)
    def bad_data(e):  # e.g. a number too big for the database column
        db.session.rollback()
        return jsonify(error="Invalid value (out of range or too long)."), 400

    from .grader import register_cli
    register_cli(app)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.argument("name")
    @click.password_option()
    def create_admin(email, name, password):
        """Create an admin account, or promote an existing user to admin."""
        from .models import User
        from .security import hash_password

        email = email.strip().lower()
        user = db.session.query(User).filter_by(email=email).first()
        if user:
            user.role = "admin"
            click.echo(f"Promoted {email} to admin")
        else:
            if len(password) < 8:
                raise click.BadParameter("Password must be at least 8 characters")
            db.session.add(User(email=email, name=name, role="admin",
                                password_hash=hash_password(password)))
            click.echo(f"Created admin {email}")
        db.session.commit()

    return app
