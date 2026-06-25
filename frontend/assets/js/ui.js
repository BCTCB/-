(function () {
  const state = window.KGState;
  const {
    chatWithMasterAgent,
    executeApprovedWorkflow,
    getPipelineStages,
    runPipelineStep,
    uploadPdfToText,
    updateExtractedText,
    updateGraphInstantiation,
    updateOntologyDraft
  } = window.KGApi;
  const { clearGraph, fitGraph, renderGraph } = window.KGGraph;
  const $ = selector => document.querySelector(selector);
  const pipelineStages = getPipelineStages();
  const AGENT_HISTORY_LIMIT = 12;
  const DEFAULT_PROJECTS = [
    {
      id: "project_demo",
      title: "示例项目",
      description: "上传一份 PDF 后，可从这里运行知识图谱抽取。",
      createdAt: Date.now(),
      updatedAt: Date.now()
    }
  ];

  function createConversationId(projectId) {
    return `conversation_${projectId}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  }

  function createConversation(projectId, title) {
    const now = Date.now();
    return {
      id: createConversationId(projectId),
      title: title || "新对话",
      createdAt: now,
      updatedAt: now
    };
  }

  function ensureProjectConversations(project) {
    if (!Array.isArray(project.conversations) || project.conversations.length === 0) {
      const conversation = createConversation(project.id);
      project.conversations = [conversation];
      project.activeConversationId = conversation.id;
    }

    if (!project.conversations.some(item => item.id === project.activeConversationId)) {
      project.activeConversationId = project.conversations[0].id;
    }

    return project.conversations;
  }

  function getActiveConversation() {
    const project = getActiveProject();
    if (!project) return null;
    return ensureProjectConversations(project)
      .find(item => item.id === state.activeConversationId) || null;
  }

  function updateActiveConversationTitle(content) {
    const conversation = getActiveConversation();
    if (!conversation) return;

    if (conversation.title === "新对话") {
      const normalized = String(content || "").replace(/\s+/g, " ").trim();
      if (normalized) {
        conversation.title = normalized.length > 22
          ? `${normalized.slice(0, 22)}…`
          : normalized;
      }
    }
    conversation.updatedAt = Date.now();
  }

  function createProject(title) {
    const now = Date.now();
    const id = `project_${now}_${Math.random().toString(16).slice(2)}`;
    const conversation = createConversation(id);
    return {
      id,
      title: title || `新项目 ${state.projects.length + 1}`,
      description: "等待上传文件并配置项目目标。",
      createdAt: now,
      updatedAt: now,
      activeConversationId: conversation.id,
      conversations: [conversation],
      files: [],
      fileName: "",
      selectedPdfFile: null,
      extractionId: "",
      activeFeature: "",
      documentSummary: "",
      userGoal: "",
      entityTypes: [],
      relationTypes: [],
      relations: [],
      ontologyDesignNotes: [],
      currentStepIndex: 0,
      approvedStepIndex: -1,
      stepResults: [],
      artifacts: [],
      activeArtifactId: "",
      currentGraphData: null,
      graphLayoutMode: "force"
    };
  }

  function getActiveProject() {
    return state.projects.find(project => project.id === state.activeProjectId) || null;
  }

  function saveActiveProjectSnapshot() {
    const project = getActiveProject();
    if (!project) return;

    project.activeConversationId = state.activeConversationId;
    project.selectedPdfFile = state.selectedPdfFile;
    project.fileName = state.selectedPdfFile ? state.selectedPdfFile.name : project.fileName || "";
    project.extractionId = state.extractionId;
    project.activeFeature = state.activeFeature;
    project.documentSummary = state.documentSummary;
    project.userGoal = state.userGoal;
    project.entityTypes = [...state.entityTypes];
    project.relationTypes = [...state.relationTypes];
    project.relations = state.relations.map(relation => ({ ...relation }));
    project.ontologyDesignNotes = [...state.ontologyDesignNotes];
    project.currentStepIndex = state.currentStepIndex;
    project.approvedStepIndex = state.approvedStepIndex;
    project.stepResults = [...state.stepResults];
    project.artifacts = (state.artifacts || []).map(artifact => ({ ...artifact }));
    project.activeArtifactId = state.activeArtifactId;
    project.currentGraphData = state.currentGraphData;
    project.graphLayoutMode = state.graphLayoutMode;
    project.updatedAt = Date.now();
  }

  function loadProject(project) {
    state.activeProjectId = project.id;
    ensureProjectConversations(project);
    state.activeConversationId = project.activeConversationId;
    state.selectedPdfFile = project.selectedPdfFile || null;
    state.extractionId = project.extractionId || "";
    state.activeFeature = project.activeFeature || "";
    state.documentSummary = project.documentSummary || "";
    state.userGoal = project.userGoal || "";
    state.entityTypes = [...(project.entityTypes || [])];
    state.relationTypes = [...(project.relationTypes || [])];
    state.relations = (project.relations || []).map(relation => ({ ...relation }));
    state.ontologyDesignNotes = [...(project.ontologyDesignNotes || [])];
    state.currentStepIndex = project.currentStepIndex || 0;
    state.approvedStepIndex = Number.isInteger(project.approvedStepIndex) ? project.approvedStepIndex : -1;
    state.stepResults = [...(project.stepResults || [])];
    state.artifacts = (project.artifacts || []).map(artifact => ({ ...artifact }));
    state.activeArtifactId = project.activeArtifactId || "";
    state.currentGraphData = project.currentGraphData || null;
    state.graphLayoutMode = project.graphLayoutMode || "force";

    $("#fileNameText").textContent = project.fileName || "尚未选择文件";
    if ($("#configFileNameText")) {
      $("#configFileNameText").textContent = project.fileName || "尚未选择文件";
    }

    showArtifactList();
    $("#workspaceSubtitle").textContent = project.description || "当前项目工作区";
    resetProgress(state.currentStepIndex > 0 ? "可以继续当前知识图谱流程。" : "等待开始处理。");
    setStatus(project.fileName ? "已选择 PDF：" + project.fileName : "等待上传 PDF。");
    renderProjectList();
    renderProjectFiles();
    renderChatMessages();
    renderStepList();
    updateActionButtons();
  }

  function renderProjectList() {
    const list = $("#projectList");
    const query = state.projectSearchQuery.trim().toLowerCase();
    const projects = state.projects.filter(project => {
      const conversationTitles = ensureProjectConversations(project)
        .map(conversation => conversation.title)
        .join(" ");
      if (!query) return true;
      return `${project.title} ${project.description} ${project.fileName || ""} ${conversationTitles}`
        .toLowerCase()
        .includes(query);
    });

    $("#projectCountText").textContent = `${state.projects.length} projects`;
    list.innerHTML = projects.map(project => {
      const conversations = ensureProjectConversations(project);
      const isExpanded = state.expandedProjectIds.includes(project.id);
      return `
      <div class="project-item ${project.id === state.activeProjectId ? "active" : ""} ${isExpanded ? "expanded" : ""}">
        <div class="project-item-header">
          <button
            type="button"
            class="project-select-button"
            data-project-id="${escapeHtml(project.id)}"
            aria-expanded="${isExpanded}"
          >
            <strong>${escapeHtml(project.title)}</strong>
            <span>${escapeHtml(project.fileName || project.description || "空项目")}</span>
          </button>
          ${conversations.length > 1 ? `
            <span
              class="project-conversation-status"
              title="该项目有 ${conversations.length} 个对话"
              aria-label="该项目有 ${conversations.length} 个对话"
            >•••</span>
          ` : ""}
          <button
            type="button"
            class="project-new-chat-button"
            data-new-chat-project-id="${escapeHtml(project.id)}"
            aria-label="在${escapeHtml(project.title)}中新建对话"
            title="新对话"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M7 18.5 3.5 21v-4.8A8 8 0 1 1 7 18.5Z"></path>
              <path d="M12 7.5v6M9 10.5h6"></path>
            </svg>
          </button>
        </div>
        ${isExpanded ? `
          <div class="project-conversation-list" aria-label="${escapeHtml(project.title)}的对话">
            ${conversations.map(conversation => `
              <button
                type="button"
                class="project-conversation-item ${project.id === state.activeProjectId && conversation.id === state.activeConversationId ? "active" : ""}"
                data-conversation-project-id="${escapeHtml(project.id)}"
                data-conversation-id="${escapeHtml(conversation.id)}"
              >
                <span class="conversation-mark" aria-hidden="true">◦</span>
                <span class="conversation-copy">
                  <strong>${escapeHtml(conversation.title)}</strong>
                  <small>${escapeHtml(formatConversationDate(conversation.updatedAt))}</small>
                </span>
              </button>
            `).join("")}
          </div>
        ` : ""}
      </div>
    `;
    }).join("") || "<p class=\"empty project-empty\">没有匹配项目。</p>";
  }

  function formatConversationDate(timestamp) {
    if (!timestamp) return "刚刚";
    return new Date(timestamp).toLocaleDateString("zh-CN", {
      month: "numeric",
      day: "numeric"
    });
  }

  function formatFileSize(bytes) {
    const size = Number(bytes) || 0;
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatFileDate(timestamp) {
    if (!timestamp) return "-";
    return new Date(timestamp).toLocaleString("zh-CN", { hour12: false });
  }

  function renderProjectFiles() {
    const project = getActiveProject();
    const files = project && Array.isArray(project.files) ? project.files : [];
    const list = $("#projectFilesList");

    $("#projectFilesCount").textContent = files.length;
    $("#projectFilesToggle").setAttribute("aria-expanded", String(!state.projectFilesCollapsed));
    $("#projectFilesChevron").textContent = state.projectFilesCollapsed ? "⌄" : "⌃";
    list.classList.toggle("hidden", state.projectFilesCollapsed);
    list.innerHTML = files.map(file => `
      <button class="project-file-item" type="button" data-project-file-id="${escapeHtml(file.id)}">
        <span class="project-file-icon" aria-hidden="true">PDF</span>
        <span class="project-file-copy">
          <strong>${escapeHtml(file.name)}</strong>
          <small>${escapeHtml(formatFileSize(file.size))}</small>
        </span>
      </button>
    `).join("") || `<p class="project-files-empty">当前项目暂无文件</p>`;
  }

  function openFileDetails(file) {
    if (!file) return;

    $("#fileDetailsTitle").textContent = file.name;
    $("#fileDetailsBody").innerHTML = `
      <dl class="file-details-list">
        <div><dt>文件名称</dt><dd>${escapeHtml(file.name)}</dd></div>
        <div><dt>文件类型</dt><dd>${escapeHtml(file.type || "PDF 文档")}</dd></div>
        <div><dt>文件大小</dt><dd>${escapeHtml(formatFileSize(file.size))}</dd></div>
        <div><dt>上传时间</dt><dd>${escapeHtml(formatFileDate(file.uploadedAt))}</dd></div>
        <div><dt>处理状态</dt><dd>${escapeHtml(file.status || "上传成功")}</dd></div>
        <div><dt>抽取编号</dt><dd>${escapeHtml(file.extractionId || "-")}</dd></div>
        <div><dt>文本字符数</dt><dd>${escapeHtml(formatValue(file.textLength))}</dd></div>
        <div><dt>提取方式</dt><dd>${escapeHtml(file.extractionMethod || "-")}</dd></div>
      </dl>
    `;
    $("#fileDetailsModal").classList.add("show");
    $("#closeFileDetailsButton").focus();
  }

  function closeFileDetails() {
    $("#fileDetailsModal").classList.remove("show");
  }

  function renderChatMessages() {
    const project = getActiveProject();
    const messages = state.chatMessages.filter(message => (
      message.projectId === state.activeProjectId
      && message.conversationId === state.activeConversationId
    ));
    const intro = project
      ? `已进入「${project.title}」。你可以上传文件、运行知识图谱抽取，或继续告诉我这个项目要做什么。`
      : "请选择或创建一个项目。";

    $("#chatMessages").innerHTML = `
      <div class="chat-message assistant-message">
        <div class="markdown-body">${renderMarkdown(intro)}</div>
      </div>
      ${messages.map(message => `
        <div class="chat-message ${getChatMessageClass(message)}">
          ${message.fileName ? renderChatFileName(message.fileName) : ""}
          <div class="markdown-body">${renderMarkdown(message.content)}</div>
          ${message.workflow ? renderWorkflowCard(message.workflow) : ""}
        </div>
      `).join("")}
    `;

    $("#chatMessages").scrollTop = $("#chatMessages").scrollHeight;
  }

  function renderChatFileName(fileName) {
    return `
      <div class="chat-uploaded-file">
        <span>已上传文件</span>
        <strong>${escapeHtml(fileName)}</strong>
      </div>
    `;
  }

  function renderWorkflowCard(workflow) {
    const steps = Array.isArray(workflow.steps) ? workflow.steps : [];
    const executionStatus = workflow.executionStatus || "pending";
    const isExecuting = executionStatus === "executing";
    const isCompleted = executionStatus === "completed";
    const buttonLabel = isExecuting ? "执行中..." : (isCompleted ? "已完成" : "审核通过并开始");
    return `
      <section class="workflow-card" aria-label="Workflow" data-workflow-status="${escapeHtml(executionStatus)}">
        <div class="workflow-card-header">
          <span>Workflow</span>
          <strong>${escapeHtml(workflow.title || "项目处理 workflow")}</strong>
          <p>${escapeHtml(workflow.summary || "已生成流程，等待确认。")}</p>
        </div>
        <ol class="workflow-step-list">
          ${steps.map((step, index) => `
            <li class="workflow-step">
              <span class="workflow-step-number">${index + 1}</span>
              <div>
                <strong>${escapeHtml(step.title || `步骤 ${index + 1}`)}</strong>
                <p>${escapeHtml(step.description || "")}</p>
                ${renderWorkflowMeta("输入", step.required_inputs)}
                ${renderWorkflowMeta("产出", step.expected_outputs)}
              </div>
            </li>
          `).join("")}
        </ol>
        <div class="workflow-confirm-row">
          <span>${escapeHtml(workflow.executionMessage || workflow.start_question || "是否开始这个流程？")}</span>
          <button
            type="button"
            class="secondary workflow-preview-button"
            data-workflow-id="${escapeHtml(workflow.id || "")}"
            ${isExecuting || isCompleted ? "disabled" : ""}
          >${buttonLabel}</button>
        </div>
      </section>
    `;
  }

  function getWorkflowMessage(workflowId) {
    return state.chatMessages.find(message => (
      message.projectId === state.activeProjectId
      && message.conversationId === state.activeConversationId
      && message.workflow
      && message.workflow.id === workflowId
    ));
  }

  async function startApprovedWorkflow(workflowId) {
    const message = getWorkflowMessage(workflowId);
    if (!message || !message.workflow || message.workflow.executionStatus === "executing") return;

    syncIntentInputs();
    message.workflow.executionStatus = "executing";
    message.workflow.executionMessage = "Workflow 已审核通过，执行 Agent 正在选择 skill 并执行...";
    setRunningState(true);
    setStatus(message.workflow.executionMessage);
    renderChatMessages();

    try {
      const result = await executeApprovedWorkflow({
        workflow: message.workflow,
        projectId: state.activeProjectId,
        extractionId: state.extractionId,
        documentSummary: state.documentSummary,
        userGoal: state.userGoal,
        entityTypes: state.entityTypes,
        relationTypes: state.relationTypes,
        relations: state.relations
      });

      state.extractionId = result.extraction_id || state.extractionId;
      let lastExecutedStageIndex = -1;
      (result.steps || []).forEach(executionStep => {
        const stageIndex = pipelineStages.findIndex(stage => {
          const stageMap = {
            upload: "pdf_to_text",
            ontology: "ontology_draft",
            strategy: "split_strategy",
            chunk: "chunking",
            extract: "graph_extraction",
            clean: "exact_cleaning",
            merge: "semantic_node_merge",
            relationClean: "relation_cleaning",
            quality: "quality_report",
            final: "final_graph"
          };
          return stageMap[stage.key] === executionStep.stage;
        });

        if (stageIndex >= 0) {
          state.stepResults[stageIndex] = executionStep.result;
          setStepProgress(stageIndex, "done");
          lastExecutedStageIndex = Math.max(lastExecutedStageIndex, stageIndex);
        }
        if (executionStep.stage === "ontology_draft") {
          setOntologyStateFromResult(executionStep.result || {});
        }
      });

      message.workflow.executionStatus = "completed";
      message.workflow.executionMessage = `执行完成，已调用 ${result.selected_skills.length} 个 skill。`;
      message.content = `${message.content}\n\nWorkflow 执行 Agent 已完成流程。`;
      state.approvedStepIndex = Math.max(state.approvedStepIndex, lastExecutedStageIndex);
      setProgress(100, "Workflow 执行完成。");
      setStatus(message.workflow.executionMessage);
      if (lastExecutedStageIndex >= 0 && result.final_result && Object.keys(result.final_result).length) {
        renderStepResult(pipelineStages[lastExecutedStageIndex], result.final_result);
      }
      state.currentStepIndex = Math.min(lastExecutedStageIndex + 1, pipelineStages.length);
    } catch (error) {
      message.workflow.executionStatus = "failed";
      message.workflow.executionMessage = "执行失败：" + error.message;
      setStatus(message.workflow.executionMessage);
    } finally {
      setRunningState(false);
      saveActiveProjectSnapshot();
      renderStepList();
      renderChatMessages();
      updateActionButtons();
    }
  }

  function renderWorkflowMeta(label, items) {
    if (!Array.isArray(items) || items.length === 0) return "";
    return `
      <div class="workflow-meta">
        <span>${escapeHtml(label)}</span>
        ${items.map(item => `<em>${escapeHtml(item)}</em>`).join("")}
      </div>
    `;
  }

  function getChatMessageClass(message) {
    const classes = [message.role === "user" ? "user-message" : "assistant-message"];

    if (message.pending) {
      classes.push("pending-message");
    }

    if (message.error) {
      classes.push("error-message");
    }

    return classes.join(" ");
  }

  function getCurrentChatHistory() {
    return state.chatMessages
      .filter(message => message.projectId === state.activeProjectId && !message.pending && !message.error)
      .filter(message => message.conversationId === state.activeConversationId)
      .slice(-AGENT_HISTORY_LIMIT)
      .map(message => ({
        role: message.role,
        content: message.content
      }));
  }

  function setStatus(message) {
    $("#statusBox").textContent = message;
  }

  function setRunningState(isRunning) {
    document.body.classList.toggle("is-running", Boolean(isRunning));
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

  function setStepProgress(stageIndex, phase) {
    const stage = pipelineStages[stageIndex];
    const base = (stageIndex / pipelineStages.length) * 100;
    const stepSize = 1 / pipelineStages.length * 100;
    const phaseRatio = phase === "done" ? 1 : 0.35;
    const message = phase === "done" ? stage.doneLabel : stage.label;

    setProgress(base + stepSize * phaseRatio, message);
  }

  function resetProgress(message) {
    setProgress(0, message || "等待开始处理。");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderMarkdown(value) {
    const source = String(value ?? "").replace(/\r\n/g, "\n").trim();
    if (!source) return "";

    const codeBlocks = [];
    const text = source.replace(/```([\w-]+)?\n?([\s\S]*?)```/g, (_, language, code) => {
      const token = `@@CODE_BLOCK_${codeBlocks.length}@@`;
      codeBlocks.push({
        language: language || "",
        code
      });
      return token;
    });

    const html = renderMarkdownBlocks(text);

    return codeBlocks.reduce((result, block, index) => {
      const languageClass = block.language ? ` language-${escapeHtml(block.language)}` : "";
      const codeHtml = `<pre><code class="${languageClass.trim()}">${escapeHtml(block.code.trim())}</code></pre>`;
      return result.replace(`@@CODE_BLOCK_${index}@@`, codeHtml);
    }, html);
  }

  function renderMarkdownBlocks(text) {
    const lines = text.split("\n");
    const blocks = [];
    let paragraph = [];
    let list = null;

    const flushParagraph = () => {
      if (paragraph.length === 0) return;
      blocks.push(`<p>${renderMarkdownInline(paragraph.join("\n")).replace(/\n/g, "<br>")}</p>`);
      paragraph = [];
    };

    const flushList = () => {
      if (!list) return;
      blocks.push(`<${list.type}>${list.items.map(item => `<li>${renderMarkdownInline(item)}</li>`).join("")}</${list.type}>`);
      list = null;
    };

    lines.forEach(line => {
      const trimmed = line.trim();

      if (!trimmed) {
        flushParagraph();
        flushList();
        return;
      }

      if (/^@@CODE_BLOCK_\d+@@$/.test(trimmed)) {
        flushParagraph();
        flushList();
        blocks.push(trimmed);
        return;
      }

      const headingMatch = /^(#{1,6})\s+(.+)$/.exec(trimmed);
      if (headingMatch) {
        flushParagraph();
        flushList();
        const level = Math.min(headingMatch[1].length + 2, 6);
        blocks.push(`<h${level}>${renderMarkdownInline(headingMatch[2])}</h${level}>`);
        return;
      }

      const unorderedMatch = /^[-*]\s+(.+)$/.exec(trimmed);
      if (unorderedMatch) {
        flushParagraph();
        if (!list || list.type !== "ul") {
          flushList();
          list = { type: "ul", items: [] };
        }
        list.items.push(unorderedMatch[1]);
        return;
      }

      const orderedMatch = /^\d+\.\s+(.+)$/.exec(trimmed);
      if (orderedMatch) {
        flushParagraph();
        if (!list || list.type !== "ol") {
          flushList();
          list = { type: "ol", items: [] };
        }
        list.items.push(orderedMatch[1]);
        return;
      }

      const quoteMatch = /^>\s+(.+)$/.exec(trimmed);
      if (quoteMatch) {
        flushParagraph();
        flushList();
        blocks.push(`<blockquote>${renderMarkdownInline(quoteMatch[1])}</blockquote>`);
        return;
      }

      flushList();
      paragraph.push(line);
    });

    flushParagraph();
    flushList();

    return blocks.join("");
  }

  function renderMarkdownInline(value) {
    const codeSpans = [];
    let html = String(value ?? "").replace(/`([^`]+)`/g, (_, code) => {
      const token = `@@CODE_SPAN_${codeSpans.length}@@`;
      codeSpans.push(`<code>${escapeHtml(code)}</code>`);
      return token;
    });

    html = escapeHtml(html)
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g, (_, label, url) => {
        return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      })
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/__([^_]+)__/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");

    return codeSpans.reduce((result, codeHtml, index) => {
      return result.replace(`@@CODE_SPAN_${index}@@`, codeHtml);
    }, html);
  }

  function formatValue(value) {
    if (value === undefined || value === null || value === "") return "-";
    if (typeof value === "number") return value.toLocaleString();
    if (typeof value === "boolean") return value ? "是" : "否";
    return String(value);
  }

  function getUniqueRelationTypes(relations) {
    return Array.from(
      new Set(
        (relations || [])
          .map(item => item.relation)
          .filter(Boolean)
      )
    );
  }

  function uniqueValues(values) {
    const seen = new Set();
    const results = [];

    values.forEach(value => {
      const normalized = String(value || "").trim();

      if (!normalized || seen.has(normalized)) return;

      seen.add(normalized);
      results.push(normalized);
    });

    return results;
  }

  function syncIntentInputs() {
    const documentSummaryInput = $("#documentSummaryInput");
    const userGoalInput = $("#userGoalInput");

    if (documentSummaryInput) {
      state.documentSummary = documentSummaryInput.value.trim();
    }

    if (userGoalInput) {
      state.userGoal = userGoalInput.value.trim();
    }
  }

  function renderStepList() {
    const box = $("#stepList");
    box.innerHTML = "";

    pipelineStages.forEach((stage, index) => {
      const item = document.createElement("div");
      const isDone = index <= state.approvedStepIndex;
      const isCurrent = index === state.currentStepIndex;
      item.className = [
        "step-item",
        isDone ? "done" : "",
        isCurrent ? "current" : "",
        index > state.currentStepIndex ? "waiting" : ""
      ].filter(Boolean).join(" ");
      item.innerHTML = `
        <span class="step-number">${isDone ? "✓" : index + 1}</span>
        <span>${escapeHtml(stage.title)}</span>
      `;
      box.appendChild(item);
    });
  }

  function updateActionButtons() {
    const stage = pipelineStages[state.currentStepIndex];
    const result = state.stepResults[state.currentStepIndex];
    const isFinished = state.currentStepIndex >= pipelineStages.length;

    $("#runStepButton").disabled = isFinished || Boolean(result);
    $("#approveStepButton").disabled = isFinished || !result;
    $("#runStepButton").textContent = stage ? `运行：${stage.title}` : "流程已完成";
    $("#currentStepTitle").textContent = stage ? stage.title : "流程已完成";
    $("#currentStepHint").textContent = stage
      ? stage.label
      : "全部步骤已完成，可以查看最终知识图谱。";
  }

  function setWorkspaceTitle(title) {
    const project = getActiveProject();
    $("#workspaceTitle").textContent = project ? project.title : title;
    if (project && title && title !== project.title) {
      $("#workspaceSubtitle").textContent = title;
    }
  }

  function showGraphToolbar(visible) {
    $("#graphToolbar").classList.toggle("hidden", !visible);
  }

  function getArtifactStats(result) {
    const report = result.report || result.split_report || {};
    const nodeCount = report.node_count ?? (Array.isArray(result.nodes) ? result.nodes.length : null);
    const edgeCount = report.edge_count ?? (Array.isArray(result.edges) ? result.edges.length : null);
    const stats = [];

    if (nodeCount !== null && nodeCount !== undefined) {
      stats.push({ label: "节点", value: nodeCount });
    }

    if (edgeCount !== null && edgeCount !== undefined) {
      stats.push({ label: "关系", value: edgeCount });
    }

    if (result.final_graph_json_path) {
      stats.push({ label: "类型", value: "知识图谱" });
    }

    return stats;
  }

  function getArtifactTitle(stage) {
    if (stage.key === "final") return "最终知识图谱";
    return `${stage.title}成果`;
  }

  function upsertArtifactFromResult(stage, result) {
    if (!stage || !result || stage.key !== "final") return;

    const artifactId = `${stage.key}_${result.extraction_id || state.extractionId || Date.now()}`;
    const artifact = {
      id: artifactId,
      type: "knowledge-graph",
      stageKey: stage.key,
      title: getArtifactTitle(stage),
      description: result.message || stage.doneLabel || "已生成成果",
      createdAt: Date.now(),
      extractionId: result.extraction_id || state.extractionId || "",
      result,
      stats: getArtifactStats(result)
    };
    const currentIndex = state.artifacts.findIndex(item => item.id === artifactId);

    if (currentIndex >= 0) {
      state.artifacts[currentIndex] = {
        ...state.artifacts[currentIndex],
        ...artifact,
        createdAt: state.artifacts[currentIndex].createdAt || artifact.createdAt
      };
    } else {
      state.artifacts.unshift(artifact);
    }

    state.activeArtifactId = artifactId;
  }

  function formatArtifactDate(timestamp) {
    if (!timestamp) return "刚刚";
    return new Date(timestamp).toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    });
  }

  function renderArtifactCards() {
    if (!state.artifacts.length) {
      return `
        <div class="artifact-empty">
          <h3>暂无成果</h3>
          <p>当流程生成最终知识图谱后，会在这里出现一张成果卡片。</p>
        </div>
      `;
    }

    return `
      <div class="artifact-card-list">
        ${state.artifacts.map(artifact => `
          <button
            type="button"
            class="artifact-card ${artifact.id === state.activeArtifactId ? "active" : ""}"
            data-artifact-id="${escapeHtml(artifact.id)}"
          >
            <span class="artifact-card-icon" aria-hidden="true">KG</span>
            <span class="artifact-card-copy">
              <strong>${escapeHtml(artifact.title)}</strong>
              <span>${escapeHtml(artifact.description)}</span>
              <small>${escapeHtml(formatArtifactDate(artifact.createdAt))}</small>
            </span>
            ${artifact.stats && artifact.stats.length ? `
              <span class="artifact-stat-strip">
                ${artifact.stats.slice(0, 2).map(stat => `
                  <em>${escapeHtml(stat.label)} ${escapeHtml(formatValue(stat.value))}</em>
                `).join("")}
              </span>
            ` : ""}
          </button>
        `).join("")}
      </div>
    `;
  }

  function showArtifactList() {
    clearGraph();
    document.body.classList.remove("artifact-detail-mode");
    showGraphToolbar(false);
    setWorkspaceTitle("成果列表");
    $("#configWorkbench").classList.remove("hidden");
    $("#configWorkbench").innerHTML = renderArtifactCards();
    $("#workbenchEmpty").classList.add("hidden");
    $("#graph").classList.add("hidden");
    $("#resultReview").classList.add("hidden");
    $("#resultReview").innerHTML = "";
  }

  function showArtifactDetail(artifactId) {
    const artifact = state.artifacts.find(item => item.id === artifactId);

    if (!artifact) {
      showArtifactList();
      return;
    }

    state.activeArtifactId = artifact.id;
    state.currentGraphData = artifact.result;
    document.body.classList.add("artifact-detail-mode");
    setWorkspaceTitle(artifact.title);
    showGraphToolbar(artifact.type === "knowledge-graph");
    $("#configWorkbench").classList.add("hidden");
    $("#workbenchEmpty").classList.add("hidden");
    $("#resultReview").classList.remove("hidden");
    $("#resultReview").innerHTML = `
      <div class="artifact-detail-header">
        <button type="button" class="secondary" data-artifact-back>返回成果列表</button>
        <div>
          <h2>${escapeHtml(artifact.title)}</h2>
          <p>${escapeHtml(artifact.description)}</p>
        </div>
      </div>
      ${renderMetricGrid((artifact.stats || []).map(stat => ({
        label: stat.label,
        value: stat.value
      })))}
    `;

    if (artifact.type === "knowledge-graph" && Array.isArray(artifact.result.nodes) && Array.isArray(artifact.result.edges)) {
      $("#graph").classList.remove("hidden");
      $("#graphLayoutSelect").value = state.graphLayoutMode;
      clearGraph();
      renderGraph(artifact.result, "graph", state.graphLayoutMode);
    } else {
      $("#graph").classList.add("hidden");
      clearGraph();
    }
  }

  function showEmptyWorkbench(title, description) {
    clearGraph();
    document.body.classList.remove("artifact-detail-mode");
    showGraphToolbar(false);
    setWorkspaceTitle("流程工作台");
    $("#configWorkbench").classList.add("hidden");
    $("#graph").classList.add("hidden");
    $("#resultReview").classList.add("hidden");
    $("#resultReview").innerHTML = "";
    $("#workbenchEmpty").classList.remove("hidden");
    $("#workbenchEmpty").innerHTML = `
      <div>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(description)}</p>
      </div>
    `;
  }

  function showConfigWorkbench() {
    showArtifactList();
  }

  function showReviewPanel(html) {
    clearGraph();
    document.body.classList.remove("artifact-detail-mode");
    showGraphToolbar(false);
    $("#configWorkbench").classList.add("hidden");
    $("#graph").classList.add("hidden");
    $("#workbenchEmpty").classList.add("hidden");
    $("#resultReview").classList.remove("hidden");
    $("#resultReview").innerHTML = html;
  }

  function showUploadSuccess() {
    clearGraph();
    document.body.classList.remove("artifact-detail-mode");
    showGraphToolbar(false);
    $("#configWorkbench").classList.add("hidden");
    $("#graph").classList.add("hidden");
    $("#resultReview").classList.add("hidden");
    $("#resultReview").innerHTML = "";
    $("#workbenchEmpty").classList.remove("hidden");
    $("#workbenchEmpty").innerHTML = "<div><h2>上传成功</h2></div>";
  }

  function showGraphResult(result) {
    showGraphToolbar(true);
    document.body.classList.remove("artifact-detail-mode");
    setWorkspaceTitle("知识图谱可视化输出");
    state.currentGraphData = result;
    document.body.classList.add("has-graph");
    $("#configWorkbench").classList.add("hidden");
    $("#workbenchEmpty").classList.add("hidden");
    $("#resultReview").classList.add("hidden");
    $("#graph").classList.remove("hidden");
    $("#graphLayoutSelect").value = state.graphLayoutMode;
    clearGraph();
    renderGraph(result, "graph", state.graphLayoutMode);
  }

  function renderMetricGrid(items) {
    const compactLabels = new Set(["文本块数量", "节点数量", "关系数量"]);
    const validItems = items.filter(item => item.value !== undefined && item.value !== null);
    const cards = validItems
      .filter(item => !compactLabels.has(item.label))
      .map(item => `
        <div class="metric-card">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(formatValue(item.value))}</strong>
        </div>
      `)
      .join("");
    const compactCards = validItems
      .filter(item => compactLabels.has(item.label))
      .map(item => `
        <span class="compact-metric-card">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(formatValue(item.value))}</strong>
        </span>
      `)
      .join("");

    return `
      ${cards ? `<div class="result-grid">${cards}</div>` : ""}
      ${compactCards ? `<div class="compact-metric-strip">${compactCards}</div>` : ""}
    `;
  }

  function renderKeyValueTable(data) {
    const rows = Object.entries(data || {})
      .filter(([, value]) => value !== undefined && value !== null && typeof value !== "object")
      .map(([key, value]) => `
        <tr>
          <th>${escapeHtml(key)}</th>
          <td>${escapeHtml(formatValue(value))}</td>
        </tr>
      `)
      .join("");

    return rows ? `<table class="result-table"><tbody>${rows}</tbody></table>` : "";
  }

  function renderResultHeader(stage, result) {
    return `
      <div class="result-header">
        <div>
          <h2>${escapeHtml(stage.title)}成果</h2>
          <p>${escapeHtml(result.message || stage.doneLabel)}</p>
        </div>
        <span class="result-badge">待审核</span>
      </div>
    `;
  }

  function renderStrategySummary(strategy) {
    if (!strategy || typeof strategy !== "object") {
      return "<p class=\"empty\">暂无切分策略。</p>";
    }

    const analysis = strategy.document_structure_analysis || {};
    const recommended = strategy.recommended_split_strategy || {};
    const rules = strategy.split_rules || {};
    const config = strategy && strategy.executable_split_config
      ? strategy.executable_split_config
      : {};
    const fallback = config.fallback || {};
    const finalDecision = strategy.final_decision || {};

    const renderTextList = values => {
      if (!Array.isArray(values) || values.length === 0) return "<p class=\"empty\">暂无。</p>";

      return `
        <ul class="strategy-list">
          ${values.map(value => `<li>${escapeHtml(value)}</li>`).join("")}
        </ul>
      `;
    };
    const renderPills = values => {
      if (!Array.isArray(values) || values.length === 0) {
        return "<span class=\"strategy-empty-pill\">未配置</span>";
      }

      return values
        .map(value => `<code class="strategy-pill">${escapeHtml(value)}</code>`)
        .join("");
    };
    const splitSteps = [
      {
        label: "识别结构",
        value: analysis.structure_type || "自动识别",
        detail: analysis.structure_description || "根据文档标题、编号和段落线索判断结构。"
      },
      {
        label: "一级切分",
        value: config.primary_unit_name || recommended.split_unit || "主切分单元",
        detail: rules.primary_split_rule || "按主要结构边界切分。"
      },
      {
        label: "二级切分",
        value: config.secondary_unit_name || "不启用",
        detail: rules.secondary_split_rule || "不需要二级切分时保持一级块完整。"
      },
      {
        label: "保留上下文",
        value: config.keep_parent_context ? "保留父级上下文" : "不额外保留父级上下文",
        detail: rules.context_retention_rule || "按配置决定是否把父标题带入切分结果。"
      },
      {
        label: "兜底策略",
        value: fallback.enabled ? "启用" : "关闭",
        detail: fallback.enabled
          ? `${fallback.method || "generic_heading_then_fixed_length"}，最大 ${formatValue(fallback.max_chars)} 字，重叠 ${formatValue(fallback.overlap)} 字`
          : "不使用兜底切分。"
      }
    ];
    const specialCases = Array.isArray(strategy.special_case_handling)
      ? strategy.special_case_handling
      : [];
    const notRecommended = Array.isArray(strategy.not_recommended_strategies)
      ? strategy.not_recommended_strategies
      : [];

    return `
      <div class="strategy-visual">
        <div class="strategy-hero">
          <div>
            <span class="strategy-kicker">${escapeHtml(config.split_mode || "split_strategy")}</span>
            <h3>${escapeHtml(recommended.strategy_name || "推荐切分策略")}</h3>
            <p>${escapeHtml(recommended.reason || "已根据文档结构生成可执行切分配置。")}</p>
          </div>
          <div class="strategy-decision">
            <span>二次切分</span>
            <strong>${finalDecision.need_second_pass_split ? "需要" : "不需要"}</strong>
          </div>
        </div>

        <div class="strategy-flow" aria-label="切分策略流程">
          ${splitSteps.map((step, index) => `
            <div class="strategy-step">
              <span class="strategy-step-number">${index + 1}</span>
              <div>
                <small>${escapeHtml(step.label)}</small>
                <strong>${escapeHtml(step.value)}</strong>
                <p>${escapeHtml(step.detail)}</p>
              </div>
            </div>
          `).join("")}
        </div>

        <div class="strategy-grid">
          <div class="strategy-card">
            <h4>结构信号</h4>
            ${renderTextList(analysis.main_organization_signals)}
          </div>
          <div class="strategy-card">
            <h4>切分单元应包含</h4>
            ${renderTextList(recommended.split_unit_should_contain)}
          </div>
          <div class="strategy-card">
            <h4>边界规则</h4>
            <dl class="strategy-definition">
              <div>
                <dt>开始边界</dt>
                <dd>${escapeHtml(rules.start_boundary_rule || "-")}</dd>
              </div>
              <div>
                <dt>结束边界</dt>
                <dd>${escapeHtml(rules.end_boundary_rule || config.end_boundary_rule || "-")}</dd>
              </div>
            </dl>
          </div>
          <div class="strategy-card">
            <h4>匹配模式</h4>
            <div class="strategy-pattern-group">
              <span>一级</span>
              <div>${renderPills(config.primary_start_patterns)}</div>
            </div>
            <div class="strategy-pattern-group">
              <span>二级</span>
              <div>${renderPills(config.secondary_start_patterns)}</div>
            </div>
            <div class="strategy-pattern-group">
              <span>父上下文</span>
              <div>${renderPills(config.parent_context_patterns)}</div>
            </div>
          </div>
        </div>

        ${specialCases.length ? `
          <div class="strategy-card strategy-wide-card">
            <h4>特殊情况处理</h4>
            <div class="strategy-case-list">
              ${specialCases.map(item => `
                <div class="strategy-case">
                  <strong>${escapeHtml(item.case || "特殊情况")}</strong>
                  <p>${escapeHtml(item.handling || "")}</p>
                </div>
              `).join("")}
            </div>
          </div>
        ` : ""}

        ${notRecommended.length ? `
          <div class="strategy-card strategy-wide-card">
            <h4>不推荐方案</h4>
            <div class="strategy-case-list">
              ${notRecommended.map(item => `
                <div class="strategy-case muted">
                  <strong>${escapeHtml(item.strategy || "不推荐策略")}</strong>
                  <p>${escapeHtml(item.reason || "")}</p>
                </div>
              `).join("")}
            </div>
          </div>
        ` : ""}

        <div class="strategy-final">
          <strong>面向知识图谱抽取的最终建议</strong>
          <p>${escapeHtml(finalDecision.recommended_for_kg_extraction || recommended.split_unit || "按推荐策略执行切分。")}</p>
        </div>
      </div>
    `;
  }

  function getCurrentOntologyDraft() {
    return {
      entity_types: state.entityTypes,
      relation_types: state.relationTypes,
      relations: state.relations,
      design_notes: state.ontologyDesignNotes
    };
  }

  function setOntologyStateFromResult(result) {
    const ontology = result.ontology || {};
    state.entityTypes = ontology.entity_types || result.entity_types || [];
    state.relationTypes = ontology.relation_types || result.relation_types || [];
    state.relations = ontology.relations || result.relations || [];
    state.ontologyDesignNotes = ontology.design_notes || [];
  }

  function renderDatalistOptions(values) {
    return values
      .map(value => `<option value="${escapeHtml(value)}"></option>`)
      .join("");
  }

  function renderSelectOptions(values, selectedValue) {
    const normalizedSelected = String(selectedValue || "").trim();
    const options = uniqueValues([
      normalizedSelected,
      ...(values || [])
    ]);

    return options
      .map(value => `
        <option value="${escapeHtml(value)}"${value === normalizedSelected ? " selected" : ""}>
          ${escapeHtml(value)}
        </option>
      `)
      .join("");
  }

  function renderOntologyDraft(result) {
    const draft = getCurrentOntologyDraft();
    const entityTypes = draft.entity_types;
    const relationTypes = draft.relation_types;
    const relations = draft.relations;
    const notes = draft.design_notes;

    return `
      <div id="ontologyEditor" class="ontology-editor">
        <datalist id="ontologyEntityTypeOptions">
          ${renderDatalistOptions(entityTypes)}
        </datalist>
        <datalist id="ontologyRelationTypeOptions">
          ${renderDatalistOptions(relationTypes)}
        </datalist>

        <div class="result-section">
          <div class="section-title compact-title">
            <h3>实体类型</h3>
            <button type="button" class="ghost mini-action" data-ontology-action="add-entity">添加实体</button>
          </div>
          <div class="ontology-chip-grid">
            ${entityTypes.map((type, index) => `
              <div class="ontology-chip-row">
                <input
                  data-ontology-entity-input
                  value="${escapeHtml(type)}"
                  placeholder="实体类型"
                />
                <button
                  type="button"
                  class="danger mini-delete"
                  data-ontology-action="remove-entity"
                  data-index="${index}"
                >删除</button>
              </div>
            `).join("") || "<p class=\"empty\">暂无实体类型。</p>"}
          </div>
        </div>

        <div class="result-section">
          <div class="section-title compact-title">
            <h3>关系类型</h3>
            <button type="button" class="ghost mini-action" data-ontology-action="add-relation-type">添加关系</button>
          </div>
          <div class="ontology-chip-grid">
            ${relationTypes.map((type, index) => `
              <div class="ontology-chip-row">
                <input
                  data-ontology-relation-type-input
                  value="${escapeHtml(type)}"
                  placeholder="关系类型"
                />
                <button
                  type="button"
                  class="danger mini-delete"
                  data-ontology-action="remove-relation-type"
                  data-index="${index}"
                >删除</button>
              </div>
            `).join("") || "<p class=\"empty\">暂无关系类型。</p>"}
          </div>
        </div>

        <div class="result-section">
          <div class="section-title compact-title">
            <h3>关系规则</h3>
            <button type="button" class="ghost mini-action" data-ontology-action="add-relation">添加规则</button>
          </div>
          <div class="ontology-relation-editor">
            ${relations.map((relation, index) => `
              <div class="ontology-relation-row" data-ontology-relation-row>
                <select
                  data-ontology-relation-from
                  aria-label="起点实体类型"
                >
                  ${renderSelectOptions(entityTypes, relation.from)}
                </select>
                <select
                  data-ontology-relation-name
                  aria-label="关系类型"
                >
                  ${renderSelectOptions(relationTypes, relation.relation)}
                </select>
                <select
                  data-ontology-relation-to
                  aria-label="终点实体类型"
                >
                  ${renderSelectOptions(entityTypes, relation.to)}
                </select>
                <button
                  type="button"
                  class="danger mini-delete"
                  data-ontology-action="remove-relation"
                  data-index="${index}"
                >删除</button>
              </div>
            `).join("") || "<p class=\"empty\">暂无关系规则。</p>"}
          </div>
        </div>

        ${notes.length ? `
          <div class="result-section">
            <h3>设计说明</h3>
            <textarea id="ontologyNotesInput" rows="4">${escapeHtml(notes.join("\n"))}</textarea>
          </div>
        ` : ""}
      </div>
    `;
  }

  function renderQualitySummary(quality) {
    if (!quality || typeof quality !== "object") return "";

    return `
      <div class="result-section">
        <h3>质量检查</h3>
        ${renderKeyValueTable(quality.summary || quality)}
      </div>
    `;
  }

  function renderExtractedTextReview(result) {
    const text = result.text || result.text_preview || "";
    const isEditing = Boolean(result.text_editing);

    return `
      <div class="result-section extracted-text-section">
        <div class="section-title compact-title">
          <h3>提取文本</h3>
          <button
            type="button"
            class="ghost mini-action"
            data-text-action="${isEditing ? "preview" : "edit"}"
          >${isEditing ? "退出编辑" : "编辑文本"}</button>
        </div>
        ${isEditing ? `
          <textarea
            id="extractedTextEditor"
            class="extracted-text-editor"
            spellcheck="false"
          >${escapeHtml(text)}</textarea>
        ` : `
          <pre class="result-preview extracted-text-preview">${escapeHtml(text)}</pre>
        `}
      </div>
    `;
  }

  function getGraphNodes(result) {
    return Array.isArray(result.nodes) ? result.nodes : [];
  }

  function getGraphEdges(result) {
    return Array.isArray(result.edges) ? result.edges : [];
  }

  function renderInstanceNodeOptions(nodes) {
    return nodes
      .map(node => {
        const label = node.name || node.label || node.id;
        return `<option value="${escapeHtml(node.id)}">${escapeHtml(label)}</option>`;
      })
      .join("");
  }

  function renderGraphInstantiationEditor(result) {
    const nodes = getGraphNodes(result);
    const edges = getGraphEdges(result);
    const nodeOptions = renderInstanceNodeOptions(nodes);

    return `
      <div class="instance-review-layout">
        <div class="instance-editor-panel">
          <div class="result-section">
            <div class="section-title compact-title">
              <h3>实例节点</h3>
              <button type="button" class="ghost mini-action" data-instance-action="add-node">添加节点</button>
            </div>
            <div class="instance-table">
              <div class="instance-row instance-row-head">
                <span>名称</span>
                <span>类型</span>
                <span>说明</span>
                <span></span>
              </div>
              ${nodes.map((node, index) => `
                <div class="instance-row" data-instance-node-row data-node-id="${escapeHtml(node.id)}">
                  <input data-instance-node-name value="${escapeHtml(node.name || node.label || "")}" placeholder="节点名称" />
                  <input data-instance-node-type value="${escapeHtml(node.type || "未分类")}" placeholder="节点类型" />
                  <input data-instance-node-description value="${escapeHtml(node.description || "")}" placeholder="说明" />
                  <button
                    type="button"
                    class="danger mini-delete"
                    data-instance-action="remove-node"
                    data-index="${index}"
                  >删除</button>
                </div>
              `).join("") || "<p class=\"empty\">暂无实例节点。</p>"}
            </div>
          </div>
        </div>

        <div class="instance-editor-panel">
          <div class="result-section">
            <div class="section-title compact-title">
              <h3>实例关系</h3>
              <button type="button" class="ghost mini-action" data-instance-action="add-edge">添加关系</button>
            </div>
            <div class="instance-edge-editor">
              ${edges.map((edge, index) => `
                <div class="instance-edge-row" data-instance-edge-row data-edge-id="${escapeHtml(edge.id || "")}">
                  <select data-instance-edge-source>
                    ${nodeOptions}
                  </select>
                  <input data-instance-edge-relation value="${escapeHtml(edge.relation || edge.label || "")}" placeholder="关系" />
                  <select data-instance-edge-target>
                    ${nodeOptions}
                  </select>
                  <input data-instance-edge-description value="${escapeHtml(edge.description || "")}" placeholder="说明" />
                  <button
                    type="button"
                    class="danger mini-delete"
                    data-instance-action="remove-edge"
                    data-index="${index}"
                  >删除</button>
                </div>
              `).join("") || "<p class=\"empty\">暂无实例关系。</p>"}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function syncInstanceSelectValues(result) {
    getGraphEdges(result).forEach((edge, index) => {
      const row = document.querySelectorAll("[data-instance-edge-row]")[index];
      if (!row) return;

      const sourceSelect = row.querySelector("[data-instance-edge-source]");
      const targetSelect = row.querySelector("[data-instance-edge-target]");

      if (sourceSelect) sourceSelect.value = edge.source || edge.from || "";
      if (targetSelect) targetSelect.value = edge.target || edge.to || "";
    });
  }

  function renderStepResult(stage, result) {
    if (stage.key === "upload") {
      showUploadSuccess();
      return;
    }

    const report = result.report || result.split_report || {};
    const metrics = [
      { label: "文本字符数", value: result.text_length },
      { label: "OCR 页数", value: result.ocr_page_count },
      { label: "OCR 错误", value: result.ocr_error_count },
      { label: "实体类型", value: result.entity_types && result.entity_types.length },
      { label: "关系类型", value: result.relation_types && result.relation_types.length },
      { label: "关系规则", value: result.relations && result.relations.length },
      { label: "文本块数量", value: report.chunk_count },
      { label: "节点数量", value: report.node_count },
      { label: "关系数量", value: report.edge_count },
      { label: "合并节点", value: result.stats && result.stats.merged_node_count },
      { label: "移除关系", value: result.stats && result.stats.removed_edge_count }
    ];

    if (stage.key === "final") {
      upsertArtifactFromResult(stage, result);
      showArtifactList();
      return;
    }

    if (stage.key !== "extract" && Array.isArray(result.nodes) && Array.isArray(result.edges)) {
      showGraphResult(result);
      return;
    }

    const preview = result.text_preview
      ? `
        <div class="result-section">
          <h3>文本预览</h3>
          <pre class="result-preview">${escapeHtml(result.text_preview)}</pre>
        </div>
      `
      : "";
    const strategy = result.strategy
      ? `
        <div class="result-section">
          <h3>切分策略</h3>
          ${renderStrategySummary(result.strategy)}
        </div>
      `
      : "";
    const ontology = result.ontology ? renderOntologyDraft(result) : "";
    const graphInstantiation = stage.key === "extract"
      ? renderGraphInstantiationEditor(result)
      : "";
    const paths = renderKeyValueTable({
      extraction_id: result.extraction_id,
      txt_path: result.txt_path || result.source_txt_path,
      ontology_path: result.ontology_path,
      strategy_path: result.strategy_path,
      chunks_json_path: result.chunks_json_path,
      raw_graph_json_path: result.raw_graph_json_path,
      cleaned_graph_json_path: result.cleaned_graph_json_path,
      merged_graph_json_path: result.merged_graph_json_path,
      relation_cleaned_graph_json_path: result.relation_cleaned_graph_json_path,
      quality_report_path: result.quality_report_path,
      final_graph_json_path: result.final_graph_json_path
    });

    showReviewPanel(`
      ${renderResultHeader(stage, result)}
      ${renderMetricGrid(metrics)}
      ${ontology}
      ${graphInstantiation}
      ${renderQualitySummary(result.quality_report)}
      ${renderQualitySummary(result.quality)}
      ${strategy}
      ${preview}
      <div class="result-section">
        <h3>输出信息</h3>
        ${paths || "<p class=\"empty\">暂无输出路径。</p>"}
      </div>
    `);

    if (stage.key === "extract") {
      syncInstanceSelectValues(result);
    }
  }

  function readOntologyDraftFromEditor() {
    const entityTypes = uniqueValues(
      Array.from(document.querySelectorAll("[data-ontology-entity-input]"))
        .map(input => input.value)
    );
    const relationTypes = uniqueValues(
      Array.from(document.querySelectorAll("[data-ontology-relation-type-input]"))
        .map(input => input.value)
    );
    const relationTypeSet = new Set(relationTypes);
    const entityTypeSet = new Set(entityTypes);
    const relations = [];
    const seenRelations = new Set();

    document.querySelectorAll("[data-ontology-relation-row]").forEach(row => {
      const from = row.querySelector("[data-ontology-relation-from]").value.trim();
      const relation = row.querySelector("[data-ontology-relation-name]").value.trim();
      const to = row.querySelector("[data-ontology-relation-to]").value.trim();
      const key = `${from}__${relation}__${to}`;

      if (!entityTypeSet.has(from) || !relationTypeSet.has(relation) || !entityTypeSet.has(to)) {
        return;
      }

      if (seenRelations.has(key)) return;

      seenRelations.add(key);
      relations.push({ from, relation, to });
    });

    const notesInput = $("#ontologyNotesInput");
    const designNotes = notesInput
      ? uniqueValues(notesInput.value.split("\n"))
      : state.ontologyDesignNotes;

    return {
      entity_types: entityTypes,
      relation_types: relationTypes,
      relations,
      design_notes: designNotes
    };
  }

  function readGraphInstantiationFromEditor() {
    const nodes = [];
    const seenNodeIds = new Set();

    document.querySelectorAll("[data-instance-node-row]").forEach((row, index) => {
      const existingId = row.dataset.nodeId || "";
      const id = existingId || `rn_user_${index + 1}`;
      const name = row.querySelector("[data-instance-node-name]").value.trim();
      const type = row.querySelector("[data-instance-node-type]").value.trim() || "未分类";
      const description = row.querySelector("[data-instance-node-description]").value.trim();

      if (!name || seenNodeIds.has(id)) return;

      seenNodeIds.add(id);
      nodes.push({
        id,
        name,
        canonical_name: name,
        label: name,
        type,
        description
      });
    });

    const nodeIdSet = new Set(nodes.map(node => node.id));
    const edges = [];
    const seenEdges = new Set();

    document.querySelectorAll("[data-instance-edge-row]").forEach((row, index) => {
      const source = row.querySelector("[data-instance-edge-source]").value;
      const target = row.querySelector("[data-instance-edge-target]").value;
      const relation = row.querySelector("[data-instance-edge-relation]").value.trim();
      const description = row.querySelector("[data-instance-edge-description]").value.trim();
      const key = `${source}__${relation}__${target}`;

      if (!source || !target || !relation || source === target) return;
      if (!nodeIdSet.has(source) || !nodeIdSet.has(target) || seenEdges.has(key)) return;

      seenEdges.add(key);
      edges.push({
        id: row.dataset.edgeId || `re_user_${index + 1}`,
        source,
        target,
        relation,
        label: relation,
        description
      });
    });

    return { nodes, edges };
  }

  function validateGraphInstantiation(graph) {
    if (graph.nodes.length === 0) {
      alert("请至少保留一个实例节点");
      return false;
    }

    return true;
  }

  function applyGraphInstantiation(graph) {
    const stageResult = state.stepResults[state.currentStepIndex];

    if (!stageResult) return;

    stageResult.nodes = graph.nodes;
    stageResult.edges = graph.edges;
    stageResult.report = {
      ...(stageResult.report || {}),
      node_count: graph.nodes.length,
      edge_count: graph.edges.length
    };
  }

  function rerenderGraphInstantiationEditor() {
    const result = state.stepResults[state.currentStepIndex];
    const stage = pipelineStages[state.currentStepIndex];

    if (!result || !stage || stage.key !== "extract") return;

    renderStepResult(stage, result);
  }

  function validateOntologyDraft(ontology) {
    if (ontology.entity_types.length === 0) {
      alert("请至少保留一个实体类型");
      return false;
    }

    if (ontology.relation_types.length === 0) {
      alert("请至少保留一个关系类型");
      return false;
    }

    if (ontology.relations.length === 0) {
      alert("请至少保留一条关系规则");
      return false;
    }

    return true;
  }

  function applyOntologyDraft(ontology) {
    state.entityTypes = ontology.entity_types;
    state.relationTypes = ontology.relation_types;
    state.relations = ontology.relations;
    state.ontologyDesignNotes = ontology.design_notes;

    const stageResult = state.stepResults[state.currentStepIndex];
    if (stageResult && stageResult.ontology) {
      stageResult.ontology = ontology;
      stageResult.entity_types = ontology.entity_types;
      stageResult.relation_types = ontology.relation_types;
      stageResult.relations = ontology.relations;
    }
  }

  function rerenderOntologyEditor() {
    const result = state.stepResults[state.currentStepIndex];
    const stage = pipelineStages[state.currentStepIndex];

    if (!result || !stage || stage.key !== "ontology") return;

    renderStepResult(stage, result);
  }

  function readExtractedTextFromEditor() {
    const editor = $("#extractedTextEditor");
    return editor ? editor.value.trim() : "";
  }

  function setExtractedTextEditing(isEditing) {
    const stageResult = state.stepResults[state.currentStepIndex];
    const stage = pipelineStages[state.currentStepIndex];

    if (!stageResult || !stage || stage.key !== "upload") return;

    if (isEditing) {
      stageResult.text_editing = true;
    } else {
      const editedText = readExtractedTextFromEditor();
      if (editedText) {
        stageResult.text = editedText;
        stageResult.text_preview = editedText.slice(0, 3000);
      }
      stageResult.text_editing = false;
    }

    renderStepResult(stage, stageResult);
  }

  function applyExtractedTextUpdate(result) {
    const stageResult = state.stepResults[state.currentStepIndex];

    if (!stageResult) return;

    state.stepResults[state.currentStepIndex] = {
      ...stageResult,
      ...result,
    };
  }

  function resetFlow(keepFile) {
    state.extractionId = "";
    state.currentStepIndex = 0;
    state.approvedStepIndex = -1;
    state.stepResults = [];
    state.entityTypes = [];
    state.relationTypes = [];
    state.relations = [];
    state.ontologyDesignNotes = [];
    state.currentGraphData = null;
    document.body.classList.remove("has-graph");
    setRunningState(false);
    syncIntentInputs();

    if (!keepFile) {
      state.selectedPdfFile = null;
      $("#pdfInput").value = "";
      $("#fileNameText").textContent = "尚未选择文件";
      if ($("#configFileNameText")) {
        $("#configFileNameText").textContent = "尚未选择文件";
      }
    }

    clearGraph();
    showConfigWorkbench();
    resetProgress("等待开始处理。");
    setStatus(keepFile && state.selectedPdfFile ? "已选择 PDF：" + state.selectedPdfFile.name : "等待上传 PDF。");
    saveActiveProjectSnapshot();
    renderStepList();
    renderProjectList();
    updateActionButtons();
  }

  function openPdfSelector() {
    $("#pdfInput").click();
  }

  async function handlePdfSelect(event) {
    const file = event.target.files[0];

    if (!file) return;

    if (file.type !== "application/pdf") {
      alert("请选择 PDF 文件");
      return;
    }

    resetFlow(false);
    state.selectedPdfFile = file;
    $("#pdfInput").value = "";
    $("#fileNameText").textContent = file.name;
    if ($("#configFileNameText")) {
      $("#configFileNameText").textContent = file.name;
    }
    const project = getActiveProject();
    if (project) {
      project.fileName = file.name;
      project.selectedPdfFile = file;
      project.description = "已上传 " + file.name;
      project.updatedAt = Date.now();
    }
    state.chatMessages.push({
      projectId: state.activeProjectId,
      conversationId: state.activeConversationId,
      role: "user",
      content: "已上传文件",
      fileName: file.name
    });
    setStatus("正在提取并清洗文件：" + file.name);
    renderProjectList();
    renderChatMessages();
    saveActiveProjectSnapshot();
    setRunningState(true);
    setStepProgress(0, "active");
    renderStepList();
    updateActionButtons();

    try {
      const result = await uploadPdfToText({
        file,
        entityTypes: state.entityTypes,
        relations: state.relations
      });

      state.extractionId = result.extraction_id || "";
      state.stepResults[0] = result;
      if (project) {
        project.extractionId = state.extractionId;
        project.stepResults = [...state.stepResults];
        project.files = Array.isArray(project.files) ? project.files : [];
        project.files.push({
          id: state.extractionId || `file_${Date.now()}`,
          name: file.name,
          type: file.type || "application/pdf",
          size: file.size,
          uploadedAt: Date.now(),
          status: "上传成功",
          extractionId: state.extractionId,
          textLength: result.text_length,
          extractionMethod: result.extraction_method
        });
        project.updatedAt = Date.now();
      }
      setStepProgress(0, "done");
      setStatus("上传成功");
      setWorkspaceTitle("上传成功");
      updateActiveConversationTitle(`上传 ${file.name}`);
      renderStepResult(pipelineStages[0], result);
      renderProjectFiles();
      renderProjectList();
    } catch (error) {
      state.extractionId = "";
      state.stepResults[0] = null;
      setStatus("文件提取失败：" + error.message);
      $("#progressStepText").textContent = "文件提取失败：" + error.message;
    } finally {
      setRunningState(false);
      saveActiveProjectSnapshot();
      renderStepList();
      renderProjectList();
      renderChatMessages();
      updateActionButtons();
    }
  }

  function handleIntentChange() {
    syncIntentInputs();
    saveActiveProjectSnapshot();
    resetFlow(true);
  }

  function validateBeforeRun() {
    syncIntentInputs();

    if (!state.selectedPdfFile) {
      alert("请先选择 PDF 文件");
      return false;
    }

    return true;
  }

  async function runCurrentStep() {
    if (!validateBeforeRun()) return;

    const stageIndex = state.currentStepIndex;
    const stage = pipelineStages[stageIndex];
    const runButton = $("#runStepButton");
    const approveButton = $("#approveStepButton");

    runButton.disabled = true;
    approveButton.disabled = true;
    setRunningState(true);
    setStepProgress(stageIndex, "active");
    setStatus(stage.label);

    try {
      const result = await runPipelineStep({
        stageKey: stage.key,
        file: state.selectedPdfFile,
        extractionId: state.extractionId,
        documentSummary: state.documentSummary,
        userGoal: state.userGoal,
        entityTypes: state.entityTypes,
        relations: state.relations,
        relationTypes: state.relationTypes.length ? state.relationTypes : getUniqueRelationTypes(state.relations)
      });

      state.extractionId = result.extraction_id || state.extractionId;

      if (stage.key === "ontology") {
        setOntologyStateFromResult(result);
      }

      state.stepResults[stageIndex] = result;
      saveActiveProjectSnapshot();
      setStepProgress(stageIndex, "done");
      setStatus(`${stage.doneLabel}，请在右侧审核成果。`);
      setWorkspaceTitle(`${stage.title}审核`);
      renderStepResult(stage, result);
      saveActiveProjectSnapshot();
    } catch (error) {
      $("#progressStepText").textContent = "处理失败：" + error.message;
      setStatus("处理失败：" + error.message);
    } finally {
      setRunningState(false);
      renderStepList();
      updateActionButtons();
    }
  }

  async function approveCurrentStep() {
    const stageIndex = state.currentStepIndex;
    const stage = pipelineStages[stageIndex];

    if (!state.stepResults[stageIndex]) {
      alert("请先运行并查看当前步骤成果");
      return;
    }

    if (stage.key === "upload" && state.stepResults[stageIndex].text_editing) {
      const text = readExtractedTextFromEditor();

      if (!text) {
        alert("提取文本不能为空");
        return;
      }

      try {
        $("#approveStepButton").disabled = true;
        setStatus("正在保存编辑后的提取文本...");
        const updateResult = await updateExtractedText({
          extractionId: state.extractionId,
          text
        });
        applyExtractedTextUpdate(updateResult);
      } catch (error) {
        setStatus("提取文本保存失败：" + error.message);
        $("#approveStepButton").disabled = false;
        return;
      }
    }

    if (stage.key === "ontology") {
      const ontology = readOntologyDraftFromEditor();

      if (!validateOntologyDraft(ontology)) return;

      try {
        $("#approveStepButton").disabled = true;
        setStatus("正在保存编辑后的本体草案...");
        const updateResult = await updateOntologyDraft({
          extractionId: state.extractionId,
          ontology
        });
        applyOntologyDraft(updateResult.ontology || ontology);
        state.stepResults[stageIndex] = {
          ...state.stepResults[stageIndex],
          ...updateResult,
        };
      } catch (error) {
        setStatus("本体草案保存失败：" + error.message);
        $("#approveStepButton").disabled = false;
        return;
      }
    }

    if (stage.key === "extract") {
      const graph = readGraphInstantiationFromEditor();

      if (!validateGraphInstantiation(graph)) return;

      try {
        $("#approveStepButton").disabled = true;
        setStatus("正在保存编辑后的本体实例化结果...");
        const updateResult = await updateGraphInstantiation({
          extractionId: state.extractionId,
          nodes: graph.nodes,
          edges: graph.edges
        });
        applyGraphInstantiation({
          nodes: updateResult.nodes || graph.nodes,
          edges: updateResult.edges || graph.edges
        });
        state.stepResults[stageIndex] = {
          ...state.stepResults[stageIndex],
          ...updateResult,
        };
      } catch (error) {
        setStatus("本体实例化结果保存失败：" + error.message);
        $("#approveStepButton").disabled = false;
        return;
      }
    }

    state.approvedStepIndex = Math.max(state.approvedStepIndex, stageIndex);
    state.currentStepIndex += 1;

    if (state.currentStepIndex >= pipelineStages.length) {
      setProgress(100, "全部步骤已完成。");
      setStatus("全部步骤已审核通过，知识图谱流程完成。");
    } else {
      setStatus(`${stage.title}已审核通过，可以继续下一步。`);
    }

    renderStepList();
    saveActiveProjectSnapshot();
    renderProjectList();
    updateActionButtons();
  }

  function bindEvents() {
    $("#newProjectButton").addEventListener("click", () => {
      saveActiveProjectSnapshot();
      const project = createProject();
      state.projects.unshift(project);
      loadProject(project);
    });
    $("#searchProjectButton").addEventListener("click", () => {
      $("#projectSearchPanel").classList.toggle("hidden");
      if (!$("#projectSearchPanel").classList.contains("hidden")) {
        $("#projectSearchInput").focus();
      }
    });
    $("#projectSearchInput").addEventListener("input", event => {
      state.projectSearchQuery = event.target.value;
      renderProjectList();
    });
    $("#projectFilesToggle").addEventListener("click", () => {
      state.projectFilesCollapsed = !state.projectFilesCollapsed;
      renderProjectFiles();
    });
    $("#projectFilesList").addEventListener("click", event => {
      const button = event.target.closest("[data-project-file-id]");
      if (!button) return;

      const project = getActiveProject();
      const files = project && Array.isArray(project.files) ? project.files : [];
      openFileDetails(files.find(file => file.id === button.dataset.projectFileId));
    });
    $("#closeFileDetailsButton").addEventListener("click", closeFileDetails);
    $("#confirmFileDetailsButton").addEventListener("click", closeFileDetails);
    $("#fileDetailsModal").addEventListener("click", event => {
      if (event.target === $("#fileDetailsModal")) closeFileDetails();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && $("#fileDetailsModal").classList.contains("show")) {
        closeFileDetails();
      }
    });
    $("#projectList").addEventListener("click", event => {
      const conversationButton = event.target.closest("[data-conversation-id]");
      if (conversationButton) {
        const project = state.projects.find(item => item.id === conversationButton.dataset.conversationProjectId);
        if (!project) return;

        const conversation = ensureProjectConversations(project)
          .find(item => item.id === conversationButton.dataset.conversationId);
        if (!conversation) return;

        saveActiveProjectSnapshot();
        project.activeConversationId = conversation.id;
        if (!state.expandedProjectIds.includes(project.id)) {
          state.expandedProjectIds.push(project.id);
        }
        loadProject(project);
        return;
      }

      const newChatButton = event.target.closest("[data-new-chat-project-id]");
      if (newChatButton) {
        const project = state.projects.find(item => item.id === newChatButton.dataset.newChatProjectId);
        if (!project) return;

        saveActiveProjectSnapshot();
        const conversation = createConversation(project.id);
        ensureProjectConversations(project).unshift(conversation);
        project.activeConversationId = conversation.id;
        if (!state.expandedProjectIds.includes(project.id)) {
          state.expandedProjectIds.push(project.id);
        }
        loadProject(project);
        return;
      }

      const button = event.target.closest("[data-project-id]");
      if (!button) return;

      const project = state.projects.find(item => item.id === button.dataset.projectId);
      if (!project) return;

      saveActiveProjectSnapshot();
      if (state.expandedProjectIds.includes(project.id)) {
        state.expandedProjectIds = state.expandedProjectIds.filter(id => id !== project.id);
      } else {
        state.expandedProjectIds.push(project.id);
      }
      loadProject(project);
    });
    $("#agentChatForm").addEventListener("submit", async event => {
      event.preventDefault();
      const input = $("#agentChatInput");
      const sendButton = $(".send-button");
      const content = input.value.trim();

      if (!content || !state.activeProjectId || state.isAgentChatting) return;

      const history = getCurrentChatHistory();
      state.chatMessages.push({
        projectId: state.activeProjectId,
        conversationId: state.activeConversationId,
        role: "user",
        content
      });
      updateActiveConversationTitle(content);
      renderProjectList();
      input.value = "";
      state.isAgentChatting = true;
      input.disabled = true;
      sendButton.disabled = true;

      const pendingMessage = {
        projectId: state.activeProjectId,
        conversationId: state.activeConversationId,
        role: "assistant",
        content: "正在回复...",
        pending: true
      };
      state.chatMessages.push(pendingMessage);
      renderChatMessages();

      try {
        syncIntentInputs();
        const result = await chatWithMasterAgent({
          message: content,
          projectId: state.activeProjectId,
          extractionId: state.extractionId,
          documentSummary: state.documentSummary,
          userGoal: state.userGoal,
          selectedFeature: state.activeFeature,
          history
        });

        pendingMessage.content = result.message || "我收到了。";
        pendingMessage.workflow = result.workflow || null;
        if (result.document_summary) {
          state.documentSummary = result.document_summary;
          if ($("#documentSummaryInput")) $("#documentSummaryInput").value = state.documentSummary;
        }
        if (result.user_goal) {
          state.userGoal = result.user_goal;
          if ($("#userGoalInput")) $("#userGoalInput").value = state.userGoal;
        }
        pendingMessage.pending = false;
      } catch (error) {
        pendingMessage.content = "主控 Agent 暂时没有回复成功：" + error.message;
        pendingMessage.pending = false;
        pendingMessage.error = true;
      } finally {
        state.isAgentChatting = false;
        input.disabled = false;
        sendButton.disabled = false;
        saveActiveProjectSnapshot();
        renderChatMessages();
        input.focus();
      }
    });
    $("#chatMessages").addEventListener("click", event => {
      const workflowButton = event.target.closest("[data-workflow-id]");
      if (!workflowButton || workflowButton.disabled) return;
      startApprovedWorkflow(workflowButton.dataset.workflowId);
    });
    document.querySelectorAll("[data-feature]").forEach(button => {
      button.addEventListener("click", async () => {
        if (!state.activeProjectId) return;
        const featureName = button.querySelector("strong")
          ? button.querySelector("strong").textContent.trim()
          : "该功能";

        document.querySelectorAll("[data-feature]").forEach(item => {
          item.classList.toggle("active", item === button);
        });
        state.activeFeature = button.dataset.feature || "knowledge-graph";
        updateActiveConversationTitle(featureName);
        renderProjectList();

        const pendingMessage = {
          projectId: state.activeProjectId,
          conversationId: state.activeConversationId,
          role: "assistant",
          content: `已选择${featureName}，正在梳理需求和预期结果...`,
          pending: true
        };
        state.chatMessages.push(pendingMessage);
        renderChatMessages();

        try {
          syncIntentInputs();
          const result = await chatWithMasterAgent({
            message: `用户在前端选择了功能：${featureName}`,
            projectId: state.activeProjectId,
            extractionId: state.extractionId,
            documentSummary: state.documentSummary,
            userGoal: state.userGoal,
            selectedFeature: state.activeFeature,
            history: getCurrentChatHistory()
          });

          pendingMessage.content = result.message || `已选择${featureName}。`;
          pendingMessage.workflow = result.workflow || null;
          if (result.document_summary) {
            state.documentSummary = result.document_summary;
            if ($("#documentSummaryInput")) $("#documentSummaryInput").value = state.documentSummary;
          }
          if (result.user_goal) {
            state.userGoal = result.user_goal;
            if ($("#userGoalInput")) $("#userGoalInput").value = state.userGoal;
          }
          pendingMessage.pending = false;
        } catch (error) {
          pendingMessage.content = "需求梳理暂时没有完成：" + error.message;
          pendingMessage.pending = false;
          pendingMessage.error = true;
        } finally {
          saveActiveProjectSnapshot();
          renderChatMessages();
        }
      });
    });
    $("#pdfInput").addEventListener("change", handlePdfSelect);
    $("#pdfSelectButton").addEventListener("click", openPdfSelector);
    $("#runStepButton").addEventListener("click", runCurrentStep);
    $("#approveStepButton").addEventListener("click", approveCurrentStep);
    $("#resetFlowButton").addEventListener("click", () => resetFlow(true));
    $("#configWorkbench").addEventListener("click", event => {
      const artifactButton = event.target.closest("[data-artifact-id]");
      if (!artifactButton) return;

      showArtifactDetail(artifactButton.dataset.artifactId);
      saveActiveProjectSnapshot();
    });
    $("#graphLayoutSelect").addEventListener("change", event => {
      state.graphLayoutMode = event.target.value;

      if (!state.currentGraphData || $("#graph").classList.contains("hidden")) return;

      renderGraph(state.currentGraphData, "graph", state.graphLayoutMode);
    });
    $("#fitGraphButton").addEventListener("click", fitGraph);
    $("#clearGraphButton").addEventListener("click", () => {
      clearGraph();
      state.currentGraphData = null;
      showEmptyWorkbench(
        "图谱已清空",
        "可以重新运行最终图谱生成步骤，或重新开始流程。"
      );
      resetProgress("等待开始处理。");
      setStatus("图谱已清空。");
    });
    $("#resultReview").addEventListener("click", event => {
      const backButton = event.target.closest("[data-artifact-back]");
      if (backButton) {
        showArtifactList();
        saveActiveProjectSnapshot();
        return;
      }

      const textButton = event.target.closest("[data-text-action]");
      if (textButton) {
        const stage = pipelineStages[state.currentStepIndex];
        if (!stage || stage.key !== "upload") return;

        setExtractedTextEditing(textButton.dataset.textAction === "edit");
        return;
      }

      const instanceButton = event.target.closest("[data-instance-action]");
      if (instanceButton) {
        const stage = pipelineStages[state.currentStepIndex];
        if (!stage || stage.key !== "extract") return;

        const action = instanceButton.dataset.instanceAction;
        const index = Number(instanceButton.dataset.index);
        const graph = readGraphInstantiationFromEditor();
        applyGraphInstantiation(graph);

        const stageResult = state.stepResults[state.currentStepIndex];
        const nodes = stageResult.nodes;
        const edges = stageResult.edges;

        if (action === "add-node") {
          const nextNumber = nodes.length + 1;
          nodes.push({
            id: `rn_user_${Date.now()}`,
            name: `新节点 ${nextNumber}`,
            canonical_name: `新节点 ${nextNumber}`,
            label: `新节点 ${nextNumber}`,
            type: state.entityTypes[0] || "未分类",
            description: ""
          });
        } else if (action === "remove-node") {
          const removedNode = nodes[index];
          if (!removedNode) return;

          nodes.splice(index, 1);
          stageResult.edges = edges.filter(edge => {
            return edge.source !== removedNode.id && edge.target !== removedNode.id;
          });
        } else if (action === "add-edge") {
          if (nodes.length < 2) {
            alert("请至少保留两个节点后再添加关系");
            return;
          }

          stageResult.edges.push({
            id: `re_user_${Date.now()}`,
            source: nodes[0].id,
            target: nodes[1].id,
            relation: state.relationTypes[0] || "相关",
            label: state.relationTypes[0] || "相关",
            description: ""
          });
        } else if (action === "remove-edge") {
          stageResult.edges.splice(index, 1);
        }

        rerenderGraphInstantiationEditor();
        return;
      }

      const button = event.target.closest("[data-ontology-action]");
      if (!button) return;

      const stage = pipelineStages[state.currentStepIndex];
      if (!stage || stage.key !== "ontology") return;

      const action = button.dataset.ontologyAction;
      const index = Number(button.dataset.index);
      const currentDraft = readOntologyDraftFromEditor();
      applyOntologyDraft(currentDraft);

      if (action === "add-entity") {
        state.entityTypes.push("");
      } else if (action === "remove-entity") {
        const removedType = state.entityTypes[index];
        state.entityTypes.splice(index, 1);
        state.relations = state.relations.filter(relation => {
          return relation.from !== removedType && relation.to !== removedType;
        });
      } else if (action === "add-relation-type") {
        state.relationTypes.push("");
      } else if (action === "remove-relation-type") {
        const removedRelationType = state.relationTypes[index];
        state.relationTypes.splice(index, 1);
        state.relations = state.relations.filter(relation => relation.relation !== removedRelationType);
      } else if (action === "add-relation") {
        if (state.entityTypes.length === 0 || state.relationTypes.length === 0) {
          alert("请先添加实体类型和关系类型");
          return;
        }

        state.relations.push({
          from: state.entityTypes[0],
          relation: state.relationTypes[0],
          to: state.entityTypes[0]
        });
      } else if (action === "remove-relation") {
        state.relations.splice(index, 1);
      }

      rerenderOntologyEditor();
    });
  }

  function initApp() {
    state.projects = DEFAULT_PROJECTS.map(project => ({
      ...createProject(project.title),
      ...project
    }));
    state.activeProjectId = state.projects[0].id;
    state.expandedProjectIds = [];
    bindEvents();
    loadProject(state.projects[0]);
  }

  window.KGUI = {
    initApp
  };
})();
