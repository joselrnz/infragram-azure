// @module 04-model: lookups, layers, locks and the selection model
  const nodeById = id => state.nodes.find(node => node.id === id);
  const boundaryById = id => state.boundaries.find(boundary => boundary.id === id);
  const edgeById = id => state.edges.find(edge => edge.id === id);
  const layerById = id => state.layers?.find(item => item.id === id);
  const layerForProvider = provider => state.layers?.find(item => item.provider === provider);
  const projectKindForProviders = providers => {
    const cloud = providers.filter(provider => providerById.get(provider)?.kind === 'cloud');
    if (providers.length === 1) return cloud.length ? 'single-cloud' : 'platform';
    if (cloud.length && cloud.length < providers.length) return 'hybrid';
    return cloud.length ? 'multicloud' : 'platform';
  };
  const isLayerVisible = id => !id || layerById(id)?.visible !== false;
  const isLayerLocked = id => Boolean(id && layerById(id)?.locked);
  const itemIsLocked = item => Boolean(item && (item.locked || isLayerLocked(item.layerId)));
  const ensureProviderLayer = provider => {
    const existing = layerForProvider(provider);
    if (existing) return existing.id;
    const providerInfo = providerById.get(provider);
    const id = `provider:${provider}`;
    state.layers.push({
      id,
      name: providerInfo?.displayName || providerInfo?.shortName || provider,
      kind: providerInfo?.kind === 'platform' ? 'platform' : 'provider',
      provider,
      visible: true,
      locked: false,
      order: state.layers.length,
    });
    if (!state.providers.includes(provider)) state.providers.push(provider);
    return id;
  };
  const clearNodeSelection = () => { selectedNodeIds = new Set(); };
  const clearBoundarySelection = () => { selectedBoundaryIds = new Set(); };
  const clearEdgeSelection = () => { selectedEdgeIds = new Set(); };
  const clearSelection = () => {
    clearNodeSelection();
    clearBoundarySelection();
    clearEdgeSelection();
    selected = null;
    flowFocus = null;
  };
  // Connectors are picked the way components are: shift adds one to the
  // selection, and shift on one already picked takes it back out.
  const selectEdge = (id, additive = false) => {
    if (!additive) clearSelection();
    if (additive && selectedEdgeIds.has(id)) selectedEdgeIds.delete(id);
    else selectedEdgeIds.add(id);
    const primary = selectedEdgeIds.has(id) ? id : [...selectedEdgeIds].at(-1);
    selected = primary ? {type: 'edge', id: primary} : null;
  };
  const selectNode = (id, additive = false) => {
    if (!additive) clearSelection();
    if (additive && selectedNodeIds.has(id)) selectedNodeIds.delete(id);
    else selectedNodeIds.add(id);
    const primary = selectedNodeIds.has(id) ? id : [...selectedNodeIds].at(-1);
    if (primary) selected = {type: 'node', id: primary};
    else if (selectedBoundaryIds.size) selected = {type: 'boundary', id: [...selectedBoundaryIds].at(-1)};
    else selected = null;
  };
  // A single click shows what flows through an item: its wires animate in
  // the traffic's direction and the rest of the drawing steps back. Nothing
  // is selected by it; a click on empty canvas or Escape ends it.
  const showFlow = (type, id, more = {}) => {
    clearSelection();
    flowFocus = {type, id, ...more};
  };
  // The lenses of the right-click menu (24-context-menu) light the drawing
  // the way a flow does, and end the way it ends: what depends on a card,
  // what the internet reaches, what is priced, what wears a tag, what an
  // Azure import found changed lately or raised findings about.
  const LENSES = ['dependents', 'internet', 'cost', 'tag', 'changes', 'findings', 'refresh'];
  const INTERNET_COMPONENTS = new Set(['public-users', 'public-user', 'public-internet']);
  const nodeIsInternet = node => INTERNET_COMPONENTS.has(String(node.componentId || '').split(':').pop());
  const nodeTags = node => {
    const tags = node.attributes?.tags;
    return tags && typeof tags === 'object' && !Array.isArray(tags) ? tags : {};
  };
  const nodeMonthly = node => {
    const monthly = Number(node.attributes?.price?.monthly);
    return node.attributes?.price && Number.isFinite(monthly) ? monthly : null;
  };
  // What an Azure import read about a card or frame: its changes in the
  // fourteen days before the read, newest first, and the findings Defender
  // for Cloud and Azure Policy raised about it, worst first.
  const itemChanges = item => {
    const changes = item?.attributes?.changes;
    return changes && Array.isArray(changes.items) && changes.items.length ? changes : null;
  };
  const itemFindings = item => {
    const findings = item?.attributes?.findings;
    return findings && Array.isArray(findings.items) && findings.items.length ? findings : null;
  };
  // changed in the week before the read: the read, not today, is the
  // measure, so an estate read last month still says what was new then
  const RECENT_DAYS = 7;
  const changedLately = item => {
    const changes = itemChanges(item);
    if (!changes) return false;
    const read = Date.parse(changes.read) || Date.parse(changes.items[0].when);
    return changes.items.some(change => read - Date.parse(change.when) <= RECENT_DAYS * 864e5);
  };
  const hasFindings = item => Boolean(itemFindings(item));
  // What export:azure --refresh found added or changed since the read the
  // diagram was drawn from (discovery/refresh.py); what was removed has no
  // element left, and the document's root lists it.
  const refreshedSince = item => ['added', 'changed'].includes(item?.attributes?.refresh?.status);
  const refreshSummary = () => {
    const account = originalProject?.topology?.attributes?.refresh || {};
    const removed = Array.isArray(account.removed)
      ? account.removed.filter(item => item && typeof item === 'object') : [];
    const counts = [`${Number(account.added) || 0} added`, `${Number(account.changed) || 0} changed`,
      `${removed.length} removed`].join(', ');
    const gone = removed.length ? `: ${removed.slice(0, 5).map(item => String(item.name || item.type || 'a resource')).join(', ')}${removed.length > 5 ? ', …' : ''}` : '';
    return `Since the last read, ${counts}${gone}`;
  };
  const showLens = lens => {
    clearSelection();
    flowFocus = lens;
  };
  // Every card a wire leads to from the starts (forward), or that leads to
  // them (backward), however many wires away; a wire with a head at both
  // ends, or at neither, is followed either way.
  const reached = (starts, forward) => {
    const nodes = new Set(starts);
    const edges = new Set();
    let grew = true;
    while (grew) {
      grew = false;
      state.edges.forEach(edge => {
        const hops = [[edge.source, edge.target]];
        if (edgeDirection(edge) !== 'forward') hops.push([edge.target, edge.source]);
        hops.forEach(([from, to]) => {
          const [have, next] = forward ? [from, to] : [to, from];
          if (!nodes.has(have) || (edges.has(edge.id) && nodes.has(next))) return;
          edges.add(edge.id);
          nodes.add(next);
          grew = true;
        });
      });
    }
    return {nodes, edges};
  };
  const lensLit = lens => {
    let nodes = new Set();
    let edges = new Set();
    let heat = null;
    // frames lit for themselves: a subnet changed, a network with a finding
    let ownFrames = [];
    if (lens.type === 'dependents') {
      if (!nodeById(lens.id)) return null;
      ({nodes, edges} = reached([lens.id], false));
    } else if (lens.type === 'internet') {
      ({nodes, edges} = reached(state.nodes.filter(nodeIsInternet).map(node => node.id), true));
    } else if (lens.type === 'cost') {
      const priced = state.nodes.filter(node => nodeMonthly(node) !== null);
      const most = Math.max(0, ...priced.map(nodeMonthly));
      heat = new Map(priced.map(node => [node.id, most ? nodeMonthly(node) / most : 0]));
      nodes = new Set(heat.keys());
    } else if (lens.type === 'changes' || lens.type === 'findings' || lens.type === 'refresh') {
      const lit = {changes: changedLately, findings: hasFindings, refresh: refreshedSince}[lens.type];
      nodes = new Set(state.nodes.filter(lit).map(node => node.id));
      ownFrames = state.boundaries.filter(lit).map(frame => frame.id);
    } else {
      nodes = new Set(state.nodes.filter(node => String(nodeTags(node)[lens.key]) === lens.value
        && lens.key in nodeTags(node)).map(node => node.id));
      state.edges.forEach(edge => {
        if (nodes.has(edge.source) && nodes.has(edge.target)) edges.add(edge.id);
      });
    }
    const frames = new Set();
    [...[...nodes].map(nodeId => nodeById(nodeId)?.boundaryId), ...ownFrames].forEach(start => {
      let frameId = start || null;
      while (frameId && !frames.has(frameId)) {
        frames.add(frameId);
        frameId = boundaryById(frameId)?.parentId || null;
      }
    });
    return {nodes, edges, frames, heat, lens: lens.type};
  };
  // What the flow lights: its wires, the cards they join, and the frames
  // holding those cards (or the frame the flow is of, and what is in it).
  const flowLit = () => {
    if (!flowFocus) return null;
    if (LENSES.includes(flowFocus.type)) return lensLit(flowFocus);
    const {type, id} = flowFocus;
    const nodes = new Set();
    const edges = new Set();
    const frames = new Set();
    let inside;
    if (type === 'node') {
      if (!nodeById(id)) return null;
      inside = new Set([id]);
    } else if (type === 'boundary') {
      if (!boundaryById(id)) return null;
      inside = new Set(state.nodes.filter(node => node.boundaryId && isBoundaryDescendant(node.boundaryId, id))
        .map(node => node.id));
      state.boundaries.filter(item => isBoundaryDescendant(item.id, id) || isBoundaryDescendant(id, item.id))
        .forEach(item => frames.add(item.id));
    } else if (type === 'step') {
      // a row of the step list: every wire told by that number in that flow
      const told = state.edges.filter(edge => edgeStep(edge) === id && (edge.stepFlow || '') === flowFocus.flow);
      if (!told.length) return null;
      inside = new Set();
      told.forEach(edge => {
        edges.add(edge.id);
        nodes.add(edge.source);
        nodes.add(edge.target);
      });
    } else {
      const edge = edgeById(id);
      if (!edge) return null;
      inside = new Set();
      edges.add(edge.id);
      nodes.add(edge.source);
      nodes.add(edge.target);
    }
    inside.forEach(nodeId => nodes.add(nodeId));
    state.edges.forEach(edge => {
      if (inside.has(edge.source) || inside.has(edge.target)) {
        edges.add(edge.id);
        nodes.add(edge.source);
        nodes.add(edge.target);
      }
    });
    nodes.forEach(nodeId => {
      let frameId = nodeById(nodeId)?.boundaryId || null;
      while (frameId && !frames.has(frameId)) {
        frames.add(frameId);
        frameId = boundaryById(frameId)?.parentId || null;
      }
    });
    return {nodes, edges, frames};
  };
  const selectBoundary = (id, additive = false) => {
    if (!additive) clearSelection();
    if (additive && selectedBoundaryIds.has(id)) selectedBoundaryIds.delete(id);
    else selectedBoundaryIds.add(id);
    const primary = selectedBoundaryIds.has(id) ? id : [...selectedBoundaryIds].at(-1);
    if (primary) selected = {type: 'boundary', id: primary};
    else if (selectedNodeIds.size) selected = {type: 'node', id: [...selectedNodeIds].at(-1)};
    else selected = null;
  };
  const selectedNodes = () => [...selectedNodeIds].map(nodeById).filter(Boolean);
  const selectedBoundaries = () => [...selectedBoundaryIds].map(boundaryById).filter(Boolean);
  const selectedObjects = () => [...selectedBoundaries(), ...selectedNodes()];
  // Every connector an action should act on: the ones picked, and the one
  // that is merely current when nothing was picked with it.
  const edgeSelectionIds = () => {
    const ids = new Set(selectedEdgeIds);
    if (selected?.type === 'edge') ids.add(selected.id);
    return [...ids];
  };
  // One action on a selection of wires is one step back: the checkpoint is
  // taken once here, and each wire is changed without taking its own.
  const forEachSelectedEdge = change => {
    const ids = edgeSelectionIds();
    if (!ids.length) return;
    checkpoint();
    ids.forEach(id => change(id, false));
  };
  const isEdgeSelected = id => selectedEdgeIds.has(id);
  const isNodeSelected = id => selectedNodeIds.has(id);
  const isBoundarySelected = id => selectedBoundaryIds.has(id);
  const selectedItem = () => {
    if (selected?.type === 'node') return nodeById(selected.id);
    if (selected?.type === 'boundary') return boundaryById(selected.id);
    if (selected?.type === 'edge') return edgeById(selected.id);
    return null;
  };
