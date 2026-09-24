from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class CustomerRecord:
    """
    Read-model returned by the customer administration service.

    This is intentionally not a SQLAlchemy model.

    User remains the source of truth for identity/account information.
    Order remains the source of truth for request/order/spending information.
    """

    id: str
    name: str
    email: str
    country: str
    joined_at: Optional[datetime]
    requests: int
    orders: int
    spend: Decimal
    status: str
    last_active: Optional[datetime]


def customer_to_dict(customer: CustomerRecord) -> dict:
    return {
        "id": str(customer.id),
        "name": customer.name,
        "email": customer.email,
        "country": customer.country or "",
        "joinedAt": (
            customer.joined_at.isoformat()
            if customer.joined_at
            else None
        ),
        "requests": customer.requests,
        "orders": customer.orders,
        "spend": float(customer.spend or 0),
        "status": customer.status,
        "lastActive": (
            customer.last_active.isoformat()
            if customer.last_active
            else None
        ),
    }