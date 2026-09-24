-- AssessDesk schema. Prefer `flask db migrate -m "assessdesk"` (models live in
-- assessdesk/models.py and are imported via assessdesk.routes at app start);
-- this file is the equivalent hand-written SQL for review / manual apply.
BEGIN;

CREATE TABLE assessdesk_accounts (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  starter_granted BOOLEAN NOT NULL DEFAULT FALSE,
  last_low_balance_notified INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE assessdesk_packages (
  id UUID PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  description VARCHAR(255),
  questions INTEGER NOT NULL CONSTRAINT ck_ad_pkg_questions_pos CHECK (questions > 0),
  validity_days INTEGER NOT NULL CONSTRAINT ck_ad_pkg_validity_pos CHECK (validity_days > 0),
  price_minor BIGINT NOT NULL CONSTRAINT ck_ad_pkg_price_nonneg CHECK (price_minor >= 0),
  currency VARCHAR(3) NOT NULL DEFAULT 'KES',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_assessdesk_packages_is_active ON assessdesk_packages(is_active);

CREATE TABLE assessdesk_purchases (
  id UUID PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  package_id UUID NOT NULL REFERENCES assessdesk_packages(id) ON DELETE RESTRICT,
  questions INTEGER NOT NULL,
  validity_days INTEGER NOT NULL,
  amount_minor BIGINT NOT NULL,
  currency VARCHAR(3) NOT NULL,
  reference VARCHAR(64) NOT NULL UNIQUE,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  gateway VARCHAR(20) NOT NULL DEFAULT 'paystack',
  gateway_response JSONB,
  paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_assessdesk_purchases_user_id ON assessdesk_purchases(user_id);
CREATE INDEX ix_assessdesk_purchases_status ON assessdesk_purchases(status);

CREATE TABLE assessdesk_grants (
  id UUID PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source VARCHAR(20) NOT NULL,
  package_id UUID REFERENCES assessdesk_packages(id) ON DELETE SET NULL,
  purchase_id UUID UNIQUE REFERENCES assessdesk_purchases(id) ON DELETE SET NULL,
  questions_granted INTEGER NOT NULL,
  questions_remaining INTEGER NOT NULL,
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  note VARCHAR(255),
  expiry_warned_hours INTEGER,
  grace_notified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_ad_grant_remaining_nonneg CHECK (questions_remaining >= 0),
  CONSTRAINT ck_ad_grant_remaining_le_granted CHECK (questions_remaining <= questions_granted)
);
CREATE INDEX ix_ad_grants_user_status_expiry ON assessdesk_grants(user_id, status, expires_at);

CREATE TABLE assessdesk_ledger (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  grant_id UUID REFERENCES assessdesk_grants(id) ON DELETE CASCADE,
  delta INTEGER NOT NULL,
  reason VARCHAR(20) NOT NULL,
  idempotency_key VARCHAR(64),
  device_id UUID,
  meta JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_assessdesk_ledger_user_id ON assessdesk_ledger(user_id);
CREATE INDEX ix_assessdesk_ledger_created_at ON assessdesk_ledger(created_at);

CREATE TABLE assessdesk_consume_requests (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  idempotency_key VARCHAR(64) NOT NULL,
  amount INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, idempotency_key)
);

CREATE TABLE assessdesk_devices (
  id UUID PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_device_id VARCHAR(64) NOT NULL,
  device_name VARCHAR(120),
  client_version VARCHAR(40),
  refresh_token_hash VARCHAR(128) NOT NULL UNIQUE,
  refresh_expires_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_assessdesk_devices_user_id ON assessdesk_devices(user_id);
CREATE INDEX ix_ad_devices_user_client ON assessdesk_devices(user_id, client_device_id);

COMMIT;
