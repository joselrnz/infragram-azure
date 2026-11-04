// @module 02-helpers: artwork lookups, saved-artwork refresh, snapping and text helpers
  const clone = value => JSON.parse(JSON.stringify(value));
  const componentArtwork = new Map();
  const componentDefinitions = new Map();
  libraryCatalog.components.forEach(component => {
    componentDefinitions.set(component.qualifiedId, component);
    componentArtwork.set(component.qualifiedId, component.iconUri || '');
    if (component.provider === generatedState.provider) {
      componentArtwork.set(component.serviceId, component.iconUri || '');
    }
  });
  const generatedNodes = new Map(generatedState.nodes.map(node => [node.id, node]));
  const generatedBoundaries = new Map(
    generatedState.boundaries.map(boundary => [boundary.id, boundary]),
  );
  // The layout as the renderer produced it, taken by value, now.
  //
  // A fresh page starts with `state = generatedState` (00-bootstrap), so the
  // records in the two maps above are the very objects a drag mutates. Read
  // later they describe where a card was dragged to, not where the layout put
  // it -- which made Tidy restore every card from itself and report success
  // having moved nothing. Copying the four numbers here, before any pointer
  // has touched the canvas, is the whole fix.
  const geometryOf = item => ({x: item.x, y: item.y, width: item.width, height: item.height});
  const laidOutNodes = new Map(generatedState.nodes.map(node => [node.id, geometryOf(node)]));
  const laidOutFrames = new Map(
    generatedState.boundaries.map(boundary => [boundary.id, geometryOf(boundary)]),
  );
  const refreshSavedArtwork = saved => {
    saved.nodes = (saved.nodes || []).map(node => {
      const generated = generatedNodes.get(node.id);
      const artworkKey = node.componentQualifiedId || node.componentId;
      const hasPaletteArtwork = componentArtwork.has(artworkKey);
      const iconUri = hasPaletteArtwork
        ? componentArtwork.get(artworkKey)
        : generated?.iconUri;
      return iconUri === undefined ? node : {...node, iconUri};
    });
    saved.boundaries = (saved.boundaries || []).map(boundary => {
      const generated = generatedBoundaries.get(boundary.id);
      const definition = componentDefinitions.get(boundary.componentQualifiedId);
      if (definition?.boundaryStyle) {
        return {...boundary, ...clone(definition.boundaryStyle)};
      }
      return generated?.kind === boundary.kind
        ? {...boundary, iconUri: generated.iconUri}
        : boundary;
    });
    return saved;
  };
  // A dialog holds the keyboard while it is open. Tab off the last control
  // and the browser walks on into the canvas and the sidebar behind it: a
  // reader using the keyboard leaves the dialog without closing it, and a
  // reader using a screen reader is read a page the dialog is sitting on top
  // of. `aria-modal` says so, the cycle keeps Tab inside, and closing puts
  // the keyboard back where it was rather than at the top of the document.
  const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),'
    + 'select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  const focusableWithin = dialog => Array.from(dialog.querySelectorAll(FOCUSABLE))
    .filter(element => element.offsetParent !== null || element === document.activeElement);
  const trapFocus = dialog => {
    let returnTo = null;
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const stops = focusableWithin(dialog);
      if (!stops.length) return;
      const first = stops[0];
      const last = stops[stops.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault();
        last.focus({preventScroll: true});
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus({preventScroll: true});
      }
    });
    return {
      opened: () => {
        returnTo = document.activeElement;
        dialog.setAttribute('aria-modal', 'true');
      },
      closed: () => {
        dialog.removeAttribute('aria-modal');
        const target = returnTo && returnTo.isConnected ? returnTo : null;
        returnTo = null;
        (target || diagram).focus({preventScroll: true});
      },
    };
  };
  const snap = value => Math.round(value / state.canvas.grid) * state.canvas.grid;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const escapeText = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const truncate = (value, length) => String(value ?? '').length > length
    ? `${String(value).slice(0, length - 1)}…` : String(value ?? '');
