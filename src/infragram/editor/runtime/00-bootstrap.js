// @module 00-bootstrap: the page's elements, the inflated library and the editor's mutable state
(async () => {
  // A document written in place (document.open, as a test or a tool reopening an export does) keeps its
  // window, so the previous page's editor would still answer here until this one is published.
  delete window.infragramEditor;
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const diagram = document.querySelector('[data-infragram-diagram]');
  const viewport = document.querySelector('.canvas-viewport');
  const stage = document.querySelector('.diagram-stage');
  const layer = diagram.querySelector('[data-graph-layer]');
  const sidebar = document.querySelector('[data-testid="provider-sidebar"]');
  const sidebarLogoTrigger = document.querySelector('[data-sidebar-logo-trigger]');
  const search = document.querySelector('[data-sidebar-search]');
  const status = document.querySelector('[data-search-status]');
  const contextMenu = document.querySelector('[data-canvas-context-menu]');
  // The library payload is the bulk of the page and travels deflated;
  // the browser inflates it before anything else comes up.
  const readEmbeddedJson = async element => {
    const encoding = element.dataset.encoding || '';
    if (!encoding) return JSON.parse(element.textContent);
    if (encoding !== 'deflate-raw;base64') throw new Error(`unknown payload encoding ${encoding}`);
    if (typeof DecompressionStream === 'undefined') {
      throw new Error('this browser cannot inflate the page\'s library; open it in a current browser');
    }
    const bytes = Uint8Array.from(atob(element.textContent.trim()), character => character.charCodeAt(0));
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
    return JSON.parse(await new Response(stream).text());
  };
  const libraryElement = document.querySelector('#infragram-library-catalog');
  const libraryCatalog = await readEmbeddedJson(libraryElement);
  const providerMenuTrigger = document.querySelector('[data-provider-menu-trigger]');
  const providerMenu = document.querySelector('[data-provider-menu]');
  const providerOptions = [...document.querySelectorAll('[data-provider-option]')];
  const providerApply = document.querySelector('[data-provider-apply]');
  const providerSummary = document.querySelector('[data-provider-summary]');
  const providerById = new Map(libraryCatalog.providers.map(provider => [provider.id, provider]));
  let providerSelection = new Set(libraryCatalog.selectedProviders);
  let pendingProviderSelection = new Set(providerSelection);
  let previousCatalogQuery = '';
  const themeToggle = document.querySelector('[data-theme-toggle]');
  const inspector = document.querySelector('[data-right-inspector]');
  const inspectorToggle = document.querySelector('[data-inspector-toggle]');
  const bottomDrawer = document.querySelector('[data-bottom-drawer]');
  const bottomToggle = document.querySelector('[data-bottom-toggle]');
  // The chrome's glyphs, drawn like the shell's (editor/shell.py): 24 units,
  // a 1.5 stroke. A lock shows a closed shackle when locked, an open one not.
  const chromeIcon = (paths, extra = '') => `<svg class="md-icon${extra ? ` ${extra}` : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths}</svg>`;
  const lockIcon = locked => chromeIcon(`<rect x="5" y="11" width="14" height="9" rx="2"/><path d="${locked ? 'M8 11V8a4 4 0 0 1 8 0v3' : 'M8 11V8a4 4 0 0 1 7.7-1.5'}"/>`);
  const expandIcon = () => chromeIcon('<path d="m6 9 6 6 6-6"/>', 'md-expand-icon');
  const categories = [...document.querySelectorAll('details[data-category-id]')];
  const originalProject = JSON.parse(document.querySelector('#infragram-project').textContent);
  const stateElement = document.querySelector('#infragram-editor-state');
  const generatedState = JSON.parse(stateElement.textContent);
  let state = generatedState;
  let selected = null;
  let selectedNodeIds = new Set();
  let selectedBoundaryIds = new Set();
  let selectedEdgeIds = new Set();
  let drag = null;
  let connection = null;
  let alignmentGuides = [];
  let marqueeSelection = null;
  let viewportPan = null;
  const activeTouchPoints = new Map();
  let touchGesture = null;
  let dropTargetId = null;
  // the card a connector being drawn or reconnected would land on
  let connectTargetId = null;
  // What a single click shows the flow of -- {type: 'node' | 'edge' |
  // 'boundary', id} -- or null. It is not a selection: nothing is moved,
  // deleted or restyled through it; a double click selects for that
  // (04-model showFlow, selectForEditing).
  let flowFocus = null;
  // What the flow lights, worked out once per drawing (04-model flowLit).
  let currentFlow = null;
  // A press on an item not selected for editing, waiting to learn whether it
  // is a click (the item's flow) or the start of a drag (select, then move).
  let pendingPress = null;
  // When a double click (or tap) last acted: the browser's own dblclick that
  // follows it must not act a second time.
  let dblclickHandledAt = -Infinity;
  // Touch has no click count: the last tap, to tell a double tap by.
  let lastTap = null;
  // A press on a card's connection point captures the pointer to draw a
  // wire, and the browser sends no dblclick after that: the last such click.
  let lastPortClick = null;
  // A phone draws the library as a drawer and the inspector as a sheet
  // (styles/responsive.css, max-width 599px); a finger needs bigger targets
  // than a mouse on any screen.
  const phoneLayout = () => window.matchMedia('(max-width: 599px)').matches;
  // Narrower than the inspector beside the drawing (a tablet, a phone): an
  // open inspector lies over the drawing (styles/responsive.css).
  const inspectorOverlays = () => window.matchMedia('(max-width: 1100px)').matches;
  const coarsePointer = () => window.matchMedia('(pointer: coarse)').matches;
  // How far a handle answers, in drawing units: a mouse's size, or on a
  // coarse pointer at least `finger` screen pixels whatever the zoom.
  const touchReach = (mouse, finger) => (coarsePointer() ? Math.max(mouse, finger / Math.max(zoom, 0.01)) : mouse);
  // Every way a line being drawn can end -- dropped, undone, cancelled,
  // taken over by a pinch -- goes through here, so the canvas is never left
  // wearing the crosshair, or lighting a card, for a line that is gone.
  const clearConnection = () => {
    connection = null;
    connectTargetId = null;
    delete viewport.dataset.connecting;
  };
  // Everything half-done with the pointer, dropped where it stands: the line
  // being drawn, a bend being pulled, a marquee. Escape does this, and so does
  // a right-click in the middle of a drag.
  const abandonGesture = () => {
    clearConnection();
    if (drag?.type === 'edge-bend') {
      const shaped = edgeById(drag.id);
      if (shaped) {
        if (drag.before.length) shaped.waypoints = drag.before;
        else delete shaped.waypoints;
      }
      discardCheckpoint();
    }
    drag = null;
    pendingPress = null;
    marqueeSelection = null;
    dropTargetId = null;
    alignmentGuides = [];
  };
  let activeSearchQuery = '';
  let zoom = 1;
  let fitMode = true;
  let fitGeneration = 0;
  const MIN_ZOOM = 0.1;
  const MAX_ZOOM = 4;
  const ZOOM_STEP = 0.1;
  const undoStack = [];
  const redoStack = [];
  const workspaceParams = new URLSearchParams(window.location.search);
  const freshWorkspace = workspaceParams.has('fresh');
  const freshWorkspaceToken = freshWorkspace
    ? (workspaceParams.get('fresh') || '1').replace(/[^a-zA-Z0-9._-]/g, '-').slice(0, 64)
    : '';
  const storageKey = `infragram-editor:${originalProject.slug}${freshWorkspace ? `:fresh:${freshWorkspaceToken}` : ''}`;
  const themeStorageKey = 'infragram-workspace-theme';
  const layoutStorageKey = 'infragram-workspace-layout';
  if (freshWorkspace) document.querySelector('[data-local-state]').textContent = 'Fresh workspace';

