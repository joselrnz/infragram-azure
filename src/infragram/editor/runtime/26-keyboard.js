// @module 26-keyboard: keyboard shortcuts
  document.addEventListener('keydown', event => {
    // A dialog over the canvas owns the keyboard while it is open. Without
    // this the editor's own Tab steps through the drawing behind the sheet
    // -- taking the key the dialog needs to cycle its own controls, so its
    // focus trap never sees one -- and Delete deletes a selection the reader
    // cannot see. The dialogs keep their own Escape.
    if (document.querySelector('[aria-modal="true"]')) return;
    const active = document.activeElement;
    // Typing into a field owns every key; a focused select or button owns
    // Delete and Backspace, which would otherwise delete the selection while
    // the reader is looking at an inspector control.
    const editing = ['INPUT', 'TEXTAREA'].includes(active?.tagName) || Boolean(active?.isContentEditable);
    const onControl = editing || ['SELECT', 'BUTTON'].includes(active?.tagName);
    if (!onControl && (event.key === 'Delete' || event.key === 'Backspace')) {
      event.preventDefault();
      deleteSelection();
    }
    if (!editing && (event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'z') {
      event.preventDefault();
      document.querySelector(`[data-editor-action="${event.shiftKey ? 'redo' : 'undo'}"]`).click();
    }
    // Ctrl+Y is redo everywhere else on Windows; Ctrl+Shift+Z is the same step.
    if (!editing && (event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'y') {
      event.preventDefault();
      document.querySelector('[data-editor-action="redo"]').click();
    }
    if (editing) return;
    const command = event.ctrlKey || event.metaKey;
    if (event.key === 'Escape') {
      abandonGesture();
      clearSelection();
      renderGraph();
    } else if (command && event.key.toLocaleLowerCase() === 'c') {
      event.preventDefault();
      copySelection();
    } else if (command && event.key.toLocaleLowerCase() === 'x') {
      event.preventDefault();
      cutSelection();
    } else if (command && event.key.toLocaleLowerCase() === 'v') {
      event.preventDefault();
      pasteClipboard();
    } else if (command && event.key.toLocaleLowerCase() === 'd') {
      event.preventDefault();
      duplicateSelection();
    } else if (command && event.key.toLocaleLowerCase() === 'a') {
      event.preventDefault();
      const primary = selectedItem();
      const parentId = selected?.type === 'boundary' ? primary?.parentId || null
        : selected?.type === 'node' ? primary?.boundaryId || null : null;
      clearSelection();
      state.nodes.filter(node => (node.boundaryId || null) === parentId && nodeIsVisible(node))
        .forEach(node => selectedNodeIds.add(node.id));
      state.boundaries.filter(boundary => (boundary.parentId || null) === parentId && boundaryIsVisible(boundary))
        .forEach(boundary => selectedBoundaryIds.add(boundary.id));
      if (selectedNodeIds.size) selected = {type: 'node', id: [...selectedNodeIds].at(-1)};
      else if (selectedBoundaryIds.size) selected = {type: 'boundary', id: [...selectedBoundaryIds].at(-1)};
      renderGraph();
    } else if (command && ['+', '='].includes(event.key)) {
      event.preventDefault();
      setZoom(zoom + ZOOM_STEP);
    } else if (command && event.key === '-') {
      event.preventDefault();
      setZoom(zoom - ZOOM_STEP);
    } else if (command && event.key === '0') {
      event.preventDefault();
      setZoom(1);
    } else if (!command && !event.altKey && ['+', '=', '-', '0', '1'].includes(event.key)) {
      // the right-click menu's keys: + and - zoom, 0 fits all, 1 is actual size
      event.preventDefault();
      if (event.key === '0') fitZoom();
      else if (event.key === '1') setZoom(1);
      else setZoom(zoom + (event.key === '-' ? -ZOOM_STEP : ZOOM_STEP));
    } else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)
        && selected?.type === 'edge' && selectedItem()?.label) {
      event.preventDefault();
      const edge = selectedItem();
      if (itemIsLocked(edge)) return;
      const item = edgeGeometry().find(candidate => candidate.edge.id === edge.id);
      if (!item) return;
      const resolved = resolvedEdgeLabel(item);
      const automatic = automaticEdgeLabel(item);
      const step = event.shiftKey ? 10 : 1;
      const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0;
      const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0;
      checkpoint();
      // Nudge the offset the author asked for, not where the label ended up
      // after being kept clear of a card: starting from the clamped point
      // would absorb every keypress and pin the label there for good.
      const manual = edge.labelPlacement?.mode === 'manual';
      const baseX = manual ? Number(edge.labelPlacement.dx) || 0 : resolved.x - automatic.x;
      const baseY = manual ? Number(edge.labelPlacement.dy) || 0 : resolved.y - automatic.y;
      edge.labelPlacement = {mode: 'manual', dx: baseX + dx, dy: baseY + dy};
      delete edge.labelX;
      delete edge.labelY;
      renderGraph();
      persist();
      setStatus(`${edge.label} label nudged`);
    } else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)
        && selectedObjects().length) {
      event.preventDefault();
      const step = event.shiftKey ? 10 : 1;
      const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0;
      const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0;
      checkpoint();
      topLevelArrangeObjects().filter(object => !itemIsLocked(object)).forEach(object => {
        translateObject(object,
          clamp(object.x + dx, 0, state.canvas.width - object.width),
          clamp(object.y + dy, 0, state.canvas.height - object.height));
      });
      persist();
      renderGraph();
    } else if (command && event.key === ']') {
      event.preventDefault();
      arrangeSelection(event.shiftKey ? 'forward' : 'to-front');
    } else if (command && event.key === '[') {
      event.preventDefault();
      arrangeSelection(event.shiftKey ? 'backward' : 'to-back');
    } else if (command && event.key.toLocaleLowerCase() === 'g') {
      event.preventDefault();
      arrangeSelection(event.shiftKey ? 'detach' : 'group');
    } else if (command && event.shiftKey && event.key.toLocaleLowerCase() === 'l') {
      event.preventDefault();
      arrangeSelection('lock');
    } else if (event.key === 'Tab' && (active === diagram || diagram.contains(active))
        && state.nodes.length + state.boundaries.length + state.edges.filter(edge => edge.label).length) {
      // Tab steps through the drawing only while the canvas has focus; on a
      // toolbar button or in the sidebar it is the browser's, so a keyboard
      // reader can reach every control. Past the last item (or before the
      // first) the key goes back to the browser too, and focus leaves the
      // canvas instead of circling inside it.
      const ordered = [
        ...state.boundaries,
        ...state.nodes,
        ...state.edges.filter(edge => edge.label),
      ].sort((a, b) => Number(a.order) - Number(b.order));
      const current = selectedItem();
      const index = ordered.findIndex(item => item.id === current?.id);
      const target = index + (event.shiftKey ? -1 : 1);
      if (index >= 0 && (target < 0 || target >= ordered.length)) {
        clearSelection();
        renderGraph();
        return;
      }
      event.preventDefault();
      const next = ordered[target < 0 ? ordered.length - 1 : target];
      if (boundaryById(next.id)) selectBoundary(next.id);
      else if (nodeById(next.id)) selectNode(next.id);
      else selectEdge(next.id);
      renderGraph();
    }
  });

