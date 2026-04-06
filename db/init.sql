-- Enable TimescaleDB if available (graceful fallback to plain PostgreSQL)
DO $$ BEGIN
    CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB extension not available — using plain PostgreSQL';
END $$;

-- Lab results table (main time-series data)
CREATE TABLE IF NOT EXISTS lab_results (
    id SERIAL,
    date TIMESTAMPTZ NOT NULL,
    category TEXT NOT NULL,
    measurement TEXT NOT NULL,
    value DOUBLE PRECISION,
    value_text TEXT,  -- for non-numeric like "not_detected"
    unit TEXT,
    flag TEXT,  -- H, L, or NULL
    source_file TEXT,
    extracted_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, date)
);

-- Convert to hypertable (TimescaleDB) — wrapped in DO block for graceful failure
DO $$ BEGIN
    PERFORM create_hypertable('lab_results', 'date', if_not_exists => TRUE);
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB not available, using regular table';
END $$;

-- Reference ranges
CREATE TABLE IF NOT EXISTS reference_ranges (
    measurement TEXT PRIMARY KEY,
    category TEXT,
    unit TEXT,
    reference_low DOUBLE PRECISION,
    reference_high DOUBLE PRECISION,
    scale TEXT DEFAULT 'linear'
);

-- Medical events (procedures, imaging, treatments, etc.)
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

-- PDF processing log
CREATE TABLE IF NOT EXISTS pdf_processing_log (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    file_hash TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT NOT NULL,  -- success, failed, duplicate
    error_message TEXT,
    records_extracted INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_lab_results_measurement ON lab_results (measurement);
CREATE INDEX IF NOT EXISTS idx_lab_results_category ON lab_results (category);
CREATE INDEX IF NOT EXISTS idx_lab_results_date ON lab_results (date);
CREATE INDEX IF NOT EXISTS idx_events_date ON events (date);
CREATE INDEX IF NOT EXISTS idx_events_category ON events (category);
CREATE INDEX IF NOT EXISTS idx_pdf_log_filename ON pdf_processing_log (filename);

-- ============================================================
-- Reference Ranges (from reference_ranges.json)
-- ============================================================

INSERT INTO reference_ranges (measurement, category, unit, reference_low, reference_high, scale) VALUES
  ('A/G Ratio', 'Liver Panel', '', 1, 2.5, 'linear'),
  ('ACTH', 'Endocrine', 'pg/mL', NULL, NULL, 'linear'),
  ('ALT', 'Liver Panel', 'U/L', 9, 46, 'linear'),
  ('AST', 'Liver Panel', 'U/L', 10, 40, 'linear'),
  ('Abs Basophils', 'WBC Differential (absolute)', 'x10E9/L', 0, 0.2, 'linear'),
  ('Abs Eosinophils', 'WBC Differential (absolute)', 'x10E9/L', 0.015, 0.5, 'linear'),
  ('Abs Immature Granulocytes', 'WBC Differential (absolute)', 'x10E9/L', NULL, NULL, 'linear'),
  ('Abs Lymphocytes', 'WBC Differential (absolute)', 'x10E9/L', 1, 3.4, 'linear'),
  ('Abs Monocytes', 'WBC Differential (absolute)', 'x10E9/L', 0.2, 0.95, 'linear'),
  ('Abs Neutrophils', 'WBC Differential (absolute)', 'x10E9/L', 1.5, 7.8, 'linear'),
  ('Albumin', 'Liver Panel', 'g/dL', 3.6, 5.1, 'linear'),
  ('Alk Phos', 'Liver Panel', 'U/L', 36, 130, 'linear'),
  ('Anion Gap', 'Metabolic Panel', '', 3, 12, 'linear'),
  ('Apolipoprotein B', 'Lipid Panel', 'mg/dL', NULL, NULL, 'linear'),
  ('BNP', 'Cardiac Markers', 'pg/mL', NULL, NULL, 'linear'),
  ('BUN', 'Metabolic Panel', 'mg/dL', 7, 25, 'linear'),
  ('BUN/Creatinine Ratio', 'Other', '', NULL, NULL, 'linear'),
  ('Base Excess', 'Blood Gas', 'mmol/L', NULL, NULL, 'linear'),
  ('Basophils %', 'WBC Differential (%)', '%', 0, 1, 'linear'),
  ('CD16/CD56 NK Cells %', 'Lymphocyte Subsets', '% Lymphs', NULL, NULL, 'linear'),
  ('CD19 B Cells %', 'Lymphocyte Subsets', '% Lymphs', NULL, NULL, 'linear'),
  ('CD19 B Cells Abs', 'Lymphocyte Subsets', 'x10E6/L', NULL, NULL, 'linear'),
  ('CD3 T Cells %', 'Lymphocyte Subsets', '% Lymphs', NULL, NULL, 'linear'),
  ('CD3 T Cells Abs', 'Lymphocyte Subsets', 'x10E6/L', NULL, NULL, 'linear'),
  ('CD4 T Cells %', 'Lymphocyte Subsets', '% Lymphs', NULL, NULL, 'linear'),
  ('CD4 T Cells Abs', 'Lymphocyte Subsets', 'x10E6/L', NULL, NULL, 'linear'),
  ('CD4/CD8 Ratio', 'Lymphocyte Subsets', 'ratio', NULL, NULL, 'linear'),
  ('CD8 T Cells %', 'Lymphocyte Subsets', '% Lymphs', NULL, NULL, 'linear'),
  ('CD8 T Cells Abs', 'Lymphocyte Subsets', 'x10E6/L', NULL, NULL, 'linear'),
  ('CK', 'Cardiac Markers', 'U/L', 44, 196, 'linear'),
  ('CK-MB', 'Cardiac Markers', 'ug/L', NULL, NULL, 'linear'),
  ('CO2', 'Metabolic Panel', 'mmol/L', 20, 32, 'linear'),
  ('CRP', 'Inflammatory Markers', 'mg/L', 0, 5, 'logarithmic'),
  ('Calcium', 'Metabolic Panel', 'mg/dL', 8.6, 10.3, 'linear'),
  ('Chloride', 'Metabolic Panel', 'mmol/L', 98, 110, 'linear'),
  ('Cholesterol/HDL Ratio', 'Lipid Panel', '', NULL, NULL, 'linear'),
  ('Cortisol', 'Endocrine', 'ug/dL', NULL, NULL, 'linear'),
  ('Creatinine', 'Metabolic Panel', 'mg/dL', 0.6, 1.29, 'linear'),
  ('Direct Bilirubin', 'Liver Panel', 'mg/dL', 0, 0.2, 'linear'),
  ('ESR', 'Inflammatory Markers', 'mm/h', 0, 15, 'linear'),
  ('Eosinophils %', 'WBC Differential (%)', '%', 1, 4, 'linear'),
  ('Ferritin', 'Iron Studies', 'ng/mL', 38, 380, 'linear'),
  ('Fibrinogen', 'Coagulation', 'mg/dL', NULL, NULL, 'linear'),
  ('Folate', 'Vitamins', 'ng/mL', NULL, NULL, 'linear'),
  ('Free T3', 'Thyroid', 'pg/mL', 2.3, 4.2, 'linear'),
  ('Free T4', 'Thyroid', 'ng/dL', 0.8, 1.8, 'linear'),
  ('GGT', 'Liver Panel', 'U/L', NULL, NULL, 'linear'),
  ('Globulin', 'Liver Panel', 'g/dL', 2, 3.5, 'linear'),
  ('Glucose', 'Metabolic Panel', 'mg/dL', 70, 100, 'linear'),
  ('Glucose, Urine', 'Other', 'mg/dL', NULL, NULL, 'linear')
ON CONFLICT (measurement) DO UPDATE SET
  category = EXCLUDED.category,
  unit = EXCLUDED.unit,
  reference_low = EXCLUDED.reference_low,
  reference_high = EXCLUDED.reference_high,
  scale = EXCLUDED.scale;

INSERT INTO reference_ranges (measurement, category, unit, reference_low, reference_high, scale) VALUES
  ('HDL Cholesterol', 'Lipid Panel', 'mg/dL', 40, 60, 'linear'),
  ('Hematocrit', 'Complete Blood Count', '%', 41, 53, 'linear'),
  ('Hemoglobin', 'Complete Blood Count', 'g/dL', 13.5, 17.7, 'linear'),
  ('Hemoglobin A1c', 'Other Chemistry', '%', 4, 5.6, 'linear'),
  ('IL-6', 'Inflammatory Markers', 'pg/mL', NULL, NULL, 'logarithmic'),
  ('INR', 'Coagulation', '', 0.8, 1.2, 'linear'),
  ('Immature Granulocytes %', 'WBC Differential (%)', '%', NULL, NULL, 'linear'),
  ('Insulin', 'Endocrine', 'uIU/mL', NULL, NULL, 'linear'),
  ('Ionized Calcium', 'Other Chemistry', 'mmol/L', NULL, NULL, 'linear'),
  ('Iron', 'Iron Studies', 'mcg/dL', 60, 170, 'linear'),
  ('Ketones, Urine', 'Other', 'mg/dL', NULL, NULL, 'linear'),
  ('LDH', 'Other Chemistry', 'U/L', 120, 246, 'linear'),
  ('LDL Cholesterol', 'Lipid Panel', 'mg/dL', 0, 100, 'linear'),
  ('Lactate', 'Other Chemistry', 'mmol/L', NULL, NULL, 'linear'),
  ('Lymphocytes %', 'WBC Differential (%)', '%', 20, 40, 'linear'),
  ('MCH', 'Complete Blood Count', 'pg', 27, 33, 'linear'),
  ('MCHC', 'Complete Blood Count', 'g/dL', 32, 36, 'linear'),
  ('MCV', 'Complete Blood Count', 'fL', 80, 100, 'linear'),
  ('MPV', 'Complete Blood Count', 'fL', 7.5, 12.5, 'linear'),
  ('Magnesium', 'Other Chemistry', 'mg/dL', 1.7, 2.2, 'linear'),
  ('Mean Plasma Glucose', 'Other', 'mg/dL', NULL, NULL, 'linear'),
  ('Monocytes %', 'WBC Differential (%)', '%', 2, 8, 'linear'),
  ('Neutrophils %', 'WBC Differential (%)', '%', 40, 70, 'linear'),
  ('Non-HDL Cholesterol', 'Lipid Panel', 'mg/dL', NULL, NULL, 'linear'),
  ('Nucleated RBC', 'Other', '/100 WBC', NULL, NULL, 'linear'),
  ('Oxygen Saturation', 'Blood Gas', '%', NULL, NULL, 'linear'),
  ('PCO2', 'Blood Gas', 'mm Hg', NULL, NULL, 'linear'),
  ('PO2', 'Blood Gas', 'mm Hg', NULL, NULL, 'linear'),
  ('PT', 'Coagulation', 'sec', 11, 14, 'linear'),
  ('PTT', 'Coagulation', 'sec', 25, 35, 'linear'),
  ('Phosphorus', 'Other Chemistry', 'mg/dL', NULL, NULL, 'linear'),
  ('Platelets', 'Complete Blood Count', 'x10E9/L', 150, 400, 'linear'),
  ('Potassium', 'Metabolic Panel', 'mmol/L', 3.5, 5.1, 'linear'),
  ('Preliminary ANC', 'WBC Differential (absolute)', 'x10E9/L', NULL, NULL, 'linear'),
  ('RBC', 'Complete Blood Count', 'x10E12/L', 4.5, 5.5, 'linear'),
  ('RDW', 'Complete Blood Count', '%', 11.5, 14.5, 'linear'),
  ('Reticulocyte Count', 'Other', 'x10E9/L', NULL, NULL, 'linear'),
  ('Sodium', 'Metabolic Panel', 'mmol/L', 136, 145, 'linear'),
  ('Specific Gravity, Urine', 'Other', '', NULL, NULL, 'linear'),
  ('T3 Total', 'Thyroid', 'ng/dL', 87, 167, 'linear'),
  ('T4 Total', 'Thyroid', 'mcg/dL', 4.9, 10.5, 'linear'),
  ('TIBC', 'Iron Studies', 'mcg/dL', 250, 370, 'linear'),
  ('TSH', 'Thyroid', 'mIU/L', 0.4, 4.5, 'logarithmic'),
  ('Total Bilirubin', 'Liver Panel', 'mg/dL', 0.1, 1.2, 'linear'),
  ('Total Cholesterol', 'Lipid Panel', 'mg/dL', 0, 200, 'linear'),
  ('Total Protein', 'Liver Panel', 'g/dL', 6, 8.3, 'linear'),
  ('Transferrin Saturation', 'Iron Studies', '%', 20, 50, 'linear'),
  ('Triglycerides', 'Lipid Panel', 'mg/dL', 0, 150, 'linear'),
  ('Troponin I', 'Cardiac Markers', 'ug/L', NULL, NULL, 'linear'),
  ('Uric Acid', 'Other Chemistry', 'mg/dL', NULL, NULL, 'linear')
ON CONFLICT (measurement) DO UPDATE SET
  category = EXCLUDED.category,
  unit = EXCLUDED.unit,
  reference_low = EXCLUDED.reference_low,
  reference_high = EXCLUDED.reference_high,
  scale = EXCLUDED.scale;

INSERT INTO reference_ranges (measurement, category, unit, reference_low, reference_high, scale) VALUES
  ('Urine pH', 'Other', '', NULL, NULL, 'linear'),
  ('Vancomycin', 'Other', 'mg/L', NULL, NULL, 'linear'),
  ('Vitamin B12', 'Vitamins', 'pg/mL', 200, 900, 'linear'),
  ('Vitamin D', 'Vitamins', 'ng/mL', 30, 100, 'linear'),
  ('WBC', 'Complete Blood Count', 'x10E9/L', 3.4, 10, 'linear'),
  ('eGFR', 'Metabolic Panel', '', NULL, NULL, 'linear'),
  ('hsCRP', 'Inflammatory Markers', 'mg/L', 0, 1, 'logarithmic'),
  ('pH', 'Blood Gas', '', NULL, NULL, 'linear')
ON CONFLICT (measurement) DO UPDATE SET
  category = EXCLUDED.category,
  unit = EXCLUDED.unit,
  reference_low = EXCLUDED.reference_low,
  reference_high = EXCLUDED.reference_high,
  scale = EXCLUDED.scale;
