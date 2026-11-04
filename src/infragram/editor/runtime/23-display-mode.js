// @module 23-display-mode: card and icon display, frames refitting and making room for their contents
  // A frame hugs what it holds. When a component changes size -- a card
  // turned into a bare icon is narrower and taller -- its frame and every
  // frame around it take the extent of their children plus their own
  // padding, snapped outward to the grid and never below their minimum size.
  // A locked frame keeps the size its author fixed. Frames and components
  // carry absolute coordinates, so moving a frame's edge never moves what is
  // inside it. Before this, only the component changed: icons spilled out of
  // the frame that had fitted the cards, and a card going back was squeezed
  // to the frame instead of the frame growing.
  const fitFrameToContents = frame => {
    if (itemIsLocked(frame)) return;
    const children = [
      ...state.boundaries.filter(item => item.parentId === frame.id),
      ...state.nodes.filter(item => item.boundaryId === frame.id),
    ];
    if (!children.length) return;
    const pad = Number(frame.pad) || 0;
    const grid = Number(state.canvas.grid) || 1;
    const left = Math.floor((Math.min(...children.map(item => item.x)) - pad) / grid) * grid;
    const top = Math.floor((Math.min(...children.map(item => item.y)) - pad) / grid) * grid;
    const right = Math.ceil((Math.max(...children.map(item => item.x + item.width)) + pad) / grid) * grid;
    const bottom = Math.ceil((Math.max(...children.map(item => item.y + item.height)) + pad) / grid) * grid;
    frame.x = left;
    frame.y = top;
    frame.width = Math.max(frame.minWidth || 160, right - left);
    frame.height = Math.max(frame.minHeight || 104, bottom - top);
  };
  const fitAllFrames = () => {
    state.boundaries.slice()
      .sort((a, b) => boundaryDepth(b) - boundaryDepth(a))
      .forEach(fitFrameToContents);
  };
  const extendCanvasToContents = () => {
    const items = [...state.boundaries, ...state.nodes];
    if (!items.length) return;
    ensureCanvasExtent({
      right: Math.max(...items.map(item => item.x + item.width)) + CANVAS_MARGIN,
      bottom: Math.max(...items.map(item => item.y + item.height)) + CANVAS_MARGIN,
    });
  };
  // A component switched between card and icon keeps its centre.
  const resizeForDisplay = (node, mode) => {
    const centerX = node.x + node.width / 2;
    const centerY = node.y + node.height / 2;
    if (mode === 'icon') {
      node.cardSize = {width: node.width, height: node.height};
      node.width = iconNodeWidth(node);
      node.height = ICON_NODE.height;
    } else {
      node.width = Math.max(96, Number(node.cardSize?.width) || 208);
      node.height = Math.max(56, Number(node.cardSize?.height) || 72);
    }
    node.displayMode = mode;
    node.x = snap(Math.max(0, centerX - node.width / 2));
    node.y = snap(Math.max(0, centerY - node.height / 2));
  };

  // Making room. A card turned into an icon is taller: resized about its
  // centre it reaches into the card stacked above and below it, and a card
  // coming back is wider and reaches into its neighbour in the row. Refitting
  // frames alone left those overlaps (icons drawn over each other's
  // captions). So, container by container from the innermost out, any two
  // siblings that overlap now but did not before are pushed apart along the
  // way they were arranged -- down a column, right along a row -- keeping
  // the gap they had; a frame moves with everything inside it, then refits,
  // and its own container makes room for its new size in turn. Nothing is
  // ever pulled closer, and a locked item is never moved.
  const DISPLAY_MIN_GAP = 16;
  const boxOf = item => ({x: item.x, y: item.y, width: item.width, height: item.height});
  const snapshotBoxes = () => new Map(
    [...state.nodes, ...state.boundaries].map(item => [item.id, boxOf(item)]),
  );
  const boxesOverlap = (a, b) => (
    a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height
  );
  const containerChildren = id => [
    ...state.boundaries.filter(item => (item.parentId || null) === id),
    ...state.nodes.filter(item => (item.boundaryId || null) === id),
  ];
  const shiftWithContents = (item, dx, dy) => {
    const moved = state.boundaries.includes(item)
      ? [
        ...state.boundaries.filter(other => isBoundaryDescendant(other.id, item.id)),
        ...state.nodes.filter(node => node.boundaryId && isBoundaryDescendant(node.boundaryId, item.id)),
      ]
      : [item];
    moved.forEach(other => {
      other.x += dx;
      other.y += dy;
    });
  };
  // A bare icon with its caption. Two of them lying on each other is never a
  // composition: it is a layout saved before siblings made room, or a drop
  // that landed on a neighbour. A label or an annotation may sit on anything.
  const isSeparableIcon = item => state.nodes.includes(item)
    && (item.displayMode || 'card') === 'icon'
    && !['custom-label', 'custom-annotation'].includes(item.componentId);
  const tangledIcons = nodes => nodes.some(a => isSeparableIcon(a) && state.nodes.some(b => (
    b !== a && isSeparableIcon(b) && (b.boundaryId || null) === (a.boundaryId || null) && boxesOverlap(a, b)
  )));
  const makeRoomAmongSiblings = (containerId, before, {untangle = false} = {}) => {
    const items = containerChildren(containerId);
    for (let pass = 0; pass < 12; pass += 1) {
      let moved = false;
      items.sort((a, b) => a.y - b.y || a.x - b.x);
      for (const a of items) {
        for (const b of items) {
          if (a === b || itemIsLocked(b) || !boxesOverlap(a, b)) continue;
          const wasA = before.get(a.id);
          const wasB = before.get(b.id);
          if (!wasA || !wasB) continue;
          if (boxesOverlap(wasA, wasB)) {
            // Already on each other: with no arrangement to restore, the
            // lower one steps below, or the one further right steps right.
            if (!untangle || !isSeparableIcon(a) || !isSeparableIcon(b)) continue;
            const dx = (b.x + b.width / 2) - (a.x + a.width / 2);
            const dy = (b.y + b.height / 2) - (a.y + a.height / 2);
            if (dy >= 0 && dy >= Math.abs(dx) / 2) {
              shiftWithContents(b, 0, Math.ceil((a.y + a.height + DISPLAY_MIN_GAP - b.y) / 4) * 4);
              moved = true;
            } else if (dx >= 0) {
              shiftWithContents(b, Math.ceil((a.x + a.width + DISPLAY_MIN_GAP - b.x) / 4) * 4, 0);
              moved = true;
            }
            continue;
          }
          if (wasB.y >= wasA.y + wasA.height) {
            const gap = Math.max(DISPLAY_MIN_GAP, wasB.y - (wasA.y + wasA.height));
            shiftWithContents(b, 0, Math.ceil((a.y + a.height + gap - b.y) / 4) * 4);
            moved = true;
          } else if (wasB.x >= wasA.x + wasA.width) {
            const gap = Math.max(DISPLAY_MIN_GAP, wasB.x - (wasA.x + wasA.width));
            shiftWithContents(b, Math.ceil((a.x + a.width + gap - b.x) / 4) * 4, 0);
            moved = true;
          }
        }
      }
      if (!moved) break;
    }
  };
  // Every frame holding a changed component, and every frame around those,
  // innermost first, ending with the canvas itself.
  const reflowContainers = (changed, before, options = {}) => {
    const frames = new Set();
    changed.forEach(node => {
      let frame = node.boundaryId ? boundaryById(node.boundaryId) : null;
      while (frame) {
        frames.add(frame);
        frame = frame.parentId ? boundaryById(frame.parentId) : null;
      }
    });
    [...frames].sort((a, b) => boundaryDepth(b) - boundaryDepth(a)).forEach(frame => {
      makeRoomAmongSiblings(frame.id, before, options);
      fitFrameToContents(frame);
    });
    makeRoomAmongSiblings(null, before, options);
  };
  // What "Card with text" and "Icon only" act on: every selected component,
  // and every component inside a selected frame. It acted on the one card
  // clicked last, so choosing Icon only with several cards selected changed
  // one of them and left the rest as cards.
  const displayTargets = () => {
    const ids = new Set(selectedNodes().map(node => node.id));
    selectedBoundaries().forEach(frame => frameComponents(frame).forEach(node => ids.add(node.id)));
    return [...ids].map(nodeById).filter(Boolean);
  };
  const setNodeDisplayMode = mode => {
    if (!['card', 'icon'].includes(mode)) return;
    const targets = displayTargets();
    const changing = targets.filter(
      node => !itemIsLocked(node) && !isPanel(node) && (node.displayMode || 'card') !== mode,
    );
    const untangle = mode === 'icon' && tangledIcons(targets);
    if (!changing.length && !untangle) return;
    checkpoint();
    const before = snapshotBoxes();
    // Each component keeps its centre; its neighbours and frames make room.
    changing.forEach(node => resizeForDisplay(node, mode));
    // icons chosen also tidy the frames of targets already icons, not only changed ones
    reflowContainers(mode === 'icon' ? targets : changing, before, {untangle: mode === 'icon'});
    extendCanvasToContents();
    persist();
    renderGraph();
    setStatus(!changing.length ? 'Overlapping icons moved apart' : changing.length === 1
      ? `${changing[0].name} displayed as ${mode === 'icon' ? 'an icon' : 'a card'}`
      : `${changing.length} components displayed as ${mode === 'icon' ? 'icons' : 'cards'}`);
  };
  // Every component inside a frame, however deep, as cards or as icons:
  // "show this region as icons" without touching the rest of the diagram.
  const frameComponents = frame => state.nodes.filter(
    node => node.boundaryId && isBoundaryDescendant(node.boundaryId, frame.id),
  );
  const setFrameDisplayMode = (frameId, mode) => {
    const frame = boundaryById(frameId);
    if (!frame || !['card', 'icon'].includes(mode)) return 0;
    const members = frameComponents(frame);
    const changing = members.filter(
      node => !itemIsLocked(node) && !isPanel(node) && (node.displayMode || 'card') !== mode,
    );
    const untangle = mode === 'icon' && tangledIcons(members);
    if (!changing.length && !untangle) return 0;
    checkpoint();
    const before = snapshotBoxes();
    changing.forEach(node => resizeForDisplay(node, mode));
    reflowContainers(mode === 'icon' ? members : changing, before, {untangle: mode === 'icon'});
    extendCanvasToContents();
    persist();
    renderGraph();
    const count = `${changing.length} component${changing.length === 1 ? '' : 's'}`;
    setStatus(changing.length
      ? `${count} in ${frame.name} shown as ${mode === 'icon' ? 'icons' : 'cards'}`
      : `Overlapping icons in ${frame.name} moved apart`);
    return changing.length;
  };
  document.querySelectorAll('[data-display-mode]').forEach(button => {
    button.addEventListener('click', () => setNodeDisplayMode(button.dataset.displayMode));
  });
  // The whole diagram as cards or as bare icons, switched in place: every
  // card is re-sized about its own centre so the composition holds, and a
  // card the author switched by hand is switched too, because "show me this
  // as icons" means all of it. Every frame then refits its contents, innermost
  // first, and siblings make room for one another (see makeRoomAmongSiblings).
  // The exporters still render each look from a document laid out for it.
  const applyProjectDisplayMode = (mode, {persist: remember = true} = {}) => {
    if (!['card', 'icon'].includes(mode)) return;
    if (remember) checkpoint();
    state.canvas.displayMode = mode;
    const before = snapshotBoxes();
    const changed = [];
    state.nodes.forEach(node => {
      // A glyph that draws bare by default stays bare when the diagram goes
      // back to cards; the per-node control still boxes any one of them.
      if (mode === 'card' && defaultDisplayMode(node) === 'icon') return;
      // a panel is a box in either look: its lines are the point of it
      if (isPanel(node)) return;
      if ((node.displayMode || 'card') === mode) return;
      resizeForDisplay(node, mode);
      changed.push(node);
    });
    const untangle = mode === 'icon';
    reflowContainers(untangle ? state.nodes : changed, before, {untangle});
    fitAllFrames();
    extendCanvasToContents();
    if (remember) persist();
    renderGraph();
    if (remember) setStatus(mode === 'icon' ? 'Components shown as icons' : 'Components shown as cards');
  };
  document.querySelector('[data-inspector-display]')?.addEventListener('click', event => {
    const choice = event.target.closest('[data-project-display]');
    if (!choice) return;
    // Icons chosen again still tidies icons that lie on each other.
    const current = state.canvas.displayMode === 'icon' ? 'icon' : 'card';
    if (choice.dataset.projectDisplay === current
      && !(current === 'icon' && tangledIcons(state.nodes))) return;
    applyProjectDisplayMode(choice.dataset.projectDisplay);
  });
  // ?display=icon|card draws the page that way for this visit only, the same
  // contract as ?theme=: exporters get both looks from one HTML file without
  // touching what the author saved.
  const requestedDisplay = String(workspaceParams.get('display') || '').toLowerCase();
  if (['card', 'icon'].includes(requestedDisplay) && requestedDisplay !== state.canvas.displayMode) {
    const saved = {
      displayMode: state.canvas.displayMode, nodes: clone(state.nodes), boundaries: clone(state.boundaries),
    };
    applyProjectDisplayMode(requestedDisplay, {persist: false});
    visitOnly.display = {saved, edits: undoStack.length};
  }
