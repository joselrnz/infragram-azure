// @module 13-canvas-geometry: visibility, canvas extent and alignment guides
  const boundaryIsVisible = boundary => {
    if (!boundary || !isLayerVisible(boundary.layerId)) return false;
    return !boundary.parentId || boundaryIsVisible(boundaryById(boundary.parentId));
  };
  const nodeIsVisible = node => (
    Boolean(node)
    && isLayerVisible(node.layerId)
    && (!node.boundaryId || boundaryIsVisible(boundaryById(node.boundaryId)))
  );
  const CANVAS_GROWTH = 400;
  const CANVAS_MARGIN = 320;
  const contentBounds = () => {
    const items = [
      ...state.boundaries.filter(boundaryIsVisible),
      ...state.nodes.filter(nodeIsVisible),
    ];
    if (!items.length) return null;
    return {
      left: Math.min(...items.map(item => item.x)),
      top: Math.min(...items.map(item => item.y)),
      right: Math.max(...items.map(item => item.x + item.width)),
      bottom: Math.max(...items.map(item => item.y + item.height)),
    };
  };
  // Routed wires and their captions may extend beyond the lowest card.
  // Measure them in diagram coordinates, including each group's transform.
  const drawnBounds = () => {
    const bounds = contentBounds();
    const matrix = diagram.getCTM();
    if (!bounds || !matrix) return bounds;
    const inverse = matrix.inverse();
    diagram.querySelectorAll('[data-graph-edge],[data-edge-label]').forEach(element => {
      const transform = element.getCTM();
      if (!transform) return;
      const box = element.getBBox();
      const local = inverse.multiply(transform);
      [[box.x, box.y], [box.x + box.width, box.y],
        [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]
        .forEach(([x, y]) => {
          const point = new DOMPoint(x, y).matrixTransform(local);
          bounds.left = Math.min(bounds.left, point.x);
          bounds.top = Math.min(bounds.top, point.y);
          bounds.right = Math.max(bounds.right, point.x);
          bounds.bottom = Math.max(bounds.bottom, point.y);
        });
    });
    return bounds;
  };
  const syncViewportGutter = () => {
    stage.style.setProperty('--canvas-gutter-x', `${Math.ceil(viewport.clientWidth / 2)}px`);
    stage.style.setProperty('--canvas-gutter-y', `${Math.ceil(viewport.clientHeight / 2)}px`);
  };
  const canvasOrigin = () => {
    const viewportRect = viewport.getBoundingClientRect();
    const diagramRect = diagram.getBoundingClientRect();
    return {
      x: diagramRect.left - viewportRect.left + viewport.scrollLeft,
      y: diagramRect.top - viewportRect.top + viewport.scrollTop,
    };
  };
  const syncCanvasGeometry = () => {
    const viewBox = `0 0 ${state.canvas.width} ${state.canvas.height}`;
    const width = `${state.canvas.width * zoom}px`;
    const height = `${state.canvas.height * zoom}px`;
    if (diagram.getAttribute('viewBox') !== viewBox) diagram.setAttribute('viewBox', viewBox);
    if (diagram.style.width !== width) diagram.style.width = width;
    if (diagram.style.height !== height) diagram.style.height = height;
    const background = layer.querySelector('[data-canvas-background]');
    const grid = layer.querySelector('[data-editor-grid]');
    [background, grid].filter(Boolean).forEach(element => {
      const canvasWidth = String(state.canvas.width);
      const canvasHeight = String(state.canvas.height);
      if (element.getAttribute('width') !== canvasWidth) element.setAttribute('width', canvasWidth);
      if (element.getAttribute('height') !== canvasHeight) element.setAttribute('height', canvasHeight);
    });
    const inspectorCanvas = document.querySelector('[data-inspector-canvas]');
    if (inspectorCanvas) inspectorCanvas.textContent = `${state.canvas.width} × ${state.canvas.height}`;
  };
  const ensureCanvasExtent = ({right = 0, bottom = 0, save = false} = {}) => {
    const bounds = contentBounds() || {right: 0, bottom: 0};
    const viewportWidth = viewport.clientWidth / Math.max(zoom, 0.01);
    const viewportHeight = viewport.clientHeight / Math.max(zoom, 0.01);
    const nextWidth = Math.ceil(Math.max(
      Number(state.canvas.width) || 0,
      Number(generatedState.canvas.width) || 0,
      viewportWidth,
      bounds.right + CANVAS_MARGIN,
      right,
    ) / CANVAS_GROWTH) * CANVAS_GROWTH;
    const nextHeight = Math.ceil(Math.max(
      Number(state.canvas.height) || 0,
      Number(generatedState.canvas.height) || 0,
      viewportHeight,
      bounds.bottom + CANVAS_MARGIN,
      bottom,
    ) / CANVAS_GROWTH) * CANVAS_GROWTH;
    const changed = nextWidth !== state.canvas.width || nextHeight !== state.canvas.height;
    state.canvas.width = nextWidth;
    state.canvas.height = nextHeight;
    syncCanvasGeometry();
    if (changed && save) persist();
    return changed;
  };
  const alignmentAxis = (node, raw, axis) => {
    const horizontal = axis === 'x';
    const size = horizontal ? node.width : node.height;
    const moving = [raw, raw + size / 2, raw + size];
    const candidates = state.nodes
      .filter(item => item.id !== node.id && !selectedNodeIds.has(item.id) && nodeIsVisible(item))
      .flatMap(item => {
        const start = horizontal ? item.x : item.y;
        const extent = horizontal ? item.width : item.height;
        return [start, start + extent / 2, start + extent];
      });
    const tolerance = 6 / zoom;
    let match = null;
    moving.forEach((value, movingIndex) => candidates.forEach(candidate => {
      const distance = Math.abs(candidate - value);
      if (distance <= tolerance && (!match || distance < match.distance)) {
        match = {distance, delta: candidate - value, position: candidate, movingIndex};
      }
    }));
    if (!match) return {value: snap(raw), guide: null};
    const value = raw + match.delta;
    const perpendicularStart = horizontal
      ? Math.min(node.y, ...state.nodes.filter(nodeIsVisible).map(item => item.y))
      : Math.min(node.x, ...state.nodes.filter(nodeIsVisible).map(item => item.x));
    const perpendicularEnd = horizontal
      ? Math.max(node.y + node.height, ...state.nodes.filter(nodeIsVisible).map(item => item.y + item.height))
      : Math.max(node.x + node.width, ...state.nodes.filter(nodeIsVisible).map(item => item.x + item.width));
    return {
      value,
      guide: {
        axis,
        position: match.position,
        from: perpendicularStart - 24,
        to: perpendicularEnd + 24,
      },
    };
  };
  const alignedNodePosition = (node, rawX, rawY, bypass = false) => {
    if (bypass) {
      return {
        x: clamp(rawX, 0, state.canvas.width - node.width),
        y: clamp(rawY, 0, state.canvas.height - node.height),
        guides: [],
      };
    }
    const spacingMatch = (raw, axis) => {
      const horizontal = axis === 'x';
      const size = horizontal ? node.width : node.height;
      const center = raw + size / 2;
      const peers = state.nodes
        .filter(item => item.id !== node.id && !selectedNodeIds.has(item.id) && nodeIsVisible(item))
        .map(item => ({
          center: (horizontal ? item.x : item.y) + (horizontal ? item.width : item.height) / 2,
          cross: horizontal ? node.y + node.height + 16 : node.x + node.width + 16,
        }))
        .sort((a, b) => a.center - b.center);
      let match = null;
      for (let leftIndex = 0; leftIndex < peers.length; leftIndex += 1) {
        for (let rightIndex = leftIndex + 1; rightIndex < peers.length; rightIndex += 1) {
          const midpoint = (peers[leftIndex].center + peers[rightIndex].center) / 2;
          const distance = Math.abs(midpoint - center);
          if (distance <= 6 / zoom && (!match || distance < match.distance)) {
            match = {
              distance,
              value: raw + midpoint - center,
              guide: {
                axis: `spacing-${axis}`,
                from: peers[leftIndex].center,
                to: peers[rightIndex].center,
                position: peers[leftIndex].cross,
                middle: midpoint,
              },
            };
          }
        }
      }
      return match;
    };
    const xMatch = alignmentAxis(node, rawX, 'x');
    const yMatch = alignmentAxis(node, rawY, 'y');
    const xSpacing = xMatch.guide ? null : spacingMatch(rawX, 'x');
    const ySpacing = yMatch.guide ? null : spacingMatch(rawY, 'y');
    return {
      x: clamp(xSpacing?.value ?? xMatch.value, 0, state.canvas.width - node.width),
      y: clamp(ySpacing?.value ?? yMatch.value, 0, state.canvas.height - node.height),
      guides: [xMatch.guide, yMatch.guide, xSpacing?.guide, ySpacing?.guide].filter(Boolean),
    };
  };
  const alignmentGuideMarkup = guide => {
    const colors = canvasPalette();
    if (guide.axis === 'spacing-x') {
      return `<path data-alignment-guide data-guide-kind="equal-spacing" d="M${guide.from},${guide.position - 4}V${guide.position + 4}M${guide.from},${guide.position}H${guide.to}M${guide.middle},${guide.position - 4}V${guide.position + 4}M${guide.to},${guide.position - 4}V${guide.position + 4}" fill="none" stroke="${colors.accent}" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
    }
    if (guide.axis === 'spacing-y') {
      return `<path data-alignment-guide data-guide-kind="equal-spacing" d="M${guide.position - 4},${guide.from}H${guide.position + 4}M${guide.position},${guide.from}V${guide.to}M${guide.position - 4},${guide.middle}H${guide.position + 4}M${guide.position - 4},${guide.to}H${guide.position + 4}" fill="none" stroke="${colors.accent}" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
    }
    return guide.axis === 'x'
      ? `<line data-alignment-guide x1="${guide.position}" y1="${guide.from}" x2="${guide.position}" y2="${guide.to}" stroke="${colors.accent}" stroke-width="1" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>`
      : `<line data-alignment-guide x1="${guide.from}" y1="${guide.position}" x2="${guide.to}" y2="${guide.position}" stroke="${colors.accent}" stroke-width="1" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>`;
  };
