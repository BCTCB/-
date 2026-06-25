"""Retention helpers for generated pipeline artifacts."""

from pathlib import Path
import re

from config import (
    CHUNK_QUALITY_DIR,
    CHUNKS_DIR,
    CLEANED_GRAPHS_DIR,
    EXTRACTED_TEXT_DIR,
    FINAL_GRAPHS_DIR,
    GRAPH_QUALITY_REPORTS_DIR,
    MERGED_GRAPHS_DIR,
    ONTOLOGY_DIR,
    PROCESSED_DIR,
    RAW_GRAPHS_DIR,
    RELATION_CLEANED_GRAPHS_DIR,
    STRATEGY_DIR,
    UPLOAD_DIR,
)


RESULT_RETENTION_DIRS = (
    UPLOAD_DIR,
    EXTRACTED_TEXT_DIR,
    STRATEGY_DIR,
    ONTOLOGY_DIR,
    CHUNKS_DIR,
    CHUNK_QUALITY_DIR,
    RAW_GRAPHS_DIR,
    CLEANED_GRAPHS_DIR,
    MERGED_GRAPHS_DIR,
    RELATION_CLEANED_GRAPHS_DIR,
    GRAPH_QUALITY_REPORTS_DIR,
    FINAL_GRAPHS_DIR,
    PROCESSED_DIR,
)

EXTRACTION_FILE_PATTERN = re.compile(r"^(?P<extraction_id>[0-9a-fA-F]{32})(?:[_.].*)?$")


def get_file_extraction_id(path: Path) -> str | None:
    match = EXTRACTION_FILE_PATTERN.fullmatch(path.name)
    if not match:
        return None

    return match.group("extraction_id").lower()


def cleanup_old_intermediate_results(current_extraction_id: str) -> dict[str, object]:
    """Delete generated artifacts for all runs except the current extraction id."""

    safe_current_id = Path(current_extraction_id).name.lower()
    deleted_paths: list[str] = []
    failed_paths: list[dict[str, str]] = []
    kept_count = 0
    skipped_count = 0

    for directory in RESULT_RETENTION_DIRS:
        if not directory.exists():
            continue

        for path in directory.iterdir():
            if not path.is_file():
                skipped_count += 1
                continue

            file_extraction_id = get_file_extraction_id(path)
            if file_extraction_id is None:
                skipped_count += 1
                continue

            if file_extraction_id == safe_current_id:
                kept_count += 1
                continue

            try:
                path.unlink()
                deleted_paths.append(str(path))
            except OSError as error:
                failed_paths.append({"path": str(path), "error": str(error)})

    return {
        "success": not failed_paths,
        "current_extraction_id": safe_current_id,
        "deleted_count": len(deleted_paths),
        "kept_count": kept_count,
        "skipped_count": skipped_count,
        "failed_count": len(failed_paths),
        "deleted_paths": deleted_paths,
        "failed_paths": failed_paths,
    }
