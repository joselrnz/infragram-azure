// @module 35-comments: comments on cards, frames and wires, kept in the page (ADR 0009)
  // A reviewer comments on what the diagram draws. The page reads the
  // comments it was exported with (#infragram-comments) and keeps the ones
  // written here in this browser, under the workspace's own key; nothing is
  // sent anywhere. Download comments writes <slug>.comments.json, which an
  // export carries back into the page when it sits beside the document.
  // A comment names its element by kind and id, and keeps its name: a card
  // whose id changed is found by name, and one found by neither is listed as
  // detached, never dropped. Markers and threads are a view: no picture
  // carries them (29-downloads strips the marker layer).
  const COMMENTS_FORMAT = 'infragram.comments/1';
  const commentsPanel = document.querySelector('[data-comments-panel]');
  const commentsToggle = document.querySelector('[data-comments-toggle]');
  const commentsCount = commentsToggle?.querySelector('[data-comments-count]');
  const commentsList = commentsPanel?.querySelector('[data-comments-list]');
  const commentForm = commentsPanel?.querySelector('[data-comment-form]');
  const commentText = commentsPanel?.querySelector('[data-comment-text]');
  const commentSubmit = commentsPanel?.querySelector('[data-comment-submit]');
  const commentTargetLine = commentsPanel?.querySelector('[data-comment-target]');
  const commentError = commentsPanel?.querySelector('[data-comment-error]');
  const commentAuthor = commentsPanel?.querySelector('[data-comment-author]');
  const commentsNote = commentsPanel?.querySelector('[data-comments-note]');
  const commentsKey = `${storageKey}:comments`;
  const AUTHOR_KEY = 'infragram-comment-author';
  const KIND_WORDS = {node: 'card', boundary: 'frame', edge: 'wire'};
  const validComment = comment => Boolean(comment) && typeof comment.id === 'string'
    && typeof comment.text === 'string' && comment.text.trim() !== '' && comment.anchor
    && ['node', 'boundary', 'edge'].includes(comment.anchor.kind) && typeof comment.anchor.id === 'string';
  const carriedPayload = (() => {
    try {
      const payload = JSON.parse(document.querySelector('#infragram-comments')?.textContent || 'null');
      return payload?.format === COMMENTS_FORMAT ? payload : null;
    } catch {
      return null;
    }
  })();
  const carriedComments = Array.isArray(carriedPayload?.comments)
    ? carriedPayload.comments.filter(validComment) : [];
  // The document the comments are on: a view's page (<slug>-<view>) carries
  // the whole document's comments, and its download goes back beside that
  // document under the document's own slug, where an export looks for it.
  const commentsSlug = typeof carriedPayload?.slug === 'string' && carriedPayload.slug
    ? carriedPayload.slug : originalProject.slug;
  // what the comments file allows (projects/comments.py), so a download is
  // always one an export reads back
  const ANCHOR_ID_MAX = 200;
  const ANCHOR_NAME_MAX = 300;
  const capped = (value, max) => String(value || '').slice(0, max);
  let localComments = (() => {
    try {
      const saved = JSON.parse(localStorage.getItem(commentsKey) || '[]');
      return Array.isArray(saved) ? saved.filter(validComment) : [];
    } catch {
      return [];
    }
  })();
  const keepLocal = () => {
    try {
      localStorage.setItem(commentsKey, JSON.stringify(localComments));
      return true;
    } catch {
      return false;
    }
  };
  // a comment the page was exported with is part of the page: only one
  // written in this browser, and not carried too, can be deleted here
  const isLocalComment = id => localComments.some(comment => comment.id === id)
    && !carriedComments.some(comment => comment.id === id);
  const allComments = () => {
    const carried = new Set(carriedComments.map(comment => comment.id));
    return [...carriedComments, ...localComments.filter(comment => !carried.has(comment.id))]
      .sort((a, b) => String(a.at).localeCompare(String(b.at)));
  };
  const itemsOfKind = kind => (kind === 'node' ? state.nodes : kind === 'boundary' ? state.boundaries : state.edges);
  const itemOfKind = (kind, id) => (kind === 'node' ? nodeById(id) : kind === 'boundary' ? boundaryById(id) : edgeById(id));
  const itemName = (kind, item) => String((kind === 'edge' ? item?.label : item?.name) || '');
  // A wire's id is its place in the drawing order, which an added wire or a
  // view moves: a comment on a wire is found by the two cards it joins, the
  // label telling apart two wires between the same pair.
  const anchoredEdge = anchor => {
    const byId = edgeById(anchor.id);
    if (!anchor.source || !anchor.target) return byId || null;
    const joins = edge => edge.source === anchor.source && edge.target === anchor.target;
    const labelled = edge => capped(itemName('edge', edge), ANCHOR_NAME_MAX) === String(anchor.name || '');
    if (byId && joins(byId) && labelled(byId)) return byId;
    const between = state.edges.filter(joins);
    if (between.length === 1) return between[0];
    const sameLabel = between.filter(labelled);
    if (sameLabel.length === 1) return sameLabel[0];
    return byId && joins(byId) ? byId : null;
  };
  // by id; else the one element of that kind with the remembered name
  const anchoredItem = anchor => {
    if (anchor.kind === 'edge' && anchor.source && anchor.target) return anchoredEdge(anchor);
    const byId = itemOfKind(anchor.kind, anchor.id);
    if (byId) return byId;
    if (!anchor.name) return null;
    const named = itemsOfKind(anchor.kind).filter(item => capped(itemName(anchor.kind, item), ANCHOR_NAME_MAX) === anchor.name);
    return named.length === 1 ? named[0] : null;
  };
  const anchorOf = (kind, item) => ({
    kind,
    id: capped(item.id, ANCHOR_ID_MAX),
    name: capped(itemName(kind, item), ANCHOR_NAME_MAX),
    ...(kind === 'edge' ? {source: capped(item.source, ANCHOR_ID_MAX), target: capped(item.target, ANCHOR_ID_MAX)} : {}),
  });
  let commentTarget = null;
  const describe = (kind, item) => {
    const name = itemName(kind, item);
    return name ? `${KIND_WORDS[kind]} ${name}` : `this ${KIND_WORDS[kind]}`;
  };
  // The panel floats over the map's top right, like a frame's review, in
  // review and in edit alike; on a phone it is a sheet along the bottom.
  const placeCommentsPanel = () => {
    if (!commentsPanel || commentsPanel.hidden) return;
    const box = viewport.getBoundingClientRect();
    commentsPanel.style.top = `${Math.round(box.top + 12)}px`;
    commentsPanel.style.left = `${Math.round(Math.max(box.left + 12, box.right - commentsPanel.offsetWidth - 12))}px`;
  };
  const showCommentsPanel = () => {
    if (!commentsPanel) return;
    commentsPanel.hidden = false;
    commentsToggle?.setAttribute('aria-pressed', 'true');
    placeCommentsPanel();
  };
  const closeCommentsPanel = () => {
    if (!commentsPanel || commentsPanel.hidden) return;
    commentsPanel.hidden = true;
    commentsToggle?.setAttribute('aria-pressed', 'false');
    commentsToggle?.focus({preventScroll: true});
  };
  commentsToggle?.addEventListener('click', () => {
    if (commentsPanel?.hidden) showCommentsPanel();
    else closeCommentsPanel();
  });
  commentsPanel?.querySelector('[data-comments-close]')?.addEventListener('click', closeCommentsPanel);
  commentsPanel?.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      closeCommentsPanel();
    }
  });
  window.addEventListener('resize', placeCommentsPanel);
  // Add comment: the form now writes on this element.
  const openCommentFor = (kind, item) => {
    if (!commentsPanel || !item || !KIND_WORDS[kind]) return;
    commentTarget = {kind, id: item.id};
    showCommentsPanel();
    commentTargetLine.textContent = `On the ${describe(kind, item)}`;
    commentText.disabled = false;
    commentSubmit.disabled = false;
    commentError.hidden = true;
    requestAnimationFrame(() => commentText.focus({preventScroll: true}));
  };
  const when = at => {
    const date = new Date(at);
    return Number.isNaN(date.getTime()) ? String(at || '')
      : date.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
  };
  const commentMarkup = (comment, {detached = false} = {}) => `<li data-comment="${escapeText(comment.id)}">`
    + `<p>${escapeText(comment.text)}</p>`
    + `<small>${escapeText(comment.author || 'Someone')} · ${escapeText(when(comment.at))}`
    + `${detached ? ` · on ${escapeText(comment.anchor.name || comment.anchor.id)}` : ''}</small>`
    + `${isLocalComment(comment.id) ? '<button type="button" class="md-button md-button--text" data-comment-delete>Delete</button>' : ''}`
    + '</li>';
  let shownComments = '';
  const renderComments = () => {
    if (!commentsList) return;
    const comments = allComments();
    if (commentsCount) commentsCount.textContent = comments.length ? String(comments.length) : '';
    commentsToggle?.setAttribute('aria-label', comments.length ? `Comments, ${comments.length}` : 'Comments');
    const threads = new Map();
    const detached = [];
    comments.forEach(comment => {
      const item = anchoredItem(comment.anchor);
      if (!item) {
        detached.push(comment);
        return;
      }
      const key = `${comment.anchor.kind}:${item.id}`;
      if (!threads.has(key)) threads.set(key, {kind: comment.anchor.kind, item, comments: []});
      threads.get(key).comments.push(comment);
    });
    const markup = comments.length
      ? [...threads.values()].map(({kind, item, comments: thread}) => `<section class="comment-thread" data-comment-thread="${escapeText(`${kind}:${item.id}`)}">`
        + `<h4><button type="button" class="comment-thread-title" data-comment-reveal="${kind}" data-comment-item="${escapeText(item.id)}">${escapeText(itemName(kind, item) || KIND_WORDS[kind])}</button>`
        + ` <span>${KIND_WORDS[kind]}</span></h4>`
        + `<ol>${thread.map(comment => commentMarkup(comment)).join('')}</ol>`
        + `<button type="button" class="md-button md-button--text" data-comment-add="${kind}" data-comment-item="${escapeText(item.id)}">Add to this</button></section>`).join('')
        + (detached.length ? '<section class="comment-thread" data-comment-detached>'
          + '<h4>Detached <span>what they were on is not in the diagram now</span></h4>'
          + `<ol>${detached.map(comment => commentMarkup(comment, {detached: true})).join('')}</ol></section>` : '')
      : '<p class="comments-empty">No comments yet.</p>';
    if (markup === shownComments) return;
    shownComments = markup;
    commentsList.innerHTML = markup;
  };
  const showCommentsError = message => {
    commentError.textContent = message;
    commentError.hidden = false;
  };
  commentForm?.addEventListener('submit', event => {
    event.preventDefault();
    const item = commentTarget ? itemOfKind(commentTarget.kind, commentTarget.id) : null;
    if (!item) {
      showCommentsError('Pick what to comment on first: right-click it and choose Add comment.');
      return;
    }
    const text = commentText.value.trim();
    if (!text) {
      showCommentsError('Write a comment first.');
      return;
    }
    localComments.push({
      id: `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      anchor: anchorOf(commentTarget.kind, item),
      author: commentAuthor.value.trim().slice(0, 80),
      text: text.slice(0, 4000),
      at: new Date().toISOString(),
    });
    if (!keepLocal()) commentsNote.textContent = 'This browser cannot keep comments: download them before you close the page.';
    commentText.value = '';
    commentError.hidden = true;
    renderComments();
    renderGraph();
  });
  // a typed button, so nothing in the page ever submits a form: it asks the form to
  commentSubmit?.addEventListener('click', () => commentForm.requestSubmit());
  commentText?.addEventListener('input', () => { commentError.hidden = true; });
  try {
    if (commentAuthor) commentAuthor.value = localStorage.getItem(AUTHOR_KEY) || '';
  } catch { /* a browser without storage asks for the name each time */ }
  commentAuthor?.addEventListener('change', () => {
    try {
      localStorage.setItem(AUTHOR_KEY, commentAuthor.value.trim());
    } catch { /* kept for this page only */ }
  });
  const revealCommented = (kind, id) => {
    const item = itemOfKind(kind, id);
    if (!item) return;
    // an element outside the open frame is shown in the whole diagram
    const shown = kind === 'node' ? nodeIsVisible(item) : kind === 'boundary' ? boundaryIsVisible(item) : true;
    if (!shown && drillPath.length) setDrillPath([]);
    if (kind === 'node') {
      selectNode(id);
      revealNode(item);
    } else if (kind === 'boundary') selectBoundary(id);
    else selectEdge(id);
    renderGraph();
  };
  commentsList?.addEventListener('click', event => {
    const reveal = event.target.closest('[data-comment-reveal]');
    if (reveal) {
      revealCommented(reveal.dataset.commentReveal, reveal.dataset.commentItem);
      return;
    }
    const add = event.target.closest('[data-comment-add]');
    if (add) {
      openCommentFor(add.dataset.commentAdd, itemOfKind(add.dataset.commentAdd, add.dataset.commentItem));
      return;
    }
    const remove = event.target.closest('[data-comment-delete]');
    const id = remove?.closest('[data-comment]')?.dataset.comment;
    if (id && isLocalComment(id)) {
      localComments = localComments.filter(comment => comment.id !== id);
      keepLocal();
      renderComments();
      renderGraph();
    }
  });
  // The file a reviewer sends back: every comment, each anchor brought up to
  // date with what it is on now, so it is found by id the next time too.
  const commentsFile = () => ({
    format: COMMENTS_FORMAT,
    slug: commentsSlug,
    comments: allComments().map(comment => {
      const item = anchoredItem(comment.anchor);
      const kept = {
        kind: comment.anchor.kind,
        id: capped(comment.anchor.id, ANCHOR_ID_MAX),
        name: capped(comment.anchor.name, ANCHOR_NAME_MAX),
        ...(comment.anchor.source && comment.anchor.target
          ? {source: capped(comment.anchor.source, ANCHOR_ID_MAX), target: capped(comment.anchor.target, ANCHOR_ID_MAX)}
          : {}),
      };
      return {
        id: comment.id,
        anchor: item ? anchorOf(comment.anchor.kind, item) : kept,
        author: String(comment.author || ''),
        text: comment.text,
        at: String(comment.at || ''),
      };
    }),
  });
  commentsPanel?.querySelector('[data-comments-download]')?.addEventListener('click', () => {
    download(`${commentsSlug}.comments.json`, 'application/json',
      `${JSON.stringify(commentsFile(), null, 2)}\n`);
  });
  // A marker on each commented element, numbered, which opens its thread.
  afterRender.push(() => {
    renderComments();
    diagram.querySelector('[data-comment-marker-layer]')?.remove();
    const counts = new Map();
    allComments().forEach(comment => {
      const item = anchoredItem(comment.anchor);
      if (!item) return;
      const key = `${comment.anchor.kind}:${item.id}`;
      counts.set(key, {kind: comment.anchor.kind, item, count: (counts.get(key)?.count || 0) + 1});
    });
    if (!counts.size) return;
    const colors = canvasPalette();
    const marks = [...counts.values()].map(({kind, item, count}) => {
      let x, y;
      if (kind === 'edge') {
        const path = diagram.querySelector(`[data-graph-edge][data-edge-id="${CSS.escape(item.id)}"]`);
        if (!path?.getTotalLength) return '';
        const middle = path.getPointAtLength(path.getTotalLength() / 2);
        [x, y] = [middle.x, middle.y];
      } else {
        if (!(kind === 'node' ? nodeIsVisible(item) : boundaryIsVisible(item))) return '';
        [x, y] = [item.x + item.width, item.y];
      }
      return `<g data-comment-marker data-comment-kind="${kind}" data-comment-item="${escapeText(item.id)}" cursor="pointer">`
        + `<title>${count} comment${count === 1 ? '' : 's'} on the ${escapeText(describe(kind, item))}</title>`
        + `<circle cx="${x}" cy="${y}" r="9" fill="${colors.accent}" stroke="${colors.card}" stroke-width="2"/>`
        + `<text x="${x}" y="${y + 4}" text-anchor="middle" font-size="11" font-weight="600" fill="${colors.card}" pointer-events="none">${count}</text></g>`;
    }).join('');
    diagram.querySelector('[data-graph-layer]')?.insertAdjacentHTML('beforeend', `<g data-comment-marker-layer>${marks}</g>`);
  });
  // a marker opens the thread, before the canvas takes the press for a pan
  diagram.addEventListener('pointerdown', event => {
    const marker = event.target.closest?.('[data-comment-marker]');
    if (!marker || event.button > 0) return;
    event.stopPropagation();
    event.preventDefault();
    showCommentsPanel();
    const thread = commentsList?.querySelector(`[data-comment-thread="${CSS.escape(`${marker.dataset.commentKind}:${marker.dataset.commentItem}`)}"]`);
    thread?.scrollIntoView({block: 'nearest'});
    thread?.querySelector('[data-comment-reveal]')?.focus({preventScroll: true});
  }, true);
  renderComments();
