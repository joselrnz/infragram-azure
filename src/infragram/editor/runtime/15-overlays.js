// @module 15-overlays: selection overlay, selection toolbar, layers panel rows and element popup
  const ensureObjectOrders = () => {
    state.nodes.forEach((node, index) => {
      if (!Number.isFinite(Number(node.order))) node.order = index;
    });
    state.boundaries.forEach((boundary, index) => {
      if (!Number.isFinite(Number(boundary.order))) boundary.order = index;
    });
  };
  const objectBounds = object => ({
    left: object.x, top: object.y,
    right: object.x + object.width, bottom: object.y + object.height,
  });
  const selectionBounds = () => {
    const objects = selectedObjects();
    if (!objects.length) return null;
    return {
      left: Math.min(...objects.map(object => object.x)),
      top: Math.min(...objects.map(object => object.y)),
      right: Math.max(...objects.map(object => object.x + object.width)),
      bottom: Math.max(...objects.map(object => object.y + object.height)),
    };
  };
  const selectionOverlayMarkup = () => {
    const bounds = selectionBounds();
    if (!bounds || selectedObjects().length < 2) return '';
    return `<rect data-selection-bbox x="${bounds.left - 6}" y="${bounds.top - 6}" width="${bounds.right - bounds.left + 12}" height="${bounds.bottom - bounds.top + 12}" rx="6" fill="none" stroke="${canvasPalette().accent}" stroke-width="1.5" stroke-dasharray="7 5" pointer-events="none"/>`;
  };
  const marqueeMarkup = () => {
    if (!marqueeSelection) return '';
    const left = Math.min(marqueeSelection.start.x, marqueeSelection.current.x);
    const top = Math.min(marqueeSelection.start.y, marqueeSelection.current.y);
    const width = Math.abs(marqueeSelection.current.x - marqueeSelection.start.x);
    const height = Math.abs(marqueeSelection.current.y - marqueeSelection.start.y);
    return `<rect data-marquee-selection data-mode="${marqueeSelection.intersect ? 'intersect' : 'contain'}" x="${left}" y="${top}" width="${width}" height="${height}" fill="${canvasPalette().accent}" fill-opacity=".08" stroke="${canvasPalette().accent}" stroke-width="1" stroke-dasharray="5 4" pointer-events="none"/>`;
  };
  // The toolbar floats centred above what it acts on -- and inside the
  // visible canvas. Centred on a component near an edge, it used to run
  // off the canvas: by the left edge the count and both align buttons went
  // behind the sidebar, and at the top the whole toolbar left the view. It
  // slides back in along the edge, and flips below what it acts on when
  // there is no room above. Called once the buttons that show are settled,
  // since they set its width.
  const placeSelectionToolbar = (toolbar, x, above, below, handles = []) => {
    const margin = 8;
    const width = toolbar.offsetWidth;
    const height = toolbar.offsetHeight;
    const low = viewport.scrollLeft + width / 2 + margin;
    const high = viewport.scrollLeft + viewport.clientWidth - width / 2 - margin;
    const centre = low > high ? viewport.scrollLeft + viewport.clientWidth / 2 : clamp(x, low, high);
    // Connector handles must stay reachable even when a label anchors the
    // toolbar beside a bend. Move the automatic toolbar clear of any handle
    // it would cover; a toolbar explicitly pinned by the user stays put.
    const frame = viewport.getBoundingClientRect();
    const boxes = handles.map(handle => handle.getBoundingClientRect()).map(box => ({
      left: box.left - frame.left + viewport.scrollLeft,
      right: box.right - frame.left + viewport.scrollLeft,
      top: box.top - frame.top + viewport.scrollTop,
      bottom: box.bottom - frame.top + viewport.scrollTop,
    })).filter(box => box.right + margin > centre - width / 2
      && box.left - margin < centre + width / 2);
    for (let pass = 0; pass < boxes.length; pass += 1) {
      const aboveHits = boxes.filter(box => box.bottom + margin > above - height && box.top - margin < above);
      const belowHits = boxes.filter(box => box.bottom + margin > below && box.top - margin < below + height);
      if (aboveHits.length) above = Math.min(...aboveHits.map(box => box.top - margin));
      if (belowHits.length) below = Math.max(...belowHits.map(box => box.bottom + margin));
      if (!aboveHits.length && !belowHits.length) break;
    }
    const roomAbove = above - height >= viewport.scrollTop + margin;
    toolbar.style.left = `${centre}px`;
    toolbar.style.top = `${roomAbove ? above : below}px`;
    toolbar.style.transform = roomAbove ? '' : 'translate(-50%, 0)';
  };
  // The selection toolbar can be moved out of the way. Dragged by its grip
  // it stays where it was put in the visible canvas -- over every selection
  // after, through scrolling and zooming -- until the grip is double-clicked.
  // Where it was put is kept with the panels' layout. The point is the
  // toolbar's bottom middle, as its stylesheet transform anchors it. Placed
  // last, once the buttons that show have set its width.
  const pinnedToolbarPoint = (toolbar, point) => {
    const halfWidth = toolbar.offsetWidth / 2 + 8;
    const height = toolbar.offsetHeight + 8;
    return {
      x: Math.round(Math.min(Math.max(point.x, halfWidth), Math.max(halfWidth, viewport.clientWidth - halfWidth))),
      y: Math.round(Math.min(Math.max(point.y, height), Math.max(height, viewport.clientHeight - 8))),
    };
  };
  const toolbarPin = () => {
    const pin = layoutState.selectionToolbar;
    return pin && Number.isFinite(pin.x) && Number.isFinite(pin.y) ? pin : null;
  };
  const placePinnedToolbar = toolbar => {
    const pin = toolbarPin();
    toolbar.toggleAttribute('data-pinned', Boolean(pin));
    if (!pin) return;
    const point = pinnedToolbarPoint(toolbar, pin);
    toolbar.style.transform = '';
    toolbar.style.left = `${viewport.scrollLeft + point.x}px`;
    toolbar.style.top = `${viewport.scrollTop + point.y}px`;
  };
  const toolbarGrip = document.querySelector('[data-selection-toolbar-grip]');
  let toolbarDrag = null;
  toolbarGrip?.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    const toolbar = toolbarGrip.closest('[data-selection-toolbar]');
    const box = toolbar.getBoundingClientRect();
    const frame = viewport.getBoundingClientRect();
    toolbarDrag = {
      pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY, moved: false,
      x: box.left + box.width / 2 - frame.left - viewport.clientLeft,
      y: box.bottom - frame.top - viewport.clientTop,
    };
    toolbarGrip.setPointerCapture(event.pointerId);
    toolbar.setAttribute('data-dragging', '');
    event.preventDefault();
  });
  toolbarGrip?.addEventListener('pointermove', event => {
    if (!toolbarDrag || event.pointerId !== toolbarDrag.pointerId) return;
    const dx = event.clientX - toolbarDrag.clientX;
    const dy = event.clientY - toolbarDrag.clientY;
    // A press that barely moves is a click, and leaves the toolbar following.
    if (!toolbarDrag.moved && Math.hypot(dx, dy) < 4) return;
    toolbarDrag.moved = true;
    const toolbar = toolbarGrip.closest('[data-selection-toolbar]');
    layoutState.selectionToolbar = pinnedToolbarPoint(toolbar, {x: toolbarDrag.x + dx, y: toolbarDrag.y + dy});
    placePinnedToolbar(toolbar);
  });
  const endToolbarDrag = event => {
    if (!toolbarDrag || event.pointerId !== toolbarDrag.pointerId) return;
    const {moved} = toolbarDrag;
    toolbarDrag = null;
    toolbarGrip.closest('[data-selection-toolbar]').removeAttribute('data-dragging');
    if (moved) persistLayout();
  };
  toolbarGrip?.addEventListener('pointerup', endToolbarDrag);
  toolbarGrip?.addEventListener('pointercancel', endToolbarDrag);
  toolbarGrip?.addEventListener('dblclick', () => {
    layoutState.selectionToolbar = null;
    persistLayout();
    updateSelectionToolbar();
  });
  const updateSelectionToolbar = () => {
    const toolbar = document.querySelector('[data-selection-toolbar]');
    // A selected connector gets its own toolbar at the middle of its wire:
    // edit the label, reverse it, reset its route, delete it.
    const chosenEdge = toolbar && selected?.type === 'edge' && !drag && !connection
      ? edgeGeometry().find(item => item.edge.id === selected.id) : null;
    // Several wires at once: the label is one wire's, the rest apply to all.
    const manyEdges = Boolean(chosenEdge) && selectedEdgeIds.size > 1;
    toolbar?.querySelectorAll('[data-edge-only]').forEach(element => { element.hidden = !chosenEdge; });
    toolbar?.querySelectorAll('[data-object-only]').forEach(element => { element.hidden = Boolean(chosenEdge); });
    // a frame does not turn; a card does, a quarter at a time
    const rotate = toolbar?.querySelector('[data-selection-action="rotate-90"]');
    if (rotate) rotate.hidden = Boolean(chosenEdge) || !selectedNodes().length;
    if (chosenEdge) {
      connectorPath(chosenEdge);
      const middle = alongPolyline(chosenEdge.routeCorners || tidyCorners(simplePathCorners(chosenEdge)), 0.5);
      const origin = canvasOrigin();
      toolbar.hidden = false;
      let anchorX = origin.x + middle.x * zoom;
      let above = origin.y + middle.y * zoom - 16;
      let below = origin.y + middle.y * zoom + 16;
      // A labelled wire keeps its label clear: the toolbar sits above it, so
      // the label can still be dragged or right-clicked.
      const label = document.querySelector(`[data-edge-label][data-edge-id="${CSS.escape(chosenEdge.edge.id)}"]`);
      const labelRect = label?.getBoundingClientRect();
      if (labelRect?.width) {
        const viewportRect = viewport.getBoundingClientRect();
        anchorX = labelRect.left + labelRect.width / 2 - viewportRect.left + viewport.scrollLeft;
        above = labelRect.top - viewportRect.top + viewport.scrollTop - 8;
        below = labelRect.bottom - viewportRect.top + viewport.scrollTop + 8;
      }
      const locked = itemIsLocked(chosenEdge.edge);
      toolbar.querySelectorAll('[data-edge-only]').forEach(button => { button.disabled = locked; });
      const reset = toolbar.querySelector('[data-selection-action="edge-reset-route"]');
      if (reset) reset.disabled = locked || !edgeRouteIsManual(chosenEdge.edge);
      toolbar.querySelectorAll('[data-selection-action="display-icon"],[data-selection-action="display-card"],[data-selection-detach]')
        .forEach(element => { element.hidden = true; });
      const labelButton = toolbar.querySelector('[data-selection-action="edge-edit-label"]');
      if (labelButton) labelButton.hidden = manyEdges;
      const chip = toolbar.querySelector('[data-selection-count-chip]');
      if (chip) {
        chip.hidden = !manyEdges;
        chip.textContent = String(selectedEdgeIds.size);
      }
      const handles = Array.from(diagram.querySelectorAll('[data-edge-end],[data-edge-bend],[data-edge-bend-ghost]'));
      placeSelectionToolbar(toolbar, anchorX, above, below, handles);
      placePinnedToolbar(toolbar);
      return;
    }
    const bounds = selectionBounds();
    if (!toolbar || !bounds || drag || marqueeSelection || connection) {
      if (toolbar) toolbar.hidden = true;
      return;
    }
    toolbar.hidden = false;
    const origin = canvasOrigin();
    const anchorX = origin.x + ((bounds.left + bounds.right) / 2) * zoom;
    // clear of the connection dots, 10 px off the edge and 7 px across hovered
    const above = origin.y + bounds.top * zoom - 22;
    const below = origin.y + bounds.bottom * zoom + 22;
    const count = toolbar.querySelector('[data-selection-count-chip]');
    if (count) count.textContent = String(selectedObjects().length);
    const detach = toolbar.querySelector('[data-selection-detach]');
    if (detach) {
      const detachable = [
        ...selectedNodes().filter(node => node.boundaryId),
        ...selectedBoundaries().filter(boundary => boundary.parentId),
      ];
      detach.hidden = detachable.length === 0;
      detach.disabled = !detachable.some(item => !itemIsLocked(item));
    }
    // one display button: icons unless everything selected already is one
    const shown = displayTargets();
    const allIcons = shown.length > 0 && shown.every(node => (node.displayMode || 'card') === 'icon');
    const toIcons = toolbar.querySelector('[data-selection-action="display-icon"]');
    const toCards = toolbar.querySelector('[data-selection-action="display-card"]');
    if (toIcons && toCards) {
      toIcons.hidden = !shown.length || allIcons;
      toCards.hidden = !allIcons;
      [toIcons, toCards].forEach(button => { button.disabled = !shown.some(node => !itemIsLocked(node)); });
    }
    const lock = toolbar.querySelector('[data-selection-action="lock"]');
    if (lock) {
      const objects = selectedObjects();
      const layerLocked = objects.some(object => isLayerLocked(object.layerId));
      const individuallyLocked = objects.length > 0
        && objects.every(object => Boolean(object.locked));
      lock.setAttribute('aria-pressed', String(individuallyLocked || layerLocked));
      lock.innerHTML = lockIcon(individuallyLocked || layerLocked);
      lock.title = layerLocked
        ? 'Unlock this library layer in the Layers panel'
        : `${individuallyLocked ? 'Unlock' : 'Lock'} selection`;
      lock.setAttribute('aria-label', lock.title);
      lock.disabled = layerLocked;
    }
    placeSelectionToolbar(toolbar, anchorX, above, below);
    placePinnedToolbar(toolbar);
    // the card's popup keeps clear of the toolbar just placed
    placeElementPopup();
  };

  const renderLayerInspector = () => {
    const list = document.querySelector('[data-layer-list]');
    if (!list) return;
    list.innerHTML = state.layers
      .slice().sort((a, b) => (a.order || 0) - (b.order || 0))
      .map(item => `<div class="md-list-item md-list-item--static layer-row" data-layer-row="${escapeText(item.id)}">
        <input type="checkbox" class="md-checkbox" data-layer-visible="${escapeText(item.id)}" aria-label="Show ${escapeText(item.name)} layer" ${item.visible === false ? '' : 'checked'}>
        <span class="md-list-item__text"><span class="md-list-item__headline">${escapeText(item.name)}</span>${item.kind === 'platform' ? '<span class="md-list-item__supporting">Platform</span>' : ''}</span>
        <button type="button" class="md-icon-button md-icon-button--toggle layer-lock" data-layer-lock="${escapeText(item.id)}" aria-pressed="${Boolean(item.locked)}" aria-label="${item.locked ? 'Unlock' : 'Lock'} ${escapeText(item.name)} layer" title="${item.locked ? 'Unlock' : 'Lock'} layer">${lockIcon(item.locked)}</button>
      </div>`).join('');
    const frameTree = document.querySelector('[data-frame-tree]');
    if (!frameTree) return;
    const rows = [];
    const visit = (parentId = null, depth = 0) => {
      state.boundaries
        .filter(boundary => (boundary.parentId || null) === parentId)
        .sort((a, b) => Number(a.order) - Number(b.order))
        .forEach(boundary => {
          rows.push(`<div class="frame-tree-row" style="--frame-depth:${depth}" data-frame-tree-row="${escapeText(boundary.id)}">
            <button type="button" class="md-list-item md-list-item--dense" data-frame-select="${escapeText(boundary.id)}" aria-pressed="${isBoundarySelected(boundary.id)}" title="Select ${escapeText(boundary.name)}"><span class="md-list-item__headline">${escapeText(boundary.name)}</span></button>
            <button type="button" class="md-icon-button md-icon-button--toggle" data-frame-lock="${escapeText(boundary.id)}" aria-pressed="${Boolean(boundary.locked)}" aria-label="${boundary.locked ? 'Unlock' : 'Lock'} ${escapeText(boundary.name)}" title="${boundary.locked ? 'Unlock' : 'Lock'} frame">${lockIcon(boundary.locked)}</button>
          </div>`);
          visit(boundary.id, depth + 1);
        });
    };
    visit();
    frameTree.innerHTML = rows.join('') || '<p class="empty-category">No frames on canvas</p>';
  };

  // A table an element carries -- a route table's routes -- opens beside the
  // card when that one card is selected, and closes with the selection, so
  // Escape and a click on empty canvas dismiss it too. Nothing is drawn on
  // the canvas: the picture and every export stay exactly as they are, and
  // the table is for the person reading the page.
  //
  // The popup also carries what the card costs, when the export priced it
  // (attributes.price, written by `--prices`), and where the component is read
  // about: its own pages, else a search of its vendor's site for its name
  // (catalog/links.json, carried in the page). A price is shown with what it
  // was priced as, each size the diagram did not state marked assumed.
  const elementPopup = document.querySelector('[data-canvas-popup]');
  let popupDismissedFor = null;
  const COMPONENT_LINKS = (() => {
    const tag = document.getElementById('infragram-component-links');
    try { return JSON.parse(tag?.textContent || '{}') || {}; } catch (error) { return {}; }
  })();
  const componentLinks = node => {
    const id = node.componentQualifiedId || '';
    const own = COMPONENT_LINKS.components?.[id];
    const links = Array.isArray(own) && own.length ? own : (() => {
      const library = COMPONENT_LINKS.libraries?.[node.componentProvider || id.split(':')[0]];
      const name = String(componentDefinitions.get(id)?.name || node.name || '').trim();
      return library?.search && name
        ? [{label: `Search ${library.site}`, url: library.search.replace('{query}', encodeURIComponent(name))}]
        : [];
    })();
    return links.filter(link => /^https:\/\//.test(String(link?.url || '')));
  };
  const SIZING_LABELS = {instance_type: 'Instance type', region: 'Region', os: 'Operating system',
    count: 'Count', hours: 'Hours a month'};
  const money = (value, currency) => {
    try {
      return new Intl.NumberFormat('en-US', {style: 'currency', currency: currency || 'USD',
        minimumFractionDigits: 2, maximumFractionDigits: value < 1 ? 4 : 2}).format(value);
    } catch (error) { return `${currency || 'USD'} ${value}`; }
  };
  const priceSection = price => {
    const sizing = price.sizing && typeof price.sizing === 'object' ? price.sizing : {};
    const assumed = new Set(Array.isArray(price.assumed) ? price.assumed : []);
    const rows = Object.entries(sizing).map(([key, value]) => `<tr><th>${escapeText(SIZING_LABELS[key]
      || key.replaceAll('_', ' '))}</th><td>${escapeText(value)}${assumed.has(key)
      ? ' <em data-popup-assumed>assumed</em>' : ''}</td></tr>`).join('');
    const hours = Number(sizing.hours) || 0;
    const count = Number(sizing.count) || 1;
    // a price made of lines shows each: what is billed, how much, at what rate
    const lines = Array.isArray(price.lines) && price.lines.length
      ? '<table data-popup-lines><tbody>' + price.lines.map(item => `<tr><th>${escapeText(item.label)}`
        + `${item.kind === 'usage' ? ' <em>usage</em>' : ''}</th><td>${escapeText(Number(item.quantity).toLocaleString('en-US', {maximumFractionDigits: 3}))} `
        + `${escapeText(item.unit)}${item.assumed ? ' <em data-popup-assumed>assumed</em>' : ''} × ${escapeText(money(Number(item.rate), price.currency))}</td>`
        + `<td>${escapeText(money(Number(item.amount), price.currency))}</td></tr>`).join('') + '</tbody></table>'
      : '';
    return '<section class="canvas-popup__section" data-popup-price>'
      + `<p class="canvas-popup__amount"><strong>≈ ${escapeText(money(Number(price.monthly), price.currency))}</strong> a month</p>`
      + (lines
        ? `<p class="canvas-popup__note">${escapeText(price.rate || '')}</p>${lines}`
        : `<p class="canvas-popup__note">${escapeText(money(Number(price.hourly), price.currency))} an hour`
          + (hours ? ` × ${escapeText(hours)} hours` : '') + (count !== 1 ? ` × ${escapeText(count)}` : '')
          + ` · ${escapeText(price.rate || '')}</p>`)
      + (rows ? `<table><tbody>${rows}</tbody></table>` : '')
      + `<p class="canvas-popup__note">${escapeText(price.source || '')}`
      + (price.published ? `, published ${escapeText(price.published)}` : '')
      + (price.priced ? `; priced ${escapeText(price.priced)}` : '') + '</p></section>';
  };
  // What a resource carries (a VM's NICs, disks, public IPs) with a switch to
  // show them on the canvas or fold them away, and for a part, what carries it.
  const attachedSection = node => {
    const parts = attachedParts(node);
    const owner = ownerOfPart(node);
    if (!parts.length && !owner) return '';
    if (!parts.length) {
      return '<section class="canvas-popup__section" data-popup-attached>'
        + `<h3>Attached to</h3><p><button type="button" class="md-button md-button--text" data-popup-owner="${escapeText(owner.id)}">`
        + `${escapeText(owner.name)}</button></p></section>`;
    }
    const shown = partsShownFor(node).length > 0;
    return '<section class="canvas-popup__section" data-popup-attached>'
      + `<h3>Attached (${parts.length})</h3><table><tbody>`
      + parts.map(part => `<tr><th>${escapeText(part.role)}</th><td>${escapeText(part.name)}`
        + `${part.detail ? ` · ${escapeText(part.detail)}` : ''}</td></tr>`).join('')
      + '</tbody></table>'
      + `<button type="button" class="md-button md-button--tonal" data-popup-parts aria-pressed="${shown}">`
      + `${shown ? 'Hide attached parts' : 'Show attached parts'}</button></section>`;
  };
  const linksSection = links => '<section class="canvas-popup__section" data-popup-links>'
    + '<h3>Read about it</h3><ul>'
    + links.map(link => `<li><a href="${escapeText(link.url)}" target="_blank" rel="noopener noreferrer">`
      + `${escapeText(link.label)}</a></li>`).join('')
    + '</ul></section>';
  // What a card's popup would hold. It opens by itself for what the author
  // attached -- a table -- and for its price and links only when asked (Details
  // in the card's right-click menu), so selecting a card to move or wire it
  // never puts a popup over the canvas.
  let popupRequestedFor = null;
  const popupContent = node => {
    const table = node?.attributes?.table;
    const price = node?.attributes?.price;
    const hasTable = Array.isArray(table?.columns) && table.columns.length > 0;
    const hasPrice = Boolean(price) && Number.isFinite(Number(price.monthly));
    const links = node ? componentLinks(node) : [];
    // every cloud card carries a price now, so a price alone does not open
    // the popup: Details, or Show on canvas in the Cost tab, asks for it
    const attached = node ? attachedSection(node) : '';
    // in review the selected strip over the inventory says what a card is,
    // so the popup waits for Details rather than covering the map; so it does
    // on a phone while the inventory is open, its sheet under the map being
    // where the popup would go
    const review = document.body.classList.contains('review-mode');
    const inventoryBelow = phoneLayout() && Boolean(document.body.dataset.dock);
    return {table, price, hasTable, hasPrice, links, attached,
      opens: (hasTable || Boolean(attached)) && !review && !inventoryBelow,
      any: hasTable || hasPrice || links.length > 0 || Boolean(attached)};
  };
  // The popup's body: the price worked out, what the card carries, the
  // table its author attached, where to read about it. The inventory's
  // details column shows the same under its own facts (Open details), less
  // what the card carries, which the column lists itself.
  const elementDetailsBody = (node, {attached: withAttached = true} = {}) => {
    const {table, price, hasTable, hasPrice, links, attached} = popupContent(node);
    const rows = hasTable && Array.isArray(table.rows) ? table.rows : [];
    return (hasPrice ? priceSection(price) : '')
      + (withAttached ? attached || '' : '')
      + (hasTable
        ? `<table data-popup-table><thead><tr>${table.columns.map(heading => `<th>${escapeText(heading)}</th>`).join('')}</tr></thead>`
          + `<tbody>${rows.map(row => `<tr>${table.columns.map((_, index) =>
            `<td>${escapeText(Array.isArray(row) ? (row[index] ?? '') : '')}</td>`).join('')}</tr>`).join('')}</tbody></table>`
        : '')
      + (links.length ? linksSection(links) : '');
  };
  // Details (the right-click menu): the selected card's popup, links and all.
  const openElementDetails = id => {
    popupRequestedFor = id;
    popupDismissedFor = null;
    syncElementPopup();
  };
  const syncElementPopup = () => {
    if (!elementPopup) return;
    // the card selected for editing, else the card whose flow is shown
    const node = selected?.type === 'node' && selectedNodeIds.size === 1
      ? nodeById(selected.id)
      : !selected && flowFocus?.type === 'node' ? nodeById(flowFocus.id) : null;
    if (!node) {
      popupDismissedFor = null;
      popupRequestedFor = null;
    }
    // Details asked for one card; selecting another is the end of that ask
    if (popupRequestedFor && popupRequestedFor !== node?.id) popupRequestedFor = null;
    const content = node ? popupContent(node) : null;
    if (!node || popupDismissedFor === node.id || !content.any
        || !(content.opens || popupRequestedFor === node.id)) {
      elementPopup.hidden = true;
      return;
    }
    elementPopup.innerHTML = `<header><strong>${escapeText(node.name)}</strong>`
      + '<button type="button" class="md-icon-button md-icon-button--sm" data-popup-close aria-label="Close" title="Close">'
      + chromeIcon('<path d="M6 6l12 12M18 6 6 18"/>')
      + '</button></header>'
      + elementDetailsBody(node);
    elementPopup.dataset.nodeId = node.id;
    elementPopup.hidden = false;
    placeElementPopup();
  };
  // Beside the card, clear of it and of the selection toolbar over it: right,
  // then left, at the card's top or slid to stay in view; then below or above
  // both. A price, a table and links together can be taller than the room on
  // any side of a card on a zoomed-out page; the popup then takes the roomier
  // of below and above and scrolls, rather than being clamped onto the card
  // it describes. Placed again whenever the toolbar is -- a zoom, a pan, a
  // fit -- since both follow the card. Measured at (0, 0) first, the way the
  // hover tooltip is placed.
  const placeElementPopup = () => {
    if (!elementPopup || elementPopup.hidden) return;
    const card = diagram.querySelector(`[data-graph-node][data-node-id="${CSS.escape(elementPopup.dataset.nodeId || '')}"]`);
    const host = elementPopup.parentElement;
    if (!card || !host) return;
    elementPopup.style.left = '0px';
    elementPopup.style.top = '0px';
    elementPopup.style.maxHeight = '';
    elementPopup.style.width = '';
    const stage = host.getBoundingClientRect();
    const box = elementPopup.getBoundingClientRect();
    // Held at the width it was measured at: placed near the canvas's right
    // edge it would otherwise shrink to the room left there, wrap, and grow
    // taller than the spot it was given -- back over the toolbar or the card.
    elementPopup.style.width = `${Math.ceil(box.width)}px`;
    const gap = 12;
    const edge = 4;
    const viewWidth = host.clientWidth || stage.width;
    const viewHeight = host.clientHeight || stage.height;
    const inView = rect => ({left: rect.left - stage.left, top: rect.top - stage.top,
      right: rect.right - stage.left, bottom: rect.bottom - stage.top});
    const anchor = inView(card.getBoundingClientRect());
    const obstacles = [anchor];
    const toolbar = document.querySelector('[data-selection-toolbar]');
    if (toolbar && !toolbar.hidden) obstacles.push(inView(toolbar.getBoundingClientRect()));
    const width = box.width;
    const clear = (x, y, height) => x >= edge && y >= edge
      && x + width <= viewWidth - edge && y + height <= viewHeight - edge
      && obstacles.every(o => x + width <= o.left || x >= o.right || y + height <= o.top || y >= o.bottom);
    const whole = Math.min(box.height, viewHeight - 2 * edge);
    const slide = y => Math.max(edge, Math.min(y, viewHeight - whole - edge));
    const bar = obstacles[1];
    const sides = [anchor.right + gap, anchor.left - gap - width];
    const heights = [anchor.top, slide(anchor.top), ...(bar ? [bar.bottom + gap, bar.top - gap - whole] : [])];
    let spot = null;
    let height = whole;
    for (const x of sides) {
      const y = heights.find(top => clear(x, top, whole));
      if (y !== undefined) { spot = [x, y]; break; }
    }
    if (!spot) {
      // below or above the card and the toolbar together, scrolling if need be
      const top = Math.min(...obstacles.map(o => o.top));
      const bottom = Math.max(...obstacles.map(o => o.bottom));
      const x = Math.max(edge, Math.min(anchor.left, viewWidth - width - edge));
      const below = viewHeight - edge - (bottom + gap);
      const above = top - gap - edge;
      if (Math.max(below, above) >= Math.min(box.height, 120)) {
        height = Math.min(box.height, Math.max(below, above));
        spot = below >= above ? [x, bottom + gap] : [x, top - gap - height];
      }
    }
    // nowhere clear of the card: at least inside the canvas
    if (!spot) spot = [Math.max(edge, Math.min(sides[0], viewWidth - width - edge)), slide(anchor.top)];
    if (height < box.height) elementPopup.style.maxHeight = `${Math.floor(height)}px`;
    elementPopup.style.left = `${spot[0] + stage.left - box.left}px`;
    elementPopup.style.top = `${spot[1] + stage.top - box.top}px`;
  };
  if (elementPopup) {
    elementPopup.addEventListener('click', event => {
      const owner = event.target.closest('[data-popup-owner]');
      if (owner) {
        // a part's owner: select it, so its popup lists what it carries
        selectNode(owner.dataset.popupOwner);
        renderGraph();
        return;
      }
      if (event.target.closest('[data-popup-parts]')) {
        toggleAttachedParts(elementPopup.dataset.nodeId);
        return;
      }
      if (!event.target.closest('[data-popup-close]')) return;
      popupDismissedFor = selected?.id || null;
      popupRequestedFor = null;
      elementPopup.hidden = true;
    });
    // Presses and wheel turns inside the popup belong to it: selecting text or
    // scrolling a long table must not pan, zoom or deselect the canvas below.
    elementPopup.addEventListener('pointerdown', event => event.stopPropagation());
    elementPopup.addEventListener('wheel', event => event.stopPropagation(), {passive: true});
  }

  // The provider mark is drawn once, below the laid-out picture. Frames grow
  // in the editor (a component switched to an icon, a card dragged down), so
  // the mark moves down with the lowest frame or card and never sits on it;
  // it returns to its drawn place when the content shrinks back.
  // The step list stands right of the drawing, level with its top, as the
  // static picture drew it; it moves right with the rightmost frame or card
  // and returns to its drawn place when they come back.
  const placeStepList = () => {
    const list = diagram.querySelector('[data-step-list]');
    if (!list) return;
    const drawnX = Number(list.getAttribute('data-drawn-x')) || 0;
    const bounds = contentBounds();
    const x = bounds ? Math.max(drawnX, bounds.right + STEP.listGap) : drawnX;
    // beside an open frame (34-drill-down), level with its top
    const drilled = drillPath.length && bounds;
    const transform = drilled
      ? `translate(${bounds.right + STEP.listGap - drawnX} ${bounds.top - list.getBBox().y})`
      : x > drawnX ? `translate(${x - drawnX} 0)` : '';
    if ((list.getAttribute('transform') || '') === transform) return;
    if (transform) list.setAttribute('transform', transform);
    else list.removeAttribute('transform');
  };
  const placeBrandMark = () => {
    const mark = diagram.querySelector('[data-brand-mark]');
    if (!mark) return;
    if (!mark.hasAttribute('data-drawn-y')) mark.setAttribute('data-drawn-y', mark.getAttribute('y') || '0');
    const drawnY = Number(mark.getAttribute('data-drawn-y')) || 0;
    const bounds = drawnBounds();
    const y = bounds ? Math.max(drawnY, bounds.bottom + MARK.gap) : drawnY;
    if (mark.getAttribute('y') !== String(y)) mark.setAttribute('y', String(y));
  };

  const legendEnabled = setting => state.canvas[setting]
    ?? Boolean(originalProject.presentation?.legend?.length || originalProject.presentation?.tones?.length);
  const legendEntries = () => {
    const palette = canvasPalette();
    const visible = new Set(state.nodes.filter(nodeIsVisible).map(node => node.id));
    const edges = state.edges.filter(edge => visible.has(edge.source) && visible.has(edge.target));
    const entries = new Map();
    const authored = new Map(originalProject.presentation?.legend || []);
    edges.forEach(edge => {
      const dash = edgeDash(edge), direction = edgeDirection(edge), arrow = edgeArrow(edge);
      const stroke = edgeThemeStroke(edge) || palette.wire;
      const pattern = dash ? (edge.kind === 'dotted' ? 'Dotted' : 'Dashed') : 'Solid';
      const name = authored.get(edge.kind) || `${pattern} connector`;
      const label = `${name} · ${direction === 'both' ? 'Two-way' : direction === 'none' ? 'No arrow' : 'One-way'}`
        + (direction !== 'none' && arrow !== 'triangle' ? ` · ${arrow[0].toUpperCase() + arrow.slice(1)} arrow` : '');
      // Custom colours do not invent a new meaning for an otherwise identical
      // connector. Keep one representative sample for each described style.
      const key = JSON.stringify([name, dash, direction, arrow]);
      entries.set(key, {label, dash, direction, arrow, stroke, type: 'line'});
    });
    // Explicit template meanings travel even when the template uses a kind
    // whose wires are not present in this particular view.
    authored.forEach((label, kind) => {
      if (edges.some(edge => edge.kind === kind)) return;
      entries.set(`authored:${kind}`, {label, type: 'line', dash: linkStyle(kind)?.dash || EDGE_DASHES[kind] || '',
        direction: 'none', arrow: 'triangle', stroke: linkStyle(kind)?.color || palette.wire});
    });
    // what each tone a box is filled with means (builders/panels.py), in the
    // order the diagram says them
    (originalProject.presentation?.tones || []).forEach(([name, label]) => {
      const tone = toneOf(name);
      if (tone) entries.set(`tone:${name}`, {label, type: 'tone', fill: tone[0], stroke: tone[1]});
    });
    state.boundaries.filter(boundaryIsVisible).forEach(frame => {
      const drawn = darkCanvas() && frame.dark ? {...frame, ...frame.dark} : frame;
      const dash = drawn.dash || '', stroke = drawn.style?.stroke || drawn.stroke || palette.border;
      const key = JSON.stringify(['frame', Boolean(dash)]);
      if (entries.has(key)) return;
      entries.set(key, {label: dash ? 'Dashed boundary / frame' : 'Boundary / frame', type: 'frame', dash, stroke});
    });
    return [...entries.values()];
  };
  const legendLayout = (entries, width = 640) => {
    const columns = width >= 560 ? 2 : 1;
    const columnWidth = width / columns;
    const capacity = Math.max(16, Math.floor((columnWidth - 80) / 6.5));
    const wrap = label => {
      const lines = [''];
      String(label).split(/\s+/).forEach(word => {
        if (lines.at(-1) && lines.at(-1).length + word.length + 1 > capacity) lines.push('');
        // Long words are split too, so a URL cannot cross a second column.
        while (word.length > capacity) {
          if (lines.at(-1)) lines.push('');
          lines[lines.length - 1] = word.slice(0, capacity);
          lines.push('');
          word = word.slice(capacity);
        }
        if (word) lines[lines.length - 1] += (lines.at(-1) ? ' ' : '') + word;
      });
      return lines.filter(Boolean);
    };
    let y = 38;
    const rows = [];
    for (let index = 0; index < entries.length; index += columns) {
      const row = entries.slice(index, index + columns).map((entry, column) => ({...entry,
        lines: wrap(entry.label), x: 16 + column * columnWidth, y}));
      rows.push(...row);
      y += Math.max(...row.map(entry => entry.lines.length)) * 16 + 12;
    }
    return {width, height: y + 8, rows};
  };
  const legendSymbol = (entry, x, y, id) => {
    const stroke = escapeText(entry.stroke), dash = escapeText(entry.dash || '');
    if (entry.type === 'tone') return `<rect data-legend-tone x="${x}" y="${y - 10}" width="32" height="14" rx="2" fill="${escapeText(entry.fill)}" stroke="${stroke}" stroke-width="1"/>`;
    if (entry.type === 'frame') return `<rect x="${x}" y="${y - 10}" width="32" height="14" rx="2" fill="none" stroke="${stroke}" stroke-width="1.5" stroke-dasharray="${dash}"/>`;
    const marker = `url(#${id})`;
    return `<defs>${markerMarkup(id, entry.arrow, stroke)}</defs><line x1="${x}" y1="${y - 3}" x2="${x + 32}" y2="${y - 3}" stroke="${stroke}" stroke-width="1.5" stroke-dasharray="${dash}"`
      + (entry.direction !== 'none' ? ` marker-end="${marker}"` : '')
      + (entry.direction === 'both' ? ` marker-start="${marker}"` : '') + '/>';
  };
  const legendSvg = (layout, x = 0, y = 0) => {
    const palette = canvasPalette();
    const surface = getComputedStyle(diagram).getPropertyValue('--diagram-surface').trim() || '#ffffff';
    return '<g data-legend-strip="">'
      + `<rect x="${x}" y="${y}" width="${layout.width}" height="${layout.height}" rx="8" fill="${escapeText(surface)}" stroke="${escapeText(palette.border)}"/>`
      + `<text x="${x + 16}" y="${y + 24}" fill="${escapeText(palette.text)}" font-family="Arial,sans-serif" font-size="13" font-weight="bold">Legend</text>`
      + layout.rows.map((entry, index) => legendSymbol(entry, x + entry.x, y + entry.y + 5, `infragram-legend-arrow-${index}`)
        + entry.lines.map((line, row) => `<text x="${x + entry.x + 44}" y="${y + entry.y + row * 16 + 5}" fill="${escapeText(palette.text)}" font-family="Arial,sans-serif" font-size="12">${escapeText(line)}</text>`).join('')).join('') + '</g>';
  };
  const updateLegend = () => {
    // The template's original SVG key is replaced by the shared footer key.
    diagram.querySelectorAll('[data-legend-strip]').forEach(strip => strip.setAttribute('display', 'none'));
    const footer = document.querySelector('[data-diagram-legend]');
    if (!footer) return;
    const entries = legendEntries();
    footer.hidden = !legendEnabled('showLegend') || !entries.length;
    if (footer.hidden) { footer.replaceChildren(); return; }
    const width = Math.max(280, Math.min(640, footer.clientWidth - 24));
    const layout = legendLayout(entries, width);
    footer.innerHTML = `<svg xmlns="${SVG_NS}" viewBox="0 0 ${layout.width} ${layout.height}" width="${layout.width}" height="${layout.height}" role="img" aria-label="Diagram legend">${legendSvg(layout)}</svg>`;
  };
  const legendPane = document.querySelector('.canvas-pane');
  if (legendPane) {
    let legendPaneWidth = 0;
    new ResizeObserver(([entry]) => {
      // a drawer opening under the map: the card's popup stays inside it
      placeElementPopup();
      if (entry.contentRect.width === legendPaneWidth) return;
      legendPaneWidth = entry.contentRect.width;
      updateLegend();
    }).observe(legendPane);
  }
