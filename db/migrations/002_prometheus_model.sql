-- ============================================================
-- Migration 002: Prometheus-inspired data model
-- ============================================================
-- Migrates from single lab_results table to:
--   documents, metrics, reference_ranges (new), samples
-- Fully idempotent — safe to run multiple times.
-- ============================================================

BEGIN;

-- ============================================================
-- 1. Create new tables (IF NOT EXISTS)
-- ============================================================

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    filename TEXT NOT NULL UNIQUE,
    file_hash TEXT,
    lab_name TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metrics (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit TEXT,
    scale TEXT DEFAULT 'linear',
    sort_order INTEGER
);

-- Temporary name to avoid collision with old reference_ranges
CREATE TABLE IF NOT EXISTS reference_ranges_v2 (
    id SERIAL PRIMARY KEY,
    metric TEXT NOT NULL REFERENCES metrics(name),
    range_type TEXT NOT NULL DEFAULT 'standard',
    sex TEXT,
    age_min INTEGER,
    age_max INTEGER,
    ref_low DOUBLE PRECISION,
    ref_high DOUBLE PRECISION,
    source TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_reference_range_v2
    ON reference_ranges_v2 (
        metric,
        range_type,
        COALESCE(sex, ''),
        COALESCE(age_min, -1),
        COALESCE(age_max, -1)
    );

CREATE TABLE IF NOT EXISTS samples (
    time TIMESTAMPTZ NOT NULL,
    metric TEXT NOT NULL REFERENCES metrics(name),
    value DOUBLE PRECISION,
    value_text TEXT,
    flag TEXT,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    PRIMARY KEY (time, metric, document_id)
);

-- TimescaleDB hypertable (graceful)
DO $$ BEGIN
    PERFORM create_hypertable('samples', 'time', if_not_exists => TRUE);
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB not available for samples table';
END $$;

-- ============================================================
-- 2. Populate metrics from old reference_ranges
-- ============================================================
-- Only runs if the old reference_ranges table exists (has 'measurement' PK)

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'reference_ranges'
          AND column_name = 'measurement'
    ) THEN
        -- Migrate metric definitions
        INSERT INTO metrics (name, display_name, category, unit, scale)
        SELECT measurement, measurement, COALESCE(category, 'Other'), unit, COALESCE(scale, 'linear')
        FROM reference_ranges
        ON CONFLICT (name) DO NOTHING;

        RAISE NOTICE 'Migrated metrics from old reference_ranges';
    END IF;
END $$;

-- ============================================================
-- 3. Ensure metrics exist for all measurements in lab_results
-- ============================================================
-- Handles measurements that exist in lab_results but not reference_ranges

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'lab_results' AND table_type = 'BASE TABLE'
    ) THEN
        INSERT INTO metrics (name, display_name, category, unit)
        SELECT DISTINCT lr.measurement, lr.measurement, lr.category,
               COALESCE(lr.unit, '')
        FROM lab_results lr
        WHERE NOT EXISTS (SELECT 1 FROM metrics WHERE name = lr.measurement)
        ON CONFLICT (name) DO NOTHING;

        RAISE NOTICE 'Ensured all lab_results measurements exist in metrics';
    END IF;
END $$;

-- ============================================================
-- 4. Populate documents from lab_results source files
-- ============================================================

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'lab_results' AND table_type = 'BASE TABLE'
    ) THEN
        INSERT INTO documents (date, filename)
        SELECT MIN(date)::date, source_file
        FROM lab_results
        WHERE source_file IS NOT NULL
        GROUP BY source_file
        ON CONFLICT (filename) DO NOTHING;

        RAISE NOTICE 'Migrated documents from lab_results';
    END IF;
END $$;

-- ============================================================
-- 5. Populate samples from lab_results
-- ============================================================

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'lab_results' AND table_type = 'BASE TABLE'
    ) THEN
        INSERT INTO samples (time, metric, value, value_text, flag, document_id)
        SELECT lr.date, lr.measurement, lr.value, lr.value_text, lr.flag, d.id
        FROM lab_results lr
        JOIN documents d ON d.filename = lr.source_file
        ON CONFLICT (time, metric, document_id) DO NOTHING;

        RAISE NOTICE 'Migrated samples from lab_results';
    END IF;
END $$;

-- ============================================================
-- 6. Populate reference_ranges_v2 from old reference_ranges
-- ============================================================

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'reference_ranges'
          AND column_name = 'measurement'
    ) THEN
        INSERT INTO reference_ranges_v2 (metric, range_type, ref_low, ref_high, source)
        SELECT measurement, 'standard', reference_low, reference_high, 'migration'
        FROM reference_ranges
        WHERE reference_low IS NOT NULL OR reference_high IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_reference_range_v2 DO NOTHING;

        RAISE NOTICE 'Migrated reference ranges';
    END IF;
END $$;

-- ============================================================
-- 7. Drop old tables, rename v2
-- ============================================================

-- Drop old lab_results (the base table, not a view)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'lab_results' AND table_type = 'BASE TABLE'
    ) THEN
        DROP TABLE lab_results CASCADE;
        RAISE NOTICE 'Dropped old lab_results table';
    END IF;
END $$;

-- Drop old reference_ranges (has 'measurement' PK, not 'metric' FK)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'reference_ranges'
          AND column_name = 'measurement'
    ) THEN
        DROP TABLE reference_ranges CASCADE;
        RAISE NOTICE 'Dropped old reference_ranges table';
    END IF;
END $$;

-- Rename v2 to final name (if v2 exists and final doesn't)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name = 'reference_ranges_v2'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'reference_ranges'
          AND table_type = 'BASE TABLE'
    ) THEN
        ALTER TABLE reference_ranges_v2 RENAME TO reference_ranges;
        ALTER INDEX IF EXISTS uq_reference_range_v2 RENAME TO uq_reference_range;
        RAISE NOTICE 'Renamed reference_ranges_v2 → reference_ranges';
    END IF;
END $$;

-- ============================================================
-- 8. Create backward-compatibility view
-- ============================================================

CREATE OR REPLACE VIEW lab_results AS
SELECT
    s.time AS date,
    m.category,
    s.metric AS measurement,
    s.value,
    s.value_text,
    m.unit,
    s.flag,
    d.filename AS source_file,
    d.processed_at AS extracted_at
FROM samples s
JOIN metrics m ON s.metric = m.name
JOIN documents d ON s.document_id = d.id;

-- ============================================================
-- 9. Create indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_documents_date ON documents (date);
CREATE INDEX IF NOT EXISTS idx_samples_metric ON samples (metric);
CREATE INDEX IF NOT EXISTS idx_samples_time ON samples (time);
CREATE INDEX IF NOT EXISTS idx_samples_document_id ON samples (document_id);
CREATE INDEX IF NOT EXISTS idx_reference_ranges_metric ON reference_ranges (metric);

COMMIT;
