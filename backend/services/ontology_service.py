"""Generate and persist ontology drafts from user intent."""

from pathlib import Path
from typing import Any

from config import ONTOLOGY_DIR
from services.llm_service import chat_json
from utils.json_utils import extract_json_from_text, read_json, write_json


ONTOLOGY_SYSTEM_PROMPT = """
你是知识图谱本体设计助手。请根据用户提供的文档摘要和建图目标，生成适合后续本体实例化的本体草案。

要求：
1. 只输出 JSON，不要输出 Markdown。
2. entity_types 保持 5 到 12 个，名称简短、互不重叠。
3. relation_types 保持 6 到 16 个，使用动词或短语。
4. relations 中的 from/to 必须来自 entity_types，relation 必须来自 relation_types。
5. 本体应服务用户目标，避免泛泛而谈。
6. 如果信息不足，也要给出保守可执行的草案。

输出格式：
{
  "entity_types": ["实体类型"],
  "relation_types": ["关系类型"],
  "relations": [
    {"from": "实体类型", "relation": "关系类型", "to": "实体类型"}
  ],
  "design_notes": ["设计说明"]
}
""".strip()


def get_ontology_draft_path(extraction_id: str) -> Path:
    safe_id = Path(extraction_id).name
    return ONTOLOGY_DIR / f"{safe_id}_ontology_draft.json"


def normalize_name(value: Any, max_chars: int = 80) -> str:
    return " ".join(str(value or "").split()).strip()[:max_chars]


def unique_names(values: Any, max_items: int) -> list[str]:
    if not isinstance(values, list):
        return []

    seen: set[str] = set()
    results: list[str] = []

    for value in values:
        name = normalize_name(value)
        if not name or name in seen:
            continue

        seen.add(name)
        results.append(name)

        if len(results) >= max_items:
            break

    return results


def normalize_relations(
    relations: Any,
    entity_types: list[str],
    relation_types: list[str],
    max_items: int = 24,
) -> list[dict[str, str]]:
    if not isinstance(relations, list):
        return []

    entity_type_set = set(entity_types)
    relation_type_set = set(relation_types)
    seen: set[tuple[str, str, str]] = set()
    results: list[dict[str, str]] = []

    for relation in relations:
        if not isinstance(relation, dict):
            continue

        source_type = normalize_name(relation.get("from"))
        relation_name = normalize_name(relation.get("relation"))
        target_type = normalize_name(relation.get("to"))
        key = (source_type, relation_name, target_type)

        if source_type not in entity_type_set:
            continue

        if relation_name not in relation_type_set:
            continue

        if target_type not in entity_type_set:
            continue

        if key in seen:
            continue

        seen.add(key)
        results.append(
            {
                "from": source_type,
                "relation": relation_name,
                "to": target_type,
            }
        )

        if len(results) >= max_items:
            break

    return results


def normalize_ontology_payload(raw_payload: Any) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        raise ValueError("本体草案必须是 JSON object")

    entity_types = unique_names(raw_payload.get("entity_types"), 12)
    relation_types = unique_names(raw_payload.get("relation_types"), 16)
    relations = normalize_relations(raw_payload.get("relations"), entity_types, relation_types)
    design_notes = unique_names(raw_payload.get("design_notes"), 8)

    if not entity_types:
        raise ValueError("本体草案缺少 entity_types")

    if not relation_types:
        raise ValueError("本体草案缺少 relation_types")

    if not relations:
        raise ValueError("本体草案缺少可执行的 relations")

    return {
        "entity_types": entity_types,
        "relation_types": relation_types,
        "relations": relations,
        "design_notes": design_notes,
    }


def generate_ontology_draft(
    extraction_id: str,
    document_summary: str,
    user_goal: str,
) -> dict[str, Any]:
    document_summary = normalize_name(document_summary, 4000)
    user_goal = normalize_name(user_goal, 1200)

    if not document_summary:
        raise ValueError("请先填写文档摘要")

    if not user_goal:
        raise ValueError("请先填写用户目标")

    user_prompt = f"""
文档摘要：
{document_summary}

用户目标：
{user_goal}
""".strip()
    response_text = chat_json(
        system_prompt=ONTOLOGY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
    )
    ontology = normalize_ontology_payload(extract_json_from_text(response_text))
    output = {
        "success": True,
        "message": "本体草案已生成",
        "extraction_id": Path(extraction_id).name,
        "document_summary": document_summary,
        "user_goal": user_goal,
        "ontology": ontology,
        "entity_types": ontology["entity_types"],
        "relation_types": ontology["relation_types"],
        "relations": ontology["relations"],
        "next_stage": "graph_extraction",
    }
    ontology_path = get_ontology_draft_path(extraction_id)
    write_json(ontology_path, output)
    output["ontology_path"] = str(ontology_path)

    return output


def update_ontology_draft(
    extraction_id: str,
    ontology: dict[str, Any],
) -> dict[str, Any]:
    ontology_path = get_ontology_draft_path(extraction_id)

    if not ontology_path.exists():
        raise FileNotFoundError(f"找不到本体草案文件：{ontology_path}")

    existing_payload = read_json(ontology_path)
    normalized_ontology = normalize_ontology_payload(ontology)
    output = {
        **existing_payload,
        "success": True,
        "message": "本体草案已更新",
        "extraction_id": Path(extraction_id).name,
        "ontology": normalized_ontology,
        "entity_types": normalized_ontology["entity_types"],
        "relation_types": normalized_ontology["relation_types"],
        "relations": normalized_ontology["relations"],
        "next_stage": "graph_extraction",
    }
    write_json(ontology_path, output)
    output["ontology_path"] = str(ontology_path)

    return output


def load_ontology_draft(extraction_id: str) -> dict[str, Any] | None:
    ontology_path = get_ontology_draft_path(extraction_id)

    if not ontology_path.exists():
        return None

    return read_json(ontology_path)
