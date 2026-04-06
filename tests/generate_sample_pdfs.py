#!/usr/bin/env python3
"""
Generate realistic sample lab report PDFs for testing the extraction pipeline.
Requires: pip install reportlab
"""

import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable, KeepTogether
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.colors import HexColor

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "sample_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Colour palette ──────────────────────────────────────────────────────────
DARK_BLUE   = HexColor("#1a3a5c")
MID_BLUE    = HexColor("#2e6da4")
LIGHT_BLUE  = HexColor("#dce8f5")
PALE_GREY   = HexColor("#f5f5f5")
FLAG_RED    = HexColor("#c0392b")
FLAG_BG     = HexColor("#fdf0ee")
DARK_TEXT   = HexColor("#1a1a1a")
MID_GREY    = HexColor("#555555")
BORDER_GREY = HexColor("#cccccc")
GREEN       = HexColor("#1e7b4b")

# ─── Style helpers ────────────────────────────────────────────────────────────

def base_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='LabHeader1',
        fontName='Helvetica-Bold',
        fontSize=20,
        textColor=DARK_BLUE,
        spaceAfter=2,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='LabHeader2',
        fontName='Helvetica',
        fontSize=13,
        textColor=MID_BLUE,
        spaceAfter=6,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='PatientLabel',
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=MID_GREY,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        name='PatientValue',
        fontName='Helvetica',
        fontSize=9,
        textColor=DARK_TEXT,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        name='SectionTitle',
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=DARK_BLUE,
        spaceBefore=10,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name='NoteText',
        fontName='Helvetica',
        fontSize=9,
        textColor=MID_GREY,
        leading=14,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name='Footer',
        fontName='Helvetica',
        fontSize=7.5,
        textColor=MID_GREY,
        alignment=TA_CENTER,
    ))
    return styles


def header_table(lab_name, report_title, styles):
    """Return a 2-column header row: lab name left, title right."""
    left  = Paragraph(lab_name,    styles['LabHeader1'])
    right = Paragraph(report_title, styles['LabHeader2'])
    tbl = Table([[left, right]], colWidths=[3.5*inch, 3.5*inch])
    tbl.setStyle(TableStyle([
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN',       (0,0), (0,0),   'LEFT'),
        ('ALIGN',       (1,0), (1,0),   'RIGHT'),
        ('BOTTOMPADDING',(0,0),(-1,-1), 4),
    ]))
    return tbl


def patient_info_table(fields, styles):
    """
    fields: list of (label, value) pairs
    Renders as a shaded box with 2-column label/value layout.
    """
    rows = []
    for label, value in fields:
        rows.append([
            Paragraph(label, styles['PatientLabel']),
            Paragraph(value, styles['PatientValue']),
        ])
    tbl = Table(rows, colWidths=[1.5*inch, 5.5*inch])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (-1,-1), PALE_GREY),
        ('BOX',          (0,0), (-1,-1), 0.5, BORDER_GREY),
        ('INNERGRID',    (0,0), (-1,-1), 0.25, BORDER_GREY),
        ('TOPPADDING',   (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
        ('LEFTPADDING',  (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
    ]))
    return tbl


def results_table(headers, rows_data, col_widths, flag_col=4):
    """
    Build a styled results table.
    flag_col: 0-based index of the Flag column (-1 to disable flag colouring).
    """
    # Build header row
    header_cells = [
        Paragraph(f'<b>{h}</b>', ParagraphStyle(
            name=f'TH_{h}', fontName='Helvetica-Bold', fontSize=9,
            textColor=colors.white, alignment=TA_CENTER
        ))
        for h in headers
    ]
    table_data = [header_cells]

    flag_rows = []
    for i, row in enumerate(rows_data):
        cells = []
        is_flagged = False
        for j, cell in enumerate(row):
            align = TA_CENTER if j != 0 else TA_LEFT
            style = ParagraphStyle(
                name=f'TD_{i}_{j}',
                fontName='Helvetica',
                fontSize=9,
                textColor=DARK_TEXT,
                alignment=align,
                leading=13,
            )
            if j == flag_col and cell and cell.strip():
                is_flagged = True
                style.fontName = 'Helvetica-Bold'
                style.textColor = FLAG_RED
            cells.append(Paragraph(str(cell) if cell is not None else '', style))
        if is_flagged:
            flag_rows.append(i + 1)  # +1 for header
        table_data.append(cells)

    tbl = Table(table_data, colWidths=col_widths)

    base_style = [
        # Header
        ('BACKGROUND',    (0,0), (-1,0), DARK_BLUE),
        ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
        ('ALIGN',         (0,0), (-1,0), 'CENTER'),
        ('TOPPADDING',    (0,0), (-1,0), 7),
        ('BOTTOMPADDING', (0,0), (-1,0), 7),
        # Body
        ('FONTNAME',      (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',      (0,1), (-1,-1), 9),
        ('TOPPADDING',    (0,1), (-1,-1), 5),
        ('BOTTOMPADDING', (0,1), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
        ('ALIGN',         (1,1), (-1,-1), 'CENTER'),
        ('ALIGN',         (0,1), (0,-1),  'LEFT'),
        ('BOX',           (0,0), (-1,-1), 0.5, BORDER_GREY),
        ('LINEBELOW',     (0,0), (-1,-1), 0.25, BORDER_GREY),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, PALE_GREY]),
    ]

    # Highlight flagged rows
    for row_idx in flag_rows:
        base_style.append(('BACKGROUND', (0,row_idx), (-1,row_idx), FLAG_BG))

    tbl.setStyle(TableStyle(base_style))
    return tbl


def make_doc(path, styles):
    doc = SimpleDocTemplate(
        path,
        pagesize=letter,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
    )
    return doc


def footer_paragraph(text, styles):
    return Paragraph(text, styles['Footer'])


# ─── PDF 1: Complete Blood Count ─────────────────────────────────────────────

def generate_cbc(styles):
    path = os.path.join(OUTPUT_DIR, "complete_blood_count_2024.pdf")
    doc  = make_doc(path, styles)
    story = []

    # Header
    story.append(header_table("Central Medical Laboratory", "Lab Results Report", styles))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE, spaceAfter=8))

    # Patient info
    story.append(patient_info_table([
        ("Patient Name:", "John Doe"),
        ("Date of Birth:", "February 13, 1991"),
        ("Report Date:",   "June 15, 2024"),
        ("Ordering Physician:", "Dr. Sarah Mitchell, MD"),
        ("Specimen Type:", "Venous Blood"),
        ("Lab ID:",        "CML-2024-061501"),
    ], styles))
    story.append(Spacer(1, 12))

    # Section title
    story.append(Paragraph("COMPLETE BLOOD COUNT (CBC) WITH DIFFERENTIAL", styles['SectionTitle']))
    story.append(Spacer(1, 4))

    headers = ["Test", "Result", "Unit", "Reference Range", "Flag"]
    rows = [
        ["WBC",            "7.2",   "x10E9/L",  "3.4 – 10.0",   ""],
        ["RBC",            "4.8",   "x10E12/L", "4.5 – 5.5",    ""],
        ["Hemoglobin",     "14.5",  "g/dL",     "13.5 – 17.5",  ""],
        ["Hematocrit",     "43",    "%",         "38 – 50",      ""],
        ["Platelets",      "250",   "x10E9/L",  "140 – 400",    ""],
        ["MCV",            "89.6",  "fL",        "80 – 100",     ""],
        ["MCH",            "30.2",  "pg",        "27 – 33",      ""],
        ["MCHC",           "33.7",  "g/dL",     "32 – 36",      ""],
        ["RDW",            "12.8",  "%",         "11.5 – 14.5",  ""],
        ["Neutrophils %",  "55",    "%",         "40 – 74",      ""],
        ["Lymphocytes %",  "33",    "%",         "19 – 48",      ""],
        ["Monocytes %",    "8",     "%",         "3.4 – 9",      ""],
        ["Eosinophils %",  "3",     "%",         "0 – 7",        ""],
        ["Basophils %",    "1",     "%",         "0 – 1.5",      ""],
    ]

    col_widths = [2.2*inch, 1.0*inch, 1.2*inch, 1.8*inch, 0.8*inch]
    story.append(results_table(headers, rows, col_widths, flag_col=4))
    story.append(Spacer(1, 16))

    # Interpretation note
    story.append(Paragraph("INTERPRETATION", styles['SectionTitle']))
    story.append(Paragraph(
        "All CBC parameters are within normal reference ranges. No abnormalities detected. "
        "The differential count is unremarkable. Recommend routine follow-up per clinical protocol.",
        styles['NoteText']
    ))
    story.append(Spacer(1, 24))

    # Footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_GREY, spaceAfter=6))
    story.append(footer_paragraph(
        "Central Medical Laboratory  |  123 Diagnostics Avenue, Suite 400, Boston, MA 02114  |  "
        "Tel: (617) 555-0192  |  CLIA#: 22D0694312\n"
        "Results are confidential and intended solely for the ordering physician. "
        "Reference ranges may vary by age, sex, and instrument.", styles))

    doc.build(story)
    print(f"  Created: {path}")
    return path


# ─── PDF 2: Comprehensive Metabolic Panel ────────────────────────────────────

def generate_metabolic(styles):
    path = os.path.join(OUTPUT_DIR, "metabolic_panel_2024.pdf")
    doc  = make_doc(path, styles)
    story = []

    story.append(header_table("Nordic Health Diagnostics", "Comprehensive Metabolic Panel", styles))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE, spaceAfter=8))

    story.append(patient_info_table([
        ("Patient Name:",        "John Doe"),
        ("Date of Birth:",       "February 13, 1991"),
        ("Report Date:",         "August 20, 2024"),
        ("Ordering Physician:",  "Dr. Erik Lindqvist, MD"),
        ("Specimen Type:",       "Serum"),
        ("Lab ID:",              "NHD-2024-082001"),
    ], styles))
    story.append(Spacer(1, 12))

    story.append(Paragraph("COMPREHENSIVE METABOLIC PANEL (CMP-14)", styles['SectionTitle']))
    story.append(Spacer(1, 4))

    headers = ["Test", "Result", "Unit", "Reference Range", "Flag"]
    rows = [
        ["Glucose",         "105",   "mg/dL",  "65 – 99",       "H"],
        ["BUN",             "15",    "mg/dL",  "7 – 25",        ""],
        ["Creatinine",      "0.9",   "mg/dL",  "0.6 – 1.29",   ""],
        ["eGFR",            ">90",   "mL/min", "≥ 60",          ""],
        ["Sodium",          "140",   "mmol/L", "136 – 145",     ""],
        ["Potassium",       "4.2",   "mmol/L", "3.5 – 5.1",    ""],
        ["Chloride",        "101",   "mmol/L", "98 – 110",      ""],
        ["CO2",             "24",    "mmol/L", "20 – 32",       ""],
        ["Calcium",         "9.5",   "mg/dL",  "8.6 – 10.3",   ""],
        ["Total Protein",   "7.1",   "g/dL",   "6.0 – 8.3",    ""],
        ["Albumin",         "4.5",   "g/dL",   "3.6 – 5.1",    ""],
        ["Total Bilirubin", "0.8",   "mg/dL",  "0.2 – 1.2",   ""],
        ["ALT",             "25",    "U/L",    "9 – 46",        ""],
        ["AST",             "22",    "U/L",    "10 – 40",       ""],
        ["Alk Phos",        "65",    "U/L",    "36 – 130",      ""],
    ]

    col_widths = [2.2*inch, 1.0*inch, 1.1*inch, 1.8*inch, 0.9*inch]
    story.append(results_table(headers, rows, col_widths, flag_col=4))
    story.append(Spacer(1, 16))

    story.append(Paragraph("CLINICAL NOTES", styles['SectionTitle']))
    story.append(Paragraph(
        "<b>Glucose (H):</b> Fasting glucose is mildly elevated at 105 mg/dL, above the normal upper limit "
        "of 99 mg/dL. This falls within the impaired fasting glucose (pre-diabetic) range of 100–125 mg/dL. "
        "Clinical correlation and repeat testing recommended. Lifestyle modification counselling advised.",
        styles['NoteText']
    ))
    story.append(Paragraph(
        "Kidney function (BUN, Creatinine, eGFR) and electrolytes are within normal limits. "
        "Liver function tests (ALT, AST, Alk Phos, Bilirubin) are all normal.",
        styles['NoteText']
    ))
    story.append(Spacer(1, 24))

    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_GREY, spaceAfter=6))
    story.append(footer_paragraph(
        "Nordic Health Diagnostics  |  88 Scandia Way, Minneapolis, MN 55402  |  "
        "Tel: (612) 555-0377  |  CLIA#: 24D1122934\n"
        "Flagged values are highlighted for clinical attention. "
        "H = Above high reference limit  |  L = Below low reference limit", styles))

    doc.build(story)
    print(f"  Created: {path}")
    return path


# ─── PDF 3: Thyroid + Lipid Panel ────────────────────────────────────────────

def generate_thyroid_lipid(styles):
    path = os.path.join(OUTPUT_DIR, "thyroid_lipid_2024.pdf")
    doc  = make_doc(path, styles)
    story = []

    story.append(header_table("University Hospital Lab", "Laboratory Report", styles))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE, spaceAfter=8))

    story.append(patient_info_table([
        ("Patient Name:",        "John Doe"),
        ("Date of Birth:",       "February 13, 1991"),
        ("Report Date:",         "November 10, 2024"),
        ("Ordering Physician:",  "Dr. Amara Osei, MD, FACE"),
        ("Specimen Type:",       "Serum / Plasma"),
        ("Lab ID:",              "UHL-2024-111001"),
    ], styles))
    story.append(Spacer(1, 12))

    # ── Thyroid section
    story.append(Paragraph("THYROID FUNCTION PANEL", styles['SectionTitle']))
    story.append(Spacer(1, 4))

    thyroid_headers = ["Test", "Result", "Unit", "Reference Range", "Flag"]
    thyroid_rows = [
        ["TSH",      "2.5",  "mIU/L", "0.4 – 4.0",  ""],
        ["Free T4",  "1.2",  "ng/dL", "0.8 – 1.8",  ""],
        ["Free T3",  "3.1",  "pg/mL", "2.3 – 4.2",  ""],
    ]
    col_widths = [2.2*inch, 1.0*inch, 1.1*inch, 1.8*inch, 0.9*inch]
    story.append(results_table(thyroid_headers, thyroid_rows, col_widths, flag_col=4))
    story.append(Spacer(1, 14))

    # ── Lipid section
    story.append(Paragraph("LIPID PANEL (FASTING)", styles['SectionTitle']))
    story.append(Spacer(1, 4))

    lipid_rows = [
        ["Total Cholesterol",  "195",  "mg/dL", "< 200",   ""],
        ["HDL Cholesterol",    "55",   "mg/dL", "> 40",    ""],
        ["LDL Cholesterol",    "120",  "mg/dL", "< 130",   ""],
        ["Triglycerides",      "100",  "mg/dL", "< 150",   ""],
    ]
    story.append(results_table(thyroid_headers, lipid_rows, col_widths, flag_col=4))
    story.append(Spacer(1, 14))

    # ── Vitamins section
    story.append(Paragraph("VITAMIN LEVELS", styles['SectionTitle']))
    story.append(Spacer(1, 4))

    vitamin_rows = [
        ["Vitamin D (25-OH)",  "32",   "ng/mL", "30 – 100",   ""],
        ["Vitamin B12",        "450",  "pg/mL", "200 – 900",  ""],
    ]
    story.append(results_table(thyroid_headers, vitamin_rows, col_widths, flag_col=4))
    story.append(Spacer(1, 18))

    # ── Follow-up note
    story.append(KeepTogether([
        Paragraph("PHYSICIAN'S NOTES & FOLLOW-UP RECOMMENDATIONS", styles['SectionTitle']),
        Spacer(1, 4),
        Paragraph(
            "Thyroid function is within normal limits with TSH of 2.5 mIU/L (optimal range 1.0–2.5 mIU/L), "
            "Free T4 of 1.2 ng/dL, and Free T3 of 3.1 pg/mL. No evidence of thyroid dysfunction.",
            styles['NoteText']
        ),
        Paragraph(
            "Lipid profile is favourable: Total Cholesterol 195 mg/dL (below 200 mg/dL threshold), "
            "HDL 55 mg/dL (cardioprotective), LDL 120 mg/dL (borderline — target < 100 mg/dL for "
            "high-risk patients), and Triglycerides 100 mg/dL (well within range).",
            styles['NoteText']
        ),
        Paragraph(
            "Vitamin D is marginally sufficient at 32 ng/mL. Patient should maintain supplementation "
            "(1000–2000 IU/day) and recheck in 6 months. Vitamin B12 is adequate.",
            styles['NoteText']
        ),
        Spacer(1, 6),
        Paragraph(
            "<b>Recommended follow-up actions:</b>",
            styles['NoteText']
        ),
        Paragraph(
            "1. Schedule follow-up appointment in 3 months for repeat fasting glucose and HbA1c assessment.<br/>"
            "2. Continue Vitamin D supplementation; recheck 25-OH Vitamin D in 6 months.<br/>"
            "3. LDL target reassessment: discuss cardiovascular risk stratification with patient.<br/>"
            "4. Annual thyroid function recheck recommended given patient history.<br/>"
            "5. Lifestyle counselling: Mediterranean diet, 150 min/week moderate exercise.",
            styles['NoteText']
        ),
    ]))
    story.append(Spacer(1, 24))

    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_GREY, spaceAfter=6))
    story.append(footer_paragraph(
        "University Hospital Laboratory  |  500 Medical Campus Drive, Chicago, IL 60611  |  "
        "Tel: (312) 555-0848  |  CLIA#: 14D0987561\n"
        "This report is for physician use only. Results should be interpreted in the context of the patient's "
        "clinical presentation. H = High  |  L = Low  |  Reference ranges are for adult males.", styles))

    doc.build(story)
    print(f"  Created: {path}")
    return path


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    styles = base_styles()
    print(f"Generating sample PDFs into: {OUTPUT_DIR}")
    generate_cbc(styles)
    generate_metabolic(styles)
    generate_thyroid_lipid(styles)
    print("Done — 3 PDF lab reports generated successfully.")
