-- Migration 004: add subject column to documents and events
-- Enables dataset switching in Grafana via a $subject variable.
-- Idempotent — safe to re-run.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS subject TEXT NOT NULL DEFAULT 'personal';
CREATE INDEX IF NOT EXISTS idx_documents_subject ON documents (subject);

ALTER TABLE events ADD COLUMN IF NOT EXISTS subject TEXT NOT NULL DEFAULT 'personal';
CREATE INDEX IF NOT EXISTS idx_events_subject ON events (subject);

-- Backfill: everything already in the DB is test/seed data
UPDATE documents SET subject = 'test-bulk' WHERE subject = 'personal';
UPDATE events    SET subject = 'test-bulk' WHERE subject = 'personal';

-- Refresh the backward-compat view to expose subject
CREATE OR REPLACE VIEW lab_results AS
SELECT
    s.time          AS date,
    m.category,
    s.metric        AS measurement,
    s.value,
    s.value_text,
    m.unit,
    s.flag,
    d.filename      AS source_file,
    d.processed_at  AS extracted_at,
    d.subject
FROM samples s
JOIN metrics   m ON s.metric      = m.name
JOIN documents d ON s.document_id = d.id;
