// @module 36-api-and-start: window.infragramEditor and start-up
  const editorApi = Object.freeze({
    setDisplayMode: mode => applyProjectDisplayMode(mode, {persist: false}),
    // the library payload as the page inflated it (the script element carries it deflated)
    getLibraryCatalog: () => libraryCatalog,
    // resolves once no zoom-to-fit is pending: a fit settles two frames after
    // it starts, and a layout change (the sidebar's grid transition, a
    // resize) can start another; anything that measures the canvas after
    // such a change waits on this rather than on a guessed delay
    whenSettled: () => new Promise(resolve => whenFitSettles(resolve)),
    getState: () => clone(state),
    getStorageKey: () => storageKey,
    // the comments file this page would download (35-comments)
    getComments: () => commentsFile(),
    // a 3D item by spec, rendered in this page and added as a node; the spec is scene.js's own
    build3d: (spec, caption) => renderIsoSpec(spec).then(render => addIsoNode(spec, render, caption)),
    exportProject,
    exportSvg,
    exportPng,
    exportDrawio,
    exportHtml,
    addNode: (component, point) => addNode(component, point),
    addBoundary: (component, point) => addBoundary(component, point),
    connect: (source, target, sourcePort = 'auto', targetPort = 'auto') => connectNodes(source, target, sourcePort, targetPort),
    // a resource's attached parts (a VM's NICs, disks, public IPs) shown
    // beside it on the canvas, or folded away: the count shown, negative when folded
    toggleAttached: id => toggleAttachedParts(id),
    setEdgeLabel,
    setEdgeStyle,
    setEdgeTextStyle,
    setEdgeWaypoints,
    setRouting: enabled => {
      checkpoint();
      visitOnly.routing = null;
      state.canvas.routeAroundNodes = Boolean(enabled);
      persist();
      renderGraph();
      return state.canvas.routeAroundNodes;
    },
    setEdgeLabelPlacement,
    expandCanvas: (width = CANVAS_GROWTH, height = CANVAS_GROWTH) => {
      checkpoint();
      state.canvas.width += Math.max(CANVAS_GROWTH, Number(width) || 0);
      state.canvas.height += Math.max(CANVAS_GROWTH, Number(height) || 0);
      syncCanvasGeometry();
      persist();
      renderGraph();
      return clone(state.canvas);
    },
  });
  viewport.addEventListener('scroll', updateSelectionToolbar, {passive: true});
  syncViewportGutter();
  renderGraph();
  // The editor is published only once its first fit has settled -- zoom and
  // scroll, including the refit the viewport observer asks for as it starts
  // -- so whatever waits for it can measure and click at once.
  // Ready once every icon's ink is known, so a picture exported on a dark
  // theme is drawn with the same filters every time.
  const inkKnown = Promise.race([
    Promise.all([...new Set(state.nodes.map(node => node.iconUri).filter(Boolean))].map(measureInk)),
    new Promise(resolve => setTimeout(resolve, 10000)),
  ]);
  requestAnimationFrame(() => {
    fitZoom();
    whenFitSettles(() => inkKnown.then(() => {
      if (darkCanvas()) renderGraph();
      statusShown = true;
      window.infragramEditor = editorApi;
    }));
  });
  persist();
  let observedViewportWidth = 0;
  let observedViewportHeight = 0;
  new ResizeObserver(() => {
    const width = viewport.clientWidth;
    const height = viewport.clientHeight;
    const layoutChanged = width !== observedViewportWidth || height !== observedViewportHeight;
    observedViewportWidth = width;
    observedViewportHeight = height;
    syncViewportGutter();
    ensureCanvasExtent({save: true});
    if (fitMode && layoutChanged) requestAnimationFrame(() => fitZoom());
  }).observe(viewport);
  // The observer refits at every intermediate width of the sidebar's grid
  // transition; the last word belongs to the final width, so refit once more
  // when the transition ends. Cheap, and it makes the end state the same on
  // a slow machine as on a fast one.
  document.querySelector('.workspace')?.addEventListener('transitionend', event => {
    if (event.propertyName === 'grid-template-columns' && fitMode) requestAnimationFrame(() => fitZoom());
  });
})().catch(error => {
  // The chrome is drawn before the runtime starts, so a throw on the way up
  // would leave a page that looks whole with every control dead and one
  // rejection in the console. Say so on the page, and publish a stub that
  // tells an exporter "the runtime crashed" apart from "no runtime yet".
  const message = String(error && error.message ? error.message : error);
  const banner = document.createElement('div');
  banner.setAttribute('data-editor-failure', '');
  banner.setAttribute('role', 'alert');
  banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:1000;padding:10px 16px;'
    + 'background:#FFF4E5;color:#7A2E0E;border-bottom:1px solid #F0B37E;'
    + 'font:13px/1.4 system-ui,sans-serif;white-space:pre-wrap';
  banner.textContent = `The editor failed to start: ${message}`;
  document.body.prepend(banner);
  window.infragramEditor = {failed: message};
  console.error('infragram editor failed to start', error);
});
