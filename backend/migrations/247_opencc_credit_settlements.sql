-- Separate reconciliation queue; the existing usage_billing_dedup ledger owns money.
CREATE TABLE IF NOT EXISTS opencc_credit_settlements (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    api_key_id BIGINT NOT NULL REFERENCES api_keys(id),
    user_id BIGINT NOT NULL REFERENCES users(id),
    upstream_request_id TEXT NOT NULL,
    upstream_api_key_id BIGINT NOT NULL,
    upstream_usage_id BIGINT,
    input JSONB NOT NULL,
    billing_command JSONB,
    credits NUMERIC(24,8),
    unit_price NUMERIC(20,8),
    upstream_cost NUMERIC(20,8),
    status TEXT NOT NULL CHECK (status IN ('pending','ready','settled','review')),
    attempts INTEGER NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    last_error TEXT,
    lease_until TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at TIMESTAMPTZ,
    UNIQUE (request_id, api_key_id),
    UNIQUE (upstream_api_key_id, upstream_request_id),
    UNIQUE (upstream_usage_id),
    CHECK (credits IS NULL OR credits >= 0),
    CHECK (unit_price IS NULL OR unit_price > 0),
    CHECK (upstream_cost IS NULL OR upstream_cost >= 0)
);
CREATE INDEX IF NOT EXISTS opencc_credit_settlements_due_idx ON opencc_credit_settlements (next_attempt_at, id) WHERE status IN ('pending','ready');
CREATE INDEX IF NOT EXISTS opencc_credit_settlements_user_idx ON opencc_credit_settlements (user_id, created_at DESC);
