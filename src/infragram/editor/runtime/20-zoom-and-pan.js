// @module 20-zoom-and-pan: zoom, fit, toolbar actions, wheel, touch pinch and panning
  const leaveFitMode = () => {
    fitMode = false;
    fitGeneration += 1;
  };
  const setZoom = (
    value,
    focusPoint = null,
    {preserveFit = false, canvasFocus = null} = {},
  ) => {
    if (!preserveFit) leaveFitMode();
    const previousZoom = zoom;
    const viewportRect = viewport.getBoundingClientRect();
    const diagramRect = diagram.getBoundingClientRect();
    const localX = focusPoint ? focusPoint.clientX - viewportRect.left
      : viewport.clientWidth / 2;
    const localY = focusPoint ? focusPoint.clientY - viewportRect.top
      : viewport.clientHeight / 2;
    const canvasX = canvasFocus?.x
      ?? (viewportRect.left + localX - diagramRect.left) / Math.max(previousZoom, 0.01);
    const canvasY = canvasFocus?.y
      ?? (viewportRect.top + localY - diagramRect.top) / Math.max(previousZoom, 0.01);
    zoom = clamp(Math.round(value * 1000) / 1000, MIN_ZOOM, MAX_ZOOM);
    ensureCanvasExtent({save: true});
    document.querySelector('[data-zoom-value]').textContent = `${Math.round(zoom * 100)}%`;
    document.querySelector('[data-editor-action="zoom-out"]').disabled = zoom <= MIN_ZOOM;
    document.querySelector('[data-editor-action="zoom-in"]').disabled = zoom >= MAX_ZOOM;
    updateEditorGrid();
    // a selected connector's end handles are sized for the zoom
    if (selected?.type === 'edge') renderGraph();
    requestAnimationFrame(() => {
      const origin = canvasOrigin();
      viewport.scrollLeft = Math.max(0, origin.x + canvasX * zoom - localX);
      viewport.scrollTop = Math.max(0, origin.y + canvasY * zoom - localY);
      updateSelectionToolbar();
    });
  };
  // The step list stands right of the drawing (placeStepList): a fit takes
  // it in, or the steps a flow is told by sit past the viewport's edge.
  const fitBounds = () => {
    let bounds = contentBounds();
    // the brand mark under the drawing is part of the picture, though it
    // can sit well left of the cards: fit it too, as the export frames it.
    // An open frame (34-drill-down) is fitted alone.
    const mark = drillPath.length ? null : diagram.querySelector('[data-brand-mark]');
    // and with the names of what its wires reach, which stand outside it
    const stubs = drillPath.length ? diagram.querySelector('[data-drill-stub-layer]') : null;
    if (bounds && stubs?.childElementCount) {
      const box = stubs.getBBox();
      bounds = {
        left: Math.min(bounds.left, box.x), top: Math.min(bounds.top, box.y),
        right: Math.max(bounds.right, box.x + box.width), bottom: Math.max(bounds.bottom, box.y + box.height),
      };
    }
    if (bounds && mark?.getClientRects().length) {
      const [x, y, width, height] = ['x', 'y', 'width', 'height'].map(name => Number(mark.getAttribute(name)));
      if ([x, y, width, height].every(Number.isFinite) && width > 0 && height > 0) {
        bounds = {
          left: Math.min(bounds.left, x),
          top: Math.min(bounds.top, y),
          right: Math.max(bounds.right, x + width),
          bottom: Math.max(bounds.bottom, y + height),
        };
      }
    }
    const list = diagram.querySelector('[data-step-list]');
    const matrix = diagram.getCTM();
    const transform = list?.getCTM();
    if (!bounds || !list || !matrix || !transform) return bounds;
    const box = list.getBBox();
    if (!box.width || !box.height) return bounds;
    const local = matrix.inverse().multiply(transform);
    const start = new DOMPoint(box.x, box.y).matrixTransform(local);
    const end = new DOMPoint(box.x + box.width, box.y + box.height).matrixTransform(local);
    return {
      left: Math.min(bounds.left, start.x),
      top: Math.min(bounds.top, start.y),
      right: Math.max(bounds.right, end.x),
      bottom: Math.max(bounds.bottom, end.y),
    };
  };
  const fitZoom = () => {
    fitMode = true;
    const generation = ++fitGeneration;
    const bounds = fitBounds();
    if (!bounds) {
      setZoom(1, null, {preserveFit: true});
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (!fitMode || generation !== fitGeneration) return;
        const origin = canvasOrigin();
        viewport.scrollLeft = Math.max(0, origin.x - viewport.clientWidth / 2);
        viewport.scrollTop = Math.max(0, origin.y - viewport.clientHeight / 2);
      }));
      return;
    }
    const width = Math.max(1, bounds.right - bounds.left);
    const height = Math.max(1, bounds.bottom - bounds.top);
    // a phone's screen is all drawing: a slimmer margin round it
    const margin = phoneLayout() ? 16 : 48;
    const pad = phoneLayout() ? 24 : 96;
    setZoom(Math.min(
      (viewport.clientWidth - margin) / (width + pad),
      (viewport.clientHeight - margin) / (height + pad),
      1,
    ), null, {preserveFit: true});
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (!fitMode || generation !== fitGeneration) return;
      const origin = canvasOrigin();
      viewport.scrollLeft = Math.max(
        0,
        origin.x + ((bounds.left + bounds.right) / 2) * zoom - viewport.clientWidth / 2,
      );
      viewport.scrollTop = Math.max(
        0,
        origin.y + ((bounds.top + bounds.bottom) / 2) * zoom - viewport.clientHeight / 2,
      );
      updateSelectionToolbar();
    }));
  };
  // Runs `callback` once no newer fit is pending: a fit settles two frames
  // after it starts, and the ResizeObserver can start another one in between.
  const whenFitSettles = callback => {
    const seen = fitGeneration;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (fitGeneration !== seen) whenFitSettles(callback);
      else callback();
    }));
  };

  document.querySelectorAll('[data-editor-action]').forEach(button => {
    button.addEventListener('click', () => {
      const action = button.dataset.editorAction;
      if (action === 'undo' && undoStack.length) {
        redoStack.push(JSON.stringify(state));
        restore(undoStack.pop());
      } else if (action === 'redo' && redoStack.length) {
        undoStack.push(JSON.stringify(state));
        restore(redoStack.pop());
      } else if (action === 'delete') deleteSelection();
      else if (action === 'zoom-in') setZoom(zoom + ZOOM_STEP);
      else if (action === 'zoom-out') setZoom(zoom - ZOOM_STEP);
      else if (action === 'zoom-reset') setZoom(1);
      else if (action === 'zoom-fit') fitZoom();
      else if (action === 'tidy-layout') tidyLayout();
      else if (action === 'library') toggleSidebarPinned();
      else if (action === 'toggle-grid') {
        visitOnly.grid = null;
        state.canvas.showGrid = !state.canvas.showGrid;
        updateEditorGrid();
        persist();
        setStatus(`${state.canvas.showGrid ? 'Grid shown' : 'Grid hidden'} · snapping remains on`);
      }
    });
  });
  document.querySelector('[data-inspector-grid-toggle]').addEventListener('click', () => {
    gridToggle.click();
  });
  document.querySelector('[data-inspector-routing]')?.addEventListener('click', event => {
    const choice = event.target.closest('[data-routing]');
    if (!choice || (choice.dataset.routing === 'around') === routingEnabled()) return;
    checkpoint();
    visitOnly.routing = null;
    state.canvas.routeAroundNodes = choice.dataset.routing === 'around';
    persist();
    renderGraph();
    setStatus(routingEnabled()
      ? 'Connectors route around cards'
      : 'Connectors take the direct path');
  });
  document.querySelector('[data-inspector-crossings]')?.addEventListener('click', event => {
    const choice = event.target.closest('[data-crossings]');
    if (!choice || choice.dataset.crossings === crossingStyle()) return;
    checkpoint();
    state.canvas.crossings = choice.dataset.crossings;
    persist();
    renderGraph();
    setStatus(crossingStyle() === 'bridge' ? 'Separate wires cross with a bridge' : 'Crossings drawn plain');
  });
  // Frame lines: every frame's border at its kind's own width, or heavier
  // (render-metrics.json line_scales); saved with the project, so every
  // export agrees.
  document.querySelector('[data-inspector-frame-lines]')?.addEventListener('click', event => {
    const choice = event.target.closest('[data-frame-lines]');
    if (!choice || choice.dataset.frameLines === state.canvas.frameLines) return;
    checkpoint();
    state.canvas.frameLines = choice.dataset.frameLines;
    persist();
    renderGraph();
    setStatus(`Frame lines ${choice.dataset.frameLines}`);
  });
  const WHEEL_ZOOM_RATE = 0.0014;
  viewport.addEventListener('wheel', event => {
    if (!event.deltaY) return;
    // Scroll moves the map (the right-click menu): the wheel scrolls, and a
    // pinch or Ctrl with the wheel still zooms.
    if (layoutState.scrollPans && !event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    // The zoom follows how far the wheel turned, as a share of the zoom it
    // is at: a mouse's notch is about 15%, a trackpad's many small deltas add
    // up to the same, and a step means as much at 20% as at 200%.
    const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1);
    setZoom(zoom * Math.exp(-clamp(pixels, -200, 200) * WHEEL_ZOOM_RATE), event);
  }, {passive: false});
  const captureViewportPointer = pointerId => {
    try { viewport.setPointerCapture(pointerId); }
    catch (_) { /* Synthetic or transferred touch pointers may not be capturable. */ }
  };
  const releaseViewportPointer = pointerId => {
    try {
      if (viewport.hasPointerCapture(pointerId)) viewport.releasePointerCapture(pointerId);
    } catch (_) { /* The pointer may already have ended. */ }
  };
  const touchPoint = event => ({clientX: event.clientX, clientY: event.clientY});
  const touchDistance = (first, second) => Math.hypot(
    second.clientX - first.clientX,
    second.clientY - first.clientY,
  );
  const touchMidpoint = (first, second) => ({
    clientX: (first.clientX + second.clientX) / 2,
    clientY: (first.clientY + second.clientY) / 2,
  });
  const beginTouchPinch = () => {
    const points = [...activeTouchPoints.entries()].slice(0, 2);
    if (points.length < 2) return;
    const [[firstId, first], [secondId, second]] = points;
    const midpoint = touchMidpoint(first, second);
    const diagramRect = diagram.getBoundingClientRect();
    drag = null;
    clearConnection();
    marqueeSelection = null;
    alignmentGuides = [];
    viewportPan = null;
    leaveFitMode();
    touchGesture = {
      type: 'pinch',
      pointerIds: [firstId, secondId],
      startDistance: Math.max(1, touchDistance(first, second)),
      startZoom: zoom,
      canvasFocus: {
        x: (midpoint.clientX - diagramRect.left) / Math.max(zoom, 0.01),
        y: (midpoint.clientY - diagramRect.top) / Math.max(zoom, 0.01),
      },
    };
    viewport.dataset.panning = 'true';
    points.forEach(([pointerId]) => {
      try {
        if (diagram.hasPointerCapture(pointerId)) diagram.releasePointerCapture(pointerId);
      } catch (_) { /* The diagram may not own this touch pointer. */ }
      captureViewportPointer(pointerId);
    });
    renderGraph();
  };
  // Touch: one finger on anything not selected for editing pans the
  // drawing, and a tap that did not pan shows the flow of what it landed on
  // (19-canvas-pointer handleCanvasTap); a double tap selects it for
  // editing, and then one finger moves or shapes it. Pressed and held, a
  // finger opens the item's menu, as a right click does.
  const LONG_PRESS_MS = 550;
  let longPress = null;
  // A finger lifted after a tap or a hold, and the browser makes a click of
  // it where the finger was -- by then on the sheet a double tap opened, or
  // on the menu a hold opened: that click chooses nothing.
  let swallowClickUntil = 0;
  document.addEventListener('click', event => {
    // the page's own clicks (a panel's tab chosen for the reader) pass
    if (!event.isTrusted || performance.now() > swallowClickUntil) return;
    swallowClickUntil = 0;
    event.preventDefault();
    event.stopPropagation();
  }, true);
  // a lift that made no click leaves nothing for the next press to lose
  document.addEventListener('pointerdown', () => { swallowClickUntil = 0; }, true);
  const cancelLongPress = () => {
    if (longPress) clearTimeout(longPress.timer);
    longPress = null;
  };
  const touchEditable = target => {
    // a handle only a selection draws, or the selection's toolbar
    if (target.closest('[data-node-resize],[data-boundary-resize],[data-selection-toolbar],'
      + '[data-edge-end],[data-edge-bend],[data-edge-bend-ghost]')) return true;
    const nodeElement = target.closest('[data-graph-node]');
    // A card's connection points answer only once it is selected: they are
    // not drawn on the others, and a finger on one would start a wire.
    if (nodeElement) return isNodeSelected(nodeElement.dataset.nodeId);
    const edgeElement = target.closest('[data-edge-label],[data-graph-edge],[data-edge-hit]');
    if (edgeElement) {
      return selectedEdgeIds.has(edgeElement.dataset.edgeId || edgeElement.dataset.edgeLabel
        || edgeElement.dataset.edgeHit);
    }
    const boundaryElement = target.closest('[data-graph-boundary]');
    return Boolean(boundaryElement && isBoundarySelected(boundaryElement.dataset.boundaryId));
  };
  viewport.addEventListener('pointerdown', event => {
    if (phoneLayout() && !document.body.classList.contains('sidebar-collapsed')) {
      document.body.classList.add('sidebar-collapsed');
      updateSidebarTrigger();
    }
    if (event.pointerType === 'touch') {
      activeTouchPoints.set(event.pointerId, touchPoint(event));
      cancelLongPress();
      if (activeTouchPoints.size >= 2) {
        beginTouchPinch();
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      const held = {clientX: event.clientX, clientY: event.clientY, target: event.target};
      longPress = {
        pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY,
        timer: setTimeout(() => {
          longPress = null;
          if (activeTouchPoints.size !== 1) return;
          if (drag && !drag.moved && drag.type !== 'edge-bend') discardCheckpoint();
          abandonGesture();
          if (viewportPan) viewportPan.tap = null;
          contextPoint = toSvgPoint(held.clientX, held.clientY);
          swallowClickUntil = performance.now() + 1500;
          // beside the finger, not under it, where it can be read
          showContextMenu({...held, clientX: held.clientX + 16, clientY: held.clientY + 16});
        }, LONG_PRESS_MS),
      };
      if (touchEditable(event.target)) return;
    } else if (event.button !== 1) return;
    leaveFitMode();
    viewportPan = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop,
    };
    touchGesture = event.pointerType === 'touch' ? {type: 'pan'} : null;
    if (event.pointerType === 'touch') {
      viewportPan.tap = {clientX: event.clientX, clientY: event.clientY, target: event.target};
    }
    viewport.dataset.panning = 'true';
    captureViewportPointer(event.pointerId);
    event.preventDefault();
    event.stopPropagation();
  }, true);
  viewport.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch' && activeTouchPoints.has(event.pointerId)) {
      activeTouchPoints.set(event.pointerId, touchPoint(event));
      // a finger that travels is panning or dragging, not tapping or holding
      if (longPress?.pointerId === event.pointerId
          && Math.hypot(event.clientX - longPress.clientX, event.clientY - longPress.clientY) > 8) {
        cancelLongPress();
      }
      if (viewportPan?.tap && viewportPan.pointerId === event.pointerId
          && Math.hypot(event.clientX - viewportPan.tap.clientX, event.clientY - viewportPan.tap.clientY) > 8) {
        viewportPan.tap = null;
      }
      if (touchGesture?.type === 'pinch') {
        const [firstId, secondId] = touchGesture.pointerIds;
        const first = activeTouchPoints.get(firstId);
        const second = activeTouchPoints.get(secondId);
        if (first && second) {
          const midpoint = touchMidpoint(first, second);
          setZoom(
            touchGesture.startZoom
              * touchDistance(first, second) / touchGesture.startDistance,
            midpoint,
            {canvasFocus: touchGesture.canvasFocus},
          );
        }
        event.preventDefault();
        event.stopPropagation();
        return;
      }
    }
    if (!viewportPan || event.pointerId !== viewportPan.pointerId) return;
    viewport.scrollLeft = viewportPan.scrollLeft - (event.clientX - viewportPan.clientX);
    viewport.scrollTop = viewportPan.scrollTop - (event.clientY - viewportPan.clientY);
    event.preventDefault();
    event.stopPropagation();
  }, true);
  const finishViewportPan = event => {
    if (event.pointerType === 'touch') {
      if (longPress?.pointerId === event.pointerId) cancelLongPress();
      activeTouchPoints.delete(event.pointerId);
      releaseViewportPointer(event.pointerId);
      if (touchGesture?.type === 'pinch') {
        const remaining = [...activeTouchPoints.entries()][0];
        if (remaining) {
          viewportPan = {
            pointerId: remaining[0],
            clientX: remaining[1].clientX,
            clientY: remaining[1].clientY,
            scrollLeft: viewport.scrollLeft,
            scrollTop: viewport.scrollTop,
          };
          touchGesture = {type: 'pan'};
        } else {
          viewportPan = null;
          touchGesture = null;
          delete viewport.dataset.panning;
        }
        event.preventDefault();
        event.stopPropagation();
        return;
      }
    }
    if (!viewportPan || event.pointerId !== viewportPan.pointerId) return;
    const tap = event.type === 'pointerup' ? viewportPan.tap : null;
    viewportPan = null;
    touchGesture = null;
    delete viewport.dataset.panning;
    releaseViewportPointer(event.pointerId);
    event.preventDefault();
    event.stopPropagation();
    if (tap) {
      tap.timeStamp = event.timeStamp;
      swallowClickUntil = performance.now() + 700;
      handleCanvasTap(tap);
    }
  };
  viewport.addEventListener('pointerup', finishViewportPan, true);
  viewport.addEventListener('pointercancel', finishViewportPan, true);
  viewport.addEventListener('auxclick', event => {
    if (event.button === 1) event.preventDefault();
  });
