
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


def main():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Conexión OK.\n")

    raw_path = Path("/opt/airflow/data/raw")  

    total = 0
    for domain in DOMAINS:
        domain_path = raw_path / domain
        if not domain_path.exists():
            print(f"[aviso] no existe {domain_path}, se omite")
            continue

        for csv_file in sorted(domain_path.glob("*.csv")):
            table_name = f"{domain}_{csv_file.stem}"
            df = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_values=[""])
            df["_source_file"] = csv_file.name
            df["_source_domain"] = domain
            df["_ingested_at"] = datetime.now(timezone.utc).isoformat()

            df.to_sql(table_name, engine, schema="bronze", if_exists="replace", index=False)
            print(f"  bronze.{table_name:<30} {len(df):>8} filas")
            total += len(df)

    print(f"\nListo. {total} filas cargadas en total.")


if __name__ == "__main__":
    main()