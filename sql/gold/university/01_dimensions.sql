-- Dimensiones de la estrella `university`.
-- Orden importa: dim_professor antes que dim_course (FK), el resto es independiente.

CREATE TABLE IF NOT EXISTS gold.dim_professor (
    sk_professor  SERIAL PRIMARY KEY,
    professor_id  TEXT UNIQUE NOT NULL,
    full_name     TEXT,
    email         TEXT,
    department    TEXT,
    hired_at      DATE
);

INSERT INTO gold.dim_professor (professor_id, full_name, email, department, hired_at)
SELECT professor_id, first_name || ' ' || last_name, email, department, hired_at
FROM staging.university_professors
ON CONFLICT (professor_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.dim_course (
    sk_course     SERIAL PRIMARY KEY,
    course_id     TEXT UNIQUE NOT NULL,
    code          TEXT,
    name          TEXT,
    credits       INT,
    department    TEXT,
    sk_professor  INT REFERENCES gold.dim_professor(sk_professor)
);

INSERT INTO gold.dim_course (course_id, code, name, credits, department, sk_professor)
SELECT c.course_id, c.code, c.name, c.credits, c.department, p.sk_professor
FROM staging.university_courses c
LEFT JOIN gold.dim_professor p ON p.professor_id = c.professor_id
ON CONFLICT (course_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.dim_semester (
    sk_semester  SERIAL PRIMARY KEY,
    semester_id  TEXT UNIQUE NOT NULL,
    code         TEXT,
    year         INT,
    half         TEXT,
    start_date   DATE,
    end_date     DATE
);

INSERT INTO gold.dim_semester (semester_id, code, year, half, start_date, end_date)
SELECT semester_id, code, year, half, start_date, end_date
FROM staging.university_semesters
ON CONFLICT (semester_id) DO NOTHING;


CREATE TABLE IF NOT EXISTS gold.dim_student (
    sk_student      SERIAL PRIMARY KEY,
    student_id      TEXT UNIQUE NOT NULL,
    full_name       TEXT,
    email           TEXT,
    birth_date      DATE,
    country         TEXT,
    age_at_enroll   NUMERIC,
    valid_age       BOOLEAN  -- ver hallazgo discovery: 636/5000 (12.72%) fuera de rango 15-90
);

INSERT INTO gold.dim_student (student_id, full_name, email, birth_date, country, age_at_enroll, valid_age)
SELECT
    student_id,
    first_name || ' ' || last_name,
    email,
    birth_date,
    country,
    _age_at_enroll,
    _valid_age
FROM staging.university_students
ON CONFLICT (student_id) DO NOTHING;
