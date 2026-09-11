"""
AI Teacher Assistant
Streamlit entry point.

Run locally:
    streamlit run app.py
"""

import os
from io import BytesIO

import pandas as pd
import streamlit as st

from rag import RAGEngine
from utils import (
    build_certificate_pdf,
    build_question_paper_pdf,
    build_text_pdf,
    calculate_result,
    dataframe_to_csv,
    detect_columns,
    extract_marks_file,
    make_question_paper_text,
    validate_question_paper,
)

st.set_page_config(
    page_title="AI Teacher Assistant",
    page_icon="📚",
    layout="wide",
)

# ---------- Session state ----------

if "rag" not in st.session_state:
    st.session_state.rag = RAGEngine()
if "marks_df" not in st.session_state:
    st.session_state.marks_df = None
if "paper" not in st.session_state:
    st.session_state.paper = None
if "answer_key" not in st.session_state:
    st.session_state.answer_key = None
if "notes" not in st.session_state:
    st.session_state.notes = ""
if "chat" not in st.session_state:
    st.session_state.chat = []


def secret_or_env(name: str, default: str = "") -> str:
    """Read a Streamlit secret first, then an environment variable."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)


# ---------- Sidebar ----------

st.sidebar.title("📚 AI Teacher Assistant")
school = st.sidebar.text_input("School Name", "My School")
teacher = st.sidebar.text_input("Teacher Name", "")
class_name = st.sidebar.text_input("Class", "")
subject = st.sidebar.text_input("Subject", "")
subject_code = st.sidebar.text_input("Subject Code", "")
exam_type = st.sidebar.text_input("Examination Type", "Annual Examination")
academic_year = st.sidebar.text_input("Academic Year", "2026")
total_marks = st.sidebar.number_input("Total Marks", min_value=1, value=100)
exam_time = st.sidebar.text_input("Exam Time", "2 Hours")

st.sidebar.divider()
st.sidebar.caption(
    "RAG status: "
    + ("Ready" if st.session_state.rag.ready else "No documents processed")
)

# ---------- Header ----------

st.title("📚 AI Teacher Assistant")
st.caption(
    "Upload teaching material, retrieve it with RAG, and generate "
    "teacher-ready notes, papers, answer keys and marks certificates."
)

# ---------- Tabs ----------

tab_upload, tab_notes, tab_paper, tab_marks, tab_cert, tab_chat = st.tabs(
    [
        "📄 Upload Material",
        "📚 Notes",
        "📝 Question Paper",
        "📊 Marks / Award List",
        "🎓 Detailed Certificate",
        "🤖 AI Assistant",
    ]
)

with tab_upload:
    st.subheader("Upload Educational Material")
    uploads = st.file_uploader(
        "PDF, JPG, JPEG or PNG",
        type=["pdf", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    if uploads:
        st.write("Selected files:")
        for f in uploads:
            st.write(f"• {f.name} ({f.size / 1024:.1f} KB)")

    if st.button("Process Documents", type="primary"):
        if not uploads:
            st.error("Please upload at least one educational document.")
        else:
            with st.spinner("Extracting, chunking, embedding and indexing..."):
                try:
                    result = st.session_state.rag.process_files(uploads)
                    st.success("Documents processed successfully.")
                    st.json(result)
                except Exception as exc:
                    st.error(f"Document processing failed: {exc}")

    if st.session_state.rag.ready:
        st.success(
            f"RAG database ready — {st.session_state.rag.chunk_count} chunks indexed."
        )
        if st.session_state.rag.sources:
            st.dataframe(pd.DataFrame(st.session_state.rag.sources), use_container_width=True)

with tab_notes:
    st.subheader("📚 Notes Generator")
    c1, c2 = st.columns(2)
    with c1:
        note_chapter = st.text_input("Chapter / Topic", key="note_chapter")
        note_length = st.selectbox(
            "Notes Type",
            ["Short Notes", "Detailed Notes", "Exam Notes", "Important Points",
             "Definitions", "Key Concepts"],
        )
    with c2:
        note_language = st.selectbox("Language", ["English", "Urdu"])
        note_extra = st.text_area("Optional instruction", "Focus only on the uploaded material.")

    if st.button("Generate Notes", type="primary"):
        if not st.session_state.rag.ready:
            st.error("Please process educational documents first.")
        else:
            with st.spinner("Retrieving source material and generating notes..."):
                try:
                    prompt = (
                        f"Create {note_length.lower()} for {note_chapter or 'the uploaded material'}. "
                        f"Language: {note_language}. {note_extra}"
                    )
                    answer, sources = st.session_state.rag.answer(prompt)
                    st.session_state.notes = answer
                    st.markdown(answer)
                    st.caption("Sources used: " + ", ".join(sources))
                except Exception as exc:
                    st.error(str(exc))

    if st.session_state.notes:
        notes_bytes = st.session_state.notes.encode("utf-8")
        st.download_button(
            "Download Notes TXT",
            notes_bytes,
            "study_notes.txt",
            "text/plain",
        )
        st.download_button(
            "Download Notes PDF",
            build_text_pdf("Study Notes", st.session_state.notes),
            "study_notes.pdf",
            "application/pdf",
        )

with tab_paper:
    st.subheader("📝 Question Paper Generator")

    st.info("The question counts and marks must add up exactly to Total Marks.")

    p1, p2, p3 = st.columns(3)
    with p1:
        mcq_n = st.number_input("MCQs", 0, 100, 20)
        mcq_marks = st.number_input("Marks / MCQ", 1, 20, 1)
    with p2:
        short_n = st.number_input("Short Questions", 0, 100, 10)
        short_marks = st.number_input("Marks / Short", 1, 50, 3)
    with p3:
        long_n = st.number_input("Long Questions", 0, 50, 5)
        long_marks = st.number_input("Marks / Long", 1, 100, 10)

    q1, q2 = st.columns(2)
    with q1:
        chapters = st.text_input(
            "Selected syllabus / chapters",
            placeholder="Chapter 1, Chapter 2, Chapter 3",
        )
    with q2:
        difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Difficult", "Mixed"])

    cognitive = st.multiselect(
        "Cognitive focus",
        ["Knowledge", "Understanding", "Application"],
        default=["Knowledge", "Understanding"],
    )

    calculated = (
        mcq_n * mcq_marks
        + short_n * short_marks
        + long_n * long_marks
    )
    st.metric("Calculated Marks", calculated)

    if calculated != total_marks:
        st.warning(
            f"Criteria total {calculated}, but Total Marks is {total_marks}. "
            "Correct the values before generating."
        )

    if st.button("Generate Question Paper", type="primary"):
        if calculated != total_marks:
            st.error("Question-paper criteria do not equal the specified Total Marks.")
        elif not st.session_state.rag.ready:
            st.error("Please process educational documents first.")
        else:
            with st.spinner("Generating and validating the paper..."):
                try:
                    paper_prompt = f"""
Create a complete examination paper from ONLY the retrieved uploaded material.

School: {school}
Class: {class_name}
Subject: {subject}
Subject Code: {subject_code}
Exam: {exam_type}
Academic Year: {academic_year}
Time: {exam_time}
Total Marks: {total_marks}

Selected syllabus/chapters: {chapters or "all uploaded material"}
Difficulty: {difficulty}
Cognitive focus: {", ".join(cognitive) or "Mixed"}

Required:
MCQs: {mcq_n} x {mcq_marks}
Short questions: {short_n} x {short_marks}
Long questions: {long_n} x {long_marks}

Rules:
- Every question must be supported by the uploaded material.
- Do not use outside syllabus content.
- Do not repeat questions.
- MCQs need four meaningful options and one clearly correct answer.
- Return two parts:
PART A: QUESTION PAPER
PART B: ANSWER KEY
"""
                    answer, sources = st.session_state.rag.answer(
                        paper_prompt,
                        top_k=10,
                        max_tokens=7000,
                    )
                    # Basic structural validation in addition to the AI's own validation.
                    validation = validate_question_paper(
                        answer,
                        expected_total=total_marks,
                        expected_mcqs=mcq_n,
                        expected_short=short_n,
                        expected_long=long_n,
                    )
                    st.session_state.paper = answer
                    st.session_state.answer_key = answer
                    st.markdown(answer)
                    st.caption("Sources used: " + ", ".join(sources))
                    if validation["warnings"]:
                        for warning in validation["warnings"]:
                            st.warning(warning)
                except Exception as exc:
                    st.error(str(exc))

    if st.session_state.paper:
        paper_text = st.session_state.paper
        st.download_button(
            "Download Question Paper PDF",
            build_question_paper_pdf(
                school, exam_type, class_name, subject, subject_code,
                exam_time, total_marks, paper_text
            ),
            "question_paper.pdf",
            "application/pdf",
        )
        st.download_button(
            "Download Answer / Output TXT",
            paper_text.encode("utf-8"),
            "question_paper_and_answer_key.txt",
            "text/plain",
        )

with tab_marks:
    st.subheader("📊 Marks / Award List")
    marks_file = st.file_uploader(
        "Upload Excel, CSV, PDF or image",
        type=["xlsx", "xls", "csv", "pdf", "jpg", "jpeg", "png"],
        key="marks_upload",
    )

    if st.button("Read Award List"):
        if not marks_file:
            st.error("Please upload a marks/award list.")
        else:
            try:
                with st.spinner("Reading marks list..."):
                    df = extract_marks_file(marks_file)
                    st.session_state.marks_df = df
                st.success(f"Loaded {len(df)} records.")
            except Exception as exc:
                st.error(f"Could not read marks list: {exc}")

    df = st.session_state.marks_df
    if df is not None:
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "Download Marks CSV",
            dataframe_to_csv(df),
            "marks_processed.csv",
            "text/csv",
        )

        detected = detect_columns(df)
        st.write("Detected columns:", detected)

        st.subheader("Find Student Marks")
        roll = st.text_input("Roll Number", key="lookup_roll")
        lookup_subject = st.text_input(
            "Subject or Subject Code",
            value=subject,
            key="lookup_subject",
        )
        lookup_total = st.number_input(
            "Subject Total Marks",
            min_value=1,
            value=int(total_marks),
            key="lookup_total",
        )

        if st.button("Find Marks"):
            try:
                result = calculate_result(
                    df, roll, lookup_subject, lookup_total
                )
                if result is None:
                    st.error("Student/Roll Number not found.")
                else:
                    st.session_state.lookup_result = result
                    st.json(result)
            except Exception as exc:
                st.error(str(exc))

with tab_cert:
    st.subheader("🎓 Detailed Marks Certificate")

    result = st.session_state.get("lookup_result")
    if result:
        st.write("Current student result:")
        st.json(result)

        father_name = st.text_input("Father Name (optional)")
        section = st.text_input("Section (optional)")
        if st.button("Generate Certificate PDF", type="primary"):
            try:
                pdf = build_certificate_pdf(
                    school_name=school,
                    exam_type=exam_type,
                    academic_year=academic_year,
                    student=result,
                    father_name=father_name,
                    section=section,
                    teacher_name=teacher,
                )
                st.download_button(
                    "Download A4 Certificate PDF",
                    pdf,
                    f"certificate_{result['roll_number']}.pdf",
                    "application/pdf",
                )
            except Exception as exc:
                st.error(str(exc))
    else:
        st.info("Find a student in the Marks / Award List tab first.")

with tab_chat:
    st.subheader("🤖 AI Assistant")
    st.caption("Ask questions about the uploaded educational material.")

    for message in st.session_state.chat:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("sources"):
                st.caption("Sources: " + ", ".join(message["sources"]))

    prompt = st.chat_input("Example: Explain Chapter 2 in simple language.")
    if prompt:
        st.session_state.chat.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        if not st.session_state.rag.ready:
            response = "Please upload and process educational material first."
            sources = []
        else:
            try:
                with st.spinner("Searching uploaded material..."):
                    response, sources = st.session_state.rag.agent_answer(prompt)
            except Exception as exc:
                response = f"AI error: {exc}"
                sources = []

        st.session_state.chat.append(
            {"role": "assistant", "content": response, "sources": sources}
        )
        with st.chat_message("assistant"):
            st.markdown(response)
            if sources:
                st.caption("Sources: " + ", ".join(sources))
