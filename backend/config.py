from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXTRACTED_TEXT_DIR = DATA_DIR / "extracted_text"
CHUNKS_DIR = DATA_DIR / "chunks"
CHUNK_QUALITY_DIR = DATA_DIR / "chunk_quality"
RAW_GRAPHS_DIR = DATA_DIR / "raw_graphs"
CLEANED_GRAPHS_DIR = DATA_DIR / "cleaned_graphs"
MERGED_GRAPHS_DIR = DATA_DIR / "merged_graphs"
RELATION_CLEANED_GRAPHS_DIR = DATA_DIR / "relation_cleaned_graphs"
GRAPH_QUALITY_REPORTS_DIR = DATA_DIR / "graph_quality_reports"
FINAL_GRAPHS_DIR = DATA_DIR / "final_graphs"
PROCESSED_DIR = DATA_DIR / "processed"
STRATEGY_DIR = DATA_DIR / "strategy"
ONTOLOGY_DIR = DATA_DIR / "ontology"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
LOG_DIR = BASE_DIR / "logs"


for directory in (
    UPLOAD_DIR,
    EXTRACTED_TEXT_DIR,
    CHUNKS_DIR,
    CHUNK_QUALITY_DIR,
    RAW_GRAPHS_DIR,
    CLEANED_GRAPHS_DIR,
    MERGED_GRAPHS_DIR,
    RELATION_CLEANED_GRAPHS_DIR,
    GRAPH_QUALITY_REPORTS_DIR,
    FINAL_GRAPHS_DIR,
    PROCESSED_DIR,
    STRATEGY_DIR,
    ONTOLOGY_DIR,
    EMBEDDINGS_DIR,
    LOG_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)
