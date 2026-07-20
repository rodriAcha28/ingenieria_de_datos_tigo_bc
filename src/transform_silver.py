"""
Silver — limpieza, tipado y estandarización de las 18 tablas de Bronze (Parquet).

Reglas aplicadas aquí provienen directamente del notebook de discovery
(notebooks/01_discovery_profiling.ipynb). Cada decisión está documentada
también en docs/decisiones.md.

Principios generales:
  - Nunca se borra una fila solo porque "se ve rara": se marca con una columna
    de calidad (_valid_*) y se documenta el % afectado. El análisis de negocio
    decide luego si excluye esas filas o no.
  - Los metadatos de linaje de Bronze (_source_file, _source_domain) no pasan
    a Silver; se reemplazan por un único _bronze_ingested_at para trazabilidad.
  - Tipos: fechas -> datetime, montos/números -> float, texto -> trim.
"""

import os
from pathlib import Path

import pandas as pd


# ---------- Helpers genéricos ----------

def read_bronze(bronze_path, domain, table_name):
    return pd.read_parquet(bronze_path / domain / f"{table_name}.parquet")


def write_silver(df, silver_path, domain, table_name):
    out_dir = silver_path / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / f"{table_name}.parquet", index=False, engine="pyarrow")
    print(f"  silver/{domain}/{table_name:<22} {len(df):>8} filas")


def base_clean(df, date_cols=None, text_cols=None, dedup_key=None):
    """Limpieza común a casi todas las tablas: tipar fechas, trim de texto,
    deduplicar por clave real, y renombrar el metadata de linaje."""
    df = df.copy()

    for col in (date_cols or []):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    for col in (text_cols or []):
        df[col] = df[col].astype(str).str.strip()

    if dedup_key:
        before = len(df)
        df = df.drop_duplicates(subset=dedup_key)
        removed = before - len(df)
        if removed:
            print(f"    [dedup] {removed} filas duplicadas eliminadas por {dedup_key}")

    df["_bronze_ingested_at"] = df["_ingested_at"]
    df = df.drop(columns=["_source_file", "_source_domain", "_ingested_at"])
    return df


# ---------- University ----------

def clean_semesters(df):
    df = base_clean(df, date_cols=["start_date", "end_date"], dedup_key=["semester_id"])
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    return df


def clean_professors(df):
    return base_clean(
        df,
        date_cols=["hired_at"],
        text_cols=["first_name", "last_name", "email", "department"],
        dedup_key=["professor_id"],
    )


def clean_students(df):
    df = base_clean(
        df,
        date_cols=["birth_date", "enrolled_at"],
        text_cols=["first_name", "last_name", "email", "country"],
        dedup_key=["student_id"],
    )
    # Hallazgo discovery: 636/5000 (12.72%) con edad implausible al inscribirse (<15 años).
    # No se elimina la fila -- se marca para que el análisis decida si la incluye.
    age_at_enroll = (df["enrolled_at"] - df["birth_date"]).dt.days / 365.25
    df["_age_at_enroll"] = age_at_enroll
    df["_valid_age"] = age_at_enroll.between(15, 90)
    return df


def clean_courses(df):
    df = base_clean(
        df, text_cols=["code", "name", "department"], dedup_key=["course_id"]
    )
    df["credits"] = pd.to_numeric(df["credits"], errors="coerce").astype("Int64")
    return df


def clean_enrollments(df):
    return base_clean(df, date_cols=["enrolled_at"], text_cols=["status"], dedup_key=["enrollment_id"])


def clean_grades(df):
    df = base_clean(df, date_cols=["graded_at"], text_cols=["assessment"], dedup_key=["grade_id"])
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    # Hallazgo discovery: 48.73% de graded_at < enrolled_at de la inscripción.
    # Se determinó que la regla original (graded_at >= enrolled_at) era un supuesto
    # incorrecto -- enrolled_at no representa "inicio de clases". No se marca como
    # inválido; se deja documentado en docs/decisiones.md como hallazgo sin acción.
    return df


# ---------- Billing ----------

def clean_customers(df):
    df = base_clean(
        df,
        date_cols=["created_at"],
        text_cols=["first_name", "last_name", "email", "country", "segment"],
        dedup_key=["customer_id"],
    )
    # Hallazgo discovery: external_ref es 50.0% nula, sin correlación con segment,
    # country ni created_at (verificado). No hay patrón de negocio detectable --
    # se conserva la columna tal cual, sin marcarla ni descartarla.
    return df


def clean_products(df):
    df = base_clean(df, text_cols=["sku", "name", "category"], dedup_key=["product_id"])
    df["monthly_price"] = pd.to_numeric(df["monthly_price"], errors="coerce")
    df["active"] = df["active"].astype(str).str.lower().isin(["true", "1", "t", "yes"])
    return df


def clean_subscriptions(df):
    df = base_clean(
        df, date_cols=["start_date", "end_date"], text_cols=["status"], dedup_key=["subscription_id"]
    )
    # Hallazgo discovery: 783/15000 (5.22%) con end_date < start_date -- error real
    # de captura (volumen bajo, no es un supuesto equivocado). Se marca, no se borra.
    has_end = df["end_date"].notna()
    df["_valid_date_range"] = ~has_end | (df["end_date"] >= df["start_date"])
    return df


def clean_invoices(df):
    df = base_clean(df, date_cols=["issued_at", "due_at"], text_cols=["status", "currency"], dedup_key=["invoice_id"])
    df["total"] = pd.to_numeric(df["total"], errors="coerce")
    # due_at >= issued_at se validó 100% consistente en discovery -- sin flag necesario.
    return df


def clean_invoice_items(df):
    df = base_clean(df, dedup_key=["invoice_item_id"])
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["line_total"] = pd.to_numeric(df["line_total"], errors="coerce")
    return df


def clean_payments(df):
    df = base_clean(df, date_cols=["paid_at"], text_cols=["method"], dedup_key=["payment_id"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    # paid_at >= issued_at (de la factura) se validó 100% consistente en discovery.
    return df


# ---------- CRM ----------

def clean_accounts(df):
    df = base_clean(
        df, date_cols=["created_at"], text_cols=["name", "industry", "country"], dedup_key=["account_id"]
    )
    df["annual_revenue"] = pd.to_numeric(df["annual_revenue"], errors="coerce")
    df["employees"] = pd.to_numeric(df["employees"], errors="coerce")
    return df


def clean_contacts(df):
    return base_clean(
        df,
        date_cols=["created_at"],
        text_cols=["first_name", "last_name", "email", "phone", "title"],
        dedup_key=["contact_id"],
    )


def clean_leads(df):
    df = base_clean(
        df,
        date_cols=["created_at"],
        text_cols=["first_name", "last_name", "email", "source", "status"],
        dedup_key=["lead_id"],
    )
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    # Tabla sin FK a otros dominios (confirmado en discovery) -- se mantiene aislada.
    return df


def clean_opportunities(df):
    df = base_clean(
        df, date_cols=["created_at", "close_date"], text_cols=["name", "stage"], dedup_key=["opportunity_id"]
    )
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    # Hallazgo discovery: 34.3% con close_date < created_at. Se determinó que la
    # regla asumida (close_date como evento posterior) era incorrecta -- close_date
    # probablemente es una fecha objetivo/planificada, no un evento posterior
    # obligatorio. No se marca como inválido; documentado en docs/decisiones.md.
    return df


def clean_opportunity_contacts(df):
    before = len(df)
    # Tabla puente N:N -- una fila sin alguna de las dos FK no conecta nada
    # y no aporta información relacional válida (regla definida en discovery).
    df = df[df["opportunity_id"].notna() & df["contact_id"].notna()].copy()
    removed = before - len(df)
    if removed:
        print(f"    [opportunity_contacts] {removed} filas sin FK completa, descartadas")
    return base_clean(df, text_cols=["role"], dedup_key=["opportunity_id", "contact_id"])


def clean_activities(df):
    df = base_clean(df, date_cols=["occurred_at"], text_cols=["type", "subject"])
    # contact_id / opportunity_id nulos son válidos aquí: una actividad puede
    # relacionarse solo con un contacto, o solo con una oportunidad (relación
    # opcional por diseño, confirmado en discovery -- no son llaves huérfanas).
    # Hallazgo discovery: 18.96% de occurred_at anterior al created_at de la
    # oportunidad relacionada. Es plausible de negocio (prospección antes de
    # crear formalmente la oportunidad) -- no se marca como inválido.
    return df


# ---------- Orquestación ----------

CLEANERS = {
    "university": {
        "semesters": clean_semesters,
        "professors": clean_professors,
        "students": clean_students,
        "courses": clean_courses,
        "enrollments": clean_enrollments,
        "grades": clean_grades,
    },
    "billing": {
        "customers": clean_customers,
        "products": clean_products,
        "subscriptions": clean_subscriptions,
        "invoices": clean_invoices,
        "invoice_items": clean_invoice_items,
        "payments": clean_payments,
    },
    "crm": {
        "accounts": clean_accounts,
        "contacts": clean_contacts,
        "leads": clean_leads,
        "opportunities": clean_opportunities,
        "opportunity_contacts": clean_opportunity_contacts,
        "activities": clean_activities,
    },
}


def main():
    bronze_path = Path(os.environ.get("BRONZE_DATA_PATH", "/opt/airflow/data/bronze"))
    silver_path = Path(os.environ.get("SILVER_DATA_PATH", "/opt/airflow/data/silver"))

    total = 0
    for domain, tables in CLEANERS.items():
        print(f"\n=== {domain} ===")
        for table_name, cleaner in tables.items():
            df = read_bronze(bronze_path, domain, table_name)
            df = cleaner(df)
            write_silver(df, silver_path, domain, table_name)
            total += len(df)

    print(f"\nListo. {total} filas en Silver.")


if __name__ == "__main__":
    main()
