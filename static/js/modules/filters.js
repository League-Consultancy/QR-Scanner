/**
 * LUXE-TRACE - Dynamic Inventory Filters
 * Loads inventory items, renders dynamic filter cards, and handles filter matching
 */

function loadActualInventory() {
  fetch('/api/inventory/items')
    .then(res => res.json())
    .then(data => {
      if (data && data.items && data.items.length > 0) {
        INVENTORY_DATABASE = data.items;
        console.log(`[Inventory] Loaded ${INVENTORY_DATABASE.length} actual items from CRM/Backend cache.`);
      }
      // Generate filter cards and chips dynamically based strictly on the loaded inventory
      setupDynamicFilters();
      renderSidebarInventoryCodes();
      renderSurface();
    })
    .catch(err => {
      console.error('[Inventory] Error loading actual inventory:', err);
      setupDynamicFilters();
      renderSidebarInventoryCodes();
    });
}

function triggerInventorySync() {
  const syncBtn = document.getElementById('btn-header-sync');
  const headerInvCount = document.getElementById('header-inv-count');

  if (syncBtn) syncBtn.classList.add('spin-animation');
  if (headerInvCount) headerInvCount.textContent = 'SYNCING...';

  fetch('/api/inventory/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'on_hand' })
  })
    .then(res => res.json())
    .then(data => {
      console.log('[Inventory Sync] Response:', data);
      if (data.status === 'success') {
        loadActualInventory();
      } else {
        alert('Sync error: ' + (data.message || 'Unknown error'));
        if (headerInvCount) headerInvCount.textContent = `SYNCED (${INVENTORY_DATABASE.length} ON HAND)`;
      }
    })
    .catch(err => {
      console.error('[Inventory Sync] Error:', err);
      alert('Network error while syncing inventory: ' + err);
      if (headerInvCount) headerInvCount.textContent = `SYNCED (${INVENTORY_DATABASE.length} ON HAND)`;
    })
    .finally(() => {
      if (syncBtn) syncBtn.classList.remove('spin-animation');
    });
}

const RANGE_FILTER_CONFIGS = [
  { id: 'carat', label: 'Carat Weight', unit: 'ct', step: '0.1', minKey: 'minCarat', maxKey: 'maxCarat', getVal: d => d.ct || d.carat },
  { id: 'length', label: 'Length (mm)', unit: 'mm', step: '0.1', minKey: 'minLength', maxKey: 'maxLength', getVal: d => d.length },
  { id: 'width', label: 'Width (mm)', unit: 'mm', step: '0.1', minKey: 'minWidth', maxKey: 'maxWidth', getVal: d => d.width },
  { id: 'height', label: 'Height (mm)', unit: 'mm', step: '0.1', minKey: 'minHeight', maxKey: 'maxHeight', getVal: d => d.height },
  { id: 'ratio', label: 'Ratio (L/W)', unit: 'ratio', step: '0.05', minKey: 'minRatio', maxKey: 'maxRatio', getVal: d => d.ratio }
];

function setupDynamicFilters() {
  const container = document.getElementById('dynamic-filters-container');
  if (!container) return;
  container.innerHTML = '';
  
  // 1. Categorical fields (excluding Color, which has its own multi-subgroup card)
  const categories = [
    { key: 'shape', label: 'Shape' },
    { key: 'clarity', label: 'Clarity' },
    { key: 'cut', label: 'Cut' },
    { key: 'polish', label: 'Polish' },
    { key: 'symmetry', label: 'Symmetry' },
    { key: 'fluorescence', label: 'Fluorescence' },
    { key: 'lab', label: 'Lab' }
  ];

  // Derive unique values dynamically from INVENTORY_DATABASE
  categories.forEach(cat => {
    const valueMap = {};
    INVENTORY_DATABASE.forEach(item => {
      const val = item[cat.key];
      if (val) {
        valueMap[val] = (valueMap[val] || 0) + 1;
      }
    });

    const uniqueValues = Object.keys(valueMap).sort();
    if (uniqueValues.length === 0) return;

    // Create Category Card
    const card = document.createElement('div');
    card.className = 'filter-category-card';
    
    const title = document.createElement('div');
    title.className = 'filter-category-title';
    title.innerHTML = `<span>${cat.label}</span> <span>${uniqueValues.length} Options</span>`;
    card.appendChild(title);

    const chipsRow = document.createElement('div');
    chipsRow.className = 'filter-chips-row';

    uniqueValues.forEach(val => {
      const chip = document.createElement('div');
      chip.className = 'filter-chip';
      chip.dataset.category = cat.key;
      chip.dataset.value = val;
      chip.innerHTML = `${escapeHtml(val)} <span class="chip-count">${valueMap[val]}</span>`;
      
      chip.addEventListener('click', () => {
        toggleFilterChip(cat.key, val, chip);
      });

      chipsRow.appendChild(chip);
    });

    card.appendChild(chipsRow);
    container.appendChild(card);
  });

  // 2. Dedicated Color Card with Subfields: Main Color, Original Color (OG), Fancy Color
  const colorSubfields = [
    { key: 'color', label: 'Main Color' },
    { key: 'original_color', label: 'Original Color (OG)' },
    { key: 'fancy_color', label: 'Fancy Color' }
  ];

  const colorCard = document.createElement('div');
  colorCard.className = 'filter-category-card filter-color-card';

  const colorTitle = document.createElement('div');
  colorTitle.className = 'filter-category-title';
  colorTitle.innerHTML = `<span>Color & Hue</span> <span>Main / OG / Fancy</span>`;
  colorCard.appendChild(colorTitle);

  let hasColorOptions = false;
  colorSubfields.forEach(sub => {
    const valueMap = {};
    INVENTORY_DATABASE.forEach(item => {
      const val = item[sub.key];
      if (val) {
        valueMap[val] = (valueMap[val] || 0) + 1;
      }
    });

    const uniqueVals = Object.keys(valueMap).sort();
    if (uniqueVals.length === 0) return;
    hasColorOptions = true;

    const subgroup = document.createElement('div');
    subgroup.className = 'filter-subgroup';

    const subLabel = document.createElement('div');
    subLabel.className = 'filter-subgroup-label';
    subLabel.innerHTML = `${sub.label} <span>${uniqueVals.length}</span>`;
    subgroup.appendChild(subLabel);

    const chipsRow = document.createElement('div');
    chipsRow.className = 'filter-chips-row';

    uniqueVals.forEach(val => {
      const chip = document.createElement('div');
      chip.className = 'filter-chip';
      chip.dataset.category = sub.key;
      chip.dataset.value = val;
      chip.innerHTML = `${escapeHtml(val)} <span class="chip-count">${valueMap[val]}</span>`;

      chip.addEventListener('click', () => {
        toggleFilterChip(sub.key, val, chip);
      });

      chipsRow.appendChild(chip);
    });

    subgroup.appendChild(chipsRow);
    colorCard.appendChild(subgroup);
  });

  if (hasColorOptions) {
    container.appendChild(colorCard);
  }

  // 3. Dynamic Numeric Ranges (Carat, Length, Width, Height, Ratio)
  RANGE_FILTER_CONFIGS.forEach(cfg => {
    const values = INVENTORY_DATABASE.map(cfg.getVal).filter(v => typeof v === 'number' && !isNaN(v) && v > 0);
    if (values.length === 0) return;

    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);

    const rangeCard = document.createElement('div');
    rangeCard.className = `filter-category-card filter-range-card filter-${cfg.id}-card`;
    rangeCard.innerHTML = `
      <div class="filter-category-title">
        <span>${escapeHtml(cfg.label)}</span>
        <span>${minVal.toFixed(2)} - ${maxVal.toFixed(2)} ${cfg.unit}</span>
      </div>
      <div class="range-inputs-row">
        <input type="number" id="${cfg.id}-min" class="range-input" step="${cfg.step}" placeholder="Min ${minVal.toFixed(2)}" />
        <span class="range-separator">to</span>
        <input type="number" id="${cfg.id}-max" class="range-input" step="${cfg.step}" placeholder="Max ${maxVal.toFixed(2)}" />
      </div>
    `;
    container.appendChild(rangeCard);

    // Hook inputs into dirty state
    [`${cfg.id}-min`, `${cfg.id}-max`].forEach(inpId => {
      const inputEl = document.getElementById(inpId);
      if (inputEl) {
        inputEl.addEventListener('input', (e) => {
          const field = inpId.endsWith('-min') ? cfg.minKey : cfg.maxKey;
          const val = parseFloat(e.target.value);
          if (isNaN(val)) {
            delete draftFilters[field];
          } else {
            draftFilters[field] = val;
          }
          evaluateDirtyState();
        });
      }
    });
  });

  // Update count in header and filters badge
  const headerInvCount = document.getElementById('header-inv-count');
  if (headerInvCount) {
    headerInvCount.textContent = `SYNCED (${INVENTORY_DATABASE.length} ON HAND)`;
  }
  const filterMatchBadge = document.getElementById('filter-match-count');
  if (filterMatchBadge) {
    filterMatchBadge.textContent = `${INVENTORY_DATABASE.length} Stones Matching`;
  }
}

// Toggle chip selection in draft state
function toggleFilterChip(category, value, chipElement) {
  if (!draftFilters[category]) {
    draftFilters[category] = new Set();
  }

  if (draftFilters[category].has(value)) {
    draftFilters[category].delete(value);
    if (draftFilters[category].size === 0) {
      delete draftFilters[category];
    }
    chipElement.classList.remove('selected');
  } else {
    draftFilters[category].add(value);
    chipElement.classList.add('selected');
  }

  evaluateDirtyState();
}

// Compare draftFilters vs committedFilters to show/hide Save & Cancel buttons
function evaluateDirtyState() {
  const isDirty = !areFilterStatesEqual(draftFilters, committedFilters);
  const actionBar = document.getElementById('filters-action-bar');
  if (actionBar) {
    if (isDirty) {
      actionBar.classList.add('is-dirty');
    } else {
      actionBar.classList.remove('is-dirty');
    }
  }

  // Preview match count with active draft filters
  const matches = getMatchingInventoryItems(draftFilters);
  const matchCountElem = document.getElementById('filter-match-count');
  if (matchCountElem) {
    matchCountElem.textContent = `${matches.length} Stones Matching`;
  }

  // Requirement: Dynamically update the Matching Diamonds section below filters
  renderFilterMatchesSection(matches);
}

function areFilterStatesEqual(f1, f2) {
  const keys1 = Object.keys(f1);
  const keys2 = Object.keys(f2);
  if (keys1.length !== keys2.length) return false;

  for (let key of keys1) {
    const val1 = f1[key];
    const val2 = f2[key];
    if (val1 instanceof Set && val2 instanceof Set) {
      if (val1.size !== val2.size) return false;
      for (let v of val1) if (!val2.has(v)) return false;
    } else if (val1 !== val2) {
      return false;
    }
  }
  return true;
}

// Save & Cancel Handlers
function saveFilters() {
  committedFilters = {};
  for (let key in draftFilters) {
    if (draftFilters[key] instanceof Set) {
      committedFilters[key] = new Set(draftFilters[key]);
    } else {
      committedFilters[key] = draftFilters[key];
    }
  }
  evaluateDirtyState();
  renderSurface();
}

function cancelFilters() {
  draftFilters = {};
  for (let key in committedFilters) {
    if (committedFilters[key] instanceof Set) {
      draftFilters[key] = new Set(committedFilters[key]);
    } else {
      draftFilters[key] = committedFilters[key];
    }
  }

  // Restore UI chips
  document.querySelectorAll('.filter-chip').forEach(chip => {
    const cat = chip.dataset.category;
    const val = chip.dataset.value;
    if (draftFilters[cat] && draftFilters[cat].has(val)) {
      chip.classList.add('selected');
    } else {
      chip.classList.remove('selected');
    }
  });

  // Restore range inputs (carat, length, width, height, ratio)
  RANGE_FILTER_CONFIGS.forEach(cfg => {
    const minInput = document.getElementById(`${cfg.id}-min`);
    const maxInput = document.getElementById(`${cfg.id}-max`);
    if (minInput) minInput.value = draftFilters[cfg.minKey] !== undefined ? draftFilters[cfg.minKey] : '';
    if (maxInput) maxInput.value = draftFilters[cfg.maxKey] !== undefined ? draftFilters[cfg.maxKey] : '';
  });

  evaluateDirtyState();
}

// ==========================================================================
// SECTION BELOW FILTERS: MATCHING DIAMONDS CARDS RENDERER & HIGHLIGHT CONTROLLER
// ==========================================================================

function renderFilterMatchesSection(matchedDiamonds) {
  const section = document.getElementById('filter-matches-results-section');
  const container = document.getElementById('filter-matches-cards-list');
  const countBadge = document.getElementById('results-count-badge');
  const inViewBadge = document.getElementById('results-inview-count-badge');
  const highlightBtn = document.getElementById('btn-highlight-selected-matches');
  const labelHighlight = document.getElementById('label-highlight-selected');

  if (!section || !container || !countBadge || !inViewBadge) return;

  // Check if any filter chips or carat ranges are actually selected in draft or committed state
  const hasFilterKeys = Object.keys(draftFilters).some(k => {
    const v = draftFilters[k];
    if (v instanceof Set) return v.size > 0;
    return typeof v === 'number' && !isNaN(v);
  });

  // If no filters are applied, completely hide the section so it doesn't take space or hide chips
  if (!hasFilterKeys) {
    section.style.display = 'none';
    selectedFilterMatchCodes.clear();
    updateHighlightSelectedBtn();
    return;
  }

  // Filters are applied: reveal the section below the filter grid
  section.style.display = 'flex';

  const matches = matchedDiamonds || [];
  countBadge.textContent = `${matches.length} Found`;

  // Determine currently in-view codes on the desk
  const inViewCodesSet = new Set();
  if (latestInViewData) {
    const allInView = [...(latestInViewData.verified_items || []), ...(latestInViewData.dispute_items || [])];
    allInView.forEach(item => {
      if (item.stock_id) inViewCodesSet.add(item.stock_id.toLowerCase());
    });
  }

  // Count how many matching diamonds are currently in view
  const inViewMatches = matches.filter(d => inViewCodesSet.has((d.stock_id || '').toLowerCase()));
  inViewBadge.textContent = `${inViewMatches.length} in view`;

  if (matches.length === 0) {
    selectedFilterMatchCodes.clear();
    updateHighlightSelectedBtn();
    container.innerHTML = '<div class="filter-matches-empty" style="color:var(--rose-accent);">No diamonds in inventory match the chosen filter criteria.</div>';
    return;
  }

  // Clean stale selections that no longer match the current filter set
  const currentMatchIdsSet = new Set(matches.map(m => m.stock_id));
  for (let code of Array.from(selectedFilterMatchCodes)) {
    if (!currentMatchIdsSet.has(code)) {
      selectedFilterMatchCodes.delete(code);
    }
  }

  container.innerHTML = '';

  matches.forEach(item => {
    const stockId = item.stock_id || 'UNKNOWN';
    const isInView = inViewCodesSet.has(stockId.toLowerCase());
    const isSelected = selectedFilterMatchCodes.has(stockId);

    const card = document.createElement('div');
    card.className = `match-item-card ${isSelected ? 'is-selected' : ''} ${isInView ? 'is-in-view' : ''}`;
    card.dataset.stockId = stockId;

    // Checkbox element
    const chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.className = 'match-card-checkbox';
    chk.checked = isSelected;

    // Toggle on checkbox or card click
    const toggleSelection = (e) => {
      if (e.target !== chk) {
        chk.checked = !chk.checked;
      }
      if (chk.checked) {
        selectedFilterMatchCodes.add(stockId);
        card.classList.add('is-selected');
      } else {
        selectedFilterMatchCodes.delete(stockId);
        card.classList.remove('is-selected');
      }
      updateHighlightSelectedBtn();
    };

    chk.addEventListener('change', toggleSelection);
    card.addEventListener('click', toggleSelection);

    // Card Body
    const body = document.createElement('div');
    body.className = 'match-card-body';

    // Top row
    const topRow = document.createElement('div');
    topRow.className = 'match-card-top-row';

    const codeSpan = document.createElement('span');
    codeSpan.className = 'match-card-code';
    codeSpan.innerHTML = `
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
        <path d="M7 7h.01M17 7h.01M7 17h.01M17 17h.01"/>
      </svg>
      ${escapeHtml(stockId)}
    `;

    const badgesSpan = document.createElement('div');
    badgesSpan.className = 'match-card-badges';

    if (isInView) {
      badgesSpan.innerHTML += `<span class="badge-inview-tag">● ON SURFACE (IN VIEW)</span>`;
    } else {
      badgesSpan.innerHTML += `<span class="badge-absent-tag">VAULT / TRAY</span>`;
    }

    topRow.appendChild(codeSpan);
    topRow.appendChild(badgesSpan);

    // Specs Row
    const specsRow = document.createElement('div');
    specsRow.className = 'match-card-specs-row';

    const properties = [
      { label: 'Shape', val: item.shape },
      { label: 'Carat', val: item.ct ? item.ct.toFixed(2) + ' ct' : (item.carat ? item.carat.toFixed(2) + ' ct' : null) },
      { label: 'Color', val: item.color },
      { label: 'OG Color', val: item.original_color },
      { label: 'Fancy Color', val: item.fancy_color },
      { label: 'Clarity', val: item.clarity },
      { label: 'Cut', val: item.cut },
      { label: 'Polish', val: item.polish },
      { label: 'Sym', val: item.symm || item.symmetry },
      { label: 'Fluor', val: item.fluo || item.fluorescence },
      { label: 'Meas', val: item.measurements },
      { label: 'Ratio', val: item.ratio ? Number(item.ratio).toFixed(2) : null },
      { label: 'Lab', val: item.lab },
      { label: 'Cert #', val: item.cert_number || item.certificate_no || item.cert_num },
      { label: 'Rate/ct', val: item.price_per_rate ? '$' + item.price_per_rate : null },
      { label: 'Amount', val: item.sale_amt ? '$' + item.sale_amt : null },
      { label: 'Loc', val: item.location }
    ].filter(p => p.val && p.val !== '--');

    specsRow.innerHTML = properties.map(p => `
      <span class="prop-chip">
        <span class="prop-label">${escapeHtml(p.label)}</span>
        <span class="prop-value">${escapeHtml(String(p.val))}</span>
      </span>
    `).join('');

    body.appendChild(topRow);
    body.appendChild(specsRow);

    card.appendChild(chk);
    card.appendChild(body);
    container.appendChild(card);
  });

  updateHighlightSelectedBtn();
}

function updateHighlightSelectedBtn() {
  const btn = document.getElementById('btn-highlight-selected-matches');
  const label = document.getElementById('label-highlight-selected');
  const count = selectedFilterMatchCodes.size;

  if (label) {
    label.textContent = `Highlight Selected (${count})`;
  }
  if (btn) {
    btn.disabled = count === 0;
  }
}

// Filter Matching Engine
function getMatchingInventoryItems(filterState) {
  const searchInput = document.getElementById('global-search-input');
  const rawQuery = (searchInput ? searchInput.value : '').trim();

  // Parse comma-separated (or newline/semicolon separated) tokens
  const queryTokens = rawQuery
    ? rawQuery.split(/[\n,;]+/).map(t => t.trim().toLowerCase()).filter(Boolean)
    : [];

  return INVENTORY_DATABASE.filter(item => {
    // 1. Text Search Filter (Matches if item satisfies ANY of the comma-separated tokens)
    if (queryTokens.length > 0) {
      const stockId = (item.stock_id || '').toLowerCase();
      const certNo = (item.cert_num || item.certificate_no || '').toLowerCase();
      const shape = (item.shape || '').toLowerCase();
      const color = (item.color || '').toLowerCase();
      const clarity = (item.clarity || '').toLowerCase();
      const lab = (item.lab || '').toLowerCase();

      const matchesAnyToken = queryTokens.some(token => {
        return (
          stockId.includes(token) ||
          certNo.includes(token) ||
          shape.includes(token) ||
          color.includes(token) ||
          clarity.includes(token) ||
          lab.includes(token)
        );
      });

      if (!matchesAnyToken) return false;
    }

    // 2. Numeric Range & Attribute Filters
    for (let key in filterState) {
      if (key === 'minCarat') {
        const c = item.ct || item.carat || 0;
        if (c < filterState.minCarat) return false;
      } else if (key === 'maxCarat') {
        const c = item.ct || item.carat || 0;
        if (c > filterState.maxCarat) return false;
      } else if (key === 'minLength') {
        if (item.length == null || item.length < filterState.minLength) return false;
      } else if (key === 'maxLength') {
        if (item.length == null || item.length > filterState.maxLength) return false;
      } else if (key === 'minWidth') {
        if (item.width == null || item.width < filterState.minWidth) return false;
      } else if (key === 'maxWidth') {
        if (item.width == null || item.width > filterState.maxWidth) return false;
      } else if (key === 'minHeight') {
        if (item.height == null || item.height < filterState.minHeight) return false;
      } else if (key === 'maxHeight') {
        if (item.height == null || item.height > filterState.maxHeight) return false;
      } else if (key === 'minRatio') {
        if (item.ratio == null || item.ratio < filterState.minRatio) return false;
      } else if (key === 'maxRatio') {
        if (item.ratio == null || item.ratio > filterState.maxRatio) return false;
      } else if (filterState[key] instanceof Set && filterState[key].size > 0) {
        if (!filterState[key].has(item[key])) return false;
      }
    }

    return true;
  });
}
