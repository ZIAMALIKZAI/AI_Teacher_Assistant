"""
Simple RAG engine for AI Teacher Assistant.

Pipeline:
file -> text/OCR -> chunks -> SentenceTransformer embeddings -> Qdrant -> Groq
"""

import os
import re
from io import BytesIO
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF
import numpy as np
import pytesseract
from PIL import Image
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
from groq import Groq


COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "ai_teacher_documents")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
DEFAULT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def clean_text(text: str) -> str:
    """Remove excessive whitespace while keeping readable paragraphs."""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdf_text(file_bytes: bytes) -> Tuple[str, int, bool]:
    """Extract normal PDF text; OCR pages that contain little/no text."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    used_ocr = False

    for page_number, page in enumerate(doc, start=1):
        text = clean_text(page.get_text("text"))
        if len(text) >= 40:
            pages.append(f"[Page {page_number}]\n{text}")
            continue

        # Scanned PDF fallback.
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_text = clean_text(pytesseract.image_to_string(image))
            if ocr_text:
                pages.append(f"[Page {page_number} - OCR]\n{ocr_text}")
                used_ocr = True
        except Exception:
            # Keep processing other pages. The UI reports the overall result.
            continue

    doc.close()
    return "\n\n".join(pages), len(pages), used_ocr


def extract_image_text(file_bytes: bytes) -> str:
    """OCR a JPG/PNG image."""
    image = Image.open(BytesIO(file_bytes)).convert("RGB")
    return clean_text(pytesseract.image_to_string(image))


class RAGEngine:
    """Small, beginner-friendly RAG implementation."""

    def __init__(self):
        self.ready = False
        self.chunk_count = 0
        self.sources: List[Dict[str, Any]] = []
        self.model = None
        self.client = None
        self.groq = None
        self.dimension = 384

    def _load_models(self):
        if self.model is None:
            self.model = SentenceTransformer(EMBEDDING_MODEL)
            self.dimension = self.model.get_sentence_embedding_dimension()

        if self.client is None:
            # In-memory Qdrant is ideal for a simple Streamlit deployment.
            # Data is rebuilt when the app process restarts.
            self.client = QdrantClient(":memory:")
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=self.dimension,
                    distance=models.Distance.COSINE,
                ),
            )

        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is missing. Add it to Streamlit Secrets or your .env."
            )
        self.groq = Groq(api_key=api_key)

    def process_files(self, uploaded_files) -> Dict[str, Any]:
        """Read uploaded files and rebuild the current RAG collection."""
        self._load_models()

        all_chunks = []
        self.sources = []
        file_count = 0

        for uploaded in uploaded_files:
            name = uploaded.name
            data = uploaded.getvalue()
            suffix = os.path.splitext(name)[1].lower()

            if suffix == ".pdf":
                text, page_count, used_ocr = extract_pdf_text(data)
                source_type = f"PDF ({page_count} pages"
                if used_ocr:
                    source_type += ", OCR used"
                source_type += ")"
            elif suffix in {".jpg", ".jpeg", ".png"}:
                text = extract_image_text(data)
                source_type = "Image (OCR)"
            else:
                continue

            text = clean_text(text)
            if not text:
                continue

            chunks = split_text(text)
            for index, chunk in enumerate(chunks, start=1):
                all_chunks.append(
                    {
                        "text": chunk,
                        "file": name,
                        "chunk": index,
                        "source_type": source_type,
                    }
                )

            self.sources.append(
                {
                    "file": name,
                    "type": source_type,
                    "chunks": len(chunks),
                    "characters": len(text),
                }
            )
            file_count += 1

        if not all_chunks:
            raise ValueError("No readable text was found in the uploaded files.")

        vectors = self.model.encode(
            [item["text"] for item in all_chunks],
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        points = []
        for idx, (item, vector) in enumerate(zip(all_chunks, vectors)):
            points.append(
                models.PointStruct(
                    id=idx,
                    vector=np.asarray(vector, dtype=np.float32).tolist(),
                    payload=item,
                )
            )

        self.client.upsert(collection_name=COLLECTION_NAME, points=points)
        self.chunk_count = len(points)
        self.ready = True

        return {
            "files_processed": file_count,
            "chunks": self.chunk_count,
            "rag_database": "Qdrant in-memory collection",
            "ocr_supported": True,
        }

    def search(self, query: str, top_k: int = 6):
        if not self.ready:
            return []

        vector = self.model.encode(
            query,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=np.asarray(vector, dtype=np.float32).tolist(),
            limit=top_k,
            with_payload=True,
        ).points

        return results

    def _groq_generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4000,
    ) -> str:
        if not self.groq:
            raise RuntimeError("Groq is not initialized.")

        response = self.groq.chat.completions.create(
            model=os.getenv("GROQ_MODEL", DEFAULT_MODEL),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Groq returned an empty response.")
        return content.strip()

    def answer(
        self,
        request: str,
        top_k: int = 6,
        max_tokens: int = 4000,
    ) -> Tuple[str, List[str]]:
        """Retrieve source chunks and ask Groq to answer only from them."""
        if not self.ready:
            raise RuntimeError("No documents have been processed.")

        results = self.search(request, top_k=top_k)
        if not results:
            return "Information not found in the uploaded material.", []

        context_parts = []
        source_labels = []
        for result in results:
            payload = result.payload or {}
            context_parts.append(
                f"FILE: {payload.get('file', 'Unknown')}\n"
                f"CHUNK: {payload.get('chunk', '?')}\n"
                f"CONTENT:\n{payload.get('text', '')}"
            )
            source_labels.append(
                f"{payload.get('file', 'Unknown')} / chunk {payload.get('chunk', '?')}"
            )

        context = "\n\n--- SOURCE CHUNK ---\n\n".join(context_parts)

        system = """You are AI Teacher Assistant.
Use the supplied uploaded-document context as the PRIMARY and AUTHORITATIVE source.
Do not invent facts, chapters, marks, questions, names or syllabus content.
If the requested information is not supported by the context, reply exactly:
Information not found in the uploaded material.

For question generation, create questions only from supported source content.
For educational output, be clear, structured and teacher-friendly."""
        user = f"""Teacher request:
{request}

Uploaded-document context:
{context}
"""
        return self._groq_generate(system, user, max_tokens), source_labels

    def detect_intent(self, request: str) -> str:
        """Predictable keyword router: this is the small agentic layer."""
        text = request.lower()

        if any(x in text for x in ["marks", "roll no", "roll number", "award list"]):
            return "marks_lookup"
        if any(x in text for x in ["certificate", "result card", "marks certificate"]):
            return "certificate"
        if "question paper" in text or "exam paper" in text:
            return "question_paper"
        if "answer key" in text:
            return "answer_key"
        if any(x in text for x in ["mcq", "multiple choice"]):
            return "mcqs"
        if "short question" in text:
            return "short_questions"
        if "long question" in text:
            return "long_questions"
        if any(x in text for x in ["notes", "study notes", "exam notes"]):
            return "notes"
        return "general_qa"

    def agent_answer(self, request: str) -> Tuple[str, List[str]]:
        """Route the request, then use RAG for the actual educational answer."""
        intent = self.detect_intent(request)

        instruction_map = {
            "notes": "Generate structured study notes from the uploaded material.",
            "mcqs": "Generate MCQs from the uploaded material. Include four options and the correct answer.",
            "short_questions": "Generate short-answer questions from the uploaded material.",
            "long_questions": "Generate long-answer questions from the uploaded material.",
            "question_paper": "Generate an examination paper from the uploaded material.",
            "answer_key": "Generate an answer key from the uploaded material.",
            "marks_lookup": "The user is asking about marks. Explain that marks lookup is performed in the Marks tab.",
            "certificate": "The user is asking for a certificate. Explain that certificate generation is performed in the Detailed Certificate tab.",
            "general_qa": "Answer the teacher's question from the uploaded material.",
        }
        request_with_intent = (
            f"Detected task: {intent}\n"
            f"{instruction_map[intent]}\n\n"
            f"Teacher request: {request}"
        )
        return self.answer(request_with_intent)
