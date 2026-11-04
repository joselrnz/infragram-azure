// @module 27-export-project: the project document the page downloads
  const exportProject = () => {
    const project = clone(originalProject);
    const installed = new Map((project.providers || []).map(provider => [provider.id, provider]));
    state.providers.forEach(provider => {
      if (!installed.has(provider)) installed.set(provider, {id: provider, enabled: true});
    });
    project.providers = [...installed.values()];
    const enabledProviders = project.providers.filter(provider => provider.enabled !== false);
    if (project.kind !== 'hybrid') {
      project.kind = projectKindForProviders([...installed.keys()]);
    }
    if (project.default_library !== 'all'
        && !enabledProviders.some(provider => provider.id === project.default_library)) {
      project.default_library = enabledProviders.length === 1 ? enabledProviders[0].id : 'all';
    }
    project.presentation = {...(project.presentation || {}), display: state.canvas.displayMode || 'card'};
    project.presentation.crossings = crossingStyle();
    project.presentation.frame_lines = state.canvas.frameLines || 'thin';
    project.layers = state.layers.map(item => ({
      id: item.id,
      name: item.name,
      kind: item.kind || 'logical',
      ...(item.provider ? {provider: item.provider} : {}),
      visible: item.visible !== false,
      locked: Boolean(item.locked),
      order: Number(item.order) || 0,
    }));
    const connections = new Map(state.nodes.map(node => [node.id, []]));
    const edgeStyles = new Map(state.nodes.map(node => [node.id, {}]));
    state.edges.forEach(edge => {
      const placement = edge.labelPlacement?.mode === 'manual'
        && Number.isFinite(Number(edge.labelPlacement.dx))
        && Number.isFinite(Number(edge.labelPlacement.dy))
        ? {
            mode: 'manual',
            dx: Number(edge.labelPlacement.dx),
            dy: Number(edge.labelPlacement.dy),
          }
        : null;
      connections.get(edge.source)?.push({
        target: edge.target,
        kind: edge.kind || 'solid',
        label: edge.label || '',
        ...(edgeDirection(edge) !== 'forward' ? {direction: edgeDirection(edge)} : {}),
        ...(Array.isArray(edge.waypoints) && edge.waypoints.length
          ? {waypoints: edge.waypoints.map(point => ({x: point.x, y: point.y}))} : {}),
        ...(placement ? {label_placement: placement} : {}),
        // a step numbers a caption: a wire whose label was cleared keeps none
        ...(edgeStep(edge) && String(edge.label || '').trim()
          ? {step: edgeStep(edge), ...(edge.stepText ? {step_text: String(edge.stepText)} : {}),
            ...(edge.stepFlow ? {step_flow: String(edge.stepFlow)} : {})} : {}),
      });
    });
    state.edges.forEach(edge => {
      const pinned = {
        ...(edge.sourcePort && edge.sourcePort !== 'auto' ? {source_port: edge.sourcePort} : {}),
        ...(edge.targetPort && edge.targetPort !== 'auto' ? {target_port: edge.targetPort} : {}),
      };
      if (!edgeStyles.has(edge.source)) return;
      if (!edge.style && !Object.keys(pinned).length) return;
      edgeStyles.get(edge.source)[edge.target] = {...clone(edge.style || {}), ...pinned};
    });
    // What the editor does not model comes back from the document it opened:
    // an element's role (the hub a drawing centres on) and the root's own id,
    // type and attributes. The editor never changes them.
    const originalRoot = originalProject.topology || {};
    const originalElements = new Map();
    const remember = element => {
      (element?.children || []).forEach(child => {
        if (child?.id) originalElements.set(child.id, child);
        remember(child);
      });
    };
    remember(originalRoot);
    const keptRole = id => {
      const role = originalElements.get(id)?.role;
      return role ? {role} : {};
    };
    const nodeElement = node => ({
        id: node.id, name: node.name, type: node.type || 'service',
        ...keptRole(node.id),
        ...(node.layerId ? {layer_id: node.layerId} : {}),
        ...(node.componentProvider ? {component: {
          provider: node.componentProvider,
          service_id: node.componentId,
          icon_ref: node.componentQualifiedId || `${node.componentProvider}:${node.componentId}`,
        }} : {}),
        attributes: {
          ...(node.attributes || {}),
          icon: node.componentId, category: node.category,
          detail: node.detail, editor_x: node.x, editor_y: node.y,
          editor_order: Number(node.order) || 0,
          editor_locked: Boolean(node.locked),
          editor_angle: Number(node.angle) || 0,
          editor_flip_x: Boolean(node.flipX), editor_flip_y: Boolean(node.flipY),
          editor_display_mode: node.displayMode || 'card',
          ...(node.cardSize ? {editor_card_size: clone(node.cardSize)} : {}),
          ...(node.textStyle ? {editor_text_style: clone(node.textStyle)} : {}),
          ...(node.style ? {editor_style: clone(node.style)} : {}),
          ...(Object.keys(edgeStyles.get(node.id) || {}).length
            ? {editor_edge_styles: edgeStyles.get(node.id)} : {}),
        },
        connections: connections.get(node.id),
      });
    const boundaryElement = boundary => ({
      id: boundary.id, name: boundary.name, type: boundary.kind || 'group',
      ...keptRole(boundary.id),
      ...(boundary.layerId ? {layer_id: boundary.layerId} : {}),
      ...(boundary.componentProvider
          && boundary.componentQualifiedId?.startsWith(`${boundary.componentProvider}:`)
        ? {component: {
        provider: boundary.componentProvider,
        service_id: boundary.componentQualifiedId.split(':').at(-1),
        icon_ref: boundary.componentQualifiedId,
      }} : {}),
      attributes: {
        ...Object.fromEntries(Object.entries(boundary.attributes || {})
          .filter(([key]) => key !== 'editor_highlight')),
        ...(boundary.highlight ? {editor_highlight: true} : {}),
        editor_x: boundary.x, editor_y: boundary.y,
        editor_width: boundary.width, editor_height: boundary.height,
        editor_order: Number(boundary.order) || 0,
        editor_locked: Boolean(boundary.locked),
        editor_user_group: Boolean(boundary.userGroup),
        editor_angle: Number(boundary.angle) || 0,
        editor_flip_x: Boolean(boundary.flipX), editor_flip_y: Boolean(boundary.flipY),
        ...(boundary.textStyle ? {editor_text_style: clone(boundary.textStyle)} : {}),
        ...(boundary.frameGroup ? {editor_frame_group: boundary.frameGroup} : {}),
        editor_boundary_style: Object.fromEntries([
          'stroke', 'fill', 'dash', 'strokeWidth', 'radius', 'tabbed', 'tab',
          'iconUri', 'labelColor', 'labelFont', 'labelSize', 'labelWeight',
          'labelTracking', 'labelCase', 'pad',
        ].filter(key => boundary[key] !== undefined).map(key => [key, clone(boundary[key])])),
        ...(boundary.style ? {editor_style: clone(boundary.style)} : {}),
      },
      // Corner badges go back as the document's badges, artwork left out:
      // the icon reference is enough to draw them again.
      ...((boundary.badges || []).length ? {badges: boundary.badges.map(badge => ({
        icon: badge.icon, collection: badge.collection || '', label: badge.label || '',
        side: badge.side || 'corner', offset: Number(badge.offset ?? 0.5),
      }))} : {}),
      children: [
        ...state.boundaries.filter(item => item.parentId === boundary.id).map(boundaryElement),
        ...state.nodes.filter(node => node.boundaryId === boundary.id).map(nodeElement),
      ],
    });
    project.topology = {
      id: originalRoot.id || 'root', name: project.title, type: originalRoot.type || 'group',
      ...(originalRoot.role ? {role: originalRoot.role} : {}),
      ...(originalRoot.component ? {component: clone(originalRoot.component)} : {}),
      ...(originalRoot.layer_id ? {layer_id: originalRoot.layer_id} : {}),
      ...(originalRoot.attributes && Object.keys(originalRoot.attributes).length
        ? {attributes: clone(originalRoot.attributes)} : {}),
      ...((originalRoot.badges || []).length ? {badges: clone(originalRoot.badges)} : {}),
      children: [
        ...state.boundaries.filter(boundary => !boundary.parentId).map(boundaryElement),
        ...state.nodes.filter(node => !node.boundaryId).map(nodeElement),
      ],
    };
    return project;
  };
