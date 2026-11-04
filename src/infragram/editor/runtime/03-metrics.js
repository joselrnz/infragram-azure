// @module 03-metrics: geometry shared with the Python renderer: icons, arrowheads, frames, the mark
  // Icon display geometry. Mirrors NodeStyle.icon_* in builders/scene.py so a
  // card the renderer sized and one the editor switched agree.
  // A bare glyph next to a 208 px card: 64 px of artwork, a name and a
  // subtitle, in a node that reads at the same weight as the card beside it.
  // The house arrowheads, from the one spec the page carries
  // (assets/catalog/arrowheads.json, written into the page by the editor
  // shell): a head is a fixed size whatever the stroke, its tip sits on the
  // node's edge, and `shaft` is the straight wire kept under it. The static
  // renderer and the checker read the same file, so no number lives here.
  // The numbers the static renderer and this one must agree on. They live in
  // assets/catalog/render-metrics.json and the shell writes them into the
  // page; before that they were typed out in both places and had drifted.
  const METRICS = (() => {
    const tag = document.getElementById('infragram-render-metrics');
    if (!tag) throw new Error('infragram editor: the render metrics are missing from the page');
    return JSON.parse(tag.textContent);
  })();

  // The badge tab: the same numbers builders/frame_style.py reads.
  const FRAME = Object.freeze(METRICS.frame
    ? {tab: METRICS.frame.tab, iconInset: METRICS.frame.icon_inset, labelGap: METRICS.frame.label_gap, baselineDivisor: METRICS.frame.baseline_divisor}
    : {tab: 20, iconInset: 2, labelGap: 5, baselineDivisor: 2.8});
  // Frame lines (the Diagram panel): what every frame's own width is drawn
  // at a multiple of, the numbers builders/scene.py FRAME_LINES reads.
  const FRAME_LINES = Object.freeze({thin: 1, ...(METRICS.frame?.line_scales || {})});
  // The provider mark's band below the drawing, the same numbers the Python
  // layout reserves.
  const MARK = Object.freeze(METRICS.mark
    ? {gap: METRICS.mark.gap, height: METRICS.mark.height}
    : {gap: 16, height: 40});
  // A wire's step: its circle in the caption's chip, and the step list.
  const STEP = Object.freeze({
    lead: METRICS.step.lead, radius: METRICS.step.radius, inset: METRICS.step.inset,
    numberSize: METRICS.step.number_size, chip: METRICS.step.chip, listGap: METRICS.step.list_gap,
  });
  const ICON_NODE = Object.freeze({width: METRICS.icon_node.width, height: METRICS.icon_node.height, glyph: METRICS.icon_node.glyph, glyphTop: Number.isFinite(METRICS.icon_node.glyph_top) ? METRICS.icon_node.glyph_top : 4, captionMinHeight: METRICS.icon_node.caption_min_height, maxWidth: METRICS.icon_node.max_width});
  // a card's height in both renderers (render-metrics.json card.height)
  const CARD_HEIGHT = Number.isFinite(METRICS.card?.height) ? METRICS.card.height : 64;
  // An icon node is as wide as its caption needs, within reason, so a name
  // like "Amazon CloudTrail" is read whole rather than as "Amazon CloudTra…".
  // Mirrors Node.resolve() for icon display in builders/scene.py.
  const iconNodeWidth = node => {
    const caption = Math.max(String(node.name || '').length * 12 * 0.58,
      String(node.detail || '').length * 5.8) + 16;
    return Math.min(ICON_NODE.maxWidth, Math.max(ICON_NODE.width, Math.ceil(caption / 4) * 4));
  };
