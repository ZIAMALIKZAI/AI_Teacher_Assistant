"""
rag.py: Ingestion into Qdrant vector database and querying Google AI Studio's
gemini-3.6-flash model via the official google-genai SDK.
"""

import os
from dotenv import load_dotenv
import streamlit as st
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from google import genai
from utils import extract_text_from_file

load_dotenv()

# Read API Key from Streamlit Secrets or Environment Variables
def get_api_key():
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    return os.getenv("GEMINI_API_KEY", "")

QDRANT_LOCATION = os.getenv("QDRANT_LOCATION", ":memory:")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "teacher_knowledge_base")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

@st.cache_resource
def get_qdrant_client():
    return QdrantClient(location=QDRANT_LOCATION)

@st.cache_resource
def get_embedder():
    return SentenceTransformer(EMBEDDING_MODEL_NAME)

qdrant = get_qdrant_client()
embedder = get_embedder()
VECTOR_SIZE = embedder.get_sentence_embedding_dimension()


def ensure_collection():
    collections = [c.name for c in qdrant.get_collections().collections]
    if QDRANT_COLLECTION not in collections:
        qdrant.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def process_and_index_documents(file_paths: list[str]) -> dict:
    ensure_collection()
    total_chunks = 0
    processed_files = 0
    points = []
    point_id = 0

    for path in file_paths:
        if not path or not os.path.exists(path):
            continue
        extracted = extract_text_from_file(path)
        processed_files += 1

        for item in extracted:
            chunks = chunk_text(item["text"])
            for c in chunks:
                vector = embedder.encode(c).tolist()
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={"text": c, "source": item["source"], "page": item["page"]}
                    )
                )
                point_id += 1
                total_chunks += 1

    if points:
        batch_size = 64
        for idx in range(0, len(points), batch_size):
            qdrant.upsert(
                collection_name=QDRANT_COLLECTION,
                points=points[idx : idx + batch_size]
            )

    return {"processed_files": processed_files, "total_chunks": total_chunks}


def retrieve_context(query: str, top_k: int = 6) -> tuple[str, list[dict]]:
    ensure_collection()
    query_vector = embedder.encode(query).tolist()

    search_result = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        limit=top_k
    ).points

    if not search_result:
        return "", []

    context_blocks = []
    sources = []
    for point in search_result:
        text = point.payload.get("text", "")
        context_blocks.append(text)
        sources.append({"source": point.payload.get("source", "Doc"), "page": point.payload.get("page", 1)})

    return "\n\n---\n\n".join(context_blocks), sources


def query_gemini(prompt: str, system_instruction: str = "You are a professional educational AI assistant.") -> str:
    api_key = get_api_key()
    if not api_key:
        return "⚠️ Error: GEMINI_API_KEY is not configured. Please add it to your Streamlit Secrets or sidebar."

    client = genai.Client(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={"system_instruction": system_instruction, "temperature": 0.2}
        )
        return response.text.strip()
    except Exception as err:
        return f"Gemini Error: {str(err)}"


def generate_study_notes(topic: str, notes_type: str, language: str) -> str:
    context, _ = retrieve_context(f"Notes, concepts, definitions: {topic}", top_k=6)
    if not context.strip():
        return "Information not found in the uploaded material."

    sys_prompt = (
        "You are an expert school educator. Create structured study notes strictly from the source context.\n"
        "If the information is not present, respond: 'Information not found in the uploaded material.'\n"
        f"Language: {language}. Structure: Chapter/Topic Title, Overview, Key Definitions, Core Concepts, Examples, Summary Points."
    )
    prompt = f"Context:\n{context}\n\nTask: Generate {notes_type} for '{topic}' in {language}."
    return query_gemini(prompt, sys_prompt)


def generate_exam_paper(criteria: dict) -> tuple[str, str]:
    syllabus = criteria.get("syllabus", "General Syllabus")
    context, _ = retrieve_context(f"Exam questions for syllabus: {syllabus}", top_k=8)

    if not context.strip():
        return "Information not found in the uploaded material.", "Answer key unavailable."

    mcq_count = criteria.get("mcq_count", 0)
    mcq_marks = criteria.get("mcq_marks", 1)
    short_count = criteria.get("short_count", 0)
    short_marks = criteria.get("short_marks", 2)
    long_count = criteria.get("long_count", 0)
    long_marks = criteria.get("long_marks", 5)

    calc_total = (mcq_count * mcq_marks) + (short_count * short_marks) + (long_count * long_marks)
    declared_total = criteria.get("total_marks", calc_total)

    if calc_total != declared_total:
        return (
            f"Error: Question marks total ({calc_total}) does not match declared Total Marks ({declared_total}).",
            ""
        )

    header = (
        f"{criteria.get('school_name', 'HIGH SCHOOL')}\n"
        f"{criteria.get('exam_type', 'EXAMINATION')}\n"
        f"Class: {criteria.get('class_name', '')} | Subject: {criteria.get('subject', '')} ({criteria.get('subject_code', '')})\n"
        f"Time Allowed: {criteria.get('exam_time', '2 Hours')} | Total Marks: {declared_total}\n"
        f"{'='*60}\n\n"
    )

    paper_prompt = (
        f"SOURCE CONTEXT:\n{context}\n\n"
        f"Generate a formal exam paper:\n"
        f"- Section A: {mcq_count} MCQs (each {mcq_marks} marks) with 4 options (a, b, c, d).\n"
        f"- Section B: {short_count} Short Questions (each {short_marks} marks).\n"
        f"- Section C: {long_count} Long Questions (each {long_marks} marks).\n"
        f"- Difficulty: {criteria.get('difficulty', 'Medium')}."
    )
    paper_body = query_gemini(paper_prompt, "You are a professional examination creator.")
    full_paper = header + paper_body

    key_prompt = f"Source Context:\n{context}\n\nExam Paper:\n{paper_body}\n\nProvide the official answer key and scoring criteria."
    answer_key = query_gemini(key_prompt, "You are an examiner providing official answer keys.")

    return full_paper, answer_key


def agent_chat_router(user_message: str) -> str:
    context, sources = retrieve_context(user_message, top_k=5)
    if not context.strip():
        return "Information not found in the uploaded material."

    prompt = f"Context:\n{context}\n\nUser Question: {user_message}\n\nAnswer accurately based only on the uploaded text."
    res = query_gemini(prompt)
    if sources:
        res += "\n\n**Sources Used:** " + ", ".join([f"{s['source']} (p.{s['page']})" for s in sources[:3]])
    return res
