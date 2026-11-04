// @module 25-panels: layers panel, frame tree, inspector tabs and outline presets
  document.querySelectorAll('[data-png-scale-choice]').forEach(choice => choice.addEventListener('click', () => {
    const scale = Number(choice.dataset.pngScaleChoice);
    if (![1, 2, 3, 4].includes(scale)) return;
    state.canvas.pngScale = scale;
    persist();
    updateInspector();
  }));
  document.querySelectorAll('[data-legend-setting]').forEach(control => {
    control.addEventListener(control.type === 'checkbox' ? 'change' : 'click', () => {
      const setting = control.dataset.legendSetting;
      state.canvas[setting] = control.type === 'checkbox' ? control.checked : !legendEnabled(setting);
      persist();
      renderGraph();
    });
  });
  document.querySelector('[data-inspector-title]')?.addEventListener('click', event => {
    const placement = event.target.closest('[data-title-placement]')?.dataset.titlePlacement;
    if (!['header', 'caption', 'hidden'].includes(placement)) return;
    state.canvas.titlePlacement = placement;
    persist();
    renderGraph();
  });
  document.querySelector('[data-layer-list]').addEventListener('change', event => {
    const input = event.target.closest('[data-layer-visible]');
    if (!input) return;
    const targetLayer = layerById(input.dataset.layerVisible);
    if (!targetLayer) return;
    checkpoint();
    targetLayer.visible = input.checked;
    if (!targetLayer.visible) {
      selectedNodeIds = new Set([...selectedNodeIds].filter(id => nodeIsVisible(nodeById(id))));
      selectedBoundaryIds = new Set([...selectedBoundaryIds].filter(id => boundaryIsVisible(boundaryById(id))));
      if (selected && !selectedItem()) selected = null;
      if (selected?.type === 'node' && !isNodeSelected(selected.id)) {
        const next = [...selectedNodeIds].at(-1);
        selected = next ? {type: 'node', id: next} : null;
      }
      if (selected?.type === 'boundary' && !isBoundarySelected(selected.id)) {
        const next = [...selectedBoundaryIds].at(-1);
        selected = next ? {type: 'boundary', id: next} : null;
      }
      if (selected && selected.type !== 'node' && !isLayerVisible(selectedItem()?.layerId)) selected = null;
    }
    persist();
    renderGraph();
    setStatus(`${targetLayer.name} layer ${targetLayer.visible ? 'shown' : 'hidden'}`);
  });
  document.querySelector('[data-layer-list]').addEventListener('click', event => {
    const button = event.target.closest('[data-layer-lock]');
    if (!button) return;
    const targetLayer = layerById(button.dataset.layerLock);
    if (!targetLayer) return;
    checkpoint();
    targetLayer.locked = !targetLayer.locked;
    persist();
    renderGraph();
    setStatus(`${targetLayer.name} layer ${targetLayer.locked ? 'locked' : 'unlocked'}`);
  });
  document.querySelector('[data-frame-tree]').addEventListener('click', event => {
    const select = event.target.closest('[data-frame-select]');
    const lock = event.target.closest('[data-frame-lock]');
    if (select) {
      selectBoundary(select.dataset.frameSelect, event.shiftKey || event.ctrlKey || event.metaKey);
      renderGraph();
      return;
    }
    if (lock) {
      const frame = boundaryById(lock.dataset.frameLock);
      if (!frame) return;
      checkpoint();
      frame.locked = !frame.locked;
      persist();
      renderGraph();
      setStatus(`${frame.name} ${frame.locked ? 'locked' : 'unlocked'}`);
    }
  });
  document.querySelectorAll('[data-inspector-tab]').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.inspectorTab;
      document.querySelectorAll('[data-inspector-tab]').forEach(item => {
        item.setAttribute('aria-selected', String(item === tab));
      });
      document.querySelectorAll('[data-inspector-panel]').forEach(panel => {
        panel.hidden = panel.dataset.inspectorPanel !== target;
      });
    });
  });
  // An outline preset changes the outline and nothing else: the card keeps the
  // theme's fill, so a preset applied on the light canvas does not paint the
  // card with the dark theme's grey. Neutral returns the item to the theme.
  const stylePresets = {
    'accent-outline': {stroke: '#479EF5'},
    'muted-outline': {stroke: '#5E87B8'},
    'danger-outline': {stroke: '#E03131'},
  };
  // A component's box (panels.py): its shape, tone and compartments. A
  // panel is sized the way Python sizes it; a card that stops being one
  // goes back to the card's own size. Neighbours make room either way.
  // `before` is the boxes as they stood (snapshotBoxes). With `grow`, a
  // panel that was one keeps a size the reader gave it if its text still
  // fits: new text only widens or lengthens it.
  const refitBox = (node, wasPanel, before, {grow = false} = {}) => {
    if (!wasPanel && !isPanel(node)) return;
    const centerX = node.x + node.width / 2;
    const centerY = node.y + node.height / 2;
    if (isPanel(node)) {
      if (!wasPanel) {
        node.cardSize = {width: node.width, height: node.height};
        node.panelIcon = Boolean(node.iconUri) && !String(node.componentId || '').startsWith('custom-');
      }
      const size = panelSize(node);
      if (grow && wasPanel) {
        size.width = Math.max(size.width, node.width);
        size.height = Math.max(size.height, node.height);
      }
      Object.assign(node, size);
      node.displayMode = 'card';
    } else {
      node.width = Math.max(96, Number(node.cardSize?.width) || 208);
      node.height = Math.max(56, Number(node.cardSize?.height) || 72);
    }
    node.x = snap(Math.max(0, centerX - node.width / 2));
    node.y = snap(Math.max(0, centerY - node.height / 2));
    reflowContainers([node], before);
    fitAllFrames();
    extendCanvasToContents();
  };
  const reshapeBox = (change, message) => {
    const node = selected?.type === 'node' ? selectedItem() : null;
    if (!node || itemIsLocked(node)) return;
    checkpoint();
    const before = snapshotBoxes();
    const wasPanel = isPanel(node);
    node.attributes = {...(node.attributes || {})};
    change(node.attributes);
    refitBox(node, wasPanel, before);
    persist();
    renderGraph();
    setStatus(`${node.name} ${message}`);
  };
  document.querySelectorAll('[data-node-shape]').forEach(button => {
    button.addEventListener('click', () => reshapeBox(attributes => {
      if (button.dataset.nodeShape === 'rect') delete attributes.shape;
      else attributes.shape = button.dataset.nodeShape;
    }, `drawn as ${button.textContent.trim().toLowerCase()}`));
  });
  document.querySelectorAll('[data-node-tone]').forEach(button => {
    button.addEventListener('click', () => reshapeBox(attributes => {
      if (button.dataset.nodeTone) attributes.tone = button.dataset.nodeTone;
      else delete attributes.tone;
    }, button.dataset.nodeTone ? `toned ${button.dataset.nodeTone}` : 'tone removed'));
  });
  document.querySelector('[data-node-sections]')?.addEventListener('change', event => {
    const rows = parseSections(event.target.value);
    reshapeBox(attributes => {
      if (rows.length) attributes.sections = rows;
      else delete attributes.sections;
    }, rows.length ? 'compartments updated' : 'compartments removed');
  });
  document.querySelectorAll('[data-style-preset]').forEach(button => {
    button.addEventListener('click', () => {
      const item = selectedItem();
      if (!item) return;
      checkpoint();
      const preset = stylePresets[button.dataset.stylePreset];
      if (preset) item.style = clone(preset);
      else delete item.style;
      persist();
      renderGraph();
      setStatus(`${selected.type === 'edge' ? (item.label || 'Connector') : item.name} style updated`);
    });
  });
