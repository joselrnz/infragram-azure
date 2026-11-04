// @module 09-persistence: local storage, undo checkpoints and saved-state migration
  // ?display=, ?routing= and ?grid= draw this visit differently without
  // touching what the author saved. Each override remembers what it
  // replaced, and persist() writes that back, so the next plain open of the
  // document comes up the way it was left. Routing and grid are one setting
  // each and stay overridden until the author picks one in the workspace.
  // The display reflows every frame, so its override holds the document as
  // it was, and holds it only while the drawing is still the one the visit
  // drew: once the author edits it (an undo step taken), the drawing they are
  // working on is what is kept, and undoing back to the start restores the
  // override.
  const visitOnly = {display: null, routing: null, grid: null};
  const persistedState = () => {
    const display = visitOnly.display && undoStack.length <= visitOnly.display.edits ? visitOnly.display : null;
    if (!display && !visitOnly.routing && !visitOnly.grid) return state;
    const saved = clone(state);
    if (visitOnly.routing) saved.canvas.routeAroundNodes = visitOnly.routing.saved;
    if (visitOnly.grid) saved.canvas.showGrid = visitOnly.grid.saved;
    if (display) {
      saved.canvas.displayMode = display.saved.displayMode;
      saved.nodes = clone(display.saved.nodes);
      saved.boundaries = clone(display.saved.boundaries);
    }
    return saved;
  };
  const persist = () => {
    const payload = JSON.stringify(persistedState());
    stateElement.textContent = payload;
    const notice = document.querySelector('[data-save-notice]');
    try {
      localStorage.setItem(storageKey, payload);
      if (notice) notice.hidden = true;
    } catch (_) {
      if (notice) notice.hidden = false;
    }
  };
  // A checkpoint clears the redo stack, as any new edit must; a pointer
  // press checkpoints before it knows whether anything will move, so the
  // redo entries are kept aside until the press turns out to be a click.
  let redoAtCheckpoint = [];
  const checkpoint = () => {
    undoStack.push(JSON.stringify(state));
    if (undoStack.length > 100) undoStack.shift();
    redoAtCheckpoint = redoStack.splice(0);
  };
  const discardCheckpoint = () => {
    const before = undoStack.pop();
    redoStack.push(...redoAtCheckpoint);
    redoAtCheckpoint = [];
    return before;
  };
  const restore = value => {
    // Undo steps the drawing back, not the reader: whatever was selected stays
    // selected as long as the step back left it there, so the handles of the
    // wire or card being worked on do not vanish between steps.
    const held = {
      selected,
      nodes: [...selectedNodeIds],
      boundaries: [...selectedBoundaryIds],
      preferences: Object.fromEntries(['pngScale', 'showLegend', 'exportLegend', 'titlePlacement']
        .map(key => [key, state.canvas[key]])),
    };
    state = JSON.parse(value);
    Object.assign(state.canvas, held.preferences);
    selected = null;
    clearNodeSelection();
    clearBoundarySelection();
    drag = null;
    clearConnection();
    alignmentGuides = [];
    held.nodes.filter(nodeById).forEach(id => selectedNodeIds.add(id));
    held.boundaries.filter(boundaryById).forEach(id => selectedBoundaryIds.add(id));
    const stillThere = {
      node: id => Boolean(nodeById(id)),
      boundary: id => Boolean(boundaryById(id)),
      edge: id => Boolean(edgeById(id)),
    };
    if (held.selected && stillThere[held.selected.type]?.(held.selected.id)) selected = held.selected;
    persist();
    renderGraph();
  };

  const migrateSavedState = saved => {
    if (!saved || ![2, 3].includes(saved.schemaVersion)) return null;
    if (saved.schemaVersion === 2 && saved.provider !== generatedState.provider) return null;
    if (saved.schemaVersion === 3 && saved.projectSlug !== generatedState.projectSlug) return null;
    const migrated = clone(saved);
    migrated.schemaVersion = 3;
    migrated.projectSlug = generatedState.projectSlug;
    migrated.provider = migrated.provider || generatedState.provider;
    migrated.providers = migrated.providers || clone(generatedState.providers);
    migrated.layers = migrated.layers?.length ? migrated.layers : clone(generatedState.layers);
    const layerIdFor = provider => (
      migrated.layers.find(layer => layer.provider === provider)?.id
      || migrated.layers[0]?.id
      || null
    );
    migrated.nodes = (migrated.nodes || []).map(node => {
      const generated = generatedNodes.get(node.id);
      const componentProvider = node.componentProvider || generated?.componentProvider || migrated.provider;
      const componentId = node.componentId || generated?.componentId || node.type || 'service';
      return {
        ...node,
        componentId,
        componentProvider,
        componentQualifiedId: node.componentQualifiedId
          || generated?.componentQualifiedId
          || `${componentProvider}:${componentId}`,
        layerId: node.layerId || generated?.layerId || layerIdFor(componentProvider),
      };
    });
    migrated.boundaries = (migrated.boundaries || []).map(boundary => {
      const generated = generatedBoundaries.get(boundary.id);
      const componentProvider = boundary.componentProvider
        || generated?.componentProvider
        || migrated.provider;
      return {
        ...boundary,
        componentProvider,
        componentQualifiedId: boundary.componentQualifiedId
          || generated?.componentQualifiedId
          || null,
        layerId: boundary.layerId || generated?.layerId || layerIdFor(componentProvider),
      };
    });
    migrated.edges = (migrated.edges || []).map(edge => (
      edge.label === 'Kubernetes API'
      && edge.sourcePort === 'top'
      && edge.targetPort === 'top'
        ? {...edge, sourcePort: 'bottom', targetPort: 'top'}
        : edge
    ));
    return refreshSavedArtwork(migrated);
  };

  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    const migrated = migrateSavedState(saved);
    if (migrated) {
      state = migrated;
      localStorage.setItem(storageKey, JSON.stringify(state));
    }
  } catch (_) { /* malformed or unavailable local storage */ }

  let defs = diagram.querySelector(':scope > defs');
  if (!defs) {
    defs = document.createElementNS(SVG_NS, 'defs');
    diagram.insertBefore(defs, diagram.children[2] || null);
  }
  // A page saved from the editor already carries the grid pattern and the
  // markers, so each is added once.
  if (!defs.querySelector('#infragram-editor-grid')) {
    defs.insertAdjacentHTML('beforeend', `
    <pattern id="infragram-editor-grid" width="48" height="48" patternUnits="userSpaceOnUse" data-grid-steps="4" data-visible-step="12">
      <path data-grid-minor fill="none" stroke="var(--diagram-grid-minor)" stroke-width="1" vector-effect="non-scaling-stroke" shape-rendering="crispEdges"/>
      <path data-grid-major fill="none" stroke="var(--diagram-grid-major)" stroke-width="1" vector-effect="non-scaling-stroke" shape-rendering="crispEdges"/>
    </pattern>`);
  }
  // One marker per head shape, plain and selected, all from the spec.
  if (!defs.querySelector(`#${INK_ON_DARK}`)) defs.insertAdjacentHTML('beforeend', INK_ON_DARK_FILTER);
  if (!defs.querySelector('#infragram-editor-arrow')) {
    defs.insertAdjacentHTML('beforeend', Object.entries(EDGE_ARROWS).flatMap(([name, suffix]) => ['', '-selected'].map(
      state => markerMarkup(`infragram-editor-arrow${suffix}${state}`, name, 'context-stroke'),
    )).join(''));
  }
  if (state.canvas.routeAroundNodes === undefined) state.canvas.routeAroundNodes = true;
  if (!['card', 'icon'].includes(state.canvas.displayMode)) state.canvas.displayMode = 'card';
  const savedPngScale = Number(state.canvas.pngScale);
  state.canvas.pngScale = Number.isInteger(savedPngScale) && savedPngScale >= 1 && savedPngScale <= 4
    ? savedPngScale : 2;
  if (['simple', 'direct', 'off', '0'].includes(
    String(workspaceParams.get('routing') || '').toLowerCase(),
  )) {
    visitOnly.routing = {saved: state.canvas.routeAroundNodes};
    state.canvas.routeAroundNodes = false;
  }
  state.canvas.gridSteps = Number(state.canvas.gridSteps) || 4;
  state.canvas.minGridPixels = Number(state.canvas.minGridPixels) || 10;
  state.canvas.visualGrid = Number(state.canvas.visualGrid) || (Number(state.canvas.grid) || 4) * 3;
  if (!Object.hasOwn(FRAME_LINES, state.canvas.frameLines)) state.canvas.frameLines = 'thin';
  // the grid shows only where it was switched on; unsaid, it is off
  state.canvas.showGrid = state.canvas.showGrid === true;
  // ?grid=0 (or off/false/hidden) opens with the grid hidden, ?grid=1 shown.
  if (workspaceParams.has('grid')) {
    visitOnly.grid = {saved: state.canvas.showGrid};
    state.canvas.showGrid = !['0', 'off', 'false', 'hidden', 'no'].includes(
      String(workspaceParams.get('grid') || '').toLowerCase(),
    );
  }
