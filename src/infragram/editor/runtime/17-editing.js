// @module 17-editing: adding components, frames and starter stacks; connecting; deleting
  const componentPayload = component => {
    const definition = componentDefinitions.get(component.dataset.componentQualifiedId) || {};
    return {
      id: component.dataset.componentId,
      qualifiedId: component.dataset.componentQualifiedId,
      provider: component.dataset.componentProvider,
      name: definition.name || component.getAttribute('aria-label').replace(/^Select /, ''),
      detail: definition.subtitle || '',
      category: component.closest('[data-category-id]').dataset.categoryId,
      iconUri: component.querySelector('img').src,
      componentKind: component.dataset.componentKind || 'node',
      boundaryKind: component.dataset.boundaryKind || '',
      frameGroup: definition.frameGroup || '',
      hierarchyLevel: definition.hierarchyLevel || 0,
      tier: definition.tier || 'service',
      defaultDisplay: definition.defaultDisplay || '',
      defaultSize: clone(definition.defaultSize || {}),
      boundaryStyle: clone(definition.boundaryStyle || {}),
    };
  };

  // How a component draws unless a node says otherwise. The answer comes
  // from the library payload, where the Python side resolved the display
  // rules (assets/catalog/display-defaults.json) for every
  // component; the tier test is the fallback for a page built before the
  // payload carried it. Same answer as display_of() gives a document.
  const defaultDisplayMode = item => (
    item.defaultDisplay === 'icon' || item.defaultDisplay === 'card'
      ? item.defaultDisplay
      : (item.tier === 'resource' ? 'icon' : 'card'));

  const addNode = (component, point, record = true) => {
    if (record) checkpoint();
    const displayMode = defaultDisplayMode(component);
    const caption = {name: component.name || component.id, detail: component.detail || ''};
    const width = displayMode === 'icon' ? iconNodeWidth(caption) : 208;
    const height = displayMode === 'icon' ? ICON_NODE.height : CARD_HEIGHT;
    ensureCanvasExtent({
      right: point.x + width / 2 + CANVAS_MARGIN,
      bottom: point.y + height / 2 + CANVAS_MARGIN,
    });
    const container = deepestBoundaryAt(point);
    const componentProvider = component.provider || state.provider;
    const layerProvider = componentProvider === 'infragram'
      ? state.provider : componentProvider;
    const node = {
      id: uniqueId(component.id), componentId: component.id,
      componentProvider,
      componentQualifiedId: component.qualifiedId || `${componentProvider}:${component.id}`,
      name: component.name || component.id, detail: component.detail || '',
      category: component.category || 'custom', type: 'service',
      iconUri: component.iconUri || '', focal: false, width, height, displayMode,
      tier: component.tier || 'service', defaultDisplay: displayMode,
      boundaryId: container?.id || null,
      layerId: ensureProviderLayer(layerProvider),
      order: state.nodes.reduce((maximum, item) => Math.max(maximum, Number(item.order) || 0), -1) + 1,
      attributes: {},
      x: snap(clamp(point.x - width / 2, 0, state.canvas.width - width)),
      y: snap(clamp(point.y - height / 2, 0, state.canvas.height - height)),
    };
    state.nodes.push(node);
    selectNode(node.id);
    persist();
    renderGraph();
    setStatus(`${node.name} added`);
    return node.id;
  };

  const addBoundary = (component, point, record = true, forceRoot = false) => {
    if (record) checkpoint();
    const kind = component.boundaryKind || component.kind || 'group';
    const sourceStyle = Object.keys(component.boundaryStyle || {}).length
      ? component.boundaryStyle
      : (state.boundaryStyles[kind] || state.boundaryStyles.group || {});
    const dimensions = Number(component.defaultSize?.width) && Number(component.defaultSize?.height)
      ? component.defaultSize
      : ['cloud', 'region', 'vpc'].includes(kind)
        ? {width: 400, height: 280}
        : ['subnet-public', 'subnet-private'].includes(kind)
          ? {width: 256, height: 144}
          : {width: 320, height: 200};
    ensureCanvasExtent({
      right: point.x + dimensions.width / 2 + CANVAS_MARGIN,
      bottom: point.y + dimensions.height / 2 + CANVAS_MARGIN,
    });
    const container = forceRoot ? null : deepestBoundaryAt(point);
    const pad = sourceStyle.pad || 24;
    const available = container
      ? {
          left: container.x + (container.pad || pad),
          top: container.y + (container.pad || pad),
          right: container.x + container.width - (container.pad || pad),
          bottom: container.y + container.height - (container.pad || pad),
        }
      : {left: 0, top: 0, right: state.canvas.width, bottom: state.canvas.height};
    const width = snap(Math.min(dimensions.width, Math.max(160, available.right - available.left)));
    const height = snap(Math.min(dimensions.height, Math.max(104, available.bottom - available.top)));
    const x = snap(clamp(point.x - width / 2, available.left, available.right - width));
    const y = snap(clamp(point.y - height / 2, available.top, available.bottom - height));
    const providerHints = [
      ['-aws-', 'aws'], ['-azure-', 'azure'], ['-gcp-', 'gcp'],
      ['-do-', 'digitalocean'], ['-oci-', 'oracle'], ['-ibm-', 'ibm'],
      ['-alibaba-', 'alibaba'], ['-kubernetes-', 'kubernetes'],
      ['-hetzner-', 'hetzner'],
    ];
    // A frame from a library's gallery belongs to that library: its frame
    // group names it, for every library, where the id hints above only cover
    // the ids that spell theirs out (an AWS Region frame's does not). The
    // core frames' generic gallery is no library of its own.
    const galleryProvider = component.frameGroup && component.frameGroup !== 'generic'
      && providerById.has(component.frameGroup) ? component.frameGroup : '';
    const hintedProvider = galleryProvider
      || providerHints.find(([token]) => String(component.id).includes(token))?.[1];
    const componentProvider = component.provider === 'infragram'
      ? (hintedProvider || state.provider)
      : (component.provider || state.provider);
    const boundary = {
      ...clone(sourceStyle),
      id: uniqueId(component.id || kind), parentId: container?.id || null,
      name: component.name || kind, kind, x, y, width, height,
      componentProvider,
      componentQualifiedId: component.qualifiedId || null,
      frameGroup: component.frameGroup || '',
      editableFoundation: Boolean(component.editableFoundation),
      hierarchyLevel: component.hierarchyLevel || 0,
      layerId: ensureProviderLayer(componentProvider),
      order: state.boundaries.reduce((maximum, item) => Math.max(maximum, Number(item.order) || 0), -1) + 1,
      minWidth: 160, minHeight: 104, pad, attributes: {},
    };
    state.boundaries.push(boundary);
    selectBoundary(boundary.id);
    persist();
    renderGraph();
    setStatus(`${boundary.name} frame added`);
    return boundary.id;
  };

  const addComponent = (component, point) => component.componentKind === 'boundary'
    ? addBoundary(component, point) : addNode(component, point);

  const definitionPayload = definition => ({
    id: definition.serviceId,
    qualifiedId: definition.qualifiedId,
    provider: definition.provider,
    name: definition.name,
    detail: definition.subtitle,
    category: definition.categoryId,
    iconUri: definition.iconUri,
    componentKind: definition.componentKind,
    boundaryKind: definition.boundaryKind,
    frameGroup: definition.frameGroup || '',
    hierarchyLevel: definition.hierarchyLevel || 0,
    defaultSize: clone(definition.defaultSize || {}),
    boundaryStyle: clone(definition.boundaryStyle || {}),
  });
  const addFramePreset = (preset, dropPoint = null) => {
    const definition = (libraryCatalog.framePresets || []).find(item => item.id === preset);
    if (!definition) return;
    const components = definition.componentIds.map(serviceId => (
      libraryCatalog.components.find(
        item => item.serviceId === serviceId && item.frameGroup === definition.group,
      )
    )).filter(Boolean);
    if (!components.length) {
      setStatus(`${definition.label} frames are unavailable in this library`);
      return;
    }
    const sizes = components.map((component, index) => ({
      width: Math.max(160, Number(definition.frameSizes?.[index]?.width)
        || Number(component.defaultSize?.width) || 320),
      height: Math.max(104, Number(definition.frameSizes?.[index]?.height)
        || Number(component.defaultSize?.height) || 200),
    }));
    const detached = definition.layout === 'detached';
    const placedTree = Array.isArray(definition.framePlacements)
      && definition.framePlacements.length === components.length;
    if (!detached && !placedTree) {
      for (let index = sizes.length - 2; index >= 0; index -= 1) {
        const pad = Number(components[index].boundaryStyle?.pad) || 24;
        sizes[index] = {
          width: snap(Math.max(sizes[index].width, sizes[index + 1].width + pad * 2)),
          height: snap(Math.max(sizes[index].height, sizes[index + 1].height + pad * 2)),
        };
      }
    }
    checkpoint();
    const center = dropPoint || {x: state.canvas.width / 2, y: state.canvas.height / 2};
    const columns = Math.min(3, components.length);
    const gap = 48;
    const cellWidth = Math.max(...sizes.map(size => size.width)) + gap;
    const cellHeight = Math.max(...sizes.map(size => size.height)) + gap;
    const rows = Math.ceil(components.length / columns);
    const layoutLeft = center.x - (columns * cellWidth - gap) / 2;
    const layoutTop = center.y - (rows * cellHeight - gap) / 2;
    const addedIds = [];
    components.forEach((component, index) => {
      const point = detached ? {
        x: layoutLeft + (index % columns) * cellWidth + sizes[index].width / 2,
        y: layoutTop + Math.floor(index / columns) * cellHeight + sizes[index].height / 2,
      } : center;
      addedIds.push(addBoundary({
        ...definitionPayload(component),
        provider: definition.group,
        editableFoundation: Boolean(definition.editableFoundation),
        defaultSize: sizes[index],
      }, point, false, detached || placedTree || index === 0));
    });
    if (placedTree && addedIds.length) {
      const outerLeft = snap(center.x - sizes[0].width / 2);
      const outerTop = snap(center.y - sizes[0].height / 2);
      definition.framePlacements.forEach((placement, index) => {
        const frame = boundaryById(addedIds[index]);
        if (!frame) return;
        frame.x = snap(outerLeft + Number(placement.x || 0));
        frame.y = snap(outerTop + Number(placement.y || 0));
        frame.width = sizes[index].width;
        frame.height = sizes[index].height;
        frame.parentId = Number.isInteger(placement.parentIndex)
          ? addedIds[placement.parentIndex] || null : null;
      });
      ensureCanvasExtent({
        right: outerLeft + sizes[0].width + CANVAS_MARGIN,
        bottom: outerTop + sizes[0].height + CANVAS_MARGIN,
      });
    }
    const addedNodeIds = [];
    (definition.nodes || []).forEach(placement => {
      const component = libraryCatalog.components.find(
        item => item.qualifiedId === placement.qualifiedId,
      );
      const hasParent = Number.isInteger(placement.parentFrameIndex);
      const parent = hasParent ? boundaryById(addedIds[placement.parentFrameIndex]) : null;
      const anchor = parent || boundaryById(addedIds[0]);
      if (!component || !anchor) return;
      const payload = definitionPayload(component);
      if (placement.name) payload.name = placement.name;
      if (placement.detail) payload.detail = placement.detail;
      const nodeId = addNode(payload, {
        x: anchor.x + Number(placement.x ?? anchor.width / 2),
        y: anchor.y + Number(placement.y ?? anchor.height / 2),
      }, false);
      const node = nodeById(nodeId);
      if (node) {
        node.boundaryId = parent?.id || null;
        node.width = Math.max(96, Number(placement.width) || node.width);
        node.height = Math.max(52, Number(placement.height) || node.height);
        node.x = snap(anchor.x + Number(placement.x ?? anchor.width / 2) - node.width / 2);
        node.y = snap(anchor.y + Number(placement.y ?? anchor.height / 2) - node.height / 2);
      }
      addedNodeIds.push(nodeId);
    });
    const addedEdgeIds = [];
    (definition.connections || []).forEach(connection => {
      const source = addedNodeIds[connection.sourceNodeIndex];
      const target = addedNodeIds[connection.targetNodeIndex];
      if (!source || !target) return;
      const edgeId = connectNodes(
        source, target, connection.sourcePort || 'auto', connection.targetPort || 'auto', false,
      );
      const edge = edgeById(edgeId);
      if (edge) {
        edge.label = connection.label || '';
        if (Array.isArray(connection.waypoints) && connection.waypoints.length) {
          edge.waypoints = connection.waypoints.map(point => ({x: point.x, y: point.y}));
        }
        if (connection.kind === 'dashed') {
          edge.kind = 'dashed';
          edge.dash = connection.dash || EDGE_DASHES.dashed;
          edge.width = Number(connection.width) || 1.2;
        }
      }
      addedEdgeIds.push(edgeId);
    });
    if (detached) {
      clearSelection();
      addedIds.forEach(id => selectedBoundaryIds.add(id));
      selected = addedIds.length ? {type: 'boundary', id: addedIds.at(-1)} : null;
    } else if (addedIds.length) {
      selectBoundary(addedIds[0]);
    }
    persist();
    renderGraph();
    setStatus(detached
      ? `${definition.label} · ${addedIds.length} independent frames added`
      : `${definition.label} composition added · ${addedIds.length} frames · ${addedNodeIds.length} components · ${addedEdgeIds.length} traffic paths`);
    if (definition.layoutBase === 'azure-landing-zone' && fitMode) {
      requestAnimationFrame(() => fitZoom());
    }
  };

  const connectNodes = (source, target, sourcePort = 'auto', targetPort = 'auto', record = true) => {
    if (!nodeById(source) || !nodeById(target) || source === target) return null;
    if (record) checkpoint();
    const edge = {
      id: uniqueId(`edge-${source}-${target}`), source, target, sourcePort, targetPort,
      kind: 'solid', direction: 'forward', label: '', paint: '#3E3E3E', width: 1.4,
      dash: null, markerId: 'infragram-editor-arrow',
    };
    state.edges.push(edge);
    selectEdge(edge.id);
    persist();
    renderGraph();
    setStatus('Connector added');
    return edge.id;
  };

  // Copy and paste, in a clipboard of this page's own. What is picked up is
  // everything the selection implies: a frame brings what it holds, and a
  // connector comes along when both of the components it joins do.
  let clipboard = null;
  let pasteRun = 0;
  const PASTE_STEP = 24;

  const selectionBundle = () => {
    const boundaryIds = new Set(selectedBoundaryIds);
    if (selected?.type === 'boundary') boundaryIds.add(selected.id);
    for (let grew = true; grew;) {
      grew = false;
      state.boundaries.forEach(item => {
        if (item.parentId && boundaryIds.has(item.parentId) && !boundaryIds.has(item.id)) {
          boundaryIds.add(item.id);
          grew = true;
        }
      });
    }
    const nodeIds = new Set(selectedNodeIds);
    if (selected?.type === 'node') nodeIds.add(selected.id);
    state.nodes.forEach(node => {
      if (node.boundaryId && boundaryIds.has(node.boundaryId)) nodeIds.add(node.id);
    });
    if (!nodeIds.size && !boundaryIds.size) return null;
    return {
      nodes: state.nodes.filter(node => nodeIds.has(node.id)).map(clone),
      boundaries: state.boundaries.filter(item => boundaryIds.has(item.id)).map(clone),
      edges: state.edges.filter(edge => nodeIds.has(edge.source) && nodeIds.has(edge.target)).map(clone),
    };
  };

  const bundleTally = bundle => [
    [bundle.nodes.length, 'component'], [bundle.boundaries.length, 'frame'],
    [bundle.edges.length, 'connector'],
  ].filter(([count]) => count).map(([count, noun]) => `${count} ${noun}${count === 1 ? '' : 's'}`).join(' · ');

  const copySelection = () => {
    const bundle = selectionBundle();
    if (!bundle) {
      setStatus(selected?.type === 'edge'
        ? 'A connector is copied with the components it joins'
        : 'Nothing selected to copy');
      return null;
    }
    clipboard = bundle;
    pasteRun = 0;
    setStatus(`${bundleTally(bundle)} copied`);
    return bundle;
  };

  // Node and frame ids are taken by uniqueId; a connector's is checked here.
  const freshEdgeId = (source, target) => {
    let candidate = uniqueId(`edge-${source}-${target}`);
    while (edgeById(candidate)) candidate = uniqueId(`${candidate}-copy`);
    return candidate;
  };

  // A pasted copy is its own item: a new id, the frame it was in if that frame
  // came too, its connectors rebuilt between the copies, and no lock carried
  // over, so what lands can be moved straight away.
  const pasteBundle = (bundle, {at = null, step = PASTE_STEP} = {}) => {
    const placed = [...bundle.nodes, ...bundle.boundaries];
    if (!placed.length) return [];
    const shift = at
      ? {x: at.x - Math.min(...placed.map(item => item.x)), y: at.y - Math.min(...placed.map(item => item.y))}
      : {x: step, y: step};
    checkpoint();
    const boundaryMap = new Map();
    const boundaries = bundle.boundaries.map(item => {
      const copy = {...clone(item), id: uniqueId(item.id), locked: false,
        x: snap(item.x + shift.x), y: snap(item.y + shift.y)};
      boundaryMap.set(item.id, copy.id);
      return copy;
    });
    boundaries.forEach((copy, index) => {
      const original = bundle.boundaries[index];
      copy.parentId = boundaryMap.get(original.parentId) || original.parentId || null;
    });
    let order = state.nodes.reduce((highest, item) => Math.max(highest, Number(item.order) || 0), -1);
    const nodeMap = new Map();
    const nodes = bundle.nodes.map(item => {
      const copy = {...clone(item), id: uniqueId(item.id), locked: false, order: ++order,
        x: snap(item.x + shift.x), y: snap(item.y + shift.y)};
      copy.boundaryId = boundaryMap.get(item.boundaryId) || item.boundaryId || null;
      nodeMap.set(item.id, copy.id);
      return copy;
    });
    const edges = bundle.edges.map(item => {
      const copy = {...clone(item), source: nodeMap.get(item.source), target: nodeMap.get(item.target)};
      copy.id = freshEdgeId(copy.source, copy.target);
      if (Array.isArray(item.waypoints)) {
        copy.waypoints = item.waypoints.map(point => ({x: point.x + shift.x, y: point.y + shift.y}));
      }
      return copy;
    });
    state.boundaries.push(...boundaries);
    state.nodes.push(...nodes);
    state.edges.push(...edges);
    const landed = [...nodes, ...boundaries];
    ensureCanvasExtent({
      right: Math.max(...landed.map(item => item.x + item.width)) + CANVAS_MARGIN,
      bottom: Math.max(...landed.map(item => item.y + item.height)) + CANVAS_MARGIN,
    });
    clearSelection();
    boundaries.forEach(item => selectedBoundaryIds.add(item.id));
    nodes.forEach(item => selectedNodeIds.add(item.id));
    selected = nodes.length
      ? {type: 'node', id: nodes.at(-1).id}
      : {type: 'boundary', id: boundaries.at(-1).id};
    persist();
    renderGraph();
    return {items: landed, tally: bundleTally({nodes, boundaries, edges})};
  };

  const pasteClipboard = (at = null) => {
    if (!clipboard) {
      setStatus('Nothing copied yet');
      return [];
    }
    pasteRun += 1;
    const pasted = pasteBundle(clipboard, at ? {at} : {step: PASTE_STEP * pasteRun});
    setStatus(`${pasted.tally} pasted`);
    return pasted.items;
  };

  const duplicateSelection = () => {
    const bundle = selectionBundle();
    if (!bundle) {
      setStatus('Nothing selected to duplicate');
      return [];
    }
    // A duplicate leaves the clipboard as it was, so it is not a surprise copy.
    const pasted = pasteBundle(bundle);
    setStatus(`${pasted.tally} duplicated`);
    return pasted.items;
  };

  const cutSelection = () => {
    const bundle = selectionBundle();
    if (!bundle) {
      setStatus('Nothing selected to cut');
      return null;
    }
    clipboard = bundle;
    pasteRun = 0;
    deleteSelection();
    setStatus(`${bundleTally(bundle)} cut`);
    return bundle;
  };

  // Move one end of a connector onto another component. The route it had
  // belonged to the old ends, so the connector routes afresh.
  const reconnectEdge = (edgeId, end, nodeId, port = 'auto') => {
    const edge = edgeById(edgeId);
    if (!edge || !['source', 'target'].includes(end) || itemIsLocked(edge) || !nodeById(nodeId)) {
      renderGraph();
      return null;
    }
    if (itemIsLocked(nodeById(nodeId))) {
      setStatus('Locked layer · connectors cannot be added');
      renderGraph();
      return null;
    }
    const other = end === 'target' ? edge.source : edge.target;
    if (nodeId === other) {
      setStatus('A connector cannot start and end on the same component');
      renderGraph();
      return null;
    }
    const portKey = end === 'target' ? 'targetPort' : 'sourcePort';
    // A drop on the card itself asks for no particular side, so landing an
    // end back on its own card changes nothing -- and must not throw away
    // the route or the side the connector was already given.
    if (edge[end] === nodeId && (port === 'auto' || (edge[portKey] || 'auto') === port)) {
      renderGraph();
      return null;
    }
    checkpoint();
    edge[end] = nodeId;
    edge[portKey] = port;
    delete edge.waypoints;
    persist();
    renderGraph();
    setStatus(`${edge.label || 'Connector'} now ${end === 'target' ? 'ends at' : 'starts at'} ${nodeById(nodeId).name}`);
    return clone(edge);
  };

  const deleteSelection = () => {
    if (!selected && !selectedObjects().length) return;
    const nodeIds = new Set(selectedNodeIds);
    const boundaryIds = new Set(selectedBoundaryIds);
    if (selected?.type === 'node') nodeIds.add(selected.id);
    if (selected?.type === 'boundary') boundaryIds.add(selected.id);
    const deletableNodeIds = new Set(
      [...nodeIds].filter(id => !itemIsLocked(nodeById(id))),
    );
    const deletableBoundaryIds = new Set(
      [...boundaryIds].filter(id => !itemIsLocked(boundaryById(id))),
    );
    const lockedNodeIds = new Set([...nodeIds].filter(id => !deletableNodeIds.has(id)));
    const lockedBoundaryIds = new Set(
      [...boundaryIds].filter(id => !deletableBoundaryIds.has(id)),
    );
    if (selected && !['node', 'boundary'].includes(selected.type) && itemIsLocked(selectedItem())) {
      setStatus('Locked layer · unlock it before deleting this item');
      return;
    }
    if ((nodeIds.size || boundaryIds.size)
        && !deletableNodeIds.size && !deletableBoundaryIds.size) {
      setStatus('Selection is locked · unlock it before deleting');
      renderGraph();
      return;
    }
    checkpoint();
    if (nodeIds.size) {
      state.nodes = state.nodes.filter(node => !deletableNodeIds.has(node.id));
      state.edges = state.edges.filter(
        edge => !deletableNodeIds.has(edge.source) && !deletableNodeIds.has(edge.target),
      );
    }
    if (boundaryIds.size) {
      [...deletableBoundaryIds].forEach(id => {
        const boundary = boundaryById(id);
        state.boundaries.forEach(item => {
          if (item.parentId === id) item.parentId = boundary?.parentId || null;
        });
        state.nodes.forEach(node => {
          if (node.boundaryId === id) node.boundaryId = boundary?.parentId || null;
        });
      });
      state.boundaries = state.boundaries.filter(item => !deletableBoundaryIds.has(item.id));
    }
    let deletedConnector = '';
    const edgeIds = new Set(selectedEdgeIds);
    if (selected?.type === 'edge') edgeIds.add(selected.id);
    const deletableEdgeIds = new Set([...edgeIds].filter(id => !itemIsLocked(edgeById(id))));
    if (deletableEdgeIds.size) {
      // A wire picked with cards goes with them; only wires and nothing else
      // is what gives the message its name.
      if (!nodeIds.size && !boundaryIds.size) {
        deletedConnector = deletableEdgeIds.size === 1
          ? (edgeById([...deletableEdgeIds][0])?.label || 'Connector')
          : `${deletableEdgeIds.size} connectors`;
      }
      state.edges = state.edges.filter(edge => !deletableEdgeIds.has(edge.id));
    }
    const deletedCount = deletableNodeIds.size + deletableBoundaryIds.size + deletableEdgeIds.size;
    clearSelection();
    lockedNodeIds.forEach(id => selectedNodeIds.add(id));
    lockedBoundaryIds.forEach(id => selectedBoundaryIds.add(id));
    if (selectedNodeIds.size) selected = {type: 'node', id: [...selectedNodeIds].at(-1)};
    else if (selectedBoundaryIds.size) {
      selected = {type: 'boundary', id: [...selectedBoundaryIds].at(-1)};
    }
    persist();
    renderGraph();
    const lockedCount = lockedNodeIds.size + lockedBoundaryIds.size;
    setStatus(lockedCount
      ? `${deletedCount} deleted · ${lockedCount} locked · unlock the rest to delete them`
      : deletedConnector ? `${deletedConnector} deleted` : 'Selection deleted');
  };


  // A resource's parts -- a VM's NICs, disks and public IPs, which an Azure
  // import lists in attributes.attached -- shown on the canvas beside it, or
  // folded away again. Each part is a card in its owner's frame, wired to it
  // with its role, and names its owner in attributes.partOf; a part an import
  // drew itself (--all) names it in attributes.attached_to. Frames only grow
  // to hold what is shown, so nothing else on the canvas moves.
  const attachedParts = node => (Array.isArray(node?.attributes?.attached) ? node.attributes.attached : []);
  const partsShownFor = owner => state.nodes.filter(node => node.attributes?.partOf === owner.id
    || (node.attributes?.attached_to && node.attributes.attached_to === owner.name
      && node.boundaryId === owner.boundaryId));
  const ownerOfPart = node => (node?.attributes?.partOf ? nodeById(node.attributes.partOf)
    : node?.attributes?.attached_to
      ? state.nodes.find(item => item.name === node.attributes.attached_to && attachedParts(item).length)
      : null);
  const PART_GAP = 24;
  const overlapsAnything = (box, skip) => state.nodes.some(item => !skip.has(item.id) && nodeIsVisible(item)
    && box.x < item.x + item.width + 8 && box.x + box.width + 8 > item.x
    && box.y < item.y + item.height + 8 && box.y + box.height + 8 > item.y);
  const growFrameToHold = (frame, box) => {
    for (let current = frame; current; current = boundaryById(current.parentId)) {
      if (itemIsLocked(current)) return;
      const pad = Number(current.pad) || 24;
      const right = Math.max(current.x + current.width, box.x + box.width + pad);
      const bottom = Math.max(current.y + current.height, box.y + box.height + pad);
      const left = Math.min(current.x, box.x - pad);
      const top = Math.min(current.y, box.y - pad);
      Object.assign(current, {x: left, y: top, width: right - left, height: bottom - top});
      box = {x: current.x, y: current.y, width: current.width, height: current.height};
    }
  };
  const showAttachedParts = ownerId => {
    const owner = nodeById(ownerId);
    const parts = attachedParts(owner).filter(part => componentDefinitions.has(part.component));
    if (!owner || !parts.length || partsShownFor(owner).length) return 0;
    checkpoint();
    const added = new Set([owner.id]);
    // a column beside the owner, right of it where there is room, else left
    const sizes = parts.map(part => ({width: iconNodeWidth({name: part.name, detail: part.detail || ''}),
      height: ICON_NODE.height}));
    const column = Math.max(...sizes.map(size => size.width));
    const tall = sizes.reduce((sum, size) => sum + size.height + PART_GAP, -PART_GAP);
    const top = snap(owner.y + owner.height / 2 - tall / 2);
    const fits = x => !overlapsAnything({x, y: top, width: column, height: tall}, added);
    const right = snap(owner.x + owner.width + PART_GAP);
    const left = snap(owner.x - PART_GAP - column);
    const x = fits(right) || !(left >= 0 && fits(left)) ? right : left;
    let y = top;
    parts.forEach((part, index) => {
      const definition = componentDefinitions.get(part.component);
      const node = {
        ...definitionPayload(definition),
        name: part.name, detail: part.detail || definition.subtitle || '',
      };
      const id = addNode(node, {x: x + column / 2, y: y + sizes[index].height / 2}, false);
      const card = nodeById(id);
      Object.assign(card, {
        x, y, boundaryId: owner.boundaryId, displayMode: 'icon', defaultDisplay: 'icon',
        width: sizes[index].width, height: sizes[index].height,
        attributes: {partOf: owner.id, role: part.role,
          table: {columns: ['Property', 'Value'], rows: [['Attached to', owner.name], ['Role', part.role],
            ['Resource ID', part.id || '']]}},
      });
      const edgeId = connectNodes(id, owner.id, 'auto', 'auto', false);
      const edge = state.edges.find(item => item.id === edgeId);
      if (edge) Object.assign(edge, {kind: 'dashed', dash: null, label: part.role});
      added.add(id);
      y += sizes[index].height + PART_GAP;
    });
    const frame = boundaryById(owner.boundaryId);
    if (frame) growFrameToHold(frame, {x, y: top, width: column, height: tall});
    extendCanvasToContents();
    selectNode(owner.id);
    persist();
    renderGraph();
    setStatus(`${owner.name}: ${parts.length} attached shown`);
    return parts.length;
  };
  const hideAttachedParts = ownerId => {
    const owner = nodeById(ownerId);
    const shown = owner ? partsShownFor(owner) : [];
    if (!shown.length) return 0;
    checkpoint();
    const ids = new Set(shown.map(node => node.id));
    state.nodes = state.nodes.filter(node => !ids.has(node.id));
    state.edges = state.edges.filter(edge => !ids.has(edge.source) && !ids.has(edge.target));
    selectNode(owner.id);
    persist();
    renderGraph();
    setStatus(`${owner.name}: ${shown.length} attached folded away`);
    return shown.length;
  };
  const toggleAttachedParts = ownerId => {
    const owner = nodeById(ownerId);
    return owner && partsShownFor(owner).length ? -hideAttachedParts(ownerId) : showAttachedParts(ownerId);
  };
