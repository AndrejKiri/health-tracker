"""
LLM prompt templates for the health data extraction service.

The system prompt is constructed once at import time by embedding the full
known measurement catalogue from reference_ranges.json.  The user prompt
wraps the raw PDF text passed to the LLM.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Known measurement catalogue (embedded from reference_ranges.json)
# Categories and measurement names must exactly match the reference data model
# so that extracted results can be joined with reference ranges downstream.
# ---------------------------------------------------------------------------

KNOWN_MEASUREMENTS: list[dict] = [
    {"measurement": "A/G Ratio", "unit": "", "category": "Liver Panel"},
    {"measurement": "ACTH", "unit": "pg/mL", "category": "Endocrine"},
    {"measurement": "ALT", "unit": "U/L", "category": "Liver Panel"},
    {"measurement": "AST", "unit": "U/L", "category": "Liver Panel"},
    {"measurement": "Abs Basophils", "unit": "x10E9/L", "category": "WBC Differential (absolute)"},
    {"measurement": "Abs Eosinophils", "unit": "x10E9/L", "category": "WBC Differential (absolute)"},
    {"measurement": "Abs Immature Granulocytes", "unit": "x10E9/L", "category": "WBC Differential (absolute)"},
    {"measurement": "Abs Lymphocytes", "unit": "x10E9/L", "category": "WBC Differential (absolute)"},
    {"measurement": "Abs Monocytes", "unit": "x10E9/L", "category": "WBC Differential (absolute)"},
    {"measurement": "Abs Neutrophils", "unit": "x10E9/L", "category": "WBC Differential (absolute)"},
    {"measurement": "Albumin", "unit": "g/dL", "category": "Liver Panel"},
    {"measurement": "Alk Phos", "unit": "U/L", "category": "Liver Panel"},
    {"measurement": "Anion Gap", "unit": "", "category": "Metabolic Panel"},
    {"measurement": "Apolipoprotein B", "unit": "mg/dL", "category": "Lipid Panel"},
    {"measurement": "BNP", "unit": "pg/mL", "category": "Cardiac Markers"},
    {"measurement": "BUN", "unit": "mg/dL", "category": "Metabolic Panel"},
    {"measurement": "BUN/Creatinine Ratio", "unit": "", "category": "Other"},
    {"measurement": "Base Excess", "unit": "mmol/L", "category": "Blood Gas"},
    {"measurement": "Basophils %", "unit": "%", "category": "WBC Differential (%)"},
    {"measurement": "CD16/CD56 NK Cells %", "unit": "% Lymphs", "category": "Lymphocyte Subsets"},
    {"measurement": "CD19 B Cells %", "unit": "% Lymphs", "category": "Lymphocyte Subsets"},
    {"measurement": "CD19 B Cells Abs", "unit": "x10E6/L", "category": "Lymphocyte Subsets"},
    {"measurement": "CD3 T Cells %", "unit": "% Lymphs", "category": "Lymphocyte Subsets"},
    {"measurement": "CD3 T Cells Abs", "unit": "x10E6/L", "category": "Lymphocyte Subsets"},
    {"measurement": "CD4 T Cells %", "unit": "% Lymphs", "category": "Lymphocyte Subsets"},
    {"measurement": "CD4 T Cells Abs", "unit": "x10E6/L", "category": "Lymphocyte Subsets"},
    {"measurement": "CD4/CD8 Ratio", "unit": "ratio", "category": "Lymphocyte Subsets"},
    {"measurement": "CD8 T Cells %", "unit": "% Lymphs", "category": "Lymphocyte Subsets"},
    {"measurement": "CD8 T Cells Abs", "unit": "x10E6/L", "category": "Lymphocyte Subsets"},
    {"measurement": "CK", "unit": "U/L", "category": "Cardiac Markers"},
    {"measurement": "CK-MB", "unit": "ug/L", "category": "Cardiac Markers"},
    {"measurement": "CO2", "unit": "mmol/L", "category": "Metabolic Panel"},
    {"measurement": "CRP", "unit": "mg/L", "category": "Inflammatory Markers"},
    {"measurement": "Calcium", "unit": "mg/dL", "category": "Metabolic Panel"},
    {"measurement": "Chloride", "unit": "mmol/L", "category": "Metabolic Panel"},
    {"measurement": "Cholesterol/HDL Ratio", "unit": "", "category": "Lipid Panel"},
    {"measurement": "Cortisol", "unit": "ug/dL", "category": "Endocrine"},
    {"measurement": "Creatinine", "unit": "mg/dL", "category": "Metabolic Panel"},
    {"measurement": "Direct Bilirubin", "unit": "mg/dL", "category": "Liver Panel"},
    {"measurement": "ESR", "unit": "mm/h", "category": "Inflammatory Markers"},
    {"measurement": "Eosinophils %", "unit": "%", "category": "WBC Differential (%)"},
    {"measurement": "Ferritin", "unit": "ng/mL", "category": "Iron Studies"},
    {"measurement": "Fibrinogen", "unit": "mg/dL", "category": "Coagulation"},
    {"measurement": "Folate", "unit": "ng/mL", "category": "Vitamins"},
    {"measurement": "Free T3", "unit": "pg/mL", "category": "Thyroid"},
    {"measurement": "Free T4", "unit": "ng/dL", "category": "Thyroid"},
    {"measurement": "GGT", "unit": "U/L", "category": "Liver Panel"},
    {"measurement": "Globulin", "unit": "g/dL", "category": "Liver Panel"},
    {"measurement": "Glucose", "unit": "mg/dL", "category": "Metabolic Panel"},
    {"measurement": "Glucose, Urine", "unit": "mg/dL", "category": "Other"},
    {"measurement": "HDL Cholesterol", "unit": "mg/dL", "category": "Lipid Panel"},
    {"measurement": "Hematocrit", "unit": "%", "category": "Complete Blood Count"},
    {"measurement": "Hemoglobin", "unit": "g/dL", "category": "Complete Blood Count"},
    {"measurement": "Hemoglobin A1c", "unit": "%", "category": "Other Chemistry"},
    {"measurement": "IL-6", "unit": "pg/mL", "category": "Inflammatory Markers"},
    {"measurement": "INR", "unit": "", "category": "Coagulation"},
    {"measurement": "Immature Granulocytes %", "unit": "%", "category": "WBC Differential (%)"},
    {"measurement": "Insulin", "unit": "uIU/mL", "category": "Endocrine"},
    {"measurement": "Ionized Calcium", "unit": "mmol/L", "category": "Other Chemistry"},
    {"measurement": "Iron", "unit": "mcg/dL", "category": "Iron Studies"},
    {"measurement": "Ketones, Urine", "unit": "mg/dL", "category": "Other"},
    {"measurement": "LDH", "unit": "U/L", "category": "Other Chemistry"},
    {"measurement": "LDL Cholesterol", "unit": "mg/dL", "category": "Lipid Panel"},
    {"measurement": "Lactate", "unit": "mmol/L", "category": "Other Chemistry"},
    {"measurement": "Lymphocytes %", "unit": "%", "category": "WBC Differential (%)"},
    {"measurement": "MCH", "unit": "pg", "category": "Complete Blood Count"},
    {"measurement": "MCHC", "unit": "g/dL", "category": "Complete Blood Count"},
    {"measurement": "MCV", "unit": "fL", "category": "Complete Blood Count"},
    {"measurement": "MPV", "unit": "fL", "category": "Complete Blood Count"},
    {"measurement": "Magnesium", "unit": "mg/dL", "category": "Other Chemistry"},
    {"measurement": "Mean Plasma Glucose", "unit": "mg/dL", "category": "Other"},
    {"measurement": "Monocytes %", "unit": "%", "category": "WBC Differential (%)"},
    {"measurement": "Neutrophils %", "unit": "%", "category": "WBC Differential (%)"},
    {"measurement": "Non-HDL Cholesterol", "unit": "mg/dL", "category": "Lipid Panel"},
    {"measurement": "Nucleated RBC", "unit": "/100 WBC", "category": "Other"},
    {"measurement": "Oxygen Saturation", "unit": "%", "category": "Blood Gas"},
    {"measurement": "PCO2", "unit": "mm Hg", "category": "Blood Gas"},
    {"measurement": "PO2", "unit": "mm Hg", "category": "Blood Gas"},
    {"measurement": "PT", "unit": "sec", "category": "Coagulation"},
    {"measurement": "PTT", "unit": "sec", "category": "Coagulation"},
    {"measurement": "Phosphorus", "unit": "mg/dL", "category": "Other Chemistry"},
    {"measurement": "Platelets", "unit": "x10E9/L", "category": "Complete Blood Count"},
    {"measurement": "Potassium", "unit": "mmol/L", "category": "Metabolic Panel"},
    {"measurement": "Preliminary ANC", "unit": "x10E9/L", "category": "WBC Differential (absolute)"},
    {"measurement": "RBC", "unit": "x10E12/L", "category": "Complete Blood Count"},
    {"measurement": "RDW", "unit": "%", "category": "Complete Blood Count"},
    {"measurement": "Reticulocyte Count", "unit": "x10E9/L", "category": "Other"},
    {"measurement": "Sodium", "unit": "mmol/L", "category": "Metabolic Panel"},
    {"measurement": "Specific Gravity, Urine", "unit": "", "category": "Other"},
    {"measurement": "T3 Total", "unit": "ng/dL", "category": "Thyroid"},
    {"measurement": "T4 Total", "unit": "mcg/dL", "category": "Thyroid"},
    {"measurement": "TIBC", "unit": "mcg/dL", "category": "Iron Studies"},
    {"measurement": "TSH", "unit": "mIU/L", "category": "Thyroid"},
    {"measurement": "Total Bilirubin", "unit": "mg/dL", "category": "Liver Panel"},
    {"measurement": "Total Cholesterol", "unit": "mg/dL", "category": "Lipid Panel"},
    {"measurement": "Total Protein", "unit": "g/dL", "category": "Liver Panel"},
    {"measurement": "Transferrin Saturation", "unit": "%", "category": "Iron Studies"},
    {"measurement": "Triglycerides", "unit": "mg/dL", "category": "Lipid Panel"},
    {"measurement": "Troponin I", "unit": "ug/L", "category": "Cardiac Markers"},
    {"measurement": "Uric Acid", "unit": "mg/dL", "category": "Other Chemistry"},
    {"measurement": "Urine pH", "unit": "", "category": "Other"},
    {"measurement": "Vancomycin", "unit": "mg/L", "category": "Other"},
    {"measurement": "Vitamin B12", "unit": "pg/mL", "category": "Vitamins"},
    {"measurement": "Vitamin D", "unit": "ng/mL", "category": "Vitamins"},
    {"measurement": "WBC", "unit": "x10E9/L", "category": "Complete Blood Count"},
    {"measurement": "eGFR", "unit": "", "category": "Metabolic Panel"},
    {"measurement": "hsCRP", "unit": "mg/L", "category": "Inflammatory Markers"},
    {"measurement": "pH", "unit": "", "category": "Blood Gas"},
]

# Build a formatted catalogue string for embedding in the system prompt
_CATALOGUE_LINES = "\n".join(
    f"  - {m['measurement']} ({m['category']}) [{m['unit'] or 'no unit'}]"
    for m in KNOWN_MEASUREMENTS
)

# ---------------------------------------------------------------------------
# System prompt (built once at import time)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: str = f"""\
You are a medical data extraction assistant. Your job is to read raw text \
extracted from clinical lab reports and return ONLY a valid JSON object \
containing structured data. Never include explanations, apologies, or \
markdown outside the JSON code block.

## Output schema

Return a JSON object with exactly two top-level keys:

{{
  "lab_results": [ ... ],
  "events": [ ... ]
}}

### lab_results items

Each item must have these fields:
- "date"        : ISO 8601 date string (YYYY-MM-DD). REQUIRED.
- "category"    : Category string from the known list below, or "unknown".
- "measurement" : Measurement name. Prefer exact names from the known list.
- "value"       : Numeric value as a JSON number, or null if not numeric.
- "value_text"  : String for qualitative results (e.g. "Positive", "Trace"), \
or null.
- "unit"        : Unit string as reported (e.g. "mg/dL", "%").
- "flag"        : "H" if value is above reference range, "L" if below, null \
otherwise.

Rules:
- At least one of "value" or "value_text" must be non-null.
- Use the EXACT measurement names from the Known Measurements Catalogue when \
possible.
- If the lab uses a different name (e.g. "Lymphs" instead of "Lymphocytes %"), \
map it to the closest known name.
- If no match exists, use the name as printed and set category to "unknown".
- Parse ALL measurements found on the page, even if they appear in tabular form.
- If the same measurement appears on multiple dates, emit one item per date.

### events items

Each item must have these fields:
- "date"        : ISO 8601 date (YYYY-MM-DD). REQUIRED.
- "end_date"    : ISO 8601 date or null (for multi-day admissions/procedures).
- "category"    : One of: "Imaging", "Procedure", "Diagnosis", "Medication", \
"Vaccination", "Visit", "Other".
- "subcategory" : More specific type (e.g. "MRI", "CT", "Surgery") or null.
- "title"       : Short title (≤80 chars).
- "description" : Narrative description or null.

Include events for:
- Imaging studies (X-ray, MRI, CT, ultrasound, etc.)
- Surgical or interventional procedures
- Hospital admissions / discharges
- Notable diagnoses mentioned
- Medication changes noted in the report
- Vaccinations

## Known Measurements Catalogue

Use these exact names and categories when possible:

{_CATALOGUE_LINES}

## Few-shot examples

### Example 1 — Standard blood panel

Input text:
```
PATIENT: John Doe    DOB: 1975-03-15    COLLECTED: 2024-06-10
COMPLETE BLOOD COUNT
WBC        11.8  x10E9/L   [3.4-10.0]   H
RBC         4.92 x10E12/L  [4.5-5.5]
Hemoglobin 15.4  g/dL      [13.5-17.7]
Hematocrit 46.1  %         [41-53]
MCV        93.7  fL        [80-100]
MCH        31.3  pg        [27-33]
MCHC       33.4  g/dL      [32-36]
Platelets   212  x10E9/L   [150-400]
```

Expected output:
```json
{{
  "lab_results": [
    {{"date": "2024-06-10", "category": "Complete Blood Count", "measurement": "WBC", "value": 11.8, "value_text": null, "unit": "x10E9/L", "flag": "H"}},
    {{"date": "2024-06-10", "category": "Complete Blood Count", "measurement": "RBC", "value": 4.92, "value_text": null, "unit": "x10E12/L", "flag": null}},
    {{"date": "2024-06-10", "category": "Complete Blood Count", "measurement": "Hemoglobin", "value": 15.4, "value_text": null, "unit": "g/dL", "flag": null}},
    {{"date": "2024-06-10", "category": "Complete Blood Count", "measurement": "Hematocrit", "value": 46.1, "value_text": null, "unit": "%", "flag": null}},
    {{"date": "2024-06-10", "category": "Complete Blood Count", "measurement": "MCV", "value": 93.7, "value_text": null, "unit": "fL", "flag": null}},
    {{"date": "2024-06-10", "category": "Complete Blood Count", "measurement": "MCH", "value": 31.3, "value_text": null, "unit": "pg", "flag": null}},
    {{"date": "2024-06-10", "category": "Complete Blood Count", "measurement": "MCHC", "value": 33.4, "value_text": null, "unit": "g/dL", "flag": null}},
    {{"date": "2024-06-10", "category": "Complete Blood Count", "measurement": "Platelets", "value": 212, "value_text": null, "unit": "x10E9/L", "flag": null}}
  ],
  "events": []
}}
```

### Example 2 — Radiology report + lipid panel

Input text:
```
RADIOLOGY REPORT
Patient: Jane Smith    Date of Service: 2023-11-15
Procedure: CT Abdomen/Pelvis with contrast
Indication: Abdominal pain, rule out appendicitis
Findings: No acute intra-abdominal pathology identified.
Impression: Normal CT abdomen and pelvis.

LIPID PANEL   Collected: 2023-11-15
Total Cholesterol   182   mg/dL   [<200]
HDL Cholesterol      55   mg/dL   [40-60]
LDL Cholesterol      98   mg/dL   [<100]
Triglycerides       145   mg/dL   [<150]
Non-HDL Cholesterol 127   mg/dL
Cholesterol/HDL       3.3
```

Expected output:
```json
{{
  "lab_results": [
    {{"date": "2023-11-15", "category": "Lipid Panel", "measurement": "Total Cholesterol", "value": 182, "value_text": null, "unit": "mg/dL", "flag": null}},
    {{"date": "2023-11-15", "category": "Lipid Panel", "measurement": "HDL Cholesterol", "value": 55, "value_text": null, "unit": "mg/dL", "flag": null}},
    {{"date": "2023-11-15", "category": "Lipid Panel", "measurement": "LDL Cholesterol", "value": 98, "value_text": null, "unit": "mg/dL", "flag": null}},
    {{"date": "2023-11-15", "category": "Lipid Panel", "measurement": "Triglycerides", "value": 145, "value_text": null, "unit": "mg/dL", "flag": null}},
    {{"date": "2023-11-15", "category": "Lipid Panel", "measurement": "Non-HDL Cholesterol", "value": 127, "value_text": null, "unit": "mg/dL", "flag": null}},
    {{"date": "2023-11-15", "category": "Lipid Panel", "measurement": "Cholesterol/HDL Ratio", "value": 3.3, "value_text": null, "unit": "", "flag": null}}
  ],
  "events": [
    {{
      "date": "2023-11-15",
      "end_date": null,
      "category": "Imaging",
      "subcategory": "CT",
      "title": "CT Abdomen/Pelvis with contrast",
      "description": "No acute intra-abdominal pathology. Normal CT abdomen and pelvis."
    }}
  ]
}}
```

### Example 3 — Qualitative result + hospital admission

Input text:
```
DISCHARGE SUMMARY
Admitted: 2022-11-10    Discharged: 2022-11-14
Diagnosis: Community-acquired pneumonia

URINALYSIS    Collected: 2022-11-10
Color          Yellow       Normal
Clarity        Clear        Normal
Specific Grav  1.015
pH             6.0
Protein        Negative
Glucose        Negative
Ketones        Trace
Blood          Negative

THYROID FUNCTION    Collected: 2022-11-10
TSH        2.45   mIU/L   [0.4-4.5]
Free T4    1.22   ng/dL   [0.8-1.8]
Free T3    3.10   pg/mL   [2.3-4.2]
```

Expected output:
```json
{{
  "lab_results": [
    {{"date": "2022-11-10", "category": "Other", "measurement": "Specific Gravity, Urine", "value": 1.015, "value_text": null, "unit": "", "flag": null}},
    {{"date": "2022-11-10", "category": "Blood Gas", "measurement": "pH", "value": 6.0, "value_text": null, "unit": "", "flag": null}},
    {{"date": "2022-11-10", "category": "Other", "measurement": "Ketones, Urine", "value": null, "value_text": "Trace", "unit": "mg/dL", "flag": null}},
    {{"date": "2022-11-10", "category": "Thyroid", "measurement": "TSH", "value": 2.45, "value_text": null, "unit": "mIU/L", "flag": null}},
    {{"date": "2022-11-10", "category": "Thyroid", "measurement": "Free T4", "value": 1.22, "value_text": null, "unit": "ng/dL", "flag": null}},
    {{"date": "2022-11-10", "category": "Thyroid", "measurement": "Free T3", "value": 3.10, "value_text": null, "unit": "pg/mL", "flag": null}}
  ],
  "events": [
    {{
      "date": "2022-11-10",
      "end_date": "2022-11-14",
      "category": "Visit",
      "subcategory": "Inpatient",
      "title": "Hospital admission — Community-acquired pneumonia",
      "description": "Admitted with community-acquired pneumonia. Discharged 2022-11-14."
    }}
  ]
}}
```

## Final instructions

- Return ONLY valid JSON wrapped in a ```json ... ``` code block.
- Do NOT include any text before or after the JSON block.
- If the document contains no lab results, return {{"lab_results": [], "events": []}}.
- Dates must be in YYYY-MM-DD format.  If only a year+month is given, use \
the first of the month.
- Strip commas from numbers (e.g. "1,234" → 1234).
- Ignore obviously erroneous or illegible values; set value to null and \
value_text to the raw string if the text is present but unparseable.
"""

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

_USER_TEMPLATE = """\
Extract all lab results and medical events from the following clinical \
document text.

<document>
{text}
</document>
"""


def build_user_prompt(text: str) -> str:
    """
    Build the user-turn prompt by inserting the PDF text into the template.

    Parameters
    ----------
    text : str
        Raw text extracted from the PDF.

    Returns
    -------
    str
        Formatted user prompt ready to send to the LLM.
    """
    return _USER_TEMPLATE.format(text=text)
