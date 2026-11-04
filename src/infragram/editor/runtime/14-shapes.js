// @module 14-shapes: frame, card and connector markup and connector label placement
  // Corner badges: what applies to a frame (a subnet's NSG, its route
  // table), the way Azure's reference diagrams seat an NSG on its subnet.
  // The first icon sits on the frame's top-right corner point, the rest on
  // the top border leftwards from it; each name sits just under the top
  // border, immediately left of its icon. Nothing is painted behind them:
  // the icon hides the line itself. The static renderer draws the same
  // geometry (CORNER_BADGE and corner_layout in builders/scene.py); change
  // both together.
  const CORNER_BADGE = {icon: 20, font: 9, advance: 0.6, gap: 3, spacing: 12, drop: 1.5};
  const cornerCaptionWidth = label => Math.round(String(label || '').length * CORNER_BADGE.font * CORNER_BADGE.advance);
  const cornerLayout = (right, labels) => {
    const c = CORNER_BADGE;
    let edge = right + c.icon / 2;
    return labels.map(label => {
      const iconX = edge - c.icon / 2;
      const textEnd = iconX - c.icon / 2 - c.gap;
      edge = textEnd - cornerCaptionWidth(label) - c.spacing;
      return {iconX, textEnd};
    });
  };
  const cornerRowWidth = labels => {
    if (!labels.length) return 0;
    const c = CORNER_BADGE;
    let reach = c.icon / 2 + c.gap + cornerCaptionWidth(labels[0]);
    labels.slice(1).forEach(label => { reach += c.spacing + c.icon + c.gap + cornerCaptionWidth(label); });
    return Math.round(reach);
  };
  // Azure NAT gateways retain the border bar used by imported subnets.
  const EDGE_BADGE = {icon: 20, bar: 3, gap: 3, spacing: 16, color: '#50c8e8'};
  const edgeRowWidth = labels => labels.length
    ? Math.round(labels.reduce((sum, label) => sum + EDGE_BADGE.icon + EDGE_BADGE.gap + cornerCaptionWidth(label), 0)
      + EDGE_BADGE.spacing * (labels.length - 1)) : 0;
  const edgeBadgesMarkup = (boundary, colors) => {
    const badges = (boundary.badges || []).filter(badge => badge.side === 'edge' && badge.iconUri);
    if (!badges.length) return '';
    const c = EDGE_BADGE;
    const x = Number(boundary.x) || 0, y = Number(boundary.y) || 0;
    const width = Number(boundary.width) || 0;
    const spans = badges.map(badge => c.icon + c.gap + cornerCaptionWidth(badge.label));
    const total = spans.reduce((sum, span) => sum + span, 0) + c.spacing * (spans.length - 1);
    let cursor = x + (width - total) / 2;
    const marks = badges.map((badge, index) => {
      const iconX = cursor + c.icon / 2, textX = cursor + c.icon + c.gap;
      cursor += spans[index] + c.spacing;
      const label = String(badge.label || '');
      const caption = label
        ? `<text data-frame-badge-label x="${textX}" y="${y + CORNER_BADGE.font + CORNER_BADGE.drop + c.bar}" font-family="'Inter',sans-serif" font-size="${CORNER_BADGE.font}" font-weight="600" fill="${escapeText(colors.text)}" pointer-events="none">${escapeText(label)}</text>` : '';
      return `<image data-frame-badge data-boundary-badge="${escapeText(label || badge.icon || '')}" href="${escapeText(badge.iconUri)}" x="${iconX - c.icon / 2}" y="${y - c.icon / 2}" width="${c.icon}" height="${c.icon}" preserveAspectRatio="xMidYMid meet" aria-hidden="true" pointer-events="none"/>${caption}`;
    }).join('');
    return `<rect data-boundary-edge-bar x="${x}" y="${y}" width="${width}" height="${c.bar}" fill="${c.color}" pointer-events="none"/>${marks}`;
  };
  const borderBadgeAnchor = (boundary, badge) => {
    const x = Number(boundary.x) || 0, y = Number(boundary.y) || 0;
    const width = Number(boundary.width) || 0, height = Number(boundary.height) || 0;
    const offset = Math.max(0, Math.min(1, Number(badge.offset ?? 0.5)));
    if (badge.side === 'top' || badge.side === 'bottom') {
      let cx = x + width * offset;
      if (badge.side === 'top') {
        const title = boundaryLabelBox(boundary);
        cx = Math.min(Math.max(cx, title.x + title.width + 9), x + width - 9);
      }
      return {x: cx, y: badge.side === 'top' ? y : y + height};
    }
    return {x: badge.side === 'left' ? x : x + width, y: y + height * offset};
  };
  const borderBadgesMarkup = boundary => (boundary.badges || [])
    .filter(badge => !['corner', 'edge'].includes(badge.side) && badge.iconUri)
    .map(badge => {
      const anchor = borderBadgeAnchor(boundary, badge);
      return `<image data-frame-badge href="${escapeText(badge.iconUri)}" x="${anchor.x - 9}" y="${anchor.y - 9}" width="18" height="18" preserveAspectRatio="xMidYMid meet" pointer-events="none" aria-hidden="true"/>`;
    }).join('');
  // The box the corner badges occupy, which wires and captions keep out of
  // as they keep out of the title. Mirrors cluster_badge_rect in
  // builders/render.py.
  const boundaryBadgeBox = boundary => {
    const badges = (boundary.badges || []).filter(badge => badge.iconUri);
    if (!badges.length) return null;
    const c = CORNER_BADGE, boxes = [];
    const x = Number(boundary.x) || 0, y = Number(boundary.y) || 0;
    const width = Number(boundary.width) || 0;
    const corners = badges.filter(badge => badge.side === 'corner');
    const edges = badges.filter(badge => badge.side === 'edge');
    if (corners.length) {
      const right = x + width, reach = cornerRowWidth(corners.map(badge => String(badge.label || '')));
      boxes.push({x: right - reach, y: y - c.icon / 2,
        width: reach + c.icon / 2, height: c.icon / 2 + c.font + c.drop + 3});
    }
    if (edges.length) {
      const reach = edgeRowWidth(edges.map(badge => String(badge.label || '')));
      boxes.push({x: x + (width - reach) / 2, y: y - EDGE_BADGE.icon / 2,
        width: reach, height: EDGE_BADGE.icon / 2 + c.font + c.drop + EDGE_BADGE.bar + 3});
    }
    badges.filter(badge => !['corner', 'edge'].includes(badge.side)).forEach(badge => {
      const anchor = borderBadgeAnchor(boundary, badge);
      boxes.push({x: anchor.x - 9, y: anchor.y - 9, width: 18, height: 18});
    });
    const left = Math.min(...boxes.map(box => box.x)), top = Math.min(...boxes.map(box => box.y));
    return {x: left, y: top, width: Math.max(...boxes.map(box => box.x + box.width)) - left,
      height: Math.max(...boxes.map(box => box.y + box.height)) - top};
  };
  const cornerBadgesMarkup = (boundary, colors) => {
    const badges = (boundary.badges || []).filter(badge => badge.side === 'corner' && badge.iconUri);
    const c = CORNER_BADGE;
    const top = Number(boundary.y) || 0;
    const slots = cornerLayout((Number(boundary.x) || 0) + (Number(boundary.width) || 0),
      badges.map(badge => String(badge.label || '')));
    return badges.map((badge, index) => {
      const {iconX, textEnd} = slots[index];
      const label = String(badge.label || '');
      // "Route table · rt-spoke": the type in the frame's quiet tone, the name in ink.
      const cut = label.indexOf(' · ');
      const kind = cut > 0 ? label.slice(0, cut + 3) : '';
      const name = cut > 0 ? label.slice(cut + 3) : label;
      const caption = label
        ? `<text data-frame-badge-label x="${textEnd}" y="${top + c.font + c.drop}" text-anchor="end" font-family="'Inter',sans-serif" font-size="${c.font}" font-weight="600" fill="${escapeText(colors.text)}">${kind ? `<tspan fill="${escapeText(colors.secondary)}" font-weight="500">${escapeText(kind)}</tspan>` : ''}${escapeText(name)}</text>`
        : '';
      // No group of their own: the frame's group is the one thing a reader
      // of the page (the shipped checker) takes a frame's parts from.
      return `<image data-frame-badge href="${escapeText(badge.iconUri)}" x="${iconX - c.icon / 2}" y="${top - c.icon / 2}" width="${c.icon}" height="${c.icon}" preserveAspectRatio="xMidYMid meet" pointer-events="none" aria-hidden="true"/>${caption.replace('<text ', '<text pointer-events="none" ')}`;
    }).join('');
  };
  // A frame's border as drawn: its kind's own width times the frame lines
  // the Diagram panel chose (builders/render.py weighs the picture alike).
  const frameStroke = boundary => Math.round((Number(boundary.strokeWidth) || 1)
    * (Number(FRAME_LINES[state.canvas.frameLines]) || 1) * 100) / 100;
  const boundaryMarkup = drawn => {
    const colors = canvasPalette();
    // A library's own colour can be one a dark ground swallows -- AWS's
    // cloud navy reads 1.4:1 on it. The document carries what each frame
    // looks like there, derived where the picture derives it
    // (builders/frame_style.py), so both draw the same frame.
    const boundary = darkCanvas() && drawn.dark ? {...drawn, ...drawn.dark} : drawn;
    const selectedBoundary = isBoundarySelected(boundary.id);
    const boundaryStroke = boundary.style?.stroke || boundary.stroke || colors.border;
    const boundaryFill = boundary.style?.fill || boundary.fill || 'none';
    const label = boundary.labelCase === 'upper'
      ? String(boundary.name).toLocaleUpperCase() : boundary.name;
    const labelSize = boundary.labelSize || 10;
    // Geometry from the document is read as numbers: a string here would
    // close the attribute it is interpolated into.
    const tab = Number(boundary.tab) || FRAME.tab;
    const bx = Number(boundary.x) || 0;
    const by = Number(boundary.y) || 0;
    const bw = Number(boundary.width) || 0;
    const bh = Number(boundary.height) || 0;
    const labelX = boundary.tabbed ? bx + tab + FRAME.labelGap : bx + 20;
    const labelY = boundary.tabbed
      ? boundary.y + tab / 2 + labelSize / FRAME.baselineDivisor
      : boundary.y + labelSize / FRAME.baselineDivisor;
    // The tab seats inside the border: its outer sides lie on the stroke's
    // inner edge so the border stays whole around the corner.
    const seat = frameStroke(boundary) / 2;
    const tabX = bx + seat;
    const tabY = by + seat;
    const icon = boundary.tabbed && boundary.iconUri
      ? `<rect data-boundary-tab x="${tabX}" y="${tabY}" width="${tab}" height="${tab}" fill="${escapeText(boundary.tabFill || boundaryStroke)}"/>
         <image href="${escapeText(boundary.iconUri)}" x="${tabX + FRAME.iconInset}" y="${tabY + FRAME.iconInset}" width="${tab - 2 * FRAME.iconInset}" height="${tab - 2 * FRAME.iconInset}" preserveAspectRatio="xMidYMid meet" aria-hidden="true"/>`
      : '';
    const dash = boundary.dash ? ` stroke-dasharray="${escapeText(boundary.dash)}"` : '';
    const textStyle = withCurrentFace({
      fontFamily: boundary.labelFont === 'sans' ? 'Inter' : 'Geist Mono',
      fontSize: labelSize,
      fontWeight: boundary.labelWeight ?? 500,
      textAlign: 'left',
      textColor: boundary.style?.label || boundary.labelColor || colors.secondary,
      opacity: 100,
      ...(boundary.textStyle || {}),
    });
    const anchor = textStyle.textAlign === 'center' ? 'middle'
      : textStyle.textAlign === 'right' ? 'end' : 'start';
    const textX = textStyle.textAlign === 'center' ? bx + bw / 2
      : textStyle.textAlign === 'right' ? bx + bw - 20 : labelX;
    const labelWidth = Math.min(
      Math.max(48, String(label).length * labelSize * 0.62 + 12),
      Math.max(48, boundary.width - 32),
    );
    const labelBacking = boundary.tabbed ? ''
      : `<rect class="boundary-label-backing" x="${labelX - 6}" y="${by - labelSize + 1}" width="${labelWidth}" height="${labelSize + 5}" fill="${colors.canvas}"/>`;
    const handlePoints = [
      [boundary.x - 4, boundary.y - 4], [bx + bw / 2 - 4, boundary.y - 4],
      [bx + bw - 4, boundary.y - 4], [boundary.x - 4, by + bh / 2 - 4],
      [bx + bw - 4, by + bh / 2 - 4],
      [boundary.x - 4, by + bh - 4],
      [bx + bw / 2 - 4, by + bh - 4],
      [bx + bw - 4, by + bh - 4],
    ];
    const handleDirections = ['nw', 'n', 'ne', 'w', 'e', 'sw', 's', 'se'];
    const selection = selectedBoundary
      ? `<rect class="boundary-selection" x="${bx - 3}" y="${by - 3}" width="${bw + 6}" height="${bh + 6}" rx="${(boundary.radius || 0) + 3}" fill="none" stroke="${colors.selection}" stroke-width="2" pointer-events="none"/>
         ${handlePoints.map(([x, y], index) => (touchReach(8, 32) > 8
           ? `<rect data-boundary-resize="${handleDirections[index]}" data-boundary-id="${escapeText(boundary.id)}" x="${x + 4 - touchReach(8, 32) / 2}" y="${y + 4 - touchReach(8, 32) / 2}" width="${touchReach(8, 32)}" height="${touchReach(8, 32)}" fill="transparent"/>`
           : '')
           + `<rect data-boundary-resize="${handleDirections[index]}" data-boundary-id="${escapeText(boundary.id)}" x="${x}" y="${y}" width="8" height="8" rx="1" fill="${colors.handle}" stroke="${colors.selection}" stroke-width="1.5"/>`).join('')}`
      : '';
    // a frame the flow shown by a single click does not reach steps back
    const focusDimmed = Boolean(currentFlow && !currentFlow.frames.has(boundary.id));
    // A frame with no name is a layout container: it arranges what is
    // inside it and draws nothing. The static renderer has always skipped it
    // (builders/render.py, which draws a cluster only `if cl.label`), and the
    // runtime drew a nameless box instead -- so the page and the picture of
    // the page disagreed about how many frames there were. It stays visible
    // and selectable here, because an invisible frame in an editor is one
    // nobody can delete, and the export strips it to leave what the static
    // renderer draws.
    const layoutOnly = !String(boundary.name || '').trim();
    return `<g data-graph-boundary${layoutOnly ? ' data-boundary-arranges' : ''} data-boundary-id="${escapeText(boundary.id)}" data-boundary-kind="${escapeText(boundary.kind)}" data-layer-id="${escapeText(boundary.layerId || '')}" data-locked="${itemIsLocked(boundary)}" data-selected="${selectedBoundary}" data-drop-target="${dropTargetId === boundary.id}" data-focus-dimmed="${focusDimmed}" role="group" aria-label="${escapeText(boundary.name)} boundary">
      ${boundary.highlight ? `<rect data-frame-highlight x="${bx - 6}" y="${by - 6}" width="${bw + 12}" height="${bh + 12}" rx="${(Number(boundary.radius) || 0) + 6}" fill="${colors.accent}" fill-opacity=".07" stroke="${colors.accent}" stroke-width="2.5" pointer-events="none"/>` : ''}
      <rect data-boundary-surface x="${Number(boundary.x) || 0}" y="${Number(boundary.y) || 0}" width="${Number(boundary.width) || 0}" height="${Number(boundary.height) || 0}" rx="${Number(boundary.radius) || 0}" fill="${escapeText(boundaryFill)}" stroke="${escapeText(boundaryStroke)}" stroke-width="${frameStroke(boundary)}"${dash} pointer-events="all"/>
      ${labelBacking}${icon}${edgeBadgesMarkup(boundary, colors)}${cornerBadgesMarkup(boundary, colors)}${borderBadgesMarkup(boundary)}
      <text x="${textX}" y="${labelY}" fill="${escapeText(textStyle.textColor)}" fill-opacity="${Number(textStyle.opacity) / 100}" font-family="'${escapeText(textStyle.fontFamily)}',sans-serif" font-size="${Number(textStyle.fontSize)}" font-weight="${escapeText(textStyle.fontWeight)}" letter-spacing="${escapeText(boundary.labelTracking || '0')}" text-anchor="${anchor}">${escapeText(label)}</text>
      ${selection}
    </g>`;
  };

  // How a node's group is placed. One place writes it, so a drag can move a
  // card by writing it again instead of drawing the whole diagram.
  const nodeTransform = node => {
    const rotate = Number(node.angle) ? ` rotate(${Number(node.angle)} ${node.width / 2} ${node.height / 2})` : '';
    const scaleX = node.flipX ? -1 : 1;
    const scaleY = node.flipY ? -1 : 1;
    const flip = scaleX === 1 && scaleY === 1 ? ''
      : ` translate(${node.flipX ? node.width : 0} ${node.flipY ? node.height : 0}) scale(${scaleX} ${scaleY})`;
    return `translate(${node.x} ${node.y})${rotate}${flip}`;
  };

  // A panel (builders/panels.py): a card with several detail lines,
  // compartments (attributes.sections) or a shape (attributes.shape), and a
  // tone that means something. Python sizes it; this lays its inside out by
  // the same rules from the same numbers (render-metrics.json panel), so
  // the page and the static picture draw it alike.
  const PANEL = METRICS.panel || null;
  const TONES = METRICS.tones || {};
  const PANEL_SHAPES = ['ellipse', 'hexagon', 'note'];
  const panelShape = node => (PANEL_SHAPES.includes(node.attributes?.shape) ? node.attributes.shape : 'rect');
  const panelRows = node => (Array.isArray(node.attributes?.sections)
    ? node.attributes.sections.filter(row => Array.isArray(row) && row.length) : []);
  const panelDetailLines = node => (node.detail ? String(node.detail).split('\n') : []);
  // a tone alone makes one too: the card is filled with it (panels.py active)
  // and a Box always is one: it has no artwork for a card to show
  const isPanel = node => Boolean(PANEL) && (node.type === 'box' || panelShape(node) !== 'rect'
    || panelRows(node).length > 0 || panelDetailLines(node).length > 1 || Boolean(TONES[node.attributes?.tone]));
  const toneOf = name => {
    const tone = name && TONES[name];
    if (!tone) return null;
    return darkCanvas() ? [tone.fill_dark, tone.stroke_dark] : [tone.fill, tone.stroke];
  };
  const cellLines = cell => (Array.isArray(cell.lines) ? cell.lines : cell.lines ? [cell.lines] : []).map(String);
  // per character, at the face's advance: len * (size * advance), the order
  // Python multiplies in, so a share floors to the same pixel
  const panelText = (text, size, advance = null) => String(text).length * (advance ?? size * METRICS.text.advance);
  const cellNeed = cell => Math.ceil(Math.max(panelText(cell.title || '', PANEL.cell_title_size),
    ...cellLines(cell).map(line => panelText(line, 0, PANEL.cell_advance))) + 2 * PANEL.cell_pad_x);
  const cellHeight = cell => 2 * PANEL.cell_pad_y + (cell.title ? PANEL.cell_title_line : 0)
    + cellLines(cell).length * PANEL.cell_line;
  const rowHeight = row => Math.max(...row.map(cellHeight));
  const cellWidths = (row, width) => {
    const needs = row.map(cellNeed);
    const total = needs.reduce((sum, need) => sum + need, 0);
    const shares = needs.slice(0, -1).map(need => Math.floor(need * width / total + 1e-9));
    return [...shares, width - shares.reduce((sum, share) => sum + share, 0)];
  };
  const panelBaseline = (top, line, size) => top + line / 2 + size * 0.35;
  // The size Python gives a panel (panels.py size): what a panel made or
  // changed in the page grows to, on the 4 px grid.
  const panelSize = node => {
    const shape = panelShape(node);
    const [insetX, insetY] = panelInsets(shape);
    const lane = node.panelIcon ? PANEL.icon_x + PANEL.icon : 0;
    const details = panelDetailLines(node);
    const heading = Math.max(panelText(node.name || '', PANEL.title_size),
      ...details.map(line => panelText(line, 0, PANEL.detail_advance)));
    let need = heading + 2 * (PANEL.pad_x + lane);
    panelRows(node).forEach(row => { need = Math.max(need, row.reduce((sum, cell) => sum + cellNeed(cell), 0)); });
    const width = Math.min(PANEL.max_width, Math.max(PANEL.min_width, need + 2 * insetX));
    const height = PANEL.pad_top + PANEL.title_line + details.length * PANEL.detail_line + PANEL.pad_bottom
      + panelRows(node).reduce((sum, row) => sum + rowHeight(row), 0) + 2 * insetY;
    return {width: Math.ceil(width / 4) * 4, height: Math.ceil(height / 4) * 4};
  };
  // The smallest a panel is drawn: its rows do not wrap, so it needs all of
  // its height, and narrower than the panel's least width every line ends
  // in an ellipsis. Shrunk past either, its compartments spilled out below.
  const panelFloor = node => ({width: PANEL.min_width, height: panelSize(node).height});
  // Compartments as the Style tab writes them: a row a line, || between
  // cells, | before each line under a cell's title, [tone] first to fill it.
  const sectionsText = node => panelRows(node).map(row => row.map(cell => `${cell.tone ? `[${cell.tone}] ` : ''}`
    + [cell.title || '', ...cellLines(cell)].join(' | ').replace(/^ \| /, '| ')).join(' || ')).join('\n');
  const parseSections = text => String(text).split('\n').map(line => line.trim()).filter(Boolean).map(line => line
    .split('||').map(part => {
      let rest = part.trim();
      const toned = rest.match(/^\[([a-z]+)\]\s*/);
      if (toned) rest = rest.slice(toned[0].length);
      const [title, ...lines] = rest.split('|').map(piece => piece.trim());
      const cell = {title: title || '', lines: lines.filter(Boolean)};
      if (toned && TONES[toned[1]]) cell.tone = toned[1];
      return cell;
    }).filter(cell => cell.title || cell.lines.length)).filter(row => row.length);
  const panelFit = (text, room, advance) => {
    const budget = Math.max(1, Math.floor(room / advance + 1e-9));
    const value = String(text);
    return value.length <= budget ? value : `${value.slice(0, budget - 1)}…`;
  };
  const panelInsets = shape => (shape === 'ellipse' ? [PANEL.ellipse_pad, PANEL.ellipse_pad_y]
    : shape === 'hexagon' ? [PANEL.hex_inset, 0] : [0, 0]);
  const panelOutline = (shape, w, h) => {
    if (shape === 'ellipse') return `<ellipse cx="${w / 2}" cy="${h / 2}" rx="${w / 2}" ry="${h / 2}"`;
    if (shape === 'hexagon') {
      const inset = PANEL.hex_inset;
      return `<polygon points="${[[inset, 0], [w - inset, 0], [w, h / 2], [w - inset, h], [inset, h], [0, h / 2]]
        .map(([x, y]) => `${x},${y}`).join(' ')}"`;
    }
    if (shape === 'note') return `<path d="M0,0 H${w - PANEL.fold} L${w},${PANEL.fold} V${h} H0 Z"`;
    return `<rect width="${w}" height="${h}" rx="${PANEL.radius}"`;
  };
  const panelMarkup = (node, fill, stroke, outlineStroke, outlineWidth) => {
    const colors = canvasPalette();
    const shape = panelShape(node);
    const w = node.width;
    const h = node.height;
    const own = toneOf(node.attributes?.tone);
    const paint = node.style?.fill ? fill : own ? own[0] : fill;
    const border = node.style?.stroke ? stroke : own ? own[1] : stroke;
    const [insetX, insetY] = panelInsets(shape);
    const lane = node.panelIcon ? PANEL.icon_x + PANEL.icon : 0;
    const lines = [`${panelOutline(shape, w, h)} fill="${escapeText(paint)}" stroke="none"/>`];
    if (node.panelIcon && node.iconUri) {
      lines.push(`<image href="${escapeText(node.iconUri)}" x="${insetX + PANEL.icon_x}" y="${insetY + PANEL.icon_y}" width="${PANEL.icon}" height="${PANEL.icon}" preserveAspectRatio="xMidYMid meet" aria-hidden="true"${inkFilter(node.iconUri)}/>`);
    }
    const sans = "'Inter',sans-serif";
    const room = w - 2 * (insetX + PANEL.pad_x + lane);
    let top = insetY + PANEL.pad_top;
    lines.push(`<text x="${w / 2}" y="${panelBaseline(top, PANEL.title_line, PANEL.title_size)}" fill="${colors.text}" font-size="${PANEL.title_size}" font-weight="${PANEL.title_weight}" font-family="${sans}" text-anchor="middle">${escapeText(panelFit(node.name, room, PANEL.title_size * METRICS.text.advance))}</text>`);
    top += PANEL.title_line;
    const details = panelDetailLines(node);
    details.forEach(line => {
      lines.push(`<text x="${w / 2}" y="${panelBaseline(top, PANEL.detail_line, PANEL.detail_size)}" fill="${colors.secondary}" font-size="${PANEL.detail_size}" font-family="${sans}" text-anchor="middle">${escapeText(panelFit(line, room, PANEL.detail_advance))}</text>`);
      top += PANEL.detail_line;
    });
    top = insetY + PANEL.pad_top + PANEL.title_line + details.length * PANEL.detail_line + PANEL.pad_bottom;
    panelRows(node).forEach(row => {
      const height = rowHeight(row);
      const widths = cellWidths(row, w);
      let left = 0;
      row.forEach((cell, index) => {
        const width = widths[index];
        const tone = toneOf(cell.tone);
        if (tone) {
          // one unit in from the outline, so a tone never shows past a
          // rounded corner; the outline is drawn over it
          const first = index === 0 ? 1 : 0;
          const last = index === row.length - 1 ? 1 : 0;
          const floor = top + height >= h - 0.5 ? 1 : 0;
          lines.push(`<rect data-panel-cell x="${left + first}" y="${top}" width="${width - first - last}" height="${height - floor}" fill="${tone[0]}"/>`);
        }
        if (index) lines.push(`<line x1="${left}" y1="${top}" x2="${left}" y2="${top + height}" stroke="${escapeText(border)}" stroke-width="1"/>`);
        const middle = left + width / 2;
        const textRoom = width - 2 * PANEL.cell_pad_x;
        let lineTop = top + PANEL.cell_pad_y;
        if (cell.title) {
          lines.push(`<text x="${middle}" y="${panelBaseline(lineTop, PANEL.cell_title_line, PANEL.cell_title_size)}" fill="${colors.text}" font-size="${PANEL.cell_title_size}" font-weight="${PANEL.cell_title_weight}" font-family="${sans}" text-anchor="middle">${escapeText(panelFit(cell.title, textRoom, PANEL.cell_title_size * METRICS.text.advance))}</text>`);
          lineTop += PANEL.cell_title_line;
        }
        cellLines(cell).forEach(text => {
          lines.push(`<text x="${middle}" y="${panelBaseline(lineTop, PANEL.cell_line, PANEL.cell_size)}" fill="${colors.secondary}" font-size="${PANEL.cell_size}" font-family="${sans}" text-anchor="middle">${escapeText(panelFit(text, textRoom, PANEL.cell_advance))}</text>`);
          lineTop += PANEL.cell_line;
        });
        left += width;
      });
      lines.push(`<line x1="0" y1="${top}" x2="${w}" y2="${top}" stroke="${escapeText(border)}" stroke-width="1"/>`);
      top += height;
    });
    const edge = outlineStroke || border;
    lines.push(`${panelOutline(shape, w, h)} fill="none" stroke="${escapeText(edge)}" stroke-width="${outlineWidth}"/>`);
    if (shape === 'note') {
      lines.push(`<path d="M${w - PANEL.fold},0 V${PANEL.fold} H${w}" fill="none" stroke="${escapeText(edge)}" stroke-width="${outlineWidth}"/>`);
    }
    return `<g data-panel>${lines.join('')}</g>`;
  };

  const nodeMarkup = node => {
    const colors = canvasPalette();
    const fill = node.style?.fill || colors.card;
    const stroke = node.style?.stroke || colors.border;
    // Keep the standard 72 px card geometry unchanged while centering compact
    // cards (for example the 52 px DOKS worker rows) from their actual height.
    // a panel is a box whatever the display (builders/panels.py)
    const panel = isPanel(node);
    const iconOnly = node.displayMode === 'icon' && !panel;
    // The connection dots stand 10 screen pixels off the middle of each
    // edge of the card's box, 5 px across whatever the zoom (--port-gap and
    // --port-unit, set with the zoom in 10-grid), so they never sit on the
    // drawing. Only the place to grab a wire moved: the wire itself still
    // starts and ends on the ink (seat and portPoint, in 19-canvas-pointer).
    const PORT_SIDES = {top: [0.5, 0, 0, -1], right: [1, 0.5, 1, 0], bottom: [0.5, 1, 0, 1], left: [0, 0.5, -1, 0]};
    // Icon display is the bare vendor mark with its caption beneath, the way
    // reference architectures are drawn. A node too short for a caption
    // (the 64 px icons older pages saved) still centres the glyph alone.
    const captioned = iconOnly && node.height >= ICON_NODE.captionMinHeight;
    const iconSize = iconOnly
      ? Math.min(ICON_NODE.glyph, node.width - 8, (captioned ? node.height - 34 : node.height) - 8)
      : 32;
    const iconX = iconOnly ? (node.width - iconSize) / 2 : 14;
    const iconY = iconOnly ? (captioned ? ICON_NODE.glyphTop : (node.height - iconSize) / 2) : (node.height - 32) / 2;
    const fallbackIconSize = iconOnly ? Math.min(40, node.width - 8, node.height - 8) : 28;
    const fallbackIconX = iconOnly ? (node.width - fallbackIconSize) / 2 : 16;
    const fallbackIconY = (node.height - fallbackIconSize) / 2;
    const titleY = node.height / 2 - 2;
    const detailY = node.height / 2 + 14;
    const icon = node.iconUri
      ? `<image href="${escapeText(node.iconUri)}" x="${iconX}" y="${iconY}" width="${iconSize}" height="${iconSize}" preserveAspectRatio="xMidYMid meet" aria-hidden="true"${inkFilter(node.iconUri)}/>`
      : `<rect x="${fallbackIconX}" y="${fallbackIconY}" width="${fallbackIconSize}" height="${fallbackIconSize}" rx="4" fill="${colors.control}"/><text x="${fallbackIconX + fallbackIconSize / 2}" y="${node.height / 2 + 5}" text-anchor="middle" font-family="'Inter',sans-serif" font-size="12" font-weight="600" fill="${colors.secondary}">${escapeText(String(node.name).slice(0, 1).toUpperCase())}</text>`;
    const selectedNode = isNodeSelected(node.id);
    const focusDimmed = Boolean(currentFlow && !currentFlow.nodes.has(node.id));
    // The cost lens tints a priced card by its share of the dearest one, and
    // says what it costs a month above it.
    const heatShare = currentFlow?.heat?.get(node.id);
    const heat = heatShare === undefined ? ''
      : `<rect data-cost-heat x="-6" y="-6" width="${node.width + 12}" height="${node.height + 12}" rx="10" fill="${colors.error}" fill-opacity="${(0.08 + 0.34 * heatShare).toFixed(2)}" stroke="${colors.error}" stroke-opacity="${(0.3 + 0.7 * heatShare).toFixed(2)}" stroke-width="1.5" pointer-events="none"/>`
        + `<text data-cost-heat x="${node.width / 2}" y="-11" text-anchor="middle" font-family="'Inter',sans-serif" font-size="11" font-weight="600" fill="${colors.error}" pointer-events="none">${escapeText(money(nodeMonthly(node), node.attributes?.price?.currency))}/mo</text>`;
    const normalizedSearch = activeSearchQuery.trim().toLocaleLowerCase();
    const searchMatch = Boolean(normalizedSearch && `${node.name} ${node.detail} ${node.componentId} ${node.componentProvider}`.toLocaleLowerCase().includes(normalizedSearch));
    const searchDimmed = Boolean(normalizedSearch && !searchMatch);
    const textStyle = withCurrentFace({fontFamily: 'Inter', fontSize: 12, fontWeight: 600,
      textAlign: 'left', textColor: colors.text, opacity: 100, ...(node.textStyle || {})});
    const anchor = textStyle.textAlign === 'center' ? 'middle' : textStyle.textAlign === 'right' ? 'end' : 'start';
    const textX = textStyle.textAlign === 'center' ? node.width / 2 : textStyle.textAlign === 'right' ? node.width - 12 : 54;
    const captionChars = Math.max(6, Math.floor((node.width - 8) / (Number(textStyle.fontSize) * 0.58)));
    const caption = captioned
      ? `<text x="${node.width / 2}" y="${iconY + iconSize + 16}" fill="${escapeText(textStyle.textColor)}" fill-opacity="${Number(textStyle.opacity) / 100}" font-family="'${escapeText(textStyle.fontFamily)}',sans-serif" font-size="${Number(textStyle.fontSize)}" font-weight="${escapeText(textStyle.fontWeight)}" text-anchor="middle">${escapeText(truncate(node.name, captionChars))}</text>`
        + (node.detail && node.height >= ICON_NODE.captionMinHeight + 12
          ? `<text x="${node.width / 2}" y="${iconY + iconSize + 31}" fill="${colors.secondary}" font-family="'Inter',sans-serif" font-size="10" text-anchor="middle">${escapeText(truncate(node.detail, Math.floor((node.width - 8) / 5.8)))}</text>`
          : '')
      : '';
    // A resource the estate keeps without using says Unused in its top-right
    // corner, inside the box, in plain text (render-metrics.json flag; render.py
    // _flag): amber on light, a lighter amber on a dark canvas.
    const tag = METRICS.flag;
    const flagWidth = tag ? Math.ceil(tag.label.length * tag.font * tag.advance + 2 * tag.pad) : 0;
    const flag = tag && node.attributes?.unused
      ? `<g data-unused-flag="true"><title>${escapeText(node.attributes.unused.reason || '')}</title><rect x="${node.width - tag.inset - flagWidth}" y="${tag.inset}" width="${flagWidth}" height="${tag.height}" rx="${tag.radius}" fill="${tag.fill}" stroke="${tag.stroke}" stroke-width="0.8"/>`
        + `<text x="${node.width - tag.inset - flagWidth / 2}" y="${tag.inset + tag.height / 2 + tag.font * 0.35}" fill="${darkCanvas() && tag.ink_dark ? tag.ink_dark : tag.ink}" font-size="${tag.font}" font-weight="${tag.weight}" font-family="'Inter',sans-serif" text-anchor="middle">${escapeText(tag.label)}</text></g>`
      : '';
    // A native tooltip for SVG viewers and for the exported .svg: the name and
    // detail, so a bare icon still explains itself with no script running.
    const nativeTitle = `<title>${escapeText([node.name, node.detail].filter(Boolean).join(' · '))}</title>`;
    const availableTitleWidth = textStyle.textAlign === 'center'
      ? node.width - 24 : Math.max(48, node.width - textX - 12);
    const maxNameChars = Math.max(
      8, Math.floor(availableTitleWidth / (Number(textStyle.fontSize) * 0.58)),
    );
    const maxDetailChars = Math.max(8, Math.floor(Math.max(48, node.width - 66) / 5.2));
    const rotate = Number(node.angle) ? ` rotate(${Number(node.angle)} ${node.width / 2} ${node.height / 2})` : '';
    const scaleX = node.flipX ? -1 : 1;
    const scaleY = node.flipY ? -1 : 1;
    const flip = scaleX === 1 && scaleY === 1 ? '' : ` translate(${node.flipX ? node.width : 0} ${node.flipY ? node.height : 0}) scale(${scaleX} ${scaleY})`;
    // A dot answers a mouse 9 px round it and a finger 22 px; the finger's
    // circle stands further out, so the card itself is still what a finger
    // on it moves. Both are screen pixels: the handle group is scaled.
    const portReach = coarsePointer() ? 22 : 9;
    const outward = coarsePointer() ? portReach - 10 : 0;
    // What a selection hugs: a card's box, or a bare icon's glyph and the
    // caption under it -- an icon's box is wider than both, and an outline
    // round the box stood far off the drawing.
    const captionWidth = (text, size) => text.length * size * 0.58;
    const detailShown = captioned && node.detail && node.height >= ICON_NODE.captionMinHeight + 12;
    const hugWidth = iconOnly ? Math.min(node.width, Math.max(iconSize,
      captioned ? captionWidth(truncate(node.name, captionChars), Number(textStyle.fontSize)) : 0,
      detailShown ? truncate(node.detail, Math.floor((node.width - 8) / 5.8)).length * 5.8 : 0)) : node.width;
    const hug = iconOnly
      ? {x: (node.width - hugWidth) / 2 - 6, y: iconY - 6, width: hugWidth + 12,
        height: (captioned ? iconSize + (detailShown ? 35 : 21) : iconSize) + 12}
      : {x: 0, y: 0, width: node.width, height: node.height};
    // the Unused word in the corner sits inside the outline, never under it
    if (iconOnly && tag && node.attributes?.unused) {
      const right = Math.max(hug.x + hug.width, node.width - tag.inset + 3);
      const top = Math.min(hug.y, tag.inset - 3);
      const left = Math.min(hug.x, node.width - right);
      Object.assign(hug, {x: left, width: right - left, height: hug.height + hug.y - top, y: top});
    }
    const ports = Object.entries(PORT_SIDES).map(([side, [fx, fy, dx, dy]]) => `<g data-node-port="${side}" transform="translate(${hug.x + hug.width * fx} ${hug.y + hug.height * fy})">`
      + `<title>Drag to another resource to connect</title><g class="node-port-handle" style="--dx:${dx};--dy:${dy}">`
      + `<circle r="${portReach}" cx="${dx * outward}" cy="${dy * outward}" fill="transparent" pointer-events="all"/>`
      + `<circle class="node-port-dot" r="5" fill="${colors.handle}" stroke="${colors.selection}" stroke-width="1.5" pointer-events="none"/></g></g>`).join('');
    // Resize from the right edge, the bottom edge and the corner between
    // them. Only the corner is drawn: the two edges answer along their
    // length, unseen but for the cursor, so no square crowds the dots that
    // keep the edges' middles. Drawn at 8 units, the corner answers a finger
    // from a larger square, and an edge from a wider strip. On a bare icon
    // they sit on the outline round glyph and caption, not on its wider box.
    const grip = touchReach(8, 32);
    const strip = touchReach(6, 16);
    const resizeId = escapeText(node.id);
    const right = hug.x + hug.width;
    const bottom = hug.y + hug.height;
    const handles = selectedNode && selectedObjects().length === 1
      ? `<rect data-node-resize="e" data-resize-node-id="${resizeId}" x="${right - strip / 2}" y="${hug.y}" width="${strip}" height="${Math.max(0, hug.height - 6)}" fill="transparent"><title>Drag to change the width</title></rect>`
        + `<rect data-node-resize="s" data-resize-node-id="${resizeId}" x="${hug.x}" y="${bottom - strip / 2}" width="${Math.max(0, hug.width - 6)}" height="${strip}" fill="transparent"><title>Drag to change the height</title></rect>`
        + (grip > 8 ? `<rect data-node-resize="se" data-resize-node-id="${resizeId}" x="${right - grip / 2}" y="${bottom - grip / 2}" width="${grip}" height="${grip}" fill="transparent"><title>Drag to change the width and height</title></rect>` : '')
        + `<rect data-node-resize="se" data-resize-node-id="${resizeId}" x="${right - 4}" y="${bottom - 4}" width="8" height="8" rx="1" fill="${colors.handle}" stroke="${colors.selection}" stroke-width="1.5"><title>Drag to change the width and height</title></rect>`
      : '';
    // Selected, a card is outlined in the accent: the card's own border turns
    // (below), a card with a border of its own gets an outline just outside
    // it, and a bare icon a rounded one round its glyph and caption.
    const outline = iconOnly
      ? `<rect class="node-selection" x="${hug.x}" y="${hug.y}" width="${hug.width}" height="${hug.height}" rx="10" fill="none" stroke="${colors.selection}" stroke-width="2" pointer-events="none"/>`
      : node.style?.stroke
        ? `<rect class="node-selection" x="-3" y="-3" width="${node.width + 6}" height="${node.height + 6}" rx="8" fill="none" stroke="${colors.selection}" stroke-width="2" pointer-events="none"/>`
        : '';
    return `<g data-graph-node data-sole-selected="${selectedNode && selectedObjects().length === 1}" data-ink="${(Array.isArray(node.ink) ? node.ink : []).join(',')}"${seatable(node) ? ` data-ink-edge="${escapeText(node.inkEdges)}"` : ''} data-node-id="${escapeText(node.id)}" data-component-id="${escapeText(node.componentId)}" data-component-provider="${escapeText(node.componentProvider || '')}" data-component-qualified-id="${escapeText(node.componentQualifiedId || '')}" data-connect-target="${connectTargetId === node.id}" data-display-mode="${iconOnly ? 'icon' : 'card'}" data-layer-id="${escapeText(node.layerId || '')}" data-locked="${itemIsLocked(node)}" data-selected="${selectedNode}" data-focus-dimmed="${focusDimmed}" data-search-match="${searchMatch}" data-search-dimmed="${searchDimmed}" transform="${nodeTransform(node)}" role="group" aria-label="${escapeText(node.name)}">
      ${nativeTitle}${heat}
      <rect data-node-surface width="${node.width}" height="${node.height}" rx="6" fill="${iconOnly || panel ? 'transparent' : escapeText(fill)}" stroke="${iconOnly || panel ? 'transparent' : selectedNode && !node.style?.stroke ? colors.selection : escapeText(stroke)}" stroke-width="${selectedNode ? 2 : 1}" pointer-events="all"/>
      ${panel ? panelMarkup(node, fill, stroke, selectedNode && !node.style?.stroke ? colors.selection : '', selectedNode ? 2 : 1) : ''}
      ${panel ? '' : icon}
      ${caption}
      ${iconOnly || panel ? '' : `<text x="${textX}" y="${titleY}" fill="${escapeText(textStyle.textColor)}" fill-opacity="${Number(textStyle.opacity) / 100}" font-family="'${escapeText(textStyle.fontFamily)}',sans-serif" font-size="${Number(textStyle.fontSize)}" font-weight="${escapeText(textStyle.fontWeight)}" text-anchor="${anchor}">${escapeText(truncate(node.name, maxNameChars))}</text>
      ${node.detail ? `<text x="54" y="${detailY}" fill="${colors.secondary}" font-family="'Inter',sans-serif" font-size="9">${escapeText(truncate(node.detail, maxDetailChars))}</text>` : ''}`}
      ${flag}
      ${outline}
      ${ports}
      ${handles}
    </g>`;
  };

  const automaticEdgeLabel = item => {
    const straightHorizontal = Math.abs(item.sourcePoint.y - item.targetPoint.y) < 0.01;
    const straightVertical = Math.abs(item.sourcePoint.x - item.targetPoint.x) < 0.01;
    const sourceIsHorizontal = ['left', 'right'].includes(item.sourcePort);
    let x = (item.sourcePoint.x + item.targetPoint.x) / 2;
    let y = item.sourcePoint.y - 12;
    let anchor = 'middle';
    let side = 'horizontal';
    if (straightVertical) {
      x = item.sourcePoint.x + 12;
      y = (item.sourcePoint.y + item.targetPoint.y) / 2 + 3;
      anchor = 'start';
      side = 'vertical';
    } else if (!straightHorizontal && sourceIsHorizontal) {
      x = snap((item.sourcePoint.x + item.targetPoint.x) / 2) + 12;
      y = (item.sourcePoint.y + item.targetPoint.y) / 2 + 3;
      anchor = 'start';
      side = 'vertical';
    } else if (!straightHorizontal) {
      x = (item.sourcePoint.x + item.targetPoint.x) / 2;
      y = snap((item.sourcePoint.y + item.targetPoint.y) / 2) - 12;
    }
    // A wire that bends is not where the midpoint of its two ports is: on a
    // detour around a card, or up and over a frame, that point sits in empty
    // space. Start halfway along the drawn wire instead -- above a level run,
    // beside a vertical one -- which is where the static picture puts it.
    if (!straightHorizontal && !straightVertical) {
      const corners = captionCorners(item);
      if (corners.length > 2) {
        const spot = alongPolyline(corners, 0.5);
        if (spot.horizontal) {
          x = snap(spot.x); y = spot.y - 12; anchor = 'middle'; side = 'horizontal';
        } else {
          x = spot.x + 12; y = snap(spot.y) + 3; anchor = 'start'; side = 'vertical';
        }
      }
    }
    // Every kind's caption starts on its own wire: a circuit's or a tunnel's
    // used to stand a fixed distance above or below the cards, wherever the
    // wire ran, and named no line (builders/captions.py).
    return {x, y, anchor, side};
  };

  const edgeLabelWidth = edge => {
    // The mask has to cover the text at whatever size the author chose,
    // otherwise a bigger label bleeds over the wire it sits on.
    const size = Number(edgeTextStyle(edge).fontSize) || EDGE_TEXT_DEFAULTS.fontSize;
    // The caption is placed and masked by this estimate, so it must fit the
    // face: Inter averages 0.51 em a character and nine labels in ten stay
    // under 0.56, which 0.55 plus the mask's 10 px of padding covers; a wider
    // estimate floats a caption set beside a vertical wire off it. A mono
    // face an author picks takes 0.63 em plus its 0.08 em tracking.
    const perCharacter = size * (monoFace(edgeTextStyle(edge).fontFamily) ? 0.72 : 0.55);
    return Math.max(24, Math.ceil((String(edge.label || '').length * perCharacter + 10) / 4) * 4);
  };

  // A wire's place in a flow told in order (1 to 99), or 0; and how much
  // further left its caption's chip reaches than its text for the numbered
  // circle (render-metrics.json step.lead, the number builders/captions.py
  // reads), so placement, the chip and the checker all count the circle.
  const edgeStep = edge => {
    const number = Number(edge?.step);
    return Number.isInteger(number) && number >= 1 && number <= 99 ? number : 0;
  };
  const captionLead = edge => (edgeStep(edge) && edge.label ? STEP.lead : 0);
  // How a step is marked: its flow's shape and colour, its number or its
  // letter (1 is A) -- the theme's main flow, or the second flow a wire's
  // stepFlow names (builders/render.py _step_badge, themes StepMark).
  const stepMark = edge => {
    const marks = state.stepMarks || {};
    return (edge.stepFlow ? marks.second : marks.main)
      || {color: state.stepColor || canvasPalette().text, shape: edge.stepFlow ? 'square' : 'circle', marks: 'numbers'};
  };
  const stepMarkText = (mark, number) => (mark.marks === 'letters' && number <= 26
    ? String.fromCharCode(64 + number) : String(number));
  // How tall the chip is, for placement, collision and drawing alike: a
  // numbered caption's holds its circle; a plain one is its type plus 5 px,
  // never under 14 (builders/captions.py CAPTION_TALL).
  const captionHeight = edge => (captionLead(edge) ? STEP.chip
    : Math.max(14, Number(edgeTextStyle(edge).fontSize) + 5));

  // Captions placed so far in the current render, in edge order, so a later
  // caption keeps clear of an earlier one the way it keeps clear of a card.
  // Reset at the start of the caption pass; consulted only during it.
  let placedCaptions = [];
  let collectingCaptions = false;
  // Every wire's corners in the current caption pass, as its caption is
  // placed along them: a numbered chip is kept off all of them.
  let captionWires = [];
  const captionBoxAt = (item, x, y, side) => {
    const width = edgeLabelWidth(item.edge);
    const lead = captionLead(item.edge);
    const tall = captionHeight(item.edge);
    return {x: side === 'vertical' ? x - 4 : x - width / 2 - lead, y: y - tall / 2 - 4, width: width + lead, height: tall};
  };

  // Node ports use a 16 px transparent hit target. By default a caption keeps
  // clear of that full interactive terminal geometry, not only the visible
  // card; a caller with nowhere else to put a caption may ask for 0 and keep
  // clear of what is drawn alone.
  const PORT_CLEARANCE = 16 + 8;
  // A caption's chip keeps this far off a frame's border line: a border
  // through the chip reads as a wire through the caption (RAIL_KEEP).
  const RAIL_KEEP = 2;

  const keepEdgeLabelClearOfNodes = (item, requestedX, requestedY, side = 'horizontal', clearance = PORT_CLEARANCE) => {
    const width = edgeLabelWidth(item.edge);
    const halfWidth = width / 2;
    // The drawn mask: centred on the anchor beside a level wire, running to
    // the right of it beside a vertical one (see edgeLabelMarkup's maskX).
    // A step's circle widens the chip left of the text above a level run,
    // right of the anchor beside a vertical wire, so it never sits on the wire.
    const lo = side === 'vertical' ? 4 : halfWidth + captionLead(item.edge);
    const hi = side === 'vertical' ? width - 4 + captionLead(item.edge) : halfWidth;
    // The chip stands `above` the baseline and `below` it: 11 and 3 for a
    // plain caption, more for a numbered one's circle.
    const tall = captionHeight(item.edge);
    const above = tall / 2 + 4;
    const below = tall / 2 - 4;
    let x = clamp(requestedX, lo, state.canvas.width - hi);
    let y = clamp(requestedY, above + 1, state.canvas.height - below - 1);
    // Frame titles block a caption for the same reason they block a route:
    // the title is the only text saying what the frame is.
    // A card blocks its box. A bare glyph blocks what it draws -- the glyph
    // and the caption band -- not the invisible box around them, otherwise
    // the corridor between two glyphs is never clear and the caption is
    // pushed far from its wire.
    const blockers = [
      ...state.nodes.filter(nodeIsVisible).flatMap(node => (node.displayMode === 'icon'
        ? ownBoxes(node).map(box => ({x: box.left, y: box.top, width: box.right - box.left, height: box.bottom - box.top}))
        : [node])),
      ...(state.boundaries || []).filter(boundaryIsVisible)
        .flatMap(boundary => [boundaryLabelBox(boundary), boundaryBadgeBox(boundary)]).filter(Boolean),
      ...(collectingCaptions ? placedCaptions : []),
      // every frame's borders as lines, top, bottom, left, right: kept
      // RAIL_KEEP off, not a card's port clearance
      ...(state.boundaries || []).filter(boundaryIsVisible).flatMap(b => [
        {x: b.x, y: b.y, width: b.width, height: 0, keep: RAIL_KEEP},
        {x: b.x, y: b.y + b.height, width: b.width, height: 0, keep: RAIL_KEEP},
        {x: b.x, y: b.y, width: 0, height: b.height, keep: RAIL_KEEP},
        {x: b.x + b.width, y: b.y, width: 0, height: b.height, keep: RAIL_KEEP},
      ]),
    ];
    const room = box => (box.keep ?? clearance);
    const hits = (px, py, box) => (
      px + hi > box.x - room(box)
      && px - lo < box.x + box.width + room(box)
      && py + below > box.y - room(box)
      && py - above < box.y + box.height + room(box)
    );
    // Stepping off one blocker can land on the next, so score each candidate
    // against every blocker and repeat until the caption is clear. Without
    // this a label nudged off a frame title settles on the card beside it.
    for (let pass = 0; pass < 4; pass += 1) {
      const hit = blockers.find(box => hits(x, y, box));
      if (!hit) break;
      const requested = {x, y};
      const keep = room(hit);
      const best = [
        {x: snap(hit.x - keep - hi), y},
        {x: snap(hit.x + hit.width + keep + lo), y},
        {x, y: snap(hit.y - keep - below)},
        {x, y: snap(hit.y + hit.height + keep + above)},
      ].map(candidate => ({
        x: clamp(candidate.x, lo, state.canvas.width - hi),
        y: clamp(candidate.y, above + 1, state.canvas.height - below - 1),
      })).map(candidate => ({
        ...candidate,
        blocked: blockers.filter(box => hits(candidate.x, candidate.y, box)).length,
        distance: Math.hypot(candidate.x - requested.x, candidate.y - requested.y),
      })).sort((a, b) => a.blocked - b.blocked || a.distance - b.distance)[0];
      x = best.x;
      y = best.y;
    }
    return {x, y, blocked: blockers.some(box => hits(x, y, box))};
  };

  // A caption belongs beside its wire. Port clearance is a preference: when
  // keeping all of it would carry the caption further than this from the
  // spot it was asked for, a nearer spot that keeps clear of what is drawn
  // wins over a far one that also keeps clear of the ports.
  const CAPTION_DRIFT = 32;

  // The automatic caption, made to fit: nudged off whatever it lands on, and
  // when no nudge is clear, tried at other points along the wire itself.
  // How far a caption may be nudged and still read as sitting on its wire.
  const CAPTION_NEAR = 24;
  // Where a caption sits for a point on its wire: above a level run, centred;
  // beside a vertical one, starting 10 px to its right. Starting from the wire
  // rather than centring on an estimate of the caption's width keeps that gap
  // exact whatever the face measures -- centred, a proportional caption
  // narrower than its estimate floated up to 35 px off the wire.
  const besideWire = spot => (spot.horizontal
    ? {x: spot.x, y: spot.y - 12, anchor: 'middle', side: 'horizontal'}
    : {x: spot.x + 10, y: spot.y + 3, anchor: 'start', side: 'vertical'});
  // How far a nudge may carry a caption away from its wire (across it; along
  // it is free) and leave it reading as beside the wire.
  const CAPTION_BESIDE = 8;
  const awayFromWire = (nudged, spot) => (spot.side === 'horizontal'
    ? Math.abs(nudged.y - spot.y) : Math.abs(nudged.x - spot.x));
  // The first spot along the wire that stays beside it: within CAPTION_NEAR
  // of where it was asked and no more than CAPTION_BESIDE off the wire.
  // Nudged toward its wire until the chip comes within 2 px of it: the wire
  // runs 12 px below a level caption's anchor, 10 px left of a vertical one's.
  // A chip asked for on a vertical wire's left keeps its right edge off it.
  const ontoWire = (item, nudged, spot, left = false) => {
    if (spot.side === 'horizontal') return nudged.y + captionHeight(item.edge) / 2 - 4 > spot.y + 10;
    return left ? nudged.x > spot.x : nudged.x - 4 < spot.x - 8;
  };
  // The same chip on a vertical wire's other side: its right edge 6 px left
  // of the wire, as its left edge is 6 px right of it on the right.
  const leftOfWire = (item, spot) => ({
    ...spot, x: spot.x - 12 - edgeLabelWidth(item.edge) - captionLead(item.edge),
  });
  // Whether a numbered chip would cover a drawn line: another wire, or its
  // own at a bend (builders/captions.py crosses). A plain chip keeps to its
  // placement as before.
  const chipCrossesWire = (item, spot) => {
    if (!captionLead(item.edge) || !collectingCaptions) return false;
    const box = captionBoxAt(item, spot.x, spot.y, spot.side);
    return captionWires.some(points => points.some((a, index) => {
      const b = points[index + 1];
      if (!b) return false;
      if (Math.abs(a.y - b.y) < 0.01) {
        return Math.min(a.x, b.x) < box.x + box.width - 1 && Math.max(a.x, b.x) > box.x + 1
          && box.y + 1 < a.y && a.y < box.y + box.height - 1;
      }
      if (Math.abs(a.x - b.x) < 0.01) {
        return Math.min(a.y, b.y) < box.y + box.height - 1 && Math.max(a.y, b.y) > box.y + 1
          && box.x + 1 < a.x && a.x < box.x + box.width - 1;
      }
      return false;
    }));
  };
  // Whether another wire runs along this one at a point: a level run through
  // a level point, an upright one through an upright point (builders/
  // captions.py shares_run). Wires leaving one side of a card leave from its
  // one point and run together before they part; a caption on that trunk
  // names any of them, so it goes where its own wire runs alone.
  const sharesRun = (spot, corners) => {
    if (!collectingCaptions) return false;
    const own = JSON.stringify(corners.map(point => [point.x, point.y]));
    return captionWires.some(points => {
      if (points === corners || JSON.stringify(points.map(point => [point.x, point.y])) === own) return false;
      return points.some((a, index) => {
        const b = points[index + 1];
        if (!b) return false;
        if (spot.horizontal) {
          return Math.abs(a.y - b.y) < 0.01 && Math.abs(a.y - spot.y) < 0.5
            && Math.min(a.x, b.x) - 0.5 <= spot.x && spot.x <= Math.max(a.x, b.x) + 0.5;
        }
        return Math.abs(a.x - b.x) < 0.01 && Math.abs(a.x - spot.x) < 0.5
          && Math.min(a.y, b.y) - 0.5 <= spot.y && spot.y <= Math.max(a.y, b.y) + 0.5;
      });
    });
  };
  // The farthest a caption's chip may stand from its own wire and still name
  // it; the checker holds every picture to the same number (captions.py REACH).
  const CAPTION_REACH = 12;
  const nearOwnWire = (item, spot, side, corners) => {
    const box = captionBoxAt(item, spot.x, spot.y, side);
    return corners.some((a, index) => {
      const b = corners[index + 1];
      if (!b) return false;
      const dx = Math.max(box.x - Math.max(a.x, b.x), 0, Math.min(a.x, b.x) - (box.x + box.width));
      const dy = Math.max(box.y - Math.max(a.y, b.y), 0, Math.min(a.y, b.y) - (box.y + box.height));
      return Math.hypot(dx, dy) <= CAPTION_REACH;
    });
  };
  // Nothing clear beside the wire: the chip centred on the wire itself,
  // breaking the line it names, where that is clear of the cards, the
  // borders and the captions before it, off every other wire and off a run
  // it shares (captions.py on_line). Read as the wire's own; a caption
  // pushed off it reads as no wire's.
  const LINE_RATIOS = [0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8, 0.15, 0.85, 0.1, 0.9];
  const LINE_CLEARANCE = 4;
  // A box another wire runs through, 1 px in from its edges (captions.py
  // crosses), over every wire but this one.
  const otherWiresThrough = corners => {
    const own = JSON.stringify(corners.map(point => [point.x, point.y]));
    const others = collectingCaptions ? captionWires.filter(points => points !== corners
      && JSON.stringify(points.map(point => [point.x, point.y])) !== own) : [];
    return box => others.some(points => points.some((a, index) => {
      const b = points[index + 1];
      if (!b) return false;
      if (Math.abs(a.y - b.y) < 0.01) {
        return Math.min(a.x, b.x) < box.x + box.width - 1 && Math.max(a.x, b.x) > box.x + 1
          && box.y + 1 < a.y && a.y < box.y + box.height - 1;
      }
      if (Math.abs(a.x - b.x) < 0.01) {
        return Math.min(a.y, b.y) < box.y + box.height - 1 && Math.max(a.y, b.y) > box.y + 1
          && box.x + 1 < a.x && a.x < box.x + box.width - 1;
      }
      return false;
    }));
  };
  // Points along the wire, then the middle of each of its legs: a short
  // level leg between stacked cards has room where the long run up a
  // frame's edge has none.
  const lineSpots = corners => [
    ...LINE_RATIOS.map(ratio => alongPolyline(corners, ratio)),
    ...corners.slice(1).map((b, index) => {
      const a = corners[index];
      return {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, horizontal: Math.abs(b.x - a.x) >= Math.abs(b.y - a.y)};
    }),
  ];
  const onOwnWire = (item, corners) => {
    const crosses = otherWiresThrough(corners);
    for (const point of lineSpots(corners)) {
      if (sharesRun(point, corners)) continue;
      // the chip's middle on the wire: it stands 4 px above the anchor
      const spot = {x: point.x, y: point.y + 4};
      const nudged = keepEdgeLabelClearOfNodes(item, spot.x, spot.y, 'horizontal', LINE_CLEARANCE);
      const box = captionBoxAt(item, nudged.x, nudged.y, 'horizontal');
      // nudged, the chip must still cover its wire's point, 2 px in
      if (nudged.blocked || !(box.x + 2 < point.x && point.x < box.x + box.width - 2)
          || !(box.y + 2 < point.y && point.y < box.y + box.height - 2)) continue;
      if (crosses(box)) continue;
      return {x: nudged.x, y: nudged.y, anchor: 'middle', side: 'horizontal'};
    }
    return null;
  };
  // Still nothing: a chip a few pixels off the wire, either side of it and
  // along it, where nothing is drawn and no other wire runs -- the nearest
  // such spot, so long as it names the wire (captions.py near_line). Nudged
  // spots are not taken: each is where it was asked for or not at all.
  const nearOwnWireSpot = (item, corners) => {
    const width = edgeLabelWidth(item.edge);
    const lead = captionLead(item.edge);
    const tall = captionHeight(item.edge);
    const crosses = otherWiresThrough(corners);
    const points = lineSpots(corners);
    for (const gap of [2, 6, 10]) {
      for (const point of points) {
        const middles = point.horizontal
          ? [-1, 1].flatMap(side => [0, -width / 2, width / 2]
            .map(by => ({x: point.x + by, y: point.y + side * (tall / 2 + gap)})))
          : [1, -1].flatMap(side => [0, -tall, tall]
            .map(by => ({x: point.x + side * ((width + lead) / 2 + gap), y: point.y + by})));
        for (const middle of middles) {
          const ax = middle.x + lead / 2;
          const ay = middle.y + 4;
          const nudged = keepEdgeLabelClearOfNodes(item, ax, ay, 'horizontal', LINE_CLEARANCE);
          if (nudged.blocked || Math.hypot(nudged.x - ax, nudged.y - ay) > 0.5) continue;
          if (crosses(captionBoxAt(item, nudged.x, nudged.y, 'horizontal'))) continue;
          if (nearOwnWire(item, nudged, 'horizontal', corners)) {
            return {x: nudged.x, y: nudged.y, anchor: 'middle', side: 'horizontal'};
          }
        }
      }
    }
    return null;
  };
  const besideOnWire = (item, corners, ratios, clearance) => {
    for (const ratio of ratios) {
      const right = besideWire(alongPolyline(corners, ratio));
      // a numbered chip with no clear spot right of a vertical wire tries its left
      const sides = [[right, false]];
      if (captionLead(item.edge) && right.side === 'vertical') sides.push([leftOfWire(item, right), true]);
      for (const [spot, left] of sides) {
        const nudged = keepEdgeLabelClearOfNodes(item, spot.x, spot.y, spot.side, clearance);
        if (!nudged.blocked && Math.hypot(nudged.x - spot.x, nudged.y - spot.y) <= CAPTION_NEAR
            && awayFromWire(nudged, spot) <= CAPTION_BESIDE && !ontoWire(item, nudged, spot, left)
            && !chipCrossesWire(item, {...nudged, side: spot.side})
            && nearOwnWire(item, nudged, spot.side, corners)) {
          return {x: nudged.x, y: nudged.y, anchor: spot.anchor, side: spot.side};
        }
      }
    }
    return null;
  };
  const bestAutomaticLabel = (item, automatic) => {
    const drift = spot => Math.hypot(spot.x - automatic.x, spot.y - automatic.y);
    const settle = spot => ({x: spot.x, y: spot.y, anchor: automatic.anchor, side: automatic.side});
    const first = keepEdgeLabelClearOfNodes(item, automatic.x, automatic.y, automatic.side);
    // Where the wire runs alone, when it shares a run with another.
    const trunkCorners = captionCorners(item);
    const trunkRatios = [0.5, 0.3, 0.7, 0.15, 0.85, 0.4, 0.6];
    const alone = trunkRatios.filter(ratio => !sharesRun(alongPolyline(trunkCorners, ratio), trunkCorners));
    const trunk = alone.length > 0 && alone.length < trunkRatios.length;
    const midAlone = !trunk || !sharesRun(alongPolyline(trunkCorners, 0.5), trunkCorners);
    if (midAlone && !first.blocked && drift(first) <= CAPTION_NEAR && awayFromWire(first, automatic) <= CAPTION_BESIDE
        && !ontoWire(item, first, automatic) && !chipCrossesWire(item, {...first, side: automatic.side})
        && nearOwnWire(item, first, automatic.side, trunkCorners)) {
      return settle(first);
    }
    if (trunk) {
      for (const clearance of [PORT_CLEARANCE, 8, 4]) {
        const own = besideOnWire(item, trunkCorners, alone, clearance);
        if (own) return own;
      }
    }
    // A caption beside its wire before one pushed off it: along the whole
    // wire with full port room, then its middle with less (builders/
    // captions.py beside_wire). 11 px captions pushed more of them off than
    // 9 px ones did, and 16 to 24 px off reads as another wire's.
    {
      const corners = captionCorners(item);
      for (const [ratios, clearance] of [
        [[0.5, 0.3, 0.7, 0.15, 0.85, 0.4, 0.6], PORT_CLEARANCE], [[0.5, 0.3, 0.7], 8], [[0.5, 0.3, 0.7], 4],
      ]) {
        const along = besideOnWire(item, corners, ratios, clearance);
        if (along) return along;
      }
    }
    const corners = captionCorners(item);
    // Each nearer fallback holds only while the chip still stands within
    // CAPTION_REACH of its wire; past that, the caption goes on the wire.
    const firstNamed = nearOwnWire(item, first, automatic.side, corners);
    if (!first.blocked && drift(first) <= CAPTION_NEAR && firstNamed) return settle(first);
    // Nudged well off the wire to clear a card: before accepting that, look
    // for a spot elsewhere along the wire that needs no such nudge. A
    // caption belongs on its wire; which part of the wire matters less.
    for (const ratio of [0.5, 0.3, 0.7, 0.15, 0.85, 0.4, 0.6]) {
      const spot = besideWire(alongPolyline(corners, ratio));
      const nudged = keepEdgeLabelClearOfNodes(item, spot.x, spot.y, spot.side);
      if (!nudged.blocked && Math.hypot(nudged.x - spot.x, nudged.y - spot.y) <= CAPTION_NEAR
          && nearOwnWire(item, nudged, spot.side, corners)) {
        return {x: nudged.x, y: nudged.y, anchor: spot.anchor, side: spot.side};
      }
    }
    if (!first.blocked && drift(first) <= CAPTION_DRIFT && firstNamed) return settle(first);
    // Between two stacked glyphs the corridor is the wire's own length, so
    // full port clearance finds room only past the neighbour's caption band,
    // a hundred pixels from a thirty-pixel wire. Ask again with less room.
    for (const clearance of [8, 4]) {
      const closer = keepEdgeLabelClearOfNodes(item, automatic.x, automatic.y, automatic.side, clearance);
      if (!closer.blocked && drift(closer) <= CAPTION_DRIFT
          && nearOwnWire(item, closer, automatic.side, corners)) return settle(closer);
    }
    // Before settling far from the wire, try every point along it with less
    // port room: beside a short hop between stacked cards, a spot that keeps
    // 8 px off the ports still reads as the wire's caption; one nudged a
    // card's height away does not.
    for (const clearance of [8, 4]) {
      for (const ratio of [0.5, 0.3, 0.7]) {
        const spot = besideWire(alongPolyline(corners, ratio));
        const nudged = keepEdgeLabelClearOfNodes(item, spot.x, spot.y, spot.side, clearance);
        if (!nudged.blocked && Math.hypot(nudged.x - spot.x, nudged.y - spot.y) <= CAPTION_NEAR
            && nearOwnWire(item, nudged, spot.side, corners)) {
          return {x: nudged.x, y: nudged.y, anchor: spot.anchor, side: spot.side};
        }
      }
    }
    // Only a spot far off the wire is left: beside it, clear of what is drawn
    // alone, wins -- a numbered caption's 24 px chip on a 28 px hop between
    // stacked glyphs has no room for port clearance, and settled a hundred
    // pixels away on the frame's edge (builders/captions.py).
    {
      const tight = besideOnWire(item, corners, [0.5, 0.3, 0.7], 0) || onOwnWire(item, corners)
        || nearOwnWireSpot(item, corners);
      if (tight) return tight;
    }
    if (!first.blocked) return settle(first);
    for (const ratio of [0.5, 0.3, 0.7, 0.15, 0.85, 0.4, 0.6]) {
      const spot = besideWire(alongPolyline(corners, ratio));
      const nudged = keepEdgeLabelClearOfNodes(item, spot.x, spot.y, spot.side);
      if (!nudged.blocked) return {x: nudged.x, y: nudged.y, anchor: spot.anchor, side: spot.side};
    }
    // A wire too short to host a caption with port clearance -- a 24 px hop
    // between stacked nodes -- still has its gap. The drawn geometry is the
    // law and the port clearance a preference, so ask once more to stay off
    // what is drawn alone, rather than settle on the card the wire leaves.
    for (const ratio of [0.5, 0.3, 0.7]) {
      const spot = besideWire(alongPolyline(corners, ratio));
      const nudged = keepEdgeLabelClearOfNodes(item, spot.x, spot.y, spot.side, 0);
      if (!nudged.blocked) return {x: nudged.x, y: nudged.y, anchor: spot.anchor, side: spot.side};
    }
    return {x: first.x, y: first.y, anchor: automatic.anchor, side: automatic.side};
  };

  const resolvedEdgeLabel = item => {
    const placed = resolveEdgeLabel(item);
    if (collectingCaptions && item.edge.label) {
      placedCaptions.push(captionBoxAt(item, placed.x, placed.y, placed.side));
    }
    return placed;
  };

  const resolveEdgeLabel = item => {
    const automatic = automaticEdgeLabel(item);
    const placement = item.edge.labelPlacement;
    if (placement?.mode === 'manual'
        && Number.isFinite(Number(placement.dx))
        && Number.isFinite(Number(placement.dy))) {
      const adjusted = keepEdgeLabelClearOfNodes(
        item,
        automatic.x + Number(placement.dx),
        automatic.y + Number(placement.dy),
        automatic.side,
      );
      // Draw where the label fits, but keep what the author asked for:
      // writing the clamped offset back would let one crowded render pin a
      // label for good, and no nudge could ever move it off the card again.
      return {
        ...automatic,
        x: adjusted.x,
        y: adjusted.y,
        anchor: 'middle',
        side: 'horizontal',
        mode: 'manual',
      };
    }
    if (Number.isFinite(Number(item.edge.labelX))
        && Number.isFinite(Number(item.edge.labelY))) {
      const adjusted = keepEdgeLabelClearOfNodes(
        item,
        Number(item.edge.labelX),
        Number(item.edge.labelY),
        automatic.side,
      );
      item.edge.labelPlacement = {
        mode: 'manual',
        dx: adjusted.x - automatic.x,
        dy: adjusted.y - automatic.y,
      };
      delete item.edge.labelX;
      delete item.edge.labelY;
      return {
        ...automatic,
        x: adjusted.x,
        y: adjusted.y,
        anchor: 'middle',
        side: 'horizontal',
        mode: 'manual',
      };
    }
    // Captions draw above the cards now, so an automatic position that lands
    // on a card hides the card's title instead of being hidden by it. Nudge
    // it clear, the same way a hand-placed caption already was.
    const placed = bestAutomaticLabel(item, automatic);
    return {...automatic, ...placed, mode: 'auto'};
  };

  const edgeMarkup = item => {
    const colors = canvasPalette();
    const path = connectorPath(item);
    const selectedEdge = isEdgeSelected(item.edge.id);
    const basePaint = edgeThemeStroke(item.edge) || colors.wire;
    const paint = selectedEdge && !item.edge.style?.stroke ? colors.selectedWire : basePaint;
    const baseWidth = Number(item.edge.style?.width) || item.edge.width || 1.4;
    const width = selectedEdge ? Math.max(2.2, baseWidth) : baseWidth;
    const dashValue = edgeDash(item.edge);
    const dash = dashValue ? ` stroke-dasharray="${escapeText(dashValue)}"` : '';
    const markerId = `infragram-editor-arrow${EDGE_ARROWS[edgeArrow(item.edge)]}`
      + (selectedEdge ? '-selected' : '');
    const direction = edgeDirection(item.edge);
    const markers = (direction === 'none' ? '' : ` marker-end="url(#${markerId})"`)
      + (direction === 'both' ? ` marker-start="url(#${markerId})"` : '');
    // The flow a single click shows: its wires animate in the traffic's
    // direction, the others step back (04-model flowLit).
    const focused = Boolean(currentFlow?.edges.has(item.edge.id));
    const flowDimmed = Boolean(currentFlow && !focused);
    const reconnecting = connection?.edgeId === item.edge.id;
    const selectionHalo = selectedEdge && !reconnecting
      ? `<path data-edge-selection-halo d="${path}" fill="none" stroke="${colors.selection}" stroke-width="${width + 8}" stroke-opacity=".3"${dash} pointer-events="none"/>`
      : '';
    return `<g data-edge-group="${escapeText(item.edge.id)}"${reconnecting ? ' data-reconnecting="true" opacity=".3"' : ''}${flowDimmed ? ' data-focus-dimmed="true"' : ''}>
      ${selectionHalo}
      <path data-graph-edge data-edge-id="${escapeText(item.edge.id)}" data-focus-edge="${focused}" data-edge-direction="${direction}" data-source-x="${(item.sourceSeat || item.sourcePoint).x}" data-source-y="${(item.sourceSeat || item.sourcePoint).y}" data-target-x="${(item.targetSeat || item.targetPoint).x}" data-target-y="${(item.targetSeat || item.targetPoint).y}" d="${path}" fill="none" stroke="${escapeText(paint)}" stroke-width="${width}"${dash}${markers} pointer-events="stroke"/>
      <path class="edge-hit" data-edge-hit="${escapeText(item.edge.id)}" d="${path}" fill="none" stroke="transparent" stroke-width="${coarsePointer() ? 28 : 14}" vector-effect="non-scaling-stroke"/>
    </g>`;
  };

  // Captions draw in their own layer above the cards. A caption sits at the
  // midpoint of the gap between two cards and is usually wider than that gap,
  // so inside the edge layer it vanishes under whichever card it overhangs --
  // "CDC extract" renders as "ext". Above the cards it stays whole, and its
  // backing chip keeps it legible over a line or a frame border.
  const edgeLabelMarkup = item => {
    if (!item.edge.label) return '';
    const colors = canvasPalette();
    const selectedEdge = isEdgeSelected(item.edge.id);
    const labelPosition = resolvedEdgeLabel(item);
    const labelWidth = edgeLabelWidth(item.edge);
    const labelStyle = edgeTextStyle(item.edge);
    const lead = captionLead(item.edge);
    // Centred 4 px above the baseline, where the type's middle is.
    const maskHeight = captionHeight(item.edge);
    const maskY = -maskHeight / 2 - 4;
    const maskX = labelPosition.side === 'vertical' ? -4 : -labelWidth / 2 - lead;
    // beside a vertical wire the circle comes first and the text after it
    const textX = labelPosition.side === 'vertical' ? lead : 0;
    const step = edgeStep(item.edge);
    // The numbered circle sits in the chip's lead, left of the text, after
    // the text in the markup: the caption is the group's first text.
    const stepX = maskX + STEP.inset + STEP.radius;
    const stepY = -4;
    const mark = step ? stepMark(item.edge) : null;
    const stepShape = !mark ? ''
      : mark.shape === 'square'
        ? `<rect data-edge-step="${step}" data-cx="${stepX}" data-cy="${stepY}" x="${stepX - STEP.radius}" y="${stepY - STEP.radius}" width="${2 * STEP.radius}" height="${2 * STEP.radius}" rx="3" fill="${escapeText(mark.color)}" pointer-events="none"/>`
        : `<circle data-edge-step="${step}" cx="${stepX}" cy="${stepY}" r="${STEP.radius}" fill="${escapeText(mark.color)}" pointer-events="none"/>`;
    const stepMarkup = step
      ? `${stepShape}
           <text data-edge-step-number="${step}" x="${stepX}" y="${stepY + STEP.numberSize * 0.36}" fill="#ffffff" font-family="'${escapeText(labelStyle.fontFamily)}',sans-serif" font-size="${STEP.numberSize}" font-weight="700" text-anchor="middle" pointer-events="none">${stepMarkText(mark, step)}</text>`
      : '';
    return `<g data-edge-label="${escapeText(item.edge.id)}" data-edge-id="${escapeText(item.edge.id)}" data-placement-mode="${labelPosition.mode}" data-label-x="${labelPosition.x}" data-label-y="${labelPosition.y}" data-selected="${selectedEdge}"${currentFlow && !currentFlow.edges.has(item.edge.id) ? ' data-focus-dimmed="true"' : ''} transform="translate(${labelPosition.x} ${labelPosition.y})" role="button" aria-label="Move connector label ${escapeText(item.edge.label)}">
           <rect class="edge-label-mask" x="${maskX}" y="${maskY}" width="${labelWidth + lead}" height="${maskHeight}" rx="3" fill="${colors.card}" stroke="${selectedEdge ? colors.accent : colors.border}" data-chip-stroke="${colors.border}" stroke-width="1" pointer-events="all"/>
           <text x="${textX}" y="0" fill="${escapeText(labelStyle.textColor)}" fill-opacity="${Number(labelStyle.opacity) / 100}" font-family="'${escapeText(labelStyle.fontFamily)}',${monoFace(labelStyle.fontFamily) ? 'monospace' : 'sans-serif'}" font-size="${Number(labelStyle.fontSize)}" font-weight="${escapeText(String(labelStyle.fontWeight))}" letter-spacing="${monoFace(labelStyle.fontFamily) ? '0.08em' : '0'}" text-anchor="${labelPosition.anchor}" pointer-events="none">${escapeText(item.edge.label)}</text>
           ${stepMarkup}
         </g>`;
  };

