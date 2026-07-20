"""
Carga los Parquet de Silver a Postgres, en el schema `staging`.

Esto existe porque Silver vive en Parquet (decisión de arquitectura) pero
Gold vive en Postgres (decisión del ingeniero encargado). `staging` es el
puente entre ambos: una copia 1:1 de Silver, sin transformación adicional,
que el SQL de sql/gold/ usa como fuente para construir dimensiones y hechos.

No confundir con Bronze: staging no tiene metadatos de linaje, es solo un
espejo de Silver dentro de Postgres para poder usar SQL en la capa Gold.
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

DOMAINS = ["university", "billing", "crm"]


def get_engine():
    host = os.environ.get("WAREHOUSE_HOST", "localhost")
    port = os.environ.get("WAREHOUSE_PORT", "5432")
    db = os.environ.get("WAREHOUSE_DB", "warehouse")
    user = os.environ.get("WAREHOUSE_USER", "rodrick")
    password = os.environ.get("WAREHOUSE_PASSWORD", "rodrick123")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def main():
    silver_path = Path(os.environ.get("SILVER_DATA_PATH", "/opt/airflow/data/silver"))
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))

    total = 0
    for domain in DOMAINS:
        domain_path = silver_path / domain
        if not domain_path.exists():
            print(f"[aviso] no existe {domain_path}, se omite")
            continue

        for pq_file in sorted(domain_path.glob("*.parquet")):
            table_name = f"{domain}_{pq_file.stem}"
            df = pd.read_parquet(pq_file)
            df.to_sql(table_name, engine, schema="staging", if_exists="replace", index=False)
            print(f"  staging.{table_name:<28} {len(df):>8} filas")
            total += len(df)

    print(f"\nListo. {total} filas cargadas a staging.")


if __name__ == "__main__":
    main()
