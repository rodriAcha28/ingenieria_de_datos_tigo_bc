# Decisiones del proyecto

Este documento registra las decisiones no obvias que se fueron tomando durante
el desarrollo del pipeline, el razonamiento detrás de cada una y qué alternativas
se descartaron.

---

## 1. Arquitectura general

### De Postgres a Parquet en Bronze y Silver

El plan inicial era construir Bronze y Silver directamente como tablas en
Postgres (así arrancó de hecho el proyecto: la primera versión de la ingesta
cargaba los CSV a un schema `bronze` en Postgres, y ahí se hizo también la
primera ronda de discovery). A mitad de camino se decidió migrar Bronze y
Silver a archivos Parquet, dejando Postgres únicamente para la capa Gold.

El motivo del cambio: Ya que la empresa trabaja con volúmenes de datos mucho más grandes
que los de este ejercicio, y Postgres no es la herramienta más adecuada para
mover y transformar datos crudos a esa escala. Parquet, al ser un formato
columnar pensado para grandes volúmenes, facilita justamente ese manejo
inicial de los datos en Bronze y Silver — lectura más liviana, mejor
compresión, y es el formato natural de entrada para herramientas de
procesamiento distribuido si en algún momento se necesita escalar. Aunque en
este proyecto el volumen no lo exige, la idea es practicar el patrón que se
usa en producción.

La exploración inicial de discovery que se hizo sobre el Bronze en Postgres no
se descartó ni se repitió desde cero — sigue siendo válida como parte del
proceso de trabajo, solo que la implementación productiva del pipeline se
migró después a Parquet.

### Variables de entorno para credenciales (`.env`)

Las credenciales que estaban hardcodeadas en el `docker-compose.yml` (usuarios
y contraseñas de Postgres, token de Jupyter) se van a mover a un archivo
`docker/.env`, referenciado con `${VARIABLE}` y excluido de Git, dejando un
`.env.example` versionado con los nombres de variable sin valores reales. Así
cualquiera puede clonar el repo, copiar el `.env.example`, poner sus propios
valores y levantar todo sin tocar código ni exponer credenciales en el
historial de Git. Pendiente de aplicar.

### Healthchecks y dependencia de `airflow-init`

Se cambió `depends_on: airflow-init` (sin condición) por
`depends_on: airflow-init: condition: service_completed_successfully`, para
que el webserver y el scheduler esperen a que `airflow db migrate` termine de
verdad, no solo a que el contenedor de init se haya iniciado. Con la
configuración original había riesgo de que el webserver arrancara buscando
tablas que aún no existían.

### Schemas de Postgres vía `init-db/`

Se usa el mecanismo estándar de la imagen de `postgres` (archivos `.sql`/`.sh`
en `/docker-entrypoint-initdb.d/`, montado desde `./init-db`) para crear los
schemas necesarios automáticamente al primer arranque del contenedor. Ojo:
esto solo corre la primera vez que el volumen de datos se crea desde cero — si
el stack ya se había levantado antes, hay que hacer `docker compose down -v`
para que se vuelva a ejecutar.

---

## 2. Ingesta (Bronze)

Todo se lee como texto (`dtype=str, keep_default_na=False`) al ingestar los
CSV — es el espíritu de Bronze, datos crudos sin interpretar. Tipar de más acá
mezclaría responsabilidades con Silver y podría esconder problemas de formato
que se necesitan ver en discovery.

Cada tabla lleva metadatos de linaje agregados en la ingesta:
`_source_file`, `_source_domain`, `_ingested_at`. Sirve para saber de qué
archivo y dominio vino cada fila, y cuándo se cargó.

Cada corrida reemplaza completamente la tabla/archivo de destino
(`if_exists="replace"`), lo que hace el proceso idempotente pero no conserva
histórico de cargas anteriores — solo se ve el último snapshot. Se consideró
aceptable porque el dataset de origen es estático en este ejercicio.

Se registra cada archivo procesado (dominio, nombre, filas, fecha) en un log
de control — primero como tabla `bronze._ingestion_log` en Postgres, y tras la
migración a Parquet, como CSV en `data/bronze/_control/ingestion_log.csv` —
para tener trazabilidad de qué se cargó y cuándo, independiente de que las
tablas de datos se reemplacen en cada corrida.

Si un CSV individual falla al leerse, se loguea el error y se sigue con los
demás archivos en vez de abortar todo el proceso — un archivo corrupto no
debería tumbar la carga completa.

---

## 3. Discovery y calidad de datos

Se revisó cada una de las 18 tablas en tres niveles, de más simple a más
complejo: formato y tipo por columna (nulos, duplicados, cardinalidad,
formatos de fecha/monto), llaves huérfanas entre tablas relacionadas, y
reglas de negocio entre columnas de una misma fila (por ejemplo, que una
fecha de cierre no sea anterior a la de creación). Este último tipo de regla
no se puede automatizar de forma genérica porque depende del significado de
negocio de cada columna, no de su tipo de dato.

### Nulos, duplicados y llaves huérfanas

- **university**: sin nulos, sin llaves huérfanas. El hallazgo inicial de
  "37,214 duplicados en `enrollment_id`" dentro de `grades` era un falso
  positivo — `grades` tiene varios registros por inscripción (varias
  evaluaciones por enrollment), no es un error de calidad. La clave primaria
  real de `grades` es `grade_id`.
- **billing**: sin duplicados, sin llaves huérfanas. `customers.external_ref`
  tiene 50% de nulos (ver más abajo).
- **crm**: sin duplicados, sin llaves huérfanas. Los nulos que se habían
  reportado en "`opportunity_id`/`contact_id`" (9,985 y 5,976) en realidad
  corresponden a la tabla `activities`, no a `opportunity_contacts` (que no
  tiene volumen suficiente para esos números) — son relaciones opcionales
  válidas por diseño: una actividad puede estar ligada solo a un contacto o
  solo a una oportunidad, no necesariamente a ambos. No se trata como error.

### Auditoría de tipos y formatos

Se revisó cada columna de fecha, monto y texto en las 18 tablas buscando
formatos mixtos, valores no convertibles y variantes de mayúsculas/espacios.
El único hallazgo (`grades.grade_id` marcado como "numérico inválido") fue un
falso positivo del heurístico automático — `grade_id` es un identificador de
texto (`GRD-00000001`), no una nota. El resto pasó limpio, sin mezcla de
formatos ni valores raros — razonable tratándose de un dataset sintético.

### Reglas de negocio entre columnas

| Regla | Tabla | Filas afectadas | % | Qué se decidió |
|---|---|---|---|---|
| `due_at >= issued_at` | invoices | 0 | 0% | Nada, dato limpio |
| `paid_at >= issued_at` (de la factura) | payments | 0 | 0% | Nada, dato limpio |
| `end_date >= start_date` | subscriptions | 783 | 5.22% | Error real — se marca (`_valid_date_range`), no se borra |
| Edad 15-90 años al inscribirse | students | 636 | 12.72% | Error real — se marca (`_valid_age`), no se borra |
| `occurred_at >= created_at` de la oportunidad | activities | 3,792 | 18.96% | La regla estaba mal planteada, no es un error de dato — es normal prospectar antes de crear formalmente la oportunidad |
| `close_date >= created_at` | opportunities | 1,029 | 34.30% | La regla estaba mal planteada — `close_date` probablemente es una fecha objetivo/planificada, no un evento posterior obligatorio |
| `graded_at >= enrolled_at` de la inscripción | grades | 29,241 | 48.73% | La regla estaba mal planteada — `enrolled_at` no necesariamente marca el inicio real de clases |

La lección de los últimos tres casos (19%, 34%, 49%) vale la pena dejarla
anotada: un porcentaje tan alto de "violaciones" casi siempre significa que el
supuesto de negocio estaba mal planteado, no que el dato esté sucio. Si se
hubiera aplicado la regla a ciegas, se habría descartado o marcado como
inválido entre un quinto y la mitad de los datos por una suposición
incorrecta, no por un problema real del dataset.

### `billing.customers.external_ref`

50% de los valores son nulos. Se investigó si el nulo se correlaciona con
`segment`, `country` o `created_at` (la hipótesis era que el campo se llena
solo para clientes migrados de otro sistema). Las proporciones de `segment` y
`country` salieron casi idénticas entre clientes con y sin `external_ref`, y
el rango de `created_at` también fue el mismo en ambos grupos — no hay ningún
patrón. Se decidió conservar la columna tal cual, sin bandera ni tratamiento
especial: el nulo se interpreta como un campo opcional legítimo.

### Relación entre los tres dominios de negocio

Se investigó si `university`, `billing` y `crm` comparten personas en común,
a pesar de no tener ninguna columna `*_id` compartida entre dominios.

Cruzando por email (señal fuerte, es único por diseño):

| Comparación | Coincidencias | Total |
|---|---|---|
| students ↔ customers | 1 | 5,000 |
| students ↔ contacts | 0 | 5,000 |
| customers ↔ contacts | 1 | 10,000 |

Como verificación extra se cruzó también por nombre completo, y ahí salió un
número mucho más alto (2,096 de 5,000 entre students y customers, por
ejemplo). Antes de sacar conclusiones apuradas, se revisó el catálogo de
nombres únicos dentro de cada tabla: `students` tiene solo 2,146 nombres
distintos en 5,000 filas — el generador sintético usa un catálogo de nombres
limitado, así que las coincidencias por nombre entre tablas sin relación real
son esperables por pura probabilidad. El chequeo decisivo: de los pares que
coincidían por nombre, solo 1 también coincidía por email — el mismo caso
aislado de la primera prueba, no evidencia nueva.

Con las dos verificaciones cruzadas, la conclusión quedó firme: los tres
dominios son poblaciones de negocio independientes, no se fuerza ninguna
dimensión de persona unificada entre ellos. Esto tiene sentido de negocio: es
común que una misma institución tenga sistemas que nacieron por separado
(académico, facturación, comercial) y nunca se integraron a nivel de base de
datos — arquitectura de data marts independientes, no un error de modelado.

---

## 4. Silver — limpieza, tipado y estandarización

En las 18 tablas se aplicó lo mismo: fechas de texto a tipo fecha real, trim
de espacios en texto, deduplicación por la clave primaria real de cada tabla
(no se encontraron duplicados reales usando la clave correcta), y los
metadatos de linaje de Bronze se reemplazan por un único `_bronze_ingested_at`
para no cargar con las tres columnas originales.

Ninguna fila se elimina solo por "verse mal" — se marca con una columna de
calidad y la decisión de incluirla o no en el análisis se deja para más
adelante:

- `students`: se agregan `_age_at_enroll` y `_valid_age`, por el hallazgo de
  12.72% con edad implausible al inscribirse.
- `subscriptions`: se agrega `_valid_date_range`, por el 5.22% con fechas
  invertidas.

El único caso donde sí se eliminan filas es `opportunity_contacts`: se
descartan las que no tengan `opportunity_id` o `contact_id` (tabla puente
N:N, sin ambas llaves no conecta nada). En los datos reales no apareció
ninguna fila así — el código está listo para el caso, pero no se activó.

**Bug encontrado y corregido:** `university_courses.credits` y
`university_semesters.year` quedaron como texto en la primera versión de
Silver porque faltó el cast numérico en `clean_courses()` y
`clean_semesters()`. No se notó hasta la carga a Gold, cuando Postgres
rechazó el insert por incompatibilidad de tipos. Se corrigió agregando
`pd.to_numeric(..., errors="coerce").astype("Int64")` a ambas columnas, y se
revisó el resto del script para confirmar que no quedara ninguna otra
columna numérica sin castear.

---

## 5. Gold — modelo dimensional (Star Schema)

Dado que los tres dominios resultaron ser poblaciones independientes (ver
sección 3), el modelo Gold se armó como tres Star Schemas separados —
`university`, `billing`, `crm` — cada uno con sus propias dimensiones y
hechos, sin forzar una dimensión de persona unificada. La única dimensión
compartida entre los tres es `dim_date`, que no representa una entidad de
negocio sino el calendario, así que no contradice la independencia de los
dominios — es una dimensión conformada, práctica estándar en modelado
dimensional.

Las dimensiones usan llaves subrogadas autoincrementales (`sk_*`) como
llave primaria interna, conservando la llave natural de origen
(`student_id`, etc.) como atributo único — es la práctica estándar de
modelado dimensional y facilita el manejo de dimensiones que cambian en el
tiempo. `dim_date` usa una convención distinta: su llave es un entero legible
tipo `YYYYMMDD` (ej. `20231130`), calculado directo desde la fecha sin
necesitar una secuencia — así los hechos calculan su propia `sk_date` sin un
join adicional al insertar.

`dim_lead` se carga en Gold pero no tiene ninguna FK entrante desde ningún
hecho — confirmado en discovery que `leads` no comparte ninguna columna con
`contacts`, `accounts` ni `opportunities`. Así se modela normalmente: un lead
vive aislado hasta que se "convierte", proceso que no está representado en
este dataset.

`fact_grades` denormaliza `sk_student`, `sk_course` y `sk_semester`
directamente desde el `enrollment` correspondiente al momento de la carga, en
vez de depender de un join a través de `fact_enrollments` para llegar a esas
dimensiones (se conserva `enrollment_id` solo como trazabilidad hacia
Silver). En Star Schema un hecho no debería depender de otro hecho para
navegarse — rompe la simplicidad para herramientas de BI. El mismo patrón se
usa en `fact_invoice_items` y `fact_payments` (denormalizan `sk_customer`
desde `fact_invoices`), y en `fact_activities` y
`bridge_opportunity_contacts`, que referencian `opportunity_id` como FK
natural hacia `fact_opportunities`.

Las banderas de calidad (`valid_age` en `dim_student`, `valid_date_range` en
`fact_subscriptions`) se conservan como atributos en Gold, no se usan para
filtrar filas en la carga — la decisión de incluir o excluir esos registros
queda en manos del análisis de negocio o el dashboard final, no se toma de
forma irreversible en el modelado.
