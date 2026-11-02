-- One schema per agent. Agents never share tables; they share answers (A2A) and facts (memory-mcp).

CREATE SCHEMA IF NOT EXISTS fitness;
CREATE SCHEMA IF NOT EXISTS wellbeing;
CREATE SCHEMA IF NOT EXISTS work;

CREATE TABLE fitness.session (
    id      bigserial PRIMARY KEY,
    kind    text NOT NULL,
    day     date NOT NULL,
    notes   text NOT NULL DEFAULT '',
    UNIQUE (kind, day)
);

CREATE TABLE fitness.set (
    session_id  bigint NOT NULL REFERENCES fitness.session(id) ON DELETE CASCADE,
    exercise    text NOT NULL,
    ex_order    int NOT NULL,
    set_no      int NOT NULL,
    weight_kg   numeric(6,2) NOT NULL,
    reps        int NOT NULL CHECK (reps > 0),
    rpe         numeric(3,1),
    bodyweight  boolean NOT NULL DEFAULT false,
    PRIMARY KEY (session_id, exercise, set_no)
);
CREATE INDEX ON fitness.set (exercise);

CREATE TABLE wellbeing.sleep (
    night_of date PRIMARY KEY,
    hours    numeric(4,2) NOT NULL CHECK (hours BETWEEN 0 AND 24)
);

CREATE TABLE wellbeing.meal (
    id    bigserial PRIMARY KEY,
    day   date NOT NULL,
    label text NOT NULL,
    kcal  int NOT NULL CHECK (kcal >= 0),
    protein_g int
);
CREATE INDEX ON wellbeing.meal (day);

CREATE TABLE wellbeing.body_weight (
    day date PRIMARY KEY,
    kg  numeric(5,2) NOT NULL
);

CREATE TABLE work.task (
    id       bigserial PRIMARY KEY,
    title    text NOT NULL,
    project  text,
    due      timestamptz,
    done_at  timestamptz
);

-- processed event ids, for idempotent NATS consumers
CREATE TABLE public.processed_event (
    id          text PRIMARY KEY,
    consumer    text NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now()
);

-- least privilege: each agent role sees only its schema
CREATE ROLE fitness_agent LOGIN;
CREATE ROLE wellbeing_agent LOGIN;
CREATE ROLE work_agent LOGIN;
GRANT USAGE ON SCHEMA fitness TO fitness_agent;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA fitness TO fitness_agent;
GRANT USAGE ON SCHEMA wellbeing TO wellbeing_agent;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA wellbeing TO wellbeing_agent;
GRANT USAGE ON SCHEMA work TO work_agent;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA work TO work_agent;
