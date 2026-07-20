-- Dimensiones de la estrella `crm`.
-- dim_lead se carga pero NO tiene ninguna FK entrante desde ningún hecho --
-- confirmado en discovery que es una tabla aislada, sin relación al resto.

CREATE TABLE IF NOT EXISTS gold.dim_account (
    sk_account      SERIAL PRIMARY KEY,
    account_id      TEXT UNIQUE NOT NULL,
    name            TEXT,
    industry        TEXT,
    country         TEXT,
    annual_revenue  NUMERIC,
    employees       INT
);

INSERT INTO gold.dim_account (account_id, name, industry, country, annual_revenue, employees)
SELECT account_id, name, industry, country, annual_revenue, employees
FROM staging.crm_accounts
ON CONFLICT (account_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.dim_contact (
    sk_contact  SERIAL PRIMARY KEY,
    contact_id  TEXT UNIQUE NOT NULL,
    full_name   TEXT,
    email       TEXT,
    phone       TEXT,
    title       TEXT,
    sk_account  INT REFERENCES gold.dim_account(sk_account)
);

INSERT INTO gold.dim_contact (contact_id, full_name, email, phone, title, sk_account)
SELECT ct.contact_id, ct.first_name || ' ' || ct.last_name, ct.email, ct.phone, ct.title, a.sk_account
FROM staging.crm_contacts ct
LEFT JOIN gold.dim_account a ON a.account_id = ct.account_id
ON CONFLICT (contact_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.dim_lead (
    sk_lead     SERIAL PRIMARY KEY,
    lead_id     TEXT UNIQUE NOT NULL,
    full_name   TEXT,
    email       TEXT,
    source      TEXT,
    status      TEXT,
    score       NUMERIC,
    created_at  TIMESTAMP
);

INSERT INTO gold.dim_lead (lead_id, full_name, email, source, status, score, created_at)
SELECT lead_id, first_name || ' ' || last_name, email, source, status, score, created_at
FROM staging.crm_leads
ON CONFLICT (lead_id) DO NOTHING;
