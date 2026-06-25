# KG Extraction Backend

This folder contains the backend service for the knowledge graph extraction project.

## Run

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

## Chinese OCR fallback

PDF text extraction uses PyMuPDF first. When a page has almost no extractable text,
the backend renders that page as an image and falls back to OCR with Tesseract.

Install the system OCR engine and Simplified Chinese language data before using
scanned/image-only Chinese PDFs:

```bash
brew install tesseract tesseract-lang
```

Optional environment variables:

- `PDF_OCR_LANGUAGE`: OCR language, default `chi_sim+eng`
- `PDF_OCR_DPI`: render DPI for OCR, default `300`
- `PDF_MIN_EXTRACTED_PAGE_CHARS`: minimum useful page characters before OCR fallback, default `20`

The frontend calls `http://127.0.0.1:8000/api/pdf/to-txt` to upload a PDF. The extracted text is saved under `data/extracted_text/` and is not returned to the browser.

The master agent chat endpoint is `POST /api/agent/master/chat`. It currently only handles project-page conversation and does not invoke skills or pipeline steps.

After PDF preprocessing, call `POST /api/graph/ontology/draft` with `{"extraction_id": "...", "document_summary": "...", "user_goal": "..."}`. The backend generates an ontology draft and saves it under `data/ontology/`.

After PDF preprocessing, call `POST /api/chunk/strategy` with `{"extraction_id": "..."}`. The backend reads `data/extracted_text/{extraction_id}.txt`, asks the LLM for a split strategy, and saves the result under `data/strategy/`.

To execute chunking with an existing strategy, call `POST /api/chunk/execute` with `{"extraction_id": "..."}`. The generated chunks are saved as JSON and JSONL under `data/chunks/`. The backend also runs a basic chunk quality validation after chunking and saves the quality report under `data/chunk_quality/`.

To run both steps together, call `POST /api/chunk/run` with `{"extraction_id": "..."}`.

After chunking and chunk quality validation, call `POST /api/extract/run` or `POST /api/graph/extract` with `{"extraction_id": "...", "allowed_entity_types": [...], "allowed_relation_types": [...], "allowed_relations": [...]}`. The raw graph is saved under `data/raw_graphs/` for the later graph merge step.

The complete pipeline is registered as independent skills in `services/pipeline_skill_service.py`. Call `GET /api/pipeline/skills` to inspect the current skill list and execution order.

## RAG embedding preparation

RAG chunk strategy and chunk generation are available through:

```bash
POST /api/rag/chunk/strategy
POST /api/rag/chunk/execute
```

After RAG chunks are generated, create embeddings with:

```bash
POST /api/rag/embedding/run
```

Search the local RAG vector index with:

```bash
POST /api/rag/search
```

Example body:

```json
{
  "extraction_id": "...",
  "query": "空压机太热应该检查什么？",
  "top_k": 5,
  "min_score": null
}
```

The default embedding model is `Qwen/Qwen3-Embedding-0.6B`. For MacBook Air M1, keep the conservative defaults unless you have verified memory headroom:

```bash
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_BATCH_SIZE=2
EMBEDDING_MAX_SEQ_LENGTH=2048
EMBEDDING_DEVICE=mps
EMBEDDING_LOCAL_FILES_ONLY=true
```

Outputs are saved under `data/embeddings/rag/`. The service writes readable JSON/JSONL records plus a retrieval-friendly `.npy` vector matrix and metadata JSON. Each record stores the normalized embedding vector plus chunk metadata such as `doc_id`, title chain, source chunk id, and character offsets.
