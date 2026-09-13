# AI Teacher Assistant + QR Code Attendance

An all-in-one educational platform for school teachers combining **Gemini 2.5 Flash** (1,000,000 token context window), **Qdrant Vector RAG**, automated marks certificates, and a **QR Code Student Attendance System**.

---

## Key Features

1. **Massive Context (Google AI Studio):**
   Uses `gemini-2.5-flash` with a 1,000,000 token input window on the free tier, eliminating Groq 413 / TPM rate-limit errors entirely.
2. **QR Code Attendance System:**
   - Generate student QR ID cards encoded with JSON student records.
   - Scan QR codes directly from a webcam or uploaded photo.
   - Automatically prevents duplicate daily attendance and exports logs to `attendance_log.csv`.
3. **Curriculum RAG Engine:**
   Extracts text and scanned OCR from textbooks and syllabi, indexing embeddings into local Qdrant.
4. **Examination & Notes Generator:**
   Produces MCQs, short/long questions, complete exam papers, matching answer keys, and structured revision notes.
5. **Marks & Certificate System:**
   Reads Excel/CSV award lists, computes grades and percentages, and produces printable A4 PDF certificates.

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10 to 3.12
- *(Optional for OCR)* Install Tesseract OCR:
  - **Windows:** Download from UB-Mannheim Tesseract.
  - **Linux/Ubuntu:** `sudo apt install tesseract-ocr`

### 2. Setup Project & Virtual Environment
```bash
git clone <your-repo-url>
cd AI_Teacher_Assistant

python -m venv venv

# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
