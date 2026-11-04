// @module 06-inspector-sync: keeps every inspector control in step with the selection
  // A colour input shows only a swatch, so its hex value is read out beside it.
  const syncColorReadouts = () => {
    document.querySelectorAll('.md-color-field__value').forEach(readout => {
      readout.textContent = readout.previousElementSibling?.value || '';
    });
  };
  document.addEventListener('input', event => {
    if (event.target.matches?.('.md-color-field > input')) syncColorReadouts();
  });
  const updateInspector = () => {
    document.querySelectorAll('[data-png-scale-choice]').forEach(choice => {
      choice.setAttribute('aria-pressed', String(Number(choice.dataset.pngScaleChoice) === (state.canvas.pngScale || 2)));
    });
    const qualityLabel = document.querySelector('[data-png-quality-label]');
    if (qualityLabel) qualityLabel.textContent = ['Standard', 'Sharp', 'High', 'Maximum'][(state.canvas.pngScale || 2) - 1];
    updateLegend();
    document.querySelectorAll('[data-legend-setting]').forEach(control => {
      const enabled = Boolean(legendEnabled(control.dataset.legendSetting));
      if (control.type === 'checkbox') control.checked = enabled;
      else control.setAttribute('aria-checked', String(enabled));
    });
    const titlePlacement = ['header', 'caption', 'hidden'].includes(state.canvas.titlePlacement)
      ? state.canvas.titlePlacement : 'header';
    const title = document.querySelector('[data-document-title]');
    if (title) title.hidden = titlePlacement !== 'header';
    const caption = document.querySelector('[data-diagram-caption]');
    if (caption) {
      caption.textContent = originalProject.title;
      caption.hidden = titlePlacement !== 'caption';
    }
    document.querySelectorAll('[data-inspector-title] [data-title-placement]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.titlePlacement === titlePlacement));
    });
    const item = selectedItem();
    const nodes = selectedNodes();
    const objects = selectedObjects();
    const selectionCount = objects.length || (item ? 1 : 0);
    // With nothing selected a panel of disabled controls says less than one
    // line saying what to select, so the selection panels show that instead.
    document.querySelectorAll('[data-inspector-panel][data-empty]').forEach(panel => {
      panel.dataset.empty = String(!item && !objects.length);
    });
    const frame = selectionCount === 1 && selected?.type === 'boundary' ? item : null;
    document.querySelectorAll('[data-frame-style-section]').forEach(section => {
      section.hidden = !frame;
    });
    // a panel is a box in either look: chosen alone, or only panels, the
    // card-or-icon choice has nothing to offer, so it steps aside
    const pickedNodes = selectedNodes();
    const panelsOnly = pickedNodes.length > 0 && pickedNodes.length === objects.length && pickedNodes.every(isPanel);
    document.querySelectorAll('[data-node-display-section]').forEach(section => {
      section.hidden = Boolean(frame) || panelsOnly;
    });
    // nor does a font: a panel's type is fixed (render-metrics.json panel),
    // so the Text tab says so rather than offer choices that change nothing
    document.querySelectorAll('[data-text-type-section]').forEach(section => {
      section.hidden = panelsOnly;
    });
    document.querySelectorAll('[data-text-type-note]').forEach(note => {
      note.hidden = !panelsOnly;
    });
    if (frame) {
      const members = state.nodes.filter(
        node => node.boundaryId && isBoundaryDescendant(node.boundaryId, frame.id),
      );
      const icons = members.filter(node => (node.displayMode || 'card') === 'icon').length;
      const toggle = document.querySelector('[data-frame-highlight-toggle]');
      if (toggle) {
        toggle.setAttribute('aria-checked', String(Boolean(frame.highlight)));
        toggle.disabled = itemIsLocked(frame);
      }
      document.querySelectorAll('[data-frame-display]').forEach(choice => {
        const mode = choice.dataset.frameDisplay;
        choice.disabled = !members.length;
        choice.setAttribute('aria-pressed', String(Boolean(members.length) && (
          mode === 'icon' ? icons === members.length : icons === 0)));
      });
    }
    document.querySelectorAll('[data-diagram-stat]').forEach(stat => {
      stat.textContent = String((state[stat.dataset.diagramStat] || []).length);
    });
    const selectionLabel = document.querySelector('[data-inspector-selection]');
    if (selectionLabel) {
      const manyEdges = selected?.type === 'edge' && selectedEdgeIds.size > 1;
      selectionLabel.textContent = manyEdges
        ? `${selectedEdgeIds.size} connectors`
        : item
          ? (selected.type === 'edge' ? (item.label || 'Connector') : item.name)
          : 'Nothing';
    }
    document.querySelectorAll('[data-style-preset]').forEach(button => {
      button.disabled = !item;
    });
    // a component's box: its shape, tone and compartments (panels)
    const boxSection = document.querySelector('[data-node-box-section]');
    if (boxSection) {
      const boxNode = selected?.type === 'node' && selectedObjects().length === 1 ? item : null;
      boxSection.hidden = !boxNode;
      if (boxNode) {
        const editable = !itemIsLocked(boxNode);
        const shape = panelShape(boxNode);
        const rows = panelRows(boxNode).length > 0;
        boxSection.querySelectorAll('[data-node-shape]').forEach(button => {
          // an ellipse and a hexagon carry no compartments
          button.disabled = !editable || (rows && ['ellipse', 'hexagon'].includes(button.dataset.nodeShape));
          button.title = button.disabled && editable ? 'Remove the compartments first' : button.getAttribute('title');
          button.setAttribute('aria-pressed', String(button.dataset.nodeShape === shape));
        });
        const meanings = new Map(originalProject.presentation?.tones || []);
        boxSection.querySelectorAll('[data-node-tone]').forEach(button => {
          button.disabled = !editable;
          button.setAttribute('aria-pressed', String((boxNode.attributes?.tone || '') === button.dataset.nodeTone));
          const meaning = meanings.get(button.dataset.nodeTone);
          if (meaning) button.title = meaning;
          const swatch = button.querySelector('.tone-swatch');
          const tone = toneOf(button.dataset.nodeTone);
          if (swatch && tone) swatch.style.cssText = `--tone-fill:${tone[0]};--tone-line:${tone[1]}`;
        });
        const sections = boxSection.querySelector('[data-node-sections]');
        const rounded = ['ellipse', 'hexagon'].includes(shape);
        sections.disabled = !editable || rounded;
        boxSection.querySelector('[data-node-sections-help]').hidden = rounded;
        boxSection.querySelector('[data-node-sections-shape]').hidden = !rounded;
        if (document.activeElement !== sections) sections.value = sectionsText(boxNode);
      }
    }
    const providerLabel = document.querySelector('[data-inspector-provider]');
    const componentLabel = document.querySelector('[data-inspector-component]');
    const layerLabel = document.querySelector('[data-inspector-layer]');
    // names a reader knows, not the ids the document stores
    const libraryName = id => (id === 'infragram' ? 'Shared'
      : providerById.get(id)?.displayName || providerById.get(id)?.shortName || id);
    const componentName = object => componentDefinitions.get(object?.componentQualifiedId)?.name
      || object?.componentQualifiedId || object?.componentId;
    const providers = new Set(objects.map(object => object.componentProvider).filter(Boolean));
    if (providerLabel) providerLabel.textContent = objects.length > 1
      ? (providers.size === 1 ? libraryName([...providers][0]) : 'Mixed')
      : (item?.componentProvider ? libraryName(item.componentProvider) : '—');
    if (componentLabel) componentLabel.textContent = objects.length > 1
      ? `${objects.length} items`
      : (componentName(item) || '—');
    if (layerLabel) layerLabel.textContent = objects.length > 1
      ? (new Set(objects.map(object => object.layerId)).size === 1
          ? (layerById(objects[0].layerId)?.name || objects[0].layerId) : 'Mixed')
      : (layerById(item?.layerId)?.name || item?.layerId || '—');
    const selectionCountElement = document.querySelector('[data-selection-count]');
    if (selectionCountElement) selectionCountElement.textContent = String(selectionCount);
    const selectionKindElement = document.querySelector('[data-arrange-selection-kind]');
    if (selectionKindElement) {
      const frameCount = selectedBoundaries().length;
      const nodeCount = selectedNodes().length;
      selectionKindElement.textContent = frameCount && nodeCount
        ? `${frameCount} frame${frameCount === 1 ? '' : 's'} + ${nodeCount} component${nodeCount === 1 ? '' : 's'} selected`
        : frameCount
          ? `${frameCount} frame${frameCount === 1 ? '' : 's'} selected`
          : nodeCount
            ? `${nodeCount} component${nodeCount === 1 ? '' : 's'} selected`
            : 'Nothing selected';
    }
    document.querySelectorAll('[data-exact-field]').forEach(input => {
      const editable = selectionCount === 1 && item && selected?.type !== 'edge' && !itemIsLocked(item);
      input.disabled = !editable;
      input.value = editable ? String(item[input.dataset.exactField] ?? '') : '';
    });
    document.querySelectorAll('[data-arrange-action]').forEach(button => {
      const action = button.dataset.arrangeAction;
      const alignmentAction = action.startsWith('align-') || action.startsWith('distribute-');
      const candidates = alignmentAction ? topLevelArrangeObjects() : objects;
      const unlocked = candidates.filter(object => !itemIsLocked(object));
      const minimum = action.startsWith('distribute-') ? 3
        : action.startsWith('align-') || action === 'group' ? 2 : 1;
      button.disabled = (action === 'lock' ? objects.length < 1 : unlocked.length < minimum)
        || (action === 'ungroup' && !(selected?.type === 'boundary' && item?.userGroup))
        || (action === 'detach' && !objects.some(object => object.boundaryId || object.parentId))
        || (action === 'shrink-fit' && selected?.type !== 'boundary')
        || (['rotate-90', 'flip-horizontal', 'flip-vertical'].includes(action)
          && !nodes.some(node => !itemIsLocked(node)));
    });
    document.querySelectorAll('[data-text-control]').forEach(control => {
      const key = control.dataset.textControl;
      // A connector label has no alignment: it sits on its own wire.
      // `edgeSelected` is declared further down, so ask the selection here.
      const edgeText = selectionCount === 1 && selected?.type === 'edge'
        && Boolean(item) && key !== 'textAlign';
      const enabled = Boolean(
        selectionCount === 1 && item && !itemIsLocked(item)
        && (selected?.type !== 'edge' || edgeText),
      );
      control.disabled = !enabled;
      if (!enabled) return;
      if (edgeText) {
        control.value = String(edgeTextStyle(item)[key]);
        return;
      }
      // what the card is drawn with when it carries no text style of its own
      const fallback = {fontFamily: 'Inter', fontSize: 12, fontWeight: 600,
        textAlign: 'left', textColor: canvasPalette().text.toLowerCase(), opacity: 100};
      control.value = String(withCurrentFace(item.textStyle || {})[key] ?? fallback[key]);
    });
    document.querySelectorAll('[data-content-control]').forEach(control => {
      const key = control.dataset.contentControl;
      const enabled = Boolean(
        selectionCount === 1
        && item
        && selected?.type !== 'edge'
        && !itemIsLocked(item)
        && (key !== 'detail' || selected?.type === 'node'),
      );
      control.disabled = !enabled;
      control.value = enabled ? String(item[key] || '') : '';
    });
    const edgeSelected = selectionCount === 1 && selected?.type === 'edge' && Boolean(item)
      && selectedEdgeIds.size <= 1;
    // a connector's text is its label, so the card's name fields step aside
    document.querySelectorAll('[data-content-section]').forEach(section => {
      section.hidden = edgeSelected;
    });
    document.querySelectorAll('[data-edge-label-section]').forEach(section => {
      section.hidden = !edgeSelected;
    });
    document.querySelectorAll('[data-edge-label-control]').forEach(control => {
      control.disabled = !edgeSelected || itemIsLocked(item);
      control.value = edgeSelected ? String(item.label || '') : '';
    });
    document.querySelectorAll('[data-edge-port-control]').forEach(control => {
      control.disabled = !edgeSelected || itemIsLocked(item);
      control.value = edgeSelected ? String(item[control.dataset.edgePortControl] || 'auto') : 'auto';
    });
    document.querySelectorAll('[data-edge-style-control]').forEach(control => {
      control.disabled = !edgeSelected || itemIsLocked(item);
      const key = control.dataset.edgeStyleControl;
      const readers = {
        kind: () => String(item.kind || 'solid'),
        direction: () => edgeDirection(item),
        arrow: () => edgeArrow(item),
        corners: () => edgeCorners(item),
        stroke: () => edgeThemeStroke(item) || canvasPalette().wire,
        width: () => String(Number(item.style?.width) || item.width || 1.4),
      };
      const value = !edgeSelected ? '' : (readers[key] || readers.kind)();
      // Only a drop-down keeps a list of options. Asked what kind it is, a
      // browser without a colour picker answers 'text' for the colour field,
      // and reading options off it would throw where the picker is missing.
      if (control.tagName !== 'SELECT') {
        control.value = value;
        return;
      }
      control.querySelectorAll('option[data-transient]').forEach(option => {
        if (option.value !== value) option.remove();
      });
      if (value && ![...control.options].some(option => option.value === value)) {
        const extra = document.createElement('option');
        extra.value = value;
        extra.textContent = value;
        extra.dataset.transient = 'true';
        control.append(extra);
      }
      control.value = value;
    });
    document.querySelectorAll('[data-edge-label-field]').forEach(control => {
      const placement = edgeSelected && item.labelPlacement?.mode === 'manual'
        ? item.labelPlacement : null;
      control.disabled = !edgeSelected || itemIsLocked(item);
      control.value = edgeSelected
        ? String(Number(placement?.[control.dataset.edgeLabelField]) || 0) : '';
    });
    document.querySelectorAll('[data-edge-label-reset]').forEach(button => {
      button.disabled = !edgeSelected || itemIsLocked(item)
        || item.labelPlacement?.mode !== 'manual';
    });
    // the whole selection, as the display actions treat it (displayTargets)
    const displayed = [...new Set([
      ...nodes,
      ...selectedBoundaries().flatMap(holder => state.nodes.filter(
        node => node.boundaryId && isBoundaryDescendant(node.boundaryId, holder.id),
      )),
    ])];
    document.querySelectorAll('[data-display-mode]').forEach(button => {
      // a panel is a box in either look, so it leaves the choice nothing to do
      const enabled = displayed.some(node => !itemIsLocked(node) && !isPanel(node));
      button.disabled = !enabled;
      button.setAttribute('aria-pressed', String(enabled && displayed.every(
        node => (node.displayMode || 'card') === button.dataset.displayMode,
      )));
    });
    const routing = state.canvas.routeAroundNodes === false ? 'direct' : 'around';
    document.querySelectorAll('[data-inspector-routing] [data-routing]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.routing === routing));
    });
    const display = state.canvas.displayMode === 'icon' ? 'icon' : 'card';
    document.querySelectorAll('[data-inspector-crossings] [data-crossings]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.crossings === crossingStyle()));
    });
    document.querySelectorAll('[data-inspector-frame-lines] [data-frame-lines]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.frameLines === state.canvas.frameLines));
    });
    document.querySelectorAll('[data-inspector-display] [data-project-display]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.projectDisplay === display));
    });
    const inspectorGrid = document.querySelector('[data-inspector-grid-toggle]');
    if (inspectorGrid) {
      inspectorGrid.setAttribute('aria-checked', String(state.canvas.showGrid === true));
    }
    syncColorReadouts();
  };
