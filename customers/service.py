from decimal import Decimal
from datetime import datetime, timezone, timedelta

from sqlalchemy import (
    and_,
    desc,
    asc,
    func,
    or_,
)

from extensions import db

from users.user import User
from orders.order import Order

from customers.customer import (
    CustomerRecord,
)

from customers.constants import (
    CUSTOMER_ROLE,
    DEFAULT_MESSAGE_BODY,
    DEFAULT_MESSAGE_SUBJECT,
)

from utils.exceptions import (
    ValidationError,
    NotFoundError,
    ConflictError,
)
from utils.transaction import transaction


# ---------------------------------------------------------------------------
# Internal model-field helpers
# ---------------------------------------------------------------------------

def _user_id_column():
    return getattr(User, "id")


def _user_name_column():
    # User.full_name is a hybrid_property (see users/user.py) - it
    # works both on loaded instances and as a SQL expression here.
    return User.full_name


def _user_country_column():
    return getattr(User, "country")


def _user_role_column():
    return getattr(User, "role")


def _user_email_column():
    return getattr(User, "email")


def _user_created_column():
    if hasattr(User, "created_at"):
        return User.created_at

    return User.createdAt


def _user_status_column():
    if hasattr(User, "status"):
        return User.status

    if hasattr(User, "account_status"):
        return User.account_status

    raise AttributeError(
        "User model must have either status or account_status."
    )


def _user_last_active_column():
    return User.last_active_at


def _order_client_column():
    return Order.customer_id


def _order_created_column():
    if hasattr(Order, "created_at"):
        return Order.created_at

    if hasattr(Order, "createdAt"):
        return Order.createdAt

    raise AttributeError(
        "Order model must have created_at or createdAt."
    )


def _order_amount_column():
    """
    Determine the customer-facing amount.

    Your historical order code uses totalCost, while newer code may use
    snake_case. Prefer total_cost if available and otherwise fall back to
    totalCost/client_budget/budget.
    """

    return Order.amount


# ---------------------------------------------------------------------------
# Customer query
# ---------------------------------------------------------------------------

def _customer_base_query():
    return User.query.filter(
        _user_role_column() == CUSTOMER_ROLE
    )


def _customer_by_id(customer_id):
    customer = (
        _customer_base_query()
        .filter(
            _user_id_column() == customer_id
        )
        .first()
    )

    if not customer:
        raise NotFoundError(
            "Customer not found.",
            {"customer_id": str(customer_id)},
        )

    return customer


# ---------------------------------------------------------------------------
# Customer statistics for one user
# ---------------------------------------------------------------------------

def _customer_order_count(customer_id):
    return (
        db.session.query(func.count(Order.id))
        .filter(
            _order_client_column() == customer_id
        )
        .scalar()
        or 0
    )


def _customer_spend(customer_id):
    amount_column = _order_amount_column()

    value = (
        db.session.query(
            func.coalesce(
                func.sum(amount_column),
                0,
            )
        )
        .filter(
            _order_client_column() == customer_id
        )
        .scalar()
    )

    return Decimal(str(value or 0))


def _customer_last_activity(
    customer,
    customer_id,
):
    user_last_active = _user_last_active_column()

    if user_last_active is not None:
        value = getattr(
            customer,
            user_last_active.key,
            None,
        )

        if value:
            return value

    return (
        db.session.query(
            func.max(_order_created_column())
        )
        .filter(
            _order_client_column()
            == customer_id
        )
        .scalar()
    )


def _build_customer_record(customer):
    customer_id = customer.id

    order_count = _customer_order_count(
        customer_id
    )

    spend = _customer_spend(
        customer_id
    )

    last_active = _customer_last_activity(
        customer,
        customer_id,
    )

    return CustomerRecord(
        id=str(customer.id),
        name=customer.full_name or "",
        email=customer.email or "",
        country=customer.country or "",
        joined_at=customer.created_at,
        requests=order_count,
        orders=order_count,
        spend=spend,
        status=customer.status or "pending",
        last_active=last_active,
    )


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

def list_customers(
    page=1,
    per_page=20,
    search=None,
    status=None,
    country=None,
    sort_by="joined_at",
    direction="desc",
):
    query = _customer_base_query()

    name_column = _user_name_column()
    email_column = _user_email_column()
    country_column = _user_country_column()

    # --------------------------------------------------
    # Search
    # --------------------------------------------------

    if search:
        pattern = f"%{search}%"

        query = query.filter(
            or_(
                name_column.ilike(pattern),
                email_column.ilike(pattern),
                country_column.ilike(pattern),
            )
        )

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    if status:
        query = query.filter(
            _user_status_column() == status
        )

    # --------------------------------------------------
    # Country
    # --------------------------------------------------

    if country:
        query = query.filter(
            country_column == country
        )

    # --------------------------------------------------
    # Sorting
    # --------------------------------------------------

    sort_map = {
        "name": name_column,
        "email": email_column,
        "country": country_column,
        "joined_at": _user_created_column(),
        "joinedAt": _user_created_column(),
        "status": _user_status_column(),
    }

    # SQL aggregation sorting requires a different query shape.
    if sort_by in ("requests", "orders", "spend"):
        order_count = (
            db.session.query(
                _order_client_column().label(
                    "customer_id"
                ),
                func.count(Order.id).label(
                    "order_count"
                ),
                func.coalesce(
                    func.sum(
                        _order_amount_column()
                    ),
                    0,
                ).label("spend"),
            )
            .group_by(
                _order_client_column()
            )
            .subquery()
        )

        query = query.outerjoin(
            order_count,
            order_count.c.customer_id
            == _user_id_column(),
        )

        if sort_by in ("requests", "orders"):
            sort_column = func.coalesce(
                order_count.c.order_count,
                0,
            )
        else:
            sort_column = func.coalesce(
                order_count.c.spend,
                0,
            )

    else:
        sort_column = sort_map.get(
            sort_by,
            _user_created_column(),
        )

    if direction == "asc":
        query = query.order_by(
            asc(sort_column),
            asc(_user_id_column()),
        )
    else:
        query = query.order_by(
            desc(sort_column),
            desc(_user_id_column()),
        )

    # --------------------------------------------------
    # Pagination
    # --------------------------------------------------

    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    records = [
        _build_customer_record(customer)
        for customer in pagination.items
    ]

    # --------------------------------------------------
    # Country filter values
    # --------------------------------------------------

    countries = [
        value[0]
        for value in (
            _customer_base_query()
            .with_entities(
                country_column
            )
            .filter(
                country_column.isnot(None)
            )
            .filter(
                country_column != ""
            )
            .distinct()
            .order_by(
                asc(country_column)
            )
            .all()
        )
    ]

    return {
        "items": records,
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "pages": pagination.pages,
            "total": pagination.total,
        },
        "countries": countries,
    }


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

def get_customer(customer_id):
    customer = _customer_by_id(
        customer_id
    )

    return _build_customer_record(
        customer
    )


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

def update_customer(
    customer_id,
    payload,
):
    customer = _customer_by_id(
        customer_id
    )

    if "status" in payload:
        setattr(
            customer,
            _user_status_column().key,
            payload["status"],
        )

    if "name" in payload:
        customer.set_full_name(
            payload["name"]
        )

    if "country" in payload:
        customer.country = (
            payload["country"]
        )

    with transaction():
        db.session.add(customer)

    return _build_customer_record(
        customer
    )


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

def delete_customer(customer_id):
    customer = _customer_by_id(
        customer_id
    )

    """
    We deliberately do not blindly delete the User.

    A customer may have orders, messages, wallet transactions, chats,
    notifications, etc. Hard deletion can therefore violate FK constraints.

    For an administrative "Delete" operation, we first attempt a real
    deletion. If the project has dependent records, replace this with the
    application's existing soft-delete/deactivation mechanism.
    """

    try:
        with transaction():
            db.session.delete(customer)

    except Exception as exc:
        raise ConflictError(
            "Customer cannot be deleted because other records depend on "
            "this account.",
            {
                "customer_id": str(customer_id),
                "reason": str(exc),
            },
        )

    return None


# ---------------------------------------------------------------------------
# BULK UPDATE
# ---------------------------------------------------------------------------

def bulk_update_customers(
    customer_ids,
    status,
):
    customers = (
        _customer_base_query()
        .filter(
            _user_id_column().in_(
                customer_ids
            )
        )
        .all()
    )

    found_ids = {
        str(customer.id)
        for customer in customers
    }

    missing = [
        customer_id
        for customer_id in customer_ids
        if str(customer_id) not in found_ids
    ]

    if missing:
        raise NotFoundError(
            "One or more customers were not found.",
            {
                "missing_ids": missing,
            },
        )

    status_field = _user_status_column().key

    with transaction():
        for customer in customers:
            setattr(
                customer,
                status_field,
                status,
            )

    return len(customers)


# ---------------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------------

def get_customer_statistics():
    customer_query = _customer_base_query()

    total = customer_query.count()

    status_column = _user_status_column()

    active = (
        customer_query
        .filter(
            status_column == "active"
        )
        .count()
    )

    restricted = (
        customer_query
        .filter(
            status_column.in_(
                ["suspended", "banned"]
            )
        )
        .count()
    )

    amount_column = _order_amount_column()

    lifetime_revenue = (
        db.session.query(
            func.coalesce(
                func.sum(
                    amount_column
                ),
                0,
            )
        )
        .join(
            User,
            _order_client_column()
            == _user_id_column(),
        )
        .filter(
            _user_role_column()
            == CUSTOMER_ROLE
        )
        .scalar()
        or 0
    )

    # Current month vs previous month customer count.
    now = datetime.now(timezone.utc)

    month_start = datetime(
        now.year,
        now.month,
        1,
        tzinfo=timezone.utc,
    )

    if now.month == 1:
        previous_month_start = datetime(
            now.year - 1,
            12,
            1,
            tzinfo=timezone.utc,
        )
    else:
        previous_month_start = datetime(
            now.year,
            now.month - 1,
            1,
            tzinfo=timezone.utc,
        )

    created_column = _user_created_column()

    current_month_total = (
        customer_query
        .filter(
            created_column >= month_start
        )
        .count()
    )

    previous_month_total = (
        customer_query
        .filter(
            and_(
                created_column
                >= previous_month_start,
                created_column
                < month_start,
            )
        )
        .count()
    )

    if previous_month_total == 0:
        if current_month_total > 0:
            total_delta = (
                f"+{current_month_total}"
            )
        else:
            total_delta = "0"
    else:
        percentage = (
            (
                current_month_total
                - previous_month_total
            )
            / previous_month_total
        ) * 100

        sign = "+" if percentage >= 0 else ""

        total_delta = (
            f"{sign}{percentage:.1f}%"
        )

    return {
        "total": total,
        "total_delta": total_delta,
        "active": active,
        "lifetime_revenue": float(
            lifetime_revenue or 0
        ),
        "restricted": restricted,
    }


# ---------------------------------------------------------------------------
# MESSAGE
# ---------------------------------------------------------------------------

def message_customer(
    customer_id,
    subject=None,
    body=None,
):
    customer = _customer_by_id(
        customer_id
    )

    subject = (
        subject
        or DEFAULT_MESSAGE_SUBJECT
    )

    body = (
        body
        or DEFAULT_MESSAGE_BODY
    )

    # Your existing project already has an email service/mailer.
    # The existing codebase imports send_email from utils.mailer.
    from utils.mailer import send_email

    send_email(
        to=customer.email,
        subject=subject,
        html=(
            body
            .replace("\n", "<br>")
        ),
    )

    return {
        "customer_id": str(
            customer.id
        ),
        "email": customer.email,
    }


# ---------------------------------------------------------------------------
# BULK EMAIL
# ---------------------------------------------------------------------------

def bulk_email_customers(
    customer_ids,
    subject=None,
    body=None,
):
    customers = (
        _customer_base_query()
        .filter(
            _user_id_column().in_(
                customer_ids
            )
        )
        .all()
    )

    found_ids = {
        str(customer.id)
        for customer in customers
    }

    missing = [
        customer_id
        for customer_id in customer_ids
        if str(customer_id) not in found_ids
    ]

    if missing:
        raise NotFoundError(
            "One or more customers were not found.",
            {
                "missing_ids": missing,
            },
        )

    subject = (
        subject
        or DEFAULT_MESSAGE_SUBJECT
    )

    body = (
        body
        or "Hello, we are following up regarding your account."
    )

    from utils.mailer import send_email

    sent = 0

    for customer in customers:
        send_email(
            to=customer.email,
            subject=subject,
            html=body.replace(
                "\n",
                "<br>",
            ),
        )

        sent += 1

    return sent