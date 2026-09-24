# utils/roles.py
"""
Single source of truth for user roles / role groups.

The application recognises three *user types*, each of which may map
to more than one underlying `User.role` value:

    Admins    -> "admin", "super_admin"
    Customers -> "customer"    (legacy DB/input value: "client")
    Experts   -> "expert"      (legacy DB/input value: "writer")

`User.role` on the database is, and remains, "customer" / "expert" /
"admin" / "super_admin" (see users/user.py and users/constants.py).
Any existing rows still holding the legacy "client" value need a data
migration (`UPDATE users SET role = 'customer' WHERE role = 'client'`)
alongside the schema migration - this file only controls newly
written values and how incoming role strings are normalized.
Everywhere else in the codebase - decorators, docstrings, variable
names - should talk about "customers" and "experts" for consistency
with the product's own vocabulary. Import the *_ROLES tuples below
rather than hard-coding role strings, so a future rename only has to
happen in one place.

Usage:

    from utils.roles import ADMIN_ROLES, CUSTOMER_ROLES, EXPERT_ROLES
    from utils.authorization import require_roles

    @require_roles(*ADMIN_ROLES)
    def admin_only_route():
        ...

    @require_roles(*CUSTOMER_ROLES, *EXPERT_ROLES)
    def customer_or_expert_route():
        ...
"""

# ---------------------------------------------------------------------------
# Individual role values (must match users/constants.py USER_ROLES exactly)
# ---------------------------------------------------------------------------

ROLE_ADMIN = "admin"
ROLE_SUPER_ADMIN = "super_admin"

# Canonical DB value is "customer"; "client" is the legacy value and is
# normalized to "customer" on input (see users/schemas.py::ROLE_ALIASES) -
# the same pattern already used for expert/writer below.
ROLE_CUSTOMER = "customer"

# Canonical DB value is "expert"; the legacy/UX term is "writer".
ROLE_EXPERT = "expert"


# ---------------------------------------------------------------------------
# Role groups - what require_roles(...) should be called with
# ---------------------------------------------------------------------------

ADMIN_ROLES = (ROLE_ADMIN, ROLE_SUPER_ADMIN)
CUSTOMER_ROLES = (ROLE_CUSTOMER,)
EXPERT_ROLES = (ROLE_EXPERT,)

# Every role able to sign in and hold a dashboard of some kind.
ALL_ROLES = ADMIN_ROLES + CUSTOMER_ROLES + EXPERT_ROLES

# Any authenticated, non-admin platform participant.
NON_ADMIN_ROLES = CUSTOMER_ROLES + EXPERT_ROLES


def user_type_for_role(role):
    """
    Map a raw `User.role` value to the user-type bucket it belongs to.

    Returns one of "admin", "customer", "expert", or None.
    """
    if role in ADMIN_ROLES:
        return "admin"

    if role in CUSTOMER_ROLES:
        return "customer"

    if role in EXPERT_ROLES:
        return "expert"

    return None
