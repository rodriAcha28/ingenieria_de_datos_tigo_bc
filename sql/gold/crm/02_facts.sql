-- Hechos de la estrella `crm`.
-- fact_opportunities primero: fact_activities y bridge_opportunity_contacts
-- referencian su llave natural (opportunity_id) como FK de fact-a-fact.

CREATE TABLE IF NOT EXISTS gold.fact_opportunities (
    opportunity_id  TEXT PRIMARY KEY,
    sk_account      INT REFERENCES gold.dim_account(sk_account),
    sk_date         INT REFERENCES gold.dim_date(sk_date),  -- created_at
    close_date      DATE,
    stage           TEXT,
    amount          NUMERIC
);

-- close_date < created_at ocurre en 34.3% de los casos (discovery). Se determinó
-- que close_date es probablemente una fecha objetivo/planificada, no un evento
-- posterior obligatorio -- no se filtra ni se marca nada, se carga todo.
INSERT INTO gold.fact_opportunities (opportunity_id, sk_account, sk_date, close_date, stage, amount)
SELECT
    o.opportunity_id,
    a.sk_account,
    TO_CHAR(o.created_at, 'YYYYMMDD')::INT,
    o.close_date::DATE,
    o.stage,
    o.amount
FROM staging.crm_opportunities o
JOIN gold.dim_account a ON a.account_id = o.account_id
ON CONFLICT (opportunity_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.fact_activities (
    activity_id     TEXT PRIMARY KEY,
    sk_contact      INT REFERENCES gold.dim_contact(sk_contact),      -- nullable: relación opcional
    opportunity_id  TEXT REFERENCES gold.fact_opportunities(opportunity_id),  -- nullable: relación opcional
    sk_date         INT REFERENCES gold.dim_date(sk_date),
    type            TEXT,
    subject         TEXT
);

-- contact_id / opportunity_id nulos son válidos por diseño (confirmado en
-- discovery: una actividad puede relacionarse solo con uno de los dos).
-- occurred_at anterior al created_at de la oportunidad (18.96% en discovery)
-- es plausible de negocio (prospección antes de crear la oportunidad
-- formalmente) -- no se filtra ni se marca.
INSERT INTO gold.fact_activities (activity_id, sk_contact, opportunity_id, sk_date, type, subject)
SELECT
    act.activity_id,
    ct.sk_contact,
    CASE
        WHEN EXISTS (SELECT 1 FROM gold.fact_opportunities fo WHERE fo.opportunity_id = act.opportunity_id)
        THEN act.opportunity_id
        ELSE NULL
    END,
    TO_CHAR(act.occurred_at, 'YYYYMMDD')::INT,
    act.type,
    act.subject
FROM staging.crm_activities act
LEFT JOIN gold.dim_contact ct ON ct.contact_id = act.contact_id
ON CONFLICT (activity_id) DO NOTHING;


-- Tabla puente N:N (factless fact -- registra la relación, no una métrica numérica)
CREATE TABLE IF NOT EXISTS gold.bridge_opportunity_contacts (
    opportunity_id  TEXT REFERENCES gold.fact_opportunities(opportunity_id),
    sk_contact      INT REFERENCES gold.dim_contact(sk_contact),
    role            TEXT,
    PRIMARY KEY (opportunity_id, sk_contact)
);

INSERT INTO gold.bridge_opportunity_contacts (opportunity_id, sk_contact, role)
SELECT oc.opportunity_id, ct.sk_contact, oc.role
FROM staging.crm_opportunity_contacts oc
JOIN gold.dim_contact       ct ON ct.contact_id      = oc.contact_id
JOIN gold.fact_opportunities fo ON fo.opportunity_id = oc.opportunity_id
ON CONFLICT (opportunity_id, sk_contact) DO NOTHING;
