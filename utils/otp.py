import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

from itsdangerous import URLSafeTimedSerializer, BadData
from flask import current_app

def generate_otp():
    return f"{secrets.randbelow(1000000):06d}"

def hash_otp(otp: str):
    return generate_password_hash(otp)

def verify_otp(otp: str, otp_hash: str):
    return check_password_hash(otp_hash, otp)

def otp_expiry(minutes=5):
    return datetime.utcnow() + timedelta(minutes=minutes)


# ---------------------------------------------------------------------------
# Login OTP session token
# ---------------------------------------------------------------------------
#
# The frontend's login flow is: POST /auth/login -> { otp_required,
# otp_session_id } -> POST /auth/login/verify-otp { otp, otp_session_id }.
# It never resends the email on the verify step, so the session id has
# to carry the user identity itself. We use a signed, short-lived token
# (mirrors utils/email_tokens.py) instead of a server-side session
# table, since the OTP hash/expiry/attempts are already persisted on
# the User row - the token just needs to point back at that row.

def generate_otp_session_token(user_id: int) -> str:
    s = URLSafeTimedSerializer(current_app.config["JWT_SECRET_KEY"])
    return s.dumps({"user_id": user_id}, salt="login-otp-session")


def decode_otp_session_token(token: str, max_age_minutes: int) -> int:
    s = URLSafeTimedSerializer(current_app.config["JWT_SECRET_KEY"])

    try:
        data = s.loads(
            token,
            salt="login-otp-session",
            max_age=max_age_minutes * 60,
        )
    except BadData:
        return None

    return data.get("user_id")
