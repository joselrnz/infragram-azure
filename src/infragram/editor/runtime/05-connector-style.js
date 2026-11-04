// @module 05-connector-style: connector kinds, directions, arrowheads, corners and text defaults
  // Connector appearance. ``kind`` picks the stroke pattern, ``direction`` the
  // arrowheads; a dash stored on the edge (theme link styles) wins over the kind.
  const EDGE_DASHES = {dashed: METRICS.link_dashes.dashed, dotted: METRICS.link_dashes.dotted};
  // A theme names its own link kinds and gives each a colour, width and dash:
  // the AWS deck calls a private circuit "vif" and a tunnel "vpn". The static
  // renderer read that table and this runtime did not, so one document drew a
  // red tunnel in the fallback picture and a grey one in the real export.
  const LINK_STYLES = (() => {
    const tag = document.getElementById('infragram-link-styles');
    if (!tag) return {};
    try { return JSON.parse(tag.textContent) || {}; } catch (error) { return {}; }
  })();
  const linkStyle = kind => LINK_STYLES[kind] || null;
  // What the theme says this wire is painted, or nothing when it says nothing
  // and the workspace ink decides.
  const edgeThemeStroke = edge => {
    if (edge.style?.stroke) return edge.style.stroke;
    return linkStyle(edge.kind)?.color || '';
  };
  //: Arrowhead shapes. The name is what the inspector shows; the value is
  //: the marker id suffix, so "triangle" keeps the original marker.
  const EDGE_ARROWS = {triangle: '', open: '-open', circle: '-circle', diamond: '-diamond'};
  // How a wire turns a corner: the bend table from render-metrics.json, the
  // same one the Python renderer reads. Legs stay horizontal and vertical.
  const CORNERS = METRICS.router.corners || {default: 'sharp', rounded: METRICS.router.radius, sharp: 0, curved: 48};
  const EDGE_CORNERS = Object.keys(CORNERS).filter(key => key !== 'default' && key !== 'note');
  const edgeCorners = edge => (EDGE_CORNERS.includes(edge?.style?.corners) ? edge.style.corners : CORNERS.default);
  const cornerRadius = edge => Number(CORNERS[edgeCorners(edge)]);
  const ARROWHEADS = (() => {
    const tag = document.getElementById('infragram-arrowheads');
    if (!tag) throw new Error('infragram editor: the arrowhead spec is missing from the page');
    return JSON.parse(tag.textContent);
  })();
  // Byte for byte what builders/arrowheads.py writes for the static picture.
  const markerMarkup = (id, name, paint) => {
    const head = ARROWHEADS.heads[name] || ARROWHEADS.heads[ARROWHEADS.default];
    return `<marker id="${id}" markerUnits="userSpaceOnUse" markerWidth="${head.length}" markerHeight="${head.width}" refX="${head.length - Number(ARROWHEADS.tip_clear || 0)}" refY="${head.width / 2}" orient="auto-start-reverse">${head.markup.split('{paint}').join(paint)}</marker>`;
  };
  //: A connector label names a protocol, a port or a step: 11 px regular on
  //: a white chip reads at a glance and stays quieter than the card titles
  //: (builders/captions.py CAPTION_SIZE and CAPTION_WEIGHT).
  const EDGE_TEXT_DEFAULTS = {
    fontFamily: 'Inter', fontSize: 11, fontWeight: 400, opacity: 100,
  };
  //: A monospaced face is set with a little tracking and measured wider.
  const monoFace = family => /mono/i.test(String(family || ''));
  //: The faces a drawing saved before Inter set every label: no page carries
  //: them now, so a label that names one is drawn in Inter.
  const RETIRED_FACES = new Set(['Roboto', 'Geist']);
  const withCurrentFace = style => (RETIRED_FACES.has(style.fontFamily) ? {...style, fontFamily: 'Inter'} : style);
  const edgeArrow = edge => (
    Object.hasOwn(EDGE_ARROWS, edge.style?.arrow) ? edge.style.arrow : 'triangle'
  );
  const edgeTextStyle = edge => withCurrentFace({
    ...EDGE_TEXT_DEFAULTS,
    // The canvas text colour on either canvas: grey read as dim.
    textColor: canvasPalette().text,
    ...(edge.style?.textStyle || {}),
  });
  const EDGE_KINDS = ['solid', 'dashed', 'dotted'];
  const EDGE_DIRECTIONS = ['forward', 'both', 'none'];
  const edgeDash = edge => edge.dash || linkStyle(edge.kind)?.dash || EDGE_DASHES[edge.kind] || '';
  const edgeDirection = edge => (EDGE_DIRECTIONS.includes(edge.direction) ? edge.direction : 'forward');
  // Which ends of a wire carry a head, so the path can keep a straight
  // shaft under each one.
  const edgeHeads = edge => {
    const direction = edgeDirection(edge);
    return {start: direction === 'both', end: direction !== 'none'};
  };
