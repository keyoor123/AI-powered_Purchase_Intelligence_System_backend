# AI-powered Purchase Intelligence System Backend

This is the backend API for the bill ingestion pipeline. It preprocesses uploaded bill images/PDFs, performs OCR, extracts structured data using a Vision LLM (via OpenRouter), validates the outputs, and stores them in MongoDB.

## Tech Stack

- **FastAPI**: Async API framework
- **MongoDB**: Storage (collections: `bills`, `dealers`, `products`, `processing_logs`)
- **Motor**: Asynchronous MongoDB client
- **OpenCV & Pillow**: Modular image preprocessing (deskew, binarize, denoise, etc.)
- **PaddleOCR**: OCR for text extraction
- **OpenRouter API**: Vision LLM extraction (utilizing free models)
- **Pydantic v2**: Structured validation

## Folder Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── api/                     # API routers
│   ├── database/                # Database configurations
│   ├── models/                  # MongoDB DB models
│   ├── prompts/                 # Vision LLM prompt templates
│   ├── schemas/                 # Pydantic validation schemas
│   ├── services/                # Image preprocessing, OCR, LLM extractors
│   ├── utils/                   # Shared utility modules (logging, etc.)
│   ├── uploads/                 # Uploaded files directory
│   ├── processed/               # Preprocessed files directory
│   ├── ocr_text/                # Extracted OCR text files
│   └── logs/                    # System logs directory
├── requirements.txt             # Project requirements
├── .env.example                 # Config template
└── README.md                    # This file
```

## Setup & Running Heuristics

1. **Prerequisites**
   - Python 3.12+ installed
   - MongoDB running locally or a MongoDB Atlas URI

2. **Virtual Environment Setup**
   ```bash
   cd backend
   python -m venv venv
   # On Windows (cmd/powershell):
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   - Copy `.env.example` to `.env`
   - Set your `OPENROUTER_API_KEY` and MongoDB configuration

5. **Start Application**
   ```bash
   python -m uvicorn app.main:app --reload
   ```

6. **Interactive Documentation**
   Open your browser at `http://127.0.0.1:8000/docs` to view and test the endpoints via Swagger.
