(function () {
  const { API_BASE_URL } = window.KGConfig;

  async function parseResponse(response, fallbackMessage) {
    const result = await response.json();

    if (!response.ok || !result.success) {
      const message = result.detail || result.message || fallbackMessage;
      throw new Error(message);
    }

    return result;
  }

  async function postJson(path, payload, fallbackMessage) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    return parseResponse(response, fallbackMessage);
  }

  function getPipelineStages() {
    return [
      {
        key: "upload",
        title: "文本提取",
        label: "正在读取 PDF 并提取文本",
        doneLabel: "PDF 文本提取完成"
      },
      {
        key: "ontology",
        title: "本体草案生成",
        label: "正在根据文档摘要和用户目标生成本体草案",
        doneLabel: "本体草案生成完成"
      },
      {
        key: "strategy",
        title: "切分策略选择",
        label: "正在分析并选择切分策略",
        doneLabel: "切分策略选择完成"
      },
      {
        key: "chunk",
        title: "执行切分",
        label: "正在按策略切分文本",
        doneLabel: "文本切分完成"
      },
      {
        key: "extract",
        title: "本体实例化",
        label: "正在根据本体草案生成实例节点和关系",
        doneLabel: "本体实例化完成"
      },
      {
        key: "clean",
        title: "重复内容清理",
        label: "正在清理重复实体和关系",
        doneLabel: "重复内容清理完成"
      },
      {
        key: "merge",
        title: "相近节点合并",
        label: "正在合并语义相近的节点",
        doneLabel: "相近节点合并完成"
      },
      {
        key: "relationClean",
        title: "关系清洗",
        label: "正在规范和清洗关系",
        doneLabel: "关系清洗完成"
      },
      {
        key: "quality",
        title: "质量报告",
        label: "正在生成图谱质量报告",
        doneLabel: "质量报告生成完成"
      },
      {
        key: "final",
        title: "最终图谱生成",
        label: "正在生成最终知识图谱",
        doneLabel: "最终知识图谱生成完成"
      }
    ];
  }

  async function runPipelineStep({
    stageKey,
    file,
    extractionId,
    documentSummary,
    userGoal,
    entityTypes,
    relations,
    relationTypes
  }) {
    if (stageKey === "upload") {
      return uploadPdfToText({
        file,
        entityTypes,
        relations
      });
    }

    if (!extractionId) {
      throw new Error("请先完成文本提取步骤");
    }

    const payload = { extraction_id: extractionId };
    const stepMap = {
      ontology: {
        path: "/api/graph/ontology/draft",
        payload: {
          ...payload,
          document_summary: documentSummary,
          user_goal: userGoal
        },
        fallback: "本体草案生成失败"
      },
      strategy: {
        path: "/api/chunk/strategy",
        payload,
        fallback: "切分策略分析失败"
      },
      chunk: {
        path: "/api/chunk/execute",
        payload,
        fallback: "文本切分失败"
      },
      extract: {
        path: "/api/graph/extract",
        payload: {
          ...payload,
          allowed_entity_types: entityTypes || [],
          allowed_relation_types: relationTypes || [],
          allowed_relations: relations || []
        },
        fallback: "本体实例化失败"
      },
      clean: {
        path: "/api/graph/clean",
        payload,
        fallback: "图谱清洗失败"
      },
      merge: {
        path: "/api/graph/merge",
        payload,
        fallback: "图谱语义合并失败"
      },
      relationClean: {
        path: "/api/graph/relations/clean",
        payload,
        fallback: "图谱关系清洗失败"
      },
      quality: {
        path: "/api/graph/quality/report",
        payload,
        fallback: "质量报告生成失败"
      },
      final: {
        path: "/api/graph/final/generate",
        payload,
        fallback: "最终知识图谱生成失败"
      }
    };

    const step = stepMap[stageKey];
    if (!step) {
      throw new Error("未知流程步骤：" + stageKey);
    }

    return postJson(step.path, step.payload, step.fallback);
  }

  async function uploadPdfToText({ file, entityTypes, relations }) {
    const formData = new FormData();
    formData.append("file", file);

    if (Array.isArray(entityTypes) && entityTypes.length) {
      formData.append("entity_types", JSON.stringify(entityTypes));
    }

    if (Array.isArray(relations) && relations.length) {
      formData.append("relations", JSON.stringify(relations));
    }

    const response = await fetch(`${API_BASE_URL}/api/pdf/to-txt`, {
      method: "POST",
      body: formData
    });

    return parseResponse(response, "PDF 文本提取失败");
  }

  async function updateOntologyDraft({ extractionId, ontology }) {
    return postJson(
      "/api/graph/ontology/update",
      {
        extraction_id: extractionId,
        ontology
      },
      "本体草案保存失败"
    );
  }

  async function updateExtractedText({ extractionId, text }) {
    return postJson(
      "/api/pdf/text/update",
      {
        extraction_id: extractionId,
        text
      },
      "提取文本保存失败"
    );
  }

  async function updateGraphInstantiation({ extractionId, nodes, edges }) {
    return postJson(
      "/api/graph/instances/update",
      {
        extraction_id: extractionId,
        nodes,
        edges
      },
      "本体实例化结果保存失败"
    );
  }

  async function chatWithMasterAgent({
    message,
    projectId,
    extractionId,
    documentSummary,
    userGoal,
    selectedFeature,
    history
  }) {
    return postJson(
      "/api/agent/master/chat",
      {
        message,
        project_id: projectId || null,
        extraction_id: extractionId || null,
        document_summary: documentSummary || null,
        user_goal: userGoal || null,
        selected_feature: selectedFeature || null,
        history: history || []
      },
      "主控 Agent 暂时无法回复"
    );
  }

  async function executeApprovedWorkflow({
    workflow,
    projectId,
    extractionId,
    documentSummary,
    userGoal,
    entityTypes,
    relationTypes,
    relations
  }) {
    return postJson(
      "/api/agent/workflow/execute",
      {
        workflow,
        approved: true,
        project_id: projectId || null,
        extraction_id: extractionId || null,
        document_summary: documentSummary || null,
        user_goal: userGoal || null,
        entity_types: entityTypes || [],
        relation_types: relationTypes || [],
        relations: relations || []
      },
      "Workflow 执行失败"
    );
  }

  async function generateKnowledgeGraph({
    file,
    documentSummary,
    userGoal,
    entityTypes,
    relations,
    relationTypes,
    onProgress
  }) {
    const stages = getPipelineStages();
    let extractionId = "";
    let finalResult = null;
    let ontologyEntityTypes = entityTypes || [];
    let ontologyRelations = relations || [];
    let ontologyRelationTypes = relationTypes || [];

    for (let stageIndex = 0; stageIndex < stages.length; stageIndex += 1) {
      const stage = stages[stageIndex];

      if (typeof onProgress === "function") {
        onProgress({
          stageIndex,
          stageCount: stages.length,
          stage,
          phase: "active"
        });
      }

      const result = await runPipelineStep({
        stageKey: stage.key,
        file,
        extraction_id: extractionId,
        extractionId,
        documentSummary,
        userGoal,
        entityTypes: ontologyEntityTypes,
        relations: ontologyRelations,
        relationTypes: ontologyRelationTypes
      });

      extractionId = result.extraction_id || extractionId;
      finalResult = result;

      if (stage.key === "ontology") {
        ontologyEntityTypes = result.entity_types || (result.ontology && result.ontology.entity_types) || [];
        ontologyRelations = result.relations || (result.ontology && result.ontology.relations) || [];
        ontologyRelationTypes = result.relation_types || (result.ontology && result.ontology.relation_types) || [];
      }

      if (typeof onProgress === "function") {
        onProgress({
          stageIndex,
          stageCount: stages.length,
          stage,
          phase: "done"
        });
      }
    }

    return {
      ...finalResult,
      message: "PDF 到最终知识图谱的一键流程已完成"
    };
  }

  window.KGApi = {
    chatWithMasterAgent,
    executeApprovedWorkflow,
    generateKnowledgeGraph,
    getPipelineStages,
    runPipelineStep,
    uploadPdfToText,
    updateExtractedText,
    updateGraphInstantiation,
    updateOntologyDraft
  };
})();
