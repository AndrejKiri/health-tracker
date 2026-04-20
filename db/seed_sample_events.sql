-- Sample medical events spanning the lab-results date range.
-- Run after seed_sample_data.sql to populate the events timeline panel.

INSERT INTO events (date, end_date, category, subcategory, title, description, source_file) VALUES
  ('2022-11-14', NULL, 'Visit',       'Annual Physical',    'Annual physical exam',                'Routine checkup, no concerns noted.',                    'seed'),
  ('2023-01-08', NULL, 'Vaccination', 'Influenza',          'Seasonal flu shot',                   'Quadrivalent inactivated influenza vaccine.',            'seed'),
  ('2023-03-22', NULL, 'Imaging',     'MRI',                'MRI lumbar spine',                    'Evaluation for lower back pain. No acute findings.',     'seed'),
  ('2023-06-10', '2023-06-10', 'Procedure', 'Endoscopy',    'Upper GI endoscopy',                  'Mild gastritis; biopsy negative.',                       'seed'),
  ('2023-09-02', NULL, 'Diagnosis',   'Dermatology',        'Eczema diagnosis',                    'Atopic dermatitis, mild.',                               'seed'),
  ('2023-11-18', NULL, 'Visit',       'Cardiology',         'Cardiology consult',                  'Baseline ECG normal.',                                   'seed'),
  ('2024-02-05', NULL, 'Vaccination', 'COVID-19',           'COVID-19 booster',                    'Updated 2023–24 formulation.',                           'seed'),
  ('2024-04-19', NULL, 'Imaging',     'Ultrasound',         'Abdominal ultrasound',                'Liver, gallbladder, pancreas unremarkable.',             'seed'),
  ('2024-07-30', NULL, 'Medication',  'Start',              'Started atorvastatin 10 mg',          'Initiated for borderline LDL.',                          'seed'),
  ('2024-10-12', NULL, 'Visit',       'Annual Physical',    'Annual physical exam',                'BP slightly elevated, recheck in 3 months.',             'seed'),
  ('2025-01-20', '2025-01-20', 'Procedure', 'Minor surgery','Mole excision (right shoulder)',      'Benign nevus, excised completely.',                      'seed'),
  ('2025-04-07', NULL, 'Imaging',     'X-ray',              'Chest X-ray',                         'No acute cardiopulmonary disease.',                      'seed'),
  ('2025-06-25', NULL, 'Vaccination', 'Tdap',               'Tdap booster',                        'Routine 10-year booster.',                               'seed'),
  ('2025-09-14', NULL, 'Diagnosis',   'Endocrinology',      'Pre-diabetes noted',                  'HbA1c 5.9%; lifestyle counseling.',                      'seed'),
  ('2025-12-03', NULL, 'Visit',       'Dermatology',        'Annual skin check',                   'Full-body exam, no suspicious lesions.',                 'seed'),
  ('2026-02-15', NULL, 'Imaging',     'MRI',                'MRI brain with contrast',             'Follow-up for occasional migraines; no abnormalities.',  'seed')
ON CONFLICT DO NOTHING;
