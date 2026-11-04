// @module 07-hit-testing: frame nesting, hit tests, drop targets and the marquee
  const boundaryDepth = boundary => {
    let depth = 0;
    let current = boundary;
    while (current?.parentId) {
      depth += 1;
      current = boundaryById(current.parentId);
    }
    return depth;
  };
  const isBoundaryDescendant = (id, ancestorId) => {
    let current = boundaryById(id);
    while (current) {
      if (current.id === ancestorId) return true;
      current = current.parentId ? boundaryById(current.parentId) : null;
    }
    return false;
  };
  const topLevelArrangeObjects = () => {
    const frames = selectedBoundaries();
    return selectedObjects().filter(object => {
      const frame = boundaryById(object.id);
      if (frame) {
        return !frames.some(candidate => (
          candidate.id !== frame.id && isBoundaryDescendant(frame.id, candidate.id)
        ));
      }
      return !frames.some(candidate => (
        object.boundaryId && isBoundaryDescendant(object.boundaryId, candidate.id)
      ));
    });
  };
  const boundaryContainsPoint = (boundary, point, inset = 0) => (
    point.x >= boundary.x + inset && point.x <= boundary.x + boundary.width - inset
    && point.y >= boundary.y + inset && point.y <= boundary.y + boundary.height - inset
  );
  const deepestBoundaryAt = (point, excludeId = null) => state.boundaries
    .filter(boundary => boundary.id !== excludeId
      && isLayerVisible(boundary.layerId)
      && !isBoundaryDescendant(boundary.id, excludeId)
      && boundaryContainsPoint(boundary, point, Math.min(boundary.pad || 0, 16)))
    .sort((a, b) => boundaryDepth(b) - boundaryDepth(a))[0] || null;
  const boundaryHitAt = point => state.boundaries
    .filter(boundary => boundaryIsVisible(boundary) && boundaryContainsPoint(boundary, point))
    .sort((a, b) => boundaryDepth(b) - boundaryDepth(a)
      || Number(b.order) - Number(a.order))[0] || null;
  const nodeHitAt = point => state.nodes
    .filter(node => nodeIsVisible(node)
      && point.x >= node.x && point.x <= node.x + node.width
      && point.y >= node.y && point.y <= node.y + node.height)
    .sort((a, b) => Number(b.order) - Number(a.order))[0] || null;
  const updateDropTarget = (object, excludeId = null, suppress = false) => {
    if (!object || suppress) {
      dropTargetId = null;
      return null;
    }
    const target = deepestBoundaryAt({
      x: object.x + object.width / 2,
      y: object.y + object.height / 2,
    }, excludeId);
    dropTargetId = target?.id || null;
    return target;
  };
  const clampIntoBoundary = (object, boundary) => {
    if (!object || !boundary) return;
    const pad = boundary.pad || 16;
    const nextX = clamp(object.x, boundary.x + pad, boundary.x + boundary.width - pad - object.width);
    const nextY = clamp(object.y, boundary.y + pad, boundary.y + boundary.height - pad - object.height);
    if (boundaryById(object.id)) translateObject(object, nextX, nextY);
    else {
      object.x = nextX;
      object.y = nextY;
    }
  };
  const finishMarquee = () => {
    if (!marqueeSelection) return;
    const selection = marqueeSelection;
    marqueeSelection = null;
    const left = Math.min(selection.start.x, selection.current.x);
    const top = Math.min(selection.start.y, selection.current.y);
    const right = Math.max(selection.start.x, selection.current.x);
    const bottom = Math.max(selection.start.y, selection.current.y);
    const matches = object => {
      const bounds = objectBounds(object);
      return selection.intersect
        ? bounds.right >= left && bounds.left <= right && bounds.bottom >= top && bounds.top <= bottom
        : bounds.left >= left && bounds.right <= right && bounds.top >= top && bounds.bottom <= bottom;
    };
    clearSelection();
    selectedNodeIds = new Set(state.nodes.filter(node => nodeIsVisible(node) && matches(node)).map(node => node.id));
    selectedBoundaryIds = new Set(state.boundaries.filter(boundary => boundaryIsVisible(boundary) && matches(boundary)).map(boundary => boundary.id));
    // A wire is caught by what it joins: both of its components inside the
    // marquee means the wire is inside it too.
    selectedEdgeIds = new Set(state.edges
      .filter(edge => selectedNodeIds.has(edge.source) && selectedNodeIds.has(edge.target))
      .map(edge => edge.id));
    if (selectedNodeIds.size) selected = {type: 'node', id: [...selectedNodeIds].at(-1)};
    else if (selectedBoundaryIds.size) selected = {type: 'boundary', id: [...selectedBoundaryIds].at(-1)};
    else if (selectedEdgeIds.size) selected = {type: 'edge', id: [...selectedEdgeIds].at(-1)};
    const caught = selectedObjects().length + selectedEdgeIds.size;
    setStatus(`${caught} item${caught === 1 ? '' : 's'} selected`, {show: false});
  };
