from fastapi import APIRouter, HTTPException

from schemas.graph_schema import (
    FinalGraphGenerateRequest,
    GraphCleanRequest,
    GraphExtractionRequest,
    GraphInstantiationUpdateRequest,
    GraphMergeRequest,
    GraphQualityReportRequest,
    GraphRelationCleanRequest,
    OntologyDraftRequest,
    OntologyUpdateRequest,
)
from services.final_graph_service import generate_final_knowledge_graph
from services.graph_clean_service import clean_raw_graph_exact_duplicates
from services.graph_extract_service import execute_graph_extraction_from_chunks, update_graph_instantiation
from services.graph_merge_service import merge_cleaned_graph_semantic_nodes
from services.graph_quality_report_service import generate_graph_quality_report
from services.graph_relation_clean_service import clean_merged_graph_relations
from services.ontology_service import generate_ontology_draft, update_ontology_draft


router = APIRouter(tags=["graph"])


@router.get("/graph/health")
def graph_health():
    return {"module": "graph", "status": "ok"}


@router.post("/graph/extract")
def extract_graph(request: GraphExtractionRequest):
    try:
        return execute_graph_extraction_from_chunks(
            extraction_id=request.extraction_id,
            mode="ontology",
            allowed_entity_types=request.allowed_entity_types,
            allowed_relation_types=request.allowed_relation_types,
            allowed_relations=request.allowed_relations,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"本体实例化失败：{error}") from error


@router.post("/api/graph/extract")
def api_extract_graph(request: GraphExtractionRequest):
    return extract_graph(request)


@router.post("/graph/instances/update")
def graph_instances_update(request: GraphInstantiationUpdateRequest):
    try:
        return update_graph_instantiation(
            extraction_id=request.extraction_id,
            nodes=request.nodes,
            edges=request.edges,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"本体实例化结果更新失败：{error}") from error


@router.post("/api/graph/instances/update")
def api_graph_instances_update(request: GraphInstantiationUpdateRequest):
    return graph_instances_update(request)


@router.post("/graph/ontology/draft")
def ontology_draft(request: OntologyDraftRequest):
    try:
        return generate_ontology_draft(
            extraction_id=request.extraction_id,
            document_summary=request.document_summary,
            user_goal=request.user_goal,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"本体草案生成失败：{error}") from error


@router.post("/api/graph/ontology/draft")
def api_ontology_draft(request: OntologyDraftRequest):
    return ontology_draft(request)


@router.post("/graph/ontology/update")
def ontology_update(request: OntologyUpdateRequest):
    try:
        return update_ontology_draft(
            extraction_id=request.extraction_id,
            ontology=request.ontology,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"本体草案更新失败：{error}") from error


@router.post("/api/graph/ontology/update")
def api_ontology_update(request: OntologyUpdateRequest):
    return ontology_update(request)


@router.post("/graph/clean")
def clean_graph(request: GraphCleanRequest):
    try:
        return clean_raw_graph_exact_duplicates(extraction_id=request.extraction_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"图谱清洗失败：{error}") from error


@router.post("/api/graph/clean")
def api_clean_graph(request: GraphCleanRequest):
    return clean_graph(request)


@router.post("/graph/merge")
def merge_graph(request: GraphMergeRequest):
    try:
        return merge_cleaned_graph_semantic_nodes(extraction_id=request.extraction_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"图谱语义合并失败：{error}") from error


@router.post("/api/graph/merge")
def api_merge_graph(request: GraphMergeRequest):
    return merge_graph(request)


@router.post("/graph/relations/clean")
def clean_graph_relations(request: GraphRelationCleanRequest):
    try:
        return clean_merged_graph_relations(extraction_id=request.extraction_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"图谱关系清洗失败：{error}") from error


@router.post("/api/graph/relations/clean")
def api_clean_graph_relations(request: GraphRelationCleanRequest):
    return clean_graph_relations(request)


@router.post("/graph/quality/report")
def graph_quality_report(request: GraphQualityReportRequest):
    try:
        return generate_graph_quality_report(extraction_id=request.extraction_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"图谱质量报告生成失败：{error}") from error


@router.post("/api/graph/quality/report")
def api_graph_quality_report(request: GraphQualityReportRequest):
    return graph_quality_report(request)


@router.post("/graph/final/generate")
def final_graph_generate(request: FinalGraphGenerateRequest):
    try:
        return generate_final_knowledge_graph(extraction_id=request.extraction_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"最终知识图谱生成失败：{error}") from error


@router.post("/api/graph/final/generate")
def api_final_graph_generate(request: FinalGraphGenerateRequest):
    return final_graph_generate(request)
