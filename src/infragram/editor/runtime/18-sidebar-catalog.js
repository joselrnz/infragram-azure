// @module 18-sidebar-catalog: sidebar cards, categories, search and library selection
  const providerSelectionSummary = selection => {
    const ids = [...selection];
    if (ids.length === libraryCatalog.providers.length) return `All ${ids.length}`;
    const names = ids.map(id => providerById.get(id)?.chipName || providerById.get(id)?.shortName || id);
    if (names.length <= 3) return names.join(' + ');
    return `${names[0]} + ${names[1]} +${names.length - 2}`;
  };
  const componentInScope = component => (
    component.provider === 'infragram' || providerSelection.has(component.provider)
  );
  const scopedComponents = (categoryId, query = '') => libraryCatalog.components.filter(
    component => component.categoryId === categoryId
      && componentInScope(component)
      && (!query || component.search.includes(query)),
  );
  // A card names its library only when the page carries more than one, and
  // repeats no subtitle that only restates the category it is listed under.
  const populatedCategories = new Set(libraryCatalog.components.map(component => component.categoryId));
  const categoryLabels = new Map(categories.map(category => [
    category.dataset.categoryId,
    category.querySelector('.category-label')?.textContent.trim().toLocaleLowerCase() || '',
  ]));
  const componentCardMarkup = component => {
    const providerBadge = component.provider === 'infragram' || libraryCatalog.providers.length < 2 ? ''
      : `<span class="md-list-item__trailing provider-badge">${escapeText(providerById.get(component.provider)?.shortName || component.provider)}</span>`;
    const subtitle = String(component.subtitle || '');
    const subtitleMarkup = !subtitle || subtitle.toLocaleLowerCase() === categoryLabels.get(component.categoryId)
      ? '' : `<span class="md-list-item__supporting">${escapeText(subtitle)}</span>`;
    const frame = component.componentKind === 'boundary' && Boolean(component.frameGroup);
    return `<button type="button" class="component-card ${frame ? 'frame-card md-tile' : 'md-list-item'}" draggable="true"
                    data-component-id="${escapeText(component.serviceId)}"
                    data-component-qualified-id="${escapeText(component.qualifiedId)}"
                    data-component-provider="${escapeText(component.provider)}"
                    data-component-kind="${escapeText(component.componentKind || 'node')}"
                    data-boundary-kind="${escapeText(component.boundaryKind || '')}"
                    data-frame-group="${escapeText(component.frameGroup || '')}"
                    data-search="${escapeText(component.search)}"
                    data-mapping-status="${escapeText(component.mappingStatus || 'mapped')}"
                    aria-label="Select ${escapeText(component.name)}" aria-pressed="false">
              <span class="${frame ? 'frame-artwork' : 'component-artwork'}"><img src="${escapeText(component.iconUri)}" alt="" width="${frame ? 120 : 32}" height="${frame ? 72 : 32}" loading="lazy"></span>
              ${frame
                ? `<span class="md-tile__label">${escapeText(component.name)}</span>`
                : `<span class="md-list-item__text"><span class="md-list-item__headline">${escapeText(component.name)}</span>${subtitleMarkup}</span>${providerBadge}`}
            </button>`;
  };
  const subsectionMarkup = (id, label, count, body, open = false) => `
    <details class="component-section" data-component-section="${escapeText(id)}" ${open ? 'open' : ''}>
      <summary class="md-list-item md-list-item--dense md-subheader"><span class="md-list-item__text">${escapeText(label)}</span><span class="md-list-item__trailing">${count}</span>${expandIcon()}</summary>
      <div class="component-section-body">${body}</div>
    </details>`;
  const renderFrameGroups = (frames, query) => (libraryCatalog.frameGroups || []).map(group => {
    const groupPreset = (libraryCatalog.framePresets || []).find(preset => preset.group === group.id);
    const preferredOrder = groupPreset?.componentIds || [];
    const items = frames
      .filter(component => component.frameGroup === group.id)
      .sort((a, b) => {
        const aIndex = preferredOrder.indexOf(a.serviceId);
        const bIndex = preferredOrder.indexOf(b.serviceId);
        if (aIndex >= 0 || bIndex >= 0) {
          if (aIndex < 0) return 1;
          if (bIndex < 0) return -1;
          return aIndex - bIndex;
        }
        return (a.hierarchyLevel || 0) - (b.hierarchyLevel || 0) || a.name.localeCompare(b.name);
      });
    if (!items.length) return '';
    const open = Boolean(query);
    const preset = groupPreset && !query
      ? `<button type="button" class="md-tile frame-preset" draggable="true"
          data-frame-preset="${escapeText(groupPreset.id)}"
          aria-label="Drag ${escapeText(groupPreset.label)} starter to canvas">
          <span class="frame-preset-preview" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
          <span class="md-list-item__text"><span class="md-list-item__headline">${escapeText(groupPreset.label)} ${groupPreset.layout === 'detached' ? 'frames' : 'starter'}</span><span class="md-list-item__supporting">${escapeText(groupPreset.detail)}</span></span>
        </button>`
      : '';
    return `<details class="frame-group" data-frame-group="${escapeText(group.id)}" ${open ? 'open' : ''}>
      <summary class="md-list-item md-list-item--dense"><span class="md-list-item__text">${escapeText(group.label)}</span><span class="md-list-item__trailing">${items.length}</span>${expandIcon()}</summary>
      <div class="frame-group-body">${preset}<div class="frame-grid">${items.map(componentCardMarkup).join('')}</div></div>
    </details>`;
  }).join('');
  const renderProviderServiceGroups = (components, query) => libraryCatalog.providers.map(provider => {
    const items = components.filter(component => component.provider === provider.id);
    if (!items.length) return '';
    return `<details class="provider-service-group" data-provider-service-group="${escapeText(provider.id)}" ${query ? 'open' : ''}>
      <summary class="md-list-item md-list-item--dense"><span class="md-list-item__text">${escapeText(provider.displayName)}</span><span class="md-list-item__trailing">${items.length}</span>${expandIcon()}</summary>
      <div class="md-list provider-service-list">${items.map(componentCardMarkup).join('')}</div>
    </details>`;
  }).join('');
  const renderCustomCategory = (list, matches, query) => {
    const basics = matches.filter(component => component.provider === 'infragram' && !component.frameGroup);
    const frames = matches.filter(component => Boolean(component.frameGroup));
    const providerServices = matches.filter(component => component.provider !== 'infragram');
    const sections = [];
    if (basics.length) {
      sections.push(subsectionMarkup(
        'basic-elements', 'Basic elements', basics.length,
        `<div class="basic-component-list">${basics.map(componentCardMarkup).join('')}</div>`,
        Boolean(query),
      ));
    }
    if (frames.length) {
      sections.push(subsectionMarkup(
        'architecture-frames', 'Architecture frames', frames.length,
        renderFrameGroups(frames, query), true,
      ));
    }
    if (providerServices.length) {
      sections.push(subsectionMarkup(
        'provider-services', 'Other provider services', providerServices.length,
        renderProviderServiceGroups(providerServices, query), Boolean(query),
      ));
    }
    list.innerHTML = sections.length
      ? sections.join('')
      : '<p class="empty-category">No custom components in the selected libraries</p>';
  };
  const renderCategory = (category, query = '') => {
    const categoryId = category.dataset.categoryId;
    const list = category.querySelector('[data-component-list]');
    const matches = scopedComponents(categoryId, query);
    const count = category.querySelector('[data-category-count]');
    count.textContent = String(matches.length);
    // A category no embedded library can fill is left out; one the current
    // selection merely leaves empty stays, so the list does not shift as
    // libraries are switched on and off.
    category.hidden = !populatedCategories.has(categoryId) || (Boolean(query) && matches.length === 0);
    if (query && matches.length && !category.open) {
      category.dataset.openedBySearch = 'true';
      category.open = true;
    }
    if (!category.open && !query) {
      list.replaceChildren();
      return matches.length;
    }
    if (categoryId === 'custom') {
      renderCustomCategory(list, matches, query);
      return matches.length;
    }
    const visible = query ? matches.slice(0, 120) : matches;
    list.innerHTML = visible.length
      ? visible.map(componentCardMarkup).join('')
      : '<p class="empty-category">No components in the selected libraries</p>';
    if (query && matches.length > visible.length) {
      list.insertAdjacentHTML(
        'beforeend',
        `<p class="empty-category">Showing ${visible.length} of ${matches.length} matches</p>`,
      );
    }
    return matches.length;
  };
  // A search that finds nothing says where else to look: the libraries the
  // page carries but has switched off, and the ones it does not carry.
  const searchEmptyText = query => {
    const carried = libraryCatalog.providers.length;
    let text = `Nothing matches “${query}” in the selected libraries.`;
    if (providerSelection.size < carried) text += ' Choose more libraries above.';
    const installed = Number(libraryCatalog.installedProviders) || 0;
    if (libraryCatalog.drawnOnly) {
      // a copy made small on purpose: the sidebar holds what the drawing uses
      text += ' This page carries only the components in the drawing; a copy exported with --libraries all carries every one.';
    } else if (installed > carried) {
      text += ` This page carries ${carried} of the ${installed} libraries; a copy exported with --libraries all carries every one.`;
    }
    return text;
  };
  const renderVisibleCatalog = () => {
    const query = search.value.trim().toLocaleLowerCase();
    activeSearchQuery = query;
    // While searching, an open category is a heading over its matches, not
    // the category the reader chose, so it must not look selected.
    sidebar.dataset.searching = String(Boolean(query));
    if (!query && previousCatalogQuery) {
      categories.forEach(category => {
        if (category.dataset.openedBySearch === 'true') {
          category.open = false;
          delete category.dataset.openedBySearch;
        }
      });
    }
    let matches = 0;
    categories.forEach(category => { matches += renderCategory(category, query); });
    const searchEmpty = sidebar.querySelector('[data-search-empty]');
    if (searchEmpty) {
      searchEmpty.hidden = !query || matches > 0;
      searchEmpty.textContent = searchEmpty.hidden ? '' : searchEmptyText(search.value.trim());
    }
    previousCatalogQuery = query;
    setStatus(`${matches} component${matches === 1 ? '' : 's'} in ${providerSelection.size} ${providerSelection.size === 1 ? 'library' : 'libraries'}`, {show: false});
    renderGraph();
  };
  const syncProviderControls = (selection, updateSummary = false) => {
    providerOptions.forEach(option => {
      option.checked = selection.has(option.dataset.providerOption);
    });
    document.querySelectorAll('[data-provider-quick-filter]').forEach(button => {
      button.setAttribute('aria-pressed', String(selection.has(button.dataset.providerQuickFilter)));
    });
    providerApply.disabled = selection.size === 0;
    if (updateSummary) providerSummary.textContent = providerSelectionSummary(selection);
  };
  const updateProjectLibraries = () => {
    const installed = new Map(
      (originalProject.providers || []).map(provider => [provider.id, {...provider}]),
    );
    providerSelection.forEach(id => {
      if (!installed.has(id)) installed.set(id, {id, enabled: true});
    });
    originalProject.providers = [...installed.values()].map(provider => ({
      ...provider, enabled: providerSelection.has(provider.id),
    }));
    if (originalProject.kind !== 'hybrid') {
      originalProject.kind = projectKindForProviders([...installed.keys()]);
    }
    originalProject.default_library = providerSelection.size === 1
      ? [...providerSelection][0] : 'all';
  };
  const applyProviderSelection = selection => {
    if (!selection.size) return;
    providerSelection = new Set(selection);
    pendingProviderSelection = new Set(selection);
    libraryCatalog.selectedProviders = [...providerSelection];
    updateProjectLibraries();
    syncProviderControls(providerSelection, true);
    closeProviderMenu();
    renderVisibleCatalog();
  };

  categories.forEach(category => {
    category.querySelector('summary').addEventListener('click', event => {
      event.preventDefault();
      category.open = !category.open;
      renderCategory(category, search.value.trim().toLocaleLowerCase());
    });
  });
  search.addEventListener('input', renderVisibleCatalog);
  // The menu is a popover on a trigger, not a modal: the sidebar behind it
  // stays usable, so it declares no `aria-modal` and does not hold Tab. What
  // it does owe a reader is the rest of the contract. It had none of it.
  // Escape did nothing, opening left the keyboard on the trigger outside the
  // dialog it had just announced, and applying hid the menu while the Apply
  // button still had focus -- which drops focus to the document body and
  // loses the reader's place in the page entirely.
  const closeProviderMenu = ({restoreFocus = true} = {}) => {
    if (providerMenu.hidden) return;
    const inside = providerMenu.contains(document.activeElement);
    providerMenu.hidden = true;
    providerMenuTrigger.setAttribute('aria-expanded', 'false');
    if (restoreFocus || inside) providerMenuTrigger.focus({preventScroll: true});
  };
  providerMenuTrigger.addEventListener('click', () => {
    if (!providerMenu.hidden) {
      closeProviderMenu({restoreFocus: false});
      return;
    }
    providerMenu.hidden = false;
    providerMenuTrigger.setAttribute('aria-expanded', 'true');
    pendingProviderSelection = new Set(providerSelection);
    syncProviderControls(pendingProviderSelection);
    providerMenu.querySelector(
      'input:not([disabled]),button:not([disabled])')?.focus({preventScroll: true});
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !providerMenu.hidden) {
      event.stopPropagation();
      closeProviderMenu();
    }
  });
  document.addEventListener('pointerdown', event => {
    if (providerMenu.hidden) return;
    if (providerMenu.contains(event.target) || providerMenuTrigger.contains(event.target)) return;
    closeProviderMenu({restoreFocus: false});
  });
  providerOptions.forEach(option => option.addEventListener('change', () => {
    const providerId = option.dataset.providerOption;
    if (option.checked) pendingProviderSelection.add(providerId);
    else pendingProviderSelection.delete(providerId);
    syncProviderControls(pendingProviderSelection);
  }));
  document.querySelector('[data-provider-select-all]').addEventListener('click', () => {
    pendingProviderSelection = new Set(libraryCatalog.providers.map(provider => provider.id));
    syncProviderControls(pendingProviderSelection);
  });
  document.querySelector('[data-provider-clear]').addEventListener('click', () => {
    pendingProviderSelection.clear();
    syncProviderControls(pendingProviderSelection);
  });
  providerApply.addEventListener('click', () => applyProviderSelection(pendingProviderSelection));
  document.querySelectorAll('[data-provider-quick-filter]').forEach(button => {
    button.addEventListener('click', () => applyProviderSelection(new Set([
      button.dataset.providerQuickFilter,
    ])));
  });
  document.addEventListener('pointerdown', event => {
    if (!providerMenu.hidden && !event.target.closest('.provider-selector')) {
      providerMenu.hidden = true;
      providerMenuTrigger.setAttribute('aria-expanded', 'false');
      syncProviderControls(providerSelection);
    }
  });
  sidebar.addEventListener('click', event => {
    const preset = event.target.closest('[data-frame-preset]');
    if (preset) {
      addFramePreset(preset.dataset.framePreset);
      return;
    }
    const component = event.target.closest('[data-component-id]');
    if (!component) return;
    // A finger cannot drag a tile out of a drawer onto the drawing: a tap
    // adds it where the reader is looking, and on a phone puts the drawer
    // away to show it.
    if ((event.pointerType || (coarsePointer() ? 'touch' : 'mouse')) === 'touch') {
      const view = viewport.getBoundingClientRect();
      addComponent(componentPayload(component),
        toSvgPoint(view.left + view.width / 2, view.top + view.height / 2));
      if (phoneLayout()) {
        document.body.classList.add('sidebar-collapsed');
        updateSidebarTrigger();
      }
      return;
    }
    sidebar.querySelectorAll('[data-component-id]').forEach(
      item => item.setAttribute('aria-pressed', 'false'),
    );
    component.setAttribute('aria-pressed', 'true');
    setStatus(`Drag ${componentDefinitions.get(component.dataset.componentQualifiedId)?.name || 'the component'} onto the canvas`, {show: false});
  });
  document.querySelector('[data-template-starter]')?.addEventListener('click', event => {
    addFramePreset(event.currentTarget.dataset.templateStarter);
  });
  sidebar.addEventListener('dblclick', event => {
    const component = event.target.closest('[data-component-id]');
    if (!component) return;
    addComponent(componentPayload(component), {
      x: state.canvas.width / 2,
      y: state.canvas.height / 2,
    });
  });
  sidebar.addEventListener('dragstart', event => {
    const preset = event.target.closest('[data-frame-preset]');
    if (preset) {
      event.dataTransfer.effectAllowed = 'copy';
      event.dataTransfer.setData(
        'application/x-infragram-frame-preset', preset.dataset.framePreset,
      );
      event.dataTransfer.setData('text/plain', preset.dataset.framePreset);
      return;
    }
    const component = event.target.closest('[data-component-id]');
    if (!component) return;
    event.dataTransfer.effectAllowed = 'copy';
    event.dataTransfer.setData(
      'application/x-infragram-component', JSON.stringify(componentPayload(component)),
    );
    event.dataTransfer.setData('text/plain', component.dataset.componentQualifiedId);
  });
  syncProviderControls(providerSelection, true);
  renderVisibleCatalog();

