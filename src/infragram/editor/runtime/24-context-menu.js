// @module 24-context-menu: the canvas context menu
  let contextPoint = null;
  // Opened on empty canvas, the menu offers what concerns the whole drawing:
  // paste, and the lenses.
  let canvasMenu = false;
  const submenu = contextMenu.querySelector('[data-context-submenu-menu]');
  const submenuToggle = contextMenu.querySelector('[data-context-submenu-toggle]');
  const closeSubmenu = () => {
    if (!submenu) return;
    submenu.hidden = true;
    submenuToggle.setAttribute('aria-expanded', 'false');
  };
  // More actions opens beside the menu, on the side with room for it
  const openSubmenu = ({focus = false} = {}) => {
    if (!submenu || submenuToggle.closest('[hidden]')) return;
    submenu.hidden = false;
    submenuToggle.setAttribute('aria-expanded', 'true');
    const row = submenuToggle.getBoundingClientRect();
    const menu = contextMenu.getBoundingClientRect();
    const box = submenu.getBoundingClientRect();
    const width = document.documentElement.clientWidth;
    const height = document.documentElement.clientHeight;
    const left = menu.right + 2 + box.width <= width - 8 ? menu.right + 2 : menu.left - 2 - box.width;
    submenu.style.left = `${clamp(left, 8, width - box.width - 8)}px`;
    submenu.style.top = `${clamp(row.top - 5, 8, height - box.height - 8)}px`;
    if (focus) menuRows(submenu)[0]?.focus({preventScroll: true});
  };
  const closeContextMenu = () => {
    closeSubmenu();
    contextMenu.hidden = true;
  };
  // the rows a reader can reach in one menu, the submenu's not counted in its parent's
  const menuRows = menu => [...menu.querySelectorAll('button')].filter(button => (
    !button.disabled && button.closest('[role="menu"]') === menu && button.getClientRects().length
  ));
  // A divider shows only between two groups that both show something.
  const tidyDividers = menu => {
    let pending = null;
    let seen = false;
    [...menu.children].forEach(element => {
      if (element.classList.contains('md-divider')) {
        element.classList.add('is-redundant');
        if (!element.hidden && seen) pending = element;
        return;
      }
      if (element.hidden) return;
      pending?.classList.remove('is-redundant');
      pending = null;
      seen = true;
    });
  };
  // Centre on item: the selection's middle to the viewport's middle.
  const centerOnSelection = () => {
    const elements = selected?.type === 'edge'
      ? [diagram.querySelector(`[data-edge-group="${CSS.escape(selected.id)}"]`)]
      : [
        ...[...selectedNodeIds].map(id => diagram.querySelector(`[data-graph-node][data-node-id="${CSS.escape(id)}"]`)),
        ...[...selectedBoundaryIds].map(id => diagram.querySelector(`[data-graph-boundary][data-boundary-id="${CSS.escape(id)}"]`)),
      ];
    const boxes = elements.filter(Boolean).map(element => element.getBoundingClientRect())
      .filter(box => box.width || box.height);
    if (!boxes.length) return;
    const x = (Math.min(...boxes.map(box => box.left)) + Math.max(...boxes.map(box => box.right))) / 2;
    const y = (Math.min(...boxes.map(box => box.top)) + Math.max(...boxes.map(box => box.bottom))) / 2;
    const view = viewport.getBoundingClientRect();
    leaveFitMode();
    viewport.scrollBy({
      left: x - (view.left + view.width / 2),
      top: y - (view.top + view.height / 2),
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    });
  };
  const lensActive = (type, tag) => flowFocus?.type === type
    && (type !== 'tag' || `${flowFocus.key}=${flowFocus.value}` === tag);
  // The tags the drawing's cards wear, most worn first, as menu entries.
  const TAG_ENTRIES = 12;
  const fillTagEntries = () => {
    const holder = contextMenu.querySelector('[data-context-tags]');
    if (!holder) return;
    const worn = new Map();
    state.nodes.forEach(node => Object.entries(nodeTags(node)).forEach(([key, value]) => {
      const tag = `${key}=${value}`;
      worn.set(tag, (worn.get(tag) || 0) + 1);
    }));
    const tags = [...worn].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, TAG_ENTRIES);
    holder.replaceChildren(...tags.map(([tag, count]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'md-list-item';
      button.setAttribute('role', 'menuitemcheckbox');
      button.setAttribute('aria-checked', String(lensActive('tag', tag)));
      button.dataset.contextAction = 'lens-tag';
      button.setAttribute('data-tag', tag);
      const slot = document.createElement('span');
      slot.className = 'md-menu__icon';
      const label = document.createElement('span');
      label.className = 'md-list-item__label';
      label.textContent = `Show ${tag} (${count})`;
      button.append(slot, label);
      return button;
    }));
    holder.hidden = !canvasMenu || !tags.length;
  };
  const openInspectorPanel = panel => {
    setInspectorCollapsed(false);
    document.querySelector(`[data-inspector-tab="${panel}"]`)?.click();
  };
  const updateContextMenu = () => {
    // On the canvas only its own entries show; what that hid comes back for
    // the next menu, where the rules below decide as before.
    [...contextMenu.children].forEach(element => {
      if (element.hasAttribute('data-context-canvas-only')) {
        element.hidden = !canvasMenu;
      } else if (canvasMenu && !element.hasAttribute('data-context-canvas')) {
        if (!element.hidden) element.dataset.canvasHid = 'true';
        element.hidden = true;
      } else if (element.dataset.canvasHid) {
        element.hidden = false;
        delete element.dataset.canvasHid;
      }
    });
    fillTagEntries();
    // the view's entries are the same wherever the menu opens
    contextMenu.querySelector('[data-context-action="zoom-in"]').disabled = zoom >= MAX_ZOOM;
    contextMenu.querySelector('[data-context-action="zoom-out"]').disabled = zoom <= MIN_ZOOM;
    contextMenu.querySelector('[data-context-action="scroll-pans"]')
      .setAttribute('aria-checked', String(Boolean(layoutState.scrollPans)));
    const dependents = contextMenu.querySelector('[data-context-action="lens-dependents"]');
    if (dependents) dependents.setAttribute('aria-checked', String(lensActive('dependents')));
    if (canvasMenu) {
      const title = contextMenu.querySelector('[data-context-menu-title]');
      if (title) title.textContent = 'Drawing';
      const facts = contextMenu.querySelector('[data-context-menu-facts]');
      if (facts) facts.hidden = true;
      const paste = contextMenu.querySelector('[data-context-action="paste"]');
      if (paste) {
        paste.hidden = false;
        paste.disabled = !clipboard;
      }
      const internet = contextMenu.querySelector('[data-context-action="lens-internet"]');
      internet.disabled = !state.nodes.some(nodeIsInternet);
      internet.setAttribute('aria-checked', String(lensActive('internet')));
      const cost = contextMenu.querySelector('[data-context-action="lens-cost"]');
      cost.disabled = !state.nodes.some(node => nodeMonthly(node) !== null);
      cost.setAttribute('aria-checked', String(lensActive('cost')));
      // what an Azure import read: offered only where it read something
      [['changes', changedLately], ['findings', hasFindings], ['refresh', refreshedSince]].forEach(([type, lit]) => {
        const entry = contextMenu.querySelector(`[data-context-action="lens-${type}"]`);
        if (!entry) return;
        entry.hidden = !([...state.nodes, ...state.boundaries].some(lit)
          || (type === 'refresh' && refreshFoundAny()));
        entry.setAttribute('aria-checked', String(lensActive(type)));
      });
      tidyDividers(contextMenu);
      return;
    }
    const item = selectedItem();
    const type = selected?.type || '';
    const objects = selectedObjects();
    const locked = item ? itemIsLocked(item) : true;
    const title = contextMenu.querySelector('[data-context-menu-title]');
    if (title) {
      title.textContent = objects.length > 1
        ? `${objects.length} items selected`
        : type === 'edge' ? (item?.label || 'Connector') : (item?.name || 'Selection');
    }
    // what the item is -- its component, frame, layer; a wire's ends; a
    // frame's parent and contents -- the facts a hover card used to show
    const facts = contextMenu.querySelector('[data-context-menu-facts]');
    if (facts) {
      const selector = type === 'node' ? `[data-graph-node][data-node-id="${CSS.escape(item?.id || '')}"]`
        : type === 'boundary' ? `[data-graph-boundary][data-boundary-id="${CSS.escape(item?.id || '')}"]`
          : type === 'edge' ? `[data-graph-edge][data-edge-id="${CSS.escape(item?.id || '')}"]` : '';
      const element = (objects.length === 1 || type === 'edge') && selector ? diagram.querySelector(selector) : null;
      const rows = (element && tooltipRows(element, {menu: true}) || []).slice(1)
        .filter(([label, value]) => value && label !== 'Details');
      facts.innerHTML = rows.map(([label, value]) => (label
        ? `<div><dt>${escapeText(label)}</dt><dd>${escapeText(value)}</dd></div>`
        : `<div class="context-menu-facts__line"><dd>${escapeText(value)}</dd></div>`)).join('');
      facts.hidden = !rows.length;
    }
    contextMenu.querySelectorAll('[data-context-node-only]').forEach(element => {
      element.hidden = type !== 'node';
    });
    contextMenu.querySelectorAll('[data-context-frame-only]').forEach(element => {
      element.hidden = type !== 'boundary';
    });
    contextMenu.querySelectorAll('[data-context-object-only]').forEach(element => {
      element.hidden = !['node', 'boundary'].includes(type);
    });
    // one item's details: a selection of several has no one item to inspect
    const details = contextMenu.querySelector('[data-context-details]');
    if (details) details.hidden = !item || (type !== 'edge' && objects.length !== 1);
    const parts = contextMenu.querySelector('[data-context-parts]');
    if (parts) {
      parts.hidden = type !== 'node' || !attachedParts(item).length;
      parts.textContent = item && partsShownFor(item).length
        ? 'Hide attached on canvas' : `Show attached on canvas (${attachedParts(item).length})`;
    }
    const edit = contextMenu.querySelector('[data-context-action="edit-text"]');
    edit.hidden = !['node', 'boundary', 'edge'].includes(type);
    const comment = contextMenu.querySelector('[data-context-action="comment-add"]');
    if (comment) comment.hidden = !['node', 'boundary', 'edge'].includes(type);
    edit.disabled = locked;
    const resetLabel = contextMenu.querySelector('[data-context-action="reset-label-position"]');
    if (resetLabel) {
      resetLabel.hidden = type !== 'edge';
      resetLabel.disabled = locked || item?.labelPlacement?.mode !== 'manual';
    }
    contextMenu.querySelectorAll('[data-context-edge-only]').forEach(element => {
      element.hidden = type !== 'edge';
      element.disabled = locked;
    });
    const resetRoute = contextMenu.querySelector('[data-context-action="edge-reset-route"]');
    if (resetRoute && type === 'edge') resetRoute.disabled = locked || !edgeRouteIsManual(item);
    ['duplicate', 'copy'].forEach(action => {
      const button = contextMenu.querySelector(`[data-context-action="${action}"]`);
      if (button) button.disabled = !objects.length;
    });
    // on an item, Paste is offered once there is something to paste
    const paste = contextMenu.querySelector('[data-context-action="paste"]');
    if (paste) paste.hidden = !clipboard;
    const arrange = contextMenu.querySelector('[data-context-action="open-arrange"]');
    arrange.hidden = !['node', 'boundary'].includes(type);
    const displayed = type === 'node' ? displayTargets() : [];
    contextMenu.querySelectorAll('[data-context-action="display-card"],[data-context-action="display-icon"]')
      .forEach(button => {
        const mode = button.dataset.contextAction === 'display-icon' ? 'icon' : 'card';
        button.disabled = !displayed.some(node => !itemIsLocked(node));
        button.setAttribute('aria-checked', String(Boolean(displayed.length)
          && displayed.every(node => (node.displayMode || 'card') === mode)));
      });
    ['to-front', 'forward', 'backward', 'to-back'].forEach(action => {
      const button = contextMenu.querySelector(`[data-context-action="${action}"]`);
      if (button) button.disabled = locked;
    });
    const group = contextMenu.querySelector('[data-context-action="group"]');
    if (group) group.disabled = objects.length < 2 || objects.every(item => itemIsLocked(item));
    const ungroup = contextMenu.querySelector('[data-context-action="ungroup"]');
    if (ungroup) ungroup.disabled = type !== 'boundary' || !item?.userGroup || locked;
    const detach = contextMenu.querySelector('[data-context-action="detach"]');
    if (detach) {
      detach.disabled = !objects.some(object => (
        !itemIsLocked(object) && (object.boundaryId || object.parentId)
      ));
    }
    const shrink = contextMenu.querySelector('[data-context-action="shrink-fit"]');
    if (shrink) {
      shrink.disabled = type !== 'boundary' || locked || !(
        state.nodes.some(node => node.boundaryId === item?.id)
        || state.boundaries.some(boundary => boundary.parentId === item?.id)
      );
    }
    const frameMembers = type === 'boundary' && item
      ? state.nodes.filter(node => node.boundaryId && isBoundaryDescendant(node.boundaryId, item.id)) : [];
    const highlight = contextMenu.querySelector('[data-context-action="frame-highlight"]');
    if (highlight) {
      highlight.disabled = type !== 'boundary' || locked;
      highlight.setAttribute('aria-checked', String(type === 'boundary' && Boolean(item?.highlight)));
    }
    ['icon', 'card'].forEach(mode => {
      const show = contextMenu.querySelector(`[data-context-action="frame-display-${mode}"]`);
      if (show) {
        show.disabled = !frameMembers.some(node => !itemIsLocked(node) && (node.displayMode || 'card') !== mode)
          && !(mode === 'icon' && tangledIcons(frameMembers));
      }
    });
    const review = contextMenu.querySelector('[data-context-action="frame-review"]');
    if (review) review.disabled = type !== 'boundary';
    const lock = contextMenu.querySelector('[data-context-action="lock"]');
    if (lock) (lock.querySelector('.md-list-item__label') || lock).textContent = objects.length && objects.every(object => object.locked) ? 'Unlock' : 'Lock';
    const remove = contextMenu.querySelector('[data-context-action="delete"]');
    if (remove) {
      remove.disabled = type === 'edge'
        ? locked
        : !objects.some(object => !itemIsLocked(object));
    }
    if (submenu) {
      tidyDividers(submenu);
      // nothing in More actions applies: the entry is not offered
      submenuToggle.closest('[data-context-submenu]').hidden = ![...submenu.querySelectorAll('button')]
        .some(button => !button.hidden);
    }
    tidyDividers(contextMenu);
  };
  const showContextMenu = event => {
    const point = toSvgPoint(event.clientX, event.clientY);
    const nodeElement = event.target.closest('[data-graph-node]');
    const edgeElement = event.target.closest('[data-edge-label],[data-graph-edge],[data-edge-hit]');
    const boundaryElement = event.target.closest('[data-graph-boundary]');
    const node = nodeElement ? nodeById(nodeElement.dataset.nodeId) : nodeHitAt(point);
    const edge = !node && edgeElement
      ? edgeById(
        edgeElement.dataset.edgeId || edgeElement.dataset.edgeLabel || edgeElement.dataset.edgeHit,
      ) : null;
    const boundary = !node && !edge && boundaryElement
      ? (boundaryHitAt(point) || boundaryById(boundaryElement.dataset.boundaryId)) : null;
    canvasMenu = !node && !edge && !boundary;
    // a lens stays while the menu is open, so its entry shows the tick
    const lens = LENSES.includes(flowFocus?.type) ? flowFocus : null;
    if (node && !isNodeSelected(node.id)) selectNode(node.id);
    else if (boundary && !isBoundarySelected(boundary.id)) selectBoundary(boundary.id);
    else if (edge) {
      selectEdge(edge.id);
    }
    if (lens) flowFocus = lens;
    renderGraph();
    closeSubmenu();
    contextMenu.hidden = false;
    updateContextMenu();
    contextMenu.style.left = `${event.clientX}px`;
    contextMenu.style.top = `${event.clientY}px`;
    const box = contextMenu.getBoundingClientRect();
    contextMenu.style.left = `${clamp(event.clientX, 8, document.documentElement.clientWidth - box.width - 8)}px`;
    contextMenu.style.top = `${clamp(event.clientY, 8, document.documentElement.clientHeight - box.height - 8)}px`;
    contextMenu.querySelector('button:not([hidden]):not(:disabled)')?.focus({preventScroll: true});
  };
  diagram.addEventListener('contextmenu', event => {
    event.preventDefault();
    // a finger held down opens the menu itself (20-zoom-and-pan)
    if (event.pointerType === 'touch' || activeTouchPoints.size) return;
    // A right-click in the middle of a drag drops what was being drawn or
    // shaped, and asks for nothing else.
    if (connection || drag) {
      abandonGesture();
      renderGraph();
      return;
    }
    // where the menu was opened, so a paste lands under the pointer
    contextPoint = toSvgPoint(event.clientX, event.clientY);
    showContextMenu(event);
  });
  // a click opens it even when the pointer already has: it never closes it
  // under the hand that reached for it
  submenuToggle?.addEventListener('click', () => openSubmenu({focus: true}));
  // a pointer resting on More actions opens it; resting on another row closes it
  contextMenu.addEventListener('pointerover', event => {
    if (event.pointerType === 'touch') return;
    const row = event.target.closest('button');
    if (!row || submenu?.contains(row)) return;
    if (row === submenuToggle) openSubmenu();
    else if (row.closest('[role="menu"]') === contextMenu) closeSubmenu();
  });
  // Up and down step through the rows, right opens More actions, left
  // closes it. The keys stop here: on the canvas they would nudge the
  // selection behind the menu.
  contextMenu.addEventListener('keydown', event => {
    const keys = ['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Home', 'End'];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    const inSubmenu = Boolean(submenu?.contains(document.activeElement));
    if (event.key === 'ArrowRight' && document.activeElement === submenuToggle) {
      openSubmenu({focus: true});
      return;
    }
    if (event.key === 'ArrowLeft' && inSubmenu) {
      closeSubmenu();
      submenuToggle.focus({preventScroll: true});
      return;
    }
    const rows = menuRows(inSubmenu ? submenu : contextMenu);
    if (!rows.length) return;
    const at = rows.indexOf(document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1
      : event.key === 'ArrowDown' ? (at + 1) % rows.length
        : event.key === 'ArrowUp' ? (at - 1 + rows.length) % rows.length : at;
    rows[Math.max(0, next)]?.focus({preventScroll: true});
  });
  contextMenu.addEventListener('click', event => {
    const button = event.target.closest('[data-context-action]');
    if (!button || button.disabled) return;
    const action = button.dataset.contextAction;
    const item = selectedItem();
    closeContextMenu();
    // the view's entries do what the toolbar's buttons do
    const view = {
      'zoom-in': 'zoom-in', 'zoom-out': 'zoom-out', 'zoom-fit': 'zoom-fit',
      'zoom-reset': 'zoom-reset', 'tidy-layout': 'tidy-layout',
    }[action];
    if (view) {
      document.querySelector(`[data-editor-action="${view}"]`)?.click();
      return;
    }
    if (action === 'scroll-pans') {
      layoutState.scrollPans = !layoutState.scrollPans;
      persistLayout();
      setStatus(layoutState.scrollPans
        ? 'Scroll moves the map · Ctrl+scroll zooms'
        : 'Scroll zooms the map');
      return;
    }
    if (action === 'center') {
      centerOnSelection();
      return;
    }
    if (action.startsWith('lens-')) {
      // an entry with its tick on ends the lens; Escape and a click on empty canvas do too
      const [key, ...rest] = String(button.dataset.tag || '').split('=');
      const lens = {
        'lens-dependents': {type: 'dependents', id: item?.id},
        'lens-internet': {type: 'internet'},
        'lens-cost': {type: 'cost'},
        'lens-changes': {type: 'changes'},
        'lens-findings': {type: 'findings'},
        'lens-refresh': {type: 'refresh'},
        'lens-tag': {type: 'tag', key, value: rest.join('=')},
      }[action];
      if (button.getAttribute('aria-checked') === 'true') clearSelection();
      else {
        showLens(lens);
        // what was removed has nothing left to light: the status says it
        if (lens.type === 'refresh') setStatus(refreshSummary());
      }
      renderGraph();
      return;
    }
    if (action === 'duplicate') duplicateSelection();
    else if (action === 'copy') copySelection();
    else if (action === 'paste') pasteClipboard(contextPoint);
    else if (action === 'edit-text') openTextEditor(item, selected?.type);
    else if (action === 'details') {
      // a card with links or a price shows its popup; anything else, the inspector
      if (selected?.type === 'node' && item && popupContent(item).any) openElementDetails(item.id);
      else openInspectorPanel('style');
    }
    else if (action === 'toggle-parts') toggleAttachedParts(item?.id);
    else if (action === 'reset-label-position') resetEdgeLabelPosition(item?.id);
    else if (action === 'edge-reverse') forEachSelectedEdge(reverseEdge);
    else if (action === 'edge-reset-route') forEachSelectedEdge(resetEdgeRoute);
    else if (action === 'open-style') openInspectorPanel('style');
    else if (action === 'open-arrange') openInspectorPanel('arrange');
    else if (action === 'display-card') setNodeDisplayMode('card');
    else if (action === 'display-icon') setNodeDisplayMode('icon');
    else if (action === 'frame-highlight') setFrameHighlight(item?.id, !item?.highlight);
    else if (action === 'frame-display-icon') setFrameDisplayMode(item?.id, 'icon');
    else if (action === 'frame-display-card') setFrameDisplayMode(item?.id, 'card');
    else if (action === 'frame-review') openFrameReview(item?.id);
    else if (action === 'frame-open') openFrame(item?.id);
    else if (action === 'comment-add') openCommentFor(selected?.type, item);
    else if (action === 'delete') deleteSelection();
    else arrangeSelection(action);
  });
  document.addEventListener('pointerdown', event => {
    if (!contextMenu.hidden && !contextMenu.contains(event.target)) closeContextMenu();
  }, true);
  viewport.addEventListener('scroll', closeContextMenu, {passive: true});
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !contextMenu.hidden) {
      event.preventDefault();
      event.stopImmediatePropagation();
      closeContextMenu();
    }
  });
