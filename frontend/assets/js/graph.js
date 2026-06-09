(function () {
  const { COLOR_MAP } = window.KGConfig;
  const state = window.KGState;

  function renderGraph(data) {
    const container = document.getElementById("graph");

    if (state.network) {
      state.network.destroy();
      state.network = null;
    }

    container.innerHTML = "";

    const nodes = new vis.DataSet(
      data.nodes.map(node => ({
        id: node.id,
        label: node.label + "\n[" + node.type + "]",
        title: `类型：${node.type}<br>名称：${node.label}`,
        color: {
          background: COLOR_MAP[node.type] || "#6b7280",
          border: "#111827"
        },
        font: {
          color: "#ffffff",
          size: 15
        },
        shape: "box",
        margin: 12
      }))
    );

    const edges = new vis.DataSet(
      data.edges.map(edge => ({
        from: edge.from,
        to: edge.to,
        label: edge.label,
        arrows: "to",
        font: {
          align: "middle",
          size: 13
        },
        color: {
          color: "#6b7280",
          highlight: "#2563eb"
        },
        smooth: {
          type: "dynamic"
        }
      }))
    );

    const options = {
      autoResize: true,

      layout: {
        improvedLayout: true
      },

      physics: {
        enabled: true,
        stabilization: {
          enabled: true,
          iterations: 200
        },
        barnesHut: {
          gravitationalConstant: -3000,
          centralGravity: 0.3,
          springLength: 160,
          springConstant: 0.04,
          damping: 0.2
        }
      },

      interaction: {
        hover: true,
        tooltipDelay: 120,
        navigationButtons: false,
        keyboard: false
      },

      nodes: {
        borderWidth: 1,
        shadow: true
      },

      edges: {
        width: 2
      }
    };

    state.network = new vis.Network(container, { nodes, edges }, options);

    state.network.once("stabilizationIterationsDone", function () {
      fitGraph();
    });
  }

  function fitGraph() {
    if (state.network) {
      state.network.fit({
        animation: {
          duration: 500,
          easingFunction: "easeInOutQuad"
        }
      });
    }
  }

  function clearGraph() {
    if (state.network) {
      state.network.destroy();
      state.network = null;
    }

    document.getElementById("graph").innerHTML = "";
  }

  window.KGGraph = {
    clearGraph,
    fitGraph,
    renderGraph
  };
})();
