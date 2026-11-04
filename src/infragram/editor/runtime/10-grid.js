// @module 10-grid: the editor grid and its toolbar toggle
  const gridPattern = defs.querySelector('#infragram-editor-grid');
  const gridToggle = document.querySelector('[data-editor-action="toggle-grid"]');
  const updateEditorGrid = () => {
    const snapStep = Math.max(1, Number(state.canvas.grid) || 4);
    const gridSteps = Math.max(2, Math.round(Number(state.canvas.gridSteps) || 4));
    // Lines closer than this on the screen are a grey wash, not a grid: a
    // zoomed-out drawing keeps every other line until they stand apart.
    const minGridPixels = Math.max(10, Number(state.canvas.minGridPixels) || 10);
    let visibleStep = Math.max(snapStep, Number(state.canvas.visualGrid) || snapStep * 3);
    while (visibleStep * zoom < minGridPixels) visibleStep *= 2;
    const majorStep = visibleStep * gridSteps;
    const minorPath = Array.from({length: gridSteps - 1}, (_, index) => {
      const offset = (index + 1) * visibleStep;
      return `M${offset} 0V${majorStep}M0 ${offset}H${majorStep}`;
    }).join('');
    gridPattern.setAttribute('width', String(majorStep));
    gridPattern.setAttribute('height', String(majorStep));
    gridPattern.dataset.gridSteps = String(gridSteps);
    gridPattern.dataset.visibleStep = String(visibleStep);
    gridPattern.querySelector('[data-grid-minor]').setAttribute('d', minorPath);
    gridPattern.querySelector('[data-grid-major]').setAttribute(
      'd', `M0 0H${majorStep}M0 0V${majorStep}`,
    );
    stage.style.setProperty('--editor-grid-minor-px', `${visibleStep * zoom}px`);
    stage.style.setProperty('--editor-grid-major-px', `${majorStep * zoom}px`);
    // Connection dots keep one screen size and stand one screen distance
    // off a card's edge at any zoom: the handle is scaled by 1/zoom and
    // moved out by 10 screen pixels' worth of drawing units.
    stage.style.setProperty('--port-unit', String(1 / Math.max(zoom, 0.01)));
    stage.style.setProperty('--port-gap', `${10 / Math.max(zoom, 0.01)}px`);
    stage.dataset.gridVisible = String(state.canvas.showGrid);
    const gridLayer = layer.querySelector('[data-editor-grid]');
    if (gridLayer) {
      gridLayer.style.display = state.canvas.showGrid ? '' : 'none';
      gridLayer.style.opacity = '0';
    }
    gridToggle.setAttribute('aria-pressed', String(state.canvas.showGrid));
    gridToggle.title = state.canvas.showGrid ? 'Hide grid' : 'Show grid';
    updateInspector();
  };
  diagram.querySelectorAll('[data-static-cluster-layer],[data-static-link-layer],[data-static-node-layer]')
    .forEach(child => { child.style.display = 'none'; });

