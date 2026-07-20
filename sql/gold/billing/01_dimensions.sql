-- Dimensiones de la estrella `billing`.

CREATE TABLE IF NOT EXISTS gold.dim_customer (
    sk_customer   SERIAL PRIMARY KEY,
    customer_id   TEXT UNIQUE NOT NULL,
    external_ref  TEXT,  -- 50% nulo, sin patrón detectado (ver docs/decisiones.md); se conserva tal cual
    full_name     TEXT,
    email         TEXT,
    country       TEXT,
    segment       TEXT,
    created_at    TIMESTAMP
);

INSERT INTO gold.dim_customer (customer_id, external_ref, full_name, email, country, segment, created_at)
SELECT customer_id, external_ref, first_name || ' ' || last_name, email, country, segment, created_at
FROM staging.billing_customers
ON CONFLICT (customer_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.dim_product (
    sk_product     SERIAL PRIMARY KEY,
    product_id     TEXT UNIQUE NOT NULL,
    sku            TEXT,
    name           TEXT,
    category       TEXT,
    monthly_price  NUMERIC,
    active         BOOLEAN
);

INSERT INTO gold.dim_product (product_id, sku, name, category, monthly_price, active)
SELECT product_id, sku, name, category, monthly_price, active
FROM staging.billing_products
ON CONFLICT (product_id) DO NOTHING;
