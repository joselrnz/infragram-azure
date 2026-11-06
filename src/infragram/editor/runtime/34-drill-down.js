// @module 34-drill-down: open one frame to see it alone, the way back, and the wires that leave it
  // Opening a frame -- a region, a subscription, a network, a cluster --
  // draws only it and what it holds, fitted to the screen. It is a view,
  // like the zoom: the document is not touched, nothing of it is saved, and
  // a download is always the whole diagram. The breadcrumb over the canvas
  // goes back up; a wire that leaves the open frame ends at its edge and
  // names what it reaches, and that name opens the frame holding it.
  const drillNav = document.querySelector('[data-drill-path]');
  // A frame and the frames it sits in, outermost first.
  const framePath = id => {
    const path = [];
    for (let frame = boundaryById(id); frame; frame = frame.parentId ? boundaryById(frame.parentId) : null) {
      path.unshift(frame.id);
    }
    return path;
  };
  const renderDrillPath = () => {
    if (!drillNav) return;
    drillNav.hidden = !drillPath.length;
    if (!drillPath.length) {
      drillNav.replaceChildren();
      return;
    }
    const crumbs = [{name: 'Whole diagram'}, ...drillPath.map(id => ({name: boundaryById(id)?.name || 'Frame'}))];
    drillNav.innerHTML = `<ol>${crumbs.map((crumb, index) => (index === crumbs.length - 1
      ? `<li><span aria-current="location">${escapeText(crumb.name)}</span></li>`
      : `<li><button type="button" data-drill-to="${index}">${escapeText(crumb.name)}</button></li>`)).join('')}</ol>`;
  };
  const setDrillPath = path => {
    drillPath = path.filter(id => boundaryById(id));
    clearSelection();
    renderGraph();
    renderDrillPath();
    const open = boundaryById(openFrameId());
    setStatus(open ? `Showing ${open.name || 'the frame'} alone` : 'Showing the whole diagram', {show: false});
    requestAnimationFrame(() => fitZoom());
  };
  const openFrame = id => {
    if (boundaryById(id)) setDrillPath(framePath(id));
  };
  // The whole diagram for the length of one call -- a download -- then the
  // open frame again, so a picture never depends on the view.
  const wholeDrawing = draw => {
    const kept = drillPath;
    drillPath = [];
    renderGraph();
    try {
      return draw();
    } finally {
      drillPath = kept;
      renderGraph();
    }
  };

  const STUB_LINE = 16;
  const STUB_GAP = 10;
  // A wire with one end in the open frame and the other outside it: a lead
  // from the card's side, level with it, out through the frame's border on
  // the side the far end lies, and the far end's name just outside, where
  // nothing else is drawn while a frame is open. Names on one side stand a
  // line apart. A far end on a hidden layer is not drawn whatever is open,
  // so it gets none.
  const drillStubsMarkup = open => {
    const colors = canvasPalette();
    const stubs = new Map();
    state.edges.forEach(edge => {
      const source = nodeById(edge.source), target = nodeById(edge.target);
      if (!source || !target) return;
      const sourceIn = nodeIsVisible(source), targetIn = nodeIsVisible(target);
      if (sourceIn === targetIn) return;
      const [near, far] = sourceIn ? [source, target] : [target, source];
      if (!isLayerVisible(far.layerId)) return;
      const key = `${near.id}\u0000${far.id}`;
      if (!stubs.has(key)) stubs.set(key, {near, far, outgoing: sourceIn});
    });
    // two far ends of one name (an AKS in each region) say which frame they sit in
    const named = new Map();
    stubs.forEach(({far}) => named.set(far.name, (named.get(far.name) || 0) + 1));
    const farName = far => (named.get(far.name) > 1 && boundaryById(far.boundaryId)
      ? `${far.name || 'a card'} · ${boundaryById(far.boundaryId).name}` : far.name || 'a card');
    const middle = open.x + open.width / 2;
    const placed = {left: [], right: []};
    return [...stubs.values()]
      .sort((a, b) => (a.near.y + a.near.height / 2) - (b.near.y + b.near.height / 2))
      .map(({near, far, outgoing}) => {
        const right = far.x + far.width / 2 >= middle;
        const side = right ? 'right' : 'left';
        const cy = near.y + near.height / 2;
        let y = cy;
        while (placed[side].some(taken => Math.abs(taken - y) < STUB_LINE)) y += STUB_LINE;
        placed[side].push(y);
        const from = right ? near.x + near.width : near.x;
        const edge = right ? open.x + open.width : open.x;
        const out = right ? edge + STUB_GAP : edge - STUB_GAP;
        const words = `${outgoing ? 'to' : 'from'} ${farName(far)}`;
        const path = y === cy ? `M${from} ${cy}H${out}` : `M${from} ${cy}H${(from + edge) / 2}V${y}H${out}`;
        return `<g data-drill-stub data-drill-target="${escapeText(far.id)}" cursor="pointer">`
          + `<path d="${path}" fill="none" stroke="${colors.secondary}" stroke-width="1" stroke-dasharray="4 3" vector-effect="non-scaling-stroke" pointer-events="none"/>`
          + `<circle cx="${out}" cy="${y}" r="2.5" fill="${colors.secondary}" pointer-events="none"/>`
          + `<text x="${right ? out + 6 : out - 6}" y="${y + 4}" text-anchor="${right ? 'start' : 'end'}" font-size="12" fill="${colors.text}" pointer-events="all">`
          + `<title>Open the frame that holds ${escapeText(far.name || 'it')}</title>${escapeText(words)}</text></g>`;
      }).join('');
  };
  // After every drawing: the stubs, what stands aside, and the step list.
  afterRender.push(() => {
    // a frame deleted or undone away while open: back to what is left
    if (drillPath.some(id => !boundaryById(id))) {
      drillPath = drillPath.filter(id => boundaryById(id));
      renderDrillPath();
      requestAnimationFrame(() => renderGraph());
    }
    const open = boundaryById(openFrameId());
    diagram.querySelectorAll('[data-brand-mark],[data-status-block],[data-legend-strip],[data-export-title],[data-static-meta-layer]')
      .forEach(element => element.toggleAttribute('data-drill-hidden', Boolean(open)));
    // the steps whose wires the open frame does not hold step back
    diagram.querySelectorAll('[data-step-row]').forEach(row => {
      const number = Number(row.dataset.stepRow), flow = row.getAttribute('data-step-flow') || '';
      const shown = !open || state.edges.some(edge => edgeStep(edge) === number && (edge.stepFlow || '') === flow
        && nodeIsVisible(nodeById(edge.source)) && nodeIsVisible(nodeById(edge.target)));
      row.toggleAttribute('data-drill-away', !shown);
    });
    if (!open) return;
    // under the cards, so a lead passing behind one is hidden by it; the
    // names stand outside the frame, clear of everything
    diagram.querySelector('[data-node-layer]')
      ?.insertAdjacentHTML('beforebegin', `<g data-drill-stub-layer>${drillStubsMarkup(open)}</g>`);
  });
  drillNav?.addEventListener('click', event => {
    const crumb = event.target.closest('[data-drill-to]');
    if (crumb) setDrillPath(drillPath.slice(0, Number(crumb.dataset.drillTo)));
  });
  // A far end's name opens the frame that holds it, or the whole diagram for
  // a card in none. Taken before the canvas's own press handling, which
  // would start a pan or a marquee.
  diagram.addEventListener('pointerdown', event => {
    const stub = event.target.closest?.('[data-drill-target]');
    if (!stub || event.button > 0) return;
    event.stopPropagation();
    event.preventDefault();
    const far = nodeById(stub.dataset.drillTarget);
    if (far) setDrillPath(far.boundaryId ? framePath(far.boundaryId) : []);
  }, true);
