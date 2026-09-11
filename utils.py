"""
Utility functions:
- PDF/OCR marks-list processing
- marks calculation
- grade calculation
- question-paper validation
- PDF generation
"""

import os
import re
from io import BytesIO

import fitz
import pandas as pd
import pytesseract
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)


def build_text_pdf(title: str, text: str) -> bytes:
    """Create a simple printable PDF."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 8),
    ]

    for paragraph in text.split("\n"):
        if paragraph.strip():
            story.append(Paragraph(paragraph.replace("&", "&amp;"), styles["BodyText"]))
            story.append(Spacer(1, 4))

    doc.build(story)
    return buffer.getvalue()


def build_question_paper_pdf(
    school, exam_type, class_name, subject, subject_code,
    exam_time, total_marks, text
) -> bytes:
    """Make a printable A4 question-paper PDF from generated text."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    center = ParagraphStyle(
        "center",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=10,
    )
    story = [
        Paragraph(f"<b>{school}</b>", styles["Title"]),
        Paragraph(exam_type, center),
        Spacer(1, 6),
        Paragraph(
            f"Class: {class_name} &nbsp;&nbsp; Subject: {subject} "
            f"&nbsp;&nbsp; Code: {subject_code}",
            center,
        ),
        Paragraph(
            f"Time: {exam_time} &nbsp;&nbsp; Total Marks: {total_marks}",
            center,
        ),
        Spacer(1, 12),
    ]

    for line in text.splitlines():
        safe = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        if safe.strip():
            story.append(Paragraph(safe, styles["BodyText"]))
            story.append(Spacer(1, 4))

    doc.build(story)
    return buffer.getvalue()


def _normalise(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def detect_columns(df: pd.DataFrame) -> dict:
    """Find common award-list column names without forcing one exact format."""
    aliases = {
        "roll_number": ["roll no", "roll number", "roll", "roll_no", "rollnumber"],
        "student_name": ["student name", "name", "student"],
        "subject": ["subject", "subject name"],
        "subject_code": ["subject code", "code", "subject_code"],
        "marks": ["marks", "obtained marks", "obtained", "score"],
        "total_marks": ["total marks", "maximum marks", "max marks", "total"],
        "father_name": ["father name", "father", "guardian"],
        "class": ["class", "grade"],
        "section": ["section"],
    }

    normalized = {_normalise(c): c for c in df.columns}
    found = {}

    for key, names in aliases.items():
        for alias in names:
            if alias in normalized:
                found[key] = normalized[alias]
                break
    return found


def extract_marks_file(uploaded_file) -> pd.DataFrame:
    """Read Excel/CSV directly, or OCR a PDF/image marks list."""
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()

    if name.endswith(".csv"):
        return pd.read_csv(BytesIO(data))

    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(BytesIO(data))

    text = ""
    if name.endswith(".pdf"):
        doc = fitz.open(stream=data, filetype="pdf")
        for page in doc:
            page_text = page.get_text("text")
            if page_text.strip():
                text += "\n" + page_text
            else:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                image = Image.frombytes(
                    "RGB", [pix.width, pix.height], pix.samples
                )
                text += "\n" + pytesseract.image_to_string(image)
        doc.close()
    elif name.endswith((".jpg", ".jpeg", ".png")):
        image = Image.open(BytesIO(data)).convert("RGB")
        text = pytesseract.image_to_string(image)
    else:
        raise ValueError("Unsupported marks file type.")

    return text_to_marks_dataframe(text)


def text_to_marks_dataframe(text: str) -> pd.DataFrame:
    """
    Convert simple OCR/text award-list rows into a DataFrame.

    Expected practical format:
    Roll No | Student Name | Subject Code | Subject | Marks
    """
    rows = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        if not line:
            continue

        # Accept pipes, tabs, commas, or multiple spaces as separators.
        parts = [p.strip() for p in re.split(r"\||\t|,", line) if p.strip()]
        if len(parts) >= 5:
            rows.append(parts[:5])

    if not rows:
        raise ValueError(
            "Could not identify tabular marks data in the PDF/image. "
            "For best results, upload Excel or CSV."
        )

    first = [x.lower() for x in rows[0]]
    header_words = {"roll", "roll no", "roll number", "student name", "subject"}
    if any(word in " ".join(first) for word in header_words):
        rows = rows[1:]

    df = pd.DataFrame(
        rows,
        columns=["Roll No", "Student Name", "Subject Code", "Subject", "Marks"],
    )
    return df


def default_grade_rules():
    return [
        (90, 100, "A+"),
        (80, 89.999, "A"),
        (70, 79.999, "B"),
        (60, 69.999, "C"),
        (50, 59.999, "D"),
        (0, 49.999, "E"),
    ]


def calculate_grade(percentage: float, rules=None) -> str:
    rules = rules or default_grade_rules()
    for low, high, grade in rules:
        if low <= percentage <= high:
            return grade
    return "N/A"


def calculate_result(
    df: pd.DataFrame,
    roll_number: str,
    subject_query: str,
    total_marks: int,
    pass_percentage: float = 50.0,
):
    """Safely match roll + subject/code and calculate the result."""
    columns = detect_columns(df)
    if "roll_number" not in columns:
        raise ValueError("Award list needs a Roll Number column.")
    if "marks" not in columns:
        raise ValueError("Award list needs a Marks column.")

    roll_col = columns["roll_number"]
    subject_col = columns.get("subject")
    code_col = columns.get("subject_code")

    matches = df[
        df[roll_col].astype(str).str.strip().str.lower()
        == str(roll_number).strip().lower()
    ].copy()

    if subject_query and not matches.empty:
        q = str(subject_query).strip().lower()
        if subject_col:
            mask = matches[subject_col].astype(str).str.strip().str.lower() == q
        else:
            mask = False

        if code_col:
            mask = mask | (
                matches[code_col].astype(str).str.strip().str.lower() == q
            )
        matches = matches[mask]

    if matches.empty:
        return None

    row = matches.iloc[0]
    try:
        obtained = float(str(row[columns["marks"]]).replace(",", ""))
    except ValueError as exc:
        raise ValueError("Obtained marks are not numeric.") from exc

    percentage = round((obtained / total_marks) * 100, 2)
    grade = calculate_grade(percentage)

    return {
        "roll_number": str(row[roll_col]),
        "student_name": str(row[columns.get("student_name", roll_col)]),
        "class": str(row[columns["class"]]) if "class" in columns else "",
        "section": str(row[columns["section"]]) if "section" in columns else "",
        "subject": str(row[subject_col]) if subject_col else subject_query,
        "subject_code": str(row[code_col]) if code_col else "",
        "obtained_marks": obtained,
        "total_marks": total_marks,
        "percentage": percentage,
        "grade": grade,
        "result": "PASS" if percentage >= pass_percentage else "FAIL",
    }


def validate_question_paper(
    text: str,
    expected_total: int,
    expected_mcqs: int,
    expected_short: int,
    expected_long: int,
) -> dict:
    """Basic non-LLM validation. It reports warnings rather than silently changing content."""
    warnings = []
    upper = text.upper()

    for section in ["SECTION A", "SECTION B", "SECTION C"]:
        if section not in upper:
            warnings.append(f"{section} was not clearly found in the generated output.")

    # Count question labels approximately.
    mcq_area = upper.split("SECTION B")[0] if "SECTION B" in upper else upper
    short_area = (
        upper.split("SECTION B")[1].split("SECTION C")[0]
        if "SECTION B" in upper and "SECTION C" in upper
        else ""
    )
    long_area = upper.split("SECTION C")[1] if "SECTION C" in upper else ""

    mcq_found = len(re.findall(r"\bQ?\d+[\.\)]", mcq_area))
    short_found = len(re.findall(r"\bQ?\d+[\.\)]", short_area))
    long_found = len(re.findall(r"\bQ?\d+[\.\)]", long_area))

    if mcq_found < expected_mcqs:
        warnings.append(f"MCQ count may be low: found about {mcq_found}, expected {expected_mcqs}.")
    if short_found < expected_short:
        warnings.append(f"Short-question count may be low: found about {short_found}, expected {expected_short}.")
    if long_found < expected_long:
        warnings.append(f"Long-question count may be low: found about {long_found}, expected {expected_long}.")

    return {"warnings": warnings}


def make_question_paper_text(metadata: dict, paper: str) -> str:
    """Convenience helper for other callers."""
    return (
        f"{metadata.get('school', '')}\n"
        f"{metadata.get('exam_type', '')}\n"
        f"Class: {metadata.get('class', '')}\n"
        f"Subject: {metadata.get('subject', '')}\n"
        f"Total Marks: {metadata.get('total_marks', '')}\n\n"
        f"{paper}"
    )


def dataframe_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def build_certificate_pdf(
    school_name: str,
    exam_type: str,
    academic_year: str,
    student: dict,
    father_name: str = "",
    section: str = "",
    teacher_name: str = "",
) -> bytes:
    """Generate an A4 detailed marks certificate."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()
    center_title = ParagraphStyle(
        "CertificateTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=17,
        leading=22,
    )
    center = ParagraphStyle(
        "CertificateCenter",
        parent=styles["Normal"],
        alignment=TA_CENTER,
    )

    story = [
        Paragraph(school_name or "SCHOOL", center_title),
        Paragraph(exam_type or "Examination", center),
        Paragraph(f"Academic Year: {academic_year}", center),
        Spacer(1, 10),
        Paragraph("DETAILED MARKS CERTIFICATE", center_title),
        Spacer(1, 12),
        Paragraph(
            f"<b>Student Name:</b> {student.get('student_name', '')}<br/>"
            f"<b>Father Name:</b> {father_name}<br/>"
            f"<b>Roll Number:</b> {student.get('roll_number', '')}<br/>"
            f"<b>Class:</b> {student.get('class', '')}<br/>"
            f"<b>Section:</b> {section or student.get('section', '')}",
            styles["BodyText"],
        ),
        Spacer(1, 12),
    ]

    table_data = [
        ["Subject", "Subject Code", "Total Marks", "Obtained", "Percentage", "Grade"],
        [
            student.get("subject", ""),
            student.get("subject_code", ""),
            str(student.get("total_marks", "")),
            str(student.get("obtained_marks", "")),
            str(student.get("percentage", "")),
            student.get("grade", ""),
        ],
    ]
    table = Table(table_data, repeatRows=1, colWidths=[45 * mm, 28 * mm, 25 * mm, 25 * mm, 25 * mm, 18 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 15))

    story.append(
        Paragraph(
            f"<b>Obtained Marks:</b> {student.get('obtained_marks', '')} / "
            f"{student.get('total_marks', '')}<br/>"
            f"<b>Percentage:</b> {student.get('percentage', '')}%<br/>"
            f"<b>Grade:</b> {student.get('grade', '')}<br/>"
            f"<b>Result:</b> {student.get('result', '')}",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 30))
    story.append(
        Paragraph(
            f"Class Teacher: {teacher_name or '________________'}"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "Principal: ____________________",
            styles["BodyText"],
        )
    )

    doc.build(story)
    return buffer.getvalue()
