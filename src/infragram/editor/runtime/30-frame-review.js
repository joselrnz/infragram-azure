// @module 30-frame-review: calling out a frame, showing its contents as icons or cards, and reviewing them
  // A highlight is part of the drawing: it is saved as editor_highlight on the
  // frame, drawn by both renderers, and travels into every export.
  const setFrameHighlight = (frameId, on) => {
    const frame = boundaryById(frameId);
    if (!frame || itemIsLocked(frame)) return false;
    if (Boolean(frame.highlight) === Boolean(on)) return Boolean(on);
    checkpoint();
    if (on) frame.highlight = true;
    else delete frame.highlight;
    persist();
    renderGraph();
    setStatus(`${frame.name} ${on ? 'highlighted' : 'no longer highlighted'}`);
    return Boolean(on);
  };

  // The review: every component inside one frame, grouped by the frame that
  // holds it, with how it is drawn. Choosing a row selects that component and
  // brings it into view, and the review stays open, so a region can be walked
  // component by component after it has been highlighted or switched.
  const frameReview = document.querySelector('[data-frame-review]');
  const reviewFocus = frameReview ? trapFocus(frameReview) : null;
  let reviewedFrameId = null;
  let reviewMarkup = '';
  const placeFrameReview = () => {
    if (!frameReview || frameReview.hidden) return;
    const box = viewport.getBoundingClientRect();
    frameReview.style.top = `${Math.round(box.top + 12)}px`;
    frameReview.style.left = `${Math.round(Math.max(box.left + 12, box.right - frameReview.offsetWidth - 12))}px`;
  };
  const revealNode = node => {
    leaveFitMode();
    const origin = canvasOrigin();
    viewport.scrollLeft = Math.max(0, origin.x + (node.x + node.width / 2) * zoom - viewport.clientWidth / 2);
    viewport.scrollTop = Math.max(0, origin.y + (node.y + node.height / 2) * zoom - viewport.clientHeight / 2);
  };
  const syncFrameReview = () => {
    if (!frameReview || frameReview.hidden) return;
    const frame = boundaryById(reviewedFrameId);
    if (!frame) {
      closeFrameReview();
      return;
    }
    const members = frameComponents(frame);
    const icons = members.filter(node => (node.displayMode || 'card') === 'icon').length;
    frameReview.querySelector('[data-frame-review-title]').textContent = frame.name;
    frameReview.querySelector('[data-frame-review-summary]').textContent = [
      `${members.length} component${members.length === 1 ? '' : 's'}`,
      `${members.length - icons} card${members.length - icons === 1 ? '' : 's'}`,
      `${icons} icon${icons === 1 ? '' : 's'}`,
    ].join(' · ');
    const highlight = frameReview.querySelector('[data-frame-review-highlight]');
    highlight.setAttribute('aria-pressed', String(Boolean(frame.highlight)));
    highlight.disabled = itemIsLocked(frame);
    frameReview.querySelectorAll('[data-frame-review-display]').forEach(button => {
      const mode = button.dataset.frameReviewDisplay;
      button.disabled = !members.some(node => !itemIsLocked(node) && (node.displayMode || 'card') !== mode)
        && !(mode === 'icon' && tangledIcons(members));
    });
    // grouped under the frame that directly holds each component, in the
    // order the frames nest and the components are placed
    const groups = new Map();
    members
      .slice()
      .sort((a, b) => boundaryDepth(boundaryById(a.boundaryId)) - boundaryDepth(boundaryById(b.boundaryId))
        || a.y - b.y || a.x - b.x)
      .forEach(node => {
        if (!groups.has(node.boundaryId)) groups.set(node.boundaryId, []);
        groups.get(node.boundaryId).push(node);
      });
    const list = frameReview.querySelector('[data-frame-review-list]');
    const markup = members.length
      ? [...groups.entries()].map(([holderId, nodes]) => `
        ${holderId === frame.id ? '' : `<p class="frame-review__group">${escapeText(boundaryById(holderId)?.name || '')}</p>`}
        ${nodes.map(node => `<button type="button" class="md-list-item frame-review__row" data-frame-review-node="${escapeText(node.id)}" aria-pressed="${isNodeSelected(node.id)}">
          <span class="md-list-item__text"><span class="md-list-item__headline">${escapeText(node.name)}</span><span class="md-list-item__supporting">${escapeText(node.detail || node.componentQualifiedId || node.componentId || '')}</span></span>
          <span class="md-list-item__trailing">${(node.displayMode || 'card') === 'icon' ? 'Icon' : 'Card'}${itemIsLocked(node) ? ' · locked' : ''}</span>
        </button>`).join('')}`).join('')
      : '<p class="empty-category">No components in this frame</p>';
    // A render runs on every pointer move of a drag: rebuild the list only
    // when what it shows changed, and give the keyboard back to the row it
    // was on, so choosing a component does not throw focus to the page.
    if (markup === reviewMarkup) return;
    const focused = document.activeElement?.closest?.('[data-frame-review-node]')?.dataset.frameReviewNode;
    list.innerHTML = markup;
    reviewMarkup = markup;
    if (focused) {
      [...list.querySelectorAll('[data-frame-review-node]')]
        .find(row => row.dataset.frameReviewNode === focused)?.focus({preventScroll: true});
    }
  };
  afterRender.push(syncFrameReview);
  const openFrameReview = frameId => {
    if (!frameReview || !boundaryById(frameId)) return;
    reviewedFrameId = frameId;
    reviewMarkup = '';
    if (frameReview.hidden) reviewFocus.opened();
    frameReview.hidden = false;
    syncFrameReview();
    placeFrameReview();
    frameReview.querySelector('[data-frame-review-close]').focus({preventScroll: true});
  };
  const closeFrameReview = () => {
    if (!frameReview || frameReview.hidden) return;
    frameReview.hidden = true;
    reviewedFrameId = null;
    reviewFocus.closed();
  };
  if (frameReview) {
    frameReview.addEventListener('click', event => {
      if (event.target.closest('[data-frame-review-close]')) {
        closeFrameReview();
        return;
      }
      const frame = boundaryById(reviewedFrameId);
      if (!frame) return;
      if (event.target.closest('[data-frame-review-highlight]')) {
        setFrameHighlight(frame.id, !frame.highlight);
        return;
      }
      if (event.target.closest('[data-frame-review-drill]')) {
        closeFrameReview();
        openFrame(frame.id);
        return;
      }
      const display = event.target.closest('[data-frame-review-display]');
      if (display) {
        setFrameDisplayMode(frame.id, display.dataset.frameReviewDisplay);
        return;
      }
      const row = event.target.closest('[data-frame-review-node]');
      const node = row ? nodeById(row.dataset.frameReviewNode) : null;
      if (node) {
        selectNode(node.id);
        revealNode(node);
        renderGraph();
      }
    });
    frameReview.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      closeFrameReview();
    });
    window.addEventListener('resize', placeFrameReview);
    new ResizeObserver(placeFrameReview).observe(viewport);
  }

  // The Style panel's frame section drives the same three operations.
  document.querySelector('[data-frame-highlight-toggle]')?.addEventListener('click', () => {
    const frame = selected?.type === 'boundary' ? selectedItem() : null;
    if (frame) setFrameHighlight(frame.id, !frame.highlight);
  });
  document.querySelector('[data-frame-display-group]')?.addEventListener('click', event => {
    const choice = event.target.closest('[data-frame-display]');
    const frame = selected?.type === 'boundary' ? selectedItem() : null;
    if (choice && frame) setFrameDisplayMode(frame.id, choice.dataset.frameDisplay);
  });
  document.querySelector('[data-frame-review-open]')?.addEventListener('click', () => {
    const frame = selected?.type === 'boundary' ? selectedItem() : null;
    if (frame) openFrameReview(frame.id);
  });

