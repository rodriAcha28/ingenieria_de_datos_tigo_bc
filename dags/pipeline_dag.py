"""
DAG del pipeline completo: CSV -> Bronze -> Silver -> staging -> Gold -> KPIs.

Estructura:
  ingest_bronze >> transform_silver >> load_staging >> gold_schema_and_date
      >> [gold_university, gold_billing, gold_crm]  (en paralelo)

Cada rama de dominio (university/billing/crm) corre dimensiones -> hechos ->
KPIs de ese dominio. Las tres ramas son independientes entre sí porque los
tres dominios de negocio no comparten datos (ver docs/decisiones.md,
sección de discovery) -- no hay razón para que una rama espere a otra.

Los scripts de ingesta y transformación (Bronze/Silver) procesan los tres
dominios en una sola corrida cada uno (no se paralelizan a nivel de tarea),
porque ya son rápidos para este volumen de datos y partirlos agregaría
complejidad sin beneficio real. Donde sí vale la pena paralelizar es en
Gold, porque cada dominio implica varias sentencias SQL secuenciales.
"""

from datetime import datetime

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

SQL_BASE_PATH = "/opt/airflow/sql/gold"


def get_pg_connection():
    import os
    return psycopg2.connect(
        host=os.environ.get("WAREHOUSE_HOST", "postgres-warehouse"),
        port=os.environ.get("WAREHOUSE_PORT", "5432"),
        dbname=os.environ.get("WAREHOUSE_DB", "warehouse"),
        user=os.environ.get("WAREHOUSE_USER", "rodrick"),
        password=os.environ.get("WAREHOUSE_PASSWORD", "rodrick123"),
    )


def run_sql_file(relative_path):
    """Ejecuta un archivo .sql completo (puede tener varias sentencias)
    contra el warehouse. relative_path es relativo a sql/gold/."""
    full_path = f"{SQL_BASE_PATH}/{relative_path}"
    with open(full_path) as f:
        sql = f.read()

    conn = get_pg_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"Ejecutado OK: {relative_path}")


def ingest_bronze_task():
    import sys
    sys.path.insert(0, "/opt/airflow/src")
    import ingest_bronze
    ingest_bronze.main()


def transform_silver_task():
    import sys
    sys.path.insert(0, "/opt/airflow/src")
    import transform_silver
    transform_silver.main()


def load_staging_task():
    import sys
    sys.path.insert(0, "/opt/airflow/src")
    import load_staging
    load_staging.main()


default_args = {
    "owner": "rodrick",
    "retries": 1,
}

with DAG(
    dag_id="pipeline_completo",
    description="CSV -> Bronze -> Silver -> staging -> Gold -> KPIs",
    default_args=default_args,
    schedule=None,       # disparo manual; cambiar a un cron si se necesita programado
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["bootcamp", "pipeline"],
) as dag:

    ingest_bronze = PythonOperator(
        task_id="ingest_bronze",
        python_callable=ingest_bronze_task,
    )

    transform_silver = PythonOperator(
        task_id="transform_silver",
        python_callable=transform_silver_task,
    )

    load_staging = PythonOperator(
        task_id="load_staging",
        python_callable=load_staging_task,
    )

    gold_schema_and_date = PythonOperator(
        task_id="gold_schema_and_date",
        python_callable=lambda: [
            run_sql_file("00_create_schema.sql"),
            run_sql_file("01_dim_date.sql"),
        ],
    )

    # --- Rama university ---
    with TaskGroup("gold_university") as gold_university:
        dims = PythonOperator(
            task_id="dimensions",
            python_callable=lambda: run_sql_file("university/01_dimensions.sql"),
        )
        facts = PythonOperator(
            task_id="facts",
            python_callable=lambda: run_sql_file("university/02_facts.sql"),
        )
        kpis = PythonOperator(
            task_id="kpis",
            python_callable=lambda: run_sql_file("kpis/01_university_kpis.sql"),
        )
        dims >> facts >> kpis

    # --- Rama billing ---
    with TaskGroup("gold_billing") as gold_billing:
        dims = PythonOperator(
            task_id="dimensions",
            python_callable=lambda: run_sql_file("billing/01_dimensions.sql"),
        )
        facts = PythonOperator(
            task_id="facts",
            python_callable=lambda: run_sql_file("billing/02_facts.sql"),
        )
        kpis = PythonOperator(
            task_id="kpis",
            python_callable=lambda: run_sql_file("kpis/02_billing_kpis.sql"),
        )
        dims >> facts >> kpis

    # --- Rama crm ---
    with TaskGroup("gold_crm") as gold_crm:
        dims = PythonOperator(
            task_id="dimensions",
            python_callable=lambda: run_sql_file("crm/01_dimensions.sql"),
        )
        facts = PythonOperator(
            task_id="facts",
            python_callable=lambda: run_sql_file("crm/02_facts.sql"),
        )
        kpis = PythonOperator(
            task_id="kpis",
            python_callable=lambda: run_sql_file("kpis/03_crm_kpis.sql"),
        )
        dims >> facts >> kpis

    ingest_bronze >> transform_silver >> load_staging >> gold_schema_and_date
    gold_schema_and_date >> [gold_university, gold_billing, gold_crm]
