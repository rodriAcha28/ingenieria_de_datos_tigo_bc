# Pipeline de Ingeniería de Datos — CRM + Billing + Universidad

Pipeline de datos de extremo a extremo que transforma datos crudos de tres
sistemas de negocio (académico, facturación, comercial) en un modelo
dimensional analítico, con KPIs, dashboard y modelo predictivo.

> El razonamiento detrás de cada decisión técnica (por qué Parquet, por qué
> 3 Star Schemas separados, hallazgos de calidad de datos, bugs encontrados
> y corregidos) está documentado en [`docs/decisiones.md`](docs/decisiones.md).
> Este README es solo la guía de instalación y uso.

---

## Arquitectura

```
CSV (raw) → Bronze (Parquet) → Silver (Parquet) → staging (Postgres) → Gold (Star Schema, Postgres) → KPIs → Dashboard
```

- **Bronze / Silver**: Parquet, procesado con Python/pandas
- **Gold**: PostgreSQL, modelado como 3 Star Schemas independientes
  (`university`, `billing`, `crm` — confirmado que no comparten datos entre sí)
- **Orquestación**: Apache Airflow, con 3 ramas paralelas por dominio
- **KPIs**: vistas SQL sobre Gold (`gold.vw_*`)
- **Dashboard**: HTML + Plotly.js, autocontenido

## Stack tecnológico

| Herramienta | Uso |
|---|---|
| Docker Compose | Levanta Postgres, Airflow y Jupyter de forma reproducible |
| Python (pandas, pyarrow) | Ingesta y transformación en Bronze/Silver |
| PostgreSQL | Capa Gold (modelo dimensional) |
| Apache Airflow | Orquestación del pipeline completo |
| Jupyter | Discovery, validación, análisis, modelo predictivo |
| Plotly.js | Dashboard interactivo |
| scikit-learn | Modelo predictivo (extra) |

---

## Requisitos previos

- [Docker](https://www.docker.com/) y Docker Compose (v2.20+)
- ~4 GB de RAM libres para los contenedores
- Los archivos CSV de origen ubicados en `data/raw/{university,billing,crm}/`

## Instalación y arranque

**1. Clonar el repositorio**
```bash
git clone <url-del-repositorio>
cd <nombre-del-proyecto>
```

**2. Configurar variables de entorno**
```bash
cp docker/.env.example docker/.env
# Editar docker/.env si se quieren usar credenciales distintas a las de ejemplo
```

**3. Levantar el ambiente**
```bash
cd docker
docker compose up -d
```
Esto crea automáticamente los schemas `bronze`/`silver`/`gold` en Postgres
(vía `docker/init-db/`) y deja disponibles:
- **Airflow**: http://localhost:8080 (usuario/clave: `admin` / `admin`)
- **Jupyter**: http://localhost:8888 (token: ver `docker/.env`)
- **Postgres**: `localhost:5432`

**4. Ejecutar el pipeline**

Opción A — automatizado con Airflow (recomendado):
1. Entrar a http://localhost:8080
2. Activar el DAG `pipeline_completo`
3. Disparar manualmente con el botón ▶️ ("Trigger DAG")

Esto corre, en orden: ingesta a Bronze → limpieza a Silver → carga a
`staging` → construcción de Gold (3 ramas en paralelo: university, billing,
crm) → cálculo de KPIs.

Opción B — manual, paso a paso:
```bash
docker exec -it docker-airflow-webserver-1 python /opt/airflow/src/ingest_bronze.py
docker exec -it docker-airflow-webserver-1 python /opt/airflow/src/transform_silver.py
docker exec -it docker-airflow-webserver-1 python /opt/airflow/src/load_staging.py
docker exec -it docker-postgres-warehouse-1 psql -U rodrick -d warehouse -f /tmp/gold/00_create_schema.sql
docker exec -it docker-postgres-warehouse-1 psql -U rodrick -d warehouse -f /tmp/gold/01_dim_date.sql
# ... resto de los scripts de sql/gold/, ver docs/decisiones.md para el orden completo
```

**5. Validar que todo cargó correctamente**
```bash
docker exec -it docker-airflow-webserver-1 python /opt/airflow/src/validate_pipeline.py
```
Debe reportar 18/18 tablas en estado `OK` (reconciliación de conteos entre
las 5 capas del pipeline).

**6. Generar el dashboard**
```bash
docker exec -it docker-airflow-webserver-1 python /opt/airflow/src/build_dashboard.py
```
Abrir `dashboards/index.html` directo en el navegador (no requiere servidor).

**7. Exportar Gold a Parquet (opcional)**
```bash
docker exec -it docker-airflow-webserver-1 python /opt/airflow/src/export_gold_parquet.py
```

---

## Estructura del repositorio

```
.
├── docker/
│   ├── docker-compose.yml
│   ├── Dockerfile.airflow
│   ├── Dockerfile.jupyter
│   ├── .env.example
│   └── init-db/              # Creación automática de schemas
├── data/
│   ├── raw/                  # CSV de origen
│   ├── bronze/                # Parquet crudo + metadatos de linaje
│   ├── silver/                 # Parquet limpio y tipado
│   └── parquet/gold/            # Exportación final de Gold
├── dags/
│   └── pipeline_dag.py        # DAG de Airflow (13 tareas, 3 ramas paralelas)
├── sql/
│   └── gold/
│       ├── 00_create_schema.sql
│       ├── 01_dim_date.sql
│       ├── university/        # Dimensiones y hechos
│       ├── billing/
│       ├── crm/
│       └── kpis/               # 14 vistas de KPIs de negocio
├── src/
│   ├── ingest_bronze.py
│   ├── transform_silver.py
│   ├── load_staging.py
│   ├── export_gold_parquet.py
│   ├── validate_pipeline.py
│   ├── build_dashboard.py
│   └── assets/plotly.min.js
├── dashboards/
│   └── index.html              # Dashboard interactivo (generado)
├── notebooks/
│   ├── 01_discovery_profiling.ipynb
│   ├── 02_silver_validation.ipynb
│   ├── 03_business_insights.ipynb
│   └── 04_predictive_model.ipynb
├── docs/
│   └── decisiones.md            # Razonamiento detrás de cada decisión técnica
├── presentacion_ejecutiva.pptx
└── README.md
```

---

## Modelo de datos (Gold)

Tres Star Schemas independientes (confirmado con evidencia que los tres
dominios no comparten datos entre sí — ver `docs/decisiones.md`), con
`gold.dim_date` como única dimensión compartida (calendario):

- **university**: `dim_student`, `dim_course`, `dim_professor`,
  `dim_semester` / `fact_enrollments`, `fact_grades`
- **billing**: `dim_customer`, `dim_product` / `fact_invoices`,
  `fact_invoice_items`, `fact_payments`, `fact_subscriptions`
- **crm**: `dim_account`, `dim_contact`, `dim_lead` / `fact_opportunities`,
  `fact_activities`, `bridge_opportunity_contacts`

## KPIs disponibles

14 vistas en `gold.vw_*` (ver `sql/gold/kpis/`), entre ellas: win rate,
revenue por producto/segmento, collection rate, churn, duración de ciclo
de venta, desempeño por curso. Documentación completa de cada cálculo y
sus decisiones en `docs/decisiones.md`.

## Entregables

| Entregable | Ubicación |
|---|---|
| Pipeline automatizado | `dags/pipeline_dag.py` |
| Notebooks de análisis | `notebooks/` |
| Documentación de decisiones | `docs/decisiones.md` |
| Presentación ejecutiva | `presentacion_ejecutiva.pptx` |
| Dashboard interactivo | `dashboards/index.html` |
| Modelo predictivo (extra) | `notebooks/04_predictive_model.ipynb` |

---

## Notas de reproducibilidad

- El pipeline es idempotente: puede re-ejecutarse sin duplicar datos
  (`ON CONFLICT DO NOTHING` en Gold, `if_exists="replace"` en Bronze/Silver).
- `docker compose down -v` reinicia el ambiente completo desde cero
  (borra los volúmenes de Postgres, útil si se modifica `init-db/`).
- Validado de punta a punta: 446,708 filas de negocio reconciliadas sin
  discrepancias entre las 5 capas del pipeline.
