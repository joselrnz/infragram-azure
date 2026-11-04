// @module 21-arrange: exact geometry, z-order, grouping, detaching and alignment
  const applyExactGeometry = input => {
    const item = selectedItem();
    const field = input.dataset.exactField;
    const value = Number(input.value);
    if (!item || selected?.type === 'edge' || itemIsLocked(item) || !Number.isFinite(value)) return;
    let next = value;
    const floor = selected?.type === 'node' && isPanel(item) ? panelFloor(item) : {width: 0, height: 0};
    if (field === 'x') next = clamp(value, 0, state.canvas.width - item.width);
    else if (field === 'y') next = clamp(value, 0, state.canvas.height - item.height);
    else if (field === 'width') {
      const contained = selected?.type === 'boundary' ? [
        ...state.boundaries.filter(child => child.parentId === item.id)
          .map(child => child.x + child.width + (item.pad || 0) - item.x),
        ...state.nodes.filter(node => node.boundaryId === item.id)
          .map(node => node.x + node.width + (item.pad || 0) - item.x),
      ] : [];
      next = clamp(value, Math.max(item.minWidth || 32, floor.width, ...contained), state.canvas.width - item.x);
    } else if (field === 'height') {
      const contained = selected?.type === 'boundary' ? [
        ...state.boundaries.filter(child => child.parentId === item.id)
          .map(child => child.y + child.height + (item.pad || 0) - item.y),
        ...state.nodes.filter(node => node.boundaryId === item.id)
          .map(node => node.y + node.height + (item.pad || 0) - item.y),
      ] : [];
      next = clamp(value, Math.max(item.minHeight || 32, floor.height, ...contained), state.canvas.height - item.y);
    }
    if (item[field] === next) return;
    checkpoint();
    if (field === 'x') translateObject(item, next, item.y);
    else if (field === 'y') translateObject(item, item.x, next);
    else item[field] = next;
    persist();
    renderGraph();
    setStatus(`${item.name} ${field} set to ${next}`);
  };
  document.querySelectorAll('[data-exact-field]').forEach(input => {
    input.addEventListener('change', () => applyExactGeometry(input));
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        applyExactGeometry(input);
      }
    });
  });
  const translateObject = (object, nextX, nextY) => {
    const dx = nextX - object.x;
    const dy = nextY - object.y;
    object.x = nextX;
    object.y = nextY;
    if (!boundaryById(object.id)) return;
    state.boundaries.filter(item => item.id !== object.id && isBoundaryDescendant(item.id, object.id))
      .forEach(item => { item.x += dx; item.y += dy; });
    state.nodes.filter(node => node.boundaryId && isBoundaryDescendant(node.boundaryId, object.id))
      .forEach(node => { node.x += dx; node.y += dy; });
  };
  const applyZOrder = action => {
    const reorder = (items, chosen) => {
      if (!chosen.length) return;
      const ordered = items.slice().sort((a, b) => Number(a.order) - Number(b.order));
      const selectedIds = new Set(chosen.map(item => item.id));
      const selectedItems = ordered.filter(item => selectedIds.has(item.id));
      const rest = ordered.filter(item => !selectedIds.has(item.id));
      let next;
      if (action === 'to-front') next = [...rest, ...selectedItems];
      else if (action === 'to-back') next = [...selectedItems, ...rest];
      else {
        next = ordered.slice();
        const direction = action === 'forward' ? 1 : -1;
        const indexes = selectedItems.map(item => next.findIndex(candidate => candidate.id === item.id));
        const scan = direction > 0 ? indexes.slice().reverse() : indexes;
        scan.forEach(index => {
          const target = index + direction;
          if (target >= 0 && target < next.length && !selectedIds.has(next[target].id)) {
            [next[index], next[target]] = [next[target], next[index]];
          }
        });
      }
      next.forEach((item, index) => { item.order = index; });
    };
    const chosenNodes = selectedNodes().filter(node => !itemIsLocked(node));
    const nodeGroups = new Map();
    chosenNodes.forEach(node => {
      const key = `${node.layerId || ''}:${node.boundaryId || ''}`;
      if (!nodeGroups.has(key)) nodeGroups.set(key, []);
      nodeGroups.get(key).push(node);
    });
    nodeGroups.forEach((chosen, key) => reorder(
      state.nodes.filter(node => `${node.layerId || ''}:${node.boundaryId || ''}` === key), chosen,
    ));
    const chosenFrames = selectedBoundaries().filter(boundary => !itemIsLocked(boundary));
    const frameGroups = new Map();
    chosenFrames.forEach(boundary => {
      const key = `${boundary.layerId || ''}:${boundary.parentId || ''}:${boundaryDepth(boundary)}`;
      if (!frameGroups.has(key)) frameGroups.set(key, []);
      frameGroups.get(key).push(boundary);
    });
    frameGroups.forEach((chosen, key) => reorder(
      state.boundaries.filter(boundary => `${boundary.layerId || ''}:${boundary.parentId || ''}:${boundaryDepth(boundary)}` === key), chosen,
    ));
  };
  const groupSelection = () => {
    const objects = selectedObjects().filter(object => !itemIsLocked(object));
    if (objects.length < 2) return;
    const bounds = selectionBounds();
    const pad = 20;
    const boundary = {
      id: uniqueId('group'), parentId: null, name: 'Group', kind: 'group', userGroup: true,
      x: snap(Math.max(0, bounds.left - pad)), y: snap(Math.max(0, bounds.top - pad - 12)),
      width: snap(bounds.right - bounds.left + pad * 2),
      height: snap(bounds.bottom - bounds.top + pad * 2 + 12),
      componentProvider: state.provider, componentQualifiedId: null, frameGroup: 'generic',
      layerId: objects.every(object => object.layerId === objects[0].layerId)
        ? objects[0].layerId : ensureProviderLayer(state.provider),
      order: state.boundaries.length, minWidth: 160, minHeight: 104, pad,
      stroke: '#727272', fill: '#2c2e330d', dash: EDGE_DASHES.dashed,
      strokeWidth: 1.0, radius: 4, attributes: {},
    };
    // A frame drawn around a selection is a generic group frame and takes
    // the theme's look for one, the same as a frame placed from the gallery.
    Object.assign(boundary, clone(state.boundaryStyles?.group || {}));
    const containing = deepestBoundaryAt({x: boundary.x + boundary.width / 2, y: boundary.y + boundary.height / 2});
    boundary.parentId = containing?.id || null;
    state.boundaries.push(boundary);
    selectedNodes().forEach(node => { node.boundaryId = boundary.id; });
    selectedBoundaries().filter(item => item.id !== boundary.id).forEach(item => { item.parentId = boundary.id; });
    selectBoundary(boundary.id);
  };
  const ungroupSelection = () => {
    const group = selected?.type === 'boundary' ? boundaryById(selected.id) : null;
    if (!group?.userGroup || itemIsLocked(group)) return;
    const nodes = state.nodes.filter(node => node.boundaryId === group.id);
    const frames = state.boundaries.filter(boundary => boundary.parentId === group.id);
    nodes.forEach(node => { node.boundaryId = group.parentId || null; });
    frames.forEach(boundary => { boundary.parentId = group.parentId || null; });
    state.boundaries = state.boundaries.filter(boundary => boundary.id !== group.id);
    clearSelection();
    nodes.forEach(node => selectedNodeIds.add(node.id));
    frames.forEach(boundary => selectedBoundaryIds.add(boundary.id));
    if (nodes.length) selected = {type: 'node', id: nodes.at(-1).id};
    else if (frames.length) selected = {type: 'boundary', id: frames.at(-1).id};
  };
  const detachSelection = () => {
    selectedNodes().filter(node => !itemIsLocked(node) && node.boundaryId).forEach(node => {
      node.boundaryId = boundaryById(node.boundaryId)?.parentId || null;
    });
    selectedBoundaries().filter(boundary => !itemIsLocked(boundary) && boundary.parentId).forEach(boundary => {
      boundary.parentId = boundaryById(boundary.parentId)?.parentId || null;
    });
  };
  const shrinkFrameToFit = () => {
    const frame = selected?.type === 'boundary' ? boundaryById(selected.id) : null;
    if (!frame || itemIsLocked(frame)) return;
    const children = [
      ...state.nodes.filter(node => node.boundaryId === frame.id),
      ...state.boundaries.filter(boundary => boundary.parentId === frame.id),
    ];
    if (!children.length) return;
    const pad = frame.pad || 20;
    const left = Math.min(...children.map(child => child.x));
    const top = Math.min(...children.map(child => child.y));
    const right = Math.max(...children.map(child => child.x + child.width));
    const bottom = Math.max(...children.map(child => child.y + child.height));
    frame.x = snap(Math.max(0, left - pad));
    frame.y = snap(Math.max(0, top - pad - 12));
    frame.width = snap(Math.max(frame.minWidth || 160, right - frame.x + pad));
    frame.height = snap(Math.max(frame.minHeight || 104, bottom - frame.y + pad));
  };
  // Hand the diagram back to the router.
  //
  // Every wire can already be un-pinned one at a time (Reset route), but once
  // cards and frames have been dragged there was no way back: the automatic
  // layout was gone the moment the first thing moved. It is not gone -- the
  // page carries it. `generatedState` is exactly what the renderer laid out
  // before anybody touched it, so tidying is a restore rather than a second
  // implementation of the layout, and it cannot disagree with the static
  // picture the way a reimplementation would drift.
  //
  // What a reader made is kept: names, details, styles, wires, the frames
  // they added. Only geometry goes back -- position, size, and the pinned
  // corners of a wire, which describe a layout that no longer exists.
  const tidyLayout = () => {
    const nodes = state.nodes.filter(node => laidOutNodes.has(node.id) && !node.locked);
    const frames = state.boundaries.filter(
      boundary => laidOutFrames.has(boundary.id) && !boundary.locked);
    if (!nodes.length && !frames.length) {
      setStatus('Nothing to tidy: this diagram has no automatic layout to return to');
      return;
    }
    checkpoint();
    nodes.forEach(node => {
      const laid = laidOutNodes.get(node.id);
      node.x = laid.x;
      node.y = laid.y;
      node.width = laid.width;
      node.height = laid.height;
      delete node.cardSize;
    });
    frames.forEach(frame => {
      const laid = laidOutFrames.get(frame.id);
      frame.x = laid.x;
      frame.y = laid.y;
      frame.width = laid.width;
      frame.height = laid.height;
    });
    // A pinned wire describes corners in the layout it was bent in. Kept, it
    // would reach for coordinates nothing sits at any more.
    let unpinned = 0;
    state.edges.forEach(edge => {
      if (edge.waypoints && edge.waypoints.length) {
        delete edge.waypoints;
        unpinned += 1;
      }
    });
    persist();
    renderGraph();
    const moved = nodes.length + frames.length;
    setStatus(`Tidied ${moved} item${moved === 1 ? '' : 's'} back to the automatic layout`
      + (unpinned ? `, ${unpinned} wire${unpinned === 1 ? '' : 's'} un-pinned` : ''));
  };

  const arrangeSelection = action => {
    const objects = topLevelArrangeObjects().filter(object => !itemIsLocked(object));
    const minimum = action.startsWith('distribute-') ? 3 : 2;
    const standalone = ['to-front', 'to-back', 'forward', 'backward', 'rotate-90',
      'flip-horizontal', 'flip-vertical', 'group', 'ungroup', 'detach', 'shrink-fit', 'lock'];
    if (!standalone.includes(action) && objects.length < minimum) return;
    if (!selectedObjects().length) return;
    if (action === 'group' && selectedObjects().length < 2) return;
    checkpoint();
    if (['to-front', 'to-back', 'forward', 'backward'].includes(action)) applyZOrder(action);
    else if (action === 'group') groupSelection();
    else if (action === 'ungroup') ungroupSelection();
    else if (action === 'detach') detachSelection();
    else if (action === 'shrink-fit') shrinkFrameToFit();
    else if (action === 'lock') {
      const shouldLock = selectedObjects().some(object => !object.locked);
      selectedObjects().forEach(object => { object.locked = shouldLock; });
    } else if (action === 'rotate-90') {
      selectedNodes().forEach(node => { node.angle = ((Number(node.angle) || 0) + 90) % 360; });
    } else if (action === 'flip-horizontal') {
      selectedNodes().forEach(node => { node.flipX = !node.flipX; });
    } else if (action === 'flip-vertical') {
      selectedNodes().forEach(node => { node.flipY = !node.flipY; });
    }
    if (standalone.includes(action)) {
      persist();
      renderGraph();
      setStatus(action === 'lock'
        ? `Selection ${selectedObjects().every(object => object.locked) ? 'locked' : 'unlocked'}`
        : `${selectedObjects().length} item${selectedObjects().length === 1 ? '' : 's'} updated`);
      return;
    }
    const left = Math.min(...objects.map(object => object.x));
    const right = Math.max(...objects.map(object => object.x + object.width));
    const top = Math.min(...objects.map(object => object.y));
    const bottom = Math.max(...objects.map(object => object.y + object.height));
    if (action === 'align-left') objects.forEach(object => translateObject(object, left, object.y));
    else if (action === 'align-center') objects.forEach(object => translateObject(object, (left + right - object.width) / 2, object.y));
    else if (action === 'align-right') objects.forEach(object => translateObject(object, right - object.width, object.y));
    else if (action === 'align-top') objects.forEach(object => translateObject(object, object.x, top));
    else if (action === 'align-middle') objects.forEach(object => translateObject(object, object.x, (top + bottom - object.height) / 2));
    else if (action === 'align-bottom') objects.forEach(object => translateObject(object, object.x, bottom - object.height));
    else if (action === 'distribute-horizontal') {
      const ordered = objects.slice().sort((a, b) => a.x - b.x);
      const width = ordered.reduce((sum, object) => sum + object.width, 0);
      const gap = (right - left - width) / (ordered.length - 1);
      let cursor = left;
      ordered.forEach(object => { translateObject(object, cursor, object.y); cursor += object.width + gap; });
    } else if (action === 'distribute-vertical') {
      const ordered = objects.slice().sort((a, b) => a.y - b.y);
      const height = ordered.reduce((sum, object) => sum + object.height, 0);
      const gap = (bottom - top - height) / (ordered.length - 1);
      let cursor = top;
      ordered.forEach(object => { translateObject(object, object.x, cursor); cursor += object.height + gap; });
    }
    objects.forEach(object => {
      translateObject(
        object,
        clamp(Math.round(object.x), 0, state.canvas.width - object.width),
        clamp(Math.round(object.y), 0, state.canvas.height - object.height),
      );
    });
    persist();
    renderGraph();
    const frameCount = objects.filter(object => boundaryById(object.id)).length;
    const objectLabel = frameCount === objects.length ? 'frames'
      : frameCount ? 'items' : 'components';
    setStatus(`${objects.length} ${objectLabel} arranged`);
  };
  document.querySelectorAll('[data-arrange-action]').forEach(button => {
    button.addEventListener('click', () => arrangeSelection(button.dataset.arrangeAction));
  });
  document.querySelectorAll('[data-selection-action]').forEach(button => {
    button.addEventListener('click', () => {
      const action = button.dataset.selectionAction;
      if (action === 'delete') deleteSelection();
      else if (action === 'duplicate') duplicateSelection();
      else if (action === 'display-icon' || action === 'display-card') setNodeDisplayMode(action.slice(8));
      else if (action === 'edge-reverse') forEachSelectedEdge(reverseEdge);
      else if (action === 'edge-reset-route') forEachSelectedEdge(resetEdgeRoute);
      else if (action === 'edge-edit-label') openTextEditor(selectedItem(), 'edge');
      else arrangeSelection(action);
    });
  });
