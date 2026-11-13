// @module 29-downloads: picture, editable document and Terraform downloads
  const cropExportSvg = (copy, margin = 32) => {
    // Measure the clean copy in SVG coordinates, including rotated nodes,
    // routed wires, captions, metadata, the provider mark and optional key.
    // Editing-canvas dimensions and the current zoom never size a picture.
    const holder = document.createElement('div');
    holder.style.cssText = 'position:fixed;left:-100000px;top:0;visibility:hidden;pointer-events:none;';
    const world = copy.viewBox.baseVal;
    copy.setAttribute('width', String(world.width));
    copy.setAttribute('height', String(world.height));
    holder.appendChild(copy);
    document.body.appendChild(holder);
    try {
      const matrix = copy.getCTM();
      if (!matrix) throw new Error('The export bounds could not be measured');
      const inverse = matrix.inverse();
      let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
      copy.querySelectorAll('[data-graph-node],[data-graph-boundary],[data-graph-edge],[data-edge-label],[data-static-meta-layer],[data-brand-mark],[data-legend-strip],[data-export-title],[data-step-list],[data-status-block]').forEach(element => {
        const screen = element.getBoundingClientRect();
        if (!screen.width && !screen.height) return;
        const transform = element.getCTM();
        if (!transform) return;
        const box = element.getBBox(), local = inverse.multiply(transform);
        [[box.x, box.y], [box.x + box.width, box.y], [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]].forEach(([x, y]) => {
          const point = new DOMPoint(x, y).matrixTransform(local);
          left = Math.min(left, point.x); top = Math.min(top, point.y);
          right = Math.max(right, point.x); bottom = Math.max(bottom, point.y);
        });
      });
      // An empty drawing exports a modest empty picture, not an enormous canvas.
      if (!Number.isFinite(left)) { left = 0; top = 0; right = 320; bottom = 180; }
      const x = Math.floor(left - margin), y = Math.floor(top - margin);
      const width = Math.max(1, Math.ceil(right + margin) - x);
      const height = Math.max(1, Math.ceil(bottom + margin) - y);
      copy.setAttribute('viewBox', `${x} ${y} ${width} ${height}`);
      copy.setAttribute('width', String(width));
      copy.setAttribute('height', String(height));
    } finally { holder.remove(); }
  };
  const exportSvg = ({includeLegend = legendEnabled('exportLegend'), background} = {}) => {
    // an open frame is a view: the picture is always the whole diagram
    if (drillPath.length) return wholeDrawing(() => exportSvg({includeLegend, background}));
    const copy = diagram.cloneNode(true);
    copy.setAttribute('xmlns', SVG_NS);
    copy.removeAttribute('tabindex');
    copy.removeAttribute('data-pointer-focus');
    copy.querySelectorAll('#infragram-editor-grid,[data-static-cluster-layer],[data-static-link-layer],[data-static-node-layer],[data-canvas-background],[data-editor-grid],[data-edge-terminal-layer],[data-edge-terminal],[data-alignment-guide-layer],[data-selection-overlay-layer],[data-edge-selection-halo],.node-selection,.boundary-selection,[data-boundary-resize],[data-node-resize],[data-node-port],[data-edge-hit],[data-connection-preview],[data-boundary-arranges]')
      .forEach(element => element.remove());
    const colors = canvasPalette();
    copy.querySelectorAll('[data-legend-strip]').forEach(strip => strip.remove());
    copy.querySelectorAll('[data-export-background],[data-export-title]').forEach(element => element.remove());
    copy.querySelectorAll('[data-graph-edge]').forEach(element => {
      const edge = edgeById(element.dataset.edgeId);
      if (!edge) return;
      element.setAttribute('stroke', edgeThemeStroke(edge) || colors.wire);
      element.setAttribute('stroke-width', String(Number(edge.style?.width) || edge.width || 1.4));
      const direction = edgeDirection(edge);
      const marker = `url(#infragram-editor-arrow${EDGE_ARROWS[edgeArrow(edge)]})`;
      if (direction === 'none') element.removeAttribute('marker-end');
      else element.setAttribute('marker-end', marker);
      if (direction === 'both') element.setAttribute('marker-start', marker);
      else element.removeAttribute('marker-start');
    });
    // The chip keeps its thin border; a selected wire's accent is the page's, not the picture's.
    // comment markers are the page's, never the picture's (35-comments)
    copy.querySelectorAll('[data-comment-marker-layer]').forEach(element => element.remove());
    copy.querySelectorAll('[data-edge-label] .edge-label-mask').forEach(element => {
      element.setAttribute('stroke', element.dataset.chipStroke || 'transparent');
    });
    // a flow or a lens shown on the page is the reader's, not the picture's
    copy.querySelectorAll('[data-cost-heat]').forEach(element => element.remove());
    copy.querySelectorAll('[data-focus-edge="true"]').forEach(element => element.setAttribute('data-focus-edge', 'false'));
    copy.querySelectorAll('[data-selected],[data-focus-dimmed],[data-search-match],[data-search-dimmed],[data-drop-target]').forEach(element => {
      ['data-selected', 'data-focus-dimmed', 'data-search-match', 'data-search-dimmed', 'data-drop-target']
        .forEach(attribute => element.removeAttribute(attribute));
    });
    // The provider mark keeps a band of its own below the drawing: left-aligned
    // with the content, one gap beneath frames, cards, wires and captions; the
    // picture grows to hold it. Nothing is ever drawn over it.
    const mark = copy.querySelector('[data-brand-mark]');
    if (mark && darkCanvas()) mark.setAttribute('color', colors.text);
    const drawn = drawnBounds();
    if (mark && drawn) {
      const height = Number(mark.getAttribute('height')) || MARK.height;
      mark.setAttribute('x', String(drawn.left));
      mark.setAttribute('y', String(drawn.bottom + MARK.gap));
      const view = copy.viewBox && copy.viewBox.baseVal;
      if (view && view.width && view.height) {
        const needed = drawn.bottom + MARK.gap + height + MARK.gap - view.y;
        if (needed > view.height) {
          copy.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${needed}`);
          copy.setAttribute('height', String(needed));
        }
      }
    }
    let footerBottom = Math.max(drawn?.bottom || 0,
      mark ? Number(mark.getAttribute('y')) + Number(mark.getAttribute('height') || MARK.height) : 0);
    // Footer annotations follow every drawn overlay, including a tall step list.
    diagram.querySelectorAll('[data-step-list],[data-status-block]').forEach(element => {
      if (!element.getBoundingClientRect().height) return;
      const box = element.getBBox();
      const transform = diagram.getCTM().inverse().multiply(element.getCTM());
      const point = new DOMPoint(box.x + box.width, box.y + box.height);
      footerBottom = Math.max(footerBottom, (transform ? point.matrixTransform(transform) : point).y);
    });
    if (state.canvas.titlePlacement === 'caption') {
      const lines = legendLayout([{label: originalProject.title}], 640).rows[0]?.lines || [];
      const x = drawn?.left || 0, y = footerBottom + MARK.gap;
      copy.insertAdjacentHTML('beforeend', '<g data-export-title="">'
        + lines.map((line, index) => `<text x="${x}" y="${y + 18 + index * 20}" fill="${escapeText(colors.text)}" font-family="Inter,sans-serif" font-size="16" font-weight="500">${escapeText(line)}</text>`).join('') + '</g>');
      footerBottom = y + lines.length * 20;
    }
    if (includeLegend) {
      const entries = legendEntries();
      if (entries.length) {
        const layout = legendLayout(entries);
        const x = Math.max(0, drawn?.left || 0);
        const y = footerBottom + MARK.gap;
        copy.insertAdjacentHTML('beforeend', legendSvg(layout, x, y));
        const view = copy.viewBox.baseVal;
        const width = Math.max(view.width, x + layout.width + MARK.gap - view.x);
        const height = Math.max(view.height, y + layout.height + MARK.gap - view.y);
        copy.setAttribute('viewBox', `${view.x} ${view.y} ${width} ${height}`);
        copy.setAttribute('width', String(width));
        copy.setAttribute('height', String(height));
      }
    }
    copy.style.width = '';
    copy.style.height = '';
    cropExportSvg(copy);
    // An SVG loaded as an image cannot borrow the editor's fonts. Carry the
    // inline faces for its named families, without pulling in unrelated UI CSS.
    const families = [...copy.querySelectorAll('[font-family]')]
      .flatMap(element => element.getAttribute('font-family').split(','))
      .map(family => family.trim().replace(/['"]/g, '').toLowerCase());
    const faces = [...document.querySelectorAll('style')].flatMap(style =>
      style.textContent.match(/@font-face\s*\{[^}]*\}/g) || []).filter(rule => {
        const family = rule.match(/font-family\s*:\s*['"]?([^;'"}]+)/i)?.[1]?.trim().toLowerCase();
        return family && families.includes(family);
      });
    if (faces.length) {
      const style = document.createElementNS(SVG_NS, 'style');
      style.textContent = [...new Set(faces)].join('');
      copy.querySelector('defs').appendChild(style);
    }
    const surface = background ?? (getComputedStyle(diagram).getPropertyValue('--diagram-surface').trim() || '#ffffff');
    if (surface !== 'transparent' && surface !== 'none') {
      const ground = document.createElementNS(SVG_NS, 'rect');
      const view = copy.viewBox.baseVal;
      Object.entries({'data-export-background': '', x: view.x, y: view.y,
        width: view.width, height: view.height, fill: surface}).forEach(([name, value]) => ground.setAttribute(name, String(value)));
      copy.insertBefore(ground, [...copy.children].find(element => !['title', 'desc', 'defs', 'style', 'metadata'].includes(element.localName)) || null);
    }
    // Serialised as HTML, which never writes the xlink namespace down. An
    // icon whose artwork says xlink:href then leaves an export that is not
    // XML: it does not open as a file, and the exporter, which parses it
    // before capturing, falls back to the automatic layout.
    if (/\sxlink:[a-z]/i.test(copy.innerHTML)) {
      copy.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
    }
    return `<?xml version="1.0" encoding="UTF-8"?>\n${copy.outerHTML}`;
  };
  const download = (name, type, content) => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([content], {type}));
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  };
  // Keep the whole drawing when a large canvas needs a smaller bitmap.
  // Both limits avoid browser canvas allocation failures without cropping.
  const PNG_MAX_SIDE = 8192;
  const PNG_MAX_PIXELS = 16 * 1024 * 1024;
  const exportPng = async (options = {}) => {
    await document.fonts.ready;
    const background = getComputedStyle(diagram).getPropertyValue('--diagram-surface').trim() || '#ffffff';
    const svg = new DOMParser().parseFromString(exportSvg(options), 'image/svg+xml');
    if (svg.querySelector('parsererror')) throw new Error('The diagram SVG could not be read');
    const picture = svg.documentElement;
    const [, , width, height] = picture.getAttribute('viewBox').trim().split(/[\s,]+/).map(Number);
    if (!(width > 0 && height > 0 && Number.isFinite(width) && Number.isFinite(height))) {
      throw new Error('The diagram dimensions are invalid');
    }
    const requestedScale = Number(options.scale ?? state.canvas.pngScale ?? 2);
    if (!Number.isFinite(requestedScale) || requestedScale < 1 || requestedScale > 4) {
      throw new Error('PNG resolution must be between 1× and 4×');
    }
    const scale = Math.min(requestedScale, PNG_MAX_SIDE / width, PNG_MAX_SIDE / height,
      Math.sqrt(PNG_MAX_PIXELS / width / height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.floor(width * scale));
    canvas.height = Math.max(1, Math.floor(height * scale));
    if (scale < requestedScale) setStatus(`PNG: ${canvas.width} × ${canvas.height} px (${scale.toFixed(2)}×; image size limit)`);
    picture.setAttribute('width', String(canvas.width));
    picture.setAttribute('height', String(canvas.height));
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)], {type: 'image/svg+xml'}));
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const context = canvas.getContext('2d');
      if (!context) throw new Error('The browser could not create the PNG canvas');
      context.fillStyle = background;
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      return await new Promise((resolve, reject) => canvas.toBlob(blob => {
        if (blob) resolve(blob);
        else reject(new Error('The browser could not encode this PNG'));
      }, 'image/png'));
    } finally {
      URL.revokeObjectURL(url);
    }
  };
  // Editable draw.io cells use the current geometry, not the original project.
  // XML attributes are written through the DOM so names and labels stay data.
  const exportDrawio = ({includeLegend = legendEnabled('exportLegend')} = {}) => {
    if (drillPath.length) return wholeDrawing(() => exportDrawio({includeLegend}));
    const xml = document.implementation.createDocument('', 'mxfile');
    const append = (parent, tag, attrs = {}) => {
      const element = xml.createElement(tag);
      Object.entries(attrs).forEach(([name, value]) => element.setAttribute(name, String(value)));
      parent.appendChild(element);
      return element;
    };
    xml.documentElement.setAttribute('host', 'infragram');
    const drawn = drawnBounds();
    const key = includeLegend ? legendLayout(legendEntries()) : null;
    const pictureWidth = Math.ceil(Math.max(drawn ? drawn.right - drawn.left : 320, key?.width || 0) + 64);
    const pictureHeight = Math.ceil((drawn ? drawn.bottom - drawn.top : 180) + (key?.rows.length ? key.height + MARK.gap : 0) + 64);
    const sheet = append(xml.documentElement, 'diagram', {id: originalProject.slug,
      name: exportProject().title, infragram_crossings: crossingStyle()});
    const model = append(sheet, 'mxGraphModel', {dx: pictureWidth, dy: pictureHeight,
      grid: 1, gridSize: state.canvas.grid, page: 0, pageScale: 1, connect: 1, arrows: 1,
      background: getComputedStyle(diagram).getPropertyValue('--diagram-surface').trim() || '#ffffff'});
    const root = append(model, 'root');
    append(root, 'mxCell', {id: '0'});
    append(root, 'mxCell', {id: '1', parent: '0'});
    const colors = canvasPalette();
    let annotationBottom = drawn?.bottom || 0;
    if (state.canvas.titlePlacement === 'caption') {
      const lines = legendLayout([{label: originalProject.title}], 640).rows[0]?.lines || [];
      const caption = append(root, 'mxCell', {id: 'infragram:title', value: lines.join('\n'),
        infragram_role: 'caption', vertex: 1, parent: '1',
        style: `text;html=0;whiteSpace=wrap;align=left;verticalAlign=top;fontSize=16;fontFamily=Inter;fontColor=${colors.text};strokeColor=none;fillColor=none;`});
      append(caption, 'mxGeometry', {x: drawn?.left || 0, y: annotationBottom + MARK.gap,
        width: 640, height: lines.length * 20, as: 'geometry'});
      annotationBottom += MARK.gap + lines.length * 20;
      model.setAttribute('dy', String(pictureHeight + MARK.gap + lines.length * 20));
    }
    const ids = new Map();
    const boxes = new Map();
    const parents = new Map();
    const frames = new Map(state.boundaries.filter(boundaryIsVisible).map(frame => [frame.id, frame]));
    const parentFor = id => frames.has(id) ? `frame:${id}` : '1';
    // The first of these that is a colour (verification.SAFE_COLOUR): a
    // stored style came from a shared file, and draw.io reads ';' and '='
    // in a style string as more keys.
    const SAFE_PAINT = /^(?:#[0-9a-fA-F]{3,8}|[A-Za-z]{3,24}|(?:rgb|rgba|hsl|hsla)\([0-9.,\s%]+\))$/;
    const paintOf = (...values) => values.find(value => typeof value === 'string' && SAFE_PAINT.test(value)) || 'none';
    const styleWord = value => String(value).replace(/[;=]/g, '');
    const originFor = parent => {
      const frame = frames.get(parent.slice(6));
      return frame ? {x: frame.x, y: frame.y} : {x: 0, y: 0};
    };
    const label = item => `<b>${escapeText(item.name || '')}</b>`
      + (item.detail ? `<br>${escapeText(item.detail).split('\n').join('<br>')}` : '')
      + (isPanel(item) ? panelRows(item).map(row => '<hr>' + row.map(cell => {
        const tone = toneOf(cell.tone);
        const words = [cell.title ? `<b>${escapeText(cell.title)}</b>` : '', ...cellLines(cell).map(escapeText)]
          .filter(Boolean).join('<br>');
        return tone ? `<span style="background-color:${tone[0]}">${words}</span>` : words;
      }).join(' &#124; ')).join('') : '');
    const vertex = (item, id, parent, box, style) => {
      ids.set(item.id, id);
      boxes.set(item.id, box);
      parents.set(id, parent);
      const object = append(root, 'object', {id, label: label(item), infragram_id: item.id,
        infragram_component: item.componentQualifiedId || ''});
      const cell = append(object, 'mxCell', {vertex: 1, parent, style});
      const origin = originFor(parent);
      append(cell, 'mxGeometry', {x: box.x - origin.x, y: box.y - origin.y,
        width: box.width, height: box.height, as: 'geometry'});
    };
    frames.forEach(drawn => {
      const frame = darkCanvas() && drawn.dark ? {...drawn, ...drawn.dark} : drawn;
      vertex(frame, `frame:${frame.id}`, parentFor(frame.parentId), frame,
        'html=1;whiteSpace=wrap;container=1;collapsible=0;recursiveResize=0;'
        + `verticalAlign=top;align=left;spacing=8;fontSize=${frame.labelSize || 10};`
        + `strokeColor=${paintOf(frame.style?.stroke, frame.stroke, colors.border)};`
        + `fillColor=${paintOf(frame.style?.fill, frame.fill)};fontColor=${paintOf(frame.style?.label, frame.labelColor, colors.text)};`
        + (frame.dash ? `dashed=1;dashPattern=${frame.dash.replace(/,/g, ' ')};` : ''));
    });
    // a panel's shape, as draw.io names it (builders/panels.py)
    const PANEL_DRAWIO = {ellipse: 'ellipse;', hexagon: 'shape=hexagon;perimeter=hexagonPerimeter2;size=0.1;',
      note: 'shape=note;size=10;', rect: 'rounded=1;arcSize=4;'};
    state.nodes.filter(nodeIsVisible).forEach(node => {
      const panel = isPanel(node);
      const icon = node.displayMode === 'icon' && !panel;
      const square = icon ? glyphSquare(node) : null;
      const box = square ? {x: square.x, y: square.y, width: square.size, height: square.size} : node;
      let art = node.iconUri?.replace(/;base64,/, ',');
      if (node.iconUri && inkFilter(node.iconUri)) {
        const wrapped = `<svg xmlns="${SVG_NS}" viewBox="0 0 64 64"><defs>${INK_ON_DARK_FILTER}</defs>`
          + `<image href="${escapeText(node.iconUri)}" width="64" height="64" filter="url(#${INK_ON_DARK})"/></svg>`;
        art = 'data:image/svg+xml,' + btoa(Array.from(new TextEncoder().encode(wrapped),
          byte => String.fromCharCode(byte)).join(''));
      }
      const text = withCurrentFace(node.textStyle || {});
      if (panel) {
        const tone = toneOf(node.attributes?.tone);
        vertex(node, `node:${node.id}`, parentFor(node.boundaryId), box,
          `html=1;whiteSpace=wrap;verticalAlign=top;spacingTop=6;${PANEL_DRAWIO[panelShape(node)]}`
          + `fillColor=${paintOf(node.style?.fill, tone?.[0], colors.card)};strokeColor=${paintOf(node.style?.stroke, tone?.[1], colors.border)};`
          + `fontColor=${colors.text};fontSize=11;fontFamily=Inter;`);
        return;
      }
      vertex(node, `node:${node.id}`, parentFor(node.boundaryId), box,
        'html=1;whiteSpace=wrap;'
        + (art ? `${icon ? 'shape=image;imageAspect=1;aspect=fixed;' : 'shape=label;imageWidth=32;imageHeight=32;imageAlign=left;spacingLeft=48;'}image=${art};` : 'shape=rect;')
        + (icon ? `verticalLabelPosition=bottom;verticalAlign=top;labelWidth=${node.width};fillColor=none;strokeColor=none;`
          : `rounded=1;fillColor=${paintOf(node.style?.fill, colors.card)};strokeColor=${paintOf(node.style?.stroke, colors.border)};`)
        + `fontColor=${paintOf(text.textColor, colors.text)};fontSize=${Number(text.fontSize) || 12};fontFamily=${styleWord(text.fontFamily || 'Inter')};`
        + `fontStyle=${Number(text.fontWeight || 600) >= 600 ? 1 : 0};rotation=${Number(node.angle) || 0};`
        + `flipH=${node.flipX ? 1 : 0};flipV=${node.flipY ? 1 : 0};`);
    });
    const ancestors = id => {
      const chain = ['1'];
      let parent = parents.get(id);
      const seen = new Set();
      while (parent && parent !== '1' && !seen.has(parent)) {
        seen.add(parent);
        chain.splice(1, 0, parent);
        parent = parents.get(parent);
      }
      return chain;
    };
    const wires = edgeGeometry();
    refreshRouteContext();
    wires.forEach(item => connectorPath(item));
    wires.forEach(item => connectorPath(item));
    spreadLanes(wires);
    wires.forEach(item => {
      const edge = item.edge;
      if (!ids.has(edge.source) || !ids.has(edge.target)) return;
      const corners = captionCorners(item);
      if (corners.length < 2) return;
      const source = ids.get(edge.source), target = ids.get(edge.target);
      const a = ancestors(source), b = ancestors(target);
      const parent = a.filter((id, index) => id === b[index]).at(-1) || '1';
      const origin = originFor(parent);
      const pin = (id, point, prefix) => {
        const box = boxes.get(id);
        // Offsets allow a seated endpoint outside the icon square (a caption,
        // for example), while disabling draw.io's own perimeter adjustment.
        const x = Math.max(0, Math.min(1, (point.x - box.x) / box.width));
        const y = Math.max(0, Math.min(1, (point.y - box.y) / box.height));
        return `${prefix}X=${x};${prefix}Y=${y};${prefix}Dx=${point.x - box.x - x * box.width};`
          + `${prefix}Dy=${point.y - box.y - y * box.height};${prefix}Perimeter=0;`;
      };
      const direction = edgeDirection(edge);
      const dash = edgeDash(edge);
      const text = edgeTextStyle(edge);
      const arrow = {triangle: 'block', open: 'open', circle: 'oval', diamond: 'diamond'}[edgeArrow(edge)];
      const style = `edgeStyle=none;rounded=${cornerRadius(edge) > 0 ? 1 : 0};html=1;`
        + (crossingStyle() === 'bridge' ? `jumpStyle=arc;jumpSize=${METRICS.router.crossing_radius * 2};` : 'jumpStyle=none;')
        + pin(edge.source, corners[0], 'exit') + pin(edge.target, corners.at(-1), 'entry')
        // a wire's stored colours and face pass the same checks as a card's,
        // so a stored value can never add a style key of its own
        + `strokeColor=${paintOf(edgeThemeStroke(edge), colors.wire)};strokeWidth=${Number(edge.style?.width) || edge.width || 1.4};`
        + `endArrow=${direction === 'none' ? 'none' : arrow};startArrow=${direction === 'both' ? arrow : 'none'};`
        + `fontColor=${paintOf(text.textColor, colors.text)};fontSize=${Number(text.fontSize) || 12};`
        + `fontFamily=${styleWord(text.fontFamily || 'Inter')};textOpacity=${Number.isFinite(Number(text.opacity)) ? Number(text.opacity) : 100};`
        + (dash ? `dashed=1;dashPattern=${styleWord(dash).replace(/,/g, ' ')};` : '');
      const cell = append(root, 'mxCell', {id: `wire:${edge.id}`, value: escapeText(edge.label || ''),
        edge: 1, parent, source, target, style});
      const geometry = append(cell, 'mxGeometry', {relative: 1, as: 'geometry'});
      if (edge.label) {
        const placed = resolvedEdgeLabel(item), midpoint = alongPolyline(corners, 0.5);
        append(geometry, 'mxPoint', {x: placed.x - midpoint.x, y: placed.y - midpoint.y, as: 'offset'});
      }
      const points = append(geometry, 'Array', {as: 'points'});
      corners.slice(1, -1).forEach(point => append(points, 'mxPoint', {x: point.x - origin.x, y: point.y - origin.y}));
    });
    if (includeLegend) {
      const entries = legendEntries();
      if (entries.length) {
        const layout = legendLayout(entries), bounds = drawnBounds();
        const legend = append(root, 'mxCell', {id: 'infragram:legend', value: 'Legend', infragram_role: 'legend', vertex: 1, parent: '1',
          style: `swimlane;html=0;startSize=30;container=1;collapsible=0;recursiveResize=0;rounded=1;horizontal=1;align=left;spacingLeft=16;fontSize=13;fontStyle=1;fillColor=${colors.canvas};strokeColor=${colors.border};fontColor=${colors.text};`});
        append(legend, 'mxGeometry', {x: Math.max(0, bounds?.left || 0), y: annotationBottom + MARK.gap,
          width: layout.width, height: layout.height, as: 'geometry'});
        layout.rows.forEach((entry, index) => {
          const arrow = {triangle: 'block', open: 'open', circle: 'oval', diamond: 'diamond'}[entry.arrow];
          const sample = append(root, 'mxCell', {id: `infragram:legend:symbol:${index}`, [entry.type === 'frame' ? 'vertex' : 'edge']: 1, parent: 'infragram:legend',
            style: (entry.type === 'frame' ? 'shape=rect;rounded=1;fillColor=none;' : `edgeStyle=none;endArrow=${entry.direction === 'none' ? 'none' : arrow};startArrow=${entry.direction === 'both' ? arrow : 'none'};`)
              + `strokeColor=${entry.stroke};strokeWidth=1.5;` + (entry.dash ? `dashed=1;dashPattern=${entry.dash.replace(/,/g, ' ')};` : '')});
          const geometry = append(sample, 'mxGeometry', entry.type === 'frame'
            ? {x: entry.x, y: entry.y - 6, width: 32, height: 14, as: 'geometry'}
            : {relative: 1, as: 'geometry'});
          if (entry.type !== 'frame') {
            append(geometry, 'mxPoint', {x: entry.x, y: entry.y + 2, as: 'sourcePoint'});
            append(geometry, 'mxPoint', {x: entry.x + 32, y: entry.y + 2, as: 'targetPoint'});
          }
          const label = append(root, 'mxCell', {id: `infragram:legend:label:${index}`, value: entry.lines.join('\n'), vertex: 1, parent: 'infragram:legend',
            style: `text;html=0;whiteSpace=wrap;align=left;verticalAlign=top;spacing=0;fontSize=12;fontColor=${colors.text};strokeColor=none;fillColor=none;`});
          append(label, 'mxGeometry', {x: entry.x + 44, y: entry.y - 7, width: layout.width / (layout.width >= 560 ? 2 : 1) - 72,
            height: entry.lines.length * 16, as: 'geometry'});
        });
      }
    }
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(xml);
  };
  const exportHtml = () => {
    // a page is saved whole, whatever frame is open (34-drill-down)
    if (drillPath.length) return wholeDrawing(() => exportHtml());
    const copy = document.documentElement.cloneNode(true);
    // Comments written here are this browser's until they are downloaded:
    // a saved page carries only those it was exported with, in their script
    // (35-comments), never this reader's list, markers or count.
    copy.querySelector('[data-comments-list]')?.replaceChildren();
    copy.querySelector('[data-comments-panel]')?.setAttribute('hidden', '');
    copy.querySelector('[data-comments-count]')?.replaceChildren();
    copy.querySelectorAll('[data-comment-marker-layer],[data-drill-stub-layer]').forEach(element => element.remove());
    const copiedPath = copy.querySelector('[data-drill-path]');
    if (copiedPath) {
      copiedPath.replaceChildren();
      copiedPath.setAttribute('hidden', '');
    }
    // The page the editor saves carries its state in <script> blocks.
    // HTML looks for an end tag or a comment opener there without regard
    // to case, so the three characters that can start one are escaped;
    // a JSON parser decodes them straight back, so nothing is lost.
    const safeJson = value => JSON.stringify(value).replace(/[<>&]/g,
      character => '\\u00' + character.charCodeAt(0).toString(16).padStart(2, '0'));
    copy.querySelector('body').classList.remove('sidebar-preview');
    // What belongs to this session stays out of the saved page: the review of
    // its selection, a snackbar still reporting its last action (nothing in
    // the saved page would ever hide it), and the hint it already dismissed.
    copy.querySelector('[data-frame-review]')?.setAttribute('hidden', '');
    copy.querySelector('[data-save-notice]')?.setAttribute('hidden', '');
    const copiedSnackbar = copy.querySelector('[data-snackbar]');
    if (copiedSnackbar) {
      copiedSnackbar.setAttribute('hidden', '');
      copiedSnackbar.removeAttribute('style');
      copiedSnackbar.textContent = '';
    }
    copy.querySelector('[data-editor-help]')?.classList.remove('canvas-help--retired');
    const copiedTrigger = copy.querySelector('[data-sidebar-logo-trigger]');
    if (copiedTrigger && copy.querySelector('body').classList.contains('sidebar-collapsed')) {
      copiedTrigger.setAttribute('aria-expanded', 'false');
    }
    copy.querySelector('#infragram-project').textContent = safeJson(exportProject());
    copy.querySelector('#infragram-editor-state').textContent = safeJson(state);
    // A page saved after an edit still carries the Terraform written before
    // it, so it is marked, and says so when its Terraform is downloaded.
    if (terraformIsStale()) copy.querySelector('#infragram-terraform')?.setAttribute('data-stale', '');
    return `<!DOCTYPE html>\n${copy.outerHTML}\n`;
  };

  sidebarLogoTrigger.addEventListener('pointerenter', previewSidebar);
  sidebarLogoTrigger.addEventListener('focus', previewSidebar);
  sidebarLogoTrigger.addEventListener('click', toggleSidebarPinned);
  sidebar.addEventListener('pointerleave', closeSidebarPreview);
  sidebar.addEventListener('focusout', event => {
    if (!sidebar.contains(event.relatedTarget)) closeSidebarPreview();
  });
  sidebar.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !providerMenu.hidden) {
      providerMenu.hidden = true;
      providerMenuTrigger.setAttribute('aria-expanded', 'false');
      syncProviderControls(providerSelection);
      providerMenuTrigger.focus();
    } else if (event.key === 'Escape' && document.body.classList.contains('sidebar-preview')) {
      closeSidebarPreview();
      sidebarLogoTrigger.blur();
    }
  });
  document.querySelector('[data-download-template]').addEventListener('click', () => download(
    `${originalProject.slug}.infragram.json`, 'application/json', `${JSON.stringify(exportProject(), null, 2)}\n`,
  ));
  document.querySelector('[data-download-html]').addEventListener('click', () => download(
    `${originalProject.slug}.html`, 'text/html', exportHtml(),
  ));
  document.querySelector('[data-download-svg]').addEventListener('click', () => download(
    `${originalProject.slug}.svg`, 'image/svg+xml', exportSvg(),
  ));
  document.querySelector('[data-download-drawio]')?.addEventListener('click', () => download(
    `${originalProject.slug}.drawio`, 'application/xml', exportDrawio(),
  ));
  document.querySelector('[data-download-png]')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      download(`${originalProject.slug}.png`, 'image/png', await exportPng());
    } catch (error) {
      setStatus(`PNG download failed: ${error.message}`);
    } finally {
      button.disabled = false;
    }
  });
  document.querySelector('[data-save-download]')?.addEventListener('click', () => download(
    `${originalProject.slug}.html`, 'text/html', exportHtml(),
  ));
  // The diagram's Terraform rides in the page, in each style, as the export
  // wrote it from this document (editor/shell.py): the page cannot write
  // Terraform itself. Each Terraform item downloads one folder as a .zip.
  const terraformElement = document.querySelector('#infragram-terraform');
  // What the Terraform is written from: every element with its frame, name,
  // kind, component and attributes, and every wire with its label and
  // direction -- not where anything is drawn. A diagram whose facts differ
  // from the exported document's has been edited since.
  const terraformFacts = project => {
    const facts = [];
    const visit = (element, parent) => (element?.children || []).forEach(child => {
      const attributes = Object.entries(child.attributes || {})
        .filter(([key, value]) => !key.startsWith('editor_') && !['icon', 'category'].includes(key)
          && value !== null && value !== undefined && value !== '')
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
      const wires = (child.connections || [])
        .map(wire => JSON.stringify([wire.target, wire.kind || 'solid', wire.label || '', wire.direction || 'forward']))
        .sort();
      facts.push(JSON.stringify([child.id, parent, child.name || '', child.type || '',
        child.component?.provider || '', child.component?.service_id || '', attributes, wires]));
      visit(child, child.id);
    });
    visit(project.topology, '');
    return JSON.stringify([project.title || '', facts.sort()]);
  };
  const terraformIsStale = () => Boolean(terraformElement?.hasAttribute('data-stale'))
    || terraformFacts(exportProject()) !== terraformFacts(originalProject);
  // A stored .zip: every unzip tool opens one, and the files are a few
  // kilobytes of text. Each entry sits in the folder, its name in UTF-8.
  const CRC_TABLE = Uint32Array.from({length: 256}, (_, index) => {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) value = value & 1 ? 0xEDB88320 ^ (value >>> 1) : value >>> 1;
    return value >>> 0;
  });
  const crc32 = bytes => {
    let crc = 0xFFFFFFFF;
    for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >>> 8);
    return (crc ^ 0xFFFFFFFF) >>> 0;
  };
  const zipFolder = (folder, files) => {
    const encoder = new TextEncoder();
    const now = new Date();
    const time = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
    const date = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
    // One record's little-endian fields, in order, as [bytes, value].
    const record = fields => {
      const view = new DataView(new ArrayBuffer(fields.reduce((sum, [bytes]) => sum + bytes, 0)));
      let at = 0;
      fields.forEach(([bytes, value]) => {
        if (bytes === 4) view.setUint32(at, value, true);
        else view.setUint16(at, value, true);
        at += bytes;
      });
      return view;
    };
    const entries = [];
    const directory = [];
    let offset = 0;
    const paths = Object.keys(files).sort();
    paths.forEach(path => {
      const name = encoder.encode(`${folder}/${path}`);
      const data = encoder.encode(files[path]);
      // version 2.0, UTF-8 name, stored; time, date, CRC, both sizes, name length
      const common = [[2, 20], [2, 0x0800], [2, 0], [2, time], [2, date], [4, crc32(data)],
        [4, data.length], [4, data.length], [2, name.length]];
      entries.push(record([[4, 0x04034b50], ...common, [2, 0]]), name, data);
      directory.push(record([[4, 0x02014b50], [2, 20], ...common,
        [2, 0], [2, 0], [2, 0], [2, 0], [4, 0], [4, offset]]), name);
      offset += 30 + name.length + data.length;
    });
    const size = directory.reduce((sum, part) => sum + part.byteLength, 0);
    const end = record([[4, 0x06054b50], [2, 0], [2, 0], [2, paths.length], [2, paths.length],
      [4, size], [4, offset], [2, 0]]);
    return new Blob([...entries, ...directory, end], {type: 'application/zip'});
  };
  document.querySelectorAll('[data-download-terraform]').forEach(item => item.addEventListener('click', async () => {
    let folder;
    try {
      folder = terraformElement ? (await readEmbeddedJson(terraformElement))[item.dataset.downloadTerraform] : null;
    } catch (error) {
      setStatus(`The page's Terraform could not be read: ${error.message}`);
      return;
    }
    if (!folder) return;
    download(`${folder.folder}.zip`, 'application/zip', zipFolder(folder.folder, folder.files));
    if (terraformIsStale()) {
      setStatus(`${folder.folder}.zip is the diagram as it was exported, without your edits: `
        + 'download the template and export it again to include them');
    }
  }));
  // The download menu is a <details>. It closes when an item is chosen --
  // before the item's own handler runs, so a saved page never keeps it
  // open -- on a press anywhere else, and on Escape.
  const downloadMenu = document.querySelector('[data-download-menu]');
  if (downloadMenu) {
    downloadMenu.addEventListener('click', event => {
      if (event.target.closest('[data-download-action]')) downloadMenu.open = false;
    }, true);
    document.addEventListener('pointerdown', event => {
      if (downloadMenu.open && !downloadMenu.contains(event.target)) downloadMenu.open = false;
    });
    downloadMenu.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || !downloadMenu.open) return;
      event.preventDefault();
      event.stopPropagation();
      downloadMenu.open = false;
      downloadMenu.querySelector('summary').focus();
    });
  }
