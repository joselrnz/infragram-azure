// @module 19-canvas-pointer: drag and drop, pointer and double-click interaction on the canvas
  diagram.addEventListener('dragover', event => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    diagram.classList.add('drop-active');
  });
  diagram.addEventListener('dragleave', event => {
    if (!diagram.contains(event.relatedTarget)) diagram.classList.remove('drop-active');
  });
  diagram.addEventListener('drop', event => {
    event.preventDefault();
    diagram.classList.remove('drop-active');
    const framePreset = event.dataTransfer.getData('application/x-infragram-frame-preset');
    if (framePreset) {
      addFramePreset(framePreset, toSvgPoint(event.clientX, event.clientY));
      return;
    }
    let payload;
    try { payload = JSON.parse(event.dataTransfer.getData('application/x-infragram-component')); }
    catch (_) { return; }
    addComponent(payload, toSvgPoint(event.clientX, event.clientY));
  });

  // The hint says how to work the canvas; once the reader has, it steps aside.
  const retireHint = () => document.querySelector('[data-editor-help]')?.classList.add('canvas-help--retired');
  viewport.addEventListener('pointerdown', retireHint, {once: true});
  viewport.addEventListener('wheel', retireHint, {once: true, passive: true});
  // and, read or not, it leaves the drawing after a first look
  setTimeout(retireHint, 10000);
  // A press gives the drawing the keyboard without the keyboard's focus
  // ring, which an engine may draw for focus a script gave; the first key
  // pressed brings the ring back, for the reader now using the keyboard.
  const focusFromPointer = () => {
    diagram.dataset.pointerFocus = 'true';
    diagram.focus({preventScroll: true, focusVisible: false});
  };
  document.addEventListener('keydown', () => { delete diagram.dataset.pointerFocus; }, true);

  // A single click shows an item's flow; a double click selects it for
  // editing -- handles, connection points, the inspector -- and a double
  // click on an item already selected edits its text. The same holds for a
  // tap and a double tap. A mouse press and drag still moves an item.
  const DOUBLE_TAP_MS = 350;
  // Touch has no click count: a second tap soon after the first, near it
  // and on the same item, is a double tap.
  const tapCount = (clientX, clientY, key, timeStamp) => {
    // Input can wait behind rendering: count the finger's timing rather than
    // how long the main thread took to reach its handler.
    const now = timeStamp;
    const second = Boolean(lastTap && now >= lastTap.time && now - lastTap.time < DOUBLE_TAP_MS && lastTap.key === key
      && Math.hypot(clientX - lastTap.x, clientY - lastTap.y) < 32);
    lastTap = second ? null : {time: now, x: clientX, y: clientY, key};
    return second ? 2 : 1;
  };
  // A mouse's double click comes as the browser's dblclick (below): a press
  // carries no dependable click count across engines. A finger's is counted.
  const clicksOf = (event, key) => {
    if (event.pointerType !== 'touch') return 1;
    const clicks = tapCount(event.clientX, event.clientY, key, event.timeStamp);
    // the dblclick an engine may make of the two taps must not act again
    if (clicks >= 2) dblclickHandledAt = performance.now();
    return clicks;
  };
  // What a press or a tap is on: a card, a wire (or its caption), a frame.
  const itemAt = (element, point) => {
    const nodeElement = element?.closest?.('[data-graph-node]');
    const node = nodeElement ? nodeById(nodeElement.dataset.nodeId) : null;
    if (node) return {type: 'node', item: node};
    const edgeElement = element?.closest?.('[data-edge-label],[data-graph-edge],[data-edge-hit]');
    const edge = edgeElement
      ? edgeById(edgeElement.dataset.edgeId || edgeElement.dataset.edgeLabel || edgeElement.dataset.edgeHit) : null;
    if (edge) return {type: 'edge', item: edge};
    const hitNode = nodeHitAt(point);
    if (hitNode) return {type: 'node', item: hitNode};
    const boundaryElement = element?.closest?.('[data-graph-boundary]');
    const boundary = boundaryElement
      ? boundaryHitAt(point) || boundaryById(boundaryElement.dataset.boundaryId) : null;
    return boundary ? {type: 'boundary', item: boundary} : null;
  };
  // The step list's row level with a press inside the list, the gaps
  // between a badge and its text included: the step it names.
  const stepRowAt = (element, clientY) => {
    const list = element?.closest?.('[data-step-list]');
    if (!list) return null;
    const rows = [...list.querySelectorAll('[data-step-row]')].map(row => {
      const box = row.getBoundingClientRect();
      return {row, middle: box.top + box.height / 2, height: box.height};
    });
    if (!rows.length) return null;
    // half the drawn spacing of two rows either side of a row's middle
    const pitch = rows.length > 1 ? Math.abs(rows[1].middle - rows[0].middle) : rows[0].height;
    const nearest = rows.reduce((best, item) => (Math.abs(item.middle - clientY) < Math.abs(best.middle - clientY) ? item : best));
    return Math.abs(nearest.middle - clientY) <= pitch / 2 ? nearest.row : null;
  };
  const isSelectedForEditing = (type, id) => (type === 'node' ? isNodeSelected(id)
    : type === 'edge' ? selectedEdgeIds.has(id) : isBoundarySelected(id));
  // On a phone the sheet opening or closing leaves the drawing where it is
  // on the screen. Refitted to the new room -- or re-centred by the gutters
  // that let any point of it scroll to the middle -- it would jump from
  // under the finger between the two taps of a double tap. `then` runs once
  // it has settled.
  const setSheetCollapsed = (collapsed, then = null) => {
    if (document.body.classList.contains('inspector-collapsed') === collapsed) {
      then?.();
      return;
    }
    leaveFitMode();
    const before = diagram.getBoundingClientRect();
    setInspectorCollapsed(collapsed);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const after = diagram.getBoundingClientRect();
      viewport.scrollLeft += after.left - before.left;
      viewport.scrollTop += after.top - before.top;
      then?.();
    }));
  };
  const selectForEditing = (type, id) => {
    if (type === 'node') selectNode(id);
    else if (type === 'edge') selectEdge(id);
    else selectBoundary(id);
    // The inspector opens on what was selected, not on the whole drawing.
    if (document.querySelector('[data-inspector-tab="diagram"]')?.getAttribute('aria-selected') === 'true') {
      document.querySelector('[data-inspector-tab="style"]')?.click();
    }
    const selector = type === 'node' ? `[data-graph-node][data-node-id="${CSS.escape(id)}"]`
      : type === 'edge' ? `[data-edge-group="${CSS.escape(id)}"]`
        : `[data-graph-boundary][data-boundary-id="${CSS.escape(id)}"]`;
    if (phoneLayout()) {
      // A phone's sheet takes the lower part of the screen; once it has, the
      // item scrolls into what is left of the drawing if it must.
      setSheetCollapsed(false, () => {
        diagram.querySelector(selector)?.scrollIntoView({block: 'nearest', inline: 'nearest'});
      });
      return;
    }
    setInspectorCollapsed(false);
    if (!inspectorOverlays()) return;
    // A tablet's panel lies over the right of the drawing: the item slides
    // left of it if the panel would cover it.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const box = diagram.querySelector(selector)?.getBoundingClientRect();
      const panel = document.querySelector('.right-inspector').getBoundingClientRect();
      if (box && box.right > panel.left - 16) {
        leaveFitMode();
        viewport.scrollLeft += box.right - (panel.left - 16);
      }
    }));
  };
  const doubleClick = (type, item) => {
    if (isSelectedForEditing(type, item.id)) {
      openTextEditor(item, type);
      return;
    }
    selectForEditing(type, item.id);
    setStatus(`${item.name || item.label || 'Connector'} selected for editing`, {show: false});
    renderGraph();
  };
  // A selection's handles have to go when a flow replaces it; with nothing
  // selected the flow is painted onto the drawing as it stands (paintFlow).
  const showFlowOf = (type, id, more = {}) => {
    const redraw = Boolean(selected || selectedNodeIds.size || selectedEdgeIds.size || selectedBoundaryIds.size);
    // a flow is for reading: on a phone the editing sheet makes way for it
    if (phoneLayout()) setSheetCollapsed(true);
    showFlow(type, id, more);
    if (redraw) renderGraph();
    else paintFlow();
  };
  // A tap that did not become a pan (20-zoom-and-pan): a flow, a selection
  // for editing on the second tap, or nothing on empty canvas.
  const handleCanvasTap = tap => {
    const point = toSvgPoint(tap.clientX, tap.clientY);
    const hit = itemAt(tap.target, point);
    const row = stepRowAt(tap.target, tap.clientY);
    if (row) {
      showFlowOf('step', Number(row.dataset.stepRow), {flow: row.getAttribute('data-step-flow') || ''});
      return;
    }
    const clicks = tapCount(tap.clientX, tap.clientY, hit ? `${hit.type}:${hit.item.id}` : 'canvas', tap.timeStamp);
    if (!hit) {
      if (phoneLayout()) setSheetCollapsed(true);
      if (selected || flowFocus) {
        clearSelection();
        renderGraph();
      }
      return;
    }
    if (clicks >= 2) {
      dblclickHandledAt = performance.now();
      doubleClick(hit.type, hit.item);
    } else {
      showFlowOf(hit.type, hit.item.id);
    }
  };
  // What a press on an item selected for editing starts -- and a drag from
  // an item not yet selected, once the pointer has travelled.
  const startNodeDrag = (node, point, pointerId, redraw = true) => {
    if (itemIsLocked(node)) {
      setStatus('Locked layer · this component cannot move');
      renderGraph();
      return;
    }
    checkpoint();
    drag = {
      type: 'node', id: node.id, offsetX: point.x - node.x, offsetY: point.y - node.y,
      nodePositions: Object.fromEntries(selectedNodes()
        .filter(item => !itemIsLocked(item))
        .map(item => [item.id, {x: item.x, y: item.y}])),
      originalParents: Object.fromEntries(selectedNodes().map(item => [item.id, item.boundaryId || null])),
      moved: false,
    };
    diagram.setPointerCapture(pointerId);
    if (redraw) renderGraph();
  };
  const startEdgeShape = (edge, item, point) => {
    connectorPath(item);
    const index = nearestEdgeStretch(edgeControlPoints(item), point);
    const before = clone(edgeWaypoints(edge));
    checkpoint();
    // Nothing is added until the pointer actually moves, so a press on a
    // wire alone changes nothing.
    drag = {type: 'edge-bend', id: edge.id, index, before, ghost: true, pending: true, moved: false};
  };
  const startLabelDrag = (edge, item, point, pointerId) => {
    if (itemIsLocked(edge)) {
      setStatus('Locked layer · this connector label cannot move');
      renderGraph();
      return;
    }
    const labelPosition = resolvedEdgeLabel(item);
    focusFromPointer();
    checkpoint();
    drag = {
      type: 'edge-label', id: edge.id,
      startX: point.x, startY: point.y,
      labelX: labelPosition.x, labelY: labelPosition.y,
      moved: false,
    };
    diagram.setPointerCapture(pointerId);
    renderGraph();
  };
  const startBoundaryMove = (boundary, point, pointerId) => {
    if (itemIsLocked(boundary)) {
      setStatus('Locked layer · this frame cannot move');
      renderGraph();
      return;
    }
    const boundaryIds = state.boundaries
      .filter(item => isBoundaryDescendant(item.id, boundary.id))
      .map(item => item.id);
    const nodeIds = state.nodes
      .filter(node => node.boundaryId && isBoundaryDescendant(node.boundaryId, boundary.id))
      .map(node => node.id);
    checkpoint();
    drag = {
      type: 'boundary-move', id: boundary.id, startX: point.x, startY: point.y,
      originalParentId: boundary.parentId || null,
      boundaryPositions: Object.fromEntries(boundaryIds.map(id => {
        const item = boundaryById(id);
        return [id, {x: item.x, y: item.y}];
      })),
      nodePositions: Object.fromEntries(nodeIds.map(id => {
        const item = nodeById(id);
        return [id, {x: item.x, y: item.y}];
      })),
      moved: false,
    };
    diagram.setPointerCapture(pointerId);
    renderGraph();
  };
  // A press on an item not selected for editing waits: released where it
  // was, it was a click (the flow); moved, it selects the item and drags it.
  const pressPending = (type, id, event) => {
    pendingPress = {
      type, id, pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY,
      point: toSvgPoint(event.clientX, event.clientY),
    };
  };
  const beginPendingDrag = event => {
    const press = pendingPress;
    pendingPress = null;
    if (press.type === 'node') {
      const node = nodeById(press.id);
      if (!node) return;
      selectNode(node.id);
      startNodeDrag(node, press.point, event.pointerId);
    } else if (press.type === 'edge' || press.type === 'label') {
      const edge = edgeById(press.id);
      const item = edge && edgeGeometry().find(candidate => candidate.edge.id === edge.id);
      if (!item) return;
      selectEdge(edge.id);
      if (press.type === 'label') startLabelDrag(edge, item, press.point, event.pointerId);
      else if (!itemIsLocked(edge)) startEdgeShape(edge, item, press.point);
      else renderGraph();
    } else if (press.type === 'boundary') {
      const boundary = boundaryById(press.id);
      if (!boundary) return;
      selectBoundary(boundary.id);
      startBoundaryMove(boundary, press.point, event.pointerId);
    }
  };
  diagram.addEventListener('pointerdown', event => {
    // a press on the map takes the picking back from the table
    delete document.body.dataset.pickedInTable;
    if (event.button === 2) return;
    // The handlers below cancel the press's default, which would have taken
    // focus from a field outside the canvas; left there, Delete and the
    // shortcuts keep typing into the search box instead of acting on the
    // selection. A field being left commits its value first, as a click would.
    const field = document.activeElement;
    // A button left focused -- the toolbar's Undo, the sidebar's logo --
    // is let go as well: a focused control owns Delete (26-keyboard), so
    // without this a card clicked after a button could not be deleted.
    if (field?.matches?.('input, textarea, select, button') && !diagram.contains(field)) field.blur();
    // The canvas takes the focus the press would have given it, so the
    // keyboard acts on what was just clicked: Tab steps the drawing only
    // while the canvas has focus (26-keyboard).
    if (document.activeElement !== diagram && !diagram.contains(document.activeElement)) {
      focusFromPointer();
    }
    const edgeEnd = event.target.closest('[data-edge-end]');
    if (edgeEnd) {
      const edge = edgeById(edgeEnd.dataset.edgeId);
      const item = edge && edgeGeometry().find(candidate => candidate.edge.id === edge.id);
      if (!edge || !item) return;
      if (itemIsLocked(edge)) {
        setStatus('Locked layer · this connector cannot be reconnected');
        event.preventDefault();
        return;
      }
      connectorPath(item);
      const end = edgeEnd.dataset.edgeEnd;
      const fixed = end === 'target' ? 'source' : 'target';
      connection = {
        edgeId: edge.id, end,
        source: edge[fixed],
        side: item[`${fixed}Port`],
        start: item[`${fixed}Seat`] || item[`${fixed}Point`],
        current: toSvgPoint(event.clientX, event.clientY),
      };
      viewport.dataset.connecting = 'true';
      diagram.setPointerCapture(event.pointerId);
      renderGraph();
      event.preventDefault();
      return;
    }
    // Shaping a wire: an existing bend, the hollow handle in the middle of a
    // stretch, or the wire itself -- all end up dragging one bend.
    const bendHandle = event.target.closest('[data-edge-bend]');
    const bendGhost = event.target.closest('[data-edge-bend-ghost]');
    if (bendHandle || bendGhost) {
      const handle = bendHandle || bendGhost;
      const edge = edgeById(handle.dataset.edgeId);
      if (!edge || itemIsLocked(edge)) {
        if (edge) setStatus('Locked layer · this connector cannot be shaped');
        return;
      }
      const point = toSvgPoint(event.clientX, event.clientY);
      const before = clone(edgeWaypoints(edge));
      checkpoint();
      let index;
      if (bendHandle) {
        index = Number(bendHandle.dataset.edgeBend);
      } else {
        index = Number(bendGhost.dataset.edgeBendGhost);
        edge.waypoints = [...before.slice(0, index), {x: snap(point.x), y: snap(point.y)}, ...before.slice(index)];
      }
      drag = {type: 'edge-bend', id: edge.id, index, before, ghost: Boolean(bendGhost), moved: false};
      if (bendGhost) renderGraph();
      event.preventDefault();
      return;
    }
    const edgeLabelElement = event.target.closest('[data-edge-label]');
    const nodeResizeHandle = event.target.closest('[data-node-resize]');
    const port = event.target.closest('[data-node-port]');
    const nodeElement = event.target.closest('[data-graph-node]');
    const edgeElement = event.target.closest('[data-graph-edge],[data-edge-hit]');
    const resizeHandle = event.target.closest('[data-boundary-resize]');
    if (edgeElement && !itemIsLocked(edgeById(edgeElement.dataset.edgeId || edgeElement.dataset.edgeHit))) {
      const edge = edgeById(edgeElement.dataset.edgeId || edgeElement.dataset.edgeHit);
      const item = edgeGeometry().find(candidate => candidate.edge.id === edge.id);
      if (item) {
        const adding = event.shiftKey || event.ctrlKey || event.metaKey;
        if (adding) {
          // adding to a selection is not the start of a shape
          selectEdge(edge.id, true);
          renderGraph();
          event.preventDefault();
          return;
        }
        if (clicksOf(event, `edge:${edge.id}`) >= 2) {
          doubleClick('edge', edge);
          event.preventDefault();
          return;
        }
        if (!selectedEdgeIds.has(edge.id)) {
          pressPending('edge', edge.id, event);
          event.preventDefault();
          return;
        }
        const already = selected?.type === 'edge' && selected.id === edge.id && selectedEdgeIds.size === 1;
        selectEdge(edge.id);
        startEdgeShape(edge, item, toSvgPoint(event.clientX, event.clientY));
        if (!already) renderGraph();
        event.preventDefault();
        return;
      }
    }
    const boundaryElement = event.target.closest('[data-graph-boundary]');
    if (edgeLabelElement) {
      const edge = edgeById(edgeLabelElement.dataset.edgeId);
      const item = edgeGeometry().find(candidate => candidate.edge.id === edge?.id);
      if (!edge || !item) return;
      const adding = event.shiftKey || event.ctrlKey || event.metaKey;
      if (adding) {
        selectEdge(edge.id, true);
        renderGraph();
        event.preventDefault();
        return;
      }
      if (clicksOf(event, `edge:${edge.id}`) >= 2) {
        doubleClick('edge', edge);
        event.preventDefault();
        return;
      }
      if (!selectedEdgeIds.has(edge.id)) {
        pressPending('label', edge.id, event);
        event.preventDefault();
        return;
      }
      selectEdge(edge.id);
      startLabelDrag(edge, item, toSvgPoint(event.clientX, event.clientY), event.pointerId);
      event.preventDefault();
      return;
    }
    if (nodeResizeHandle) {
      // Handles carry their own attribute so data-node-id stays unique per node.
      const node = nodeById(nodeResizeHandle.dataset.resizeNodeId);
      selectNode(node.id);
      if (itemIsLocked(node)) {
        setStatus('Locked layer · this component cannot be resized');
        renderGraph();
        event.preventDefault();
        return;
      }
      const point = toSvgPoint(event.clientX, event.clientY);
      checkpoint();
      drag = {
        type: 'node-resize', id: node.id, startX: point.x, startY: point.y,
        x: node.x, y: node.y, width: node.width, height: node.height,
        direction: nodeResizeHandle.dataset.nodeResize || 'se', moved: false,
      };
      diagram.setPointerCapture(event.pointerId);
      renderGraph();
      event.preventDefault();
      return;
    }
    if (resizeHandle) {
      const boundary = boundaryById(resizeHandle.dataset.boundaryId);
      selectBoundary(boundary.id);
      if (itemIsLocked(boundary)) {
        setStatus('Locked layer · this frame cannot be resized');
        renderGraph();
        event.preventDefault();
        return;
      }
      const point = toSvgPoint(event.clientX, event.clientY);
      checkpoint();
      drag = {
        type: 'boundary-resize', id: boundary.id, startX: point.x, startY: point.y,
        x: boundary.x, y: boundary.y, width: boundary.width, height: boundary.height,
        direction: resizeHandle.dataset.boundaryResize || 'se', moved: false,
      };
      diagram.setPointerCapture(event.pointerId);
      renderGraph();
      event.preventDefault();
      return;
    }
    if (port && nodeElement && !itemIsLocked(nodeById(nodeElement.dataset.nodeId))) {
      const node = nodeById(nodeElement.dataset.nodeId);
      // the second click of a double click on a connection point: the card
      if (event.pointerType !== 'touch' && lastPortClick?.id === node.id
          && performance.now() - lastPortClick.time < 500
          && Math.hypot(event.clientX - lastPortClick.clientX, event.clientY - lastPortClick.clientY) < 8) {
        lastPortClick = null;
        dblclickHandledAt = performance.now();
        doubleClick('node', node);
        event.preventDefault();
        return;
      }
      const side = port.dataset.nodePort;
      connection = {
        source: node.id, side,
        start: seat(node, side, portPoint(node, side)), current: seat(node, side, portPoint(node, side)),
        // released where it was pressed on a card not selected for editing,
        // the press was a click on the card: its flow (pointerup)
        click: isNodeSelected(node.id) ? null : {clientX: event.clientX, clientY: event.clientY},
      };
      viewport.dataset.connecting = 'true';
      diagram.setPointerCapture(event.pointerId);
      renderGraph();
      event.preventDefault();
      return;
    }
    if (nodeElement) {
      const node = nodeById(nodeElement.dataset.nodeId);
      const adding = event.shiftKey || event.ctrlKey || event.metaKey;
      if (!adding && clicksOf(event, `node:${node.id}`) >= 2) {
        doubleClick('node', node);
        event.preventDefault();
        return;
      }
      if (!adding && !isNodeSelected(node.id)) {
        pressPending('node', node.id, event);
        event.preventDefault();
        return;
      }
      // already the one thing selected: nothing to redraw, so the element
      // stays under the pointer for the second click of a double click
      const only = selectedNodeIds.size === 1 && isNodeSelected(node.id)
        && !selectedBoundaryIds.size && !selectedEdgeIds.size;
      selectNode(node.id, adding);
      if (!isNodeSelected(node.id)) {
        renderGraph();
        event.preventDefault();
        return;
      }
      startNodeDrag(node, toSvgPoint(event.clientX, event.clientY), event.pointerId, !only);
      event.preventDefault();
      return;
    }
    if (edgeElement) {
      // a locked wire: its flow, or a selection that cannot shape it
      const edge = edgeById(edgeElement.dataset.edgeId || edgeElement.dataset.edgeHit);
      if (edge && clicksOf(event, `edge:${edge.id}`) >= 2) doubleClick('edge', edge);
      else if (edge && !selectedEdgeIds.has(edge.id)) showFlowOf('edge', edge.id);
      event.preventDefault();
      return;
    }
    if (boundaryElement) {
      const point = toSvgPoint(event.clientX, event.clientY);
      const boundary = boundaryHitAt(point)
        || boundaryById(boundaryElement.dataset.boundaryId);
      const adding = event.shiftKey || event.ctrlKey || event.metaKey;
      if (!adding && clicksOf(event, `boundary:${boundary.id}`) >= 2) {
        doubleClick('boundary', boundary);
        event.preventDefault();
        return;
      }
      if (!adding && !isBoundarySelected(boundary.id)) {
        pressPending('boundary', boundary.id, event);
        event.preventDefault();
        return;
      }
      selectBoundary(boundary.id, adding);
      if (!isBoundarySelected(boundary.id)) {
        renderGraph();
        event.preventDefault();
        return;
      }
      startBoundaryMove(boundary, point, event.pointerId);
      event.preventDefault();
      return;
    }
    // a row of the step list shows its step's wires, as a tap on it does
    const row = event.button === 0 && !event.shiftKey && !event.ctrlKey && !event.metaKey
      ? stepRowAt(event.target, event.clientY) : null;
    if (row) {
      focusFromPointer();
      showFlowOf('step', Number(row.dataset.stepRow), {flow: row.getAttribute('data-step-flow') || ''});
      event.preventDefault();
      return;
    }
    clearSelection();
    alignmentGuides = [];
    focusFromPointer();
    const point = toSvgPoint(event.clientX, event.clientY);
    marqueeSelection = {start: point, current: point, intersect: event.altKey};
    diagram.setPointerCapture(event.pointerId);
    renderGraph();
    event.preventDefault();
  });

  diagram.addEventListener('dblclick', event => {
    const bend = event.target.closest('[data-edge-bend]');
    if (bend) {
      removeEdgeBend(bend.dataset.edgeId, Number(bend.dataset.edgeBend));
      event.preventDefault();
      return;
    }
    // a double tap has acted already (clicksOf, handleCanvasTap)
    if (performance.now() - dblclickHandledAt < 700) {
      event.preventDefault();
      return;
    }
    const under = document.elementFromPoint(event.clientX, event.clientY);
    const hit = itemAt(under && diagram.contains(under) ? under : event.target,
      toSvgPoint(event.clientX, event.clientY));
    if (!hit) return;
    doubleClick(hit.type, hit.item);
    event.preventDefault();
  });

  diagram.addEventListener('pointermove', event => {
    if (pendingPress && event.pointerId === pendingPress.pointerId) {
      if (Math.hypot(event.clientX - pendingPress.clientX, event.clientY - pendingPress.clientY) < 4) return;
      beginPendingDrag(event);
    }
    if (drag?.type === 'edge-bend') {
      const edge = edgeById(drag.id);
      if (!edge) return;
      if (!drag.captured) {
        // now that it is a drag and not a click, follow the pointer anywhere
        diagram.setPointerCapture(event.pointerId);
        drag.captured = true;
      }
      const point = toSvgPoint(event.clientX, event.clientY);
      const at = {
        x: clamp(event.altKey ? point.x : snap(point.x), 0, state.canvas.width),
        y: clamp(event.altKey ? point.y : snap(point.y), 0, state.canvas.height),
      };
      if (drag.pending) {
        // the first real movement is what adds the bend
        edge.waypoints = [...drag.before.slice(0, drag.index), at, ...drag.before.slice(drag.index)];
        drag.pending = false;
      } else {
        const points = edgeWaypoints(edge);
        points[drag.index] = at;
        edge.waypoints = points;
      }
      drag.moved = true;
      renderGraph();
      return;
    }
    if (drag?.type === 'edge-label') {
      const edge = edgeById(drag.id);
      const item = edgeGeometry().find(candidate => candidate.edge.id === edge?.id);
      if (!edge || !item) return;
      const point = toSvgPoint(event.clientX, event.clientY);
      const automatic = automaticEdgeLabel(item);
      let labelX = clamp(drag.labelX + point.x - drag.startX, 12, state.canvas.width - 12);
      let labelY = clamp(drag.labelY + point.y - drag.startY, 12, state.canvas.height - 12);
      if (!event.altKey) {
        labelX = snap(labelX);
        labelY = snap(labelY);
      }
      const dx = labelX - automatic.x;
      const dy = labelY - automatic.y;
      drag.moved ||= dx !== Number(edge.labelPlacement?.dx || 0)
        || dy !== Number(edge.labelPlacement?.dy || 0);
      edge.labelPlacement = {mode: 'manual', dx, dy};
      delete edge.labelX;
      delete edge.labelY;
      renderGraph();
    } else if (drag?.type === 'node-resize') {
      const node = nodeById(drag.id);
      const point = toSvgPoint(event.clientX, event.clientY);
      ensureCanvasExtent({
        right: point.x + CANVAS_MARGIN,
        bottom: point.y + CANVAS_MARGIN,
      });
      const parent = node.boundaryId ? boundaryById(node.boundaryId) : null;
      const pad = parent?.pad || 0;
      const minLeft = parent ? parent.x + pad : 0;
      const minTop = parent ? parent.y + pad : 0;
      const maxRight = parent ? parent.x + parent.width - pad : state.canvas.width;
      const maxBottom = parent ? parent.y + parent.height - pad : state.canvas.height;
      const floor = isPanel(node) ? panelFloor(node) : null;
      const minWidth = floor?.width || node.minWidth || (node.displayMode === 'icon' ? 48 : 96);
      const minHeight = floor?.height || node.minHeight || (node.displayMode === 'icon' ? 48 : 56);
      const dx = point.x - drag.startX;
      const dy = point.y - drag.startY;
      let left = drag.x;
      let top = drag.y;
      let right = drag.x + drag.width;
      let bottom = drag.y + drag.height;
      if (drag.direction.includes('w')) left = clamp(drag.x + dx, minLeft, right - minWidth);
      if (drag.direction.includes('e')) right = clamp(drag.x + drag.width + dx, left + minWidth, maxRight);
      if (drag.direction.includes('n')) top = clamp(drag.y + dy, minTop, bottom - minHeight);
      if (drag.direction.includes('s')) bottom = clamp(drag.y + drag.height + dy, top + minHeight, maxBottom);
      if (!event.altKey) {
        left = snap(left);
        top = snap(top);
        right = snap(right);
        bottom = snap(bottom);
      }
      drag.moved ||= left !== node.x || top !== node.y
        || right - left !== node.width || bottom - top !== node.height;
      node.x = left;
      node.y = top;
      node.width = right - left;
      node.height = bottom - top;
      renderGraph();
    } else if (drag?.type === 'node') {
      const node = nodeById(drag.id);
      const point = toSvgPoint(event.clientX, event.clientY);
      const moving = Object.keys(drag.nodePositions).map(nodeById).filter(Boolean);
      ensureCanvasExtent({
        right: point.x + Math.max(...moving.map(item => item.width)) + CANVAS_MARGIN,
        bottom: point.y + Math.max(...moving.map(item => item.height)) + CANVAS_MARGIN,
      });
      const origin = drag.nodePositions[node.id];
      const position = alignedNodePosition(
        node,
        point.x - drag.offsetX,
        point.y - drag.offsetY,
        event.altKey,
      );
      const dx = position.x - origin.x;
      const dy = position.y - origin.y;
      drag.moved ||= dx !== 0 || dy !== 0;
      // the dots are for wiring a card that stands still
      if (drag.moved) viewport.dataset.moving = 'true';
      Object.entries(drag.nodePositions).forEach(([id, start]) => {
        const item = nodeById(id);
        item.x = clamp(start.x + dx, 0, state.canvas.width - item.width);
        item.y = clamp(start.y + dy, 0, state.canvas.height - item.height);
      });
      alignmentGuides = position.guides;
      updateDropTarget(node, null, event.altKey);
      // Only the cards being dragged and the wires they carry have moved.
      if (!dragMovedNodes(Object.keys(drag.nodePositions))) renderGraph();
    } else if (drag?.type === 'boundary-move') {
      const boundary = boundaryById(drag.id);
      const origin = drag.boundaryPositions[boundary.id];
      const point = toSvgPoint(event.clientX, event.clientY);
      ensureCanvasExtent({
        right: point.x + boundary.width + CANVAS_MARGIN,
        bottom: point.y + boundary.height + CANVAS_MARGIN,
      });
      const bounds = {left: 0, top: 0, right: state.canvas.width, bottom: state.canvas.height};
      const rawDx = clamp(point.x - drag.startX, bounds.left - origin.x, bounds.right - origin.x - boundary.width);
      const rawDy = clamp(point.y - drag.startY, bounds.top - origin.y, bounds.bottom - origin.y - boundary.height);
      const dx = event.altKey ? rawDx : snap(rawDx);
      const dy = event.altKey ? rawDy : snap(rawDy);
      drag.moved ||= dx !== 0 || dy !== 0;
      Object.entries(drag.boundaryPositions).forEach(([id, position]) => {
        const item = boundaryById(id);
        item.x = position.x + dx;
        item.y = position.y + dy;
      });
      Object.entries(drag.nodePositions).forEach(([id, position]) => {
        const item = nodeById(id);
        item.x = position.x + dx;
        item.y = position.y + dy;
      });
      updateDropTarget(boundary, boundary.id, event.altKey);
      renderGraph();
    } else if (drag?.type === 'boundary-resize') {
      const boundary = boundaryById(drag.id);
      const point = toSvgPoint(event.clientX, event.clientY);
      ensureCanvasExtent({
        right: point.x + CANVAS_MARGIN,
        bottom: point.y + CANVAS_MARGIN,
      });
      const childBoundaries = state.boundaries.filter(item => item.parentId === boundary.id);
      const childNodes = state.nodes.filter(node => node.boundaryId === boundary.id);
      const contentRight = Math.max(
        boundary.x + (boundary.minWidth || 160),
        ...childBoundaries.map(item => item.x + item.width + (boundary.pad || 0)),
        ...childNodes.map(node => node.x + node.width + (boundary.pad || 0)),
      );
      const contentBottom = Math.max(
        boundary.y + (boundary.minHeight || 104),
        ...childBoundaries.map(item => item.y + item.height + (boundary.pad || 0)),
        ...childNodes.map(node => node.y + node.height + (boundary.pad || 0)),
      );
      const contentLeft = Math.min(
        boundary.x + boundary.width - (boundary.minWidth || 160),
        ...childBoundaries.map(item => item.x - (boundary.pad || 0)),
        ...childNodes.map(node => node.x - (boundary.pad || 0)),
      );
      const contentTop = Math.min(
        boundary.y + boundary.height - (boundary.minHeight || 104),
        ...childBoundaries.map(item => item.y - (boundary.pad || 0)),
        ...childNodes.map(node => node.y - (boundary.pad || 0)),
      );
      const parent = boundary.parentId ? boundaryById(boundary.parentId) : null;
      const growsEditableFoundation = Boolean(boundary.editableFoundation);
      const minLeft = parent ? parent.x + (parent.pad || 0) : 0;
      const minTop = parent ? parent.y + (parent.pad || 0) : 0;
      const maxRight = parent && !growsEditableFoundation
        ? parent.x + parent.width - (parent.pad || 0) : state.canvas.width;
      const maxBottom = parent && !growsEditableFoundation
        ? parent.y + parent.height - (parent.pad || 0) : state.canvas.height;
      const dx = point.x - drag.startX;
      const dy = point.y - drag.startY;
      let left = drag.x;
      let top = drag.y;
      let right = drag.x + drag.width;
      let bottom = drag.y + drag.height;
      if (drag.direction.includes('w')) {
        left = clamp(drag.x + dx, minLeft, contentLeft);
      }
      if (drag.direction.includes('e')) {
        right = clamp(drag.x + drag.width + dx, contentRight, maxRight);
      }
      if (drag.direction.includes('n')) {
        top = clamp(drag.y + dy, minTop, contentTop);
      }
      if (drag.direction.includes('s')) {
        bottom = clamp(drag.y + drag.height + dy, contentBottom, maxBottom);
      }
      if (!event.altKey) {
        left = snap(left);
        top = snap(top);
        right = snap(right);
        bottom = snap(bottom);
      }
      drag.moved ||= left !== boundary.x || top !== boundary.y
        || right - left !== boundary.width || bottom - top !== boundary.height;
      boundary.x = left;
      boundary.y = top;
      boundary.width = right - left;
      boundary.height = bottom - top;
      if (growsEditableFoundation) {
        let child = boundary;
        let ancestor = child.parentId ? boundaryById(child.parentId) : null;
        while (ancestor) {
          const pad = ancestor.pad || 0;
          ancestor.width = snap(Math.max(
            ancestor.width,
            child.x + child.width + pad - ancestor.x,
          ));
          ancestor.height = snap(Math.max(
            ancestor.height,
            child.y + child.height + pad - ancestor.y,
          ));
          child = ancestor;
          ancestor = child.parentId ? boundaryById(child.parentId) : null;
        }
      }
      renderGraph();
    } else if (connection) {
      // Like an ETL canvas: the card under the pointer lights up and the line
      // runs to it, so a drop anywhere on the card connects.
      const point = toSvgPoint(event.clientX, event.clientY);
      // Which card the pointer is over: the page answers first, because what is
      // drawn on top is what a reader is pointing at. With the pointer
      // captured, Firefox hit-tests the canvas as the element that holds it and
      // answers nothing useful; the drawing itself is asked then.
      const under = document.elementFromPoint(event.clientX, event.clientY);
      const hovered = under?.closest?.('[data-graph-node]');
      const candidate = hovered ? nodeById(hovered.dataset.nodeId) : nodeHitAt(point);
      connectTargetId = candidate && candidate.id !== connection.source && !itemIsLocked(candidate)
        ? candidate.id : null;
      if (connectTargetId) {
        // Whatever the drop will do, the line shows it: the handle under the
        // pointer if it is on one, otherwise the side this pair of cards will
        // be wired on, worked out exactly as the finished connector will be.
        // An engine that hit-tests the canvas as a whole gives no handle here;
        // the line then shows the side the router will pick, which is what the
        // drop will do anyway.
        const hoveredPort = under?.closest?.('[data-node-port]');
        const fixed = nodeById(connection.source);
        const movingEnd = connection.end === 'source' ? 'sourcePort' : 'targetPort';
        const sides = connection.end === 'source'
          ? inferredSides(candidate, fixed, {sourcePort: 'auto', targetPort: connection.side || 'auto'})
          : inferredSides(fixed, candidate, {sourcePort: connection.side || 'auto', targetPort: 'auto'});
        const side = hoveredPort?.dataset.nodePort || sides[movingEnd];
        connection.current = seat(candidate, side, portPoint(candidate, side));
      } else {
        connection.current = point;
      }
      // Nothing but the line and the lit card changes while a connection is
      // drawn, and a whole re-render costs a third of a second on a large
      // diagram. Move the line itself and leave the rest of the drawing alone.
      const preview = diagram.querySelector('[data-connection-preview]');
      if (!preview) {
        renderGraph();
      } else {
        preview.setAttribute('d', routedPath(connection.start, connection.current, connection.side));
        const lit = diagram.querySelector('[data-graph-node][data-connect-target="true"]');
        if ((lit?.dataset.nodeId || null) !== connectTargetId) {
          if (lit) lit.dataset.connectTarget = 'false';
          const target = connectTargetId
            ? diagram.querySelector(`[data-graph-node][data-node-id="${CSS.escape(connectTargetId)}"]`) : null;
          if (target) target.dataset.connectTarget = 'true';
        }
      }
    } else if (marqueeSelection) {
      marqueeSelection.current = toSvgPoint(event.clientX, event.clientY);
      marqueeSelection.intersect = event.altKey;
      renderGraph();
    }
  });

  diagram.addEventListener('pointerup', event => {
    if (pendingPress && event.pointerId === pendingPress.pointerId) {
      const press = pendingPress;
      pendingPress = null;
      showFlowOf(press.type === 'label' ? 'edge' : press.type, press.id);
      if (diagram.hasPointerCapture(event.pointerId)) diagram.releasePointerCapture(event.pointerId);
      return;
    }
    if (drag) {
      if (!drag.moved) {
        discardCheckpoint();
        // a bend the pointer never moved was never wanted
        if (drag.type === 'edge-bend') {
          const edge = edgeById(drag.id);
          if (edge) {
            if (drag.before.length) edge.waypoints = drag.before;
            else delete edge.waypoints;
          }
        }
      }
      else {
        if (drag.type === 'edge-bend') {
          const edge = edgeById(drag.id);
          if (edge) dropStraightBends(edge);
          setStatus(`${edge?.label || 'Connector'} ${drag.ghost ? 'bent' : 'bend moved'}`, {show: false});
        } else if (drag.type === 'edge-label') {
          setStatus('Connector label moved', {show: false});
        } else if (drag.type === 'node-resize') {
          setStatus('Component resized', {show: false});
        } else if (drag.type === 'node') {
          Object.keys(drag.nodePositions).forEach(id => {
            const node = nodeById(id);
            if (event.altKey) {
              node.boundaryId = drag.originalParents[id];
              return;
            }
            const container = deepestBoundaryAt({x: node.x + node.width / 2, y: node.y + node.height / 2});
            const previous = drag.originalParents[id] ? boundaryById(drag.originalParents[id]) : null;
            const fallback = previous?.parentId ? boundaryById(previous.parentId) : null;
            const resolvedParent = container || fallback;
            node.boundaryId = resolvedParent?.id || null;
            if (resolvedParent) clampIntoBoundary(node, resolvedParent);
          });
          setStatus('Component moved', {show: false});
        } else if (drag.type === 'boundary-resize') {
          setStatus('Frame resized', {show: false});
        } else {
          const boundary = boundaryById(drag.id);
          if (!event.altKey) {
            const target = deepestBoundaryAt({
              x: boundary.x + boundary.width / 2,
              y: boundary.y + boundary.height / 2,
            }, boundary.id);
            const previous = drag.originalParentId ? boundaryById(drag.originalParentId) : null;
            const fallback = previous?.parentId ? boundaryById(previous.parentId) : null;
            const resolvedParent = target || fallback;
            boundary.parentId = resolvedParent?.id || null;
            if (resolvedParent) clampIntoBoundary(boundary, resolvedParent);
          }
          setStatus('Frame moved with its contents', {show: false});
        }
        persist();
      }
      // A press that never moved changed nothing; redrawing would swap the
      // element out from under the pointer and the browser would never see
      // the second click of a double-click.
      const quiet = !drag.moved;
      drag = null;
      delete viewport.dataset.moving;
      dropTargetId = null;
      alignmentGuides = [];
      if (!quiet) renderGraph();
    } else if (connection) {
      const hit = document.elementFromPoint(event.clientX, event.clientY);
      const port = hit?.closest('[data-node-port]');
      const targetId = hit?.closest?.('[data-graph-node]')?.dataset.nodeId
        || nodeHitAt(toSvgPoint(event.clientX, event.clientY))?.id
        || connectTargetId;
      const pending = connection;
      clearConnection();
      if (pending.click && Math.hypot(event.clientX - pending.click.clientX,
        event.clientY - pending.click.clientY) < 4) {
        // pressed on a handle of a card not selected, and let go: a click
        lastPortClick = {id: pending.source, time: performance.now(), clientX: event.clientX, clientY: event.clientY};
        showFlowOf('node', pending.source);
      } else if (pending.edgeId) {
        reconnectEdge(pending.edgeId, pending.end, targetId, port?.dataset.nodePort || 'auto');
      } else if (targetId && targetId !== pending.source) {
        // dropped on the card itself, not only on one of its handles
        if (itemIsLocked(nodeById(targetId))) {
          setStatus('Locked layer · connectors cannot be added');
          renderGraph();
        } else {
          connectNodes(pending.source, targetId, pending.side, port?.dataset.nodePort || 'auto');
        }
      } else {
        renderGraph();
      }
    } else if (marqueeSelection) {
      finishMarquee();
      renderGraph();
    }
    if (diagram.hasPointerCapture(event.pointerId)) diagram.releasePointerCapture(event.pointerId);
  });

  // A gesture the browser takes away -- a touch that became a scroll, a pen
  // lifted, the window handed to something else -- must not leave the canvas
  // mid-drag, with a line still following a pointer that is gone.
  diagram.addEventListener('pointercancel', event => {
    clearConnection();
    pendingPress = null;
    const interrupted = drag;
    drag = null;
    delete viewport.dataset.moving;
    dropTargetId = null;
    alignmentGuides = [];
    if (marqueeSelection) finishMarquee();
    // The gesture never finished, so nothing it did is kept: the checkpoint it
    // pushed when it started is the drawing as it was before.
    const before = interrupted ? discardCheckpoint() : undefined;
    if (before === undefined) renderGraph();
    else restore(before);
    if (diagram.hasPointerCapture(event.pointerId)) diagram.releasePointerCapture(event.pointerId);
  });
