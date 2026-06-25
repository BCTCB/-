(function () {
  const { COLOR_MAP } = window.KGConfig;
  const state = window.KGState;
  const DEFAULT_NODE_COLOR = "#334155";
  const EDGE_COLOR = "#7dd3fc";

  function destroyGraph() {
    if (state.network) {
      state.network.destroy();
      state.network = null;
    }

    if (state.graphResizeObserver) {
      state.graphResizeObserver.disconnect();
      state.graphResizeObserver = null;
    }
  }

  function getContainerSize(container) {
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 560;
    return { width, height };
  }

  function createTooltipContent(model) {
    const tooltip = document.createElement("div");
    tooltip.className = "graph-tooltip";

    const title = document.createElement("strong");
    title.textContent = model.label || model.id || "未命名";
    tooltip.appendChild(title);

    const type = document.createElement("span");
    type.textContent = model.type
      ? `类型：${model.type}`
      : `关系：${model.edgeLabel || model.label || "未命名"}`;
    tooltip.appendChild(type);

    return tooltip;
  }

  function toGraphData(data) {
    const nodes = (data.nodes || []).map(node => ({
      id: String(node.id),
      label: node.label || node.name || node.canonical_name || node.id,
      type: node.type || "未分类",
      style: {
        fill: COLOR_MAP[node.type] || DEFAULT_NODE_COLOR,
        stroke: "#111827",
        lineWidth: 1.2,
        radius: 6,
        shadowColor: "rgba(0, 0, 0, 0.34)",
        shadowBlur: 14,
        shadowOffsetY: 6
      },
      labelCfg: {
        style: {
          fill: "#ffffff",
          fontSize: 14,
          fontWeight: 600,
          maxWidth: 116,
          overflow: "ellipsis"
        }
      }
    }));

    const edges = (data.edges || []).map((edge, index) => ({
      id: edge.id ? String(edge.id) : `edge-${index}`,
      source: String(edge.from || edge.source),
      target: String(edge.to || edge.target),
      label: edge.label || edge.relation || "",
      edgeLabel: edge.label || edge.relation || "",
      labelCfg: {
        autoRotate: true,
        style: {
          fill: "#cbd5e1",
          fontSize: 12,
          maxWidth: 96,
          overflow: "ellipsis",
          background: {
            fill: "#111820",
            stroke: "#263241",
            padding: [3, 5, 3, 5],
            radius: 3
          }
        }
      }
    }));

    return { nodes, edges };
  }

  function getLayoutConfig(layoutMode) {
    if (layoutMode === "tree") {
      return {
        type: "dagre",
        rankdir: "LR",
        align: "UL",
        nodesep: 80,
        ranksep: 180,
        controlPoints: true
      };
    }

    return {
      type: "force",
      preventOverlap: true,
      linkDistance: 260,
      nodeStrength: -420,
      edgeStrength: 0.22,
      collideStrength: 1,
      nodeSize: 190
    };
  }

  function renderGraph(data, containerId = "graph", layoutMode = "force") {
    const container = document.getElementById(containerId);

    if (!container) return;

    destroyGraph();
    container.innerHTML = "";

    if (!window.G6) {
      container.textContent = "AntV G6 加载失败，请检查网络后刷新页面。";
      return;
    }

    const { width, height } = getContainerSize(container);
    const tooltip = new G6.Tooltip({
      offsetX: 12,
      offsetY: 16,
      itemTypes: ["node", "edge"],
      getContent: event => createTooltipContent(event.item.getModel())
    });

    state.network = new G6.Graph({
      container,
      width,
      height,
      layout: getLayoutConfig(layoutMode),
      modes: {
        default: ["drag-canvas", "zoom-canvas", "drag-node", "activate-relations"]
      },
      plugins: [tooltip],
      defaultNode: {
        type: "rect",
        size: [136, 44],
        labelCfg: {
          position: "center"
        }
      },
      defaultEdge: {
        type: layoutMode === "tree" ? "polyline" : "quadratic",
        style: {
          stroke: EDGE_COLOR,
          lineWidth: 1.8,
          opacity: 0.76,
          endArrow: {
            path: G6.Arrow.triangle(8, 10, 0),
            fill: EDGE_COLOR
          }
        }
      },
      nodeStateStyles: {
        hover: {
          lineWidth: 2,
          stroke: "#67e8c9"
        },
        active: {
          lineWidth: 2,
          stroke: "#67e8c9"
        }
      },
      edgeStateStyles: {
        active: {
          stroke: "#67e8c9",
          lineWidth: 2.4
        }
      }
    });

    state.network.on("afterlayout", function () {
      fitGraph();
    });

    state.network.data(toGraphData(data));
    state.network.render();

    state.graphResizeObserver = new ResizeObserver(function () {
      if (!state.network || container.classList.contains("hidden")) return;
      const nextSize = getContainerSize(container);
      state.network.changeSize(nextSize.width, nextSize.height);
      fitGraph();
    });
    state.graphResizeObserver.observe(container);
  }

  function fitGraph() {
    if (state.network) {
      state.network.fitView(32);
      state.network.fitCenter();
    }
  }

  function clearGraph() {
    destroyGraph();
    const container = document.getElementById("graph");
    if (container) {
      container.innerHTML = "";
    }
  }

  window.KGGraph = {
    clearGraph,
    fitGraph,
    renderGraph
  };
})();
