
import os
from pathlib import Path

import pandas as pd
import psycopg2


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("WAREHOUSE_HOST", "localhost"),
        port=os.environ.get("WAREHOUSE_PORT", "5432"),
        dbname=os.environ.get("WAREHOUSE_DB", "warehouse"),
        user=os.environ.get("WAREHOUSE_USER", "rodrick"),
        password=os.environ.get("WAREHOUSE_PASSWORD", "rodrick123"),
    )


def main():
    out_path = Path(os.environ.get("GOLD_PARQUET_PATH", "/opt/airflow/data/parquet/gold"))
    out_path.mkdir(parents=True, exist_ok=True)

    conn = get_connection()

    tables = pd.read_sql("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'gold' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """, conn)["table_name"].tolist()

    total = 0
    for table_name in tables:
        df = pd.read_sql(f'SELECT * FROM gold."{table_name}"', conn)
        out_file = out_path / f"{table_name}.parquet"
        df.to_parquet(out_file, index=False, engine="pyarrow")
        print(f"  gold/{table_name:<28} {len(df):>8} filas -> {out_file}")
        total += len(df)

    conn.close()
    print(f"\nListo. {len(tables)} tablas, {total} filas exportadas a Parquet.")


if __name__ == "__main__":
    main()
