-- Hechos de la estrella `university`.
-- fact_enrollments primero: fact_grades denormaliza sus llaves desde ahí
-- (evita que un hecho dependa de otro hecho para navegarse en BI).

CREATE TABLE IF NOT EXISTS gold.fact_enrollments (
    enrollment_id  TEXT PRIMARY KEY,     -- degenerada (viene de Silver, no se genera sk)
    sk_student     INT REFERENCES gold.dim_student(sk_student),
    sk_course      INT REFERENCES gold.dim_course(sk_course),
    sk_semester    INT REFERENCES gold.dim_semester(sk_semester),
    sk_date        INT REFERENCES gold.dim_date(sk_date),
    status         TEXT
);

INSERT INTO gold.fact_enrollments (enrollment_id, sk_student, sk_course, sk_semester, sk_date, status)
SELECT
    e.enrollment_id,
    st.sk_student,
    c.sk_course,
    sem.sk_semester,
    TO_CHAR(e.enrolled_at, 'YYYYMMDD')::INT,
    e.status
FROM staging.university_enrollments e
JOIN gold.dim_student  st  ON st.student_id   = e.student_id
JOIN gold.dim_course   c   ON c.course_id     = e.course_id
JOIN gold.dim_semester sem ON sem.semester_id = e.semester_id
ON CONFLICT (enrollment_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.fact_grades (
    grade_id       TEXT PRIMARY KEY,
    enrollment_id  TEXT,   -- se conserva solo para trazabilidad hacia Silver, no es FK de navegación
    sk_student     INT REFERENCES gold.dim_student(sk_student),
    sk_course      INT REFERENCES gold.dim_course(sk_course),
    sk_semester    INT REFERENCES gold.dim_semester(sk_semester),
    sk_date        INT REFERENCES gold.dim_date(sk_date),
    assessment     TEXT,
    score          NUMERIC,
    weight         NUMERIC
);

-- Nota: graded_at < enrolled_at ocurre en 48.73% de los casos (discovery).
-- Se determinó que era un supuesto de regla incorrecto, no un error de dato,
-- por lo que no se filtra ni se marca nada aquí -- se carga todo.
INSERT INTO gold.fact_grades (grade_id, enrollment_id, sk_student, sk_course, sk_semester, sk_date, assessment, score, weight)
SELECT
    g.grade_id,
    g.enrollment_id,
    fe.sk_student,
    fe.sk_course,
    fe.sk_semester,
    TO_CHAR(g.graded_at, 'YYYYMMDD')::INT,
    g.assessment,
    g.score,
    g.weight
FROM staging.university_grades g
JOIN gold.fact_enrollments fe ON fe.enrollment_id = g.enrollment_id
ON CONFLICT (grade_id) DO NOTHING;
