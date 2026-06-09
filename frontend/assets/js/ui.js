(function () {
  const state = window.KGState;
  const { generateKnowledgeGraph, getPipelineStages } = window.KGApi;
  const { clearGraph, fitGraph, renderGraph } = window.KGGraph;
  const $ = selector => document.querySelector(selector);
  const pipelineStages = getPipelineStages();

  function getSelectedMode() {
    const selected = $('input[name="extractionMode"]:checked');
    return selected ? selected.value : "auto";
  }

  function getUniqueRelationTypes() {
    return Array.from(
      new Set(
        state.relations
          .map(item => item.relation.trim())
          .filter(Boolean)
      )
    );
  }

  function setStatus(message) {
    $("#statusBox").textContent = message;
  }

  function setProgress(percent, message) {
    const value = Math.max(0, Math.min(100, Math.round(percent)));
    const progressTrack = $(".progress-track");

    $("#progressBarFill").style.width = value + "%";
    $("#progressPercentText").textContent = value + "%";
    $("#progressStepText").textContent = message;

    if (progressTrack) {
      progressTrack.setAttribute("aria-valuenow", String(value));
    }
  }

  function resetProgress(message) {
    setProgress(0, message || "等待开始处理。");
  }

  function updatePipelineProgress(progress) {
    const completedStages = progress.phase === "done"
      ? progress.stageIndex + 1
      : progress.stageIndex;
    const percent = (completedStages / progress.stageCount) * 100;
    const message = progress.phase === "done"
      ? progress.stage.doneLabel
      : progress.stage.label;

    setProgress(percent, message);
  }

  function handleModeChange() {
    state.extractionMode = getSelectedMode();
    const isCustom = state.extractionMode === "custom";
    $("#customConfig").classList.toggle("hidden", !isCustom);
    $("#modeText").textContent = isCustom ? "自定义抽取" : "默认抽取";
  }

  function openPdfSelector() {
    $("#pdfInput").click();
  }

  function handlePdfSelect(event) {
    const file = event.target.files[0];

    if (!file) return;

    if (file.type !== "application/pdf") {
      alert("请选择 PDF 文件");
      return;
    }

    state.selectedPdfFile = file;
    $("#fileNameText").textContent = file.name;
    resetProgress("等待开始处理。");
    setStatus("已选择 PDF：" + file.name);
  }

  function renderEntityTypes() {
    const box = $("#entityList");
    box.innerHTML = "";

    if (state.entityTypes.length === 0) {
      box.innerHTML = `<div class="empty">暂无抽取对象。</div>`;
    }

    state.entityTypes.forEach((type, index) => {
      const tag = document.createElement("div");
      tag.className = "tag";
      tag.innerHTML = `
        ${type}
        <button type="button" data-remove-entity="${index}">×</button>
      `;
      box.appendChild(tag);
    });

    $("#entityCountText").textContent = state.entityTypes.length + " 个";
  }

  function openEntityModal() {
    $("#entityModal").classList.add("show");
    setTimeout(() => {
      $("#entityInput").focus();
    }, 50);
  }

  function closeEntityModal() {
    $("#entityModal").classList.remove("show");
    $("#entityInput").value = "";
  }

  function addEntityType() {
    const input = $("#entityInput");
    const value = input.value.trim();

    if (!value) {
      alert("请输入对象类型名称");
      return;
    }

    if (!state.entityTypes.includes(value)) {
      state.entityTypes.push(value);
    }

    renderEntityTypes();
    renderRelations();
    closeEntityModal();
  }

  function removeEntityType(index) {
    const removedType = state.entityTypes[index];
    state.entityTypes.splice(index, 1);
    state.relations = state.relations.filter(r => {
      return r.from !== removedType && r.to !== removedType;
    });

    renderEntityTypes();
    renderRelations();
  }

  function renderRelations() {
    const box = $("#relationList");
    box.innerHTML = "";

    if (state.relations.length === 0) {
      box.innerHTML = `<div class="empty">暂无关系规则。</div>`;
    }

    state.relations.forEach((relation, index) => {
      const item = document.createElement("div");
      item.className = "relation-box";
      item.innerHTML = `
        <div class="relation-box-top">
          <div class="relation-text">
            <strong>${relation.from}</strong>
            —— ${relation.relation} ——
            <strong>${relation.to}</strong>
          </div>

          <button
            type="button"
            class="danger mini-delete"
            data-remove-relation="${index}"
          >
            删除
          </button>
        </div>
      `;
      box.appendChild(item);
    });

    $("#relationCountText").textContent = state.relations.length + " 条";
  }

  function openRelationModal() {
    if (state.entityTypes.length < 2) {
      alert("请至少添加两个抽取对象，再建立关系。");
      return;
    }

    refreshRelationSelectOptions();
    $("#relationModal").classList.add("show");
    setTimeout(() => {
      $("#relationNameInput").focus();
    }, 50);
  }

  function closeRelationModal() {
    $("#relationModal").classList.remove("show");
    $("#relationNameInput").value = "";
  }

  function refreshRelationSelectOptions() {
    const fromSelect = $("#fromTypeSelect");
    const toSelect = $("#toTypeSelect");

    fromSelect.innerHTML = "";
    toSelect.innerHTML = "";

    state.entityTypes.forEach(type => {
      const fromOption = document.createElement("option");
      fromOption.value = type;
      fromOption.textContent = type;
      fromSelect.appendChild(fromOption);

      const toOption = document.createElement("option");
      toOption.value = type;
      toOption.textContent = type;
      toSelect.appendChild(toOption);
    });
  }

  function addRelation() {
    const from = $("#fromTypeSelect").value;
    const relation = $("#relationNameInput").value.trim();
    const to = $("#toTypeSelect").value;

    if (!from || !relation || !to) {
      alert("请完整填写关系规则");
      return;
    }

    state.relations.push({ from, relation, to });
    renderRelations();
    closeRelationModal();
  }

  function removeRelation(index) {
    state.relations.splice(index, 1);
    renderRelations();
  }

  async function startExtraction() {
    if (!state.selectedPdfFile) {
      alert("请先选择 PDF 文件");
      return;
    }

    const extractButton = $("#extractButton");
    extractButton.disabled = true;
    resetProgress(pipelineStages[0].label);
    setStatus("正在生成知识图谱，请稍候...");

    try {
      const mode = getSelectedMode();
      const result = await generateKnowledgeGraph({
        file: state.selectedPdfFile,
        mode,
        entityTypes: state.entityTypes,
        relations: state.relations,
        relationTypes: getUniqueRelationTypes(),
        onProgress: updatePipelineProgress
      });

      clearGraph();
      renderGraph(result);
      setProgress(100, "知识图谱生成完成。");
      setStatus(
        `知识图谱生成完成，编号：${result.extraction_id}。节点 ${result.report.node_count} 个，关系 ${result.report.edge_count} 条。`
      );
    } catch (error) {
      $("#progressStepText").textContent = "处理失败：" + error.message;
      setStatus("处理失败：" + error.message);
    } finally {
      extractButton.disabled = false;
    }
  }

  function handleGlobalKeydown(event) {
    if (event.key === "Escape") {
      closeEntityModal();
      closeRelationModal();
    }

    if (event.key === "Enter") {
      const entityModalOpen = $("#entityModal").classList.contains("show");
      const relationModalOpen = $("#relationModal").classList.contains("show");

      if (entityModalOpen) {
        addEntityType();
      }

      if (relationModalOpen) {
        addRelation();
      }
    }
  }

  function bindEvents() {
    $("#pdfInput").addEventListener("change", handlePdfSelect);
    $("#pdfSelectButton").addEventListener("click", openPdfSelector);
    $("#extractButton").addEventListener("click", startExtraction);
    $("#fitGraphButton").addEventListener("click", fitGraph);
    $("#clearGraphButton").addEventListener("click", () => {
      clearGraph();
      resetProgress("等待开始处理。");
      setStatus("图谱已清空。");
    });

    document.querySelectorAll('input[name="extractionMode"]').forEach(input => {
      input.addEventListener("change", handleModeChange);
    });

    $("#openEntityModalButton").addEventListener("click", openEntityModal);
    $("#closeEntityModalButton").addEventListener("click", closeEntityModal);
    $("#cancelEntityButton").addEventListener("click", closeEntityModal);
    $("#confirmEntityButton").addEventListener("click", addEntityType);
    $("#entityList").addEventListener("click", event => {
      const button = event.target.closest("[data-remove-entity]");
      if (!button) return;
      removeEntityType(Number(button.dataset.removeEntity));
    });

    $("#openRelationModalButton").addEventListener("click", openRelationModal);
    $("#closeRelationModalButton").addEventListener("click", closeRelationModal);
    $("#cancelRelationButton").addEventListener("click", closeRelationModal);
    $("#confirmRelationButton").addEventListener("click", addRelation);
    $("#relationList").addEventListener("click", event => {
      const button = event.target.closest("[data-remove-relation]");
      if (!button) return;
      removeRelation(Number(button.dataset.removeRelation));
    });

    document.addEventListener("keydown", handleGlobalKeydown);
  }

  function initApp() {
    bindEvents();
    handleModeChange();
    renderEntityTypes();
    renderRelations();
    resetProgress("等待开始处理。");
  }

  window.KGUI = {
    initApp
  };
})();
