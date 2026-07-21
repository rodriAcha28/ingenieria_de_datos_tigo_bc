-- KPIs de negocio — billing

CREATE OR REPLACE VIEW gold.vw_revenue_by_product AS
SELECT
    p.category,
    p.name AS product_name,
    SUM(ii.line_total) AS total_revenue,
    SUM(ii.quantity) AS total_quantity
FROM gold.fact_invoice_items ii
JOIN gold.dim_product p ON p.sk_product = ii.sk_product
GROUP BY p.category, p.name
ORDER BY total_revenue DESC;


CREATE OR REPLACE VIEW gold.vw_revenue_by_segment AS
SELECT
    c.segment,
    SUM(i.total) AS total_invoiced,
    COUNT(DISTINCT i.sk_customer) AS distinct_customers
FROM gold.fact_invoices i
JOIN gold.dim_customer c ON c.sk_customer = i.sk_customer
GROUP BY c.segment
ORDER BY total_invoiced DESC;


CREATE OR REPLACE VIEW gold.vw_collection_rate AS
SELECT
    ROUND(SUM(pay.amount), 2) AS total_collected,
    ROUND(SUM(inv.total), 2) AS total_invoiced,
    ROUND(100.0 * SUM(pay.amount) / NULLIF(SUM(inv.total), 0), 1) AS collection_rate_pct
FROM gold.fact_invoices inv
LEFT JOIN gold.fact_payments pay ON pay.invoice_id = inv.invoice_id;


CREATE OR REPLACE VIEW gold.vw_avg_days_to_pay AS
SELECT
    ROUND(AVG(dd.full_date - di.full_date), 1) AS avg_days_to_pay
FROM gold.fact_payments pay
JOIN gold.fact_invoices inv ON inv.invoice_id = pay.invoice_id
JOIN gold.dim_date di ON di.sk_date = inv.sk_date
JOIN gold.dim_date dd ON dd.sk_date = pay.sk_date;


-- Suscripciones activas vs finalizadas.
-- IMPORTANTE: el churn se calcula por status = 'cancelled', NO por
-- presencia de end_date. Se verificó que end_date está poblada incluso en
-- suscripciones con status='active' (fecha de fin de contrato planificada,
-- no un indicador de cancelación real) -- ver docs/decisiones.md.
CREATE OR REPLACE VIEW gold.vw_subscription_churn AS
SELECT
    COUNT(*) AS total_subscriptions,
    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_subscriptions,
    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_subscriptions,
    SUM(CASE WHEN status = 'paused' THEN 1 ELSE 0 END) AS paused_subscriptions,
    ROUND(100.0 * SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_rate_pct
FROM gold.fact_subscriptions;


-- Nota de calidad de datos: 783 de 15,000 suscripciones (5.22%) tienen
-- end_date anterior a start_date. Se muestra el impacto, no se excluyen
-- del resto de los KPIs de este archivo.
CREATE OR REPLACE VIEW gold.vw_data_quality_subscriptions AS
SELECT
    COUNT(*) AS total_subscriptions,
    SUM(CASE WHEN NOT valid_date_range THEN 1 ELSE 0 END) AS invalid_range_count,
    ROUND(100.0 * SUM(CASE WHEN NOT valid_date_range THEN 1 ELSE 0 END) / COUNT(*), 2) AS invalid_range_pct
FROM gold.fact_subscriptions;
