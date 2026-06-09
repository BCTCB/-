# KG Extraction Backend

This folder contains the backend service for the knowledge graph extraction project.

## Run

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

The frontend calls `http://127.0.0.1:8000/api/pdf/to-txt` to upload a PDF. The extracted text is saved under `data/extracted_text/` and is not returned to the browser.

After PDF preprocessing, call `POST /api/chunk/strategy` with `{"extraction_id": "..."}`. The backend reads `data/extracted_text/{extraction_id}.txt`, asks the LLM for a split strategy, and saves the result under `data/strategy/`.

To execute chunking with an existing strategy, call `POST /api/chunk/execute` with `{"extraction_id": "..."}`. The generated chunks are saved as JSON and JSONL under `data/chunks/`. The backend also runs a basic chunk quality validation after chunking and saves the quality report under `data/chunk_quality/`.

To run both steps together, call `POST /api/chunk/run` with `{"extraction_id": "..."}`.

After chunking and chunk quality validation, call `POST /api/extract/run` or `POST /api/graph/extract` with `{"extraction_id": "...", "mode": "auto"}`. The raw graph is saved under `data/raw_graphs/` for the later graph merge step. Use `mode: "custom"` with `allowed_entity_types` and `allowed_relation_types` when you want to constrain the ontology.
