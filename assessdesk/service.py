# assessdesk/service.py
"""
AssessDesk business logic.

Invariants
----------
* Server clock (UTC) is the only authority for expiry.
* A grant is usable while status == active, questions_remaining > 0 and
  now < expires_at + GRACE_PERIOD.
* Debits lock the user's usable grants (SELECT ... FOR UPDATE) and
  consume FIFO by expiry, so concurrent requests can never overdraw.
* Every debit is keyed by a client idempotency key; a retry of the same
  key returns the current balance without charging again.
* Every balance change writes an immutable ledger row.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import timedelta

from flask import current_app
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

from extensions import db
from users.user import User
from utils.exceptions import ConflictError, NotFoundError, ServiceError, ValidationError
from utils.pagination import paginate_query
from utils.transaction import transaction

from assessdesk import notifications, paystack
from assessdesk.constants import (
    DESKTOP_REFRESH_TTL,
    EXPIRY_WARNING_HOURS,
    GRACE_PERIOD,
    GRANT_ACTIVE,
    GRANT_EXHAUSTED,
    GRANT_EXPIRED,
    GRANT_IN_GRACE,
    GRANT_REVOKED,
    LEDGER_ADJUST,
    LEDGER_CONSUME,
    LEDGER_EXPIRE,
    LEDGER_GRANT,
    LEDGER_REVOKE,
    LOW_BALANCE_THRESHOLDS,
    MAX_ACTIVE_DEVICES_PER_USER,
    PURCHASE_ABANDONED,
    PURCHASE_FAILED,
    PURCHASE_PAID,
    PURCHASE_PENDING,
    SOURCE_ADMIN,
    SOURCE_PURCHASE,
    SOURCE_STARTER,
    STARTER_QUESTIONS,
    STARTER_VALIDITY_DAYS,
)
from assessdesk.models import (
    AssessDeskAccount,
    AssessDeskConsumeRequest,
    AssessDeskDevice,
    AssessDeskGrant,
    AssessDeskLedgerEntry,
    AssessDeskPackage,
    AssessDeskPurchase,
    utcnow,
)
from assessdesk.schemas import grant_effective_status, iso, serialize_grant

log = logging.getLogger(__name__)


class InsufficientCredits(ServiceError):
    def __init__(self, remaining):
        super().__init__(
            code="INSUFFICIENT_CREDITS",
            message="You don't have enough questions left. Top up to continue.",
            details={"questions_remaining": remaining},
            status_code=402,
        )


# ===========================================================================
# Accounts
# ===========================================================================

def _usable_filter(now):
    return (
        AssessDeskGrant.status == GRANT_ACTIVE,
        AssessDeskGrant.questions_remaining > 0,
        AssessDeskGrant.expires_at + GRACE_PERIOD > now,
    )


def _create_grant(user_id, *, questions, validity_days, source, now,
                  package_id=None, purchase_id=None, granted_by=None, note=None):
    grant = AssessDeskGrant(
        user_id=user_id,
        source=source,
        package_id=package_id,
        purchase_id=purchase_id,
        questions_granted=questions,
        questions_remaining=questions,
        granted_at=now,
        # Whole days = exact 24h periods from the grant instant (UTC):
        # no calendar/DST ambiguity for any timezone.
        expires_at=now + timedelta(days=validity_days),
        status=GRANT_ACTIVE,
        granted_by=granted_by,
        note=note,
    )
    db.session.add(grant)
    db.session.flush()
    db.session.add(AssessDeskLedgerEntry(
        user_id=user_id, grant_id=grant.id, delta=questions, reason=LEDGER_GRANT,
        meta={"source": source}, created_at=now,
    ))
    # New credit re-arms low-balance notifications.
    db.session.query(AssessDeskAccount).filter_by(user_id=user_id).update(
        {"last_low_balance_notified": None}
    )
    return grant


def ensure_account(user):
    """
    Idempotently create the AssessDesk account for any platform user and
    issue the one-time starter grant. Safe under concurrent calls.
    """
    account = db.session.get(AssessDeskAccount, user.id)
    if account and account.starter_granted:
        if not account.enabled:
            raise ConflictError("AssessDesk access is disabled for this account.")
        return account

    with transaction():
        db.session.execute(
            pg_insert(AssessDeskAccount.__table__)
            .values(user_id=user.id, enabled=True, starter_granted=False,
                    created_at=utcnow(), updated_at=utcnow())
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        account = (
            db.session.query(AssessDeskAccount)
            .filter_by(user_id=user.id)
            .with_for_update()
            .one()
        )
        if not account.starter_granted:
            _create_grant(
                user.id,
                questions=STARTER_QUESTIONS,
                validity_days=STARTER_VALIDITY_DAYS,
                source=SOURCE_STARTER,
                now=utcnow(),
                note="Welcome grant",
            )
            account.starter_granted = True

    if not account.enabled:
        raise ConflictError("AssessDesk access is disabled for this account.")
    return account


# ===========================================================================
# Balance
# ===========================================================================

def _warning_for(total, next_grant, now):
    """Single most-urgent message for the client to display."""
    if total <= 0:
        return {"level": "empty", "message": "You're out of questions. Top up to keep going."}
    if next_grant is not None:
        status = grant_effective_status(next_grant, now)
        if status == GRANT_IN_GRACE:
            mins = int((next_grant.expires_at + GRACE_PERIOD - now).total_seconds() // 60)
            return {
                "level": "grace",
                "message": f"{next_grant.questions_remaining} questions expired and will be "
                           f"forfeited in {mins} min. Use them or top up.",
            }
        hours_left = (next_grant.expires_at - now).total_seconds() / 3600
        if hours_left <= EXPIRY_WARNING_HOURS[-1]:
            return {"level": "expiring",
                    "message": f"{next_grant.questions_remaining} questions expire within 24 hours."}
    if total <= LOW_BALANCE_THRESHOLDS[1]:
        return {"level": "critical", "message": f"Only {total} questions left. Top up now."}
    if total <= LOW_BALANCE_THRESHOLDS[0]:
        return {"level": "low", "message": f"{total} questions left. Consider topping up soon."}
    if next_grant is not None and (next_grant.expires_at - now).total_seconds() <= EXPIRY_WARNING_HOURS[0] * 3600:
        return {"level": "expiring",
                "message": f"{next_grant.questions_remaining} questions expire within 3 days."}
    return {"level": "none", "message": None}


def build_balance(user_id, now=None):
    now = now or utcnow()
    grants = (
        AssessDeskGrant.query
        .filter(AssessDeskGrant.user_id == user_id, *_usable_filter(now))
        .options(selectinload(AssessDeskGrant.package))
        .order_by(AssessDeskGrant.expires_at.asc(), AssessDeskGrant.granted_at.asc())
        .all()
    )
    total = sum(g.questions_remaining for g in grants)
    nxt = grants[0] if grants else None
    return {
        "tokens": total,  # legacy field name the desktop client already reads
        "questions_remaining": total,
        "in_grace": bool(nxt and grant_effective_status(nxt, now) == GRANT_IN_GRACE),
        "next_expiry": serialize_grant(nxt, now) if nxt else None,
        "grants": [serialize_grant(g, now) for g in grants],
        "warning": _warning_for(total, nxt, now),
        "low_balance_thresholds": list(LOW_BALANCE_THRESHOLDS),
        "server_time": iso(now),
    }


# ===========================================================================
# Consumption
# ===========================================================================

def consume(user, amount, idempotency_key, device_id=None, meta=None):
    ensure_account(user)
    now = utcnow()
    replayed = False

    with transaction():
        inserted = db.session.execute(
            pg_insert(AssessDeskConsumeRequest.__table__)
            .values(user_id=user.id, idempotency_key=idempotency_key, amount=amount, created_at=now)
            .on_conflict_do_nothing()
            .returning(AssessDeskConsumeRequest.__table__.c.idempotency_key)
        ).first()

        if inserted is None:
            replayed = True
        else:
            grants = (
                AssessDeskGrant.query
                .filter(AssessDeskGrant.user_id == user.id, *_usable_filter(now))
                .order_by(AssessDeskGrant.expires_at.asc(), AssessDeskGrant.granted_at.asc())
                .with_for_update()
                .all()
            )
            available = sum(g.questions_remaining for g in grants)
            if available < amount:
                # Raising rolls back the idempotency row too, so the
                # client may retry the same key after topping up.
                raise InsufficientCredits(available)

            left = amount
            for g in grants:
                if left == 0:
                    break
                take = min(left, g.questions_remaining)
                g.questions_remaining -= take
                if g.questions_remaining == 0:
                    g.status = GRANT_EXHAUSTED
                left -= take
                db.session.add(AssessDeskLedgerEntry(
                    user_id=user.id, grant_id=g.id, delta=-take, reason=LEDGER_CONSUME,
                    idempotency_key=idempotency_key, device_id=device_id,
                    meta=meta, created_at=now,
                ))

    balance = build_balance(user.id, now)
    balance["replayed"] = replayed
    if not replayed:
        _maybe_notify_low_balance(user, balance["questions_remaining"])
    return balance


def _maybe_notify_low_balance(user, remaining):
    crossed = [t for t in LOW_BALANCE_THRESHOLDS if remaining <= t]
    if not crossed:
        return
    level = min(crossed)
    with transaction():
        account = (
            db.session.query(AssessDeskAccount)
            .filter_by(user_id=user.id).with_for_update().one()
        )
        already = account.last_low_balance_notified
        if already is not None and already <= level:
            return
        account.last_low_balance_notified = level
    notifications.send_low_balance(user, remaining)


# ===========================================================================
# Packages & purchases (Paystack)
# ===========================================================================

def list_active_packages():
    return (
        AssessDeskPackage.query.filter_by(is_active=True)
        .order_by(AssessDeskPackage.sort_order.asc(), AssessDeskPackage.price_minor.asc())
        .all()
    )


def start_purchase(user, package_id):
    ensure_account(user)
    pkg = db.session.get(AssessDeskPackage, package_id)
    if not pkg or not pkg.is_active:
        raise NotFoundError("Package not found.")

    purchase = AssessDeskPurchase(
        user_id=user.id,
        package_id=pkg.id,
        questions=pkg.questions,
        validity_days=pkg.validity_days,
        amount_minor=pkg.price_minor,
        currency=pkg.currency,
        reference=f"AD-{uuid.uuid4().hex[:20].upper()}",
        status=PURCHASE_PENDING,
    )
    with transaction():
        db.session.add(purchase)

    base = current_app.config.get("ASSESSDESK_FRONTEND_URL", "https://assessdesk.scholardesk.pro")
    data = paystack.initialize_transaction(
        email=user.email,
        amount_minor=purchase.amount_minor,
        currency=purchase.currency,
        reference=purchase.reference,
        callback_url=f"{base}/purchase/complete",
        metadata={"product": "assessdesk", "purchase_id": str(purchase.id), "user_id": user.id},
    )
    return purchase, data.get("authorization_url"), data.get("access_code")


def fulfil_purchase(reference, gateway_data=None):
    """
    Verify with Paystack and credit the grant exactly once. Called from
    both the browser callback and the webhook; whichever arrives first
    wins, the other is a no-op.
    """
    purchase = AssessDeskPurchase.query.filter_by(reference=reference).first()
    if not purchase:
        raise NotFoundError("Purchase not found.")
    if purchase.status == PURCHASE_PAID:
        return purchase

    data = gateway_data or paystack.verify_transaction(reference)
    gw_status = data.get("status")

    with transaction():
        purchase = (
            AssessDeskPurchase.query.filter_by(reference=reference).with_for_update().one()
        )
        if purchase.status == PURCHASE_PAID:
            return purchase

        purchase.gateway_response = {
            k: data.get(k) for k in ("id", "status", "amount", "currency", "channel", "paid_at", "gateway_response")
        }

        if gw_status != "success":
            if gw_status in ("failed", "reversed"):
                purchase.status = PURCHASE_FAILED
            elif gw_status == "abandoned":
                purchase.status = PURCHASE_ABANDONED
            return purchase

        if int(data.get("amount") or 0) != purchase.amount_minor or \
                (data.get("currency") or "").upper() != purchase.currency:
            log.error("[assessdesk] amount/currency mismatch on %s: %s", reference, data)
            purchase.status = PURCHASE_FAILED
            return purchase

        now = utcnow()
        purchase.status = PURCHASE_PAID
        purchase.paid_at = now
        grant = _create_grant(
            purchase.user_id,
            questions=purchase.questions,
            validity_days=purchase.validity_days,
            source=SOURCE_PURCHASE,
            now=now,
            package_id=purchase.package_id,
            purchase_id=purchase.id,
        )

    notifications.send_purchase_receipt(purchase.user, purchase, grant)
    return purchase


def list_my_purchases(user_id, page, per_page):
    q = (AssessDeskPurchase.query.filter_by(user_id=user_id)
         .options(selectinload(AssessDeskPurchase.package))
         .order_by(AssessDeskPurchase.created_at.desc()))
    return paginate_query(q, page, per_page)


# ===========================================================================
# Desktop device sessions
# ===========================================================================

def _hash_refresh(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_device_session(user, client_device_id, device_name=None, client_version=None):
    now = utcnow()
    raw = secrets.token_urlsafe(48)
    with transaction():
        # Re-login on the same install replaces its previous session.
        (AssessDeskDevice.query
         .filter_by(user_id=user.id, client_device_id=client_device_id, revoked_at=None)
         .update({"revoked_at": now}))

        active = (AssessDeskDevice.query
                  .filter(AssessDeskDevice.user_id == user.id,
                          AssessDeskDevice.revoked_at.is_(None),
                          AssessDeskDevice.refresh_expires_at > now)
                  .order_by(AssessDeskDevice.last_seen_at.asc())
                  .all())
        # Cap simultaneous installs: sign out the least recently used.
        for d in active[: max(0, len(active) - MAX_ACTIVE_DEVICES_PER_USER + 1)]:
            d.revoked_at = now

        device = AssessDeskDevice(
            user_id=user.id,
            client_device_id=client_device_id,
            device_name=device_name,
            client_version=client_version,
            refresh_token_hash=_hash_refresh(raw),
            refresh_expires_at=now + DESKTOP_REFRESH_TTL,
            last_seen_at=now,
        )
        db.session.add(device)
    return device, raw


def rotate_device_session(raw_refresh):
    """Validate a refresh token and rotate it (one-time use)."""
    now = utcnow()
    with transaction():
        device = (AssessDeskDevice.query
                  .filter_by(refresh_token_hash=_hash_refresh(raw_refresh or ""))
                  .with_for_update().first())
        if not device or device.revoked_at or device.refresh_expires_at <= now:
            raise ServiceError("SESSION_EXPIRED", "Please sign in again.", status_code=401)
        user = db.session.get(User, device.user_id)
        if not user or user.status in ("banned", "suspended"):
            device.revoked_at = now
            raise ServiceError("SESSION_EXPIRED", "Please sign in again.", status_code=401)
        new_raw = secrets.token_urlsafe(48)
        device.refresh_token_hash = _hash_refresh(new_raw)
        device.refresh_expires_at = now + DESKTOP_REFRESH_TTL
        device.last_seen_at = now
    return user, device, new_raw


def revoke_device(device_id, user_id=None):
    with transaction():
        q = AssessDeskDevice.query.filter_by(id=device_id)
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        q.update({"revoked_at": utcnow()})


def device_is_active(device_id):
    d = db.session.get(AssessDeskDevice, device_id)
    return bool(d and not d.revoked_at and d.refresh_expires_at > utcnow())


def touch_device(device_id):
    AssessDeskDevice.query.filter_by(id=device_id).update({"last_seen_at": utcnow()})
    db.session.commit()


# ===========================================================================
# Scheduled sweep (expiry warnings, grace start, forfeiture)
# ===========================================================================

def run_sweep(now=None):
    """
    Idempotent; run every 10-15 min (see assessdesk/cli.py).
    Returns counters for logging.
    """
    now = now or utcnow()
    stats = {"warned": 0, "grace": 0, "expired": 0}

    # 1) Expiry warnings (72h, 24h), once per window per grant.
    for hours in EXPIRY_WARNING_HOURS:
        due = (AssessDeskGrant.query
               .filter(AssessDeskGrant.status == GRANT_ACTIVE,
                       AssessDeskGrant.questions_remaining > 0,
                       AssessDeskGrant.expires_at > now,
                       AssessDeskGrant.expires_at <= now + timedelta(hours=hours),
                       or_(AssessDeskGrant.expiry_warned_hours.is_(None),
                           AssessDeskGrant.expiry_warned_hours > hours))
               .all())
        for g in due:
            g.expiry_warned_hours = hours
            db.session.commit()
            notifications.send_expiry_warning(g.user, g, hours)
            stats["warned"] += 1

    # 2) Grace started.
    grace = (AssessDeskGrant.query
             .filter(AssessDeskGrant.status == GRANT_ACTIVE,
                     AssessDeskGrant.questions_remaining > 0,
                     AssessDeskGrant.expires_at <= now,
                     AssessDeskGrant.expires_at + GRACE_PERIOD > now,
                     AssessDeskGrant.grace_notified_at.is_(None))
             .all())
    for g in grace:
        g.grace_notified_at = now
        db.session.commit()
        notifications.send_grace_started(g.user, g, g.expires_at + GRACE_PERIOD)
        stats["grace"] += 1

    # 3) Forfeit after grace.
    with transaction():
        ended = (AssessDeskGrant.query
                 .filter(AssessDeskGrant.status == GRANT_ACTIVE,
                         AssessDeskGrant.expires_at + GRACE_PERIOD <= now)
                 .with_for_update(skip_locked=True).all())
        for g in ended:
            if g.questions_remaining:
                db.session.add(AssessDeskLedgerEntry(
                    user_id=g.user_id, grant_id=g.id, delta=-g.questions_remaining,
                    reason=LEDGER_EXPIRE, created_at=now,
                ))
            g.questions_remaining = 0
            g.status = GRANT_EXPIRED
            stats["expired"] += 1

    # 4) Old pending checkouts become abandoned.
    with transaction():
        (AssessDeskPurchase.query
         .filter(AssessDeskPurchase.status == PURCHASE_PENDING,
                 AssessDeskPurchase.created_at < now - timedelta(hours=24))
         .update({"status": PURCHASE_ABANDONED}, synchronize_session=False))

    return stats


# ===========================================================================
# Admin
# ===========================================================================

def admin_list_packages():
    return AssessDeskPackage.query.order_by(
        AssessDeskPackage.sort_order.asc(), AssessDeskPackage.price_minor.asc()
    ).all()


def admin_create_package(fields):
    pkg = AssessDeskPackage(**fields)
    with transaction():
        db.session.add(pkg)
    return pkg


def admin_update_package(package_id, fields):
    pkg = db.session.get(AssessDeskPackage, package_id)
    if not pkg:
        raise NotFoundError("Package not found.")
    with transaction():
        for k, v in fields.items():
            setattr(pkg, k, v)
    return pkg


def admin_list_grants(f):
    now = utcnow()
    q = (AssessDeskGrant.query.join(User, User.id == AssessDeskGrant.user_id)
         .options(selectinload(AssessDeskGrant.user), selectinload(AssessDeskGrant.package)))
    if f["status"] == GRANT_IN_GRACE:
        q = q.filter(AssessDeskGrant.status == GRANT_ACTIVE,
                     AssessDeskGrant.expires_at <= now,
                     AssessDeskGrant.expires_at + GRACE_PERIOD > now)
    elif f["status"] == GRANT_ACTIVE:
        q = q.filter(AssessDeskGrant.status == GRANT_ACTIVE, AssessDeskGrant.expires_at > now)
    elif f["status"]:
        q = q.filter(AssessDeskGrant.status == f["status"])
    if f["source"]:
        q = q.filter(AssessDeskGrant.source == f["source"])
    if f["search"]:
        like = f"%{f['search'].lower()}%"
        q = q.filter(or_(func.lower(User.email).like(like),
                         func.lower(User.first_name + " " + User.last_name).like(like)))
    col = getattr(AssessDeskGrant, f["sort_by"])
    q = q.order_by(col.asc() if f["direction"] == "asc" else col.desc())
    return paginate_query(q, f["page"], f["per_page"])


def admin_manual_grant(admin, fields):
    user = db.session.get(User, fields["user_id"])
    if not user:
        raise NotFoundError("User not found.")
    ensure_account(user)
    with transaction():
        grant = _create_grant(
            user.id, questions=fields["questions"], validity_days=fields["validity_days"],
            source=SOURCE_ADMIN, now=utcnow(), granted_by=admin.id, note=fields["note"],
        )
    return grant


def admin_extend_grant(admin, grant_id, hours):
    with transaction():
        g = AssessDeskGrant.query.filter_by(id=grant_id).with_for_update().first()
        if not g:
            raise NotFoundError("Grant not found.")
        if g.status in (GRANT_REVOKED, GRANT_EXHAUSTED):
            raise ValidationError(f"A {g.status} grant cannot be extended.")
        now = utcnow()
        base = max(g.expires_at, now) if g.status == GRANT_EXPIRED else g.expires_at
        g.expires_at = base + timedelta(hours=hours)
        g.status = GRANT_ACTIVE if g.questions_remaining > 0 else GRANT_EXHAUSTED
        g.expiry_warned_hours = None
        g.grace_notified_at = None
        db.session.add(AssessDeskLedgerEntry(
            user_id=g.user_id, grant_id=g.id, delta=0, reason=LEDGER_ADJUST,
            meta={"action": "extend", "hours": hours, "by": admin.id}, created_at=now,
        ))
    return g


def admin_revoke_grant(admin, grant_id):
    with transaction():
        g = AssessDeskGrant.query.filter_by(id=grant_id).with_for_update().first()
        if not g:
            raise NotFoundError("Grant not found.")
        if g.status == GRANT_REVOKED:
            return g
        now = utcnow()
        if g.questions_remaining:
            db.session.add(AssessDeskLedgerEntry(
                user_id=g.user_id, grant_id=g.id, delta=-g.questions_remaining,
                reason=LEDGER_REVOKE, meta={"by": admin.id}, created_at=now,
            ))
        g.questions_remaining = 0
        g.status = GRANT_REVOKED
    return g


def admin_list_accounts(page, per_page, search=None):
    now = utcnow()
    remaining = (
        db.session.query(func.coalesce(func.sum(AssessDeskGrant.questions_remaining), 0))
        .filter(AssessDeskGrant.user_id == AssessDeskAccount.user_id, *_usable_filter(now))
        .correlate(AssessDeskAccount).scalar_subquery()
    )
    devices = (
        db.session.query(func.count(AssessDeskDevice.id))
        .filter(AssessDeskDevice.user_id == AssessDeskAccount.user_id,
                AssessDeskDevice.revoked_at.is_(None),
                AssessDeskDevice.refresh_expires_at > now)
        .correlate(AssessDeskAccount).scalar_subquery()
    )
    last_seen = (
        db.session.query(func.max(AssessDeskDevice.last_seen_at))
        .filter(AssessDeskDevice.user_id == AssessDeskAccount.user_id)
        .correlate(AssessDeskAccount).scalar_subquery()
    )
    q = (db.session.query(AssessDeskAccount, User,
                          remaining.label("remaining"), devices.label("devices"),
                          last_seen.label("last_seen"))
         .join(User, User.id == AssessDeskAccount.user_id))
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(or_(func.lower(User.email).like(like),
                         func.lower(User.first_name + " " + User.last_name).like(like)))
    q = q.order_by(AssessDeskAccount.created_at.desc())
    rows, pagination = paginate_query(q, page, per_page)
    items = [{
        "user_id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role,
        "enabled": a.enabled,
        "questions_remaining": int(rem or 0),
        "active_devices": int(dev or 0),
        "last_seen_at": iso(seen),
        "joined_at": iso(a.created_at),
    } for a, u, rem, dev, seen in rows]
    return items, pagination


def admin_set_account_enabled(user_id, enabled):
    with transaction():
        a = db.session.get(AssessDeskAccount, user_id)
        if not a:
            raise NotFoundError("AssessDesk account not found.")
        a.enabled = enabled
        if not enabled:
            AssessDeskDevice.query.filter_by(user_id=user_id, revoked_at=None).update(
                {"revoked_at": utcnow()})
    return a


def admin_statistics():
    now = utcnow()
    week_ago = now - timedelta(days=7)
    usable = db.session.query(func.coalesce(func.sum(AssessDeskGrant.questions_remaining), 0)) \
        .filter(*_usable_filter(now)).scalar()
    sold = db.session.query(func.coalesce(func.sum(AssessDeskPurchase.questions), 0)) \
        .filter(AssessDeskPurchase.status == PURCHASE_PAID).scalar()
    revenue = db.session.query(AssessDeskPurchase.currency,
                               func.coalesce(func.sum(AssessDeskPurchase.amount_minor), 0)) \
        .filter(AssessDeskPurchase.status == PURCHASE_PAID) \
        .group_by(AssessDeskPurchase.currency).all()
    consumed_7d = db.session.query(func.coalesce(-func.sum(AssessDeskLedgerEntry.delta), 0)) \
        .filter(AssessDeskLedgerEntry.reason == LEDGER_CONSUME,
                AssessDeskLedgerEntry.created_at >= week_ago).scalar()
    expiring_7d = db.session.query(func.coalesce(func.sum(AssessDeskGrant.questions_remaining), 0)) \
        .filter(AssessDeskGrant.status == GRANT_ACTIVE,
                AssessDeskGrant.questions_remaining > 0,
                AssessDeskGrant.expires_at > now,
                AssessDeskGrant.expires_at <= now + timedelta(days=7)).scalar()
    active_users = db.session.query(func.count(func.distinct(AssessDeskGrant.user_id))) \
        .filter(*_usable_filter(now)).scalar()
    accounts = db.session.query(func.count(AssessDeskAccount.user_id)).scalar()
    return {
        "accounts": int(accounts or 0),
        "active_users": int(active_users or 0),
        "questions_outstanding": int(usable or 0),
        "questions_sold": int(sold or 0),
        "questions_consumed_7d": int(consumed_7d or 0),
        "questions_expiring_7d": int(expiring_7d or 0),
        "revenue": [{"currency": c, "amount": int(a) / 100} for c, a in revenue],
    }


def admin_list_purchases(page, per_page, status=None, search=None):
    q = (AssessDeskPurchase.query.join(User, User.id == AssessDeskPurchase.user_id)
         .options(selectinload(AssessDeskPurchase.user), selectinload(AssessDeskPurchase.package)))
    if status:
        q = q.filter(AssessDeskPurchase.status == status)
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(or_(func.lower(User.email).like(like),
                         func.lower(AssessDeskPurchase.reference).like(like)))
    q = q.order_by(AssessDeskPurchase.created_at.desc())
    return paginate_query(q, page, per_page)
