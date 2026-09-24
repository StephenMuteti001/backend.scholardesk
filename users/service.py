# users/service.py

from datetime import datetime, timedelta

from flask import current_app

from extensions import db
from utils.auth_utils import hash_password, check_password
from utils.email_tokens import (
    generate_email_verification_token,
    decode_email_verification_token,
)
from utils.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from utils.mailer import send_email
from utils.otp import (
    generate_otp,
    hash_otp,
    verify_otp,
    otp_expiry,
    generate_otp_session_token,
    decode_otp_session_token,
)
from utils.transaction import transaction

from users.constants import (
    DEFAULT_ACCOUNT_STATUS,
    MAX_LOGIN_OTP_ATTEMPTS,
    OTP_EXPIRY_MINUTES,
    USER_SEARCH_FIELDS,
    USER_SORT_FIELDS,
)
from users.schemas import (
    validate_email,
    validate_full_name,
    validate_name,
    validate_password,
    validate_role,
    validate_status,
    serialize_user,
)

from users.user import User

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
)


def get_user_by_id(user_id):
    user = db.session.get(User, user_id)

    if not user:
        raise NotFoundError("User not found.")

    return user


def get_user_by_email(email):
    email = validate_email(email)

    return (
        User.query
        .filter(db.func.lower(User.email) == email)
        .first()
    )


def register_user(
    full_name=None,
    email=None,
    password=None,
    country=None,
    role="customer",
    first_name=None,
    last_name=None,
):
    """
    Every frontend registration form sends a single `full_name`
    field. We accept that as the primary contract and split it into
    first_name/last_name for storage. Passing first_name/last_name
    directly is still supported (e.g. for admin-created accounts).
    """
    email = validate_email(email)
    validate_password(password)
    role = validate_role(role)

    if role in {"admin", "super_admin"}:
        raise ValidationError(
            "Administrative accounts cannot be created through public registration."
        )

    if first_name or last_name:
        first_name = validate_name(first_name, "First name")
        last_name = validate_name(last_name or "", "Last name")
    else:
        full_name = validate_full_name(full_name)
        parts = full_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

    existing = get_user_by_email(email)

    if existing:
        raise ConflictError(
            "An account with this email already exists."
        )

    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=hash_password(password),
        country=country.strip() if country else None,
        role=role,
        status="pending",
        account_status=DEFAULT_ACCOUNT_STATUS,
    )

    with transaction():
        db.session.add(user)
        db.session.flush()

    return user


def authenticate_password(email, password):
    email = validate_email(email)

    user = get_user_by_email(email)

    if not user:
        raise ValidationError("Invalid email or password.")

    if not check_password(password, user.password_hash):
        raise ValidationError("Invalid email or password.")

    if user.status == "banned":
        raise ConflictError("This account has been banned.")

    if user.status == "suspended":
        raise ConflictError("This account is currently suspended.")

    return user


def create_login_otp(user):
    """
    Generate and persist a login OTP for the user.

    Returns:
        str: plaintext OTP that should only be sent through
        the email delivery service.
    """

    otp = generate_otp()

    user.login_otp_hash = hash_otp(otp)
    user.login_otp_expires_at = otp_expiry(
        current_app.config.get(
            "OTP_EXPIRY_MINUTES",
            10,
        )
    )
    user.login_otp_attempts = 0

    db.session.commit()

    return otp


def request_login_otp(email):
    """
    Generate and send a login OTP for an existing user.

    This is the public service operation used by both:
        - initial login
        - OTP resend

    Returns (user, otp_session_id). otp_session_id is a signed,
    short-lived token identifying the pending login attempt; the
    frontend carries it back on the verify step instead of the
    email address.
    """

    email = validate_email(email)

    user = get_user_by_email(email)

    if not user:
        raise ValidationError(
            "Unable to authenticate this account."
        )

    if user.status == "banned":
        raise ConflictError(
            "This account has been banned."
        )

    if user.status == "suspended":
        raise ConflictError(
            "This account is currently suspended."
        )

    otp = create_login_otp(user)

    from users.mailer_service import send_login_otp

    send_login_otp(user, otp)

    otp_session_id = generate_otp_session_token(user.id)

    return user, otp_session_id


def verify_login_otp(otp_session_id, otp):
    if not otp or not otp.isdigit() or len(otp) != 6:
        raise ValidationError(
            "Invalid login code."
        )

    user_id = decode_otp_session_token(
        otp_session_id or "",
        max_age_minutes=OTP_EXPIRY_MINUTES,
    )

    if not user_id:
        raise ValidationError(
            "This login session has expired. Please log in again."
        )

    user = db.session.get(User, user_id)

    if not user:
        raise ValidationError(
            "Invalid login code."
        )

    if user.status == "banned":
        raise ConflictError(
            "This account has been banned."
        )

    if user.status == "suspended":
        raise ConflictError(
            "This account is currently suspended."
        )

    if not user.login_otp_hash:
        raise ValidationError(
            "No active login code."
        )

    if (
        not user.login_otp_expires_at
        or datetime.utcnow() > user.login_otp_expires_at
    ):
        raise ValidationError(
            "The login code has expired."
        )

    if user.login_otp_attempts >= MAX_LOGIN_OTP_ATTEMPTS:
        raise ConflictError(
            "Too many incorrect login attempts. "
            "Please request a new code."
        )

    if not verify_otp(
        otp,
        user.login_otp_hash,
    ):
        user.login_otp_attempts += 1
        db.session.commit()

        raise ValidationError(
            "Invalid login code."
        )

    # Consume the OTP.
    user.login_otp_hash = None
    user.login_otp_expires_at = None
    user.login_otp_attempts = 0

    user.record_login()

    db.session.commit()

    return user


def send_verification_email_for_user(user):
    token = generate_email_verification_token(user.id)

    from users.mailer_service import send_verification_email

    send_verification_email(user, token)

    user.email_verification_sent_at = datetime.utcnow()
    db.session.commit()


def verify_user_email(token):
    try:
        user_id = decode_email_verification_token(token)
    except Exception:
        raise ValidationError(
            "The email verification link is invalid or expired."
        )

    user = get_user_by_id(user_id)

    if user.is_email_verified:
        return user

    user.mark_email_verified()

    db.session.commit()

    return user



def update_user(user_id, payload, acting_user=None):
    """
    user_id: the id for the user account we are updating
    payload: contains the data that we need to change to
    acting_user: the user trying to perform the update
    """
    user = get_user_by_id(user_id)

    if "full_name" in payload:
        user.set_full_name(
            validate_full_name(payload["full_name"])
        )

    elif "name" in payload:
        user.set_full_name(
            validate_full_name(payload["name"])
        )

    if "first_name" in payload:
        user.first_name = validate_name(
            payload["first_name"],
            "First name",
        )

    if "last_name" in payload:
        user.last_name = validate_name(
            payload["last_name"],
            "Last name",
        )

    if "country" in payload:
        user.country = payload["country"]

    if "status" in payload:
        validate_status(payload["status"])

        if (
            acting_user
            and user.id == acting_user.id
            and payload["status"] in {"suspended", "banned"}
        ):
            raise ConflictError(
                "You cannot disable your own account."
            )

        user.status = payload["status"]

    if "role" in payload:
        new_role = validate_role(payload["role"])

        if (
            acting_user
            and user.id == acting_user.id
            and new_role != user.role
        ):
            raise ConflictError(
                "You cannot change your own administrative role."
            )

        user.role = new_role

    db.session.commit()

    return user



def delete_user(user_id, acting_user=None):
    user = get_user_by_id(user_id)

    if acting_user and user.id == acting_user.id:
        raise ConflictError("You cannot delete your own account.")

    user.status = "banned"
    user.account_status = "closed"

    db.session.commit()

    return user



def list_users(
    page=1,
    per_page=20,
    search=None,
    status=None,
    role=None,
    country=None,
    sort_by="created_at",
    direction="desc",
):
    query = User.query

    # ---------------------------------------------------------
    # Filters
    # ---------------------------------------------------------

    if role:
        role = validate_role(role)
        query = query.filter(User.role == role)

    if status:
        validate_status(status)
        query = query.filter(User.status == status)

    if country:
        query = query.filter(User.country == country)

    # ---------------------------------------------------------
    # Search
    # ---------------------------------------------------------

    if search:
        search = search.strip()

        if search:
            pattern = f"%{search}%"
            search_conditions = []

            search_column_map = {
                "first_name": User.first_name,
                "last_name": User.last_name,
                "email": User.email,
                "country": User.country,
            }

            for field in USER_SEARCH_FIELDS:
                column = search_column_map.get(field)

                if column is not None:
                    search_conditions.append(
                        column.ilike(pattern)
                    )

            if search_conditions:
                query = query.filter(
                    db.or_(*search_conditions)
                )

    # ---------------------------------------------------------
    # Sorting
    # ---------------------------------------------------------

    if sort_by not in USER_SORT_FIELDS:
        raise ValidationError(
            "Invalid sort field.",
            {
                "field": sort_by,
                "allowed_fields": sorted(USER_SORT_FIELDS),
            },
        )

    if direction not in {"asc", "desc"}:
        raise ValidationError(
            "Invalid sort direction.",
            {
                "direction": direction,
                "allowed_directions": ["asc", "desc"],
            },
        )

    sort_map = {
        "name": (
            User.first_name,
            User.last_name,
        ),
        "email": User.email,
        "country": User.country,
        "created_at": User.created_at,
        "last_active": User.last_active_at,
        "status": User.status,
        "role": User.role,
    }

    sort_columns = sort_map.get(sort_by)

    if sort_columns is None:
        raise ValidationError(
            "Sort field is not supported.",
            {"field": sort_by},
        )

    if not isinstance(sort_columns, tuple):
        sort_columns = (sort_columns,)

    for column in sort_columns:
        query = query.order_by(
            column.asc()
            if direction == "asc"
            else column.desc()
        )

    # ---------------------------------------------------------
    # Stable secondary ordering
    # ---------------------------------------------------------
    #
    # This is important when many users have the same value
    # (e.g. same status or country). It prevents records from
    # appearing to jump between pages.
    #

    if sort_by != "created_at":
        query = query.order_by(User.created_at.desc())

    # ---------------------------------------------------------
    # Pagination
    # ---------------------------------------------------------

    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return pagination

def generate_access_token(user):
    return create_access_token(
        identity=str(user.id),
        expires_delta=timedelta(
            seconds=current_app.config.get(
                "ACCESS_EXPIRES",
                86400,
            )
        ),
        additional_claims={
            "role": user.role,
        },
    )


def generate_tokens_for_user(user):
    access = generate_access_token(user)

    refresh = create_refresh_token(
        identity=str(user.id),
        expires_delta=timedelta(
            seconds=current_app.config.get(
                "REFRESH_EXPIRES",
                86400,
            )
        ),
    )

    return access, refresh