// @module 32-iso3d: the 3D builder: a recipe and its knobs, rendered in this page
  const iso3dVocabulary = (() => {
    try { return JSON.parse(document.getElementById('infragram-iso3d-vocabulary')?.textContent || 'null'); }
    catch (_) { return null; }
  })();
  const ISO_PX = 192;
  const ISO_EDGE_LEVELS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  // the shipped measurer, verbatim from the package, so both agree
  const isoMeasureAll = iso3dVocabulary && iso3dVocabulary.measure
    ? new Function(`return (${iso3dVocabulary.measure});`)() : null;
  const isoSortedJson = value => JSON.stringify(value, (key, item) => (
    item && typeof item === 'object' && !Array.isArray(item)
      ? Object.fromEntries(Object.keys(item).sort().map(name => [name, item[name]])) : item));
  // this page's own key for a render: two FNV-1a passes over the sorted spec
  const isoHash = text => {
    let a = 0x811c9dc5, b = 0x050c5d1f;
    for (let i = 0; i < text.length; i += 1) {
      const code = text.charCodeAt(i);
      a = Math.imul(a ^ code, 0x01000193) >>> 0;
      b = Math.imul(b ^ code, 0x0100019b) >>> 0;
    }
    return a.toString(16).padStart(8, '0') + b.toString(16).padStart(8, '0');
  };
  const isoWrap = png => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${ISO_PX} ${ISO_PX}" aria-hidden="true"><image width="${ISO_PX}" height="${ISO_PX}" href="${png}"/></svg>\n`;
  // the 768 px render down to the shipped 192 px, halving with smoothing on the way
  const isoDownscale = async uri => {
    const image = new Image();
    await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = () => reject(new Error('the render did not load')); image.src = uri; });
    let source = image, size = image.naturalWidth;
    while (size > ISO_PX * 2) {
      const half = document.createElement('canvas'); half.width = half.height = size / 2;
      const context = half.getContext('2d'); context.imageSmoothingEnabled = true; context.imageSmoothingQuality = 'high';
      context.drawImage(source, 0, 0, size / 2, size / 2);
      source = half; size /= 2;
    }
    const out = document.createElement('canvas'); out.width = out.height = ISO_PX;
    const context = out.getContext('2d'); context.imageSmoothingEnabled = true; context.imageSmoothingQuality = 'high';
    context.drawImage(source, 0, 0, ISO_PX, ISO_PX);
    return out.toDataURL('image/png');
  };
  // measure.summarise / entries_for: the box insets and the edge lines, encoded as the table stores them
  const isoRoundHalfEven = value => { const floor = Math.floor(value); const rest = value - floor; return rest > 0.5 ? floor + 1 : rest < 0.5 ? floor : (floor % 2 === 0 ? floor : floor + 1); };
  const isoSummarise = edges => {
    const size = Number(iso3dVocabulary?.size) || 128;
    const box = [], parts = [];
    for (const side of ['left', 'right', 'top', 'bottom']) {
      const depths = edges[side];
      const hits = depths.filter(depth => depth !== -1).map(depth => (depth >= 0 ? depth : -2 - depth));
      box.push(hits.length ? Math.round(Math.min(...hits) / size * 1000) / 1000 : 0);
      parts.push(depths.map(depth => (depth < 0 ? '.' : ISO_EDGE_LEVELS[Math.min(ISO_EDGE_LEVELS.length - 1, isoRoundHalfEven(depth * 64 / size))])).join(''));
    }
    const code = parts.join('|');
    return {profile: Math.max(...box) > 0.02 ? box : null, edges: /[^A|]/.test(code) ? code : null};
  };
  const renderIsoSpec = async spec => {
    if (!window.iso3d) throw new Error('this page carries no 3D renderer');
    const big = await window.iso3d.render(spec);
    const png = await isoDownscale(big);
    const svg = isoWrap(png);
    const uri = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    const measured = isoMeasureAll ? await isoMeasureAll([['item', uri]]) : {};
    const ink = measured.item ? isoSummarise(measured.item) : {profile: null, edges: null};
    return {svg, uri, ink, hash: isoHash(isoSortedJson(spec))};
  };
  const isoViewportCentre = () => {
    const origin = canvasOrigin();
    return {
      x: clamp((viewport.scrollLeft + viewport.clientWidth / 2 - origin.x) / zoom, 0, state.canvas.width),
      y: clamp((viewport.scrollTop + viewport.clientHeight / 2 - origin.y) / zoom, 0, state.canvas.height),
    };
  };
  const addIsoNode = (spec, render, caption = {}) => {
    const shipped = (libraryCatalog.components || []).find(item => item.id === 'custom-3d' && item.provider === 'infragram');
    const component = {
      ...(shipped || {id: 'custom-3d', provider: 'infragram', qualifiedId: 'infragram:custom-3d', name: '3D render', category: 'custom', tier: 'service', componentKind: 'node'}),
      name: caption.name || spec.recipe, detail: caption.detail || '', defaultDisplay: 'icon', iconUri: render.uri,
    };
    const id = addNode(component, caption.point || isoViewportCentre());
    const node = state.nodes.find(item => item.id === id);
    if (!node) return null;
    node.displayMode = 'icon';
    node.iconUri = render.uri;
    node.ink = render.ink.profile || [];
    node.inkEdges = render.ink.edges || '';
    node.attributes = {...(node.attributes || {}), iso: spec, iso_hash: render.hash, iso_artwork: render.svg, iso_ink: {profile: render.ink.profile, edges: render.ink.edges}};
    node.width = iconNodeWidth({name: node.name, detail: node.detail});
    node.height = ICON_NODE.height;
    persist();
    renderGraph();
    return node.id;
  };
  const isoPanel = document.querySelector('[data-iso-builder]');
  if (isoPanel && !window.iso3d) {
    isoPanel.parentElement?.querySelector('[data-iso-unavailable]')?.removeAttribute('hidden');
    isoPanel.hidden = true;
  }
  if (isoPanel && window.iso3d && iso3dVocabulary) {
    const recipeSelect = isoPanel.querySelector('[data-iso-recipe]');
    const knobBox = isoPanel.querySelector('[data-iso-knobs]');
    const familySelect = isoPanel.querySelector('[data-iso-family]');
    const colourInput = isoPanel.querySelector('[data-iso-colour]');
    const glyphSelect = isoPanel.querySelector('[data-iso-glyph]');
    const previewButton = isoPanel.querySelector('[data-iso-preview]');
    const addButton = isoPanel.querySelector('[data-iso-add]');
    const previewImage = isoPanel.querySelector('[data-iso-preview-image]');
    const statusLine = isoPanel.querySelector('[data-iso-status]');
    [...window.iso3d.recipes].sort().forEach(name => recipeSelect.append(new Option(name, name)));
    Object.entries(iso3dVocabulary.families).forEach(([name, colour]) => familySelect.append(new Option(`${name} ${colour}`, name)));
    glyphSelect.append(new Option('family glyph', ''));
    glyphSelect.append(new Option('no badge', '-'));
    Object.keys(iso3dVocabulary.glyphs).sort().forEach(name => glyphSelect.append(new Option(name, name)));
    const knobInput = knob => {
      const field = document.createElement('label'); field.className = 'iso-builder-knob';
      const text = document.createElement('span'); text.textContent = knob.name; field.append(text);
      const input = document.createElement('input');
      const kind = typeof knob.default === 'boolean' ? 'boolean' : typeof knob.default === 'number' ? 'number' : 'text';
      if (kind === 'boolean') { input.type = 'checkbox'; input.checked = Boolean(knob.default); }
      else if (kind === 'number') { input.type = 'number'; input.step = 'any'; input.value = String(knob.default); }
      else { input.type = 'text'; input.value = knob.default == null ? '' : String(knob.default); }
      input.dataset.isoKnob = knob.name; input.dataset.isoKind = kind;
      field.append(input);
      return field;
    };
    const readKnobs = () => Array.from(knobBox.querySelectorAll('[data-iso-knob]')).map(input => (
      input.dataset.isoKind === 'boolean' ? input.checked : input.dataset.isoKind === 'number' ? Number(input.value) : input.value));
    // infragram.iso3d.api.build_spec, in the page: the knobs in order with the trailing defaults dropped
    const specFromPanel = () => {
      const recipe = recipeSelect.value;
      const knobs = window.iso3d.knobs(recipe);
      const args = readKnobs();
      while (args.length && JSON.stringify(args[args.length - 1]) === JSON.stringify(knobs[args.length - 1].default)) args.pop();
      const family = familySelect.value;
      const colourText = colourInput.value.trim();
      const colour = /^#[0-9a-fA-F]{6}$/.test(colourText) ? colourText.toLowerCase() : iso3dVocabulary.families[family];
      const glyphName = glyphSelect.value === '' ? iso3dVocabulary.familyGlyph[family] : glyphSelect.value === '-' ? null : glyphSelect.value;
      const glyph = glyphName ? (iso3dVocabulary.glyphs[glyphName] || []).join('|') : '';
      return {id: `${recipe}:${JSON.stringify(args)}`, recipe, args, kwargs: {}, colour, glyph};
    };
    let lastRender = null;
    const stale = () => { lastRender = null; addButton.disabled = true; };
    const fillKnobs = () => { knobBox.replaceChildren(...window.iso3d.knobs(recipeSelect.value).map(knobInput)); stale(); };
    if (window.iso3d.recipes.includes('server')) recipeSelect.value = 'server';
    recipeSelect.addEventListener('change', fillKnobs);
    fillKnobs();
    [knobBox, familySelect, colourInput, glyphSelect].forEach(control => control.addEventListener('input', stale));
    previewButton.addEventListener('click', async () => {
      previewButton.disabled = true;
      statusLine.textContent = 'Rendering...';
      try {
        const spec = specFromPanel();
        const render = await renderIsoSpec(spec);
        lastRender = {spec, render};
        previewImage.src = render.uri; previewImage.hidden = false;
        addButton.disabled = false;
        statusLine.textContent = render.ink.edges ? 'Rendered and measured: links will seat on it.' : 'Rendered.';
      } catch (error) {
        stale();
        statusLine.textContent = `Could not render: ${error && error.message ? error.message : error}`;
      } finally {
        previewButton.disabled = false;
      }
    });
    addButton.addEventListener('click', () => {
      if (!lastRender) return;
      const name = isoPanel.querySelector('[data-iso-name]').value.trim() || recipeSelect.value;
      const detail = isoPanel.querySelector('[data-iso-detail]').value.trim();
      const id = addIsoNode(lastRender.spec, lastRender.render, {name, detail});
      statusLine.textContent = id ? `${name} added; it carries its spec, artwork and ink.` : 'Could not add the item.';
    });
  }
  // A preset paints what the canvas draws by default in the current theme:
  // the card fill and the border, accent, muted or danger ink from the
  // workspace tokens, so "Neutral" on the light canvas is a white card, not
  // the near-black one a dark palette would give.
