"""
Genera un dashboard HTML autocontenido (Fase "plus" — dashboard de KPIs)
a partir de las vistas gold.vw_* en Postgres.

Por qué HTML/Plotly en vez de Power BI: no se cuenta con licencia/instalación
de Power BI en el ambiente de desarrollo. Se optó por un dashboard estático
autocontenido (un solo archivo .html, sin backend ni conexión en vivo) que:
  - No requiere instalar nada para verlo (se abre en cualquier navegador)
  - Es fácil de compartir o adjuntar a la entrega
  - Usa Plotly.js (vía CDN) para gráficos interactivos reales (zoom, hover),
    no imágenes estáticas

Trade-off documentado: al no tener conexión en vivo, los datos quedan
"congelados" al momento de generar el archivo. Para refrescarlos, se
vuelve a correr este script.
"""

import json
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


import decimal


def to_native(obj):
    """Convierte recursivamente tipos no serializables (Decimal, etc.) a
    tipos nativos de Python/JSON. Sin esto, los montos (NUMERIC en Postgres)
    llegan al HTML como texto en vez de número real, lo que confunde a
    Plotly al intentar inferir el tipo de eje (numérico vs. fecha)."""
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_native(v) for v in obj]
    return obj


def df_records(conn, query):
    records = pd.read_sql(query, conn).to_dict(orient="records")
    return to_native(records)


def main():
    conn = get_connection()

    data = {
        "summary": {
            "win_rate": df_records(conn, "SELECT * FROM gold.vw_win_rate")[0],
            "collection": df_records(conn, "SELECT * FROM gold.vw_collection_rate")[0],
            "churn": df_records(conn, "SELECT * FROM gold.vw_subscription_churn")[0],
            "dq_students": df_records(conn, "SELECT * FROM gold.vw_data_quality_students")[0],
        },
        "university": {
            "course_performance": df_records(conn,
                "SELECT * FROM gold.vw_course_performance ORDER BY avg_score DESC LIMIT 15"),
            "enrollments_by_semester": df_records(conn,
                "SELECT * FROM gold.vw_enrollments_by_semester"),
        },
        "billing": {
            "revenue_by_product": df_records(conn,
                "SELECT * FROM gold.vw_revenue_by_product LIMIT 15"),
            "revenue_by_segment": df_records(conn,
                "SELECT * FROM gold.vw_revenue_by_segment"),
            "days_to_pay": df_records(conn, "SELECT * FROM gold.vw_avg_days_to_pay")[0],
        },
        "crm": {
            "pipeline_value": df_records(conn, "SELECT * FROM gold.vw_pipeline_value"),
            "sales_cycle": df_records(conn, "SELECT * FROM gold.vw_sales_cycle_duration")[0],
            "activities_by_outcome": df_records(conn,
                "SELECT * FROM gold.vw_activities_by_outcome"),
        },
    }
    conn.close()

    data_json = json.dumps(data, default=str)

    # Plotly se incrusta directo en el HTML (no via CDN) para que el
    # dashboard funcione sin conexión a internet -- evita el problema de
    # gráficos en blanco cuando el navegador no puede alcanzar cdn.plot.ly
    # (redes corporativas, firewalls, o simplemente sin internet).
    plotly_js_path = Path(__file__).parent / "assets" / "plotly.min.js"
    plotly_js = plotly_js_path.read_text(encoding="utf-8")

    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json)
    html = html.replace("__PLOTLY_JS__", plotly_js)

    out_path = Path(os.environ.get("DASHBOARD_OUTPUT_PATH", "/opt/airflow/dashboards/index.html"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Dashboard generado en {out_path} ({out_path.stat().st_size / 1_000_000:.1f} MB, autocontenido)")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Pipeline de Datos — Dashboard Ejecutivo</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>__PLOTLY_JS__</script>
<style>
  :root{
    --dark:#1D3557; --darker:#14213D; --teal:#2A9D8F; --coral:#E76F51;
    --amber:#E9C46A; --orange:#F4A261; --slate:#264653; --gray:#6C757D;
    --bg:#FAFBFC; --card:#FFFFFF; --border:#E7EAEE;
    --font-display: Georgia, 'Times New Roman', serif;
    --font-body: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --font-mono: ui-monospace, 'SF Mono', 'Cascadia Code', Consolas, monospace;
  }
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--dark);font-family:var(--font-body);}
  header{background:var(--dark);color:#fff;padding:28px 40px 22px;}
  header h1{font-family:var(--font-display);font-weight:700;font-size:28px;margin:0 0 4px;}
  header p{margin:0;color:#AAB4C8;font-size:14px;}
  .lineage{display:flex;gap:6px;align-items:center;margin-top:16px;flex-wrap:wrap;}
  .lineage span{font-family:var(--font-mono);font-size:11px;background:rgba(255,255,255,.08);
    color:#D7DEEA;padding:4px 10px;border-radius:4px;}
  .lineage .arrow{color:#5A6B8C;font-size:12px;}
  nav{display:flex;gap:4px;padding:0 40px;background:var(--dark);border-top:1px solid rgba(255,255,255,.08);}
  nav button{background:none;border:none;color:#AAB4C8;font-family:var(--font-body);font-size:14px;
    font-weight:600;padding:12px 18px;cursor:pointer;border-bottom:3px solid transparent;}
  nav button.active{color:#fff;border-bottom-color:var(--teal);}
  main{padding:28px 40px 60px;max-width:1320px;margin:0 auto;}
  .summary-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:32px;}
  .stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px;}
  .stat{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px 20px;}
  .stat .value{font-family:var(--font-mono);font-weight:700;font-size:30px;line-height:1;}
  .stat .label{color:var(--gray);font-size:12.5px;margin-top:8px;line-height:1.4;}
  .panel{display:none;}
  .panel.active{display:block;}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;}
  .card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px 20px;}
  .card h3{font-family:var(--font-display);font-size:16px;margin:0 0 12px;font-weight:600;color:var(--darker);}
  .note{font-size:12.5px;color:var(--gray);background:#F1F3F5;border-radius:6px;padding:10px 14px;margin-top:10px;line-height:1.5;}
  .footer{text-align:center;color:var(--gray);font-size:12px;padding:20px;}
  @media (max-width:900px){.summary-row{grid-template-columns:repeat(2,1fr);} .grid2{grid-template-columns:1fr;}}
</style>
</head>
<body>

<header>
  <h1>Pipeline de Ingeniería de Datos — Dashboard Ejecutivo</h1>
  <p>CRM + Billing + Universidad · KPIs calculados directo desde la capa Gold</p>
  <div class="lineage">
    <span>CSV</span><span class="arrow">→</span>
    <span>Bronze (Parquet)</span><span class="arrow">→</span>
    <span>Silver (Parquet)</span><span class="arrow">→</span>
    <span>Gold (Star Schema)</span><span class="arrow">→</span>
    <span>KPIs</span>
  </div>
</header>

<nav>
  <button class="tab-btn active" data-tab="resumen">Resumen</button>
  <button class="tab-btn" data-tab="university">University</button>
  <button class="tab-btn" data-tab="billing">Billing</button>
  <button class="tab-btn" data-tab="crm">CRM</button>
</nav>

<main>

  <div class="summary-row" id="summary-cards"></div>

  <div class="panel active" id="panel-resumen">
    <div class="card">
      <h3>Cómo leer este dashboard</h3>
      <p style="font-size:14px;color:var(--dark);line-height:1.6;margin:0;">
        Cada KPI de este panel se calcula directo sobre las vistas <code>gold.vw_*</code>
        del Star Schema — el mismo número que verías consultando la base de datos.
        Navega por dominio (University / Billing / CRM) usando las pestañas de arriba.
        Los recuadros con fondo gris son notas de calidad de datos: se muestran de forma
        transparente en vez de ocultarse.
      </p>
    </div>
  </div>

  <div class="panel" id="panel-university">
    <div class="stat-row" id="university-stats"></div>
    <div class="grid2">
      <div class="card"><h3>Top 15 cursos por promedio de nota</h3><div id="chart-course-perf"></div></div>
      <div class="card"><h3>Inscripciones por semestre</h3><div id="chart-enrollments"></div></div>
    </div>
    <div class="note" id="university-note"></div>
  </div>

  <div class="panel" id="panel-billing">
    <div class="stat-row" id="billing-stats"></div>
    <div class="grid2">
      <div class="card"><h3>Top 15 productos por revenue</h3><div id="chart-revenue-product"></div></div>
      <div class="card"><h3>Revenue por segmento de cliente</h3><div id="chart-revenue-segment"></div></div>
    </div>
    <div class="note" id="billing-note"></div>
  </div>

  <div class="panel" id="panel-crm">
    <div class="stat-row" id="crm-stats"></div>
    <div class="grid2">
      <div class="card"><h3>Valor de pipeline por etapa</h3><div id="chart-pipeline"></div></div>
      <div class="card"><h3>Actividades promedio por resultado</h3><div id="chart-activities"></div></div>
    </div>
    <div class="note" id="cycle-note"></div>
  </div>

</main>

<div class="footer">Generado automáticamente desde gold.vw_* — datos congelados al momento de la última corrida del pipeline</div>

<script>
const DATA = __DATA_JSON__;

const PALETTE = { teal:'#2A9D8F', coral:'#E76F51', amber:'#E9C46A', orange:'#F4A261', slate:'#264653', dark:'#1D3557' };

// IMPORTANTE: freshLayout() devuelve un objeto NUEVO cada vez que se llama,
// nunca el mismo objeto reutilizado. Plotly modifica el objeto de layout
// que recibe (por ejemplo, fija el tipo de eje como 'date' si detecta que
// los valores parecen fechas) -- si varios gráficos compartieran el mismo
// objeto, esa modificación se "contagiaría" de un gráfico a otro sin
// relación entre sí. Cada llamada a Plotly.newPlot debe recibir su propia
// copia independiente.
function freshLayout(overrides = {}) {
  return {
    margin:{t:10,l:50,r:20,b:60},
    font:{family:'Inter, sans-serif', size:12, color:'#1D3557'},
    paper_bgcolor:'#fff', plot_bgcolor:'#fff',
    xaxis:{gridcolor:'#F1F3F5', type:'category'},
    yaxis:{gridcolor:'#F1F3F5'},
    ...overrides,
  };
}

// ---- Tabs (con dibujado perezoso de gráficos) ----
const drawn = { university: false, billing: false, crm: false };

function drawUniversity() {
  const dq = DATA.summary.dq_students;
  const es = DATA.university.enrollments_by_semester;
  const totalEnroll = es.reduce((a,r)=>a+r.total_enrollments, 0);
  const avgPerSem = Math.round(totalEnroll / es.length);
  const cpAll = DATA.university.course_performance;
  const bestCourse = cpAll[0];

  document.getElementById('university-stats').innerHTML = [
    { value: bestCourse.avg_score, label: 'Mejor promedio de curso: ' + bestCourse.course_name, color: PALETTE.teal },
    { value: avgPerSem.toLocaleString(), label: 'Inscripciones promedio por semestre', color: PALETTE.dark },
    { value: dq.invalid_age_pct + '%', label: dq.invalid_age_count + ' de ' + dq.total_students + ' estudiantes con edad implausible', color: PALETTE.amber },
  ].map(c => `<div class="stat"><div class="value" style="color:${c.color}">${c.value}</div><div class="label">${c.label}</div></div>`).join('');

  document.getElementById('university-note').innerHTML =
    `<strong>Nota de calidad de datos:</strong> el ${dq.invalid_age_pct}% de los estudiantes tiene una edad ` +
    `implausible registrada al momento de inscribirse. No se descartan estos registros -- quedan marcados ` +
    `(dim_student.valid_age) para que el análisis decida si los incluye.`;

  const cp = DATA.university.course_performance;
  Plotly.newPlot('chart-course-perf', [{
    type:'bar', orientation:'h',
    x: cp.map(r=>r.avg_score).reverse(), y: cp.map(r=>r.course_name).reverse(),
    marker:{color: PALETTE.teal},
  }], freshLayout({height:420, margin:{t:10,l:110,r:20,b:60}, xaxis:{gridcolor:'#F1F3F5', type:'linear', title:'Promedio de nota'}}), {responsive:true, displayModeBar:false});

  Plotly.newPlot('chart-enrollments', [{
    type:'scatter', mode:'lines+markers',
    x: es.map(r=>r.semester_code), y: es.map(r=>r.total_enrollments),
    line:{color: PALETTE.dark, width:3}, marker:{size:8, color:PALETTE.teal},
    fill:'tozeroy', fillcolor:'rgba(42,157,143,0.08)',
  }], freshLayout({height:420, yaxis:{gridcolor:'#F1F3F5', title:'Inscripciones', rangemode:'tozero'}}), {responsive:true, displayModeBar:false});
}

function drawBilling() {
  const col = DATA.summary.collection;
  const churn = DATA.summary.churn;
  const dtp = DATA.billing.days_to_pay;

  document.getElementById('billing-stats').innerHTML = [
    { value: col.collection_rate_pct + '%', label: 'Collection rate ($' + Number(col.total_collected).toLocaleString(undefined,{maximumFractionDigits:0}) + ' cobrado de $' + Number(col.total_invoiced).toLocaleString(undefined,{maximumFractionDigits:0}) + ')', color: PALETTE.coral },
    { value: dtp.avg_days_to_pay, label: 'Días promedio para pagar una factura', color: PALETTE.dark },
    { value: churn.churn_rate_pct + '%', label: 'Churn real (' + churn.cancelled_subscriptions + ' de ' + churn.total_subscriptions + ' canceladas)', color: PALETTE.orange },
  ].map(c => `<div class="stat"><div class="value" style="color:${c.color}">${c.value}</div><div class="label">${c.label}</div></div>`).join('');

  document.getElementById('billing-note').innerHTML =
    `<strong>Nota de calidad de datos:</strong> el churn se calcula por status='cancelled', no por presencia ` +
    `de end_date -- se verificó que end_date está poblada incluso en suscripciones activas (fecha de fin de ` +
    `contrato planificada, no cancelación real). Ver docs/decisiones.md.`;

  const rp = DATA.billing.revenue_by_product;
  Plotly.newPlot('chart-revenue-product', [{
    type:'bar', orientation:'h',
    x: rp.map(r=>r.total_revenue).reverse(), y: rp.map(r=>r.product_name).reverse(),
    marker:{color: PALETTE.orange},
  }], freshLayout({height:420, margin:{t:10,l:110,r:20,b:60}, xaxis:{gridcolor:'#F1F3F5', type:'linear', title:'Revenue total'}}), {responsive:true, displayModeBar:false});

  const rs = DATA.billing.revenue_by_segment;
  Plotly.newPlot('chart-revenue-segment', [{
    type:'pie', labels: rs.map(r=>r.segment), values: rs.map(r=>r.total_invoiced),
    marker:{colors:[PALETTE.coral, PALETTE.orange, PALETTE.amber]}, hole:0.45,
    textinfo:'label+percent',
  }], freshLayout({height:420, margin:{t:10,l:10,r:10,b:10}, showlegend:false}), {responsive:true, displayModeBar:false});
}

function drawCRM() {
  const cyc = DATA.crm.sales_cycle;
  const pv = DATA.crm.pipeline_value;
  const pipelineTotal = pv.reduce((a,r)=>a+r.total_amount, 0);

  document.getElementById('crm-stats').innerHTML = [
    { value: '$' + Math.round(pipelineTotal).toLocaleString(), label: 'Valor total de pipeline abierto (' + pv.reduce((a,r)=>a+r.opportunity_count,0) + ' oportunidades)', color: PALETTE.slate },
    { value: cyc.avg_days_to_close + ' días', label: 'Duración del ciclo de venta', color: PALETTE.coral },
    { value: cyc.pct_included + '%', label: 'Oportunidades con fecha de cierre confiable', color: PALETTE.amber },
  ].map(c => `<div class="stat"><div class="value" style="color:${c.color}">${c.value}</div><div class="label">${c.label}</div></div>`).join('');
  Plotly.newPlot('chart-pipeline', [{
    type:'bar', x: pv.map(r=>r.stage), y: pv.map(r=>r.total_amount),
    marker:{color: PALETTE.slate},
  }], freshLayout({height:420, yaxis:{gridcolor:'#F1F3F5', title:'Valor de pipeline'}}), {responsive:true, displayModeBar:false});

  const ao = DATA.crm.activities_by_outcome;
  Plotly.newPlot('chart-activities', [{
    type:'bar', x: ao.map(r=>r.stage), y: ao.map(r=>r.avg_activities_per_opportunity),
    marker:{color: PALETTE.amber},
  }], freshLayout({height:420, yaxis:{gridcolor:'#F1F3F5', title:'Actividades promedio'}}), {responsive:true, displayModeBar:false});

  document.getElementById('cycle-note').innerHTML =
    `<strong>Duración del ciclo de venta:</strong> ${cyc.avg_days_to_close} días en promedio — calculado sobre ` +
    `${cyc.opportunities_included} de ${cyc.opportunities_total} oportunidades (${cyc.pct_included}%). ` +
    `Se excluyen las oportunidades con close_date anterior a created_at (ver docs/decisiones.md).`;
}

const DRAWERS = { university: drawUniversity, billing: drawBilling, crm: drawCRM };

document.querySelectorAll('.tab-btn').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-'+btn.dataset.tab).classList.add('active');

    const tab = btn.dataset.tab;
    if (DRAWERS[tab] && !drawn[tab]) {
      // El panel ya es .active (visible) en este punto -> el contenedor
      // tiene tamaño real y Plotly puede dibujar correctamente.
      DRAWERS[tab]();
      drawn[tab] = true;
    } else {
      window.dispatchEvent(new Event('resize'));
    }
  });
});

// ---- Summary cards ----
const s = DATA.summary;
const cards = [
  { value: s.win_rate.win_rate_pct + '%', label: 'Win rate CRM (' + s.win_rate.won_count + ' ganadas / ' + s.win_rate.lost_count + ' perdidas)', color: PALETTE.teal },
  { value: s.collection.collection_rate_pct + '%', label: 'Collection rate — % de lo facturado que se cobra', color: PALETTE.coral },
  { value: s.churn.churn_rate_pct + '%', label: 'Churn real de suscripciones (status=cancelled)', color: PALETTE.orange },
  { value: s.dq_students.invalid_age_pct + '%', label: 'Estudiantes con edad implausible registrada', color: PALETTE.amber },
];
document.getElementById('summary-cards').innerHTML = cards.map(c =>
  `<div class="stat"><div class="value" style="color:${c.color}">${c.value}</div><div class="label">${c.label}</div></div>`
).join('');
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
