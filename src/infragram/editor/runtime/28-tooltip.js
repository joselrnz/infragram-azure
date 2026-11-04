// @module 28-tooltip: the canvas hover tooltip
  // Hover tooltips. The SVG <title> on each card covers viewers with no
  // script; this is the richer version for the page itself: what the thing
  // is, what it runs, which frame and layer it sits in, and for a wire, what
  // it joins. Positioned off the pointer so it never covers what it names.
  const tooltip = document.querySelector('[data-canvas-tooltip]');
  const tooltipRows = (target, {menu = false} = {}) => {
    // a connection dot or a resize handle says what it does, and only that
    const handle = target.closest('[data-node-port],[data-node-resize]');
    if (handle) return [['', handle.querySelector('title')?.textContent || '']];
    const nodeElement = target.closest('[data-graph-node]');
    if (nodeElement) {
      const node = nodeById(nodeElement.dataset.nodeId);
      if (!node) return null;
      // its details are open already: the popup says all this and more
      if (!menu && elementPopup && !elementPopup.hidden && elementPopup.dataset.nodeId === node.id) return null;
      const frame = node.boundaryId ? boundaryById(node.boundaryId) : null;
      return [
        ['', node.name],
        ['', node.detail || ''],
        ['Component', node.componentQualifiedId || node.componentId || ''],
        ['Frame', frame?.name || ''],
        ['Layer', layerById(node.layerId)?.name || ''],
        ['Details', popupContent(node).links.length ? 'right-click for links' : ''],
      ];
    }
    const edgeElement = target.closest('[data-graph-edge],[data-edge-hit],[data-edge-label]');
    if (edgeElement) {
      const edge = edgeById(edgeElement.dataset.edgeId || edgeElement.dataset.edgeHit);
      if (!edge) return null;
      return [
        ['', edge.label || 'Connector'],
        ['From', nodeById(edge.source)?.name || edge.source],
        ['To', nodeById(edge.target)?.name || edge.target],
        ['Line', `${edge.kind || 'solid'}${edgeDirection(edge) === 'both' ? ' · both ways' : ''}`],
      ];
    }
    const boundaryElement = target.closest('[data-graph-boundary]');
    if (boundaryElement) {
      const boundary = boundaryById(boundaryElement.dataset.boundaryId);
      if (!boundary) return null;
      const parent = boundary.parentId ? boundaryById(boundary.parentId) : null;
      return [
        ['', boundary.name],
        ['Frame', boundary.kind || boundary.type || ''],
        ['Inside', parent?.name || ''],
        ['Contains', `${state.nodes.filter(node => node.boundaryId === boundary.id).length} components`],
      ];
    }
    return null;
  };
  const hideTooltip = () => { if (tooltip) tooltip.hidden = true; };
  // The box the tooltip must not cover: the hovered card or caption. A frame
  // is the thing being pointed into, so nothing to avoid there.
  const tooltipAnchor = target => {
    const named = target.closest('[data-graph-node],[data-edge-label]');
    return named ? named.getBoundingClientRect() : null;
  };
  // The tooltip is a small card of block rows. It is measured at its natural
  // width first (max-content, capped by the stylesheet), then placed beside
  // the pointer on the side with room -- right and below by default, left or
  // above when the stage runs out -- and moved off the hovered element's box
  // when the two would overlap, so it never covers the thing it names.
  const showTooltip = (rows, event, anchor = null) => {
    if (!tooltip || !rows) return;
    tooltip.innerHTML = rows
      .filter(([, value]) => value)
      .map(([label, value], index) => index === 0
        ? `<strong>${escapeText(value)}</strong>`
        : label
          ? `<span><em>${escapeText(label)}</em>${escapeText(value)}</span>`
          : `<span>${escapeText(value)}</span>`)
      .join('');
    tooltip.hidden = false;
    // Measure at (0, 0): the box's size, and where (0, 0) lands on screen.
    // Placing by that origin makes the maths independent of which ancestor
    // is the containing block and of how far the viewport has scrolled.
    tooltip.style.left = '0px';
    tooltip.style.top = '0px';
    const host = tooltip.parentElement;
    const stage = host.getBoundingClientRect();
    const box = tooltip.getBoundingClientRect();
    const viewWidth = host.clientWidth || stage.width;
    const viewHeight = host.clientHeight || stage.height;
    const gap = 12;
    const px = event.clientX - stage.left;
    const py = event.clientY - stage.top;
    const fits = (x, y) => x >= 4 && y >= 4
      && x + box.width <= viewWidth - 4 && y + box.height <= viewHeight - 4;
    const overlaps = (x, y) => Boolean(anchor)
      && x < anchor.right - stage.left && x + box.width > anchor.left - stage.left
      && y < anchor.bottom - stage.top && y + box.height > anchor.top - stage.top;
    const candidates = [
      [px + gap, py + gap], [px - box.width - gap, py + gap],
      [px + gap, py - box.height - gap], [px - box.width - gap, py - box.height - gap],
    ];
    if (anchor) {
      const ax = anchor.left - stage.left;
      const ay = anchor.top - stage.top;
      candidates.push(
        [ax, anchor.bottom - stage.top + gap], [ax, ay - box.height - gap],
        [anchor.right - stage.left + gap, ay], [ax - box.width - gap, ay],
      );
    }
    const spot = candidates.find(([x, y]) => fits(x, y) && !overlaps(x, y))
      || candidates.find(([x, y]) => fits(x, y))
      || [
        Math.max(4, Math.min(px + gap, viewWidth - box.width - 4)),
        Math.max(4, Math.min(py + gap, viewHeight - box.height - 4)),
      ];
    tooltip.style.left = `${spot[0] + stage.left - box.left}px`;
    tooltip.style.top = `${spot[1] + stage.top - box.top}px`;
  };
  if (tooltip) {
    // On hover only a handle (a connection dot, a resize grip) says what it
    // does: a card over every card the pointer crossed stood in the way.
    // What an item is shows under the right-click menu's title instead.
    const hoverRows = target => (target.closest('[data-node-port],[data-node-resize]') ? tooltipRows(target) : null);
    diagram.addEventListener('pointerover', event => {
      if (event.buttons !== 0 || connection) return hideTooltip();
      const rows = hoverRows(event.target);
      if (rows) showTooltip(rows, event, tooltipAnchor(event.target)); else hideTooltip();
    });
    diagram.addEventListener('pointermove', event => {
      if (tooltip.hidden || event.buttons !== 0 || connection) return;
      const rows = hoverRows(event.target);
      if (rows) showTooltip(rows, event, tooltipAnchor(event.target)); else hideTooltip();
    });
    diagram.addEventListener('pointerleave', hideTooltip);
    diagram.addEventListener('pointerdown', hideTooltip);
  }

