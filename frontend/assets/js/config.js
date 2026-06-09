(function () {
  window.KGConfig = {
    API_BASE_URL: "http://127.0.0.1:8000",

    DEFAULT_ENTITY_TYPES: [
      "系统",
      "设备",
      "部件",
      "故障现象",
      "故障原因",
      "解决方法"
    ],

    DEFAULT_RELATIONS: [
      { from: "系统", relation: "包含", to: "设备" },
      { from: "设备", relation: "包含", to: "部件" },
      { from: "部件", relation: "出现", to: "故障现象" },
      { from: "故障原因", relation: "导致", to: "故障现象" },
      { from: "故障现象", relation: "采取", to: "解决方法" }
    ],

    COLOR_MAP: {
      "系统": "#2563eb",
      "子系统": "#0891b2",
      "设备": "#16a34a",
      "部件": "#f59e0b",
      "故障现象": "#dc2626",
      "故障原因": "#7c3aed",
      "解决方法": "#059669"
    }
  };
})();
