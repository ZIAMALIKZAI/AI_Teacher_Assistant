"""
app.py: Gradio user interface for AI Teacher Assistant with QR Code Student
Attendance, document RAG, automated exam generation, and marks certification.
"""

import os
import gradio as gr
import pandas as pd
from rag import (
    process_and_index_documents,
    generate_study_notes,
    generate_exam_paper,
    agent_chat_router
)
from utils import (
    parse_marks_file,
    lookup_student_record,
    generate_pdf_report,
    generate_marks_certificate_pdf,
    generate_student_qr_card,
    decode_qr_image,
    record_attendance
)

TEMP_DIR = "temp_output"
os.makedirs(TEMP_DIR, exist_ok=True)

uploaded_marks_df = pd.DataFrame()


# --- Handlers ---
def handle_doc_upload(files):
    if not files:
        return "No files uploaded."
    res = process_and_index_documents([f.name for f in files])
    return f"Indexed {res['processed_files']} file(s) into Qdrant ({res['total_chunks']} chunks created)."


def handle_notes_gen(topic, notes_type, language):
    if not topic.strip():
        return "Please specify a topic.", None
    notes = generate_study_notes(topic, notes_type, language)
    pdf_path = os.path.join(TEMP_DIR, "Study_Notes.pdf")
    generate_pdf_report("STUDY NOTES", notes, pdf_path)
    return notes, pdf_path


def handle_paper_gen(school, exam_type, cls_name, subj, code, time_lim, total_marks,
                     mcq_count, mcq_mk, short_count, short_mk, long_count, long_mk,
                     syllabus, diff):
    criteria = {
        "school_name": school, "exam_type": exam_type, "class_name": cls_name,
        "subject": subj, "subject_code": code, "exam_time": time_lim,
        "total_marks": int(total_marks), "mcq_count": int(mcq_count),
        "mcq_marks": int(mcq_mk), "short_count": int(short_count),
        "short_marks": int(short_mk), "long_count": int(long_count),
        "long_marks": int(long_mk), "syllabus": syllabus, "difficulty": diff
    }
    paper, ans_key = generate_exam_paper(criteria)
    if "Error:" in paper or "Information not found" in paper:
        return paper, ans_key, None, None

    p_path = os.path.join(TEMP_DIR, "Question_Paper.pdf")
    k_path = os.path.join(TEMP_DIR, "Answer_Key.pdf")
    generate_pdf_report("EXAMINATION QUESTION PAPER", paper, p_path)
    generate_pdf_report("OFFICIAL ANSWER KEY", ans_key, k_path)
    return paper, ans_key, p_path, k_path


def handle_marks_upload(file):
    global uploaded_marks_df
    if not file:
        return "No file selected.", None
    uploaded_marks_df = parse_marks_file(file.name)
    if uploaded_marks_df.empty:
        return "Failed to parse records.", None
    return f"Loaded {len(uploaded_marks_df)} students successfully.", uploaded_marks_df.head(10)


def handle_student_lookup(roll_no, subject_query, school, exam_type, academic_year, cls_name):
    global uploaded_marks_df
    if uploaded_marks_df.empty:
        return "Please upload an award list first.", None

    res = lookup_student_record(uploaded_marks_df, roll_no, subject_query)
    if "error" in res:
        return res["error"], None

    report = (
        f"Roll Number: {res.get('roll_number')}\n"
        f"Student Name: {res.get('student_name', 'N/A')}\n"
        f"Subject: {res.get('subject', subject_query)}\n"
        f"Obtained Marks: {res.get('obtained_marks')}/{res.get('total_marks', 100)}\n"
        f"Percentage: {res.get('calculated_percentage')}%\n"
        f"Grade: {res.get('calculated_grade')}\n"
        f"Result: {res.get('calculated_status')}"
    )
    school_info = {
        "school_name": school, "exam_type": exam_type,
        "academic_year": academic_year, "class_name": cls_name,
        "subject": res.get("subject", subject_query),
        "subject_code": res.get("subject_code", "")
    }
    cert_path = os.path.join(TEMP_DIR, f"Certificate_{roll_no}.pdf")
    generate_marks_certificate_pdf(res, school_info, cert_path)
    return report, cert_path


# --- QR Code Handlers ---
def handle_make_qr(roll_no, name, class_name):
    if not roll_no.strip():
        return None, "Please provide a Roll Number."
    out_file = os.path.join(TEMP_DIR, f"QR_Student_{roll_no.strip()}.png")
    generate_student_qr_card(roll_no, name, class_name, out_file)
    return out_file, f"QR Card generated for {name} ({roll_no})."


def handle_scan_qr(img_frame):
    if img_frame is None:
        return "No image captured or uploaded.", None
    data = decode_qr_image(img_frame)
    msg, df = record_attendance(data)
    log_csv = "attendance_log.csv" if os.path.exists("attendance_log.csv") else None
    return msg, df.tail(10) if not df.empty else None, log_csv


# -------------------------------------------------------------
# Gradio Interface
# -------------------------------------------------------------
with gr.Blocks(title="AI Teacher Assistant") as demo:
    gr.Markdown("# 🎓 AI Teacher Assistant\n*RAG Prep, Exam Paper Generator, Marks Certificates & QR Attendance.*")

    with gr.Sidebar():
        gr.Markdown("### 🏫 School & Exam Settings")
        sb_school = gr.Textbox(label="School Name", value="City Public High School")
        sb_exam = gr.Textbox(label="Exam Type", value="Annual Examination")
        sb_year = gr.Textbox(label="Academic Year", value="2025-2026")
        sb_class = gr.Textbox(label="Class", value="Grade 10")
        sb_subject = gr.Textbox(label="Subject", value="Computer Science")
        sb_sub_code = gr.Textbox(label="Subject Code", value="CS-101")
        gr.Markdown("---")
        sb_gemini_key = gr.Textbox(label="Gemini API Key (Override)", type="password")
        def set_gemini_key(k):
            if k: os.environ["GEMINI_API_KEY"] = k
        sb_gemini_key.change(set_gemini_key, inputs=[sb_gemini_key])

    with gr.Tabs():
        # TAB 1: Upload Documents
        with gr.TabItem("📁 Upload Material"):
            doc_files = gr.File(label="Upload Textbooks / Syllabi / Scans", file_count="multiple", file_types=[".pdf", ".png", ".jpg", ".jpeg"])
            btn_process = gr.Button("⚡ Index into Qdrant", variant="primary")
            doc_status = gr.Textbox(label="RAG Index Status", interactive=False)
            btn_process.click(handle_doc_upload, inputs=[doc_files], outputs=[doc_status])

        # TAB 2: Notes Generator
        with gr.TabItem("📚 Notes Generator"):
            with gr.Row():
                note_topic = gr.Textbox(label="Topic / Chapter", placeholder="e.g., Chapter 4: Database Systems")
                note_type = gr.Dropdown(["Detailed Notes", "Short Notes", "Exam Notes", "Key Concepts"], label="Type", value="Detailed Notes")
                note_lang = gr.Radio(["English", "Urdu"], label="Language", value="English")
            btn_gen_notes = gr.Button("Generate Notes", variant="primary")
            notes_out = gr.Markdown()
            notes_pdf = gr.File(label="Download Notes (PDF)")
            btn_gen_notes.click(handle_notes_gen, inputs=[note_topic, note_type, note_lang], outputs=[notes_out, notes_pdf])

        # TAB 3: Question Paper Generator
        with gr.TabItem("📝 Question Paper"):
            with gr.Row():
                paper_syllabus = gr.Textbox(label="Syllabus Scope", value="All Uploaded Chapters", scale=2)
                paper_diff = gr.Dropdown(["Easy", "Medium", "Difficult", "Mixed"], label="Difficulty", value="Medium")
                paper_time = gr.Textbox(label="Time Allowed", value="2 Hours")
                paper_total = gr.Number(label="Total Marks", value=100)
            with gr.Row():
                mcq_n = gr.Number(label="No. of MCQs", value=20)
                mcq_m = gr.Number(label="Marks / MCQ", value=1)
                short_n = gr.Number(label="No. of Short Qs", value=10)
                short_m = gr.Number(label="Marks / Short Q", value=3)
                long_n = gr.Number(label="No. of Long Qs", value=5)
                long_m = gr.Number(label="Marks / Long Q", value=10)

            btn_gen_paper = gr.Button("Generate Paper & Answer Key", variant="primary")
            with gr.Row():
                paper_out = gr.Textbox(label="Question Paper", lines=14)
                key_out = gr.Textbox(label="Answer Key", lines=14)
            with gr.Row():
                paper_pdf = gr.File(label="Download Question Paper (PDF)")
                key_pdf = gr.File(label="Download Answer Key (PDF)")

            btn_gen_paper.click(
                handle_paper_gen,
                inputs=[sb_school, sb_exam, sb_class, sb_subject, sb_sub_code, paper_time, paper_total,
                        mcq_n, mcq_m, short_n, short_m, long_n, long_m, paper_syllabus, paper_diff],
                outputs=[paper_out, key_out, paper_pdf, key_pdf]
            )

        # TAB 4: Marks List & Certificates
        with gr.TabItem("📊 Marks & Certificates"):
            marks_file = gr.File(label="Award List (.xlsx, .csv)", file_types=[".xlsx", ".xls", ".csv"])
            marks_status = gr.Textbox(label="Upload Status", interactive=False)
            marks_preview = gr.DataFrame(label="Uploaded Preview")
            marks_file.change(handle_marks_upload, inputs=[marks_file], outputs=[marks_status, marks_preview])

            with gr.Row():
                srch_roll = gr.Textbox(label="Roll Number")
                srch_sub = gr.Textbox(label="Subject Filter")
            btn_srch = gr.Button("Search & Generate Certificate", variant="primary")
            with gr.Row():
                srch_res = gr.Textbox(label="Student Record", lines=5)
                cert_pdf = gr.File(label="Download Certificate (PDF)")
            btn_srch.click(handle_student_lookup, inputs=[srch_roll, srch_sub, sb_school, sb_exam, sb_year, sb_class], outputs=[srch_res, cert_pdf])

        # TAB 5: QR Code Attendance System
        with gr.TabItem("📷 QR Code Attendance"):
            gr.Markdown("### Student Attendance Management via QR Code")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### 1. Generate Student QR ID Card")
                    qr_roll = gr.Textbox(label="Roll Number", placeholder="e.g. 101")
                    qr_name = gr.Textbox(label="Student Name", placeholder="e.g. Ahmad Ali")
                    qr_cls = gr.Textbox(label="Class", placeholder="e.g. Grade 10")
                    btn_make_qr = gr.Button("Create QR Card", variant="primary")
                    qr_img_out = gr.Image(label="Generated QR ID Card", type="filepath")
                    qr_msg = gr.Textbox(label="Status", interactive=False)
                    btn_make_qr.click(handle_make_qr, inputs=[qr_roll, qr_name, qr_cls], outputs=[qr_img_out, qr_msg])

                with gr.Column():
                    gr.Markdown("#### 2. Scan QR Code (Live Camera or Image)")
                    cam_input = gr.Image(label="Capture or Upload QR Code", sources=["webcam", "upload"], type="numpy")
                    btn_scan = gr.Button("Mark Attendance", variant="secondary")
                    scan_status = gr.Textbox(label="Scan Result", interactive=False)
                    recent_attendance = gr.DataFrame(label="Recent Scans")
                    download_log = gr.File(label="Download Attendance Log (.csv)")
                    btn_scan.click(handle_scan_qr, inputs=[cam_input], outputs=[scan_status, recent_attendance, download_log])

        # TAB 6: AI Chat Assistant
        with gr.TabItem("🤖 AI Assistant"):
            gr.ChatInterface(fn=lambda msg, hist: agent_chat_router(msg))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
