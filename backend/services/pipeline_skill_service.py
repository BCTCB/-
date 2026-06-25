"""Skill registry for the knowledge extraction pipeline."""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from services.chunk_service import analyze_split_strategy_from_extraction, execute_chunking_from_extraction
from services.final_graph_service import generate_final_knowledge_graph
from services.graph_clean_service import clean_raw_graph_exact_duplicates
from services.graph_extract_service import execute_graph_extraction_from_chunks
from services.graph_merge_service import merge_cleaned_graph_semantic_nodes
from services.graph_quality_report_service import generate_graph_quality_report
from services.graph_relation_clean_service import clean_merged_graph_relations
from services.ontology_service import generate_ontology_draft
from services.pdf_service import convert_uploaded_pdf_to_txt


SkillRunner = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class KnowledgeExtractionSkill:
    key: str
    stage: str
    title: str
    label: str
    done_label: str
    description: str
    required_inputs: tuple[str, ...]
    output_path_field: str
    runner: SkillRunner

    def metadata(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "stage": self.stage,
            "title": self.title,
            "label": self.label,
            "doneLabel": self.done_label,
            "description": self.description,
            "required_inputs": list(self.required_inputs),
            "output_path_field": self.output_path_field,
        }

    def build_step(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "skill": self.key,
            "title": self.title,
            "success": bool(result.get("success")),
            "message": result.get("message", ""),
            "output_path": result.get(self.output_path_field, ""),
        }


def _require_extraction_id(context: dict[str, Any]) -> str:
    extraction_id = context.get("extraction_id")

    if not extraction_id:
        raise ValueError("请先完成文本提取步骤")

    return str(extraction_id)


async def _run_pdf_to_text(context: dict[str, Any]) -> dict[str, Any]:
    file = context.get("file")

    if file is None or not hasattr(file, "filename") or not hasattr(file, "read"):
        raise ValueError("文本提取 skill 需要上传 PDF 文件")

    return await convert_uploaded_pdf_to_txt(
        file=file,
        entity_types=context.get("entity_types") or [],
        relations=context.get("relations") or [],
    )


def _run_ontology_draft(context: dict[str, Any]) -> dict[str, Any]:
    return generate_ontology_draft(
        extraction_id=_require_extraction_id(context),
        document_summary=str(context.get("document_summary") or ""),
        user_goal=str(context.get("user_goal") or ""),
    )


def _run_split_strategy(context: dict[str, Any]) -> dict[str, Any]:
    return analyze_split_strategy_from_extraction(_require_extraction_id(context))


def _run_chunking(context: dict[str, Any]) -> dict[str, Any]:
    return execute_chunking_from_extraction(_require_extraction_id(context))


def _run_graph_extraction(context: dict[str, Any]) -> dict[str, Any]:
    ontology = context.get("ontology") or {}
    relations = context.get("relations") or ontology.get("relations", [])

    return execute_graph_extraction_from_chunks(
        extraction_id=_require_extraction_id(context),
        mode="ontology",
        allowed_entity_types=context.get("allowed_entity_types") or ontology.get("entity_types", []),
        allowed_relation_types=context.get("allowed_relation_types") or ontology.get("relation_types", []),
        allowed_relations=relations,
    )


def _run_exact_cleaning(context: dict[str, Any]) -> dict[str, Any]:
    return clean_raw_graph_exact_duplicates(_require_extraction_id(context))


def _run_semantic_node_merge(context: dict[str, Any]) -> dict[str, Any]:
    return merge_cleaned_graph_semantic_nodes(_require_extraction_id(context))


def _run_relation_cleaning(context: dict[str, Any]) -> dict[str, Any]:
    return clean_merged_graph_relations(_require_extraction_id(context))


def _run_quality_report(context: dict[str, Any]) -> dict[str, Any]:
    return generate_graph_quality_report(_require_extraction_id(context))


def _run_final_graph(context: dict[str, Any]) -> dict[str, Any]:
    return generate_final_knowledge_graph(_require_extraction_id(context))


PIPELINE_SKILLS: tuple[KnowledgeExtractionSkill, ...] = (
    KnowledgeExtractionSkill(
        key="pdf_text_extraction",
        stage="pdf_to_text",
        title="文本提取",
        label="正在读取 PDF 并提取文本",
        done_label="PDF 文本提取完成",
        description="上传 PDF，提取全文并保存为后续流程使用的 TXT。",
        required_inputs=("file",),
        output_path_field="txt_path",
        runner=_run_pdf_to_text,
    ),
    KnowledgeExtractionSkill(
        key="ontology_draft_generation",
        stage="ontology_draft",
        title="本体草案生成",
        label="正在根据文档摘要和用户目标生成本体草案",
        done_label="本体草案生成完成",
        description="根据文档摘要和建图目标生成实体类型、关系类型和关系约束。",
        required_inputs=("extraction_id", "document_summary", "user_goal"),
        output_path_field="ontology_path",
        runner=_run_ontology_draft,
    ),
    KnowledgeExtractionSkill(
        key="split_strategy_analysis",
        stage="split_strategy",
        title="切分策略选择",
        label="正在分析并选择切分策略",
        done_label="切分策略选择完成",
        description="分析文本结构，选择适合知识图谱抽取的切分策略。",
        required_inputs=("extraction_id",),
        output_path_field="strategy_path",
        runner=_run_split_strategy,
    ),
    KnowledgeExtractionSkill(
        key="text_chunking",
        stage="chunking",
        title="执行切分",
        label="正在按策略切分文本",
        done_label="文本切分完成",
        description="按切分策略生成 chunks，并输出 chunk 质量检查结果。",
        required_inputs=("extraction_id",),
        output_path_field="chunks_json_path",
        runner=_run_chunking,
    ),
    KnowledgeExtractionSkill(
        key="ontology_instantiation",
        stage="graph_extraction",
        title="本体实例化",
        label="正在根据本体草案生成实例节点和关系",
        done_label="本体实例化完成",
        description="基于 chunks 和本体约束抽取实体、关系，生成原始图谱。",
        required_inputs=("extraction_id",),
        output_path_field="raw_graph_json_path",
        runner=_run_graph_extraction,
    ),
    KnowledgeExtractionSkill(
        key="exact_duplicate_cleaning",
        stage="exact_cleaning",
        title="重复内容清理",
        label="正在清理重复实体和关系",
        done_label="重复内容清理完成",
        description="清理完全重复的节点和边，生成去重后的图谱。",
        required_inputs=("extraction_id",),
        output_path_field="cleaned_graph_json_path",
        runner=_run_exact_cleaning,
    ),
    KnowledgeExtractionSkill(
        key="semantic_node_merge",
        stage="semantic_node_merge",
        title="相近节点合并",
        label="正在合并语义相近的节点",
        done_label="相近节点合并完成",
        description="识别语义相近节点并进行归并，减少概念重复。",
        required_inputs=("extraction_id",),
        output_path_field="merged_graph_json_path",
        runner=_run_semantic_node_merge,
    ),
    KnowledgeExtractionSkill(
        key="relation_cleaning",
        stage="relation_cleaning",
        title="关系清洗",
        label="正在规范和清洗关系",
        done_label="关系清洗完成",
        description="规范关系命名并清理低质量关系。",
        required_inputs=("extraction_id",),
        output_path_field="relation_cleaned_graph_json_path",
        runner=_run_relation_cleaning,
    ),
    KnowledgeExtractionSkill(
        key="graph_quality_report",
        stage="quality_report",
        title="质量报告",
        label="正在生成图谱质量报告",
        done_label="质量报告生成完成",
        description="统计图谱质量指标，输出可审核的质量报告。",
        required_inputs=("extraction_id",),
        output_path_field="quality_report_path",
        runner=_run_quality_report,
    ),
    KnowledgeExtractionSkill(
        key="final_graph_generation",
        stage="final_graph",
        title="最终图谱生成",
        label="正在生成最终知识图谱",
        done_label="最终知识图谱生成完成",
        description="结合清洗后图谱和质量报告，生成最终展示用知识图谱。",
        required_inputs=("extraction_id",),
        output_path_field="final_graph_json_path",
        runner=_run_final_graph,
    ),
)

PIPELINE_SKILL_MAP = {skill.key: skill for skill in PIPELINE_SKILLS}


def list_pipeline_skills() -> list[dict[str, Any]]:
    return [skill.metadata() for skill in PIPELINE_SKILLS]


async def execute_pipeline_skill(
    skill: KnowledgeExtractionSkill,
    context: dict[str, Any],
) -> dict[str, Any]:
    result = skill.runner(context)

    if inspect.isawaitable(result):
        result = await result

    return result
