# utils/authorization.py

from functools import wraps

from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)

from extensions import db
from users.user import User
from utils.exceptions import (
    ForbiddenError,
    NotFoundError,
)


def get_current_user():
    """
    Load the authenticated user for the current request.

    Requires a valid JWT to already be present (pair this with
    @jwt_required() or @require_roles(...) on the route). Raises
    NotFoundError if the token's subject no longer maps to a user
    (e.g. the account was deleted after the token was issued).

    Centralising this avoids every module re-implementing its own
    "uid = get_jwt_identity(); user = User.query.get(uid)" lookup.
    """

    user_id = get_jwt_identity()

    user = db.session.get(User, user_id)

    if not user:
        raise NotFoundError(
            "User not found."
        )

    return user


def require_roles(*allowed_roles):
    """
    Require an authenticated user whose role is one of
    the supplied allowed roles.

    Example:

        @require_roles("admin", "super_admin")

    Authentication and authorization are both handled here.
    """

    if not allowed_roles:
        raise ValueError(
            "require_roles() requires at least one role."
        )

    def decorator(fn):

        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):

            user_id = get_jwt_identity()

            user = db.session.get(User, user_id)

            if not user:
                raise NotFoundError(
                    "User not found."
                )

            if user.role not in allowed_roles:
                raise ForbiddenError(
                    details={
                        "required_roles": list(allowed_roles),
                    }
                )

            return fn(*args, **kwargs)

        return wrapper

    return decorator