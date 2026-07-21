-- KPIs de negocio — crm

CREATE OR REPLACE VIEW gold.vw_win_rate AS
SELECT
    COUNT(*) FILTER (WHERE stage = 'won') AS won_count,
    COUNT(*) FILTER (WHERE stage = 'lost') AS lost_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE stage = 'won')
        / NULLIF(COUNT(*) FILTER (WHERE stage IN ('won', 'lost')), 0), 1
    ) AS win_rate_pct
FROM gold.fact_opportunities;


CREATE OR REPLACE VIEW gold.vw_pipeline_value AS
SELECT
    stage,
    COUNT(*) AS opportunity_count,
    SUM(amount) AS total_amount
FROM gold.fact_opportunities
WHERE stage NOT IN ('won', 'lost')
GROUP BY stage
ORDER BY total_amount DESC;


CREATE OR REPLACE VIEW gold.vw_revenue_by_account_profile AS
SELECT
    a.industry,
    a.country,
    SUM(o.amount) FILTER (WHERE o.stage = 'won') AS won_revenue,
    COUNT(*) FILTER (WHERE o.stage = 'won') AS won_count
FROM gold.fact_opportunities o
JOIN gold.dim_account a ON a.sk_account = o.sk_account
GROUP BY a.industry, a.country
ORDER BY won_revenue DESC NULLS LAST;


-- Duración del ciclo de venta.
-- IMPORTANTE: se calcula solo sobre oportunidades donde close_date >= created_at
-- (65.7% del total). El 34.3% restante quedó excluido porque close_date es,
-- según lo investigado en discovery, una fecha objetivo/planificada y no un
-- evento posterior real -- incluirlas daría duraciones negativas sin sentido.
-- Ver docs/decisiones.md, sección de discovery, para el detalle completo.
CREATE OR REPLACE VIEW gold.vw_sales_cycle_duration AS
SELECT
    ROUND(AVG(dc.full_date - do_.full_date), 1) AS avg_days_to_close,
    COUNT(*) AS opportunities_included,
    (SELECT COUNT(*) FROM gold.fact_opportunities) AS opportunities_total,
    ROUND(
        100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM gold.fact_opportunities), 0), 1
    ) AS pct_included
FROM gold.fact_opportunities o
JOIN gold.dim_date do_ ON do_.sk_date = o.sk_date
JOIN gold.dim_date dc ON dc.full_date = o.close_date
WHERE o.close_date >= do_.full_date;


CREATE OR REPLACE VIEW gold.vw_activities_by_outcome AS
SELECT
    o.stage,
    COUNT(act.activity_id) AS total_activities,
    COUNT(DISTINCT act.opportunity_id) AS opportunities_with_activity,
    ROUND(COUNT(act.activity_id)::NUMERIC / NULLIF(COUNT(DISTINCT act.opportunity_id), 0), 1) AS avg_activities_per_opportunity
FROM gold.fact_opportunities o
LEFT JOIN gold.fact_activities act ON act.opportunity_id = o.opportunity_id
GROUP BY o.stage
ORDER BY avg_activities_per_opportunity DESC NULLS LAST;
