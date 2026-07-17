
import os
from datetime import datetime, timezone
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


def log_ingestion(engine, domain, file_name, rows):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bronze._ingestion_log (
                id SERIAL PRIMARY KEY,
                domain TEXT,
                file_name TEXT,
                rows INTEGER,
                ingested_at TIMESTAMPTZ
            )
        """))
        conn.execute(text("""
            INSERT INTO bronze._ingestion_log (domain, file_name, rows, ingested_at)
            VALUES (:domain, :file_name, :rows, :ingested_at)
        """), {
            "domain": domain,
            "file_name": file_name,
            "rows": rows,
            "ingested_at": datetime.now(timezone.utc)
        })


def main():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Conexión OK.\n")

    raw_path = Path(os.environ.get("RAW_DATA_PATH", "/opt/airflow/data/raw"))

    total = 0
    for domain in DOMAINS:
        domain_path = raw_path / domain
        if not domain_path.exists():
            print(f"[aviso] no existe {domain_path}, se omite")
            continue

        for csv_file in sorted(domain_path.glob("*.csv")):
            table_name = f"{domain}_{csv_file.stem}"

            try:
                df = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_values=[""])
            except Exception as e:
                print(f"  [ERROR] no se pudo leer {csv_file.name}: {e}")
                continue

            df["_source_file"] = csv_file.name
            df["_source_domain"] = domain
            df["_ingested_at"] = datetime.now(timezone.utc).isoformat()

            df.to_sql(table_name, engine, schema="bronze", if_exists="replace", index=False)
            log_ingestion(engine, domain, csv_file.name, len(df))
            print(f"  bronze.{table_name:<30} {len(df):>8} filas")
            total += len(df)

    print(f"\nListo. {total} filas cargadas en total.")


if __name__ == "__main__":
    main()