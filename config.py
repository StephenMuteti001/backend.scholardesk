import os
from datetime import timedelta
from dotenv import load_dotenv
import json

load_dotenv()

class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

    JWT_TOKEN_LOCATION = json.loads(
        os.getenv("JWT_TOKEN_LOCATION", '["cookies", "headers"]')
    )

    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    JWT_COOKIE_SECURE = os.getenv("JWT_COOKIE_SECURE", "False") == "True"

    JWT_COOKIE_HTTPONLY = (
        os.getenv("JWT_COOKIE_HTTPONLY", "True") == "True"
    )

    JWT_COOKIE_SAMESITE = os.getenv("JWT_COOKIE_SAMESITE", "Lax")

    JWT_ACCESS_COOKIE_PATH = os.getenv("JWT_ACCESS_COOKIE_PATH", "/")

    JWT_REFRESH_COOKIE_PATH = os.getenv("JWT_REFRESH_COOKIE_PATH", "/")

    JWT_COOKIE_DOMAIN = os.getenv("JWT_COOKIE_DOMAIN")

    JWT_COOKIE_CSRF_PROTECT = True

    JWT_ACCESS_COOKIE_NAME = "access_token_cookie"
    JWT_REFRESH_COOKIE_NAME = "refresh_token_cookie"

    JWT_ACCESS_CSRF_COOKIE_NAME = "csrf_access_token"
    JWT_REFRESH_CSRF_COOKIE_NAME = "csrf_refresh_token"

    JWT_ACCESS_CSRF_HEADER_NAME = "X-CSRF-TOKEN"
    JWT_REFRESH_CSRF_HEADER_NAME = "X-CSRF-TOKEN"

    SQLALCHEMY_DATABASE_URI = (
        f"{os.getenv('DATABASE_URL')}"
        f"?sslmode=verify-full"
        f"&sslrootcert={os.getenv('DB_SSLROOTCERT')}"
    )

    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8080"
    )

    RATELIMIT_HEADERS_ENABLED = True

    FREE_ORDER_LIMIT = int(os.getenv("FREE_ORDER_LIMIT", 2))

    ACCESS_EXPIRES = int(os.getenv("ACCESS_EXPIRES", 86400))
    REFRESH_EXPIRES = int(os.getenv("REFRESH_EXPIRES", 86400))

    # Never hardcode gateway keys. Set these in the environment.
    PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
    PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")

    ASSESSDESK_FRONTEND_URL = os.getenv(
        "ASSESSDESK_FRONTEND_URL", "https://assessdesk.scholardesk.pro"
    )

    EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME")
    EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS")
    # ScholarDesk is 4 separate deployed SPAs (auth, customer, expert,
    # admin), not one unified frontend with role-prefixed paths - each
    # needs its own base URL for email deep-links. FRONTEND_URL is the
    # auth/marketing portal (email verification, login OTP, register).
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://scholardesk.pro")
    AUTH_FRONTEND_URL = os.getenv(
        "AUTH_FRONTEND_URL", "https://auth.scholardesk.pro"
    )
    CUSTOMER_FRONTEND_URL = os.getenv(
        "CUSTOMER_FRONTEND_URL", "https://customer.scholardesk.pro"
    )
    EXPERT_FRONTEND_URL = os.getenv(
        "EXPERT_FRONTEND_URL", "https://expert.scholardesk.pro"
    )
    ADMIN_FRONTEND_URL = os.getenv(
        "ADMIN_FRONTEND_URL", "https://admin.scholardesk.pro"
    )

    # Shared inbox for internal, support-team-facing alerts (new
    # counter-offer, submission awaiting review, refund requested,
    # etc.) - see users/mailer_service.py::send_internal_alert(). A
    # shared inbox rather than emailing every admin individually.
    SUPPORT_TEAM_EMAIL = os.getenv(
        "SUPPORT_TEAM_EMAIL", "support@scholardesk.pro"
    )

    ZOHO_SMTP_HOST = os.getenv("ZOHO_SMTP_HOST", "smtppro.zoho.com")
    ZOHO_SMTP_PORT = int(os.getenv("ZOHO_SMTP_PORT", 465))
    ZOHO_APP_PASSWORD = os.getenv("ZOHO_APP_PASSWORD")

    EMAIL_VERIFY_EXPIRES = int(os.getenv("EMAIL_VERIFY_EXPIRES", 3600))

    # Local disk destination for user uploads (expert application
    # essays/CVs/work samples, etc). See utils/uploads.py.
    UPLOAD_FOLDER = os.getenv(
        "UPLOAD_FOLDER",
        os.path.join(os.path.dirname(__file__), "uploads"),
    )

    MAX_CONTENT_LENGTH = int(
        os.getenv("MAX_CONTENT_LENGTH", 25 * 1024 * 1024)
    )

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
