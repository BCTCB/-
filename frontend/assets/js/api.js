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
        label: "正在读取 PDF 并提取文本",
        doneLabel: "PDF 文本提取完成"
      },
      {
        key: "chunk",
        label: "正在分析切分策略并切分文本",
        doneLabel: "文本切分完成"
      },
      {
        key: "extract",
        label: "正在从文本块中抽取实体和关系",
        doneLabel: "实体与关系抽取完成"
      },
      {
        key: "clean",
        label: "正在清理重复实体和关系",
        doneLabel: "重复内容清理完成"
      },
      {
        key: "merge",
        label: "正在合并语义相近的节点",
        doneLabel: "相近节点合并完成"
      },
      {
        key: "relationClean",
        label: "正在规范和清洗关系",
        doneLabel: "关系清洗完成"
      },
      {
        key: "quality",
        label: "正在生成图谱质量报告",
        doneLabel: "质量报告生成完成"
      },
      {
        key: "final",
        label: "正在生成最终知识图谱",
        doneLabel: "最终知识图谱生成完成"
      }
    ];
  }

  async function generateKnowledgeGraph({
    file,
    mode,
    entityTypes,
    relations,
    relationTypes,
    onProgress
  }) {
    const stages = getPipelineStages();
    const reportProgress = (stageIndex, phase) => {
      if (typeof onProgress === "function") {
        onProgress({
          stageIndex,
          stageCount: stages.length,
          stage: stages[stageIndex],
          phase
        });
      }
    };

    const formData = new FormData();
    formData.append("file", file);

    if (mode === "custom") {
      formData.append("entity_types", JSON.stringify(entityTypes));
      formData.append("relations", JSON.stringify(relations));
    }

    reportProgress(0, "active");
    const uploadResponse = await fetch(`${API_BASE_URL}/api/pdf/to-txt`, {
      method: "POST",
      body: formData
    });
    const uploadResult = await parseResponse(uploadResponse, "PDF 文本提取失败");
    const extractionId = uploadResult.extraction_id;
    reportProgress(0, "done");

    reportProgress(1, "active");
    await postJson(
      "/api/chunk/run",
      { extraction_id: extractionId },
      "文本切分失败"
    );
    reportProgress(1, "done");

    reportProgress(2, "active");
    await postJson(
      "/api/graph/extract",
      {
        extraction_id: extractionId,
        mode,
        allowed_entity_types: mode === "custom" ? entityTypes : [],
        allowed_relation_types: mode === "custom" ? relationTypes : []
      },
      "知识图谱抽取失败"
    );
    reportProgress(2, "done");

    reportProgress(3, "active");
    await postJson(
      "/api/graph/clean",
      { extraction_id: extractionId },
      "图谱清洗失败"
    );
    reportProgress(3, "done");

    reportProgress(4, "active");
    await postJson(
      "/api/graph/merge",
      { extraction_id: extractionId },
      "图谱语义合并失败"
    );
    reportProgress(4, "done");

    reportProgress(5, "active");
    await postJson(
      "/api/graph/relations/clean",
      { extraction_id: extractionId },
      "图谱关系清洗失败"
    );
    reportProgress(5, "done");

    reportProgress(6, "active");
    await postJson(
      "/api/graph/quality/report",
      { extraction_id: extractionId },
      "质量报告生成失败"
    );
    reportProgress(6, "done");

    reportProgress(7, "active");
    const finalResult = await postJson(
      "/api/graph/final/generate",
      { extraction_id: extractionId },
      "最终知识图谱生成失败"
    );
    reportProgress(7, "done");

    return {
      ...finalResult,
      message: "PDF 到最终知识图谱的一键流程已完成"
    };
  }

  window.KGApi = {
    generateKnowledgeGraph,
    getPipelineStages
  };
})();
