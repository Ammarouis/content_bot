-- ITGenix Academy bot schema (SQLite), version 2. Applied idempotently on startup
-- after the ordered migrations in database.py have upgraded older databases.

CREATE TABLE IF NOT EXISTS academic_years (
    id                      INTEGER PRIMARY KEY CHECK (id BETWEEN 1 AND 5),
    name                    TEXT    NOT NULL UNIQUE,
    requires_specialization INTEGER NOT NULL CHECK (requires_specialization IN (0, 1))
);

INSERT OR IGNORE INTO academic_years (id, name, requires_specialization) VALUES
    (1, 'السنة الأولى', 0),
    (2, 'السنة الثانية', 0),
    (3, 'السنة الثالثة', 0),
    (4, 'السنة الرابعة', 1),
    (5, 'السنة الخامسة', 1);

CREATE TABLE IF NOT EXISTS specializations (
    id         INTEGER PRIMARY KEY,
    year_id    INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    name       TEXT    NOT NULL CHECK (length(trim(name)) BETWEEN 2 AND 100),
    created_at TEXT    NOT NULL,
    UNIQUE (year_id, name)
);

CREATE TRIGGER IF NOT EXISTS trg_spec_year_check_ins BEFORE INSERT ON specializations
BEGIN
    SELECT RAISE(ABORT, 'year_has_no_specializations')
    WHERE (SELECT requires_specialization FROM academic_years WHERE id = NEW.year_id) <> 1;
END;

CREATE TABLE IF NOT EXISTS subjects (
    id                INTEGER PRIMARY KEY,
    code              TEXT    NOT NULL UNIQUE
                      CHECK (length(code) BETWEEN 2 AND 20
                             AND code GLOB '[A-Z]*'
                             AND code NOT GLOB '*[^A-Z0-9]*'),
    name              TEXT    NOT NULL CHECK (length(trim(name)) BETWEEN 2 AND 150),
    year_id           INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    specialization_id INTEGER REFERENCES specializations(id) ON DELETE RESTRICT,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    -- v2: every subject belongs to exactly one semester (1 = first, 2 = second)
    semester           INTEGER NOT NULL DEFAULT 1 CHECK (semester IN (1, 2)),
    -- v2: 0 = semester was assigned automatically by the v1→v2 migration and awaits admin confirmation
    semester_confirmed INTEGER NOT NULL DEFAULT 1 CHECK (semester_confirmed IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_subjects_year_spec ON subjects(year_id, specialization_id);
CREATE INDEX IF NOT EXISTS idx_subjects_hierarchy ON subjects(year_id, specialization_id, semester);

CREATE TRIGGER IF NOT EXISTS trg_subject_spec_ins BEFORE INSERT ON subjects
BEGIN
    SELECT RAISE(ABORT, 'specialization_required')
    WHERE (SELECT requires_specialization FROM academic_years WHERE id = NEW.year_id) = 1
      AND NEW.specialization_id IS NULL;
    SELECT RAISE(ABORT, 'specialization_not_allowed')
    WHERE (SELECT requires_specialization FROM academic_years WHERE id = NEW.year_id) = 0
      AND NEW.specialization_id IS NOT NULL;
    SELECT RAISE(ABORT, 'specialization_year_mismatch')
    WHERE NEW.specialization_id IS NOT NULL
      AND (SELECT year_id FROM specializations WHERE id = NEW.specialization_id) <> NEW.year_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_subject_spec_upd BEFORE UPDATE OF year_id, specialization_id ON subjects
BEGIN
    SELECT RAISE(ABORT, 'specialization_required')
    WHERE (SELECT requires_specialization FROM academic_years WHERE id = NEW.year_id) = 1
      AND NEW.specialization_id IS NULL;
    SELECT RAISE(ABORT, 'specialization_not_allowed')
    WHERE (SELECT requires_specialization FROM academic_years WHERE id = NEW.year_id) = 0
      AND NEW.specialization_id IS NOT NULL;
    SELECT RAISE(ABORT, 'specialization_year_mismatch')
    WHERE NEW.specialization_id IS NOT NULL
      AND (SELECT year_id FROM specializations WHERE id = NEW.specialization_id) <> NEW.year_id;
END;

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    full_name   TEXT    NOT NULL CHECK (length(trim(full_name)) BETWEEN 2 AND 100),
    role        TEXT    NOT NULL CHECK (role IN ('admin', 'uploader', 'student')),
    added_by    INTEGER,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE TABLE IF NOT EXISTS student_subjects (
    student_id  INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    assigned_at TEXT    NOT NULL,
    PRIMARY KEY (student_id, subject_id)
);
CREATE INDEX IF NOT EXISTS idx_student_subjects_subject ON student_subjects(subject_id);

CREATE TABLE IF NOT EXISTS contents (
    id                INTEGER PRIMARY KEY,
    subject_id        INTEGER NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    content_type      TEXT    NOT NULL CHECK (content_type IN ('lecture', 'session')),
    number            INTEGER NOT NULL CHECK (number BETWEEN 1 AND 9999),
    student_id        INTEGER REFERENCES users(telegram_id) ON DELETE SET NULL,
    status            TEXT    NOT NULL CHECK (status IN
                        ('uploading', 'pending', 'approving', 'approved', 'rejected', 'resubmitting')),
    pdf_skip_reason   TEXT,
    rejection_reason  TEXT,
    reviewer_id       INTEGER REFERENCES users(telegram_id) ON DELETE SET NULL,
    submitted_at      TEXT    NOT NULL,
    decided_at        TEXT,
    status_changed_at TEXT    NOT NULL,
    created_at        TEXT    NOT NULL,
    UNIQUE (subject_id, content_type, number),
    CHECK (status <> 'rejected' OR rejection_reason IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_contents_status ON contents(status, submitted_at);
CREATE INDEX IF NOT EXISTS idx_contents_student ON contents(student_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_contents_subject_status ON contents(subject_id, status);

CREATE TABLE IF NOT EXISTS content_files (
    content_id     INTEGER NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
    kind           TEXT    NOT NULL CHECK (kind IN ('pdf', 'tex')),
    stage          TEXT    NOT NULL CHECK (stage IN ('temp', 'approved')),
    chat_id        INTEGER NOT NULL,
    message_id     INTEGER NOT NULL,
    file_id        TEXT    NOT NULL,
    file_unique_id TEXT,
    file_name      TEXT,
    file_size      INTEGER,
    updated_at     TEXT    NOT NULL,
    -- v2: protection requested when the message was posted, and the flag Telegram actually reported
    protect_requested INTEGER NOT NULL DEFAULT 0 CHECK (protect_requested IN (0, 1)),
    protected         INTEGER CHECK (protected IN (0, 1)),   -- NULL = unknown (posted before v2)
    PRIMARY KEY (content_id, kind),
    UNIQUE (chat_id, message_id)
);

-- Review / preview copies sent into private chats (tracked so nothing is orphaned).
CREATE TABLE IF NOT EXISTS preview_messages (
    id         INTEGER PRIMARY KEY,
    content_id INTEGER REFERENCES contents(id) ON DELETE CASCADE,
    chat_id    INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    created_at TEXT    NOT NULL,
    UNIQUE (chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_preview_created ON preview_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_preview_content ON preview_messages(content_id);

CREATE TABLE IF NOT EXISTS deletion_jobs (
    id              INTEGER PRIMARY KEY,
    description     TEXT    NOT NULL,
    requested_by    INTEGER,
    status          TEXT    NOT NULL CHECK (status IN ('in_progress', 'completed', 'needs_attention')),
    notified_status TEXT,
    created_at      TEXT    NOT NULL,
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON deletion_jobs(status);

-- Database-backed cleanup queue: every Telegram message that has to disappear.
-- held    : message posted during an in-flight operation (not deleted unless the operation fails)
-- pending : waiting for (re)try      done : deleted      failed : max attempts reached (admin can retry)
CREATE TABLE IF NOT EXISTS cleanup_queue (
    id              INTEGER PRIMARY KEY,
    chat_id         INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    reason          TEXT    NOT NULL,
    content_ref     INTEGER,
    job_id          INTEGER REFERENCES deletion_jobs(id) ON DELETE SET NULL,
    status          TEXT    NOT NULL CHECK (status IN ('held', 'pending', 'done', 'failed')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    next_attempt_at TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    UNIQUE (chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_cleanup_due ON cleanup_queue(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_cleanup_job ON cleanup_queue(job_id, status);
CREATE INDEX IF NOT EXISTS idx_cleanup_content ON cleanup_queue(content_ref, status);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL
);
