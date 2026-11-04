// @module 12-routing: orthogonal connector routing around cards
  // --- Orthogonal routing ---------------------------------------------------
  // The naive path is a single dog-leg through the midpoint. That is fine
  // until something sits in the way, and then the wire runs straight across
  // an unrelated card. This is the same A* over a lane grid the static
  // renderer uses (builders/routing.py): lanes are drawn from the obstacle
  // edges, which are the only coordinates a shortest orthogonal path ever
  // turns at, and a turn costs extra so the search does not stair-step
  // across open space.
  const ROUTE = {
    clearance: METRICS.router.clearance,   // how far a wire stays off a card
    stub: METRICS.router.stub,             // straight run out of a side before it may turn
    margin: METRICS.router.margin,         // how far outside the content a detour may go
    turnCost: METRICS.router.turn_cost,    // pixels charged per corner
    straighten: METRICS.router.straighten, // ports this close to one line are put on one line
    maxObstacles: Number.isFinite(METRICS.router.max_obstacles) ? METRICS.router.max_obstacles : 48, // nearest cards considered; keeps the grid small
    rail: Number.isFinite(METRICS.router.rail) ? METRICS.router.rail : 4,                 // this near a frame's border runs along it
    railCost: Number.isFinite(METRICS.router.rail_cost) ? METRICS.router.rail_cost : 3,   // per pixel run along a border
    railRun: Number.isFinite(METRICS.router.rail_run) ? METRICS.router.rail_run : 24,     // the plain path's allowance along one
    crossCost: Number.isFinite(METRICS.router.cross_cost) ? METRICS.router.cross_cost : 0, // per border crossed of a frame holding neither end
    spread: Number.isFinite(METRICS.router.spread) ? METRICS.router.spread : 8,           // wires on one line drawn this far apart
    spreadMin: Number.isFinite(METRICS.router.spread_min) ? METRICS.router.spread_min : 4, // narrower than this, they stay together
  };

  // A frame's borders, as the router sees them: a wire may cross one, but
  // running along it costs extra, or the wire reads as the border and the
  // border as a wire (frame rails, builders/routing.py). Top, bottom, left,
  // right, frame by frame.
  const frameRails = boundaries => boundaries.flatMap(b => [
    {axis: 'h', at: b.y, lo: b.x, hi: b.x + b.width},
    {axis: 'h', at: b.y + b.height, lo: b.x, hi: b.x + b.width},
    {axis: 'v', at: b.x, lo: b.y, hi: b.y + b.height},
    {axis: 'v', at: b.x + b.width, lo: b.y, hi: b.y + b.height},
  ]);

  // Every frame that holds neither end of a wire, in document order
  // (render.py _fences): a wire crosses one's border only when the way
  // around costs more (ROUTE.crossCost). A frame holds a card when it holds
  // its box, to half a pixel.
  const holds = (b, node) => node.x >= b.x - 0.5 && node.y >= b.y - 0.5
    && node.x + node.width <= b.x + b.width + 0.5 && node.y + node.height <= b.y + b.height + 0.5;
  const fenceBoxes = (boundaries, source, target) => boundaries
    .filter(b => !holds(b, source) && !holds(b, target))
    .map(b => ({left: b.x, top: b.y, right: b.x + b.width, bottom: b.y + b.height}));
  // How many fence borders a segment crosses: a border past the segment's
  // low end and up to its high end, so a route that stops on one and goes on
  // counts it once (fence_crossings).
  const fenceCrossings = (fences, a, b) => {
    let count = 0;
    if (Math.abs(a.y - b.y) < 0.01) {
      const lo = Math.min(a.x, b.x);
      const hi = Math.max(a.x, b.x);
      fences.forEach(fence => {
        if (fence.top < a.y && a.y < fence.bottom) {
          count += (lo < fence.left && fence.left <= hi) + (lo < fence.right && fence.right <= hi);
        }
      });
    } else if (Math.abs(a.x - b.x) < 0.01) {
      const lo = Math.min(a.y, b.y);
      const hi = Math.max(a.y, b.y);
      fences.forEach(fence => {
        if (fence.left < a.x && a.x < fence.right) {
          count += (lo < fence.top && fence.top <= hi) + (lo < fence.bottom && fence.bottom <= hi);
        }
      });
    }
    return count;
  };

  // How much of the span lo..hi a rail covers.
  const railOverlap = (lo, hi, rail) => Math.max(0, Math.min(hi, rail.hi) - Math.max(lo, rail.lo));
  // How far a segment runs along the rails, within ROUTE.rail of them:
  // every rail's overlap, added in order (rail_run).
  const railRun = (rails, a, b) => {
    let run = 0;
    if (Math.abs(a.y - b.y) < 0.01) {
      const lo = Math.min(a.x, b.x);
      const hi = Math.max(a.x, b.x);
      rails.forEach(rail => {
        if (rail.axis === 'h' && Math.abs(a.y - rail.at) <= ROUTE.rail) run += railOverlap(lo, hi, rail);
      });
    } else if (Math.abs(a.x - b.x) < 0.01) {
      const lo = Math.min(a.y, b.y);
      const hi = Math.max(a.y, b.y);
      rails.forEach(rail => {
        if (rail.axis === 'v' && Math.abs(a.x - rail.at) <= ROUTE.rail) run += railOverlap(lo, hi, rail);
      });
    }
    return run;
  };

  const inflated = (node, by) => ({
    left: node.x - by,
    top: node.y - by,
    right: node.x + node.width + by,
    bottom: node.y + node.height + by,
  });

  // A point one stub outside an anchor, straight out of its side: where a
  // routed wire's search begins and ends, so the wire meets the side
  // squarely. The full stub gives an arrowhead its shaft; when a neighbour
  // sits that close the stub shortens to the clearance, which still fits
  // one gap away.
  const outward = (point, side, boxes = []) => {
    const at = distance => ({
      x: point.x + (side === 'right' ? distance : side === 'left' ? -distance : 0),
      y: point.y + (side === 'bottom' ? distance : side === 'top' ? -distance : 0),
    });
    const inside = (p, box) => p.x > box.left + 0.01 && p.x < box.right - 0.01
      && p.y > box.top + 0.01 && p.y < box.bottom - 0.01;
    const full = at(ROUTE.stub);
    return boxes.some(box => inside(full, box)) ? at(ROUTE.clearance) : full;
  };

  // Every segment is axis-aligned, so "does it enter this box" is two
  // interval overlaps. The epsilon lets a wire graze an inflated edge,
  // which is exactly where the clearance puts it.
  const segmentBlocked = (box, a, b) => {
    const eps = 0.01;
    if (Math.abs(a.y - b.y) < eps) {
      const [lo, hi] = a.x <= b.x ? [a.x, b.x] : [b.x, a.x];
      return a.y > box.top + eps && a.y < box.bottom - eps
        && hi > box.left + eps && lo < box.right - eps;
    }
    const [lo, hi] = a.y <= b.y ? [a.y, b.y] : [b.y, a.y];
    return a.x > box.left + eps && a.x < box.right - eps
      && hi > box.top + eps && lo < box.bottom - eps;
  };

  const nearestObstacles = (start, end, boxes) => {
    if (boxes.length <= ROUTE.maxObstacles) return boxes;
    const left = Math.min(start.x, end.x);
    const right = Math.max(start.x, end.x);
    const top = Math.min(start.y, end.y);
    const bottom = Math.max(start.y, end.y);
    const distance = box => Math.max(0, box.left - right) + Math.max(0, left - box.right)
      + Math.max(0, box.top - bottom) + Math.max(0, top - box.bottom);
    return boxes.slice().sort((a, b) => distance(a) - distance(b)).slice(0, ROUTE.maxObstacles);
  };

  const routeCorners = (start, end, boxes, walls = [], rails = [], fences = []) => {
    const xs = new Set([start.x, end.x]);
    const ys = new Set([start.y, end.y]);
    boxes.forEach(box => {
      xs.add(box.left); xs.add(box.right);
      ys.add(box.top); ys.add(box.bottom);
    });
    // Each fence that overlaps the span offers lanes one and two clearances
    // outside every border (one may fall on a neighbour's border), so the way
    // around it stays beside it rather than out past everything (routing.py
    // route_prepared).
    const spanLeft = Math.min(start.x, end.x);
    const spanRight = Math.max(start.x, end.x);
    const spanTop = Math.min(start.y, end.y);
    const spanBottom = Math.max(start.y, end.y);
    fences.forEach(fence => {
      if (fence.left <= spanRight && fence.right >= spanLeft && fence.top <= spanBottom && fence.bottom >= spanTop) {
        [ROUTE.clearance, 2 * ROUTE.clearance].forEach(gap => {
          xs.add(fence.left - gap); xs.add(fence.right + gap);
          ys.add(fence.top - gap); ys.add(fence.bottom + gap);
        });
      }
    });
    const lanesX = [...xs].sort((a, b) => a - b);
    const lanesY = [...ys].sort((a, b) => a - b);
    lanesX.unshift(lanesX[0] - ROUTE.margin);
    lanesX.push(lanesX[lanesX.length - 1] + ROUTE.margin);
    lanesY.unshift(lanesY[0] - ROUTE.margin);
    lanesY.push(lanesY[lanesY.length - 1] + ROUTE.margin);

    const nearestLane = (lanes, value) => {
      let best = 0;
      for (let i = 1; i < lanes.length; i += 1) {
        if (Math.abs(lanes[i] - value) < Math.abs(lanes[best] - value)) best = i;
      }
      return best;
    };
    const at = (col, row) => ({x: lanesX[col], y: lanesY[row]});
    const source = [nearestLane(lanesX, start.x), nearestLane(lanesY, start.y)];
    const target = [nearestLane(lanesX, end.x), nearestLane(lanesY, end.y)];
    if (source[0] === target[0] && source[1] === target[1]) return [start, end];

    const key = (col, row, axis) => `${col},${row},${axis}`;
    const goal = at(target[0], target[1]);
    const remaining = (col, row) => Math.abs(lanesX[col] - goal.x) + Math.abs(lanesY[row] - goal.y);
    const startKey = key(source[0], source[1], '');
    const best = new Map([[startKey, 0]]);
    const came = new Map();
    const cells = new Map([[startKey, [source[0], source[1], '']]]);
    // A small binary heap: the grid is at most a few thousand cells, and a
    // sorted-array queue turns quadratic on the dense diagrams that need
    // routing most.
    const queue = [[remaining(source[0], source[1]), 0, startKey]];
    const push = entry => {
      queue.push(entry);
      let i = queue.length - 1;
      while (i > 0) {
        const parent = (i - 1) >> 1;
        if (queue[parent][0] <= queue[i][0]) break;
        [queue[parent], queue[i]] = [queue[i], queue[parent]];
        i = parent;
      }
    };
    const pop = () => {
      const top = queue[0];
      const last = queue.pop();
      if (queue.length) {
        queue[0] = last;
        let i = 0;
        for (;;) {
          const left = i * 2 + 1;
          const right = left + 1;
          let small = i;
          if (left < queue.length && queue[left][0] < queue[small][0]) small = left;
          if (right < queue.length && queue[right][0] < queue[small][0]) small = right;
          if (small === i) break;
          [queue[small], queue[i]] = [queue[i], queue[small]];
          i = small;
        }
      }
      return top;
    };

    // The borders each lane runs along: a level step pays for its overlap
    // with the level ones near its row, an upright step for the upright
    // ones near its column.
    const alongRow = lanesY.map(y => rails
      .filter(rail => rail.axis === 'h' && Math.abs(y - rail.at) <= ROUTE.rail));
    const alongCol = lanesX.map(x => rails
      .filter(rail => rail.axis === 'v' && Math.abs(x - rail.at) <= ROUTE.rail));
    // The fence borders each lane crosses: a level step the sides of the
    // fences across its row, an upright step the tops and bottoms of those
    // across its column, by where they lie.
    const fenceRow = lanesY.map(y => fences
      .filter(fence => fence.top < y && y < fence.bottom).flatMap(fence => [fence.left, fence.right]));
    const fenceCol = lanesX.map(x => fences
      .filter(fence => fence.left < x && x < fence.right).flatMap(fence => [fence.top, fence.bottom]));

    const steps = [[1, 0, 'h'], [-1, 0, 'h'], [0, 1, 'v'], [0, -1, 'v']];
    let guard = 40000;
    while (queue.length && guard > 0) {
      guard -= 1;
      const [, spent, stateKey] = pop();
      if (spent > (best.get(stateKey) ?? Infinity)) continue;
      const [col, row, axis] = cells.get(stateKey);
      if (col === target[0] && row === target[1]) {
        const trail = [];
        let cursor = stateKey;
        while (cursor !== undefined) {
          const [c, r] = cells.get(cursor);
          trail.push(at(c, r));
          cursor = came.get(cursor);
        }
        trail.reverse();
        return [start, ...trail, end];
      }
      for (const [dcol, drow, moved] of steps) {
        const ncol = col + dcol;
        const nrow = row + drow;
        if (ncol < 0 || nrow < 0 || ncol >= lanesX.length || nrow >= lanesY.length) continue;
        const here = at(col, row);
        const there = at(ncol, nrow);
        if (boxes.some(box => segmentBlocked(box, here, there))
          || walls.some(box => segmentBlocked(box, here, there))) continue;
        let run = 0;
        let fenced = 0;
        if (moved === 'h') {
          const lo = Math.min(here.x, there.x);
          const hi = Math.max(here.x, there.x);
          for (const rail of alongRow[row]) run += railOverlap(lo, hi, rail);
          for (const at of fenceRow[row]) if (lo < at && at <= hi) fenced += 1;
        } else {
          const lo = Math.min(here.y, there.y);
          const hi = Math.max(here.y, there.y);
          for (const rail of alongCol[col]) run += railOverlap(lo, hi, rail);
          for (const at of fenceCol[col]) if (lo < at && at <= hi) fenced += 1;
        }
        const cost = spent + Math.abs(there.x - here.x) + Math.abs(there.y - here.y)
          + (axis && axis !== moved ? ROUTE.turnCost : 0)
          + run * ROUTE.railCost
          + fenced * ROUTE.crossCost;
        const nextKey = key(ncol, nrow, moved);
        if (cost < (best.get(nextKey) ?? Infinity)) {
          best.set(nextKey, cost);
          came.set(nextKey, stateKey);
          cells.set(nextKey, [ncol, nrow, moved]);
          push([cost + remaining(ncol, nrow), cost, nextKey]);
        }
      }
    }
    return null;
  };

  // Wires that run along one line, drawn apart (builders/routing.py spread,
  // step for step). Every run of a wire but its first and last is matched
  // against the other wires' runs; runs on one line that overlap form a
  // group, spread ROUTE.spread apart (a run alone too, when it lies within
  // ROUTE.rail of a frame border: off it, to the roomier side) across the room the boxes and the frame
  // rails leave either side, within ROUTE.margin -- closer when narrow, not
  // at all below ROUTE.spreadMin. Wires whose ends turn the lower way take
  // the lower lanes. A group stays as it was if a moved wire would enter a
  // box or leave a card along a leg shorter than ROUTE.clearance. A null
  // wire (shaped by hand) is not spread and comes back null.
  const spreadWires = (wires, boxes, rails) => {
    const sign = value => (value > 0) - (value < 0);
    const entered = wire => {
      let count = 0;
      for (let k = 0; k + 1 < wire.length; k += 1) {
        for (const box of boxes) if (segmentBlocked(box, wire[k], wire[k + 1])) count += 1;
      }
      return count;
    };
    const out = wires.map(wire => (wire ? wire.map(point => ({x: point.x, y: point.y})) : null));
    const runs = [];
    out.forEach((wire, index) => {
      if (!wire) return;
      for (let k = 1; k < wire.length - 2; k += 1) {
        const a = wire[k];
        const b = wire[k + 1];
        if (Math.abs(a.y - b.y) < 0.01 && Math.abs(a.x - b.x) >= 1) {
          runs.push(['h', a.y, Math.min(a.x, b.x), Math.max(a.x, b.x), index, k]);
        } else if (Math.abs(a.x - b.x) < 0.01 && Math.abs(a.y - b.y) >= 1) {
          runs.push(['v', a.x, Math.min(a.y, b.y), Math.max(a.y, b.y), index, k]);
        }
      }
    });
    const root = runs.map((_, index) => index);
    const top = i => {
      while (root[i] !== i) i = root[i];
      return i;
    };
    for (let p = 0; p < runs.length; p += 1) {
      for (let q = p + 1; q < runs.length; q += 1) {
        const one = runs[p];
        const other = runs[q];
        if (one[0] === other[0] && one[4] !== other[4] && Math.abs(one[1] - other[1]) < 0.5
            && Math.min(one[3], other[3]) - Math.max(one[2], other[2]) > 1) {
          const a = top(p);
          const b = top(q);
          if (a !== b) root[Math.max(a, b)] = Math.min(a, b);
        }
      }
    }
    const groups = new Map();
    runs.forEach((_, i) => {
      const key = top(i);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(i);
    });
    for (const members of groups.values()) {
      const [axis, at] = runs[members[0]];
      const lo = Math.min(...members.map(i => runs[i][2]));
      const hi = Math.max(...members.map(i => runs[i][3]));
      let low = at - ROUTE.margin;
      let high = at + ROUTE.margin;
      for (const box of boxes) {
        if (axis === 'v' && box.bottom > lo && box.top < hi) {
          if (box.right <= at) low = Math.max(low, box.right);
          else if (box.left >= at) high = Math.min(high, box.left);
        } else if (axis === 'h' && box.right > lo && box.left < hi) {
          if (box.bottom <= at) low = Math.max(low, box.bottom);
          else if (box.top >= at) high = Math.min(high, box.top);
        }
      }
      let hugged = false;
      const under = [];
      for (const rail of rails) {
        if (rail.axis === axis && rail.hi > lo && rail.lo < hi) {
          hugged = hugged || Math.abs(rail.at - at) <= ROUTE.rail;
          if (Math.abs(rail.at - at) < 0.5) under.push(rail.at);
          else if (rail.at < at) low = Math.max(low, rail.at);
          else high = Math.min(high, rail.at);
        }
      }
      if (new Set(members.map(i => runs[i][4])).size < 2 && !hugged) continue;
      // a border right under the run bounds the side with less room
      for (const line of under) {
        if (high - at >= at - low) low = Math.max(low, line);
        else high = Math.min(high, line);
      }
      const count = members.length;
      const step = Math.min(ROUTE.spread, (high - low) / (count + 1));
      if (step < ROUTE.spreadMin) continue;
      const turn = i => {
        const [, line, , , w, k] = runs[i];
        const wire = out[w];
        return axis === 'v'
          ? sign(wire[k - 1].x - line) + sign(wire[k + 2].x - line)
          : sign(wire[k - 1].y - line) + sign(wire[k + 2].y - line);
      };
      const ordered = members.slice().sort((a, b) => turn(a) - turn(b) || a - b);
      const first = at - step * (count - 1) / 2;
      const last = first + step * (count - 1);
      let shift = 0;
      if (first < low + step) shift = low + step - first;
      else if (last > high - step) shift = high - step - last;
      const moved = new Map();
      let fits = true;
      ordered.forEach((i, j) => {
        const [, , , , w, k] = runs[i];
        const wire = moved.get(w) || out[w].map(point => ({x: point.x, y: point.y}));
        const place = first + step * j + shift;
        for (const n of [k, k + 1]) {
          wire[n] = axis === 'v' ? {x: place, y: wire[n].y} : {x: wire[n].x, y: place};
        }
        moved.set(w, wire);
      });
      for (const [w, wire] of moved) {
        const was = out[w];
        const ends = [[wire[0], wire[1], was[0], was[1]],
          [wire[wire.length - 1], wire[wire.length - 2], was[was.length - 1], was[was.length - 2]]];
        for (const [a, b, c, d] of ends) {
          if (Math.abs(b.x - a.x) + Math.abs(b.y - a.y) < ROUTE.clearance
              || sign(b.x - a.x) !== sign(d.x - c.x) || sign(b.y - a.y) !== sign(d.y - c.y)) fits = false;
        }
        if (entered(wire) > entered(was)) fits = false;
      }
      if (fits) moved.forEach((wire, w) => { out[w] = wire; });
    }
    return out.map(wire => (wire ? tidyCorners(wire) : null));
  };

  // Drop repeats, then collapse runs that continue along one axis.
  const tidyCorners = points => {
    const unique = points.filter((point, index) => index === 0
      || Math.abs(point.x - points[index - 1].x) > 0.5
      || Math.abs(point.y - points[index - 1].y) > 0.5);
    if (unique.length < 3) return unique;
    const kept = [unique[0]];
    for (let i = 1; i < unique.length - 1; i += 1) {
      const [before, corner, after] = [unique[i - 1], unique[i], unique[i + 1]];
      const flatX = Math.abs(before.x - corner.x) < 0.5 && Math.abs(corner.x - after.x) < 0.5;
      const flatY = Math.abs(before.y - corner.y) < 0.5 && Math.abs(corner.y - after.y) < 0.5;
      if (!flatX && !flatY) kept.push(corner);
    }
    kept.push(unique[unique.length - 1]);
    return kept;
  };

  // One obstacle set and one route cache per render pass: edgeMarkup runs
  // once per edge, and recomputing the boxes each time is what would make
  // routing feel slow on a busy diagram.
  let routeContext = {signature: '', boxes: [], rails: [], frames: [], byNode: new Map(), cache: new Map()};
  // The routes spreadLanes drew apart in the last render, by edge id, each
  // with the route key it was spread from: a wire that has moved since
  // routes afresh and is drawn as routed until the next render spreads it.
  let laneSpread = new Map();

  // A frame's title, not the frame. A line crossing a frame's interior is
  // ordinary -- something outside has to reach something inside. A line
  // crossing the frame's *name* destroys the only text saying what the frame
  // is, so the title alone is an obstacle. Mirrors cluster_label_rect in
  // builders/render.py, which does the same for the static renderer.
  const boundaryLabelBox = boundary => {
    const label = boundary.labelCase === 'upper'
      ? String(boundary.name || '').toLocaleUpperCase() : String(boundary.name || '');
    if (!label) return null;
    const labelSize = boundary.labelSize || 10;
    const tab = boundary.tab || FRAME.tab;
    // One formula with ClusterStyle.title_width, on the numbers both
    // renderers read: max(label_min, characters * size * label_advance +
    // label_pad) + tab, clamped to the frame's width. The advance is the one
    // the shipped checker measures text with.
    const title = METRICS.frame || {};
    const advance = Number.isFinite(title.label_advance) ? title.label_advance : 0.58;
    const pad = Number.isFinite(title.label_pad) ? title.label_pad : 12;
    const least = Number.isFinite(title.label_min) ? title.label_min : 48;
    const width = Math.min(
      Math.max(least, label.length * labelSize * advance + pad) + (boundary.tabbed ? tab : 20),
      Math.max(least, boundary.width),
    );
    return {
      x: boundary.x, y: boundary.y - labelSize,
      width, height: labelSize + tab,
    };
  };

  const refreshRouteContext = () => {
    const visible = state.nodes.filter(nodeIsVisible);
    const labelled = (state.boundaries || []).filter(boundaryIsVisible);
    const signature = [
      ...visible.map(node => `${node.id}:${node.x},${node.y},${node.width},${node.height}`),
      ...labelled.map(b => `b${b.id}:${b.x},${b.y},${b.width},${b.height},${b.name},${(b.badges || []).map(badge => badge.label).join('/')}`),
    ].join('|');
    // Nothing has moved: every route still ends where it did, around the same
    // boxes, so the ones already worked out stand. Selecting, hovering and
    // opening a panel all redraw, and none of them re-routes a wire.
    if (signature === routeContext.signature) return;
    const byNode = new Map();
    const boxes = visible.map(node => {
      const box = inflated(node, ROUTE.clearance);
      byNode.set(node.id, box);
      return box;
    });
    // each frame's title, then its corner badges (cluster_badge_rect)
    labelled.forEach(boundary => {
      [boundaryLabelBox(boundary), boundaryBadgeBox(boundary)].forEach(box => {
        if (box) boxes.push(inflated(box, 1));
      });
    });
    // While a card is being dragged, only the wires it carries are worked out
    // again. The rest keep the route they had and settle when the drag ends,
    // which is the difference between a drawing that follows the pointer and
    // one that stutters behind it.
    const moving = drag?.type === 'node' ? new Set(Object.keys(drag.nodePositions || {})) : null;
    const kept = new Map();
    if (moving?.size) {
      const carried = new Set(state.edges
        .filter(edge => moving.has(edge.source) || moving.has(edge.target))
        .map(edge => edge.id));
      routeContext.cache.forEach((value, key) => {
        // matched against the ids themselves: an id may contain the separator
        const moved = [...carried].some(id => key.startsWith(`${id}|`));
        if (!moved) kept.set(key, value);
      });
    }
    routeContext = {signature, boxes, rails: frameRails(labelled), frames: labelled, byNode, cache: kept};
  };

  const routingEnabled = () => state.canvas.routeAroundNodes !== false;

  const connectorPath = item => {
    const heads = edgeHeads(item.edge);
    const bend = cornerRadius(item.edge);
    // Where each end touches the drawing, for the path and its terminals.
    const finish = path => {
      item.sourceSeat = seat(item.source, item.sourcePort, item.sourcePoint);
      item.targetSeat = seat(item.target, item.targetPort, item.targetPoint);
      return path;
    };
    const simple = routedPath(seat(item.source, item.sourcePort, item.sourcePoint),
      seat(item.target, item.targetPort, item.targetPoint), item.sourcePort, heads, bend);
    if (!routingEnabled()) return finish(simple);
    // A wire carried by a card being dragged takes the plain path until the
    // card is dropped. Searching a way around the other cards on every move,
    // for a card that is still moving, is what made a large diagram stutter;
    // the route settles the moment the drag ends.
    if (drag?.type === 'node' && (drag.nodePositions?.[item.edge.source] || drag.nodePositions?.[item.edge.target])) {
      return finish(simple);
    }
    const pinned = Array.isArray(item.edge.waypoints) && item.edge.waypoints.length;
    const manual = pinned
      ? item.edge.waypoints.filter(point => Number.isFinite(point?.x) && Number.isFinite(point?.y))
      : laneCorner(item.sourcePoint, item.targetPoint, parallelLane(item));
    if (manual && manual.length) {
      // The cards a bent wire must still miss: everything but its own two.
      const between = [
        ...routeContext.boxes.filter(box => box !== routeContext.byNode.get(item.source.id)
          && box !== routeContext.byNode.get(item.target.id)),
        ...ownBoxes(item.source), ...ownBoxes(item.target),
      ];
      const bent = bentCorners(item.sourcePoint, item.targetPoint,
        item.sourcePort, item.targetPort, manual,
        (a, b) => between.some(box => segmentBlocked(box, a, b)));
      const corners = tidyCorners(seatEnds(item, item, bent));
      // An automatic parallel lane is only a preference: if its elbows
      // cross an obstacle, use the normal search and lane spreading below.
      // Explicit waypoints stay pinned and the picture checker judges them.
      const fences = pinned ? [] : fenceBoxes(routeContext.frames, item.source, item.target);
      const clear = pinned || !corners.some((point, index) => index > 0
        && (between.some(box => segmentBlocked(box, corners[index - 1], point))
          || railRun(routeContext.rails, corners[index - 1], point) >= ROUTE.railRun
          || fenceCrossings(fences, corners[index - 1], point)));
      if (clear) {
        item.shaped = true;
        item.plainRoute = false;
        item.routeCorners = corners;
        item.rawCorners = null;
        return finish(roundedPath(corners, heads, bend) || simple);
      }
    }
    // What is cached is a drawn path, so everything that draws it belongs in
    // the key: move a card and the ends change, restyle a wire and its heads
    // or its corners do. The cache outlives a render now, and a key that
    // forgot the style would hand back the picture from before the change.
    const cacheKey = [item.edge.id, item.sourcePoint.x, item.sourcePoint.y,
      item.targetPoint.x, item.targetPoint.y, item.sourcePort, item.targetPort,
      edgeArrow(item.edge), edgeCorners(item.edge), edgeDirection(item.edge),
      Number(item.edge.style?.width) || item.edge.width || 1.4].join('|');
    item.shaped = false;
    item.routeKey = cacheKey;
    // A route may have moved the wire's ends to other sides of its cards, so
    // the cache carries the ends with the path and a hit restores them.
    const cached = routeContext.cache.get(cacheKey);
    if (cached) {
      Object.assign(item, cached.ends);
      item.routeCorners = cached.corners;
      item.rawCorners = cached.corners;
      item.plainRoute = Boolean(cached.plain);
      const spread = laneSpread.get(item.edge.id);
      if (spread && spread.key === cacheKey) {
        item.routeCorners = spread.corners;
        item.plainRoute = false;
        return finish(spread.path);
      }
      return finish(cached.path);
    }
    const skip = new Set([routeContext.byNode.get(item.source.id), routeContext.byNode.get(item.target.id)]);
    // Other cards keep their clearance; the wire's own two cards are hard
    // obstacles at their true size, so a wire never runs back through the
    // card it leaves or arrives at.
    const own = [...ownBoxes(item.source), ...ownBoxes(item.target)];
    const boxes = [...routeContext.boxes.filter(box => !skip.has(box)), ...own];
    let path = simple;
    let corners = null;
    const ends = {
      sourcePoint: item.sourcePoint, targetPoint: item.targetPoint,
      sourcePort: item.sourcePort, targetPort: item.targetPort,
    };
    // ... and to cross a frame that holds neither of its ends
    const fences = fenceBoxes(routeContext.frames, item.source, item.target);
    if (boxes.length) {
      // Only pay for a search when the plain path actually hits something.
      const straight = tidyCorners(simplePathCorners(item));
      // ... or when it runs along a frame's border: a wire there reads as
      // the border (frame rails), or crosses a frame that holds neither end.
      // ... or when it leaves or arrives along a side instead of straight
      // out of it: a dog-leg whose middle falls on an anchor's own line.
      const level = (a, b) => Math.abs(a.y - b.y) < 0.5;
      const across = side => side === 'left' || side === 'right';
      const last = straight.length - 1;
      const sideways = straight.length > 1
        && (level(straight[0], straight[1]) !== across(item.sourcePort)
          || level(straight[last - 1], straight[last]) !== across(item.targetPort));
      // The rails are asked of the plain path as drawn too: from the seated
      // ends its middle may sit a few pixels off the one routed here.
      const seated = tidyCorners(simplePathCorners({...item,
        sourcePoint: seat(item.source, item.sourcePort, item.sourcePoint),
        targetPoint: seat(item.target, item.targetPort, item.targetPoint)}));
      const hits = sideways || straight.some((point, index) => index > 0
        && boxes.some(box => segmentBlocked(box, straight[index - 1], point)))
        || [straight, seated].some(corners => corners.some((point, index) => index > 0
          && (railRun(routeContext.rails, corners[index - 1], point) >= ROUTE.railRun
            || fenceCrossings(fences, corners[index - 1], point))));
      if (hits) {
        // A wire leaves its side straight out and arrives straight in (ADR
        // 0006, rule 8): the search runs between a point one stub outside
        // each anchor and the anchors are spliced back on, so the first and
        // last segments are perpendicular to the sides they meet and a route
        // can never slide along a glyph's or a card's border to get in.
        // The strip between an anchor and its stub point is a wall the search
        // may not cross, so it can only arrive at the stub from outside: a
        // route that reached it from the node's side would fold back on the
        // spliced stub and leave a one-pixel leg under the head. The strip
        // stops a pixel short of the stub point, which stays free, and adds
        // no lanes of its own.
        const strip = (anchor, stub) => {
          const short = {x: stub.x + Math.sign(anchor.x - stub.x), y: stub.y + Math.sign(anchor.y - stub.y)};
          return {
            left: Math.min(anchor.x, short.x) - 0.25, right: Math.max(anchor.x, short.x) + 0.25,
            top: Math.min(anchor.y, short.y) - 0.25, bottom: Math.max(anchor.y, short.y) + 0.25,
          };
        };
        // The search also pays to run along the wire's own cards, which it
        // may touch but should not graze: a wire along its card's edge reads
        // as the card's outline (render.py _box_rails).
        const searchedRails = [...routeContext.rails, ...own.flatMap(box => [
          {axis: 'h', at: box.top, lo: box.left, hi: box.right},
          {axis: 'h', at: box.bottom, lo: box.left, hi: box.right},
          {axis: 'v', at: box.left, lo: box.top, hi: box.bottom},
          {axis: 'v', at: box.right, lo: box.top, hi: box.bottom},
        ])];
        const routeSides = (start, out, end, into) => {
          const a = outward(start, out, boxes);
          const b = outward(end, into, boxes);
          const walls = [strip(start, a), strip(end, b)];
          const near = nearestObstacles(a, b, boxes);
          const found = routeCorners(a, b, near === boxes ? boxes : [...near, ...own], walls, searchedRails, fences)
            || (near === boxes ? null : routeCorners(a, b, boxes, walls, searchedRails, fences));
          return found ? tidyCorners([start, ...found, end]) : null;
        };
        corners = routeSides(item.sourcePoint, item.sourcePort, item.targetPoint, item.targetPort);
        if (!corners) {
          // Boxed in on the facing sides. Try the other sides of any port the
          // author left on auto, horizontal pairs first because they read
          // best, and keep the first pair that routes clear. A side is never
          // paired with itself: that wire would wrap around the node.
          const sides = ['right', 'left', 'bottom', 'top'];
          const sourceSides = item.edge.sourcePort === 'auto' ? sides : [item.sourcePort];
          const targetSides = item.edge.targetPort === 'auto' ? sides : [item.targetPort];
          outer: for (const out of sourceSides) {
            for (const into of targetSides) {
              if ((out === item.sourcePort && into === item.targetPort) || out === into) continue;
              const start = out === item.sourcePort ? item.sourcePoint : portPoint(item.source, out);
              const end = into === item.targetPort ? item.targetPoint : portPoint(item.target, into);
              const found = routeSides(start, out, end, into);
              if (found) {
                corners = found;
                Object.assign(ends, {sourcePoint: start, targetPoint: end, sourcePort: out, targetPort: into});
                break outer;
              }
            }
          }
        }
        if (corners) path = roundedPath(seatEnds(item, ends, corners), heads, bend) || simple;
      }
    }
    Object.assign(item, ends);
    item.routeCorners = corners || tidyCorners([ends.sourcePoint, ...simplePathCorners({...item, ...ends}).slice(1, -1), ends.targetPoint]);
    routeContext.cache.set(cacheKey, {path, ends, corners: item.routeCorners, plain: !corners});
    item.rawCorners = item.routeCorners;
    item.plainRoute = !corners;
    return finish(path);
  };

  // Every wire routed, the ones that run along one line are drawn apart
  // (spreadWires; builders/render.py _route_all): what the boxes and the
  // frame rails leave room for. Hand-shaped wires stay as drawn. Run once a
  // render, after the routes have settled, before anything is drawn.
  const spreadLanes = edges => {
    laneSpread = new Map();
    if (!routingEnabled()) return;
    // from each route as routed, never as the last render spread it
    const wires = edges.map(item => (item.shaped || !item.rawCorners ? null : item.rawCorners));
    const boxes = [
      ...state.nodes.filter(nodeIsVisible).flatMap(node => ownBoxes(node)),
      ...(state.boundaries || []).filter(boundaryIsVisible)
        .flatMap(boundary => [boundaryLabelBox(boundary), boundaryBadgeBox(boundary)])
        .filter(Boolean)
        .map(box => inflated(box, 0)),
    ];
    const spread = spreadWires(wires, boxes, routeContext.rails);
    edges.forEach((item, index) => {
      const corners = spread[index];
      const was = wires[index];
      if (!corners || (corners.length === was.length
          && corners.every((point, i) => point.x === was[i].x && point.y === was[i].y))) return;
      const path = roundedPath(seatEnds(item, item, corners), edgeHeads(item.edge), cornerRadius(item.edge));
      if (!path) return;
      laneSpread.set(item.edge.id, {key: item.routeKey, corners, path});
      item.routeCorners = corners;
      item.plainRoute = false;
    });
  };

  // The corners a wire's caption is placed along: the route, or for a plain
  // path the path as drawn from its seated ends, whose middle sits a few
  // pixels off the one routed between the anchors (render.py, _place_captions).
  const captionCorners = item => {
    if (item.plainRoute && item.routeCorners) {
      return tidyCorners(simplePathCorners({...item,
        sourcePoint: seat(item.source, item.sourcePort, item.sourcePoint),
        targetPoint: seat(item.target, item.targetPort, item.targetPoint)}));
    }
    return item.routeCorners || tidyCorners(simplePathCorners(item));
  };

  // A point a given way along a polyline, and whether that stretch is level.
  const alongPolyline = (corners, ratio) => {
    const lengths = corners.slice(1).map((point, index) => (
      Math.abs(point.x - corners[index].x) + Math.abs(point.y - corners[index].y)));
    let remaining = lengths.reduce((sum, length) => sum + length, 0) * ratio;
    for (let index = 0; index < lengths.length; index += 1) {
      const a = corners[index];
      const b = corners[index + 1];
      if (remaining <= lengths[index] || index === lengths.length - 1) {
        const t = lengths[index] ? Math.max(0, Math.min(1, remaining / lengths[index])) : 0;
        return {x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t,
          horizontal: Math.abs(b.x - a.x) >= Math.abs(b.y - a.y)};
      }
      remaining -= lengths[index];
    }
    return {x: corners[0].x, y: corners[0].y, horizontal: true};
  };

  // The corner list the naive path would draw, for the "is it blocked" test.
  const simplePathCorners = item => {
    const start = item.sourcePoint;
    const end = item.targetPoint;
    if (Math.abs(start.y - end.y) < 0.01 || Math.abs(start.x - end.x) < 0.01) return [start, end];
    if (['left', 'right'].includes(item.sourcePort)) {
      const mid = snap((start.x + end.x) / 2);
      return [start, {x: mid, y: start.y}, {x: mid, y: end.y}, end];
    }
    const mid = snap((start.y + end.y) / 2);
    return [start, {x: start.x, y: mid}, {x: end.x, y: mid}, end];
  };

  // A wire bent by hand turns at right angles like every other wire: it runs
  // the stub straight out of its side, elbows through each corner it was
  // pinned to, and comes straight into the other side.
  // The static renderer bends the same way (_bent_corners in builders/render).
  const STUB_OUT = {
    left: {x: -1, y: 0}, right: {x: 1, y: 0}, top: {x: 0, y: -1}, bottom: {x: 0, y: 1},
  };
  // Wires that join the same two components share both anchors -- a side
  // has one connection point -- so they would draw one on top of
  // another. Each takes a lane of its own through the middle instead, which
  // is a bend the router puts there rather than the reader.
  const parallelLane = item => {
    const pair = [item.edge.source, item.edge.target].sort().join('\u0000');
    // Only the wires actually drawn share the lanes; one whose layer is hidden
    // is not there to be drawn on top of, and the static renderer counts the
    // same way (it is given the links it built).
    const siblings = state.edges.filter(edge => [edge.source, edge.target].sort().join('\u0000') === pair
      && nodeIsVisible(nodeById(edge.source)) && nodeIsVisible(nodeById(edge.target)));
    if (siblings.length < 2) return 0;
    const index = siblings.findIndex(edge => edge.id === item.edge.id);
    return (index - (siblings.length - 1) / 2) * METRICS.router.lane;
  };
  const laneCorner = (start, end, offset) => {
    if (!offset) return [];
    const middle = {x: (start.x + end.x) / 2, y: (start.y + end.y) / 2};
    return Math.abs(end.x - start.x) >= Math.abs(end.y - start.y)
      ? [{x: middle.x, y: middle.y + offset}]
      : [{x: middle.x + offset, y: middle.y}];
  };

  const bentCorners = (start, end, sourcePort, targetPort, points, blocked = () => false) => {
    const stub = METRICS.router.stub;
    const away = STUB_OUT[sourcePort] || STUB_OUT.right;
    const into = STUB_OUT[targetPort] || STUB_OUT.left;
    const chain = [
      start,
      {x: start.x + away.x * stub, y: start.y + away.y * stub},
      ...points,
      {x: end.x + into.x * stub, y: end.y + into.y * stub},
      end,
    ];
    const corners = [chain[0]];
    let horizontal = ['left', 'right'].includes(sourcePort);
    for (let index = 1; index < chain.length; index += 1) {
      const previous = corners[corners.length - 1];
      const point = chain[index];
      const movesX = Math.abs(point.x - previous.x) > 0.5;
      const movesY = Math.abs(point.y - previous.y) > 0.5;
      if (movesX && movesY) {
        // Two ways to turn a corner. Take the one that keeps the wire off
        // whatever stands between; failing that, the one that turns first,
        // so the wire never doubles back along the line it came in on.
        const turning = {x: previous.x, y: point.y};
        const carrying = {x: point.x, y: previous.y};
        const clear = elbow => !blocked(previous, elbow) && !blocked(elbow, point);
        const first = horizontal ? turning : carrying;
        const second = horizontal ? carrying : turning;
        corners.push(clear(first) || !clear(second) ? first : second);
      } else if (movesX || movesY) {
        horizontal = movesX;
      }
      corners.push(point);
    }
    return corners;
  };

  const routedPath = (start, end, sourcePort = 'right', heads = {start: false, end: true}, maxRadius = cornerRadius()) => {
    const [a, b] = trimHeads([start, end], heads);
    if (Math.abs(start.y - end.y) < 0.01) return `M${a.x},${a.y} H${b.x}`;
    if (Math.abs(start.x - end.x) < 0.01) return `M${a.x},${a.y} V${b.y}`;
    if (['left', 'right'].includes(sourcePort)) {
      const mid = snap((start.x + end.x) / 2);
      return roundedPath([start, {x: mid, y: start.y}, {x: mid, y: end.y}, end], heads, maxRadius);
    }
    const mid = snap((start.y + end.y) / 2);
    return roundedPath([start, {x: start.x, y: mid}, {x: end.x, y: mid}, end], heads, maxRadius);
  };

  // Crossings alter only the final ink, after routing, lanes and captions.
  // Horizontal wires hop upward; a transparent mask separates the vertical
  // wire at the arc's crown. builders/crossings.py follows the same policy.
  const crossingStyle = () => (
    (state.canvas.crossings || generatedState.canvas.crossings) === 'bridge' ? 'bridge' : 'plain'
  );
  const crossingSegments = (path, wire) => {
    if ([...(path.match(/[A-Za-z]/g) || [])].some(letter => !'MLQHVeE'.includes(letter))) return [];
    let point = [0, 0];
    const segments = [];
    for (const match of path.matchAll(/([MLQHV])([^MLQHV]*)/g)) {
      const values = (match[2].match(/[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g) || []).map(Number);
      if (!values.length) continue;
      const end = match[1] === 'H' ? [values[0], point[1]]
        : match[1] === 'V' ? [point[0], values[0]] : values.slice(-2);
      if ('LHV'.includes(match[1]) && (point[0] === end[0] || point[1] === end[1])) {
        segments.push({wire, start: match.index, end: match.index + match[0].length, a: point, b: end});
      }
      point = end;
    }
    return segments;
  };
  const crossingPlan = (wires, obstacles = []) => {
    const radius = METRICS.router.crossing_radius;
    const padding = METRICS.router.crossing_clearance;
    const segments = wires.flatMap(([path], index) => crossingSegments(path, index));
    const horizontal = segments.filter(segment => segment.a[1] === segment.b[1]);
    const vertical = segments.filter(segment => segment.a[0] === segment.b[0]);
    const overlaps = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    const hits = new Map();
    for (const h of horizontal) {
      for (const v of vertical) {
        if (h.wire === v.wire) continue;
        const x = v.a[0], y = h.a[1];
        const cut = Math.max(2.5, (wires[h.wire][1] + wires[v.wire][1]) / 2 + 1);
        const clearance = radius + Math.max(cut + padding, ARROWHEADS.shaft);
        if (!(Math.min(h.a[0], h.b[0]) + clearance < x && x < Math.max(h.a[0], h.b[0]) - clearance
          && Math.min(v.a[1], v.b[1]) + clearance < y && y < Math.max(v.a[1], v.b[1]) - clearance)) continue;
        const reach = {left:x-radius-padding, top:y-radius-cut-padding, right:x+radius+padding, bottom:y+cut+padding};
        if (reach.left < 0 || reach.top < 0 || obstacles.some(box => overlaps(reach, box))) continue;
        if (segments.some(s => s !== h && s !== v && overlaps(reach, {
          left:Math.min(s.a[0],s.b[0]), top:Math.min(s.a[1],s.b[1]),
          right:Math.max(s.a[0],s.b[0]), bottom:Math.max(s.a[1],s.b[1]),
        }))) continue;
        if (!hits.has(h)) hits.set(h, []);
        hits.get(h).push([x,y,cut,v.wire]);
      }
    }
    const paths = wires.map(([path]) => path), masks = new Map(), counts = new Map(), edits = new Map();
    for (const [segment, candidates] of hits) {
      const chosen = [];
      candidates.sort((a,b) => a[0]-b[0]).forEach(hit => {
        if (!chosen.length || hit[0]-chosen[chosen.length-1][0] > 2*(radius+hit[2]+padding)) chosen.push(hit);
      });
      const direction = segment.b[0] > segment.a[0] ? 1 : -1;
      const parts = [];
      if (direction < 0) chosen.reverse();
      for (const [x,y,cut,under] of chosen) {
        parts.push(`L${x-direction*radius},${y} A${radius},${radius} 0 0 ${direction > 0 ? 1 : 0} ${x+direction*radius},${y}`);
        if (!masks.has(under)) masks.set(under, []);
        masks.get(under).push([x,y-radius,cut]);
        counts.set(segment.wire, (counts.get(segment.wire) || 0)+1);
      }
      parts.push(`L${segment.b[0]},${segment.b[1]} `);
      if (!edits.has(segment.wire)) edits.set(segment.wire, []);
      edits.get(segment.wire).push([segment.start,segment.end,parts.join(' ')]);
    }
    for (const [index, replacements] of edits) {
      replacements.sort((a,b) => b[0]-a[0]).forEach(([start,end,text]) => {
        paths[index] = paths[index].slice(0,start)+text+paths[index].slice(end);
      });
    }
    return {paths,masks,counts};
  };
  const applyCrossings = items => {
    defs.querySelectorAll('[data-crossing-mask]').forEach(mask => mask.remove());
    // A full draw already put down plain paths; Plain adds no extra work.
    if (crossingStyle() !== 'bridge') return;
    const paths = items.map(item => connectorPath(item));
    const obstacles = state.nodes.filter(nodeIsVisible).flatMap(ownBoxes);
    state.boundaries.filter(boundaryIsVisible).forEach(boundary => {
      [boundaryLabelBox(boundary), boundaryBadgeBox(boundary)].filter(Boolean)
        .forEach(box => obstacles.push(inflated(box,0)));
    });
    const matrix = diagram.getCTM();
    if (matrix) {
      const inverse = matrix.inverse();
      diagram.querySelectorAll('[data-edge-label]').forEach(element => {
        const box = element.getBBox(), transform = element.getCTM();
        if (!transform) return;
        const local = inverse.multiply(transform);
        const a = new DOMPoint(box.x,box.y).matrixTransform(local);
        const b = new DOMPoint(box.x+box.width,box.y+box.height).matrixTransform(local);
        obstacles.push({left:Math.min(a.x,b.x),top:Math.min(a.y,b.y),right:Math.max(a.x,b.x),bottom:Math.max(a.y,b.y)});
      });
    }
    const plan = crossingPlan(items.map((item,index) => [paths[index],
      Number(item.edge.style?.width) || item.edge.width || 1.4]), obstacles);
    items.forEach((item,index) => {
      const id = CSS.escape(item.edge.id);
      const wire = diagram.querySelector(`[data-graph-edge][data-edge-id="${id}"]`);
      if (!wire) return;
      const path = plan.paths[index];
      [wire, diagram.querySelector(`[data-edge-hit="${id}"]`),
        diagram.querySelector(`[data-edge-group="${id}"] [data-edge-selection-halo]`)]
        .filter(Boolean).forEach(element => element.setAttribute('d',path));
      wire.removeAttribute('mask');
      wire.removeAttribute('data-crossing-count');
      if (plan.counts.has(index)) wire.dataset.crossingCount = String(plan.counts.get(index));
      if (plan.masks.has(index)) {
        const maskId = `infragram-crossing-${index}`;
        const circles = plan.masks.get(index).map(([x,y,r]) => `<circle cx="${x}" cy="${y}" r="${r}" fill="#000"/>`).join('');
        defs.insertAdjacentHTML('beforeend', `<mask data-crossing-mask id="${maskId}" maskUnits="userSpaceOnUse" x="0" y="0" width="${state.canvas.width}" height="${state.canvas.height}" style="mask-type:luminance"><rect width="${state.canvas.width}" height="${state.canvas.height}" fill="#fff"/>${circles}</mask>`);
        wire.setAttribute('mask',`url(#${maskId})`);
      }
    });
  };
