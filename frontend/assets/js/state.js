(function () {
  const { DEFAULT_ENTITY_TYPES, DEFAULT_RELATIONS } = window.KGConfig;

  window.KGState = {
    selectedPdfFile: null,
    network: null,
    extractionMode: "auto",
    entityTypes: [...DEFAULT_ENTITY_TYPES],
    relations: DEFAULT_RELATIONS.map(relation => ({ ...relation }))
  };
})();
