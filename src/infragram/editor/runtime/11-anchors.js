// @module 11-anchors: where wires touch cards and glyphs and arrowhead trimming
  const toSvgPoint = (clientX, clientY) => {
    const matrix = diagram.getScreenCTM();
    if (!matrix) return {x: state.canvas.width / 2, y: state.canvas.height / 2};
    const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
    return {x: point.x, y: point.y};
  };

  const inferredSides = (source, target, edge) => {
    const dx = (target.x + target.width / 2) - (source.x + source.width / 2);
    const dy = (target.y + target.height / 2) - (source.y + source.height / 2);
    let sourcePort;
    let targetPort;
    if (Math.abs(dx) >= Math.abs(dy)) {
      sourcePort = dx >= 0 ? 'right' : 'left';
      targetPort = dx >= 0 ? 'left' : 'right';
    } else {
      sourcePort = dy >= 0 ? 'bottom' : 'top';
      targetPort = dy >= 0 ? 'top' : 'bottom';
    }
    return {
      sourcePort: edge.sourcePort === 'auto' ? sourcePort : edge.sourcePort,
      targetPort: edge.targetPort === 'auto' ? targetPort : edge.targetPort,
    };
  };

  // Where a wire touches a node. A card is its box. An icon-only
  // node is a glyph with a caption beneath inside a wider invisible box, and
  // a wire that met that box would start in empty air beside the glyph; so
  // its left, right and top anchors sit on the glyph's own edges and its
  // bottom anchor sits beneath the caption. Same numbers as the node markup.
  const anchorBox = node => {
    if (node.displayMode !== 'icon') {
      return {x: node.x, y: node.y, width: node.width, height: node.height, bottom: node.y + node.height};
    }
    const square = glyphSquare(node);
    // Most artwork keeps air inside its square -- the globe primitive leaves
    // 9 px a side -- so the box is drawn in to where the ink starts, and a
    // wire touches the mark instead of the white around it. node.ink is
    // [left, right, top, bottom] as fractions, from the shipped table.
    const ink = Array.isArray(node.ink) ? node.ink.map(v => (Number(v) || 0) * square.size) : [0, 0, 0, 0];
    return {
      x: square.x + ink[0],
      y: square.y + ink[2],
      width: Math.max(4, square.size - ink[0] - ink[1]),
      height: Math.max(4, square.size - ink[2] - ink[3]),
      bottom: node.y + node.height,
    };
  };

  // The square a bare glyph's artwork is drawn in, as the node drawing
  // places it.
  const glyphSquare = node => {
    const captioned = node.height >= ICON_NODE.captionMinHeight;
    const size = Math.min(ICON_NODE.glyph, node.width - 8, (captioned ? node.height - 34 : node.height) - 8);
    return {x: node.x + (node.width - size) / 2, y: node.y + (captioned ? ICON_NODE.glyphTop : (node.height - size) / 2), size};
  };

  // Where the ink begins along each side, from the shipped table
  // (catalog/ink.py): 33 characters a side from its start to its end, the
  // depth in 64ths of the glyph square ('A' is 0, '/' is 63, '.' no ink),
  // sides joined by '|' as left, right, top, bottom. Lines between are
  // interpolated; a line with no ink borrows the shallower of its nearest
  // measured neighbours; nothing is seated past the square's middle.
  const INK_LEVELS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const INK_SIDES = ['left', 'right', 'top', 'bottom'];
  const inkDepth = (code, side, along) => {
    const parts = typeof code === 'string' ? code.split('|') : [];
    if (parts.length !== INK_SIDES.length || !INK_SIDES.includes(side)) return null;
    const line = parts[INK_SIDES.indexOf(side)];
    const count = line.length;
    if (count < 2) return null;
    const level = index => {
      // Ink that begins past the middle of the square is no seat either.
      if (index < 0 || index >= count || line[index] === '.') return null;
      const found = INK_LEVELS.indexOf(line[index]);
      return found < 0 || found / 64 > 0.5 ? null : found / 64;
    };
    const position = Math.min(1, Math.max(0, along)) * (count - 1);
    const low = Math.floor(position);
    const high = Math.min(low + 1, count - 1);
    const a = level(low);
    const b = level(high);
    let depth = null;
    // Lines more than a step apart are an edge of the mark, not a slope, so
    // the nearer line's depth is the drawn one.
    if (a !== null && b !== null) depth = Math.abs(a - b) > 3 / 64 ? (position - low < 0.5 ? a : b) : a + (b - a) * (position - low);
    else if (a !== null || b !== null) depth = a !== null ? a : b;
    else {
      for (let step = 1; step <= 3 && depth === null; step += 1) {
        const near = [level(low - step), level(high + step)].filter(value => value !== null);
        if (near.length) depth = Math.min(...near);
      }
      if (depth === null) return null;
    }
    return Math.min(depth, 0.5);
  };

  // `along`, or the nearest measured line to it whose ink begins short of the
  // square's middle: a link that falls on a gap in a mark has no drawing on its
  // own line to touch, so it moves along the side to the drawing nearest it.
  const inkedAlong = (code, side, along) => {
    const parts = typeof code === 'string' ? code.split('|') : [];
    if (parts.length !== INK_SIDES.length || !INK_SIDES.includes(side)) return along;
    const line = parts[INK_SIDES.indexOf(side)];
    const count = line.length;
    if (count < 2) return along;
    const depthAt = index => {
      const found = line[index] === '.' ? -1 : INK_LEVELS.indexOf(line[index]);
      return found >= 0 && found / 64 <= 0.5 ? found / 64 : null;
    };
    const inked = index => depthAt(index) !== null;
    const position = Math.min(1, Math.max(0, along)) * (count - 1);
    const low = Math.floor(position);
    const high = Math.min(low + 1, count - 1);
    if (inked(low) && inked(high)) {
      // Between two lines a step apart the point sits on the nearer line
      // itself, so its seat is that line's own edge (mirrors catalog/ink.py).
      if (Math.abs(depthAt(low) - depthAt(high)) > 3 / 64) return (position - low < 0.5 ? low : high) / (count - 1);
      return along;
    }
    let nearest = -1;
    for (let index = 0; index < count; index += 1) {
      if (inked(index) && (nearest < 0 || Math.abs(index - position) < Math.abs(nearest - position))) nearest = index;
    }
    return nearest < 0 ? along : nearest / (count - 1);
  };

  // Where the table puts a side's connection point by hand (a person's body,
  // not the neck the rule would pick), as a fraction along it, or null.
  // Mirrors catalog/ink.py ports.
  const setPort = (node, side) => {
    const along = node && node.inkPorts ? node.inkPorts[side] : undefined;
    return typeof along === 'number' && Number.isFinite(along) ? along : null;
  };

  // A point that falls on a gap in the mark slides along its side to the
  // nearest line the drawing reaches, so there is ink on its line to seat on.
  // A port the table sets by hand stays where it was set.
  const onInk = (node, side, point) => {
    if (!seatable(node) || side === 'bottom' || setPort(node, side) !== null) return point;
    const square = glyphSquare(node);
    const vertical = side === 'left' || side === 'right';
    const along = (vertical ? point.y - square.y : point.x - square.x) / square.size;
    const slid = inkedAlong(node.inkEdges, side, along);
    if (slid === along) return point;
    return vertical ? {x: point.x, y: square.y + slid * square.size} : {x: square.x + slid * square.size, y: point.y};
  };

  // The middle of the stretch of a side the device's drawing reaches -- from
  // the first to the last line whose first ink is the device -- as a
  // fraction along the side, or null. Mirrors catalog/ink.py usable_middle.
  const inkMiddle = (code, side) => {
    const parts = typeof code === 'string' ? code.split('|') : [];
    if (parts.length !== INK_SIDES.length || !INK_SIDES.includes(side)) return null;
    const line = parts[INK_SIDES.indexOf(side)];
    let first = -1;
    let last = -1;
    for (let index = 0; index < line.length; index += 1) {
      const found = line[index] === '.' ? -1 : INK_LEVELS.indexOf(line[index]);
      if (found >= 0 && found <= 64 * 0.5) {
        if (first < 0) first = index;
        last = index;
      }
    }
    // On a measured line (a half rounds to the later line), as catalog/ink.py does.
    return first < 0 || line.length < 2 ? null : Math.floor((first + last + 1) / 2) / (line.length - 1);
  };

  // A side's one connection point sits at the middle of the stretch of that
  // side the device's drawing reaches, so a link meets the middle of a
  // router's body, not the middle of its body and wifi arcs together.
  const centred = (node, side, point) => {
    if (!seatable(node) || side === 'bottom') return point;
    const along = setPort(node, side) ?? inkMiddle(node.inkEdges, side);
    if (along === null) return point;
    const square = glyphSquare(node);
    return side === 'top' ? {x: square.x + along * square.size, y: point.y}
      : {x: point.x, y: square.y + along * square.size};
  };

  // A turned or mirrored glyph no longer matches its measured edges, so it
  // keeps its box anchors.
  const seatable = node => Boolean(node) && node.displayMode === 'icon' && typeof node.inkEdges === 'string'
    && node.inkEdges !== '' && !node.flipX && !node.flipY && !Number(node.angle);

  // Where a wire ending at `point` on a bare glyph's box touches the drawing:
  // pushed straight in along its own line to where the ink begins.
  // The box is the ink's outermost extent, so on a round or uneven
  // mark a point on it can sit in air; seated, it sits on the mark.
  // A card, the caption's underside and artwork with no edges keep the point.
  const seat = (node, side, point) => {
    if (!seatable(node) || side === 'bottom') return point;
    const square = glyphSquare(node);
    if (side === 'left' || side === 'right') {
      const depth = inkDepth(node.inkEdges, side, (point.y - square.y) / square.size);
      if (depth === null) return point;
      const x = side === 'left' ? Math.max(point.x, square.x + depth * square.size)
        : Math.min(point.x, square.x + square.size - depth * square.size);
      return {x, y: point.y};
    }
    const depth = inkDepth(node.inkEdges, 'top', (point.x - square.x) / square.size);
    return depth === null ? point : {x: point.x, y: Math.max(point.y, square.y + depth * square.size)};
  };

  // A route's corners with both ends seated on their glyphs. Routing runs
  // between points on the boxes, so the search is untouched; each end then
  // moves along the wire's own first or last segment.
  const seatEnds = (item, ends, corners) => {
    if (corners.length < 2) return corners;
    const seated = corners.slice();
    seated[0] = seat(item.source, ends.sourcePort, seated[0]);
    seated[seated.length - 1] = seat(item.target, ends.targetPort, seated[seated.length - 1]);
    return seated;
  };

  // What a node's own wire may not cross: a card's box; for an icon-only
  // node the glyph and the caption band beneath it, leaving the air beside
  // the glyph free for the wire to leave and arrive through.
  const ownBoxes = node => {
    if (node.displayMode !== 'icon') return [inflated(node, 0)];
    const box = anchorBox(node);
    const glyphBox = {left: box.x, top: box.y, right: box.x + box.width, bottom: box.y + box.height};
    const captionTop = box.y + box.height + 4;
    if (captionTop >= node.y + node.height - 1) return [glyphBox];
    return [glyphBox, {left: node.x, top: captionTop, right: node.x + node.width, bottom: node.y + node.height}];
  };

  const portPoint = (node, side, index = 0, count = 1) => {
    const ratio = (index + 1) / (count + 1);
    const box = anchorBox(node);
    if (side === 'bottom') return {x: box.x + box.width * ratio, y: box.bottom};
    const point = side === 'top' ? {x: box.x + box.width * ratio, y: box.y}
      : {x: side === 'left' ? box.x : box.x + box.width, y: box.y + box.height * ratio};
    return onInk(node, side, centred(node, side, point));
  };

  const edgeWaypoints = edge => (Array.isArray(edge?.waypoints) ? edge.waypoints : [])
    .filter(point => Number.isFinite(point?.x) && Number.isFinite(point?.y));

  // The points a wire is shaped by: where it leaves, every bend, where it
  // arrives. Bends are absolute canvas points, as the document stores them.
  const edgeControlPoints = item => [
    item.sourceSeat || item.sourcePoint,
    ...edgeWaypoints(item.edge),
    item.targetSeat || item.targetPoint,
  ];

  // Which stretch of the wire a point is nearest, so a new bend joins the
  // route in the right place instead of at the end of the list.
  const nearestEdgeStretch = (points, at) => {
    let best = 0;
    let bestGap = Infinity;
    points.slice(1).forEach((point, index) => {
      const from = points[index];
      const run = Math.hypot(point.x - from.x, point.y - from.y) || 1;
      const along = Math.max(0, Math.min(1,
        ((at.x - from.x) * (point.x - from.x) + (at.y - from.y) * (point.y - from.y)) / (run * run)));
      const gap = Math.hypot(from.x + (point.x - from.x) * along - at.x,
        from.y + (point.y - from.y) * along - at.y);
      if (gap < bestGap) {
        bestGap = gap;
        best = index;
      }
    });
    return best;
  };

  const edgeGeometry = () => {
    const resolved = state.edges.map(edge => {
      const source = nodeById(edge.source);
      const target = nodeById(edge.target);
      if (!source || !target || !nodeIsVisible(source) || !nodeIsVisible(target)) return null;
      return {edge, source, target, ...inferredSides(source, target, edge)};
    }).filter(Boolean);
    // Every wire on a side meets at that side's one point: a node has four
    // connection points, one a side, and wires that share a side share its
    // point instead of fanning along the edge like a circuit board. The
    // static renderer anchors the same way.
    resolved.forEach(item => {
      item.sourcePoint = portPoint(item.source, item.sourcePort);
      item.targetPoint = portPoint(item.target, item.targetPort);
    });
    // Two ports on facing sides that are within a few pixels of each other's
    // line are put on one line, so the wire is drawn straight instead of
    // with a two-pixel jog. The moved port stays on its side.
    resolved.forEach(item => {
      const vertical = ['top', 'bottom'].includes(item.sourcePort) && ['top', 'bottom'].includes(item.targetPort);
      const horizontal = ['left', 'right'].includes(item.sourcePort) && ['left', 'right'].includes(item.targetPort);
      if (vertical && Math.abs(item.sourcePoint.x - item.targetPoint.x) <= ROUTE.straighten) {
        item.targetPoint = {...item.targetPoint, x: item.sourcePoint.x};
      } else if (horizontal && Math.abs(item.sourcePoint.y - item.targetPoint.y) <= ROUTE.straighten) {
        item.targetPoint = {...item.targetPoint, y: item.sourcePoint.y};
      }
    });
    return resolved;
  };

  // Straight wire an arrowhead needs under it, from the spec: the head and a
  // little more, so a bend never runs into the head. A corner next to a
  // headed end gives up its rounding before it gives up the shaft.
  const HEAD_SHAFT = Number(ARROWHEADS.shaft);

  // The wire stops a hair short of a head's tip (the spec's tip_clear), so
  // the stroke never pokes out of the point where the head is thinner than
  // the line; the marker's refX puts the tip back exactly on the anchor.
  const trimHeads = (points, heads) => {
    const clear = Number(ARROWHEADS.tip_clear) || 0;
    const pulled = points.slice();
    const pullBack = (from, toward) => {
      const length = Math.hypot(toward.x - from.x, toward.y - from.y);
      if (length <= clear + 1) return from;
      return {x: from.x + ((toward.x - from.x) / length) * clear, y: from.y + ((toward.y - from.y) / length) * clear};
    };
    if (pulled.length >= 2 && heads.end) pulled[pulled.length - 1] = pullBack(pulled[pulled.length - 1], pulled[pulled.length - 2]);
    if (pulled.length >= 2 && heads.start) pulled[0] = pullBack(pulled[0], pulled[1]);
    return pulled;
  };

  const roundedPath = (points, heads = {start: false, end: true}, maxRadius = cornerRadius()) => {
    const clean = trimHeads(points.filter((point, index) => index === 0
      || point.x !== points[index - 1].x || point.y !== points[index - 1].y), heads);
    if (clean.length < 2) return '';
    let path = `M${clean[0].x},${clean[0].y}`;
    for (let index = 1; index < clean.length - 1; index += 1) {
      const previous = clean[index - 1];
      const current = clean[index];
      const next = clean[index + 1];
      const beforeLength = Math.hypot(current.x - previous.x, current.y - previous.y);
      const afterLength = Math.hypot(next.x - current.x, next.y - current.y);
      let radius = Math.min(maxRadius, beforeLength / 2, afterLength / 2);
      if (heads.end && index === clean.length - 2) radius = Math.min(radius, Math.max(0, afterLength - HEAD_SHAFT));
      if (heads.start && index === 1) radius = Math.min(radius, Math.max(0, beforeLength - HEAD_SHAFT));
      if (radius <= 0) {
        path += ` L${current.x},${current.y}`;
        continue;
      }
      const before = {
        x: current.x - ((current.x - previous.x) / beforeLength) * radius,
        y: current.y - ((current.y - previous.y) / beforeLength) * radius,
      };
      const after = {
        x: current.x + ((next.x - current.x) / afterLength) * radius,
        y: current.y + ((next.y - current.y) / afterLength) * radius,
      };
      path += ` L${before.x},${before.y} Q${current.x},${current.y} ${after.x},${after.y}`;
    }
    const last = clean[clean.length - 1];
    return `${path} L${last.x},${last.y}`;
  };

