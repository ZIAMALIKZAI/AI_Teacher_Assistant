# AI Teacher Assistant

A simple educational RAG application for teachers.

It uses:

- **Streamlit** for the web interface
- **Groq** for generation
- **Sentence Transformers** for local/free embeddings
- **Qdrant** for vector search
- **PyMuPDF + Tesseract OCR** for PDFs and scanned images
- **Pandas** for Excel/CSV marks lists
- **ReportLab** for printable PDFs

The project deliberately keeps the Python architecture to **three Python files**:

```text
ai-teacher-assistant/
├── app.py
├── rag.py
├── utils.py
├── requirements.txt
├── packages.txt
├── .env.example
├── .gitignore
└── README.md
```

## Important: Streamlit vs the original Gradio requirement

The original specification requested Gradio and `gradio run app.py`, but this version is intentionally changed to **Streamlit** because the deployment target is **Streamlit Community Cloud**.

Run locally with:

```bash
streamlit run app.py
```

Streamlit Community Cloud deploys an entrypoint from a GitHub repository and installs dependencies from `requirements.txt`.

## Features

### RAG
1. Upload PDF/JPG/JPEG/PNG educational material.
2. Extract normal PDF text.
3. OCR scanned PDF pages and images when needed.
4. Split text into chunks.
5. Create local Sentence Transformer embeddings.
6. Store vectors in an in-memory Qdrant collection.
7. Retrieve relevant chunks for the teacher request.
8. Send the retrieved context to Groq.
9. Tell the teacher when information is not supported by the uploaded material.

### Simple Agentic Workflow

The application uses a small predictable router instead of a large agent framework.

Examples:

- `make notes` → notes workflow
- `make MCQs` → MCQ workflow
- `make short questions` → short-question workflow
- `make long questions` → long-question workflow
- `question paper` → question-paper workflow
- `answer key` → answer-key workflow
- `marks` → marks workflow
- `certificate` → certificate workflow
- anything else → general RAG question answering

### Question Paper

The UI calculates:

```text
MCQs × marks
+ Short questions × marks
+ Long questions × marks
= Total Marks
```

Generation is blocked when the criteria do not equal the selected Total Marks.

The generated paper is also checked for the expected sections and approximate question counts.

### Marks / Award List

Best-supported input:

- `.xlsx`
- `.xls`
- `.csv`

The app also attempts PDF/image OCR.

For reliable marks matching, use columns similar to:

```text
Roll No | Student Name | Subject Code | Subject | Marks
```

The app matches **Roll Number first** and then Subject/Subject Code, helping avoid accidentally showing another student's marks.

### Detailed Certificate

A printable A4 PDF can be generated for the selected student.

## 1. Install Python

Use Python 3.11 or 3.12 for a straightforward setup.

Check:

```bash
python --version
```

## 2. Create a virtual environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Tesseract OCR

### Windows

Install Tesseract OCR separately.

If Tesseract is not automatically found, set its executable path in `utils.py` before using OCR, for example:

```python
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

### Streamlit Community Cloud

`packages.txt` already contains:

```text
tesseract-ocr
```

Community Cloud can install Linux system packages listed in `packages.txt`.

## 5. Configure Groq

Create a local `.env` file based on `.env.example`:

```env
GROQ_API_KEY=your_real_key
GROQ_MODEL=llama-3.3-70b-versatile
```

Never commit `.env`.

The application expects the Groq API key as an environment variable.

## 6. Run locally

From the repository root:

```bash
streamlit run app.py
```

Then open the local Streamlit address shown in the terminal.

## 7. Use the application

### Upload Material

1. Upload textbook, syllabus, notes, scanned PDF or image.
2. Click **Process Documents**.
3. Wait for extraction, embeddings and Qdrant indexing.
4. Confirm that the RAG status is ready.

### Notes

Enter a chapter/topic and choose:

- Short Notes
- Detailed Notes
- Exam Notes
- Important Points
- Definitions
- Key Concepts

Choose English or Urdu and generate.

### Question Paper

Set:

- MCQ count and marks
- Short-question count and marks
- Long-question count and marks
- selected chapters
- difficulty
- cognitive focus
- total marks

The app will refuse to generate when the mark calculation is wrong.

### Marks

Upload Excel/CSV when possible.

Enter:

- Roll Number
- Subject or Subject Code

The app calculates:

- obtained marks
- percentage
- grade
- pass/fail

### Certificate

After finding a student, open the certificate tab and generate the A4 PDF.

## Streamlit Community Cloud deployment

1. Create a GitHub repository.
2. Upload the project files.
3. Do **not** upload `.env`.
4. Go to Streamlit Community Cloud.
5. Connect your GitHub account.
6. Create a new app.
7. Select your repository.
8. Select branch, normally `main`.
9. Select `app.py` as the entrypoint.
10. Open **Advanced settings / Secrets**.
11. Add:

```toml
GROQ_API_KEY = "your_real_groq_key"
GROQ_MODEL = "llama-3.3-70b-versatile"
QDRANT_COLLECTION = "ai_teacher_documents"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
```

12. Deploy.

### Why `.env` is not used on GitHub

Secrets should not be committed to source control. Streamlit Community Cloud provides an app Secrets field for this purpose.

## Qdrant note

This beginner-friendly version uses:

```python
QdrantClient(":memory:")
```

That means Qdrant is running inside the application process and does not require Docker or a separate Qdrant server.

This is intentionally simple for a teacher/demo deployment.

**Important:** in-memory data can disappear when the Streamlit process restarts. Therefore, uploaded documents should be processed again after a restart.

For a larger production system, replace the local client with a hosted Qdrant server.

## Privacy

Do not upload student information unless your school permits it.

Do not put API keys, passwords or private credentials into GitHub.

The application is designed as a simple educational tool and should be reviewed by a teacher before generated questions, marks or certificates are used officially.

## Troubleshooting

### "GROQ_API_KEY is missing"

For local use, set it in `.env` and make sure your environment loads it, or export it as an environment variable.

For Streamlit Cloud, add it to App Settings → Secrets.

### OCR does not work

Check that Tesseract is installed and available.

For Community Cloud, verify `packages.txt` contains:

```text
tesseract-ocr
```

### PDF has no text

The app attempts OCR on pages with very little normal PDF text. Scanned PDFs can be slower.

### Qdrant error

The app uses an in-memory Qdrant collection. Restarting the Streamlit process creates a fresh collection. Process your documents again.

### Generated answer says information was not found

This is intentional. The application prioritizes retrieved uploaded material and should not invent unsupported educational content.

### Deployment fails while installing dependencies

Check the Community Cloud deployment logs and make sure `requirements.txt` is in the repository root.

## Architecture in simple words

```text
Teacher
   |
   v
Streamlit UI
   |
   +---- Upload PDF/Image
   |          |
   |          v
   |       Text/OCR
   |          |
   |          v
   |       Chunks
   |          |
   |          v
   |   Sentence Transformers
   |          |
   |          v
   |        Qdrant
   |
   +---- Teacher Request
              |
              v
        Simple Agent Router
              |
              v
        Qdrant Retrieval
              |
              v
        Relevant Context
              |
              v
             Groq
              |
              v
    Notes / Questions / Answers
```

### What each Python file does

**app.py**

Contains the Streamlit interface, tabs, inputs, buttons and application workflow.

**rag.py**

Contains document extraction, OCR, chunking, embeddings, Qdrant retrieval, Groq generation and the small intent router.

**utils.py**

Contains PDF creation, marks-list reading, grade calculation, result matching and validation helpers.

## Future improvements

- Persistent hosted Qdrant
- Better page-level citations
- Full Urdu PDF font support
- Bulk certificates for every student
- More configurable grading rules in the UI
- Authentication for school staff
- Better structured JSON output from the LLM
- More rigorous automated question validation
