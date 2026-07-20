-- Schemas necesarios para la capa Gold.
-- staging: espejo de Silver dentro de Postgres (poblado por src/load_staging.py)
-- gold: modelo dimensional final (Star Schema)

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS gold;
