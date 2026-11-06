// @module 33-costs: the Cost tab, the header's cost chip and the Resources table
  // What the diagram costs a month, approximately, from the prices the export
  // wrote into each element (attributes.price: on-demand list prices, from
  // the shipped tables or fetched live) and the reasons it wrote where it
  // could not price (attributes.unpriced; "free: ..." for what costs nothing
  // on its own). Nothing is priced here: the page stays offline, and a card
  // added in the page shows as not priced until the diagram is exported again.
  const costPanel = document.querySelector('[data-inspector-panel="cost"]');
  const costTab = document.querySelector('[data-inspector-tab="cost"]');
  const COST_KEYS = {instance_type: 'instance type', instance_class: 'instance class', os: 'OS',
    hours: 'hours a month', count: 'count'};
  const costOf = node => {
    const price = node.attributes?.price;
    const monthly = Number(price?.monthly);
    if (!price || !Number.isFinite(monthly)) return null;
    const usage = Number(price.usage) || 0;
    return {node, price, monthly, usage, fixed: Number.isFinite(Number(price.fixed)) && price.lines?.length
      ? Number(price.fixed) : monthly - usage, currency: price.currency || 'USD'};
  };
  const sumBy = (items, pick) => {
    const totals = new Map();
    items.forEach(item => totals.set(item.currency, (totals.get(item.currency) || 0) + pick(item)));
    return totals;
  };
  const amounts = totals => [...totals].map(([currency, value]) => money(value, currency)).join(' + ') || money(0, 'USD');
  const roundMoney = (value, currency) => {
    try {
      return new Intl.NumberFormat('en-US', {style: 'currency', currency: currency || 'USD',
        maximumFractionDigits: 0}).format(value);
    } catch (error) { return `${currency || 'USD'} ${Math.round(value)}`; }
  };
  const quantity = value => Number(value).toLocaleString('en-US', {maximumFractionDigits: 3});
  const framesOf = node => {
    const chain = [];
    let frameId = node.boundaryId || null;
    while (frameId) {
      const frame = boundaryById(frameId);
      if (!frame || chain.includes(frame)) break;
      chain.unshift(frame);
      frameId = frame.parentId || null;
    }
    return chain;
  };
  const costLines = price => (Array.isArray(price.lines) ? price.lines : []).map(item => `<tr${item.kind === 'usage' ? ' data-cost-usage' : ''}>`
    + `<th>${escapeText(item.label)}${item.kind === 'usage' ? ' <em>usage</em>' : ''}</th>`
    + `<td>${escapeText(quantity(item.quantity))} ${escapeText(item.unit)}${item.assumed ? ' <em data-popup-assumed>assumed</em>' : ''}`
    + ` × ${escapeText(money(Number(item.rate), price.currency))}</td>`
    + `<td>${escapeText(money(Number(item.amount), price.currency))}</td></tr>`).join('');
  const syncCosts = () => {
    if (!costPanel) return;
    // with a frame open the sum is of what it holds (34-drill-down)
    const shown = state.nodes.filter(nodeInOpenFrame);
    const priced = shown.map(costOf).filter(Boolean);
    const unpriced = shown.filter(node => !costOf(node) && typeof node.attributes?.unpriced === 'string');
    const free = unpriced.filter(node => node.attributes.unpriced.startsWith('free: '));
    const missing = unpriced.filter(node => !node.attributes.unpriced.startsWith('free: '));
    const totals = sumBy(priced, item => item.monthly);
    const usage = sumBy(priced, item => item.usage);
    const fixed = sumBy(priced, item => item.fixed);
    const any = priced.length > 0;
    if (costTab) {
      costTab.hidden = !any && !unpriced.length;
      // a tab does not vanish while it is the open one
      if (costTab.hidden && costTab.getAttribute('aria-selected') === 'true') {
        document.querySelector('[data-inspector-tab="diagram"]')?.click();
      }
    }
    const summary = costPanel.querySelector('[data-cost-summary]');
    const assumedCount = priced.reduce((count, item) => count + (item.price.assumed?.length || 0), 0);
    summary.innerHTML = any
      ? `<p class="cost-total"><strong>≈ ${escapeText(amounts(totals))}</strong> a month</p>`
        + '<dl class="cost-split">'
        + `<div><dt>Fixed</dt><dd>${escapeText(amounts(fixed))}</dd></div>`
        + `<div><dt>Usage</dt><dd>${escapeText(amounts(usage))}</dd></div>`
        + `<div><dt>Priced</dt><dd>${priced.length} of ${priced.length + missing.length}</dd></div>`
        + (free.length ? `<div><dt>Free</dt><dd>${free.length}</dd></div>` : '')
        + (assumedCount ? `<div><dt>Sizes assumed</dt><dd>${assumedCount}</dd></div>` : '') + '</dl>'
      : '<p>Nothing in this diagram is priced. ' + (missing.length ? 'Why each is not is listed under Not priced.' : 'Export it again to price its Azure components (they are priced unless the export was asked for --no-prices).') + '</p>';
    // each frame's subtotal: everything priced inside it, however deep
    const frameTotals = new Map();
    priced.forEach(item => framesOf(item.node).forEach(frame => {
      const entry = frameTotals.get(frame.id) || {totals: new Map(), count: 0};
      entry.totals.set(item.currency, (entry.totals.get(item.currency) || 0) + item.monthly);
      entry.count += 1;
      frameTotals.set(frame.id, entry);
    }));
    const frameRows = [];
    const visit = (parentId = null, depth = 0) => {
      state.boundaries
        .filter(frame => (frame.parentId || null) === parentId && frameTotals.has(frame.id))
        .sort((a, b) => Number(a.order) - Number(b.order))
        .forEach(frame => {
          const entry = frameTotals.get(frame.id);
          frameRows.push(`<div class="cost-row" style="--cost-depth:${depth}" data-cost-frame="${escapeText(frame.id)}">`
            + `<span>${escapeText(frame.name)} <small>${entry.count}</small></span><strong>${escapeText(amounts(entry.totals))}</strong></div>`);
          visit(frame.id, depth + 1);
        });
    };
    visit();
    costPanel.querySelector('[data-cost-frames]').innerHTML = frameRows.join('');
    costPanel.querySelector('[data-cost-heading="frames"]').hidden = !frameRows.length;
    costPanel.querySelector('[data-cost-items]').innerHTML = priced
      .sort((a, b) => b.monthly - a.monthly || a.node.name.localeCompare(b.node.name))
      .map(({node, price, monthly}) => `<details class="cost-item" data-cost-item="${escapeText(node.id)}">`
        + `<summary><span><strong>${escapeText(node.name)}</strong><small>${escapeText(price.rate || '')}</small></span>`
        + `<b>${escapeText(money(monthly, price.currency))}</b></summary>`
        + (price.lines?.length ? `<table><tbody>${costLines(price)}</tbody></table>` : '')
        + `<p><small>${escapeText(price.source || '')}${price.priced ? `, read ${escapeText(price.priced)}` : ''}</small>`
        + ` <button type="button" class="md-button md-button--text" data-cost-show="${escapeText(node.id)}">Show on canvas</button></p>`
        + '</details>').join('');
    costPanel.querySelector('[data-cost-heading="items"]').hidden = !any;
    const assumed = priced.filter(item => item.price.assumed?.length);
    costPanel.querySelector('[data-cost-assumed]').innerHTML = assumed.map(({node, price}) => `<li><strong>${escapeText(node.name)}</strong>: `
      + price.assumed.map(key => {
        const value = price.sizing?.[key];
        return `${escapeText(COST_KEYS[key] || String(key).replaceAll('_', ' '))}${value === undefined ? '' : ` ${escapeText(value)}`}`;
      }).join(', ') + '</li>').join('');
    costPanel.querySelector('[data-cost-heading="assumed"]').hidden = !assumed.length;
    costPanel.querySelector('[data-cost-unpriced]').innerHTML = missing.map(node => `<li><strong>${escapeText(node.name)}</strong>: ${escapeText(node.attributes.unpriced)}</li>`).join('')
      + (free.length ? `<li class="cost-free"><details><summary>${free.length} free</summary><ul>${free.map(node => `<li><strong>${escapeText(node.name)}</strong>: ${escapeText(node.attributes.unpriced.slice(6))}</li>`).join('')}</ul></details></li>` : '');
    costPanel.querySelector('[data-cost-heading="unpriced"]').hidden = !unpriced.length;
    const read = priced.map(item => item.price.priced).filter(Boolean).sort().at(-1);
    costPanel.querySelector('[data-cost-note]').textContent = any
      ? `On-demand list prices${read ? ` read ${read}` : ''}, before tax, discounts, savings plans and reserved rates; usage lines rest on the quantities shown. An estimate, not a bill.`
      : '';
  };
  costPanel?.addEventListener('click', event => {
    const show = event.target.closest('[data-cost-show]');
    if (!show) return;
    const node = nodeById(show.dataset.costShow);
    if (!node) return;
    showFlowOf('node', node.id);
    revealNode(node);
    openElementDetails(node.id);
  });
  afterRender.push(syncCosts);
  syncCosts();

  // Resources: every card the diagram draws, and every frame an import found
  // unused, as one table in the bottom drawer -- what it is, where it lives,
  // what it carries, what it costs a month and whether it sits unused -- to
  // search, filter, sort, download as CSV, and click through to the canvas.
  // It reads what the export wrote (attributes.table, price, unused, attached,
  // tags) and what the page holds now, so a card added here shows too.
  const resourcePanel = document.querySelector('[data-bottom-panel="resources"]');
  // artwork drawn in dark ink is lifted on the dark theme, as the canvas lifts
  // it (08-theme-and-layout.js); the stylesheet applies it only there
  resourcePanel?.addEventListener('load', event => {
    const image = event.target;
    if (!image.matches?.('img.resource-icon')) return;
    measureInk(image.src).then(dark => image.toggleAttribute('data-ink-dark', dark));
  }, true);
  // What to do about each kind of unused resource, said as an action.
  const SAVING_ACTIONS = {
    'unattached-disk': 'Delete the disk',
    'unassociated-ip': 'Release the public IP',
    'detached-nic': 'Delete the NIC',
    'empty-load-balancer': 'Delete the load balancer',
    'empty-application-gateway': 'Delete the app gateway',
    'empty-plan': 'Delete or scale in the plan',
    'stopped-app': 'Delete or restart the app',
    'stopped-vm': 'Deallocate the VM',
    'deallocated-vm': 'Delete the VM',
    'idle-gateway': 'Delete the gateway',
    'idle-nat-gateway': 'Delete the NAT gateway',
    'unlinked-dns-zone': 'Link or delete the DNS zone',
    'disconnected-endpoint': 'Delete the private endpoint',
    'unassociated-nsg': 'Delete the NSG',
    'unassociated-route-table': 'Delete the route table',
    'empty-availability-set': 'Delete the availability set',
    'empty-resource-group': 'Delete the resource group',
  };
  // each saving: the action, the resource, why, and what it saves a month --
  // what the resource bills, unless the rule says it bills nothing
  const savingRows = all => all.filter(row => row.unused).map(row => ({
    ...row,
    action: SAVING_ACTIONS[row.unused.rule] || 'Review it',
    saving: row.unused.bills === 'no' || row.monthly === null ? 0 : row.monthly,
  })).sort((a, b) => b.saving - a.saving || a.name.localeCompare(b.name));
  const resourceView = {query: '', type: '', group: '', only: new Set(), sort: 'monthly', descending: true,
    groupBy: '', folded: new Set()};
  // What an Azure import read about an item, as its row carries it: its
  // changes (the newest first) and its findings (the worst first), and what
  // each sorts by.
  const SEVERITY_RANK = {High: 3, Medium: 2, Low: 1};
  const signals = item => {
    const changes = itemChanges(item);
    const findings = itemFindings(item);
    return {
      changes, lastChange: changes?.items[0]?.when || '', recent: changedLately(item),
      findings, worst: findings ? Math.max(0, ...findings.items.map(finding => SEVERITY_RANK[finding.severity] || 0)) : -1,
    };
  };
  const CHANGE_WORDS = {Create: 'Created', Update: 'Updated', Delete: 'Deleted'};
  // a change's day and time as Azure states them, in UTC
  const changeDate = (when, options) => {
    const date = new Date(when);
    return Number.isNaN(date.getTime()) ? String(when || '') : date.toLocaleString(undefined, {timeZone: 'UTC', ...options});
  };
  const changeDay = when => changeDate(when, {day: 'numeric', month: 'short'});
  const changeTime = when => changeDate(when, {hour: '2-digit', minute: '2-digit', hour12: false});
  const changeLine = change => `${CHANGE_WORDS[change.kind] || change.kind} ${changeDay(change.when)}`;
  const changeWho = change => [change.by, change.client].filter(Boolean).join(' · ');
  // what a change moved, a line each: networkAcls.defaultAction: Deny → Allow;
  // a value naming another resource by its ARM id says its name
  const changeValue = value => (/^\/subscriptions\/[^/]+\/resourcegroups\//i.test(String(value))
    ? String(value).replace(/\/+$/, '').split('/').at(-1) : String(value || '') || 'none');
  const changeMoves = change => [
    ...(change.properties || []).map(item => `${String(item.path).replace(/^properties\./, '')}: ${changeValue(item.before)} → ${changeValue(item.after)}`),
    ...(change.more ? [`${change.more} more`] : []),
  ];
  // 1 high, 2 medium, 1 policy: worst first, Policy's (which has no severity) last
  const findingSummary = findings => {
    if (!findings) return '';
    const counts = new Map();
    findings.items.forEach(finding => {
      const key = finding.severity || 'Policy';
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    const unlisted = (Number(findings.count) || 0) - findings.items.length;
    return [...['High', 'Medium', 'Low', 'Policy'].filter(key => counts.has(key))
      .map(key => `${counts.get(key)} ${key.toLowerCase()}`), ...(unlisted > 0 ? [`${unlisted} more`] : [])].join(', ');
  };
  // a frame's row: its kind said plainly, and the resource group it is in
  const FRAME_TYPES = {'resource-group': 'Resource group', network: 'Virtual network', 'subnet-private': 'Subnet',
    'subnet-public': 'Subnet', subscription: 'Subscription', 'management-group': 'Management group'};
  const frameType = frame => FRAME_TYPES[frame.kind]
    || String(frame.kind || 'Frame').replaceAll('-', ' ').replace(/^./, letter => letter.toUpperCase());
  const frameGroup = frame => {
    let at = frame;
    while (at && at.kind !== 'resource-group') at = boundaryById(at.parentId);
    return at?.name || '';
  };
  const tableValue = (item, label) => {
    const rows = Array.isArray(item.attributes?.table?.rows) ? item.attributes.table.rows : [];
    const row = rows.find(entry => Array.isArray(entry) && entry[0] === label);
    return row ? String(row[1] ?? '') : '';
  };
  const resourceRows = () => {
    const nodes = state.nodes.filter(nodeInOpenFrame).map(node => {
      const definition = componentDefinitions.get(node.componentQualifiedId) || {};
      const frames = framesOf(node);
      const group = tableValue(node, 'Resource group')
        || frames.filter(frame => /resource.?group/i.test(String(frame.kind || frame.type || ''))).map(frame => frame.name).at(-1)
        || frames.at(-1)?.name || '';
      const parts = attachedParts(node);
      const owner = ownerOfPart(node);
      const unused = node.attributes?.unused || null;
      // an app names the plan it runs on; a plan, the apps it hosts
      const runsOn = String(node.attributes?.runs_on || '');
      const hosts = Array.isArray(node.attributes?.hosts) ? node.attributes.hosts.map(String) : [];
      // what it is tied to: the card that carries it or that it runs on, or
      // the parts and apps it carries; else the network it sits in -- its
      // innermost frame that is not a resource group, subscription or other scope
      const network = frames.filter(frame => !/resource.?group|subscription|management|organi[sz]ation|tenant|account|region|cloud|provider/i
        .test(String(frame.kind || frame.type || ''))).at(-1);
      const carrier = owner?.name || node.attributes?.attached_to || runsOn
        || (parts.length || hosts.length ? node.name : '');
      const tied = carrier ? `Tied to ${carrier}` : network ? `In ${network.name}` : '';
      return {
        id: node.id, kind: 'node', name: node.name, icon: node.iconUri || '',
        type: definition.name || node.componentId || '',
        group, location: tableValue(node, 'Location'),
        links: parts.length ? parts.map(part => `${part.role}: ${part.name}`).join(', ')
          : owner ? `on ${owner.name}` : node.attributes?.attached_to ? `on ${node.attributes.attached_to}`
          : runsOn ? `runs on ${runsOn}` : hosts.length ? `hosts ${hosts.join(', ')}` : '',
        monthly: nodeMonthly(node), currency: node.attributes?.price?.currency || 'USD',
        running: Number(unused?.running_monthly) || null,
        unused, tags: nodeTags(node), tied, runsOn, hosts, ...signals(node),
      };
    });
    // a frame has a row when an import found something about it: unused, changed, or a finding
    const frames = state.boundaries.filter(frame => frame.attributes?.unused || itemChanges(frame) || itemFindings(frame)).map(frame => ({
      id: frame.id, kind: 'boundary', name: frame.name, icon: frame.iconUri || '', type: frameType(frame), group: frameGroup(frame),
      location: '', links: '', monthly: null, currency: 'USD', running: null,
      unused: frame.attributes.unused || null, tags: {}, tied: '', runsOn: '', hosts: [], ...signals(frame),
    }));
    return [...nodes, ...frames];
  };
  const tagText = tags => Object.entries(tags).map(([key, value]) => `${key}=${value}`).join(' ');
  const resourceMatches = row => {
    const view = resourceView;
    if (view.type && row.type !== view.type) return false;
    if (view.group && row.group !== view.group) return false;
    if (view.only.has('unused') && !row.unused) return false;
    if (view.only.has('untagged') && (row.kind !== 'node' || Object.keys(row.tags).length)) return false;
    if (view.only.has('priced') && row.monthly === null) return false;
    if (view.only.has('changed') && !row.recent) return false;
    if (view.only.has('findings') && !row.findings) return false;
    const query = view.query.trim().toLocaleLowerCase();
    return !query || [row.name, row.type, row.group, row.location, row.links, tagText(row.tags),
      row.unused?.reason || '', ...(row.findings?.items || []).map(finding => finding.title)]
      .join(' ').toLocaleLowerCase().includes(query);
  };
  const resourceKey = (row, key) => (key === 'monthly' ? (row.monthly ?? -1)
    : key === 'unused' ? (row.unused ? 1 : 0)
      : key === 'findings' ? row.worst * 1000 + (Number(row.findings?.count) || 0)
        : key === 'changed' ? row.lastChange
          : key === 'tags' ? tagText(row.tags) : String(row[key] || '').toLocaleLowerCase());
  // a column chosen again turns its order round; a new one starts with the
  // most first for cost, status, findings and changes, from A for the rest
  const MOST_FIRST = new Set(['monthly', 'unused', 'findings', 'changed']);
  const sortBy = key => {
    resourceView.descending = resourceView.sort === key ? !resourceView.descending : MOST_FIRST.has(key);
    resourceView.sort = key;
    syncResources();
  };
  const sortOrder = (key, descending) => (key === 'monthly' ? (descending ? 'Most first' : 'Least first')
    : key === 'unused' ? (descending ? 'Unused first' : 'In use first')
      : key === 'findings' ? (descending ? 'Worst first' : 'Fewest first')
        : key === 'changed' ? (descending ? 'Newest first' : 'Oldest first')
          : descending ? 'Z to A' : 'A to Z');
  // names in natural order (vm-2 before vm-10), and an empty value last
  // whichever way the column runs
  const NATURAL = new Intl.Collator(undefined, {numeric: true, sensitivity: 'base'});
  const sortedResources = rows => rows.slice().sort((a, b) => {
    const x = resourceKey(a, resourceView.sort);
    const y = resourceKey(b, resourceView.sort);
    const text = typeof x === 'string' || typeof y === 'string';
    if (text && !x !== !y) return x ? -1 : 1;
    const order = text ? NATURAL.compare(String(x), String(y)) : x < y ? -1 : x > y ? 1 : 0;
    return (resourceView.descending ? -order : order) || NATURAL.compare(a.name, b.name);
  });
  const fillOptions = (select, values, label) => {
    const chosen = select.value;
    select.innerHTML = `<option value="">${escapeText(label)}</option>`
      + values.map(value => `<option value="${escapeText(value)}">${escapeText(value)}</option>`).join('');
    select.value = values.includes(chosen) ? chosen : '';
  };
  // Rewritten only when what it says has changed: a redraw between a press
  // and its release would otherwise replace the button being clicked.
  const setMarkup = (element, markup) => {
    if (element && element.dataset.markup !== markup) {
      element.innerHTML = markup;
      element.dataset.markup = markup;
    }
  };
  const tally = (rows, key) => rows.reduce((counts, row) => counts.set(row[key], (counts.get(row[key]) || 0) + 1), new Map());
  const renderChoices = (select, counts) => {
    const list = select?.closest('.resource-filter-section')?.querySelector('[data-filter-choices]');
    if (!list) return;
    setMarkup(list, [...select.options].filter(option => option.value).map(option => '<button type="button" class="md-list-item filter-choice"'
      + ` data-filter-value="${escapeText(option.value)}" aria-pressed="${option.value === select.value}">`
      + `${'<span class="filter-check" aria-hidden="true"></span>'}<span class="md-list-item__label">${escapeText(option.textContent)}</span>`
      + `<span class="filter-count">${counts.get(option.value) || 0}</span></button>`).join(''));
  };
  const syncResources = () => {
    if (!resourcePanel) return;
    applyColumns();
    const all = resourceRows();
    fillOptions(resourcePanel.querySelector('[data-resource-type]'),
      [...new Set(all.map(row => row.type).filter(Boolean))].sort(), 'Type');
    fillOptions(resourcePanel.querySelector('[data-resource-group]'),
      [...new Set(all.map(row => row.group).filter(Boolean))].sort(), 'Group');
    resourceView.type = resourcePanel.querySelector('[data-resource-type]').value;
    resourceView.group = resourcePanel.querySelector('[data-resource-group]').value;
    renderChoices(resourcePanel.querySelector('[data-resource-type]'), tally(all, 'type'));
    renderChoices(resourcePanel.querySelector('[data-resource-group]'), tally(all, 'group'));
    const onlyCounts = {
      unused: all.filter(row => row.unused).length,
      untagged: all.filter(row => row.kind === 'node' && !Object.keys(row.tags).length).length,
      priced: all.filter(row => row.monthly !== null).length,
      changed: all.filter(row => row.recent).length,
      findings: all.filter(row => row.findings).length,
    };
    // the import's filters show only where it read something
    resourcePanel.querySelectorAll('[data-resource-only="changed"],[data-resource-only="findings"]').forEach(choice => {
      choice.hidden = !all.some(row => (choice.dataset.resourceOnly === 'changed' ? row.changes : row.findings));
      // a filter whose chip is gone cannot stay on, with nothing to untick
      if (choice.hidden && resourceView.only.delete(choice.dataset.resourceOnly)) choice.setAttribute('aria-pressed', 'false');
    });
    resourcePanel.querySelectorAll('[data-only-count]').forEach(count => {
      count.textContent = String(onlyCounts[count.dataset.onlyCount] ?? '');
    });
    const rows = sortedResources(all.filter(resourceMatches));
    // the card picked on the map: selected to edit, or its flow shown
    const selectedId = selected?.id || (flowFocus?.type === 'node' ? flowFocus.id : null);
    // one line a row: the card's own artwork, small, before its name (its
    // type on hover, and in its own column when that is shown); the cells
    // in the panel's column order
    const order = columnOrder();
    const rowMarkup = row => {
      const cells = {
        name: `<td data-col="name" title="${escapeText(row.type ? `${row.name}, ${row.type}` : row.name)}"><div class="resource-name">${row.icon ? `<img class="resource-icon" src="${escapeText(row.icon)}"${inkIsDark.get(row.icon) ? ' data-ink-dark' : ''} alt="" loading="lazy">` : '<span class="resource-icon" aria-hidden="true"></span>'}`
          + `<strong>${escapeText(row.name)}</strong></div></td>`,
        type: `<td data-col="type">${escapeText(row.type)}</td>`,
        group: `<td data-col="group">${escapeText(row.group)}</td>`,
        location: `<td data-col="location">${escapeText(row.location)}</td>`,
        links: `<td data-col="links" title="${escapeText(row.links)}">${escapeText(row.links)}</td>`,
        monthly: `<td data-col="monthly" class="resource-money"${row.running ? ` title="${escapeText(money(row.running, row.currency))} a month if started"` : ''}>`
          + `${row.monthly === null ? '' : escapeText(money(row.monthly, row.currency))}</td>`,
        unused: `<td data-col="unused" title="${escapeText(row.unused?.reason || '')}">${row.unused
          ? `<span class="resource-unused">Unused</span> <small>${escapeText(row.unused.reason || '')}</small>` : ''}</td>`,
        findings: `<td data-col="findings" title="${escapeText((row.findings?.items || []).map(finding => `${finding.severity || 'Policy'}: ${finding.title}`).join('\n'))}">`
          + `${escapeText(findingSummary(row.findings))}</td>`,
        changed: `<td data-col="changed" title="${escapeText(row.changes ? changeWho(row.changes.items[0]) : '')}">${row.changes
          ? `${escapeText(changeLine(row.changes.items[0]))}${row.changes.count > 1 ? ` <small>${row.changes.count} changes</small>` : ''}` : ''}</td>`,
        tags: `<td data-col="tags">${escapeText(Object.entries(row.tags).map(([key, value]) => `${key}=${value}`).join(', '))}</td>`,
      };
      return `<tr data-resource-row="${escapeText(row.id)}" data-resource-kind="${row.kind}" data-selected="${row.id === selectedId}">`
        + order.map(key => cells[key]).join('') + '</tr>';
    };
    // Grouped, each bucket opens under a header row -- its name, how many,
    // what they cost -- that folds it away; buckets keep the table's sort
    // inside and come in name order, the catch-all last.
    const groupKey = {
      group: row => row.group || 'No resource group',
      type: row => row.type || 'Other',
      tied: row => row.tied || 'Not tied to anything',
      status: row => (row.unused ? 'Unused' : 'In use'),
    }[resourceView.groupBy];
    // a header row spans the columns the table shows, no more: a wider span
    // would add a column of its own to the fixed layout
    const columnCount = [...resourcePanel.querySelectorAll('[data-resource-table] thead th')]
      .filter(th => getComputedStyle(th).display !== 'none').length || 1;
    let markup;
    if (groupKey) {
      const buckets = new Map();
      rows.forEach(row => {
        const key = groupKey(row);
        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key).push(row);
      });
      const last = new Set(['No resource group', 'Other', 'Not tied to anything', 'In use']);
      const order = [...buckets.keys()].sort((a, b) => (last.has(a) - last.has(b)) || a.localeCompare(b));
      markup = order.map(key => {
        const members = buckets.get(key);
        const priced = members.filter(row => row.monthly !== null);
        const folded = resourceView.folded.has(key);
        return `<tr class="resource-group-row" data-resource-group-key="${escapeText(key)}">`
          + `<td colspan="${columnCount}"><button type="button" class="resource-group-toggle" aria-expanded="${!folded}"><span class="resource-group-chevron" aria-hidden="true"></span>`
          + `<strong>${escapeText(key)}</strong><span class="resource-group-count">${members.length}</span>`
          + (priced.length ? `<span class="resource-group-total">${escapeText(amounts(sumBy(priced, row => row.monthly)))} a month</span>` : '')
          + '</button></td></tr>'
          + (folded ? '' : members.map(rowMarkup).join(''));
      }).join('');
    } else {
      markup = rows.map(rowMarkup).join('');
    }
    setMarkup(resourcePanel.querySelector('[data-resource-rows]'), markup);
    resourcePanel.querySelector('[data-resource-empty]').hidden = rows.length > 0;
    const activeFilters = Number(Boolean(resourceView.type)) + Number(Boolean(resourceView.group)) + resourceView.only.size;
    const filterCount = resourcePanel.querySelector('[data-resource-filters-count]');
    if (filterCount) {
      filterCount.hidden = !activeFilters;
      filterCount.textContent = String(activeFilters);
    }
    resourcePanel.querySelector('[data-resource-filters-toggle]')
      ?.setAttribute('aria-label', activeFilters ? `Filters, ${activeFilters} on` : 'Filters');
    resourcePanel.querySelectorAll('[data-resource-sort]').forEach(button => {
      const on = button.dataset.resourceSort === resourceView.sort;
      // aria-sort belongs to the column header, not the button in it
      (button.closest('th') || button).setAttribute('aria-sort',
        on ? (resourceView.descending ? 'descending' : 'ascending') : 'none');
    });
    // One quiet line: how many resources, the frames counted apart (a row
    // each, but no resource: empty resource groups, or frames an import
    // found changed or raised a finding about), and -- while the A month column
    // is hidden, so its totals row has no figure -- what they cost a month.
    // Filtered, it says how many of the whole are shown and how many of those
    // are unused, with Clear to show them all again; what the unused part
    // costs is the Savings tab's to say.
    const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`;
    const shownNodes = rows.filter(row => row.kind === 'node').length;
    const allNodes = all.filter(row => row.kind === 'node').length;
    const shownFrames = rows.filter(row => row.kind !== 'node');
    const shownGroups = shownFrames.length;
    const emptyOnly = shownFrames.every(row => row.unused?.rule === 'empty-resource-group');
    const priced = rows.filter(row => row.monthly !== null);
    const total = priced.length ? amounts(sumBy(priced, row => row.monthly)) : '';
    const unused = rows.filter(row => row.unused).length;
    const filtered = rows.length !== all.length || Boolean(resourceView.query.trim()) || activeFilters > 0;
    const monthShown = resourcePanel.dataset.columns?.split(' ').includes('monthly');
    setMarkup(resourcePanel.querySelector('[data-resource-summary]'), (filtered
      ? `<strong>${shownNodes}</strong> of ${plural(allNodes, 'resource', 'resources')}`
      : `<strong>${allNodes}</strong> ${allNodes === 1 ? 'resource' : 'resources'}`)
      + (shownGroups ? ` · ${emptyOnly ? plural(shownGroups, 'empty group', 'empty groups') : plural(shownGroups, 'frame', 'frames')}` : '')
      + (total && !monthShown ? ` · <strong>${escapeText(total)}</strong> a month` : '')
      + (filtered && unused ? ` · ${unused} unused` : '')
      + (filtered ? ' <button type="button" class="md-button md-button--text resource-summary-clear" data-resource-clear-all>Clear</button>' : ''));
    // the totals row: what the rows shown cost a month, under its column
    const foot = resourcePanel.querySelector('[data-resource-foot]');
    if (foot) {
      foot.hidden = !rows.length;
      foot.querySelector('[data-foot-total]').textContent = total;
    }
    syncResourceHead(all, selectedId);
    syncSavings(all, selectedId);
    syncChanges(all, selectedId);
  };
  // The Savings view: what the unused part costs, as actions ranked by what
  // each saves a month; those that save nothing but clutter come last.
  const syncSavings = (all, selectedId = selected?.id || null) => {
    const holder = resourcePanel.querySelector('[data-resource-savings]');
    if (!holder) return;
    const rows = savingRows(all);
    const paying = rows.filter(row => row.saving > 0);
    const free = rows.filter(row => row.saving <= 0);
    const total = sumBy(paying, row => row.saving);
    const yearly = new Map([...total].map(([currency, value]) => [currency, value * 12]));
    const tabTotal = resourcePanel.querySelector('[data-savings-tab-total]');
    if (tabTotal) {
      tabTotal.hidden = !paying.length;
      tabTotal.textContent = paying.length ? amounts(total) : '';
    }
    const narrow = resourcePanel.getBoundingClientRect().width < 460;
    resourcePanel.dataset.savingsNarrow = String(narrow);
    const savingRow = row => `<tr data-saving-row="${escapeText(row.id)}" data-resource-kind="${row.kind}" data-selected="${row.id === (selectedId || '')}">`
      + `<td><div class="resource-name">${row.icon ? `<img class="resource-icon" src="${escapeText(row.icon)}"${inkIsDark.get(row.icon) ? ' data-ink-dark' : ''} alt="" loading="lazy">` : '<span class="resource-icon" aria-hidden="true"></span>'}`
      + `<div class="resource-name__text"><strong>${escapeText(row.action)}</strong><small class="resource-type-line">${escapeText(row.name)} · ${escapeText(row.type)}</small>`
      + (narrow ? `<small class="resource-type-line savings-why">${escapeText(row.unused.reason || '')}</small>` : '') + '</div></div></td>'
      + (narrow ? '' : `<td title="${escapeText(row.unused.reason || '')}">${escapeText(row.unused.reason || '')}</td>`)
      + `<td class="resource-money">${row.saving > 0 ? escapeText(money(row.saving, row.currency)) : '<span class="savings-none">No cost</span>'}</td></tr>`;
    const band = (label, count, sum) => `<tr class="resource-group-row"><td colspan="${narrow ? 2 : 3}"><div class="resource-group-toggle">`
      + `<strong>${escapeText(label)}</strong><span class="resource-group-count">${count}</span>`
      + (sum ? `<span class="resource-group-total">${escapeText(sum)} a month</span>` : '') + '</div></td></tr>';
    setMarkup(holder, rows.length
      ? '<div class="savings-head">'
        + `<div><span>Could save a month</span><b>${escapeText(amounts(total))}</b><small>${escapeText(amounts(yearly))} a year</small></div>`
        + `<div><span>Actions</span><b>${rows.length}</b><small>${paying.length} save money, ${free.length} tidy up</small></div>`
        + `<button type="button" class="md-icon-button md-icon-button--sm" data-savings-csv title="Download the savings as CSV" aria-label="Download the savings as CSV">${resourcePanel.querySelector('[data-resource-csv] svg')?.outerHTML || '↓'}</button>`
        + '</div>'
        + '<div class="resource-table-wrap savings-wrap"><table class="resource-table savings-table"><thead><tr>'
        + `<th scope="col"><span>Action</span></th>${narrow ? '' : '<th scope="col"><span>Why</span></th>'}<th scope="col" class="resource-money"><span>Saves</span></th>`
        + '</tr></thead><tbody>'
        + (paying.length ? band('Saves money', paying.length, amounts(total)) + paying.map(savingRow).join('') : '')
        + (free.length ? band('No cost, but clutter', free.length, '') + free.map(savingRow).join('') : '')
        + '</tbody></table></div>'
        + '<p class="savings-note">List prices from the export; what a resource bills unused, as Resource Graph states it. Review before deleting anything.</p>'
      : '<div class="resource-empty"><strong>Nothing to save here</strong><span>No resource in this estate is unused.</span></div>');
  };
  // The Changes view: what the import found changed in the fourteen days
  // before it read the estate, newest first under a band for each day (UTC,
  // as Azure states it). A row picks the card or frame the change is on; a
  // deleted resource, which has no card, is on its resource group.
  const changeEntries = all => all.filter(row => row.changes)
    .flatMap(row => row.changes.items.map(change => ({row, change})))
    .sort((a, b) => String(b.change.when).localeCompare(String(a.change.when)) || a.row.name.localeCompare(b.row.name));
  const syncChanges = (all, selectedId = selected?.id || null) => {
    const holder = resourcePanel.querySelector('[data-resource-changes]');
    const tab = resourcePanel.querySelector('[data-resource-view="changes"]');
    if (!holder || !tab) return;
    const entries = changeEntries(all);
    tab.hidden = !entries.length;
    if (!entries.length) {
      if (resourcePanel.dataset.view === 'changes') resourcePanel.querySelector('[data-resource-view="resources"]')?.click();
      setMarkup(holder, '');
      return;
    }
    const narrow = resourcePanel.getBoundingClientRect().width < 460;
    const holders = all.filter(row => row.changes);
    const counted = holders.reduce((sum, row) => sum + (Number(row.changes.count) || row.changes.items.length), 0);
    const recent = entries.filter(({row, change}) => (Date.parse(row.changes.read) || Date.now()) - Date.parse(change.when)
      <= RECENT_DAYS * 864e5).length;
    const people = new Set(entries.map(({change}) => change.by).filter(Boolean));
    const read = holders.map(row => row.changes.read).filter(Boolean).sort().at(-1);
    const changeRow = ({row, change}) => {
      // a part's change is said on the card that lists it, naming the part
      const part = change.part && change.part !== row.name ? change.part : '';
      const moves = changeMoves(change);
      const who = changeWho(change);
      return `<tr data-change-row="${escapeText(row.id)}" data-resource-kind="${row.kind}" data-selected="${row.id === (selectedId || '')}">`
        + `<td class="change-time">${escapeText(changeTime(change.when))}</td>`
        + `<td><div class="resource-name">${row.icon ? `<img class="resource-icon" src="${escapeText(row.icon)}"${inkIsDark.get(row.icon) ? ' data-ink-dark' : ''} alt="" loading="lazy">` : '<span class="resource-icon" aria-hidden="true"></span>'}`
        + `<div class="resource-name__text"><strong>${escapeText(`${CHANGE_WORDS[change.kind] || change.kind} ${part || row.name}`)}</strong>`
        + `<small class="resource-type-line">${escapeText(part ? `on ${row.name}` : row.type)}</small>`
        + (narrow ? [...moves, who].filter(Boolean).map(line => `<small class="resource-type-line">${escapeText(line)}</small>`).join('') : '')
        + '</div></div></td>'
        + (narrow ? '' : `<td class="change-what">${moves.map(line => `<span title="${escapeText(line)}">${escapeText(line)}</span>`).join('')}</td>`
          + `<td class="change-who" title="${escapeText(who)}">${escapeText(who)}</td>`)
        + '</tr>';
    };
    const days = new Map();
    entries.forEach(entry => {
      const day = changeDate(entry.change.when, {weekday: 'short', day: 'numeric', month: 'short'});
      if (!days.has(day)) days.set(day, []);
      days.get(day).push(entry);
    });
    const columns = narrow ? 2 : 4;
    setMarkup(holder, '<div class="savings-head">'
      + `<div><span>Changes in 14 days</span><b>${counted}</b><small>on ${holders.length} ${holders.length === 1 ? 'item' : 'items'}</small></div>`
      + `<div><span>Changes in 7 days</span><b>${recent}</b><small>${people.size ? `by ${people.size} ${people.size === 1 ? 'person or app' : 'people or apps'}` : 'by no one Azure named'}</small></div>`
      + `<button type="button" class="md-icon-button md-icon-button--sm" data-changes-csv title="Download the changes as CSV" aria-label="Download the changes as CSV">${resourcePanel.querySelector('[data-resource-csv] svg')?.outerHTML || '↓'}</button>`
      + '</div>'
      + '<div class="resource-table-wrap savings-wrap"><table class="resource-table changes-table"><thead><tr>'
      + '<th scope="col"><span>UTC</span></th><th scope="col"><span>Change</span></th>'
      + (narrow ? '' : '<th scope="col"><span>What changed</span></th><th scope="col"><span>By</span></th>')
      + '</tr></thead><tbody>'
      + [...days].map(([day, members]) => `<tr class="resource-group-row"><td colspan="${columns}"><div class="resource-group-toggle">`
        + `<strong>${escapeText(day)}</strong><span class="resource-group-count">${members.length}</span></div></td></tr>`
        + members.map(changeRow).join('')).join('')
      + '</tbody></table></div>'
      + `<p class="savings-note">Read from Azure Resource Graph${read ? ` on ${escapeText(changeDate(read, {day: 'numeric', month: 'short', year: 'numeric'}))}` : ''}, which keeps fourteen days of changes; each card lists its newest ten.</p>`);
  };
  const changesCsv = () => {
    const head = ['When (UTC)', 'Change', 'Resource', 'On', 'Type', 'What changed', 'By', 'Client'];
    return [head, ...changeEntries(resourceRows()).map(({row, change}) => [change.when, change.kind,
      change.part || row.name, change.part && change.part !== row.name ? row.name : '', row.type,
      changeMoves(change).join('; '), change.by || '', change.client || ''])]
      .map(line => line.map(csvCell).join(',')).join('\r\n') + '\r\n';
  };
  const savingsCsv = () => {
    const rows = savingRows(resourceRows());
    const head = ['Action', 'Resource', 'Type', 'Resource group', 'Why', 'Saves a month', 'Currency', 'Rule'];
    return [head, ...rows.map(row => [row.action, row.name, row.type, row.group, row.unused.reason || '',
      row.saving.toFixed(2), row.currency, row.unused.rule || ''])]
      .map(line => line.map(csvCell).join(',')).join('\r\n') + '\r\n';
  };
  let resourceRowShown = null;
  // Open details: the card's whole story -- its price worked out, its own
  // table, where to read about it -- under the column's facts, for the one
  // card it was asked for. The column scrolls; the map stays in view.
  let detailsShownFor = null;
  // the sheet's size before Open details made it full, to go back to
  let sizeBeforeDetails = null;
  // the close button's cross, as the chrome's icons draw it
  const CLOSE_ICON = resourcePanel?.querySelector('[data-dock-close] svg')?.outerHTML || '×';
  const syncResourceHead = (all, selectedId) => {
    // the selected card, beside the table (over it, as a sheet, when the
    // panel is narrow): its name and what can be done with it, then its facts
    // -- type, group, place, cost, status, what it carries, its tags
    const strip = resourcePanel.querySelector('[data-resource-selected]');
    const node = selectedId ? nodeById(selectedId) : null;
    // a frame with a row (unused, changed, a finding) has its details too
    const frame = !node && selectedId ? boundaryById(selectedId) : null;
    const row = (node || frame) && all.find(item => item.id === (node || frame).id);
    strip.hidden = !row;
    if (!row || detailsShownFor !== row.id) detailsShownFor = null;
    // details closed by picking another card or none: the sheet goes back,
    // scrolled to its top (its peek is measured from there)
    if (!detailsShownFor && sizeBeforeDetails) {
      sheetSize = sizeBeforeDetails;
      sizeBeforeDetails = null;
      strip.scrollTop = 0;
    }
    if (row) {
      // what the strip's buttons act on, kept while a press elsewhere clears the focus
      strip.dataset.resourceId = row.id;
      const parts = node ? attachedParts(node) : [];
      const shown = parts.length && partsShownFor(node).length > 0;
      const tags = Object.entries(row.tags).map(([key, value]) => `${key}=${value}`).join(', ');
      const pick = name => {
        const target = state.nodes.find(item => item.name === name);
        return target ? `<button type="button" class="resource-link" data-pick-resource="${escapeText(target.id)}">${escapeText(name)}</button>`
          : escapeText(name);
      };
      const fact = (label, value, wide = false) => (value
        ? `<div class="resource-fact${wide ? ' resource-fact--wide' : ''}"><dt>${label}</dt><dd>${value}</dd></div>` : '');
      const cost = row.monthly === null ? '' : `${money(row.monthly, row.currency)} a month`;
      const more = node ? elementDetailsBody(node, {attached: false}) : '';
      // what Azure raised about it, worst first, and its newest changes
      const findingItems = (row.findings?.items || []).map(finding => `<li><strong>${escapeText(finding.severity || 'Policy')}</strong> `
        + `${escapeText(finding.title)}${finding.part ? ` <small>on ${escapeText(finding.part)}</small>` : ''}`
        + (finding.detail ? `<small class="resource-signal-detail">${escapeText(finding.detail)}</small>` : '') + '</li>');
      const changeItems = (row.changes?.items || []).slice(0, 5).map(change => `<li><strong>${escapeText(changeLine(change))}</strong>`
        + `${change.part && change.part !== row.name ? ` ${escapeText(change.part)}` : ''}`
        + [...changeMoves(change), changeWho(change)].filter(Boolean).map(line => `<small class="resource-signal-detail">${escapeText(line)}</small>`).join('')
        + '</li>');
      const unlistedChanges = (Number(row.changes?.count) || 0) - changeItems.length;
      if (unlistedChanges > 0) changeItems.push(`<li><small>${unlistedChanges} more in the Changes tab</small></li>`);
      const open = Boolean(more) && detailsShownFor === row.id;
      // narrow, a handle on top drags the sheet between a peek (the name and
      // cost), half the table and all of it; a press steps through them
      setMarkup(strip, '<button type="button" class="md-icon-button resource-sheet-handle" data-sheet-handle title="Drag to resize"></button>'
        + '<div class="resource-selected-head">'
        + `<h3 title="${escapeText(row.name)}">${escapeText(row.name)}</h3>`
        + (cost ? `<span class="resource-selected-cost">${escapeText(cost)}</span>` : '')
        + `<button type="button" class="md-icon-button resource-selected-close" data-selected-close aria-label="Close ${escapeText(row.name)}" title="Close">${CLOSE_ICON}</button>`
        + '<div class="resource-selected-actions">'
        + (more ? `<button type="button" class="md-button md-button--outlined" data-selected-details aria-expanded="${open}">${open ? 'Hide details' : 'Open details'}</button>` : '')
        + (parts.length ? `<button type="button" class="md-button md-button--outlined" data-selected-parts>${shown ? 'Hide attached parts' : `Show attached parts (${parts.length})`}</button>` : '')
        + '</div></div><dl class="resource-facts">'
        + fact('Type', escapeText(row.type))
        + fact('Resource group', escapeText(row.group))
        + fact('Location', escapeText(row.location))
        + fact('Cost', !node ? '' : row.monthly === null ? (row.runsOn ? `Billed through ${pick(row.runsOn)}` : 'Not priced')
          : `${escapeText(money(row.monthly, row.currency))} a month`
          + (row.running ? `, ${escapeText(money(row.running, row.currency))} if started` : ''))
        + fact('Status', row.unused
          ? `<span class="resource-unused">Unused</span>: ${escapeText(row.unused.reason || '')}` : 'In use', Boolean(row.unused))
        + fact('Findings', findingItems.length ? `<ul class="resource-signal-list">${findingItems.join('')}</ul>` : '', true)
        + fact('Changes', changeItems.length ? `<ul class="resource-signal-list">${changeItems.join('')}</ul>` : '', true)
        + fact('Runs on', row.runsOn ? pick(row.runsOn) : '')
        + fact('Hosts', row.hosts.map(pick).join(', '), row.hosts.length > 1)
        + fact('Attached', parts.length ? parts.map(part => escapeText(`${part.role}: ${part.name}`)).join(', ')
          : row.runsOn || row.hosts.length ? '' : escapeText(row.links), true)
        + fact('Tags', !node ? '' : tags ? escapeText(tags) : 'None')
        + '</dl>'
        + (open ? `<div class="element-details" data-selected-more>${more}</div>` : ''));
    }
    fitSheet();
    // the card picked on the map brings its row into view, clear of the
    // sheet; once more after the frame, when a phone's bars have settled
    if (selectedId !== resourceRowShown) {
      resourceRowShown = selectedId;
      const id = CSS.escape(selectedId || '');
      resourcePanel.querySelector(resourcePanel.dataset.view === 'savings' ? `[data-saving-row="${id}"]` : `[data-resource-row="${id}"]`)
        ?.scrollIntoView({block: 'nearest'});
      keepPickedClear();
      requestAnimationFrame(() => requestAnimationFrame(keepPickedClear));
    }
  };
  // A sheet over the table (a narrow panel) has three sizes: a peek of the
  // name and cost; half, as tall as leaves the header and three rows showing
  // over it, or half the table where that is short; and full, over the whole table. The table leaves room under its
  // last row for it, which keeps its totals row clear of it too.
  const SHEET_SIZES = ['peek', 'half', 'full'];
  const SHEET_LABELS = {peek: 'name and cost', half: 'half the table', full: 'the whole table'};
  let sheetSize = 'half';
  const sheetHeights = (strip, wrap) => {
    const room = resourcePanel.getBoundingClientRect().bottom - wrap.getBoundingClientRect().top;
    const row = wrap.querySelector('[data-resource-rows] [data-resource-row]')?.getBoundingClientRect().height || 36;
    const close = strip.querySelector('[data-selected-close]');
    // (measured from the sheet: the sticky name row is the close button's offset parent)
    const peek = Math.round((close ? close.getBoundingClientRect().bottom - strip.getBoundingClientRect().top
      + strip.scrollTop : 56) + 8);
    // (in a short table, such as a phone's under the map, at least half of it)
    const half = Math.round(Math.max(peek, Math.min(340, Math.max(room - 4 * row, room / 2))));
    // full: all of the details, up to the whole table
    return {peek, half, full: Math.round(Math.max(half, Math.min(room, strip.scrollHeight)))};
  };
  // the sizes worth stepping through: full only when it shows more than half
  const sheetSteps = sizes => SHEET_SIZES.filter(size => size !== 'full' || sizes.full - sizes.half > 24);
  const fitSheet = () => {
    const strip = resourcePanel?.querySelector('[data-resource-selected]');
    const wrap = resourcePanel?.querySelector('[data-resource-wrap]');
    if (!strip || !wrap) return;
    const overTable = !strip.hidden && resourcePanel.dataset.compact === 'true';
    if (overTable) {
      if (strip.dataset.sheet !== sheetSize) strip.dataset.sheet = sheetSize;
      strip.querySelector('[data-sheet-handle]')?.setAttribute('aria-label', `Details show ${SHEET_LABELS[sheetSize]}; press to resize`);
      if (!strip.dataset.dragging) {
        const most = `${sheetHeights(strip, wrap)[sheetSize]}px`;
        if (strip.style.maxHeight !== most) strip.style.maxHeight = most;
      }
    } else if (strip.style.maxHeight) strip.style.maxHeight = '';
    // (the sheet hangs 12 px below the panel, over its padding)
    const sheet = overTable ? `${Math.max(0, strip.offsetHeight - 12)}px` : '';
    if (wrap.style.paddingBottom !== sheet) wrap.style.paddingBottom = sheet;
  };
  // the picked row, scrolled to sit between the table's header and the
  // totals row over the sheet (a full sheet hides the table: nothing to do)
  const keepPickedClear = () => {
    const strip = resourcePanel?.querySelector('[data-resource-selected]');
    const wrap = resourcePanel?.querySelector('[data-resource-wrap]');
    const row = resourcePanel?.querySelector('[data-resource-rows] [data-selected="true"]');
    if (!wrap || !row) return;
    // beside the table the details cover nothing; as a sheet they cover its foot
    const sheet = Boolean(strip) && !strip.hidden && resourcePanel.dataset.compact === 'true';
    if (sheet) {
      fitSheet();
      if (sheetSize === 'full') return;
    }
    const box = row.getBoundingClientRect();
    // (the header's and the totals' cells hold their sticky places, not their row groups)
    const head = wrap.querySelector('thead th')?.getBoundingClientRect().bottom ?? wrap.getBoundingClientRect().top;
    const totals = wrap.querySelector('[data-resource-foot]:not([hidden]) td')?.getBoundingClientRect().top ?? Infinity;
    const foot = Math.min(sheet ? strip.getBoundingClientRect().top : Infinity, totals, wrap.getBoundingClientRect().bottom) - 4;
    if (box.bottom > foot) wrap.scrollTop += box.bottom - foot;
    else if (box.top < head) wrap.scrollTop -= head - box.top;
  };
  // The sheet's handle and its name's row: dragged up or down with a thumb,
  // the sheet follows and settles on the nearest size, or closes when pulled
  // well under the peek. The handle pressed (or Enter, Space) steps peek,
  // half, full; the up and down arrows make it bigger or smaller.
  const setSheetSize = size => {
    sheetSize = size;
    fitSheet();
    keepPickedClear();
  };
  if (resourcePanel) {
    let dragged = false;
    resourcePanel.addEventListener('pointerdown', event => {
      // the handle or the name's row, but not a button on it
      const grip = event.target.closest('[data-sheet-handle], .resource-selected-head');
      if (!grip || resourcePanel.dataset.compact !== 'true'
        || event.target.closest('button:not([data-sheet-handle]), .resource-link')) return;
      const strip = resourcePanel.querySelector('[data-resource-selected]');
      const wrap = resourcePanel.querySelector('[data-resource-wrap]');
      const sizes = sheetHeights(strip, wrap);
      const startY = event.clientY;
      const start = strip.offsetHeight;
      dragged = false;
      grip.setPointerCapture(event.pointerId);
      const move = moved => {
        if (!dragged && Math.abs(moved.clientY - startY) < 6) return;
        dragged = true;
        strip.dataset.dragging = 'true';
        // below the peek it keeps following the finger down, to close
        strip.style.maxHeight = `${Math.round(Math.max(24, Math.min(sizes.full, start + startY - moved.clientY)))}px`;
      };
      const end = () => {
        grip.removeEventListener('pointermove', move);
        grip.removeEventListener('pointerup', end);
        grip.removeEventListener('pointercancel', end);
        delete strip.dataset.dragging;
        if (!dragged) return;
        const height = strip.offsetHeight;
        // pulled well under the peek, the details close; the next pick opens at half
        if (height < sizes.peek - 32) {
          sheetSize = 'half';
          clearSelection();
          renderGraph();
          return;
        }
        setSheetSize(sheetSteps(sizes).reduce((best, size) => (Math.abs(sizes[size] - height) < Math.abs(sizes[best] - height) ? size : best)));
      };
      grip.addEventListener('pointermove', move);
      grip.addEventListener('pointerup', end);
      grip.addEventListener('pointercancel', end);
    });
    resourcePanel.addEventListener('click', event => {
      if (!event.target.closest('[data-sheet-handle]')) return;
      // a drag ends in a click as well: the drag has already settled it
      if (dragged) { dragged = false; return; }
      const steps = sheetSteps(sheetHeights(resourcePanel.querySelector('[data-resource-selected]'), resourcePanel.querySelector('[data-resource-wrap]')));
      setSheetSize(steps[(steps.indexOf(sheetSize) + 1) % steps.length]);
    });
    resourcePanel.addEventListener('keydown', event => {
      if (!event.target.closest('[data-sheet-handle]') || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
      event.preventDefault();
      const steps = sheetSteps(sheetHeights(resourcePanel.querySelector('[data-resource-selected]'), resourcePanel.querySelector('[data-resource-wrap]')));
      const at = steps.indexOf(sheetSize) + (event.key === 'ArrowUp' ? 1 : -1);
      setSheetSize(steps[Math.max(0, Math.min(steps.length - 1, at))]);
    });
  }
  // a cell a spreadsheet would run as a formula (=, +, -, @ first) is
  // written as text; a negative number stays a number
  const csvCell = value => {
    let text = String(value ?? '');
    if (/^[=+\-@\t\r]/.test(text) && !/^-?\d[\d.,]*$/.test(text)) text = `'${text}`;
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const resourceCsv = () => {
    const rows = sortedResources(resourceRows().filter(resourceMatches));
    const head = ['Name', 'Type', 'Resource group', 'Location', 'Attached', 'Monthly', 'Currency',
      'If started', 'Unused', 'Unused reason', 'Still billed', 'Findings', 'Last changed', 'Changes in 14 days', 'Tags'];
    return [head, ...rows.map(row => [row.name, row.type, row.group, row.location, row.links,
      row.monthly === null ? '' : row.monthly.toFixed(2), row.currency, row.running ? row.running.toFixed(2) : '',
      row.unused?.rule || '', row.unused?.reason || '', row.unused?.bills || '', findingSummary(row.findings),
      row.lastChange, row.changes ? String(row.changes.count) : '', tagText(row.tags)])]
      .map(line => line.map(csvCell).join(',')).join('\r\n') + '\r\n';
  };
  // The table's columns. Name is always shown; the rest are ticked on or
  // off in the Display menu and remembered for each place the table sits --
  // beside the map, under it, or alone -- and until then chosen by the width
  // the table has.
  const COLUMN_LABELS = {type: 'Type', group: 'Group', location: 'Location', links: 'Attached',
    monthly: 'A month', unused: 'Unused', findings: 'Findings', changed: 'Changed', tags: 'Tags'};
  // a column's width: fixed, or a floor and a share of the room left over
  const COLUMN_WIDTHS = {name: {floor: 168, share: 3}, type: {fixed: 152}, group: {fixed: 112},
    location: {fixed: 96}, links: {floor: 112, share: 2}, monthly: {fixed: 104},
    unused: {floor: 112, share: 3}, findings: {floor: 128, share: 1.5}, changed: {fixed: 136},
    tags: {floor: 96, share: 1.5}};
  // Findings and Changed show by default only where an import read them
  const SIGNAL_COLUMNS = {findings: hasFindings, changed: item => Boolean(itemChanges(item))};
  const signalColumns = () => Object.keys(SIGNAL_COLUMNS)
    .filter(key => [...state.nodes, ...state.boundaries].some(SIGNAL_COLUMNS[key]));
  // Narrow (a phone, a side dock), the table shows what a wide one does but
  // the attachments and tags, the cost and status first after the name and
  // the rest scrolling in under the frozen name, the next one's edge in sight.
  const defaultColumns = width => {
    const read = signalColumns();
    return width < 1100 ? ['type', 'group', 'location', 'monthly', 'unused', ...read]
      : width < 1400 ? ['type', 'group', 'location', 'links', 'monthly', 'unused', ...read]
        : Object.keys(COLUMN_LABELS).filter(key => !(key in SIGNAL_COLUMNS) || read.includes(key));
  };
  const columnPlace = () => (document.body.dataset.dockMode === 'table' ? 'table' : document.body.dataset.dock || 'bottom');
  const savedColumns = () => {
    const saved = layoutState.inventoryColumns?.[columnPlace()];
    return Array.isArray(saved) ? saved.filter(key => key in COLUMN_LABELS) : null;
  };
  const shownColumns = () => savedColumns() || defaultColumns(resourcePanel.getBoundingClientRect().width);
  const COLUMN_ORDER = {wide: ['name', 'type', 'group', 'location', 'links', 'monthly', 'unused', 'findings', 'changed', 'tags'],
    narrow: ['name', 'monthly', 'unused', 'findings', 'changed', 'type', 'group', 'location', 'links', 'tags']};
  const columnOrder = () => COLUMN_ORDER[resourcePanel?.dataset.compact === 'true' ? 'narrow' : 'wide'];
  // Each shown column takes its fixed width or its floor, and the floors
  // share what room is left; narrower than that, the table scrolls sideways
  // under its frozen Name column.
  const sizeColumns = () => {
    const wrap = resourcePanel?.querySelector('[data-resource-wrap]');
    const table = wrap?.querySelector('[data-resource-table]');
    const room = wrap?.clientWidth || 0;
    if (!room) return;
    const compact = resourcePanel.dataset.compact === 'true';
    // narrow, Unused says only the word, its reason on hover, and the name
    // and type give a little room to the columns after them
    const NARROW = {unused: {fixed: 88}, name: {floor: 156, share: 3}, type: {fixed: 136},
      findings: {fixed: 128}, changed: {fixed: 128}};
    const spec = key => (compact && NARROW[key]) || COLUMN_WIDTHS[key];
    const keys = ['name', ...shownColumns()];
    const total = (field, fallback = 0) => keys.reduce((sum, key) => sum + (spec(key)[field] ?? fallback), 0);
    const fixed = total('fixed') + total('floor');
    const width = Math.max(room, fixed);
    const shares = total('share');
    keys.forEach(key => {
      const th = table.querySelector(`thead th[data-col="${key}"]`);
      const own = spec(key);
      const size = own.fixed ?? Math.floor(own.floor + (shares ? (width - fixed) * own.share / shares : 0));
      if (th && th.style.width !== `${size}px`) th.style.width = `${size}px`;
      // too narrow for a reason to read, Unused says the word alone
      if (key === 'unused') resourcePanel.dataset.unusedShort = String(size < 200);
    });
    if (table.style.width !== `${width}px`) table.style.width = `${width}px`;
  };
  const applyColumns = () => {
    if (!resourcePanel) return false;
    const columns = shownColumns();
    const order = columnOrder();
    const shown = columns.join(' ');
    const changed = resourcePanel.dataset.columns !== shown || resourcePanel.dataset.columnOrder !== order.join(' ');
    resourcePanel.dataset.columns = shown;
    resourcePanel.dataset.lastColumn = order.filter(key => key === 'name' || columns.includes(key)).at(-1);
    // the header's and the totals' cells follow the order; the rows are drawn in it
    if (resourcePanel.dataset.columnOrder !== order.join(' ')) {
      resourcePanel.dataset.columnOrder = order.join(' ');
      resourcePanel.querySelectorAll('[data-resource-table] thead tr, [data-resource-foot] tr').forEach(line => {
        order.forEach(key => {
          const cell = line.querySelector(`:scope > [data-col="${key}"]`);
          if (cell) line.append(cell);
        });
      });
    }
    sizeColumns();
    return changed;
  };
  // Filters and Display: a button that opens its panel under it, held
  // inside the window; Escape and a press elsewhere close it.
  const menuPanel = (holder, panel, toggle, onOpen = () => {}) => {
    if (!holder || !panel || !toggle) return;
    const close = () => {
      if (panel.hidden) return;
      panel.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      document.removeEventListener('pointerdown', outside, true);
      document.removeEventListener('keydown', onEscape, true);
    };
    const outside = event => { if (!holder.contains(event.target)) close(); };
    // Escape closes it wherever the focus is, and gives the focus back to its button
    const onEscape = event => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      close();
      toggle.focus();
    };
    toggle.addEventListener('click', () => {
      if (!panel.hidden) { close(); return; }
      onOpen();
      panel.hidden = false;
      panel.style.left = '';
      // as tall as the room under the button, scrolling within it only past that
      panel.style.maxHeight = `${Math.max(160, innerHeight - toggle.getBoundingClientRect().bottom - 16)}px`;
      // past the window's edge it hangs from its button's right edge, as the
      // header's menus do, and never past the window's left edge
      const box = panel.getBoundingClientRect();
      if (box.right > document.documentElement.clientWidth - 8) {
        const shift = Math.min(box.right - toggle.getBoundingClientRect().right, box.left - 8);
        panel.style.left = `${-shift}px`;
      }
      toggle.setAttribute('aria-expanded', 'true');
      document.addEventListener('pointerdown', outside, true);
      document.addEventListener('keydown', onEscape, true);
    });
  };
  const revealRow = item => {
    const origin = canvasOrigin();
    const left = origin.x + item.x * zoom - viewport.scrollLeft;
    const top = origin.y + item.y * zoom - viewport.scrollTop;
    const inView = left >= 0 && top >= 0
      && left + item.width * zoom <= viewport.clientWidth
      && top + item.height * zoom <= viewport.clientHeight;
    if (!inView) revealNode(item);
  };
  // Pick a resource as a click on its row does: the map outlines it and the
  // table marks it. Savings, Changes and the details' links call it too, so
  // a row the search hides or a folded band holds is picked all the same.
  const pickResource = (id, kind = 'node') => {
    if (kind === 'boundary') {
      const frame = boundaryById(id);
      if (!frame) return;
      selectBoundary(frame.id);
      document.body.dataset.pickedInTable = 'true';
      revealRow(frame);
      renderGraph();
      return;
    }
    const node = nodeById(id);
    if (!node) return;
    // A row picked in the table is looked at, not edited: the map outlines
    // it, and the editing bar, the dots and the grips wait for a press on
    // the map itself. Its details are the panel's own; Open details lists
    // the rest under them.
    selectNode(node.id);
    document.body.dataset.pickedInTable = 'true';
    revealRow(node);
    renderGraph();
  };
  const pickById = id => pickResource(id, boundaryById(id) ? 'boundary' : 'node');
  if (resourcePanel) {
    // the search, with a cross to empty it once something is typed; / goes
    // to it from anywhere but a field
    const search = resourcePanel.querySelector('[data-resource-search]');
    const searchClear = resourcePanel.querySelector('[data-resource-search-clear]');
    const setQuery = value => {
      resourceView.query = value;
      if (search.value !== value) search.value = value;
      searchClear.hidden = !value;
      syncResources();
    };
    search.addEventListener('input', () => setQuery(search.value));
    searchClear.addEventListener('click', () => {
      setQuery('');
      search.focus();
    });
    document.addEventListener('keydown', event => {
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
        || document.activeElement?.isContentEditable;
      if (event.key !== '/' || typing || event.ctrlKey || event.metaKey || event.altKey) return;
      // a dialog over the page owns the keyboard (26-keyboard.js)
      if (document.querySelector('[aria-modal="true"]')) return;
      if (!resourcePanel.getClientRects().length) return;
      event.preventDefault();
      if (resourcePanel.dataset.view !== 'resources') resourcePanel.querySelector('[data-resource-view="resources"]')?.click();
      search.focus();
      search.select();
    });
    resourcePanel.querySelectorAll('[data-resource-type],[data-resource-group]').forEach(select => {
      select.addEventListener('change', syncResources);
    });
    // a ticked row is the filter; ticking it again clears it
    resourcePanel.querySelector('[data-resource-filters-panel]')?.addEventListener('click', event => {
      const choice = event.target.closest('[data-filter-value]');
      const select = choice?.closest('.resource-filter-section')?.querySelector('select');
      if (!select) return;
      select.value = select.value === choice.dataset.filterValue ? '' : choice.dataset.filterValue;
      select.dispatchEvent(new Event('change', {bubbles: true}));
    });
    // Resources, Savings or Changes, remembered with the layout; Changes
    // only where an import read some (syncChanges hides its tab elsewhere)
    const showView = view => {
      const chosen = ['savings', 'changes'].includes(view) ? view : 'resources';
      resourcePanel.dataset.view = chosen;
      resourcePanel.querySelectorAll('[data-resource-view]').forEach(tab => {
        tab.setAttribute('aria-selected', String(tab.dataset.resourceView === chosen));
      });
      resourcePanel.querySelector('[data-resource-savings]').hidden = chosen !== 'savings';
      resourcePanel.querySelector('[data-resource-changes]').hidden = chosen !== 'changes';
    };
    showView(layoutState.inventoryView);
    resourcePanel.querySelector('.resource-views')?.addEventListener('click', event => {
      const tab = event.target.closest('[data-resource-view]');
      if (!tab) return;
      layoutState.inventoryView = tab.dataset.resourceView;
      persistLayout();
      showView(tab.dataset.resourceView);
      // a slim dock scrolls the tabs sideways, with no bar: the one picked
      // comes fully into sight
      tab.scrollIntoView({block: 'nearest', inline: 'nearest'});
      syncResources();
    });
    resourcePanel.querySelector('[data-resource-savings]')?.addEventListener('click', event => {
      if (event.target.closest('[data-savings-csv]')) {
        const link = document.createElement('a');
        link.href = URL.createObjectURL(new Blob(['\uFEFF', savingsCsv()], {type: 'text/csv;charset=utf-8'}));
        link.download = `${originalProject.slug || 'diagram'}-savings.csv`;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(link.href), 0);
        return;
      }
      // a saving's row picks its resource, as the table's rows do
      const row = event.target.closest('[data-saving-row]');
      if (row) pickById(row.dataset.savingRow);
    });
    resourcePanel.querySelector('[data-resource-changes]')?.addEventListener('click', event => {
      if (event.target.closest('[data-changes-csv]')) {
        const link = document.createElement('a');
        link.href = URL.createObjectURL(new Blob(['\uFEFF', changesCsv()], {type: 'text/csv;charset=utf-8'}));
        link.download = `${originalProject.slug || 'diagram'}-changes.csv`;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(link.href), 0);
        return;
      }
      // a change's row picks what it is on, as the table's rows do
      const row = event.target.closest('[data-change-row]');
      if (row) pickById(row.dataset.changeRow);
    });
    const groupBy = resourcePanel.querySelector('[data-resource-groupby]');
    const groupChoices = resourcePanel.querySelector('[data-groupby-choices]');
    const columnChoices = resourcePanel.querySelector('[data-column-choices]');
    const sortChoices = resourcePanel.querySelector('[data-sort-choices]');
    // the Display menu: one choice of grouping, and a tick per column
    const renderDisplay = () => {
      setMarkup(groupChoices, [...groupBy.options].map(option => '<button type="button" class="md-list-item filter-choice"'
        + ` data-groupby-value="${escapeText(option.value)}" role="radio" aria-checked="${option.value === groupBy.value}">`
        + `<span class="filter-check filter-check--radio" aria-hidden="true"></span><span class="md-list-item__label">${escapeText(option.textContent)}</span></button>`).join(''));
      const shown = shownColumns();
      // in the order the table shows them
      setMarkup(columnChoices, columnOrder().filter(key => key in COLUMN_LABELS).map(key => [key, COLUMN_LABELS[key]]).map(([key, label]) => '<button type="button" class="md-list-item filter-choice"'
        + ` data-column="${key}" aria-pressed="${shown.includes(key)}"><span class="filter-check" aria-hidden="true"></span>`
        + `<span class="md-list-item__label">${escapeText(label)}</span></button>`).join(''));
      resourcePanel.querySelector('[data-columns-reset]').disabled = !savedColumns();
      // by any column, the headers' arrows or not: the chosen one says its order,
      // and choosing it again turns the order round
      setMarkup(sortChoices, Object.entries({name: 'Name', ...COLUMN_LABELS}).map(([key, label]) => {
        const chosen = resourceView.sort === key;
        return '<button type="button" class="md-list-item filter-choice"'
          + ` data-sort-value="${key}" role="radio" aria-checked="${chosen}">`
          + `<span class="filter-check filter-check--radio" aria-hidden="true"></span><span class="md-list-item__label">${escapeText(label)}</span>`
          + (chosen ? `<span class="filter-count">${escapeText(sortOrder(key, resourceView.descending))}</span>` : '') + '</button>';
      }).join(''));
    };
    // remembered with the page's layout, as the dock is
    groupBy.value = ['group', 'type', 'tied', 'status'].includes(layoutState.inventoryGroupBy) ? layoutState.inventoryGroupBy : '';
    resourceView.groupBy = groupBy.value;
    groupBy.addEventListener('change', () => {
      resourceView.groupBy = groupBy.value;
      resourceView.folded.clear();
      layoutState.inventoryGroupBy = groupBy.value;
      persistLayout();
      syncResources();
      renderDisplay();
    });
    const setColumns = keys => {
      const columns = {...(layoutState.inventoryColumns || {})};
      if (keys) columns[columnPlace()] = Object.keys(COLUMN_LABELS).filter(key => keys.includes(key));
      else delete columns[columnPlace()];
      layoutState.inventoryColumns = columns;
      persistLayout();
      syncResources();
      renderDisplay();
    };
    resourcePanel.querySelector('[data-resource-display-panel]')?.addEventListener('click', event => {
      const grouping = event.target.closest('[data-groupby-value]');
      const column = event.target.closest('[data-column]');
      const sorting = event.target.closest('[data-sort-value]');
      // the rows are drawn again: the one pressed keeps the focus
      if (sorting) {
        sortBy(sorting.dataset.sortValue);
        renderDisplay();
        sortChoices.querySelector(`[data-sort-value="${sorting.dataset.sortValue}"]`)?.focus();
      } else if (grouping) {
        const value = grouping.dataset.groupbyValue;
        groupBy.value = value;
        groupBy.dispatchEvent(new Event('change'));
        groupChoices.querySelector(`[data-groupby-value="${CSS.escape(value)}"]`)?.focus();
      } else if (column) {
        const shown = shownColumns();
        const key = column.dataset.column;
        setColumns(shown.includes(key) ? shown.filter(item => item !== key) : [...shown, key]);
        columnChoices.querySelector(`[data-column="${key}"]`)?.focus();
      } else if (event.target.closest('[data-columns-reset]')) {
        setColumns(null);
        columnChoices.querySelector('[data-column]')?.focus();
      }
    });
    menuPanel(resourcePanel.querySelector('[data-resource-display-menu]'), resourcePanel.querySelector('[data-resource-display-panel]'),
      resourcePanel.querySelector('[data-resource-display-toggle]'), renderDisplay);
    resourcePanel.querySelectorAll('[data-resource-only]').forEach(chip => chip.addEventListener('click', () => {
      const key = chip.dataset.resourceOnly;
      if (resourceView.only.has(key)) resourceView.only.delete(key);
      else resourceView.only.add(key);
      chip.setAttribute('aria-pressed', String(resourceView.only.has(key)));
      syncResources();
    }));
    menuPanel(resourcePanel.querySelector('[data-resource-filters-menu]'), resourcePanel.querySelector('[data-resource-filters-panel]'),
      resourcePanel.querySelector('[data-resource-filters-toggle]'));
    const clearFilters = () => {
      resourceView.only.clear();
      resourcePanel.querySelectorAll('[data-resource-only]').forEach(chip => chip.setAttribute('aria-pressed', 'false'));
      resourcePanel.querySelectorAll('[data-resource-type],[data-resource-group]').forEach(select => {
        select.value = '';
      });
    };
    resourcePanel.querySelector('[data-resource-filters-clear]')?.addEventListener('click', () => {
      clearFilters();
      syncResources();
    });
    // the empty table's button and the count's Clear: the search and the filters both
    const clearAll = () => {
      clearFilters();
      setQuery('');
    };
    resourcePanel.querySelector('[data-resource-clear]')?.addEventListener('click', clearAll);
    resourcePanel.querySelector('[data-resource-summary]')?.addEventListener('click', event => {
      if (!event.target.closest('[data-resource-clear-all]')) return;
      clearAll();
      search.focus();
    });
    resourcePanel.querySelectorAll('[data-resource-sort]').forEach(button => button.addEventListener('click', () => {
      sortBy(button.dataset.resourceSort);
    }));
    resourcePanel.querySelector('[data-resource-csv]').addEventListener('click', () => {
      const link = document.createElement('a');
      link.href = URL.createObjectURL(new Blob(['\uFEFF', resourceCsv()], {type: 'text/csv;charset=utf-8'}));
      link.download = `${originalProject.slug || 'diagram'}-resources.csv`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 0);
    });
    // a row is the card: select it, bring it into view, open its details.
    // A card already on screen stays where it is, and the map keeps its fit.
    // With the sheet focused the arrow keys walk its rows, picking each as a
    // click does, and Enter opens the picked one's details.
    resourcePanel.querySelector('[data-resource-wrap]')?.addEventListener('keydown', event => {
      if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key) || event.target.closest('button,input')) return;
      const rows = [...resourcePanel.querySelectorAll('[data-resource-row]')];
      if (!rows.length) return;
      event.preventDefault();
      const at = rows.findIndex(row => row.dataset.selected === 'true');
      if (event.key === 'Enter') {
        if (at >= 0 && rows[at].dataset.resourceKind === 'node' && detailsShownFor !== rows[at].dataset.resourceRow) {
          resourcePanel.querySelector('[data-selected-details]')?.click();
        }
        return;
      }
      const next = rows[event.key === 'ArrowDown' ? Math.min(rows.length - 1, at + 1) : Math.max(0, at < 0 ? 0 : at - 1)];
      next.click();
      resourcePanel.querySelector(`[data-resource-row="${CSS.escape(next.dataset.resourceRow)}"]`)?.scrollIntoView({block: 'nearest'});
    });
    resourcePanel.querySelector('[data-resource-rows]').addEventListener('click', event => {
      const header = event.target.closest('[data-resource-group-key]');
      if (header) {
        const key = header.dataset.resourceGroupKey;
        if (resourceView.folded.has(key)) resourceView.folded.delete(key);
        else resourceView.folded.add(key);
        syncResources();
        return;
      }
      const row = event.target.closest('[data-resource-row]');
      if (row) pickResource(row.dataset.resourceRow, row.dataset.resourceKind);
    });
  }

  // The inventory dock. The Resources panel is one element, moved between a
  // column beside the map (right) and the bottom drawer (bottom); a divider
  // resizes whichever it is, Split shows map and table, Table gives the
  // table the room, and Map (or closing it) gives the map the room. Where it
  // was, how big and in which mode is remembered with the rest of the layout.
  // An inventory -- a page drawn from Azure, whose cards carry a Resource ID
  // -- opens docked beside the map on a wide screen and under it otherwise,
  // in review: the library and the inspector folded away until Edit.
  const dockAside = document.querySelector('[data-resource-dock]');
  const resourceHome = resourcePanel?.parentElement || null;
  const dockDividers = {
    right: document.querySelector('[data-dock-divider="right"]'),
    bottom: document.querySelector('[data-dock-divider="bottom"]'),
  };
  const inventoryToggle = document.querySelector('[data-inventory-toggle]');
  const editToggle = document.querySelector('[data-edit-mode]');
  const looksLikeInventory = () => state.nodes.some(node => tableValue(node, 'Resource ID'));
  const DOCK_LIMITS = {right: [320, 1400], bottom: [180, 1200]};
  // The dock's size follows the screen until the reader sets one with the
  // divider: beside the map, 30% of the window's width (360 to 720 px);
  // under it, 42% of its height (220 to 560 px), and on a phone as tall as
  // leaves the map its 240 px, so the sheet opens on a page of rows. A size
  // set by hand is kept, and held inside the window when the window shrinks.
  const clampTo = (value, [least, most]) => Math.max(least, Math.min(most, value));
  const autoDock = {
    right: () => clampTo(Math.round(window.innerWidth * 0.3), [360, 720]),
    bottom: () => (phoneLayout() ? 560 : clampTo(Math.round(window.innerHeight * 0.42), [220, 560])),
  };
  const dockState = {open: false, side: 'right', mode: 'split', right: null, bottom: null, custom: {}, review: false,
    ...(layoutState.dock && typeof layoutState.dock === 'object' ? layoutState.dock : {})};
  dockState.custom = dockState.custom && typeof dockState.custom === 'object' ? dockState.custom : {};
  if (!layoutState.dock) {
    const inventory = looksLikeInventory() && !phoneLayout();
    Object.assign(dockState, {open: inventory, review: inventory,
      side: window.innerWidth >= 1280 ? 'right' : 'bottom'});
  }
  const dockSize = side => {
    const auto = autoDock[side]();
    if (!dockState.custom[side] || !Number(dockState[side])) return auto;
    const room = side === 'right' ? window.innerWidth * 0.55 : window.innerHeight * 0.6;
    return clampTo(Number(dockState[side]), [DOCK_LIMITS[side][0], Math.max(DOCK_LIMITS[side][0], room)]);
  };
  const saveDock = () => {
    layoutState.dock = {...dockState};
    persistLayout();
  };
  const showDrawerPanel = target => {
    document.querySelectorAll('[data-bottom-tab]').forEach(item => {
      item.setAttribute('aria-selected', String(item.dataset.bottomTab === target));
    });
    document.querySelectorAll('[data-bottom-drawer] [data-bottom-panel]').forEach(panel => {
      panel.hidden = panel.dataset.bottomPanel !== target;
    });
    if (bottomDrawer) bottomDrawer.dataset.panel = target;
  };
  // Below 1280 px there is no room for a column beside the map: the
  // inventory goes under it whatever was chosen, and goes back beside it
  // when the window widens again.
  const narrowWindow = () => window.innerWidth < 1280;
  const applyDock = ({refit = true} = {}) => {
    if (!resourcePanel || !dockAside || !resourceHome) return;
    const open = dockState.open && dockState.mode !== 'map';
    const side = narrowWindow() ? 'bottom' : dockState.side;
    document.body.style.setProperty('--dock-right', `${Math.round(dockSize('right'))}px`);
    document.body.style.setProperty('--dock-bottom', `${Math.round(dockSize('bottom'))}px`);
    if (open) {
      document.body.dataset.dock = side;
      document.body.dataset.dockMode = dockState.mode;
    } else {
      delete document.body.dataset.dock;
      delete document.body.dataset.dockMode;
    }
    const right = open && side === 'right';
    const bottom = open && side === 'bottom';
    if (right) {
      if (resourcePanel.parentElement !== dockAside) dockAside.append(resourcePanel);
      // the drawer keeps its other panels; it no longer holds this one
      // (switching them hides every panel but one, this one too: so first)
      if (bottomDrawer?.dataset.panel === 'resources') {
        showDrawerPanel('examples');
        if (layoutState.bottomExpanded) setBottomExpanded(false);
      }
      resourcePanel.hidden = false;
    } else if (resourcePanel.parentElement !== resourceHome) {
      resourceHome.append(resourcePanel);
    }
    if (bottom) {
      showDrawerPanel('resources');
      if (!layoutState.bottomExpanded) setBottomExpanded(true);
    } else if (!right && bottomDrawer?.dataset.panel === 'resources' && dockState.mode === 'map') {
      setBottomExpanded(false);
    }
    dockAside.hidden = !right;
    dockDividers.right.hidden = !right || dockState.mode !== 'split';
    dockDividers.bottom.hidden = !bottom || dockState.mode !== 'split';
    // one switch of three: beside the map, under it, or the table alone
    // (which keeps the side it was opened on)
    resourcePanel.querySelectorAll('[data-dock-side]').forEach(button => {
      button.setAttribute('aria-pressed', String(dockState.mode !== 'table' && button.dataset.dockSide === side));
      button.disabled = button.dataset.dockSide === 'right' && narrowWindow();
    });
    resourcePanel.querySelectorAll('[data-dock-mode]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.dockMode === dockState.mode));
    });
    inventoryToggle?.setAttribute('aria-pressed', String(open));
    if (refit) requestAnimationFrame(() => fitZoom());
  };
  // a window resized -- or a page opened on another screen -- takes the
  // dock with it: its side below 1280 px, its size by the rules above
  let narrowShown = narrowWindow();
  let resizeFrame = 0;
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      const crossed = narrowWindow() !== narrowShown;
      narrowShown = narrowWindow();
      applyDock({refit: crossed});
      if (crossed) syncResources();
    });
  });
  const setDock = changes => {
    Object.assign(dockState, changes);
    applyDock();
    saveDock();
    syncResources();
  };
  // Review: the map and the inventory, with the library and the inspector
  // folded away; Edit brings both back.
  const applyReview = () => {
    const review = Boolean(dockState.review);
    document.body.classList.toggle('review-mode', review);
    editToggle?.setAttribute('aria-pressed', String(!review));
    if (review) {
      document.body.classList.add('sidebar-collapsed');
      document.body.classList.remove('sidebar-preview');
      setInspectorCollapsed(true);
    } else {
      // four columns -- library, map, inventory, inspector -- need a wide
      // screen; narrower, the library stays on its rail, a press away. On a
      // phone the library is a drawer over everything: it waits to be asked
      // for, and the inspector's sheet waits while the inventory's is open.
      const inventoryOpen = dockState.open && dockState.mode !== 'map';
      const crowded = phoneLayout() || (inventoryOpen && dockState.side === 'right' && window.innerWidth < 1700);
      document.body.classList.toggle('sidebar-collapsed', crowded);
      setInspectorCollapsed(phoneLayout() && inventoryOpen);
    }
    updateSidebarTrigger();
  };
  editToggle?.addEventListener('click', () => {
    dockState.review = !dockState.review;
    applyReview();
    saveDock();
    requestAnimationFrame(() => fitZoom());
  });
  inventoryToggle?.addEventListener('click', () => {
    const open = dockState.open && dockState.mode !== 'map';
    // a phone has room for one sheet under the map: the inventory's, now
    if (!open && phoneLayout()) setInspectorCollapsed(true);
    setDock(open ? {open: false} : {open: true, mode: dockState.mode === 'map' ? 'split' : dockState.mode});
  });
  // ... and the inspector's, when a card is opened for editing (a double
  // tap, the context menu): the inventory closes to make way for it
  new MutationObserver(() => {
    if (!phoneLayout() || document.body.classList.contains('inspector-collapsed')) return;
    if (dockState.open && dockState.mode !== 'map') setDock({open: false});
  }).observe(document.body, {attributes: true, attributeFilter: ['class']});
  // the drawer's Resources tab docks it under the map
  document.querySelector('[data-bottom-tab="resources"]')?.addEventListener('click', () => {
    setDock({open: true, side: 'bottom', mode: dockState.mode === 'map' ? 'split' : dockState.mode});
  });
  // folding the drawer while the inventory is in it gives the map the room
  bottomToggle?.addEventListener('click', () => {
    if (dockState.open && dockState.side === 'bottom' && !layoutState.bottomExpanded) {
      setDock({mode: 'map'});
    }
  });
  if (resourcePanel) {
    resourcePanel.addEventListener('click', event => {
      const side = event.target.closest('button[data-dock-side]');
      const mode = event.target.closest('button[data-dock-mode]');
      if (side) setDock({open: true, side: side.dataset.dockSide, mode: 'split'});
      else if (mode) setDock({open: true, mode: mode.dataset.dockMode});
      else if (event.target.closest('[data-dock-close]')) setDock({open: false});
      else if (event.target.closest('[data-pick-resource]')) {
        pickById(event.target.closest('[data-pick-resource]').dataset.pickResource);
      } else if (event.target.closest('[data-selected-parts]')) {
        const id = resourcePanel.querySelector('[data-resource-selected]').dataset.resourceId;
        if (id) toggleAttachedParts(id);
      } else if (event.target.closest('[data-selected-close]')) {
        clearSelection();
        renderGraph();
      } else if (event.target.closest('[data-selected-details]')) {
        const id = resourcePanel.querySelector('[data-resource-selected]').dataset.resourceId;
        detailsShownFor = detailsShownFor === id ? null : id || null;
        renderGraph();
        resourcePanel.querySelector('[data-selected-details]')?.focus();
        // over the table (a phone, a narrow dock) the sheet opens as tall as
        // what was opened, up to the whole table, so it can be read rather
        // than glimpsed a line at a time; hidden again, it goes back
        if (resourcePanel.dataset.compact === 'true') {
          if (detailsShownFor) {
            sizeBeforeDetails = sizeBeforeDetails || sheetSize;
            setSheetSize('full');
          } else if (sizeBeforeDetails) {
            setSheetSize(sizeBeforeDetails);
            sizeBeforeDetails = null;
          }
        }
        // and the column scrolls to it, under the name that stays on top
        const strip = resourcePanel.querySelector('[data-resource-selected]');
        const more = strip.querySelector('[data-selected-more]');
        const head = strip.querySelector('.resource-selected-head');
        // twice: the name sticks only once the column has scrolled under it
        for (let pass = 0; more && head && pass < 2; pass += 1) {
          strip.scrollTop += more.getBoundingClientRect().top - head.getBoundingClientRect().bottom - 8;
        }
      }
    });
  }
  // The divider: dragged, or moved 24 px at a time with the arrow keys.
  Object.entries(dockDividers).forEach(([side, divider]) => {
    if (!divider) return;
    const resize = size => {
      const [least, most] = DOCK_LIMITS[side];
      // the map keeps 40% of the workbench, up to 480 px, as the grid does
      const bench = document.querySelector('.editor-workbench').getBoundingClientRect().width;
      const room = side === 'right'
        ? bench - Math.min(480, bench * 0.4) - 8
        : window.innerHeight - document.querySelector('.editor-header').getBoundingClientRect().height - 160;
      dockState[side] = Math.max(least, Math.min(most, room, size));
      dockState.custom = {...dockState.custom, [side]: true};
      document.body.style.setProperty(`--dock-${side}`, `${Math.round(dockState[side])}px`);
    };
    divider.addEventListener('pointerdown', event => {
      event.preventDefault();
      divider.setPointerCapture(event.pointerId);
      divider.dataset.dragging = 'true';
      const edge = side === 'right'
        ? dockAside.getBoundingClientRect().right
        : bottomDrawer.getBoundingClientRect().bottom;
      const move = moved => resize(side === 'right' ? edge - moved.clientX : edge - moved.clientY);
      const end = () => {
        divider.removeEventListener('pointermove', move);
        divider.removeEventListener('pointerup', end);
        divider.removeEventListener('pointercancel', end);
        delete divider.dataset.dragging;
        saveDock();
        requestAnimationFrame(() => fitZoom());
      };
      divider.addEventListener('pointermove', move);
      divider.addEventListener('pointerup', end);
      divider.addEventListener('pointercancel', end);
    });
    divider.addEventListener('keydown', event => {
      const grow = side === 'right' ? 'ArrowLeft' : 'ArrowUp';
      const shrink = side === 'right' ? 'ArrowRight' : 'ArrowDown';
      if (event.key !== grow && event.key !== shrink) return;
      event.preventDefault();
      resize(dockSize(side) + (event.key === grow ? 24 : -24));
      saveDock();
      requestAnimationFrame(() => fitZoom());
    });
  });
  applyDock({refit: false});
  if (layoutState.dock || dockState.review) applyReview();
  // Narrower than a full table (beside the map, or under it on a phone),
  // the panel keeps the columns a comparison needs, the toolbar takes a row
  // of its own and a picked resource opens over the table as a sheet.
  if (resourcePanel) {
    new ResizeObserver(() => {
      const width = resourcePanel.getBoundingClientRect().width;
      if (!width) return;
      const compact = String(width < 680);
      const compactChanged = compact !== resourcePanel.dataset.compact;
      resourcePanel.dataset.compact = compact;
      // taller or shorter (a phone's bars come and go): the sheet refits,
      // and the picked row stays clear of it
      keepPickedClear();
      fitSheet();
      // a phone's search field says only what it is
      const search = resourcePanel.querySelector('[data-resource-search]');
      const hint = width < 460 ? 'Search' : 'Search name, type, group, tag';
      if (search.placeholder !== hint) search.placeholder = hint;
      // the columns shown changed: group headers span them again
      const columnsChanged = applyColumns();
      const narrowNow = String(width < 460);
      if (((columnsChanged || compactChanged) && resourceView.groupBy) || compactChanged
        || (resourcePanel.dataset.view !== 'resources' && narrowNow !== resourcePanel.dataset.savingsNarrow)) syncResources();
    }).observe(resourcePanel);
    // the details opening beside the table narrows it: the columns follow
    const wrap = resourcePanel.querySelector('[data-resource-wrap]');
    if (wrap) {
      new ResizeObserver(() => sizeColumns()).observe(wrap);
      // scrolled sideways, the frozen Name column draws its edge
      wrap.addEventListener('scroll', () => {
        const scrolled = String(wrap.scrollLeft > 0);
        if (wrap.dataset.scrolled !== scrolled) wrap.dataset.scrolled = scrolled;
      }, {passive: true});
    }
  }
  afterRender.push(syncResources);
  syncResources();
