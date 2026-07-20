-- dim_date: dimensión de calendario compartida por las tres estrellas
-- (university, billing, crm). Es la única dimensión transversal a los tres
-- dominios -- no representa una entidad de negocio, solo el calendario,
-- por lo que compartirla no contradice el hallazgo de que los tres dominios
-- son poblaciones de negocio independientes (ver docs/decisiones.md).
--
-- sk_date usa el patrón YYYYMMDD como entero (ej. 2023-11-30 -> 20231130).
-- Es una convención estándar de Kimball: permite que los hechos calculen su
-- propia sk_date sin necesidad de un JOIN (TO_CHAR(fecha, 'YYYYMMDD')::INT),
-- y sigue siendo una llave interpretable a simple vista.

CREATE TABLE IF NOT EXISTS gold.dim_date (
    sk_date      INT PRIMARY KEY,
    full_date    DATE UNIQUE NOT NULL,
    year         INT,
    month        INT,
    month_name   TEXT,
    quarter      INT,
    day          INT,
    day_of_week  INT,
    day_name     TEXT
);

-- Rango amplio para cubrir fechas de nacimiento, contratación de profesores,
-- y proyecciones de close_date que llegan hasta 2026 (visto en discovery).
INSERT INTO gold.dim_date (sk_date, full_date, year, month, month_name, quarter, day, day_of_week, day_name)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT AS sk_date,
    d::DATE AS full_date,
    EXTRACT(YEAR FROM d)::INT,
    EXTRACT(MONTH FROM d)::INT,
    TRIM(TO_CHAR(d, 'Month')),
    EXTRACT(QUARTER FROM d)::INT,
    EXTRACT(DAY FROM d)::INT,
    EXTRACT(ISODOW FROM d)::INT,
    TRIM(TO_CHAR(d, 'Day'))
FROM generate_series('1970-01-01'::date, '2030-12-31'::date, interval '1 day') AS d
ON CONFLICT (full_date) DO NOTHING;
