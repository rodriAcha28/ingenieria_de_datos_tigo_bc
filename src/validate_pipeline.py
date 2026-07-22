
import os
from pathlib import Path

import pandas as pd
import psycopg2

# Mapeo tabla de origen -> tabla en Gold (los nombres no son 1:1 porque
# Gold usa convención dim_/fact_ en vez del nombre original de la tabla)
SOURCE_TO_GOLD = {
    "university_professors": "dim_professor",
    "university_courses": "dim_course",
    "university_semesters": "dim_semester",
    "university_students": "dim_student",
    "university_enrollments": "fact_enrollments",
    "university_grades": "fact_grades",
    "billing_customers": "dim_customer",
    "billing_products": "dim_product",
    "billing_subscriptions": "fact_subscriptions",
    "billing_invoices": "fact_invoices",
    "billing_invoice_items": "fact_invoice_items",
    "billing_payments": "fact_payments",
    "crm_accounts": "dim_account",
    "crm_contacts": "dim_contact",
    "crm_leads": "dim_lead",
    "crm_opportunities": "fact_opportunities",
    "crm_opportunity_contacts": "bridge_opportunity_contacts",
    "crm_activities": "fact_activities",
}

# Tablas donde una diferencia de conteo entre capas es esperada y ya está
# documentada -- no se marcan como hallazgo si difieren.
EXPECTED_DIFFERENCES = {
    "crm_opportunity_contacts": (
        "Silver descarta filas sin opportunity_id o contact_id completos "
        "(ver docs/decisiones.md, sección 4.3)."
    ),
}


def get_pg_connection():
    return psycopg2.connect(
        host=os.environ.get("WAREHOUSE_HOST", "localhost"),
        port=os.environ.get("WAREHOUSE_PORT", "5432"),
        dbname=os.environ.get("WAREHOUSE_DB", "warehouse"),
        user=os.environ.get("WAREHOUSE_USER", "rodrick"),
        password=os.environ.get("WAREHOUSE_PASSWORD", "rodrick123"),
    )


def count_raw(raw_path, domain, table):
    csv_file = raw_path / domain / f"{table}.csv"
    if not csv_file.exists():
        return None
    return len(pd.read_csv(csv_file, dtype=str))


def count_parquet(base_path, domain, table):
    pq_file = base_path / domain / f"{table}.parquet"
    if not pq_file.exists():
        return None
    return len(pd.read_parquet(pq_file))


def count_postgres_table(conn, schema, table):
    with conn.cursor() as cur:
        try:
            cur.execute(f'SELECT COUNT(*) FROM {schema}."{table}"')
            return cur.fetchone()[0]
        except Exception:
            conn.rollback()
            return None


def main():
    raw_path = Path(os.environ.get("RAW_DATA_PATH", "/opt/airflow/data/raw"))
    bronze_path = Path(os.environ.get("BRONZE_DATA_PATH", "/opt/airflow/data/bronze"))
    silver_path = Path(os.environ.get("SILVER_DATA_PATH", "/opt/airflow/data/silver"))

    conn = get_pg_connection()

    rows = []
    for source_table, gold_table in SOURCE_TO_GOLD.items():
        domain, table = source_table.split("_", 1)

        raw_n = count_raw(raw_path, domain, table)
        bronze_n = count_parquet(bronze_path, domain, table)
        silver_n = count_parquet(silver_path, domain, table)
        staging_n = count_postgres_table(conn, "staging", source_table)
        gold_n = count_postgres_table(conn, "gold", gold_table)

        counts = [c for c in [raw_n, bronze_n, silver_n, staging_n, gold_n] if c is not None]
        all_equal = len(set(counts)) <= 1
        is_expected = source_table in EXPECTED_DIFFERENCES

        status = "OK" if all_equal else ("ESPERADO" if is_expected else "REVISAR")

        rows.append({
            "tabla": source_table,
            "raw": raw_n, "bronze": bronze_n, "silver": silver_n,
            "staging": staging_n, "gold": gold_n,
            "estado": status,
        })

    conn.close()

    df = pd.DataFrame(rows)
    pd.set_option("display.width", 140)
    print(df.to_string(index=False))

    problems = df[df["estado"] == "REVISAR"]
    print(f"\nTotal tablas revisadas: {len(df)}")
    print(f"OK: {(df['estado'] == 'OK').sum()}  |  "
          f"Esperado (documentado): {(df['estado'] == 'ESPERADO').sum()}  |  "
          f"A revisar: {len(problems)}")

    if len(problems) > 0:
        print("\n⚠ Tablas con diferencias NO documentadas -- revisar manualmente:")
        print(problems.to_string(index=False))
        raise SystemExit(1)

    print("\n✅ Validación del pipeline completada sin hallazgos pendientes.")


if __name__ == "__main__":
    main()
