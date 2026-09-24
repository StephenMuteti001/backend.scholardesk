import os
import re

from flask import Flask
from flask_cors import CORS

from config import DevelopmentConfig, ProductionConfig
from extensions import bcrypt, db, jwt, ma, migrate

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def create_app(config_name=None):
    app = Flask(
        __name__,
        instance_relative_config=False,
        template_folder=os.path.join(BASE_DIR, "templates"),
    )

    env = os.getenv("FLASK_ENV", "development")

    if env == "production":
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    # initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    ma.init_app(app)

    # -----------------------------
    # JWT Debug Callbacks
    # -----------------------------

    from utils.response_formatter import error_response

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return error_response(
            "INVALID_TOKEN",
            "The authentication token is invalid.",
            status=401,
        )

    @jwt.unauthorized_loader
    def missing_token(reason):
        return error_response(
            "UNAUTHORIZED",
            "Authentication is required.",
            status=401,
        )

    @jwt.revoked_token_loader
    def revoked_token(jwt_header, jwt_payload):
        return error_response(
            "TOKEN_REVOKED",
            "The authentication token has been revoked.",
            status=401,
        )

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_payload):
        return error_response(
            "TOKEN_EXPIRED",
            "The authentication token has expired.",
            status=401,
        )

    @jwt.csrf_error_loader
    def csrf_error(reason):
        return error_response(
            "CSRF_ERROR",
            "CSRF validation failed.",
            status=401,
        )

    # parse env list for dev (localhost) and prod
    origins = [o.strip() for o in app.config["CORS_ORIGINS"].split(",")]

    origins.extend(
        [
            "https://scholardesk.pro",
        ]
    )

    # Subdomains (regex)
    origins.append(re.compile(r"https://.*\.scholardesk\.pro"))

    CORS(
        app,
        resources={r"/api/*": {"origins": origins}},
        supports_credentials=True,
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-CSRF-TOKEN",
        ],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    bcrypt.init_app(app)

    if app.config.get("DEBUG"):
        app.logger.debug(
            "JWT cookie config: csrf_protect=%s secure=%s samesite=%s",
            app.config.get("JWT_COOKIE_CSRF_PROTECT"),
            app.config.get("JWT_COOKIE_SECURE"),
            app.config.get("JWT_COOKIE_SAMESITE"),
        )

    # -----------------------------
    # Register blueprints
    #
    # Every module that exposes an admin-facing surface follows the
    # same "<role>_bp" naming so registration reads the same way for
    # each of the three user types.
    # -----------------------------

    from analytics.routes import (
        admin_bp as analytics_admin_bp,
        customer_bp as analytics_customer_bp,
        expert_bp as analytics_expert_bp,
    )
    from customer_orders.routes import customer_bp as customer_orders_bp
    from customers.routes import customers_bp
    from dashboard.routes import (
        admin_bp as dashboard_admin_bp,
        customer_bp as dashboard_customer_bp,
        expert_bp as dashboard_expert_bp,
    )
    from exam_materials.routes import (
        customer_bp as exam_materials_customer_bp,
        exam_materials_bp,
    )
    from expert_applications.routes import (
        admin_bp as expert_applications_admin_bp,
        applications_alias_bp,
        customer_bp as expert_applications_customer_bp,
    )
    from experts.routes import bp as experts_bp, self_bp as experts_self_bp
    from integrity_reports.routes import customer_bp as integrity_reports_bp
    from orders.routes import (
        expert_bp as orders_expert_bp,
        expert_portal_bp as orders_expert_portal_bp,
        orders_bp,
    )
    from payments.routes import payments_bp, expert_bp as payments_expert_bp
    from platform_settings.routes import (
        admin_bp as platform_settings_admin_bp,
        public_bp as platform_settings_public_bp,
    )
    from requests.routes import requests_bp
    from submissions.routes import (
        admin_bp as submissions_admin_bp,
        expert_bp as submissions_expert_bp,
    )
    from support_chat.routes import customer_bp as support_chat_bp
    from users.routes import users_bp
    from assessdesk.routes import (
        admin_bp as assessdesk_admin_bp,
        public_bp as assessdesk_public_bp,
    )
    from assessdesk.cli import assessdesk_cli

    # Auth / account management
    app.register_blueprint(users_bp)

    # Admin management surfaces
    app.register_blueprint(customers_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(orders_expert_bp)
    app.register_blueprint(orders_expert_portal_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(payments_expert_bp)
    app.register_blueprint(requests_bp)
    app.register_blueprint(exam_materials_bp)
    app.register_blueprint(experts_bp)
    app.register_blueprint(experts_self_bp)

    # Expert applications (admin review + applicant self-service)
    app.register_blueprint(expert_applications_admin_bp)
    app.register_blueprint(expert_applications_customer_bp)
    app.register_blueprint(applications_alias_bp)

    # Dashboard (admin / customer / expert)
    app.register_blueprint(dashboard_admin_bp)
    app.register_blueprint(dashboard_customer_bp)
    app.register_blueprint(dashboard_expert_bp)

    # Analytics (admin / customer / expert)
    app.register_blueprint(analytics_admin_bp)
    app.register_blueprint(analytics_customer_bp)
    app.register_blueprint(analytics_expert_bp)

    # Customer portal (academic-hub-refined-main frontend) - unified
    # orders/quotes/payments, exam-material purchases, support chat,
    # and integrity scanning. See docs/API.md in that frontend repo.
    app.register_blueprint(customer_orders_bp)
    app.register_blueprint(exam_materials_customer_bp)
    app.register_blueprint(support_chat_bp)
    app.register_blueprint(integrity_reports_bp)

    # Submissions: expert delivers work against an order; admin
    # releases it to the client once it clears integrity review.
    # Shares the /api/v1/orders and /api/v1/admin/orders prefixes
    # with customer_orders_bp / orders_bp respectively - see
    # submissions/routes.py for why that's safe.
    app.register_blueprint(submissions_expert_bp)
    app.register_blueprint(submissions_admin_bp)

    # Platform-wide settings (currently: is expert/writer hiring open).
    # Public GET is read by every ScholarDesk frontend with no auth.
    app.register_blueprint(platform_settings_public_bp)
    app.register_blueprint(platform_settings_admin_bp)

    # AssessDesk (desktop answer-credits product). Public surface is
    # used by assessdesk.scholardesk.pro (cookies) and the desktop app
    # (bearer + device refresh token); admin surface by the admin portal.
    app.register_blueprint(assessdesk_public_bp)
    app.register_blueprint(assessdesk_admin_bp)
    app.cli.add_command(assessdesk_cli)

    # -----------------------------
    # Error handlers to match required error format
    # -----------------------------

    from utils.exceptions import ServiceError
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(ServiceError)
    def handle_service_error(error):
        return error_response(
            code=error.code,
            message=error.message,
            details=error.details,
            status=error.status_code,
        )

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        return error_response(
            code=error.name.upper().replace(" ", "_"),
            message=error.description,
            status=error.code,
        )

    @app.errorhandler(500)
    def server_error(e):
        return error_response(
            "SERVER_ERROR", "Internal server error", status=500
        )

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error):
        app.logger.exception(error)

        return error_response(
            "SERVER_ERROR",
            "An unexpected error occurred.",
            status=500,
        )

    return app
