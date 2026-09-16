"""
app.py: Streamlit web application interface for AI Teacher Assistant.
Tabs include: Upload Material, Notes, Question Papers, Marks & Certificates,
QR Code Attendance, and Chat Assistant.
"""
from master_timetable import render_master_timetable_page
from teacher_attendance import render_teacher_attendance_page
from master_timetable import render_master_timetable_page
import os
import streamlit as st
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

st.set_page_config(page_title="AI Teacher Assistant", page_icon="🎓", layout="wide")

# Load external responsive styling
if os.path.exists("style.css"):
    with open("style.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

TEMP_DIR = "temp_output"
os.makedirs(TEMP_DIR, exist_ok=True)

# App Header
st.title("🎓 Well Come To AI Teacher Assistant")
st.caption("Empowering Teachers with AI — Lesson Notes, Exam Papers, Result Cards & Attendance")

# Sidebar Configuration
with st.sidebar:
    st.header("🏫 School & Exam Settings")
    sb_school = st.text_input("School Name", value="Govt. Fida Muhammad Khan High School Yar Hussain-Swabi")
    sb_exam = st.text_input("Exam Type", value="Annual Examination")
    sb_year = st.text_input("Academic Year", value="2026-2027")
    sb_class = st.text_input("Class", value="Grade 10 or Class 10 ")
    sb_subject = st.text_input("Subject", value="Computer Science")
    sb_sub_code = st.text_input("Subject Code", value="CS-101  or just any value")
    
    st.markdown("---")
    custom_key = st.text_input("Gemini API Key (Optional Override)", type="password")
    if custom_key:
        os.environ["GEMINI_API_KEY"] = custom_key

# Navigation Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📁 Upload Material", "📚 Notes Generator", "📝 Question Paper",
    "📊 Marks & Certificates", "📷 QR Attendance", "🗓️ Master Timetable"
])

# Then under your tabs:
with tab6:
    render_master_timetable_page(school_name=sb_school)

# TAB 1: Document Upload & Indexing

   tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
       "📁 Upload Material",
       "📚 Notes Generator",
       "📝 Question Paper",
       "📊 Marks & Certificates",
       "📷 Student QR Attendance",
       "👨‍🏫 Teacher Attendance & WhatsApp",
       "🗓️ Master Timetable",
   ])
    if st.button("⚡ Process & Index Documents into Qdrant", type="primary"):
        if uploaded_files:
            saved_paths = []
            for f in uploaded_files:
                path = os.path.join(TEMP_DIR, f.name)
                with open(path, "wb") as out:
                    out.write(f.getbuffer())
                saved_paths.append(path)

            with st.spinner("Extracting text and indexing into Qdrant..."):
                res = process_and_index_documents(saved_paths)
            st.success(f"Indexed {res['processed_files']} document(s) with {res['total_chunks']} chunks into Qdrant vector database.")
        else:
            st.warning("Please upload at least one document.")

# TAB 2: Notes Generator
with tab2:
    st.subheader("Generate Study Notes")
    col1, col2, col3 = st.columns(3)
    with col1:
        note_topic = st.text_input("Chapter / Topic Name", placeholder="e.g. Chapter 2: Hardware Components")
    with col2:
        note_type = st.selectbox("Notes Style", ["Detailed Notes", "Short Notes", "Exam Notes", "Key Concepts"])
    with col3:
        note_lang = st.radio("Language", ["English", "Urdu"], horizontal=True)

    if st.button("Generate Study Notes", type="primary"):
        if note_topic:
            with st.spinner("Consulting knowledge base with Gemini 2.5 Flash..."):
                notes = generate_study_notes(note_topic, note_type, note_lang)
            st.markdown(notes)
            pdf_path = os.path.join(TEMP_DIR, "Study_Notes.pdf")
            generate_pdf_report("STUDY NOTES", notes, pdf_path)
            with open(pdf_path, "rb") as f:
                st.download_button("📥 Download Notes (PDF)", data=f, file_name="Study_Notes.pdf", mime="application/pdf")
        else:
            st.warning("Please enter a topic.")

# TAB 3: Question Paper Generator
with tab3:
    st.subheader("Automated Examination Paper & Answer Key")
    col1, col2 = st.columns([2, 1])
    with col1:
        p_syllabus = st.text_input("Syllabus Scope / Chapters", value="All Uploaded Material")
    with col2:
        p_diff = st.selectbox("Difficulty", ["Medium", "Easy", "Difficult", "Mixed"])

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        p_time = st.text_input("Time Allowed", value="2 Hours")
    with col_t2:
        p_total = st.number_input("Total Marks Required", value=100, min_value=1)

    st.markdown("##### Questions Configuration")
    q_col1, q_col2, q_col3 = st.columns(3)
    with q_col1:
        mcq_n = st.number_input("No. of MCQs", value=20, min_value=0)
        mcq_m = st.number_input("Marks per MCQ", value=1, min_value=1)
    with q_col2:
        short_n = st.number_input("No. of Short Questions", value=10, min_value=0)
        short_m = st.number_input("Marks per Short Q", value=3, min_value=1)
    with q_col3:
        long_n = st.number_input("No. of Long Questions", value=5, min_value=0)
        long_m = st.number_input("Marks per Long Q", value=10, min_value=1)

    if st.button("Generate Question Paper & Answer Key", type="primary"):
        criteria = {
            "school_name": sb_school, "exam_type": sb_exam, "class_name": sb_class,
            "subject": sb_subject, "subject_code": sb_sub_code, "exam_time": p_time,
            "total_marks": int(p_total), "mcq_count": int(mcq_n), "mcq_marks": int(mcq_m),
            "short_count": int(short_n), "short_marks": int(short_m),
            "long_count": int(long_n), "long_marks": int(long_m),
            "syllabus": p_syllabus, "difficulty": p_diff
        }
        with st.spinner("Synthesizing balanced exam paper and official answer key..."):
            paper, key = generate_exam_paper(criteria)

        if "Error:" in paper:
            st.error(paper)
        else:
            paper_col, key_col = st.columns(2)
            with paper_col:
                st.markdown("#### Question Paper")
                st.text_area("Paper Content", value=paper, height=450)
                p_file = os.path.join(TEMP_DIR, "Question_Paper.pdf")
                generate_pdf_report("EXAMINATION QUESTION PAPER", paper, p_file)
                with open(p_file, "rb") as f:
                    st.download_button("📥 Download Question Paper (PDF)", data=f, file_name="Question_Paper.pdf", mime="application/pdf")

            with key_col:
                st.markdown("#### Official Answer Key")
                st.text_area("Answer Key Content", value=key, height=450)
                k_file = os.path.join(TEMP_DIR, "Answer_Key.pdf")
                generate_pdf_report("OFFICIAL ANSWER KEY", key, k_file)
                with open(k_file, "rb") as f:
                    st.download_button("📥 Download Answer Key (PDF)", data=f, file_name="Answer_Key.pdf", mime="application/pdf")

# TAB 4: Marks List & Certificates
with tab4:
    st.subheader("Student Marks Processing & Certificate Generator")
    marks_file = st.file_uploader("Upload Marks/Award List (.xlsx or .csv)", type=["xlsx", "xls", "csv"])
    
    if marks_file:
        m_path = os.path.join(TEMP_DIR, marks_file.name)
        with open(m_path, "wb") as out:
            out.write(marks_file.getbuffer())
        df_marks = parse_marks_file(m_path)
        st.session_state["marks_df"] = df_marks
        # Reset index to avoid index-column collision in PyArrow
        st.dataframe(df_marks.head(10).reset_index(drop=True), use_container_width=True)

    st.markdown("---")
    st.markdown("##### Search Student Record")
    s_col1, s_col2 = st.columns(2)
    with s_col1:
        lookup_roll = st.text_input("Enter Roll Number", placeholder="e.g. 101")
    with s_col2:
        lookup_subj = st.text_input("Subject Filter (Optional)", placeholder="e.g. Computer Science")

    if st.button("Find Student & Generate Certificate"):
        if "marks_df" in st.session_state and not st.session_state["marks_df"].empty:
            res = lookup_student_record(st.session_state["marks_df"], lookup_roll, lookup_subj)
            if "error" in res:
                st.error(res["error"])
            else:
                st.success(f"Record matched: {res.get('student_name', 'Student')} (Percentage: {res.get('calculated_percentage')}%, Grade: {res.get('calculated_grade')})")
                
                school_meta = {
                    "school_name": sb_school, "exam_type": sb_exam,
                    "academic_year": sb_year, "class_name": sb_class,
                    "subject": res.get("subject", lookup_subj),
                    "subject_code": res.get("subject_code", sb_sub_code)
                }
                c_path = os.path.join(TEMP_DIR, f"Certificate_{lookup_roll}.pdf")
                generate_marks_certificate_pdf(res, school_meta, c_path)
                with open(c_path, "rb") as f:
                    st.download_button("📥 Download Detailed Marks Certificate (PDF)", data=f, file_name=f"Certificate_{lookup_roll}.pdf", mime="application/pdf")
        else:
            st.warning("Please upload an award list first.")

# TAB 5: QR Code Attendance
with tab5:
    st.subheader("Student QR Code Attendance System")
    col_qr_gen, col_qr_scan = st.columns(2)

    with col_qr_gen:
        st.markdown("##### 1. Generate Student QR ID Card")
        q_roll = st.text_input("Student Roll No.", placeholder="e.g. 101")
        q_name = st.text_input("Student Full Name", placeholder="e.g. Ahmad Ali")
        q_cls = st.text_input("Class / Grade", placeholder="e.g. Grade 10")
        
        if st.button("Generate QR Card"):
            if q_roll.strip():
                card_path = os.path.join(TEMP_DIR, f"QR_Student_{q_roll.strip()}.png")
                generate_student_qr_card(q_roll, q_name, q_cls, card_path)
                st.image(card_path, caption=f"ID Card: {q_name} ({q_roll})", width=220)
                with open(card_path, "rb") as img_file:
                    st.download_button("📥 Download QR Card (PNG)", data=img_file, file_name=f"QR_{q_roll}.png", mime="image/png")
            else:
                st.warning("Please enter a roll number.")

    with col_qr_scan:
        st.markdown("##### 2. Live Scanner (Webcam or Upload)")
        cam_shot = st.camera_input("Take photo of student QR code")
        uploaded_qr = st.file_uploader("Or upload image containing QR", type=["png", "jpg", "jpeg"], key="qr_file_up")

        img_bytes = None
        if cam_shot is not None:
            img_bytes = cam_shot.getvalue()
        elif uploaded_qr is not None:
            img_bytes = uploaded_qr.getvalue()

        if img_bytes is not None:
            decoded = decode_qr_image(img_bytes)
            status_msg, updated_df = record_attendance(decoded)
            if "Error" in status_msg or "⚠️" in status_msg:
                st.warning(status_msg)
            else:
                st.success(status_msg)

            if os.path.exists("attendance_log.csv"):
                log_df = pd.read_csv("attendance_log.csv")
                st.markdown("###### Today's Attendance Log")
                st.dataframe(log_df.tail(5), use_container_width=True)
                with open("attendance_log.csv", "rb") as f:
                    st.download_button("📥 Download Full Attendance Sheet (.csv)", data=f, file_name="attendance_log.csv", mime="text/csv")

# TAB 6: AI Chat Assistant
with tab6:
    st.subheader("Chat with your Uploaded Documents")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_query = st.chat_input("Ask a question about your uploaded syllabus or chapters...")
    if user_query:
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Searching syllabus..."):
                ans = agent_chat_router(user_query)
            st.markdown(ans)
            st.session_state.chat_history.append({"role": "assistant", "content": ans})
