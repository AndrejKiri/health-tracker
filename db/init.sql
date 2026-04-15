-- ============================================================
-- Health Tracker — Database Schema (Prometheus-inspired model)
-- ============================================================
-- Four core tables:
--   documents        — source lab reports (≈ Prometheus scrape targets)
--   metrics          — measurement definitions (≈ TYPE/HELP/UNIT)
--   reference_ranges — multi-dimensional thresholds
--   samples          — time-series data (≈ TSDB)
-- Plus:
--   events           — medical events (imaging, procedures, etc.)
--   pdf_processing_log — extraction pipeline audit trail
-- ============================================================

-- Enable TimescaleDB if available (graceful fallback to plain PostgreSQL)
DO $$ BEGIN
    CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB extension not available — using plain PostgreSQL';
END $$;

-- ============================================================
-- Documents (source lab reports)
-- ============================================================

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    filename TEXT NOT NULL UNIQUE,
    file_hash TEXT,
    lab_name TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_date ON documents (date);

-- ============================================================
-- Metrics (measurement definitions)
-- ============================================================

CREATE TABLE IF NOT EXISTS metrics (
    name TEXT PRIMARY KEY,        -- display name, e.g. 'WBC', 'Hemoglobin'
    display_name TEXT NOT NULL,   -- same as name for now; future flexibility
    category TEXT NOT NULL,       -- e.g. 'Complete Blood Count'
    unit TEXT,                    -- e.g. 'x10E9/L', 'mg/dL'
    description TEXT,             -- clinical explanation shown in dashboard tooltips
    scale TEXT DEFAULT 'linear',  -- 'linear' or 'logarithmic'
    sort_order INTEGER            -- controls display position in dashboards
);

-- ============================================================
-- Reference Ranges (multi-dimensional thresholds)
-- ============================================================
-- A single metric can have multiple ranges:
--   range_type: 'standard' (lab flag thresholds), 'optimal', 'critical'
--   sex:        'M', 'F', or NULL (universal)
--   age range:  optional age brackets

CREATE TABLE IF NOT EXISTS reference_ranges (
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

-- Unique constraint for deduplication on upserts
CREATE UNIQUE INDEX IF NOT EXISTS uq_reference_range
    ON reference_ranges (
        metric,
        range_type,
        COALESCE(sex, ''),
        COALESCE(age_min, -1),
        COALESCE(age_max, -1)
    );

CREATE INDEX IF NOT EXISTS idx_reference_ranges_metric ON reference_ranges (metric);

-- ============================================================
-- Samples (time-series lab result data)
-- ============================================================

CREATE TABLE IF NOT EXISTS samples (
    time TIMESTAMPTZ NOT NULL,
    metric TEXT NOT NULL REFERENCES metrics(name),
    value DOUBLE PRECISION,
    value_text TEXT,              -- for non-numeric results, e.g. 'not detected'
    flag TEXT,                    -- 'H' (high), 'L' (low), or NULL
    document_id INTEGER NOT NULL REFERENCES documents(id),
    PRIMARY KEY (time, metric, document_id)
);

-- Convert to hypertable (TimescaleDB) — wrapped for graceful failure
DO $$ BEGIN
    PERFORM create_hypertable('samples', 'time', if_not_exists => TRUE);
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB not available, using regular table for samples';
END $$;

CREATE INDEX IF NOT EXISTS idx_samples_metric ON samples (metric);
CREATE INDEX IF NOT EXISTS idx_samples_time ON samples (time);
CREATE INDEX IF NOT EXISTS idx_samples_document_id ON samples (document_id);

-- ============================================================
-- Backward-compatibility view
-- ============================================================
-- Allows existing Grafana dashboards and CLI queries to keep working
-- with the old `lab_results` table shape during the transition.

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
-- Medical Events (unchanged from previous schema)
-- ============================================================

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    end_date DATE,
    category TEXT NOT NULL,
    subcategory TEXT,
    title TEXT NOT NULL,
    description TEXT,
    source_file TEXT,
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_date ON events (date);
CREATE INDEX IF NOT EXISTS idx_events_category ON events (category);

-- ============================================================
-- PDF Processing Log (unchanged from previous schema)
-- ============================================================

CREATE TABLE IF NOT EXISTS pdf_processing_log (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    file_hash TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT NOT NULL,  -- success, failed, duplicate
    error_message TEXT,
    records_extracted INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pdf_log_filename ON pdf_processing_log (filename);

-- ============================================================
-- Seed: Metrics (108 measurements)
-- ============================================================
-- sort_order groups by category, then alphabetical within category.
-- Categories ordered as they appear in the lab-results-overview dashboard.

INSERT INTO metrics (name, display_name, category, unit, scale, sort_order) VALUES
  -- Complete Blood Count (sort 100–109)
  ('WBC', 'WBC', 'Complete Blood Count', 'x10E9/L', 'linear', 100),
  ('RBC', 'RBC', 'Complete Blood Count', 'x10E12/L', 'linear', 101),
  ('Hemoglobin', 'Hemoglobin', 'Complete Blood Count', 'g/dL', 'linear', 102),
  ('Hematocrit', 'Hematocrit', 'Complete Blood Count', '%', 'linear', 103),
  ('Platelets', 'Platelets', 'Complete Blood Count', 'x10E9/L', 'linear', 104),
  ('MCV', 'MCV', 'Complete Blood Count', 'fL', 'linear', 105),
  ('MCH', 'MCH', 'Complete Blood Count', 'pg', 'linear', 106),
  ('MCHC', 'MCHC', 'Complete Blood Count', 'g/dL', 'linear', 107),
  ('RDW', 'RDW', 'Complete Blood Count', '%', 'linear', 108),
  ('MPV', 'MPV', 'Complete Blood Count', 'fL', 'linear', 109),

  -- WBC Differential (absolute) (sort 200–206)
  ('Abs Neutrophils', 'Abs Neutrophils', 'WBC Differential (absolute)', 'x10E9/L', 'linear', 200),
  ('Abs Lymphocytes', 'Abs Lymphocytes', 'WBC Differential (absolute)', 'x10E9/L', 'linear', 201),
  ('Abs Monocytes', 'Abs Monocytes', 'WBC Differential (absolute)', 'x10E9/L', 'linear', 202),
  ('Abs Eosinophils', 'Abs Eosinophils', 'WBC Differential (absolute)', 'x10E9/L', 'linear', 203),
  ('Abs Basophils', 'Abs Basophils', 'WBC Differential (absolute)', 'x10E9/L', 'linear', 204),
  ('Abs Immature Granulocytes', 'Abs Immature Granulocytes', 'WBC Differential (absolute)', 'x10E9/L', 'linear', 205),
  ('Preliminary ANC', 'Preliminary ANC', 'WBC Differential (absolute)', 'x10E9/L', 'linear', 206),

  -- WBC Differential (%) (sort 300–306)
  ('Neutrophils %', 'Neutrophils %', 'WBC Differential (%)', '%', 'linear', 300),
  ('Lymphocytes %', 'Lymphocytes %', 'WBC Differential (%)', '%', 'linear', 301),
  ('Monocytes %', 'Monocytes %', 'WBC Differential (%)', '%', 'linear', 302),
  ('Eosinophils %', 'Eosinophils %', 'WBC Differential (%)', '%', 'linear', 303),
  ('Basophils %', 'Basophils %', 'WBC Differential (%)', '%', 'linear', 304),
  ('Immature Granulocytes %', 'Immature Granulocytes %', 'WBC Differential (%)', '%', 'linear', 305),

  -- Metabolic Panel (sort 400–409)
  ('Glucose', 'Glucose', 'Metabolic Panel', 'mg/dL', 'linear', 400),
  ('BUN', 'BUN', 'Metabolic Panel', 'mg/dL', 'linear', 401),
  ('Creatinine', 'Creatinine', 'Metabolic Panel', 'mg/dL', 'linear', 402),
  ('eGFR', 'eGFR', 'Metabolic Panel', '', 'linear', 403),
  ('Sodium', 'Sodium', 'Metabolic Panel', 'mmol/L', 'linear', 404),
  ('Potassium', 'Potassium', 'Metabolic Panel', 'mmol/L', 'linear', 405),
  ('Chloride', 'Chloride', 'Metabolic Panel', 'mmol/L', 'linear', 406),
  ('CO2', 'CO2', 'Metabolic Panel', 'mmol/L', 'linear', 407),
  ('Calcium', 'Calcium', 'Metabolic Panel', 'mg/dL', 'linear', 408),
  ('Anion Gap', 'Anion Gap', 'Metabolic Panel', '', 'linear', 409),

  -- Liver Panel (sort 500–509)
  ('ALT', 'ALT', 'Liver Panel', 'U/L', 'linear', 500),
  ('AST', 'AST', 'Liver Panel', 'U/L', 'linear', 501),
  ('Alk Phos', 'Alk Phos', 'Liver Panel', 'U/L', 'linear', 502),
  ('Total Bilirubin', 'Total Bilirubin', 'Liver Panel', 'mg/dL', 'linear', 503),
  ('Direct Bilirubin', 'Direct Bilirubin', 'Liver Panel', 'mg/dL', 'linear', 504),
  ('GGT', 'GGT', 'Liver Panel', 'U/L', 'linear', 505),
  ('Albumin', 'Albumin', 'Liver Panel', 'g/dL', 'linear', 506),
  ('Total Protein', 'Total Protein', 'Liver Panel', 'g/dL', 'linear', 507),
  ('Globulin', 'Globulin', 'Liver Panel', 'g/dL', 'linear', 508),
  ('A/G Ratio', 'A/G Ratio', 'Liver Panel', '', 'linear', 509),

  -- Lipid Panel (sort 600–606)
  ('Total Cholesterol', 'Total Cholesterol', 'Lipid Panel', 'mg/dL', 'linear', 600),
  ('HDL Cholesterol', 'HDL Cholesterol', 'Lipid Panel', 'mg/dL', 'linear', 601),
  ('LDL Cholesterol', 'LDL Cholesterol', 'Lipid Panel', 'mg/dL', 'linear', 602),
  ('Triglycerides', 'Triglycerides', 'Lipid Panel', 'mg/dL', 'linear', 603),
  ('Non-HDL Cholesterol', 'Non-HDL Cholesterol', 'Lipid Panel', 'mg/dL', 'linear', 604),
  ('Apolipoprotein B', 'Apolipoprotein B', 'Lipid Panel', 'mg/dL', 'linear', 605),
  ('Cholesterol/HDL Ratio', 'Cholesterol/HDL Ratio', 'Lipid Panel', '', 'linear', 606),

  -- Thyroid (sort 700–704)
  ('TSH', 'TSH', 'Thyroid', 'mIU/L', 'logarithmic', 700),
  ('Free T4', 'Free T4', 'Thyroid', 'ng/dL', 'linear', 701),
  ('Free T3', 'Free T3', 'Thyroid', 'pg/mL', 'linear', 702),
  ('T4 Total', 'T4 Total', 'Thyroid', 'mcg/dL', 'linear', 703),
  ('T3 Total', 'T3 Total', 'Thyroid', 'ng/dL', 'linear', 704),

  -- Cardiac Markers (sort 800–803)
  ('Troponin I', 'Troponin I', 'Cardiac Markers', 'ug/L', 'linear', 800),
  ('CK', 'CK', 'Cardiac Markers', 'U/L', 'linear', 801),
  ('CK-MB', 'CK-MB', 'Cardiac Markers', 'ug/L', 'linear', 802),
  ('BNP', 'BNP', 'Cardiac Markers', 'pg/mL', 'linear', 803),

  -- Iron Studies (sort 900–903)
  ('Ferritin', 'Ferritin', 'Iron Studies', 'ng/mL', 'linear', 900),
  ('Iron', 'Iron', 'Iron Studies', 'mcg/dL', 'linear', 901),
  ('TIBC', 'TIBC', 'Iron Studies', 'mcg/dL', 'linear', 902),
  ('Transferrin Saturation', 'Transferrin Saturation', 'Iron Studies', '%', 'linear', 903),

  -- Coagulation (sort 1000–1003)
  ('PT', 'PT', 'Coagulation', 'sec', 'linear', 1000),
  ('PTT', 'PTT', 'Coagulation', 'sec', 'linear', 1001),
  ('INR', 'INR', 'Coagulation', '', 'linear', 1002),
  ('Fibrinogen', 'Fibrinogen', 'Coagulation', 'mg/dL', 'linear', 1003),

  -- Inflammatory Markers (sort 1100–1103)
  ('CRP', 'CRP', 'Inflammatory Markers', 'mg/L', 'logarithmic', 1100),
  ('hsCRP', 'hsCRP', 'Inflammatory Markers', 'mg/L', 'logarithmic', 1101),
  ('ESR', 'ESR', 'Inflammatory Markers', 'mm/h', 'linear', 1102),
  ('IL-6', 'IL-6', 'Inflammatory Markers', 'pg/mL', 'logarithmic', 1103),

  -- Endocrine (sort 1200–1202)
  ('Insulin', 'Insulin', 'Endocrine', 'uIU/mL', 'linear', 1200),
  ('Cortisol', 'Cortisol', 'Endocrine', 'ug/dL', 'linear', 1201),
  ('ACTH', 'ACTH', 'Endocrine', 'pg/mL', 'linear', 1202),

  -- Vitamins (sort 1300–1302)
  ('Vitamin D', 'Vitamin D', 'Vitamins', 'ng/mL', 'linear', 1300),
  ('Vitamin B12', 'Vitamin B12', 'Vitamins', 'pg/mL', 'linear', 1301),
  ('Folate', 'Folate', 'Vitamins', 'ng/mL', 'linear', 1302),

  -- Other Chemistry (sort 1400–1406)
  ('Hemoglobin A1c', 'Hemoglobin A1c', 'Other Chemistry', '%', 'linear', 1400),
  ('LDH', 'LDH', 'Other Chemistry', 'U/L', 'linear', 1401),
  ('Magnesium', 'Magnesium', 'Other Chemistry', 'mg/dL', 'linear', 1402),
  ('Ionized Calcium', 'Ionized Calcium', 'Other Chemistry', 'mmol/L', 'linear', 1403),
  ('Uric Acid', 'Uric Acid', 'Other Chemistry', 'mg/dL', 'linear', 1404),
  ('Phosphorus', 'Phosphorus', 'Other Chemistry', 'mg/dL', 'linear', 1405),
  ('Lactate', 'Lactate', 'Other Chemistry', 'mmol/L', 'linear', 1406),

  -- Lymphocyte Subsets (sort 1500–1509)
  ('CD3 T Cells %', 'CD3 T Cells %', 'Lymphocyte Subsets', '% Lymphs', 'linear', 1500),
  ('CD3 T Cells Abs', 'CD3 T Cells Abs', 'Lymphocyte Subsets', 'x10E6/L', 'linear', 1501),
  ('CD4 T Cells %', 'CD4 T Cells %', 'Lymphocyte Subsets', '% Lymphs', 'linear', 1502),
  ('CD4 T Cells Abs', 'CD4 T Cells Abs', 'Lymphocyte Subsets', 'x10E6/L', 'linear', 1503),
  ('CD8 T Cells %', 'CD8 T Cells %', 'Lymphocyte Subsets', '% Lymphs', 'linear', 1504),
  ('CD8 T Cells Abs', 'CD8 T Cells Abs', 'Lymphocyte Subsets', 'x10E6/L', 'linear', 1505),
  ('CD4/CD8 Ratio', 'CD4/CD8 Ratio', 'Lymphocyte Subsets', 'ratio', 'linear', 1506),
  ('CD19 B Cells %', 'CD19 B Cells %', 'Lymphocyte Subsets', '% Lymphs', 'linear', 1507),
  ('CD19 B Cells Abs', 'CD19 B Cells Abs', 'Lymphocyte Subsets', 'x10E6/L', 'linear', 1508),
  ('CD16/CD56 NK Cells %', 'CD16/CD56 NK Cells %', 'Lymphocyte Subsets', '% Lymphs', 'linear', 1509),

  -- Blood Gas (sort 1600–1604)
  ('pH', 'pH', 'Blood Gas', '', 'linear', 1600),
  ('PCO2', 'PCO2', 'Blood Gas', 'mm Hg', 'linear', 1601),
  ('PO2', 'PO2', 'Blood Gas', 'mm Hg', 'linear', 1602),
  ('Oxygen Saturation', 'Oxygen Saturation', 'Blood Gas', '%', 'linear', 1603),
  ('Base Excess', 'Base Excess', 'Blood Gas', 'mmol/L', 'linear', 1604),

  -- Urinalysis & Other (sort 1700–1710)
  ('BUN/Creatinine Ratio', 'BUN/Creatinine Ratio', 'Other', '', 'linear', 1700),
  ('Glucose, Urine', 'Glucose, Urine', 'Other', 'mg/dL', 'linear', 1701),
  ('Ketones, Urine', 'Ketones, Urine', 'Other', 'mg/dL', 'linear', 1702),
  ('Specific Gravity, Urine', 'Specific Gravity, Urine', 'Other', '', 'linear', 1703),
  ('Urine pH', 'Urine pH', 'Other', '', 'linear', 1704),
  ('Reticulocyte Count', 'Reticulocyte Count', 'Other', 'x10E9/L', 'linear', 1705),
  ('Nucleated RBC', 'Nucleated RBC', 'Other', '/100 WBC', 'linear', 1706),
  ('Mean Plasma Glucose', 'Mean Plasma Glucose', 'Other', 'mg/dL', 'linear', 1707),
  ('Vancomycin', 'Vancomycin', 'Other', 'mg/L', 'linear', 1708)
ON CONFLICT (name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  category     = EXCLUDED.category,
  unit         = EXCLUDED.unit,
  scale        = EXCLUDED.scale,
  sort_order   = EXCLUDED.sort_order;

-- ============================================================
-- Seed: Reference Ranges (standard, sex-unspecified unless noted)
-- ============================================================
-- NOTE: Several ranges are male-only. Future enhancement: add sex='F' rows.
--   Hematocrit   F: 36–46 %          M: 41–53 %
--   Hemoglobin   F: 12.0–15.5 g/dL   M: 13.5–17.7 g/dL
--   RBC          F: 3.9–5.2 x10E12/L M: 4.5–5.5 x10E12/L
--   Ferritin     F: 12–150 ng/mL     M: 38–380 ng/mL
--   CK           F: 26–140 U/L       M: 44–196 U/L

INSERT INTO reference_ranges (metric, range_type, ref_low, ref_high) VALUES
  ('WBC', 'standard', 3.4, 10),
  ('RBC', 'standard', 4.5, 5.5),
  ('Hemoglobin', 'standard', 13.5, 17.7),
  ('Hematocrit', 'standard', 41, 53),
  ('Platelets', 'standard', 150, 400),
  ('MCV', 'standard', 80, 100),
  ('MCH', 'standard', 27, 33),
  ('MCHC', 'standard', 32, 36),
  ('RDW', 'standard', 11.5, 14.5),
  ('MPV', 'standard', 7.5, 12.5),
  ('Abs Neutrophils', 'standard', 1.5, 7.8),
  ('Abs Lymphocytes', 'standard', 1, 3.4),
  ('Abs Monocytes', 'standard', 0.2, 0.95),
  ('Abs Eosinophils', 'standard', 0.015, 0.5),
  ('Abs Basophils', 'standard', 0, 0.2),
  ('Neutrophils %', 'standard', 40, 70),
  ('Lymphocytes %', 'standard', 20, 40),
  ('Monocytes %', 'standard', 2, 8),
  ('Eosinophils %', 'standard', 1, 4),
  ('Basophils %', 'standard', 0, 1),
  ('Glucose', 'standard', 70, 100),
  ('BUN', 'standard', 7, 25),
  ('Creatinine', 'standard', 0.6, 1.29),
  ('Sodium', 'standard', 136, 145),
  ('Potassium', 'standard', 3.5, 5.1),
  ('Chloride', 'standard', 98, 110),
  ('CO2', 'standard', 20, 32),
  ('Calcium', 'standard', 8.6, 10.3),
  ('Anion Gap', 'standard', 3, 12),
  ('ALT', 'standard', 9, 46),
  ('AST', 'standard', 10, 40),
  ('Alk Phos', 'standard', 36, 130),
  ('Total Bilirubin', 'standard', 0.1, 1.2),
  ('Direct Bilirubin', 'standard', 0, 0.2),
  ('Albumin', 'standard', 3.6, 5.1),
  ('Total Protein', 'standard', 6, 8.3),
  ('Globulin', 'standard', 2, 3.5),
  ('A/G Ratio', 'standard', 1, 2.5),
  ('Total Cholesterol', 'standard', 0, 200),
  ('HDL Cholesterol', 'standard', 40, 60),
  ('LDL Cholesterol', 'standard', 0, 100),
  ('Triglycerides', 'standard', 0, 150),
  ('TSH', 'standard', 0.4, 4.5),
  ('Free T4', 'standard', 0.8, 1.8),
  ('Free T3', 'standard', 2.3, 4.2),
  ('T4 Total', 'standard', 4.9, 10.5),
  ('T3 Total', 'standard', 87, 167),
  ('CK', 'standard', 44, 196),
  ('Ferritin', 'standard', 38, 380),
  ('Iron', 'standard', 60, 170),
  ('TIBC', 'standard', 250, 370),
  ('Transferrin Saturation', 'standard', 20, 50),
  ('PT', 'standard', 11, 14),
  ('PTT', 'standard', 25, 35),
  ('INR', 'standard', 0.8, 1.2),
  ('CRP', 'standard', 0, 5),
  ('hsCRP', 'standard', 0, 1),
  ('ESR', 'standard', 0, 15),
  ('Vitamin D', 'standard', 30, 100),
  ('Vitamin B12', 'standard', 200, 900),
  ('Hemoglobin A1c', 'standard', 4, 5.6),
  ('LDH', 'standard', 120, 246),
  ('Magnesium', 'standard', 1.7, 2.2)
ON CONFLICT (metric, range_type, COALESCE(sex, ''), COALESCE(age_min, -1), COALESCE(age_max, -1))
DO UPDATE SET
  ref_low  = EXCLUDED.ref_low,
  ref_high = EXCLUDED.ref_high;
