-- KPIs de negocio — university
-- Umbral de aprobación: score >= 60 (supuesto documentado, ajustar si el
-- negocio define otro corte oficial).

CREATE OR REPLACE VIEW gold.vw_course_performance AS
SELECT
    c.course_id,
    c.name AS course_name,
    c.department,
    p.full_name AS professor_name,
    COUNT(*) AS total_grades,
    ROUND(AVG(g.score), 1) AS avg_score,
    ROUND(100.0 * SUM(CASE WHEN g.score >= 60 THEN 1 ELSE 0 END) / COUNT(*), 1) AS approval_rate_pct
FROM gold.fact_grades g
JOIN gold.dim_course c ON c.sk_course = g.sk_course
JOIN gold.dim_professor p ON p.sk_professor = c.sk_professor
GROUP BY c.course_id, c.name, c.department, p.full_name;


CREATE OR REPLACE VIEW gold.vw_enrollments_by_semester AS
SELECT
    sem.semester_id,
    sem.code AS semester_code,
    sem.year,
    sem.half,
    COUNT(*) AS total_enrollments,
    COUNT(DISTINCT e.sk_student) AS distinct_students
FROM gold.fact_enrollments e
JOIN gold.dim_semester sem ON sem.sk_semester = e.sk_semester
GROUP BY sem.semester_id, sem.code, sem.year, sem.half
ORDER BY sem.year, sem.half;


-- Nota de calidad de datos: 636 de 5,000 estudiantes (12.72%) tienen edad
-- implausible al inscribirse. Este KPI muestra el impacto para transparencia,
-- no para excluir del pipeline.
CREATE OR REPLACE VIEW gold.vw_data_quality_students AS
SELECT
    COUNT(*) AS total_students,
    SUM(CASE WHEN NOT valid_age THEN 1 ELSE 0 END) AS invalid_age_count,
    ROUND(100.0 * SUM(CASE WHEN NOT valid_age THEN 1 ELSE 0 END) / COUNT(*), 2) AS invalid_age_pct
FROM gold.dim_student;
