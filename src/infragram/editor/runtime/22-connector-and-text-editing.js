// @module 22-connector-and-text-editing: connector labels and styles, text and content fields
  const setEdgeLabel = (id, label) => {
    const edge = edgeById(id);
    if (!edge || itemIsLocked(edge)) return null;
    const value = String(label ?? '').trim();
    if (edge.label === value) return clone(edge);
    checkpoint();
    edge.label = value;
    renderGraph();
    persist();
    setStatus(`${value || 'Connector'} label updated`);
    return clone(edge);
  };
  const setEdgeWaypoints = (id, points = []) => {
    const edge = edgeById(id);
    if (!edge || itemIsLocked(edge)) return null;
    const clean = (Array.isArray(points) ? points : [])
      .filter(point => Number.isFinite(point?.x) && Number.isFinite(point?.y))
      .map(point => ({x: snap(point.x), y: snap(point.y)}));
    checkpoint();
    if (clean.length) edge.waypoints = clean;
    else delete edge.waypoints;
    renderGraph();
    persist();
    setStatus(clean.length
      ? `${edge.label || 'Connector'} routed through ${clean.length} point${clean.length === 1 ? '' : 's'}`
      : `${edge.label || 'Connector'} routing reset`);
    return clone(edge);
  };
  const setEdgeStyle = (id, style = {}) => {
    const edge = edgeById(id);
    if (!edge || itemIsLocked(edge)) return null;
    const kind = EDGE_KINDS.includes(style.kind) ? style.kind : String(edge.kind || 'solid');
    const direction = EDGE_DIRECTIONS.includes(style.direction)
      ? style.direction : edgeDirection(edge);
    const arrow = Object.hasOwn(EDGE_ARROWS, style.arrow) ? style.arrow : edgeArrow(edge);
    const corners = EDGE_CORNERS.includes(style.corners) ? style.corners : edgeCorners(edge);
    const stroke = typeof style.stroke === 'string' && style.stroke
      ? style.stroke : edge.style?.stroke;
    const width = Number.isFinite(Number(style.width)) && Number(style.width) > 0
      ? Number(style.width) : Number(edge.style?.width) || edge.width || 1.4;
    const unchanged = kind === String(edge.kind || 'solid')
      && direction === edgeDirection(edge)
      && arrow === edgeArrow(edge)
      && corners === edgeCorners(edge)
      && stroke === edge.style?.stroke
      && width === (Number(edge.style?.width) || edge.width || 1.4);
    if (unchanged) return clone(edge);
    checkpoint();
    if (kind !== String(edge.kind || 'solid')) {
      edge.kind = kind;
      edge.dash = null;
    }
    edge.direction = direction;
    edge.style = {...(edge.style || {}), arrow, corners, width, ...(stroke ? {stroke} : {})};
    renderGraph();
    persist();
    const arrows = direction === 'both' ? 'two-way' : direction === 'none' ? 'no arrows' : 'one-way';
    setStatus(`${edge.label || 'Connector'} · ${kind} · ${arrows} · ${arrow}`);
    return clone(edge);
  };

  const setEdgeTextStyle = (id, patch = {}) => {
    const edge = edgeById(id);
    if (!edge || itemIsLocked(edge)) return null;
    const clean = {};
    ['fontFamily', 'fontWeight'].forEach(key => {
      if (typeof patch[key] === 'string' && patch[key]) clean[key] = patch[key];
    });
    ['fontSize', 'opacity'].forEach(key => {
      if (Number.isFinite(Number(patch[key]))) clean[key] = Number(patch[key]);
    });
    if (typeof patch.textColor === 'string' && patch.textColor) clean.textColor = patch.textColor;
    if (!Object.keys(clean).length) return clone(edge);
    checkpoint();
    edge.style = {
      ...(edge.style || {}),
      textStyle: {...(edge.style?.textStyle || {}), ...clean},
    };
    renderGraph();
    persist();
    setStatus(`${edge.label || 'Connector'} label updated`);
    return clone(edge);
  };
  const setEdgeLabelPlacement = (id, placement) => {
    const edge = edgeById(id);
    if (!edge || itemIsLocked(edge)) return null;
    const dx = Number(placement?.dx);
    const dy = Number(placement?.dy);
    if (!Number.isFinite(dx) || !Number.isFinite(dy)) return null;
    if (edge.labelPlacement?.mode === 'manual'
        && Number(edge.labelPlacement.dx) === dx
        && Number(edge.labelPlacement.dy) === dy) return clone(edge);
    checkpoint();
    edge.labelPlacement = {mode: 'manual', dx, dy};
    delete edge.labelX;
    delete edge.labelY;
    renderGraph();
    persist();
    setStatus(`${edge.label || 'Connector'} label moved`);
    return clone(edge);
  };
  // Swap which end a connector starts from: the arrow turns round.
  const reverseEdge = (id, record = true) => {
    const edge = edgeById(id);
    if (!edge || itemIsLocked(edge)) return null;
    if (record) checkpoint();
    [edge.source, edge.target] = [edge.target, edge.source];
    [edge.sourcePort, edge.targetPort] = [edge.targetPort || 'auto', edge.sourcePort || 'auto'];
    if (Array.isArray(edge.waypoints)) edge.waypoints.reverse();
    persist();
    renderGraph();
    setStatus(`${edge.label || 'Connector'} reversed`);
    return clone(edge);
  };
  // Back to the automatic route and label spot.
  // A side chosen by hand is part of the route, like a bend or a label that
  // was placed: Reset route puts all of it back to automatic.
  const edgePortIsPinned = edge => ['sourcePort', 'targetPort']
    .some(key => edge?.[key] && edge[key] !== 'auto');
  const edgeRouteIsManual = edge => Boolean(edge && (edge.waypoints?.length || edge.labelPlacement
    || Number.isFinite(Number(edge.labelX)) || Number.isFinite(Number(edge.labelY))
    || edgePortIsPinned(edge)));

  const EDGE_SIDES = ['auto', 'top', 'right', 'bottom', 'left'];
  // Which side of its card an end leaves from. A node has one connection point
  // a side, so these are the choices; 'auto' lets the router pick.
  const setEdgePort = (id, end, side) => {
    const edge = edgeById(id);
    const key = end === 'source' ? 'sourcePort' : 'targetPort';
    if (!edge || itemIsLocked(edge) || !EDGE_SIDES.includes(side)) return null;
    if ((edge[key] || 'auto') === side) return clone(edge);
    checkpoint();
    edge[key] = side;
    persist();
    renderGraph();
    setStatus(side === 'auto'
      ? `${edge.label || 'Connector'} ${end === 'source' ? 'start' : 'end'} back to the automatic side`
      : `${edge.label || 'Connector'} ${end === 'source' ? 'leaves' : 'arrives'} ${side}`);
    return clone(edge);
  };

  // A bend that has come back into line with its neighbours is no bend at all.
  const dropStraightBends = edge => {
    const item = edgeGeometry().find(entry => entry.edge.id === edge.id);
    if (!item) return;
    connectorPath(item);
    const ends = [item.sourceSeat || item.sourcePoint, item.targetSeat || item.targetPoint];
    const kept = edgeWaypoints(edge).filter((point, index, points) => {
      const before = index === 0 ? ends[0] : points[index - 1];
      const after = index === points.length - 1 ? ends[1] : points[index + 1];
      const run = Math.hypot(after.x - before.x, after.y - before.y);
      if (!run) return true;
      const off = Math.abs((after.x - before.x) * (before.y - point.y)
        - (before.x - point.x) * (after.y - before.y)) / run;
      return off > 6;
    });
    if (kept.length === edgeWaypoints(edge).length) return;
    if (kept.length) edge.waypoints = kept;
    else delete edge.waypoints;
  };

  const removeEdgeBend = (id, index) => {
    const edge = edgeById(id);
    if (!edge || itemIsLocked(edge)) return null;
    const points = edgeWaypoints(edge);
    if (!points[index]) return null;
    checkpoint();
    const kept = points.filter((point, at) => at !== index);
    if (kept.length) edge.waypoints = kept;
    else delete edge.waypoints;
    persist();
    renderGraph();
    setStatus(kept.length
      ? `${edge.label || 'Connector'} bend removed`
      : `${edge.label || 'Connector'} route back to automatic`);
    return clone(edge);
  };

  const resetEdgeRoute = (id, record = true) => {
    const edge = edgeById(id);
    if (!edge || itemIsLocked(edge) || !edgeRouteIsManual(edge)) return null;
    if (record) checkpoint();
    delete edge.waypoints;
    delete edge.labelPlacement;
    delete edge.labelX;
    delete edge.labelY;
    edge.sourcePort = 'auto';
    edge.targetPort = 'auto';
    persist();
    renderGraph();
    setStatus(`${edge.label || 'Connector'} route reset`);
    return clone(edge);
  };
  const resetEdgeLabelPosition = id => {
    const edge = edgeById(id);
    if (!edge || itemIsLocked(edge)) return null;
    if (!edge.labelPlacement && !Number.isFinite(Number(edge.labelX))
        && !Number.isFinite(Number(edge.labelY))) return clone(edge);
    checkpoint();
    delete edge.labelPlacement;
    delete edge.labelX;
    delete edge.labelY;
    persist();
    renderGraph();
    setStatus(`${edge.label || 'Connector'} label back to automatic placement`);
    return clone(edge);
  };
  document.querySelectorAll('[data-edge-label-control]').forEach(control => {
    const apply = () => {
      if (selected?.type !== 'edge') return;
      setEdgeLabel(selected.id, control.value);
    };
    control.addEventListener('change', apply);
    control.addEventListener('keydown', event => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      apply();
    });
  });
  document.querySelectorAll('[data-edge-port-control]').forEach(control => {
    control.addEventListener('change', () => {
      if (selected?.type !== 'edge') return;
      setEdgePort(selected.id, control.dataset.edgePortControl === 'sourcePort' ? 'source' : 'target', control.value);
    });
  });
  document.querySelectorAll('[data-edge-style-control]').forEach(control => {
    control.addEventListener('change', () => {
      if (selected?.type !== 'edge') return;
      setEdgeStyle(selected.id, {[control.dataset.edgeStyleControl]: control.value});
    });
  });
  document.querySelectorAll('[data-edge-text-reset]').forEach(button => {
    button.addEventListener('click', () => {
      const edge = selected?.type === 'edge' ? selectedItem() : null;
      if (!edge || itemIsLocked(edge)) return;
      checkpoint();
      if (edge.style) delete edge.style.textStyle;
      renderGraph();
      persist();
      setStatus(`${edge.label || 'Connector'} label style reset`);
    });
  });
  document.querySelectorAll('[data-edge-label-field]').forEach(control => {
    const apply = () => {
      const edge = selected?.type === 'edge' ? selectedItem() : null;
      if (!edge) return;
      const key = control.dataset.edgeLabelField;
      const value = Number(control.value);
      if (!Number.isFinite(value)) return;
      setEdgeLabelPlacement(edge.id, {
        dx: key === 'dx' ? value : Number(edge.labelPlacement?.dx) || 0,
        dy: key === 'dy' ? value : Number(edge.labelPlacement?.dy) || 0,
      });
    };
    control.addEventListener('change', apply);
    control.addEventListener('keydown', event => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      apply();
    });
  });
  document.querySelectorAll('[data-edge-label-reset]').forEach(button => {
    button.addEventListener('click', () => {
      if (selected?.type === 'edge') resetEdgeLabelPosition(selected.id);
    });
  });
  document.querySelectorAll('[data-text-control]').forEach(control => {
    const apply = () => {
      const item = selectedItem();
      if (!item || itemIsLocked(item)) return;
      const key = control.dataset.textControl;
      if (selected?.type === 'edge') {
        if (key === 'textAlign') return;
        setEdgeTextStyle(selected.id, {[key]: control.value});
        return;
      }
      const numeric = ['fontSize', 'fontWeight', 'opacity'].includes(key);
      const value = numeric ? Number(control.value) : control.value;
      if (numeric && !Number.isFinite(value)) return;
      checkpoint();
      item.textStyle = {...(item.textStyle || {}), [key]: value};
      persist();
      renderGraph();
      setStatus(`${item.name} text updated`);
    };
    control.addEventListener('change', apply);
  });
  document.querySelectorAll('[data-content-control]').forEach(control => {
    const apply = () => {
      const item = selectedItem();
      const key = control.dataset.contentControl;
      if (!item || selected?.type === 'edge' || itemIsLocked(item)) return;
      if (key === 'detail' && selected?.type !== 'node') return;
      // a description keeps its lines, each trimmed, the blank ones dropped
      const value = control.value.split('\n').map(line => line.trim()).filter(Boolean).join('\n');
      if (key === 'name' && !value) {
        control.value = item.name || '';
        setStatus('A component name cannot be empty');
        return;
      }
      if (String(item[key] || '') === value) return;
      checkpoint();
      // a panel grows to its new text (and a card given a second line becomes one)
      const before = selected?.type === 'node' ? snapshotBoxes() : null;
      const wasPanel = Boolean(before) && isPanel(item);
      item[key] = value;
      if (before) refitBox(item, wasPanel, before, {grow: true});
      persist();
      renderGraph();
      setStatus(`${item.name} ${key === 'name' ? 'name' : 'description'} updated`);
    };
    control.addEventListener('change', apply);
    // In a description, Shift+Enter starts a line; a touch keyboard has no
    // Shift, so there Return does, and leaving the field applies it.
    control.addEventListener('keydown', event => {
      if (event.key !== 'Enter') return;
      if (control.tagName === 'TEXTAREA' && (event.shiftKey || !matchMedia('(pointer: fine)').matches)) return;
      event.preventDefault();
      apply();
    });
  });
