// @module 16-render: renderGraph, which draws the whole graph from state
  // Views that follow the drawing -- the frame review -- add themselves here.
  const afterRender = [];
  // A drag moves the cards being dragged and the wires they carry, and leaves
  // the rest of the drawing where it is. Drawing all of it again costs most of
  // a second on the largest template, and nothing else on it has changed.
  // Returns false when the page is not in a state it can patch, and the
  // caller draws everything instead.
  const dragMovedNodes = ids => {
    const moved = ids.map(nodeById).filter(Boolean);
    if (!moved.length || moved.length !== ids.length) return false;
    const groups = moved.map(node => [node,
      diagram.querySelector(`[data-graph-node][data-node-id="${CSS.escape(node.id)}"]`)]);
    if (groups.some(([, group]) => !group)) return false;
    groups.forEach(([node, group]) => group.setAttribute('transform', nodeTransform(node)));
    const carried = new Set(ids);
    // Every wire is asked for its route -- the ones that did not move answer
    // from the cache -- because a label is placed against all of them, and a
    // label that stayed behind would read as the wrong wire's.
    const all = edgeGeometry();
    all.forEach(item => connectorPath(item));
    const items = all.filter(item => carried.has(item.edge.source) || carried.has(item.edge.target));
    for (const item of items) {
      const path = connectorPath(item);
      const id = CSS.escape(item.edge.id);
      const drawn = diagram.querySelector(`[data-graph-edge][data-edge-id="${id}"]`);
      const hit = diagram.querySelector(`[data-edge-hit="${id}"]`);
      if (!drawn || !hit) return false;
      const halo = diagram.querySelector(`[data-edge-group="${id}"] [data-edge-selection-halo]`);
      [drawn, hit, halo].forEach(element => element && element.setAttribute('d', path));
      const source = item.sourceSeat || item.sourcePoint;
      const target = item.targetSeat || item.targetPoint;
      drawn.dataset.sourceX = source.x;
      drawn.dataset.sourceY = source.y;
      drawn.dataset.targetX = target.x;
      drawn.dataset.targetY = target.y;
      diagram.querySelectorAll(`[data-edge-terminal][data-edge-id="${id}"]`).forEach((circle, index) => {
        const point = index === 0 ? source : target;
        circle.setAttribute('cx', point.x);
        circle.setAttribute('cy', point.y);
      });
    }
    for (const item of all) {
      const label = diagram.querySelector(`[data-edge-label="${CSS.escape(item.edge.id)}"]`);
      if (!label) continue;
      const placed = resolvedEdgeLabel(item);
      label.setAttribute('transform', `translate(${placed.x} ${placed.y})`);
      label.dataset.labelX = placed.x;
      label.dataset.labelY = placed.y;
      label.dataset.placementMode = placed.mode;
    }
    // The guides, the selection's outline and the frame a card is over are
    // small enough to draw afresh; an outline left behind would sit over the
    // place the cards were picked up from.
    applyCrossings(all);
    placeBrandMark();
    const guides = diagram.querySelector('[data-alignment-guide-layer]');
    if (guides) guides.innerHTML = alignmentGuides.map(alignmentGuideMarkup).join('');
    const overlay = diagram.querySelector('[data-selection-overlay-layer]');
    if (overlay) overlay.innerHTML = selectionOverlayMarkup();
    diagram.querySelectorAll('[data-graph-boundary]').forEach(element => {
      element.dataset.dropTarget = String(element.dataset.boundaryId === dropTargetId);
    });
    return true;
  };

  const renderGraph = () => {
    const welcome = document.querySelector('[data-canvas-welcome]');
    if (welcome) welcome.hidden = Boolean(state.nodes.length || state.boundaries.length || state.edges.length);
    currentFlow = flowLit();
    ensureCanvasExtent();
    placeStepList();
    paintStepRows(currentFlow);
    ensureObjectOrders();
    const colors = canvasPalette();
    const edges = edgeGeometry();
    refreshRouteContext();
    // Routing may move a wire's ends to other sides of its cards; settle
    // every route first so terminals, markup and captions agree on them.
    edges.forEach(item => connectorPath(item));
    const terminals = edges.flatMap(item => [
      [item.edge.id, item.sourceSeat || item.sourcePoint],
      [item.edge.id, item.targetSeat || item.targetPoint],
    ])
      .map(([id, point]) => `<circle data-edge-terminal data-edge-id="${escapeText(id)}" cx="${point.x}" cy="${point.y}" r="3" fill="${colors.handle}" stroke="${colors.accent}" stroke-width="1.5" pointer-events="none"/>`)
      .join('');
    // The routes as they are drawn -- the settled wires routed again from the
    // sides they moved to -- then the wires on one line drawn apart.
    edges.forEach(item => connectorPath(item));
    spreadLanes(edges);
    // A selected connector shows a handle at each end: drag one onto another card to reconnect.
    const chosenEdge = selected?.type === 'edge' && !connection && selectedEdgeIds.size <= 1
      ? edges.find(item => item.edge.id === selected.id) : null;
    const endHandles = chosenEdge && !itemIsLocked(chosenEdge.edge)
      ? [['source', chosenEdge.sourceSeat || chosenEdge.sourcePoint], ['target', chosenEdge.targetSeat || chosenEdge.targetPoint]]
        .map(([end, point]) => `<circle data-edge-end="${end}" data-edge-id="${escapeText(chosenEdge.edge.id)}" cx="${point.x}" cy="${point.y}" r="${touchReach(Math.max(6, 7 / zoom), 12)}" fill="${colors.handle}" stroke="${colors.accent}" stroke-width="2" vector-effect="non-scaling-stroke" pointer-events="all"><title>Drag to reconnect the ${end === 'source' ? 'start' : 'end'}</title></circle>`)
        .join('')
      : '';
    // Bends: a handle on each one, and a hollow one in the middle of every
    // stretch between them -- drag either, or the wire itself, to shape it.
    const bendHandles = chosenEdge && !itemIsLocked(chosenEdge.edge)
      ? (() => {
        const points = edgeControlPoints(chosenEdge);
        const id = escapeText(chosenEdge.edge.id);
        const bends = edgeWaypoints(chosenEdge.edge).map((point, index) => `<circle data-edge-bend="${index}" data-edge-id="${id}" cx="${point.x}" cy="${point.y}" r="${touchReach(Math.max(5, 6 / zoom), 11)}" fill="${colors.accent}" stroke="${colors.handle}" stroke-width="2" vector-effect="non-scaling-stroke" pointer-events="all"><title>Drag to move this bend · double-click to remove it</title></circle>`).join('');
        // While a bend is being pulled, the hollow handles stand aside.
        const ghosts = drag?.type === 'edge-bend' && drag.moved ? '' : points.slice(1).map((point, index) => {
          const middle = {x: (points[index].x + point.x) / 2, y: (points[index].y + point.y) / 2};
          return `<circle data-edge-bend-ghost="${index}" data-edge-id="${id}" cx="${middle.x}" cy="${middle.y}" r="${touchReach(Math.max(4, 5 / zoom), 9)}" fill="${colors.handle}" fill-opacity=".9" stroke="${colors.accent}" stroke-width="1.5" stroke-dasharray="2 2" vector-effect="non-scaling-stroke" pointer-events="all"><title>Drag to bend the connector here</title></circle>`;
        }).join('');
        return bends + ghosts;
      })()
      : '';
    const preview = connection
      ? `<path data-connection-preview d="${routedPath(connection.start, connection.current, connection.side)}" fill="none" stroke="${colors.accent}" stroke-width="2" stroke-dasharray="6 4" vector-effect="non-scaling-stroke" pointer-events="none"/>`
      : '';
    const layerOrder = item => Number(layerById(item.layerId)?.order) || 0;
    const visibleBoundaries = state.boundaries.filter(boundaryIsVisible)
      .sort((a, b) => boundaryDepth(a) - boundaryDepth(b)
        || layerOrder(a) - layerOrder(b) || Number(a.order) - Number(b.order));
    const visibleNodes = state.nodes.filter(nodeIsVisible)
      .sort((a, b) => layerOrder(a) - layerOrder(b) || Number(a.order) - Number(b.order));
    layer.innerHTML = `
      <rect data-canvas-background width="${state.canvas.width}" height="${state.canvas.height}" fill="none"/>
      <rect data-editor-grid width="${state.canvas.width}" height="${state.canvas.height}" fill="url(#infragram-editor-grid)" pointer-events="none"/>
      <g data-boundary-layer>${visibleBoundaries.map(boundaryMarkup).join('')}</g>
      <g data-edge-layer>${edges.map(edgeMarkup).join('')}</g>
      ${preview}
      <g data-node-layer>${visibleNodes.map(nodeMarkup).join('')}</g>
      <g data-edge-label-layer>${(() => {
        placedCaptions = [];
        captionWires = edges.map(item => captionCorners(item));
        collectingCaptions = true;
        try { return edges.map(edgeLabelMarkup).join(''); } finally { collectingCaptions = false; }
      })()}</g>
      <g data-edge-terminal-layer>${terminals}${endHandles}${bendHandles}</g>
      <g data-alignment-guide-layer>${alignmentGuides.map(alignmentGuideMarkup).join('')}</g>
      <g data-selection-overlay-layer>${selectionOverlayMarkup()}${marqueeMarkup()}</g>`;
    document.querySelector('[data-editor-action="undo"]').disabled = undoStack.length === 0;
    document.querySelector('[data-editor-action="redo"]').disabled = redoStack.length === 0;
    document.querySelectorAll('[data-editor-action="delete"], [data-selection-action="delete"]').forEach(button => {
      const objects = selectedObjects();
      const selectedEdge = selected?.type === 'edge' ? selectedItem() : null;
      button.disabled = selectedEdge
        ? itemIsLocked(selectedEdge)
        : !objects.some(object => !itemIsLocked(object));
    });
    applyCrossings(edges);
    placeBrandMark();
    renderLayerInspector();
    updateEditorGrid();
    updateInspector();
    syncElementPopup();
    afterRender.forEach(hook => hook());
    requestAnimationFrame(updateSelectionToolbar);
  };
  // The step list answers a flow as the drawing does: a row whose wires it
  // lights stays, the others step back. The list is drawn once, so a full
  // draw paints it here too.
  const paintStepRows = lit => {
    diagram.querySelectorAll('[data-step-row]').forEach(row => {
      const number = Number(row.dataset.stepRow), flow = row.getAttribute('data-step-flow') || '';
      const shown = !lit || state.edges.some(edge => lit.edges.has(edge.id)
        && edgeStep(edge) === number && (edge.stepFlow || '') === flow);
      if (shown) row.removeAttribute('data-focus-dimmed');
      else row.setAttribute('data-focus-dimmed', 'true');
    });
  };
  // A single click's flow, painted onto the drawing as it stands: the
  // attributes a full draw writes, without replacing an element, so the
  // second click of a double click lands on what the first one hit.
  const paintFlow = () => {
    currentFlow = flowLit();
    const lit = currentFlow;
    const dim = (element, dimmed) => (dimmed
      ? element.setAttribute('data-focus-dimmed', 'true') : element.removeAttribute('data-focus-dimmed'));
    diagram.querySelectorAll('[data-graph-node]').forEach(element => {
      element.setAttribute('data-focus-dimmed', String(Boolean(lit && !lit.nodes.has(element.dataset.nodeId))));
    });
    diagram.querySelectorAll('[data-graph-boundary]').forEach(element => {
      element.setAttribute('data-focus-dimmed', String(Boolean(lit && !lit.frames.has(element.dataset.boundaryId))));
    });
    diagram.querySelectorAll('[data-graph-edge]').forEach(element => {
      element.setAttribute('data-focus-edge', String(Boolean(lit?.edges.has(element.dataset.edgeId))));
    });
    diagram.querySelectorAll('[data-edge-group]').forEach(element => {
      dim(element, Boolean(lit && !lit.edges.has(element.dataset.edgeGroup)));
    });
    diagram.querySelectorAll('[data-edge-label]').forEach(element => {
      dim(element, Boolean(lit && !lit.edges.has(element.dataset.edgeLabel)));
    });
    paintStepRows(lit);
    // the cost lens's tint is drawn by a full draw; a click's flow ends it
    if (!lit?.heat) diagram.querySelectorAll('[data-cost-heat]').forEach(element => element.remove());
    syncElementPopup();
    // the inventory's row follows the card whose flow is shown (33-costs)
    if (typeof syncResources === 'function') syncResources();
  };
