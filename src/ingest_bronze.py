
import os
import csv
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DOMAINS = ["university", "billing", "crm"]


def log_ingestion(log_path, domain, file_name, rows):
    """Registra cada archivo ingestado en un CSV de control, para auditoría.
    Reemplaza a la tabla bronze._ingestion_log de la versión anterior (Postgres)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_path.exists()
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["domain", "file_name", "rows", "ingested_at"])
        writer.writerow([domain, file_name, rows, datetime.now(timezone.utc).isoformat()])


def main():
    raw_path = Path(os.environ.get("RAW_DATA_PATH", "/opt/airflow/data/raw"))
    bronze_path = Path(os.environ.get("BRONZE_DATA_PATH", "/opt/airflow/data/bronze"))
    log_path = bronze_path / "_control" / "ingestion_log.csv"

    total = 0
    for domain in DOMAINS:
        domain_path = raw_path / domain
        if not domain_path.exists():
            print(f"[aviso] no existe {domain_path}, se omite")
            continue

        out_dir = bronze_path / domain
        out_dir.mkdir(parents=True, exist_ok=True)

        for csv_file in sorted(domain_path.glob("*.csv")):
            table_name = csv_file.stem

            try:
                df = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_values=[""])
            except Exception as e:
                print(f"  [ERROR] no se pudo leer {csv_file.name}: {e}")
                continue

            df["_source_file"] = csv_file.name
            df["_source_domain"] = domain
            df["_ingested_at"] = datetime.now(timezone.utc).isoformat()

            out_file = out_dir / f"{table_name}.parquet"
            df.to_parquet(out_file, index=False, engine="pyarrow")
            log_ingestion(log_path, domain, csv_file.name, len(df))

            print(f"  bronze/{domain}/{table_name:<25} {len(df):>8} filas -> {out_file}")
            total += len(df)

    print(f"\nListo. {total} filas cargadas en total.")


if __name__ == "__main__":
    main()
