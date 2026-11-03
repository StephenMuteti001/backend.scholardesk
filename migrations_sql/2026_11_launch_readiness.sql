-- 2026-11 launch-readiness migration.
-- Safe to run more than once. Prefer `flask db migrate` / `flask db upgrade`
-- once a Flask-Migrate migrations/ folder is initialised (see LAUNCH.md).

-- 1) Public website Contact form inbox
CREATE TABLE IF NOT EXISTS contact_messages (
	id UUID NOT NULL, 
	reference VARCHAR(20) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	topic VARCHAR(40) NOT NULL, 
	subject VARCHAR(200) NOT NULL, 
	message TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	source_page VARCHAR(255), 
	ip_address VARCHAR(64), 
	user_agent VARCHAR(400), 
	admin_note TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_contact_messages_ip_address ON contact_messages (ip_address);
CREATE INDEX IF NOT EXISTS ix_contact_messages_status ON contact_messages (status);
CREATE UNIQUE INDEX IF NOT EXISTS ix_contact_messages_reference ON contact_messages (reference);
CREATE INDEX IF NOT EXISTS ix_contact_messages_email ON contact_messages (email);
CREATE INDEX IF NOT EXISTS ix_contact_messages_created_at ON contact_messages (created_at);
-- 2) Admin workspace settings (Settings & Team page)
ALTER TABLE platform_settings
    ADD COLUMN IF NOT EXISTS workspace JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 3) Break the orders <-> service_requests FK cycle (name the FK so it can
--    be created after both tables). Only needed on fresh databases; existing
--    databases already have an equivalent constraint.

-- 4) Legacy role values (see utils/roles.py)
UPDATE users SET role = 'customer' WHERE role = 'client';
UPDATE users SET role = 'expert'   WHERE role = 'writer';
