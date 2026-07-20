-- Hechos de la estrella `billing`.
-- Orden: fact_invoices antes que fact_invoice_items y fact_payments,
-- que denormalizan sk_customer desde ahí.

CREATE TABLE IF NOT EXISTS gold.fact_invoices (
    invoice_id   TEXT PRIMARY KEY,
    sk_customer  INT REFERENCES gold.dim_customer(sk_customer),
    sk_date      INT REFERENCES gold.dim_date(sk_date),  -- issued_at
    due_date     DATE,
    status       TEXT,
    currency     TEXT,
    total        NUMERIC
);

-- due_at >= issued_at se validó 100% consistente en discovery: sin flag necesario.
INSERT INTO gold.fact_invoices (invoice_id, sk_customer, sk_date, due_date, status, currency, total)
SELECT
    i.invoice_id,
    c.sk_customer,
    TO_CHAR(i.issued_at, 'YYYYMMDD')::INT,
    i.due_at::DATE,
    i.status,
    i.currency,
    i.total
FROM staging.billing_invoices i
JOIN gold.dim_customer c ON c.customer_id = i.customer_id
ON CONFLICT (invoice_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.fact_invoice_items (
    invoice_item_id  TEXT PRIMARY KEY,
    invoice_id       TEXT,  -- trazabilidad
    sk_customer      INT REFERENCES gold.dim_customer(sk_customer),
    sk_product       INT REFERENCES gold.dim_product(sk_product),
    quantity         NUMERIC,
    unit_price       NUMERIC,
    line_total       NUMERIC
);

INSERT INTO gold.fact_invoice_items (invoice_item_id, invoice_id, sk_customer, sk_product, quantity, unit_price, line_total)
SELECT
    ii.invoice_item_id,
    ii.invoice_id,
    fi.sk_customer,
    p.sk_product,
    ii.quantity,
    ii.unit_price,
    ii.line_total
FROM staging.billing_invoice_items ii
JOIN gold.fact_invoices fi ON fi.invoice_id = ii.invoice_id
JOIN gold.dim_product   p  ON p.product_id  = ii.product_id
ON CONFLICT (invoice_item_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.fact_payments (
    payment_id   TEXT PRIMARY KEY,
    invoice_id   TEXT,  -- trazabilidad
    sk_customer  INT REFERENCES gold.dim_customer(sk_customer),
    sk_date      INT REFERENCES gold.dim_date(sk_date),  -- paid_at
    amount       NUMERIC,
    method       TEXT
);

-- paid_at >= issued_at se validó 100% consistente en discovery.
INSERT INTO gold.fact_payments (payment_id, invoice_id, sk_customer, sk_date, amount, method)
SELECT
    pay.payment_id,
    pay.invoice_id,
    fi.sk_customer,
    TO_CHAR(pay.paid_at, 'YYYYMMDD')::INT,
    pay.amount,
    pay.method
FROM staging.billing_payments pay
JOIN gold.fact_invoices fi ON fi.invoice_id = pay.invoice_id
ON CONFLICT (payment_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.fact_subscriptions (
    subscription_id    TEXT PRIMARY KEY,
    sk_customer         INT REFERENCES gold.dim_customer(sk_customer),
    sk_product           INT REFERENCES gold.dim_product(sk_product),
    sk_date              INT REFERENCES gold.dim_date(sk_date),  -- start_date
    end_date             DATE,
    status               TEXT,
    duration_days         INT,
    valid_date_range      BOOLEAN  -- ver hallazgo discovery: 783/15000 (5.22%) con end_date < start_date
);

INSERT INTO gold.fact_subscriptions (subscription_id, sk_customer, sk_product, sk_date, end_date, status, duration_days, valid_date_range)
SELECT
    s.subscription_id,
    c.sk_customer,
    p.sk_product,
    TO_CHAR(s.start_date, 'YYYYMMDD')::INT,
    s.end_date,
    s.status,
    CASE WHEN s.end_date IS NOT NULL THEN (s.end_date::DATE - s.start_date::DATE) ELSE NULL END,
    s._valid_date_range
FROM staging.billing_subscriptions s
JOIN gold.dim_customer c ON c.customer_id = s.customer_id
JOIN gold.dim_product  p ON p.product_id  = s.product_id
ON CONFLICT (subscription_id) DO NOTHING;
