"""
utils.py: PDF extraction, OCR, mark calculations, PDF certificate rendering,
and QR Code attendance management (generation & decoding).
"""

import os
import io
import json
import datetime
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import pandas as pd
import qrcode
import cv2
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

tess_cmd = os.getenv("TESSERACT_CMD")
if tess_cmd:
    pytesseract.pytesseract.tesseract_cmd = tess_cmd


# -------------------------------------------------------------
# Document & Image Text Extraction
# -------------------------------------------------------------
def extract_text_from_file(file_path: str) -> list[dict]:
    if not file_path or not os.path.exists(file_path):
        return []

    ext = os.path.splitext(file_path)[1].lower()
    records = []
    base_name = os.path.basename(file_path)

    if ext == ".pdf":
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()

            if len(text) < 40:
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                try:
                    ocr_text = pytesseract.image_to_string(img).strip()
                    if len(ocr_text) > len(text):
                        text = ocr_text
                except Exception:
                    pass

            if text:
                records.append({"page": page_num + 1, "text": text, "source": base_name})
        doc.close()

    elif ext in [".jpg", ".jpeg", ".png"]:
        try:
            img = Image.open(file_path)
            ocr_text = pytesseract.image_to_string(img).strip()
            if ocr_text:
                records.append({"page": 1, "text": ocr_text, "source": base_name})
        except Exception as err:
            records.append({"page": 1, "text": f"Error performing OCR: {str(err)}", "source": base_name})

    return records


# -------------------------------------------------------------
# Marks & Award List Data Processing
# -------------------------------------------------------------
def parse_marks_file(file_path: str) -> pd.DataFrame:
    if not file_path or not os.path.exists(file_path):
        return pd.DataFrame()

    ext = os.path.splitext(file_path)[1].lower()
    df = pd.DataFrame()

    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        elif ext == ".csv":
            df = pd.read_csv(file_path)
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    cleaned_columns = {}
    for col in df.columns:
        norm = str(col).strip().lower().replace(" ", "_").replace(".", "")
        if "roll" in norm:
            cleaned_columns[col] = "roll_number"
        elif "student" in norm or "name" in norm:
            cleaned_columns[col] = "student_name"
        elif "subject_code" in norm or "code" in norm:
            cleaned_columns[col] = "subject_code"
        elif "subject" in norm:
            cleaned_columns[col] = "subject"
        elif "total" in norm:
            cleaned_columns[col] = "total_marks"
        elif "mark" in norm or "obtained" in norm:
            cleaned_columns[col] = "obtained_marks"
        else:
            cleaned_columns[col] = norm

    df = df.rename(columns=cleaned_columns)
    if "roll_number" in df.columns:
        df["roll_number"] = df["roll_number"].astype(str).str.strip()
    return df


def calculate_grade(percentage: float, criteria: dict = None) -> tuple[str, str]:
    if criteria is None:
        criteria = {"A+": 90, "A": 80, "B": 70, "C": 60, "D": 50, "Passing": 50}

    passing_thresh = criteria.get("Passing", 50)
    status = "Pass" if percentage >= passing_thresh else "Fail"

    if percentage >= criteria.get("A+", 90):
        grade = "A+"
    elif percentage >= criteria.get("A", 80):
        grade = "A"
    elif percentage >= criteria.get("B", 70):
        grade = "B"
    elif percentage >= criteria.get("C", 60):
        grade = "C"
    elif percentage >= criteria.get("D", 50):
        grade = "D"
    else:
        grade = "E"

    return grade, status


def lookup_student_record(df: pd.DataFrame, roll_no: str, subject_query: str = "") -> dict:
    if df.empty or "roll_number" not in df.columns:
        return {"error": "Award list data is missing or has no valid 'roll_number' column."}

    roll_no = str(roll_no).strip()
    matches = df[df["roll_number"] == roll_no]

    if matches.empty:
        return {"error": f"Roll Number '{roll_no}' not found in the uploaded list."}

    if subject_query and "subject" in matches.columns:
        subj_filtered = matches[matches["subject"].astype(str).str.contains(subject_query.strip(), case=False, na=False)]
        if not subj_filtered.empty:
            matches = subj_filtered

    record = matches.iloc[0].to_dict()
    obtained = float(record.get("obtained_marks", 0))
    total = float(record.get("total_marks", 100))
    percentage = round((obtained / total) * 100, 2) if total > 0 else 0.0
    grade, status = calculate_grade(percentage)

    record.update({
        "calculated_percentage": percentage,
        "calculated_grade": grade,
        "calculated_status": status
    })
    return record


# -------------------------------------------------------------
# QR Code Attendance Management
# -------------------------------------------------------------
def generate_student_qr_card(roll_no: str, name: str, class_name: str, output_path: str) -> str:
    """Creates a printable PNG attendance card containing a structured JSON QR code."""
    qr_data = json.dumps({"roll_no": str(roll_no).strip(), "name": str(name).strip(), "class": str(class_name).strip()})
    
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    card = Image.new("RGB", (360, 440), color="white")
    card.paste(qr_img, (30, 20))

    # Save to file
    card.save(output_path)
    return output_path


def decode_qr_image(image_input) -> dict:
    """
    Decodes QR code from an uploaded image or webcam frame using OpenCV.
    """
    if image_input is None:
        return {"error": "No image frame received."}

    if isinstance(image_input, str):
        img = cv2.imread(image_input)
    elif isinstance(image_input, np.ndarray):
        img = image_input
    elif isinstance(image_input, Image.Image):
        img = cv2.cvtColor(np.array(image_input), cv2.COLOR_RGB2BGR)
    else:
        return {"error": "Unsupported image format."}

    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(img)

    if not data:
        return {"error": "No valid QR code detected in the frame."}

    try:
        parsed = json.loads(data)
        return parsed
    except Exception:
        return {"raw_data": data}


def record_attendance(qr_data: dict, log_file: str = "attendance_log.csv") -> tuple[str, pd.DataFrame]:
    """
    Appends a verified attendance scan with a live timestamp to the attendance CSV.
    """
    if "error" in qr_data:
        return qr_data["error"], pd.DataFrame()

    roll_no = qr_data.get("roll_no") or qr_data.get("raw_data")
    name = qr_data.get("name", "N/A")
    cls_name = qr_data.get("class", "N/A")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    cols = ["Date", "Timestamp", "Roll Number", "Student Name", "Class", "Status"]
    if os.path.exists(log_file):
        df = pd.read_csv(log_file)
    else:
        df = pd.DataFrame(columns=cols)

    # Check if student already marked present today
    if not df.empty and "Date" in df.columns and "Roll Number" in df.columns:
        already_present = df[(df["Date"] == date_str) & (df["Roll Number"].astype(str) == str(roll_no))]
        if not already_present.empty:
            return f"⚠️ Student {name} (Roll: {roll_no}) is ALREADY marked present today!", df

    new_entry = pd.DataFrame([{
        "Date": date_str,
        "Timestamp": now_str,
        "Roll Number": roll_no,
        "Student Name": name,
        "Class": cls_name,
        "Status": "Present"
    }])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(log_file, index=False)

    return f"✅ Attendance Marked: {name} (Roll: {roll_no}) at {now_str}", df


# -------------------------------------------------------------
# PDF Exporters
# -------------------------------------------------------------
def generate_pdf_report(title: str, body_text: str, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("DocTitle", parent=styles["Heading1"], fontSize=16, leading=20, alignment=1, spaceAfter=15)
    body_style = ParagraphStyle("DocBody", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=8)

    elements = [Paragraph(title, title_style), Spacer(1, 10)]
    for line in body_text.splitlines():
        line = line.strip()
        if not line:
            elements.append(Spacer(1, 4))
        else:
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            elements.append(Paragraph(safe, body_style))

    doc.build(elements)
    return output_path


def generate_marks_certificate_pdf(student_data: dict, school_info: dict, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle("CertHeader", parent=styles["Heading1"], fontSize=18, leading=22, alignment=1, textColor=colors.HexColor("#1A365D"))
    subhead_style = ParagraphStyle("CertSubHeader", parent=styles["Heading2"], fontSize=12, leading=16, alignment=1, textColor=colors.HexColor("#4A5568"))
    normal_style = ParagraphStyle("CertNormal", parent=styles["Normal"], fontSize=10, leading=14)

    elements = [
        Paragraph(school_info.get("school_name", "ACADEMIC INSTITUTION"), header_style),
        Paragraph(f"{school_info.get('exam_type', 'EXAMINATION')} — {school_info.get('academic_year', '2025-2026')}", subhead_style),
        Paragraph("<b>DETAILED MARKS CERTIFICATE</b>", subhead_style),
        Spacer(1, 15)
    ]

    demo_data = [
        [Paragraph(f"<b>Roll No:</b> {student_data.get('roll_number', 'N/A')}", normal_style),
         Paragraph(f"<b>Student Name:</b> {student_data.get('student_name', 'N/A')}", normal_style)],
        [Paragraph(f"<b>Class:</b> {school_info.get('class_name', 'N/A')}", normal_style),
         Paragraph(f"<b>Subject Code:</b> {student_data.get('subject_code', school_info.get('subject_code', 'N/A'))}", normal_style)]
    ]
    demo_table = Table(demo_data, colWidths=[240, 270])
    elements.extend([demo_table, Spacer(1, 15)])

    subj = student_data.get("subject", school_info.get("subject", "General Subject"))
    obt = str(student_data.get("obtained_marks", 0))
    tot = str(student_data.get("total_marks", 100))
    pct = f"{student_data.get('calculated_percentage', 0)}%"
    grd = student_data.get("calculated_grade", "N/A")
    res = student_data.get("calculated_status", "N/A")

    marks_table_data = [
        ["Subject", "Subject Code", "Total", "Obtained", "Percentage", "Grade", "Status"],
        [subj, student_data.get("subject_code", "-"), tot, obt, pct, grd, res]
    ]
    marks_table = Table(marks_table_data, colWidths=[130, 75, 55, 60, 70, 55, 65])
    marks_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#EDF2F7")),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E0")),
    ]))
    elements.extend([marks_table, Spacer(1, 40)])

    sig_table = Table([["Date: _____________", "Class Teacher: _____________", "Principal: _____________"]], colWidths=[170, 170, 170])
    sig_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
    elements.append(sig_table)

    doc.build(elements)
    return output_path
