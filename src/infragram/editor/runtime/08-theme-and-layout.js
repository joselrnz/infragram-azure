// @module 08-theme-and-layout: status line, canvas palette, theme, inspector collapse, text editing entry
  // Every action reports what it did. Screen readers hear it through the live
  // region; everyone sees it in a snackbar for a few seconds. The status line
  // it used to reach left the header, and the messages had been reaching no
  // one on screen since -- "Locked layer · ..." included. Routine reports that
  // would flicker while typing or dragging (search counts, selection counts,
  // a component moved) are announced but not shown.
  const snackbar = document.querySelector('[data-snackbar]');
  let snackbarTimer = 0;
  let statusShown = false;
  const showSnackbar = message => {
    if (!snackbar || !statusShown) return;
    const box = viewport.getBoundingClientRect();
    snackbar.textContent = message;
    snackbar.style.left = `${Math.round(box.left + box.width / 2)}px`;
    snackbar.style.bottom = `${Math.round(window.innerHeight - box.bottom + 16)}px`;
    snackbar.hidden = true;
    void snackbar.offsetWidth;
    snackbar.hidden = false;
    clearTimeout(snackbarTimer);
    snackbarTimer = setTimeout(() => { snackbar.hidden = true; }, 4000);
  };
  const setStatus = (message, {show = true} = {}) => {
    if (status) status.textContent = message;
    if (show) showSnackbar(message);
  };
  const canvasPalette = () => {
    const styles = getComputedStyle(document.body);
    const color = name => styles.getPropertyValue(name).trim();
    return {
      card: color('--card-bg'), control: color('--control-bg'), text: color('--text-canvas'),
      secondary: color('--text-secondary'), border: color('--border-color'),
      wire: color('--wire-color'), selectedWire: color('--wire-selected'),
      handle: color('--handle-color'), accent: color('--accent'),
      accentMuted: color('--accent-muted'), error: color('--error-color'),
      canvas: color('--canvas-bg'),
      // the chrome's accent, for what marks a selection on the canvas: it is
      // editor chrome, never saved, so it follows the theme, not the drawing
      selection: color('--md-sys-color-primary'),
    };
  };
  // Artwork drawn in a dark ink -- the built-in line icons, a black vendor
  // mark -- all but vanishes on a dark canvas. On a dark theme such an icon
  // is drawn through INK_ON_DARK, which turns its lightness over and keeps
  // its hue: black reads white and a dark slate a light one, while colourful
  // artwork is left as its vendor drew it. Whether artwork is dark is
  // measured once per icon in this page -- rasterised, the mean luminance of
  // its opaque pixels -- so an icon added later is judged the same way.
  const INK_ON_DARK = 'infragram-ink-on-dark';
  const INK_ON_DARK_FILTER = `<filter id="${INK_ON_DARK}" color-interpolation-filters="sRGB">`
    + '<feColorMatrix type="matrix" values="-1 0 0 0 1 0 -1 0 0 1 0 0 -1 0 1 0 0 0 1 0"/>'
    + '<feColorMatrix type="hueRotate" values="180"/></filter>';
  //: Below this mean relative luminance, ink cannot hold 3:1 against a dark canvas.
  const DARK_INK_LUMINANCE = 0.12;
  const inkIsDark = new Map();
  const inkMeasures = new Map();
  const measureInk = uri => {
    if (!inkMeasures.has(uri)) {
      inkMeasures.set(uri, new Promise(resolve => {
        const settle = dark => { inkIsDark.set(uri, dark); resolve(dark); };
        const image = new Image();
        image.onerror = () => settle(false);
        image.onload = () => {
          let dark = false;
          try {
            const size = 48;
            const canvas = document.createElement('canvas');
            canvas.width = size;
            canvas.height = size;
            const context = canvas.getContext('2d', {willReadFrequently: true});
            context.drawImage(image, 0, 0, size, size);
            const pixels = context.getImageData(0, 0, size, size).data;
            const linear = value => {
              const channel = value / 255;
              return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
            };
            let total = 0;
            let count = 0;
            for (let index = 0; index < pixels.length; index += 4) {
              if (pixels[index + 3] < 128) continue;
              total += 0.2126 * linear(pixels[index]) + 0.7152 * linear(pixels[index + 1])
                + 0.0722 * linear(pixels[index + 2]);
              count += 1;
            }
            dark = count > 0 && total / count < DARK_INK_LUMINANCE;
          } catch (_) { /* artwork the canvas will not read back is left as drawn */ }
          settle(dark);
        };
        image.src = uri;
      }));
    }
    return inkMeasures.get(uri);
  };
  const darkCanvas = () => document.body.dataset.workspaceTheme === 'dark';
  // The filter an icon is drawn through: none on a light canvas, none for
  // artwork that reads, and none until its ink is known (which then redraws).
  // One redraw however many measurements land in a frame, and one waiting
  // measurement per artwork: a render while measurements are still out must
  // not queue a redraw per call, or a page that opens dark on many dark-ink
  // icons redraws without end.
  let inkRedraw = 0;
  const inkFilter = uri => {
    if (!uri || !darkCanvas()) return '';
    if (!inkIsDark.has(uri)) {
      if (!inkMeasures.has(uri)) {
        measureInk(uri).then(dark => {
          if (!dark || !darkCanvas() || inkRedraw) return;
          inkRedraw = requestAnimationFrame(() => { inkRedraw = 0; renderGraph(); });
        });
      }
      return '';
    }
    return inkIsDark.get(uri) ? ` filter="url(#${INK_ON_DARK})"` : '';
  };
  // The palette offers three themes. Darker is the dark theme on neutral
  // near-black surfaces: it keeps data-workspace-theme="dark", so every rule
  // and every canvas behaviour written for dark still holds, and adds a
  // palette attribute whose tokens override the surfaces.
  const workspaceThemes = {light: 'Light', dark: 'Dark', darker: 'Darker'};
  const themeMenu = document.querySelector('[data-theme-menu]');
  const applyWorkspaceTheme = theme => {
    const palette = Object.hasOwn(workspaceThemes, theme) ? theme : 'dark';
    document.body.dataset.workspaceTheme = palette === 'light' ? 'light' : 'dark';
    document.body.dataset.workspacePalette = palette;
    themeToggle.setAttribute('aria-label', `Theme: ${workspaceThemes[palette]}`);
    themeToggle.title = `Theme: ${workspaceThemes[palette]}`;
    themeMenu?.querySelectorAll('[data-theme-choice]').forEach(choice => {
      choice.setAttribute('aria-checked', String(choice.dataset.themeChoice === palette));
    });
  };
  // Diagrams are read on white: printed, pasted into a document, exported
  // to PNG. Opening dark meant the first look at a drawing was in a theme
  // the finished artwork is never seen in, so light is the default. The
  // toggle still remembers whatever the reader picks.
  let savedTheme = document.body.dataset.workspaceTheme || 'light';
  try { savedTheme = localStorage.getItem(themeStorageKey) || savedTheme; } catch (_) { /* file privacy modes */ }
  // ?theme=light|dark|darker opens the workspace in that theme for this visit
  // only: exporters and shared links get white cards on light without
  // touching the preference the browser saved.
  const requestedTheme = (workspaceParams.get('theme') || '').toLowerCase();
  applyWorkspaceTheme(Object.hasOwn(workspaceThemes, requestedTheme) ? requestedTheme : savedTheme);
  // The palette menu is a <details>, like Download: choosing a theme closes
  // it, and so do a press anywhere else and Escape.
  themeMenu?.addEventListener('click', event => {
    const choice = event.target.closest('[data-theme-choice]');
    if (!choice) return;
    themeMenu.open = false;
    const next = choice.dataset.themeChoice;
    applyWorkspaceTheme(next);
    try { localStorage.setItem(themeStorageKey, next); } catch (_) { /* file privacy modes */ }
    renderGraph();
    setStatus(`${workspaceThemes[next]} workspace theme`);
  });
  document.addEventListener('pointerdown', event => {
    if (themeMenu?.open && !themeMenu.contains(event.target)) themeMenu.open = false;
  });
  themeMenu?.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !themeMenu.open) return;
    themeMenu.open = false;
    themeToggle.focus();
  });
  let layoutState = {inspectorCollapsed: false, bottomExpanded: false};
  try {
    layoutState = {...layoutState, ...JSON.parse(localStorage.getItem(layoutStorageKey) || '{}')};
  } catch (_) { /* malformed or unavailable local storage */ }
  const persistLayout = () => {
    try { localStorage.setItem(layoutStorageKey, JSON.stringify(layoutState)); }
    catch (_) { /* file privacy modes */ }
  };
  // Where the inspector lies over the drawing -- a phone's sheet, a tablet's
  // panel -- it starts closed whatever a wider screen last left, and opening
  // it there is not remembered for the wider one.
  const setInspectorCollapsed = collapsed => {
    const value = Boolean(collapsed);
    document.body.classList.toggle('inspector-collapsed', value);
    inspector.dataset.collapsed = String(value);
    inspectorToggle.setAttribute('aria-expanded', String(!value));
    inspectorToggle.setAttribute('aria-label', value ? 'Expand inspector' : 'Collapse inspector');
    inspectorToggle.title = inspectorToggle.getAttribute('aria-label');
    if (inspectorOverlays()) return;
    layoutState.inspectorCollapsed = value;
    persistLayout();
  };
  setInspectorCollapsed(inspectorOverlays() || layoutState.inspectorCollapsed);
  inspectorToggle.addEventListener('click', () => {
    // a phone's sheet takes its room from the drawing, which stays where it
    // is (19-canvas-pointer setSheetCollapsed); a wider page refits
    if (phoneLayout()) leaveFitMode();
    setInspectorCollapsed(!document.body.classList.contains('inspector-collapsed'));
    if (!phoneLayout()) requestAnimationFrame(() => fitZoom());
  });
  const setBottomExpanded = expanded => {
    if (!expanded) document.body.classList.remove('welcome-examples-open');
    layoutState.bottomExpanded = Boolean(expanded);
    bottomDrawer.dataset.expanded = String(layoutState.bottomExpanded);
    bottomToggle.setAttribute('aria-expanded', String(layoutState.bottomExpanded));
    bottomToggle.setAttribute(
      'aria-label', layoutState.bottomExpanded ? 'Collapse diagram library' : 'Expand diagram library',
    );
    bottomToggle.title = bottomToggle.getAttribute('aria-label');
    persistLayout();
  };
  setBottomExpanded(layoutState.bottomExpanded);
  bottomToggle.addEventListener('click', () => {
    setBottomExpanded(!layoutState.bottomExpanded);
    requestAnimationFrame(() => fitZoom());
  });
  // A drawer tab shows its panel, and opens the drawer if it was closed.
  document.querySelector('[data-welcome-examples]')?.addEventListener('click', () => {
    if (phoneLayout()) document.body.classList.add('welcome-examples-open');
    document.querySelector('[data-bottom-tab="examples"]')?.click();
  });
  document.querySelectorAll('[data-bottom-tab]').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.bottomTab;
      document.querySelectorAll('[data-bottom-tab]').forEach(item => {
        item.setAttribute('aria-selected', String(item === tab));
      });
      // only the drawer's own: the inventory docked beside the map keeps showing
      document.querySelectorAll('[data-bottom-drawer] [data-bottom-panel]').forEach(panel => {
        panel.hidden = panel.dataset.bottomPanel !== target;
      });
      // the Resources table is taller than the shelf (drawer.css)
      const drawer = document.querySelector('[data-bottom-drawer]');
      if (drawer) drawer.dataset.panel = target;
      if (!layoutState.bottomExpanded) setBottomExpanded(true);
    });
  });
  const openTextEditor = (item, type) => {
    if (!item || !['node', 'boundary', 'edge'].includes(type)) return;
    if (type === 'node') selectNode(item.id);
    else if (type === 'boundary') selectBoundary(item.id);
    else selectEdge(item.id);
    setInspectorCollapsed(false);
    document.querySelector('[data-inspector-tab="text"]').click();
    renderGraph();
    requestAnimationFrame(() => {
      const input = type === 'edge'
        ? document.querySelector('[data-edge-label-control="label"]')
        : document.querySelector('[data-content-control="name"]');
      input?.focus();
      input?.select();
    });
    setStatus(`${type === 'edge' ? (item.label || 'Connector label') : item.name} ready to edit`);
  };
  const uniqueId = base => {
    const stem = String(base || 'component').toLocaleLowerCase()
      .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'component';
    let candidate = stem;
    let suffix = 2;
    while (nodeById(candidate) || boundaryById(candidate)) candidate = `${stem}-${suffix++}`;
    return candidate;
  };
