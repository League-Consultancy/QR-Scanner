/**
 * LUXE-TRACE - Optical Inventory & Picking Engine
 * Master Application Orchestrator & Event Listeners
 */

window.addEventListener('DOMContentLoaded', () => {
  setupCanvases();
  setupEventListeners();
  setupModalControllers();
  setupSidebarCodesTracker();
  
  // Load real synced inventory from backend and generate filter options dynamically
  loadActualInventory();

  // Periodically refresh inventory in UI every 15 minutes (900,000 ms) in sync with backend
  setInterval(() => {
    console.log('[Inventory] Performing periodic 15-minute UI inventory refresh...');
    loadActualInventory();
  }, 15 * 60 * 1000);

  // Check calibration status from backend on startup
  checkCalibrationStatus();
});

function setupEventListeners() {
  // Search Input Handlers
  const searchInput = document.getElementById('global-search-input');
  const searchClear = document.getElementById('search-clear-btn');

  if (searchInput && searchClear) {
    searchInput.addEventListener('input', () => {
      searchClear.style.display = searchInput.value ? 'block' : 'none';
      renderSurface();
      updateInViewAutocompleteDropdown();
    });

    searchInput.addEventListener('focus', () => {
      updateInViewAutocompleteDropdown();
    });

    searchClear.addEventListener('click', () => {
      searchInput.value = '';
      searchClear.style.display = 'none';
      hideInViewAutocompleteDropdown();
      renderSurface();
    });

    // Close autocomplete on click outside
    document.addEventListener('click', (e) => {
      const dropdown = document.getElementById('search-inview-dropdown');
      if (dropdown && !dropdown.contains(e.target) && e.target !== searchInput) {
        hideInViewAutocompleteDropdown();
      }
    });

    // Keyboard shortcut '/' to search, Escape to close dropdown
    window.addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement !== searchInput) {
        e.preventDefault();
        searchInput.focus();
      } else if (e.key === 'Escape' && document.activeElement === searchInput) {
        hideInViewAutocompleteDropdown();
      }
    });
  }

  // Header Manual CRM Inventory Sync Button
  const btnHeaderSync = document.getElementById('btn-header-sync');
  if (btnHeaderSync) {
    btnHeaderSync.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (typeof triggerInventorySync === 'function') {
        triggerInventorySync();
      }
    });
  }

  // Project highlight trigger button (Feature 3 & 6 Endpoint)
  const btnHighlight = document.getElementById('btn-project-highlight');
  const btnClearHighlights = document.getElementById('btn-clear-highlights');

  if (btnHighlight) {
    btnHighlight.addEventListener('click', () => {
      if (!isSystemCalibrated) {
        alert("⚠️ Calibration Required!\n\nPlease click 'Re-Calibrate' in the sidebar first to align the camera with the projector before projection highlighting can be activated.");
        return;
      }

      // 1. Get codes matching committed filters & search from Master Inventory
      const matchingInventory = getMatchingInventoryItems(committedFilters);
      const codesSet = new Set(matchingInventory.map(i => i.stock_id));

      // 2. Also check if the user typed or pasted comma-separated codes directly
      const rawSearchQuery = (document.getElementById('global-search-input')?.value || '').trim();
      const rawTokens = rawSearchQuery
        ? rawSearchQuery.split(/[\n,;]+/).map(t => t.trim()).filter(Boolean)
        : [];

      if (rawTokens.length > 0) {
        rawTokens.forEach(token => {
          codesSet.add(token);
          // Check case-insensitive match against currently detected camera codes
          if (latestInViewData) {
            const allInView = [...(latestInViewData.verified_items || []), ...(latestInViewData.dispute_items || [])];
            allInView.forEach(item => {
              if (item.stock_id && item.stock_id.toLowerCase() === token.toLowerCase()) {
                codesSet.add(item.stock_id);
              }
            });
          }
        });
      }

      const codes = Array.from(codesSet).filter(Boolean);
      if (codes.length === 0) {
        alert("No matching diamonds found to highlight. Please enter diamond codes or select inventory filters.");
        return;
      }

      // Choose next distinct color from palette based on existing batches count
      const paletteIndex = activeHighlightBatches.length % HIGHLIGHT_PALETTES.length;
      const assignedColor = HIGHLIGHT_PALETTES[paletteIndex];

      // Create new batch object
      const batchId = 'batch_' + Date.now();
      const batchLabel = rawTokens.length > 0
        ? (rawTokens.slice(0, 3).join(', ') + (rawTokens.length > 3 ? ` +${rawTokens.length - 3}` : ''))
        : `${codes.length} Stones`;

      const newBatch = {
        id: batchId,
        label: batchLabel,
        codes: codes,
        color: assignedColor
      };

      // Append new batch (keeps previous searches active!)
      activeHighlightBatches.push(newBatch);

      // Rebuild codeColorMap so surface canvas and projector know each code's assigned color
      rebuildCodeColorMap();

      // Render the active batches tray and show the Clear Highlights button
      renderHighlightBatchesTray();

      triggerPulseHighlight();

      // Send to Backend: /api/projector/highlight
      console.log(`[API Call] Sending batch '${batchLabel}' with color ${assignedColor.name} to /api/projector/highlight:`, codes);
      fetch('/api/projector/highlight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'append',
          codes: codes,
          color: assignedColor.bgr
        })
      })
      .then(res => res.json())
      .then(data => {
        console.log('[API Response] /api/projector/highlight response:', data);
        if (data.status === 'error') {
          alert(data.message);
        }
      })
      .catch(err => console.error('[API Error] /api/projector/highlight:', err));
    });
  }

  // Clear All Highlights Trigger Button
  if (btnClearHighlights) {
    btnClearHighlights.addEventListener('click', () => {
      clearAllHighlights();
    });
  }

  // Filter Save / Cancel Buttons
  const btnSaveFilters = document.getElementById('btn-save-filters');
  const btnCancelFilters = document.getElementById('btn-cancel-filters');
  if (btnSaveFilters) btnSaveFilters.addEventListener('click', saveFilters);
  if (btnCancelFilters) btnCancelFilters.addEventListener('click', cancelFilters);

  // Section Below Filters: Action Button Listeners
  const btnSelectAllMatches = document.getElementById('btn-select-all-matches');
  const btnSelectInViewMatches = document.getElementById('btn-select-inview-matches');
  const btnClearSelectedMatches = document.getElementById('btn-clear-selected-matches');
  const btnHighlightSelectedMatches = document.getElementById('btn-highlight-selected-matches');

  if (btnSelectAllMatches) {
    btnSelectAllMatches.addEventListener('click', () => {
      document.querySelectorAll('.match-item-card').forEach(card => {
        const stockId = card.dataset.stockId;
        const chk = card.querySelector('.match-card-checkbox');
        if (stockId) {
          selectedFilterMatchCodes.add(stockId);
          if (chk) chk.checked = true;
          card.classList.add('is-selected');
        }
      });
      updateHighlightSelectedBtn();
    });
  }

  if (btnSelectInViewMatches) {
    btnSelectInViewMatches.addEventListener('click', () => {
      selectedFilterMatchCodes.clear();
      document.querySelectorAll('.match-item-card').forEach(card => {
        const stockId = card.dataset.stockId;
        const chk = card.querySelector('.match-card-checkbox');
        const isInView = card.classList.contains('is-in-view');
        if (isInView && stockId) {
          selectedFilterMatchCodes.add(stockId);
          if (chk) chk.checked = true;
          card.classList.add('is-selected');
        } else {
          if (chk) chk.checked = false;
          card.classList.remove('is-selected');
        }
      });
      updateHighlightSelectedBtn();
    });
  }

  if (btnClearSelectedMatches) {
    btnClearSelectedMatches.addEventListener('click', () => {
      selectedFilterMatchCodes.clear();
      document.querySelectorAll('.match-item-card').forEach(card => {
        const chk = card.querySelector('.match-card-checkbox');
        if (chk) chk.checked = false;
        card.classList.remove('is-selected');
      });
      updateHighlightSelectedBtn();
    });
  }

  if (btnHighlightSelectedMatches) {
    btnHighlightSelectedMatches.addEventListener('click', () => {
      if (!isSystemCalibrated) {
        alert("⚠️ Calibration Required!\n\nPlease click 'Re-Calibrate' in the sidebar first to align the camera with the projector before projection highlighting can be activated.");
        return;
      }

      const codes = Array.from(selectedFilterMatchCodes).filter(Boolean);
      if (codes.length === 0) {
        alert("Please select at least one diamond from the list below.");
        return;
      }

      // Assign next distinct color from palette
      const paletteIndex = activeHighlightBatches.length % HIGHLIGHT_PALETTES.length;
      const assignedColor = HIGHLIGHT_PALETTES[paletteIndex];

      const batchId = 'batch_' + Date.now();
      const batchLabel = `Filter: ${codes.length} Stones`;

      const newBatch = {
        id: batchId,
        label: batchLabel,
        codes: codes,
        color: assignedColor
      };

      activeHighlightBatches.push(newBatch);
      rebuildCodeColorMap();
      renderHighlightBatchesTray();
      triggerPulseHighlight();

      console.log(`[API Call] Highlighting ${codes.length} filtered stones with color ${assignedColor.name}:`, codes);
      fetch('/api/projector/highlight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'append',
          codes: codes,
          color: assignedColor.bgr
        })
      })
      .then(res => res.json())
      .then(data => {
        console.log('[API Response] /api/projector/highlight response:', data);
        if (data.status === 'error') {
          alert(data.message);
        }
      })
      .catch(err => console.error('[API Error] /api/projector/highlight:', err));
    });
  }

  // Simulation buttons (if present)
  const simBtn = document.getElementById('btn-simulate-detect');
  if (simBtn) {
    simBtn.addEventListener('click', () => {
      simulateStonesOnTable();
      renderSurface();
    });
  }

  const clearBtn = document.getElementById('btn-clear-table');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      activeStonesOnTable = [];
      renderSurface();
      updateAuditMetrics();
    });
  }
}

function setupModalControllers() {
  // Modal Elements
  const calibOverlay = document.getElementById('overlay-calibration');
  const feedOverlay = document.getElementById('overlay-cam-feed');
  const exportOverlay = document.getElementById('overlay-export');

  // Trigger Buttons
  const btnOpenCalib = document.getElementById('btn-open-calibration');
  if (btnOpenCalib && calibOverlay) {
    btnOpenCalib.addEventListener('click', () => {
      calibOverlay.classList.add('active');
      initCalibrationCanvas();
    });
  }

  const btnOpenFeed = document.getElementById('btn-open-cam-feed');
  if (btnOpenFeed && feedOverlay) {
    btnOpenFeed.addEventListener('click', () => {
      feedOverlay.classList.add('active');
      startRealCameraStream();
    });
  }

  const exportConfigScreen = document.getElementById('export-config-screen');
  const exportLoader = document.getElementById('export-loader');
  const exportReport = document.getElementById('export-report');
  const btnOpenExport = document.getElementById('btn-open-export');

  if (btnOpenExport && exportOverlay) {
    btnOpenExport.addEventListener('click', () => {
      exportOverlay.classList.add('active');
      // Always start on the Report Configuration screen
      if (exportConfigScreen) exportConfigScreen.style.display = 'flex';
      if (exportLoader) exportLoader.style.display = 'none';
      if (exportReport) exportReport.style.display = 'none';
    });
  }

  // Report config card selection handlers
  document.querySelectorAll('.report-type-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.report-type-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      const radio = card.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
    });
  });

  // Generate Custom Report Button
  const btnGenerateCustom = document.getElementById('btn-generate-custom-report');
  if (btnGenerateCustom) {
    btnGenerateCustom.addEventListener('click', () => {
      const selectedScope = document.querySelector('input[name="report-scope"]:checked')?.value || 'full';
      const includeMetrics = document.getElementById('chk-include-metrics')?.checked ?? true;
      const autoPrint = document.getElementById('chk-auto-print')?.checked ?? true;
      runCustomExportFlow(selectedScope, includeMetrics, autoPrint);
    });
  }

  // Back to Config Button from Report View
  const btnBackToConfig = document.getElementById('btn-back-to-config');
  if (btnBackToConfig) {
    btnBackToConfig.addEventListener('click', () => {
      if (exportReport) exportReport.style.display = 'none';
      if (exportConfigScreen) exportConfigScreen.style.display = 'flex';
    });
  }

  // Close handlers for export modal
  const closeExportModal = () => exportOverlay && exportOverlay.classList.remove('active');
  const btnCloseExportConfig = document.getElementById('btn-close-export-config');
  const btnCancelExportConfig = document.getElementById('btn-cancel-export-config');
  const btnCloseExport = document.getElementById('btn-close-export');
  if (btnCloseExportConfig) btnCloseExportConfig.addEventListener('click', closeExportModal);
  if (btnCancelExportConfig) btnCancelExportConfig.addEventListener('click', closeExportModal);
  if (btnCloseExport) btnCloseExport.addEventListener('click', closeExportModal);

  // History modal handlers
  const historyModal = document.getElementById('modal-history');
  const btnOpenHistory = document.getElementById('btn-open-history');
  if (btnOpenHistory && historyModal) {
    btnOpenHistory.addEventListener('click', () => {
      historyModal.classList.add('active');
      initHistoryModal();
    });
  }

  const historyCloseBtn = document.getElementById('modal-history-close');
  if (historyCloseBtn && historyModal) {
    historyCloseBtn.addEventListener('click', () => historyModal.classList.remove('active'));
  }

  // Calibration Close Handlers
  const btnCloseCalib = document.getElementById('btn-close-calibration');
  const btnCancelCalib = document.getElementById('btn-cancel-calibration');
  if (btnCloseCalib && calibOverlay) btnCloseCalib.addEventListener('click', () => calibOverlay.classList.remove('active'));
  if (btnCancelCalib && calibOverlay) btnCancelCalib.addEventListener('click', () => calibOverlay.classList.remove('active'));

  // Live Camera Close Handlers
  function closeFeedModal() {
    if (feedOverlay) feedOverlay.classList.remove('active');
    stopRealCameraStream();
  }
  const btnCloseCamFeed = document.getElementById('btn-close-cam-feed');
  const btnCloseCamFeedBtn = document.getElementById('btn-close-cam-feed-btn');
  if (btnCloseCamFeed) btnCloseCamFeed.addEventListener('click', closeFeedModal);
  if (btnCloseCamFeedBtn) btnCloseCamFeedBtn.addEventListener('click', closeFeedModal);

  // Calibration points reset & save (Feature 2 Endpoint)
  const btnResetCalib = document.getElementById('btn-reset-calib-points');
  const btnSaveCalib = document.getElementById('btn-save-calibration');

  if (btnResetCalib) btnResetCalib.addEventListener('click', resetCalibration);
  if (btnSaveCalib && calibOverlay) {
    btnSaveCalib.addEventListener('click', () => {
      calibOverlay.classList.remove('active');

      console.log('[API Call] Posting calibration points to /api/calibration/save:', recordedCalibPoints);
      fetch('/api/calibration/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          camera_points: recordedCalibPoints,
          projector_points: CALIBRATION_STEPS.map(s => ({ x: s.projX, y: s.projY }))
        })
      })
      .then(res => res.json())
      .then(data => {
        console.log('[API Response] /api/calibration/save response:', data);
        if (data.is_calibrated) {
          updateCalibrationUI(true);
        } else {
          alert(data.message || 'Homography computation failed.');
        }
      })
      .catch(err => console.error('[API Error] /api/calibration/save:', err));
    });
  }

  // Native Print Trigger
  const btnTriggerPrint = document.getElementById('btn-trigger-print');
  if (btnTriggerPrint) {
    btnTriggerPrint.addEventListener('click', () => {
      window.print();
    });
  }
}

// ==========================================================================
// MULTI-BATCH HIGHLIGHT MANAGEMENT HELPERS
// ==========================================================================

function rebuildCodeColorMap() {
  codeColorMap = {};
  activeHighlightBatches.forEach(batch => {
    batch.codes.forEach(code => {
      codeColorMap[code] = batch.color;
      codeColorMap[code.toLowerCase()] = batch.color;
    });
  });
}

function renderHighlightBatchesTray() {
  const tray = document.getElementById('active-highlights-tray');
  const list = document.getElementById('highlight-batches-list');
  const clearBtn = document.getElementById('btn-clear-highlights');

  if (!tray || !list) return;

  if (activeHighlightBatches.length === 0) {
    tray.style.display = 'none';
    if (clearBtn) clearBtn.style.display = 'none';
    list.innerHTML = '';
    return;
  }

  tray.style.display = 'flex';
  if (clearBtn) clearBtn.style.display = 'flex';
  list.innerHTML = '';

  activeHighlightBatches.forEach(batch => {
    const chip = document.createElement('div');
    chip.className = 'highlight-batch-chip';
    chip.style.backgroundColor = batch.color.bgLight;
    chip.style.borderColor = batch.color.border;
    chip.style.color = batch.color.hex;

    chip.innerHTML = `
      <span class="batch-chip-dot" style="background-color: ${batch.color.hex};"></span>
      <span>${escapeHtml(batch.label)} (${batch.codes.length})</span>
      <button class="batch-chip-remove" title="Remove this highlight layer">✕</button>
    `;

    const removeBtn = chip.querySelector('.batch-chip-remove');
    if (removeBtn) {
      removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        removeHighlightBatch(batch.id);
      });
    }

    list.appendChild(chip);
  });
}

function removeHighlightBatch(batchId) {
  activeHighlightBatches = activeHighlightBatches.filter(b => b.id !== batchId);
  rebuildCodeColorMap();
  renderHighlightBatchesTray();
  renderSurface();

  // Sync remaining batches to backend projector loop
  syncBatchesToProjector();
}

function clearAllHighlights() {
  activeHighlightBatches = [];
  codeColorMap = {};
  renderHighlightBatchesTray();
  renderSurface();

  console.log('[API Call] Clearing all highlights via /api/projector/clear');
  fetch('/api/projector/clear', { method: 'POST' })
    .then(res => res.json())
    .then(data => console.log('[API Response] /api/projector/clear:', data))
    .catch(err => console.error('[API Error] /api/projector/clear:', err));
}

function syncBatchesToProjector() {
  const batchesPayload = {};
  activeHighlightBatches.forEach(batch => {
    batch.codes.forEach(code => {
      batchesPayload[code] = batch.color.bgr;
    });
  });

  fetch('/api/projector/highlight', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mode: 'replace',
      batches: batchesPayload
    })
  })
  .then(res => res.json())
  .then(data => console.log('[API Response] Batches synced to projector:', data))
  .catch(err => console.error('[API Error] Syncing batches:', err));
}

// ==========================================================================
// LIVE IN-VIEW AUTOCOMPLETE & PROPERTY PREVIEW CONTROLLER
// ==========================================================================

function hideInViewAutocompleteDropdown() {
  const dropdown = document.getElementById('search-inview-dropdown');
  if (dropdown) dropdown.style.display = 'none';
}

function updateInViewAutocompleteDropdown() {
  const searchInput = document.getElementById('global-search-input');
  const dropdown = document.getElementById('search-inview-dropdown');
  const list = document.getElementById('dropdown-inview-list');
  const badge = document.getElementById('dropdown-match-badge');

  if (!searchInput || !dropdown || !list || !badge) return;

  // 1. Gather all diamonds currently present in camera view
  const verified = (latestInViewData && latestInViewData.verified_items) ? latestInViewData.verified_items : [];
  const disputes = (latestInViewData && latestInViewData.dispute_items) ? latestInViewData.dispute_items : [];
  const allInView = [...verified, ...disputes];

  // 2. Extract all codes currently already entered anywhere in search input to prevent duplicates
  const rawVal = searchInput.value;
  const cursorPosition = searchInput.selectionStart || rawVal.length;
  const allExistingTokens = rawVal
    .split(/[\n,;]+/)
    .map(t => t.trim().toLowerCase())
    .filter(Boolean);
  const existingCodesSet = new Set(allExistingTokens);

  // 3. Identify the active token the user is currently typing (the token under/before cursor)
  const textBeforeCursor = rawVal.slice(0, cursorPosition);
  const parts = textBeforeCursor.split(/[\n,;]+/);
  const currentToken = (parts[parts.length - 1] || '').trim().toLowerCase();

  // If no codes in view at all on the surface
  if (allInView.length === 0) {
    if (rawVal.trim()) {
      badge.textContent = '0 Matches';
      list.innerHTML = `<div class="dropdown-empty-state">No matched codes found in camera view</div>`;
      dropdown.style.display = 'flex';
    } else {
      hideInViewAutocompleteDropdown();
    }
    return;
  }

  // 4. Filter in-view items matching current token
  const matchingItems = allInView.filter(item => {
    if (!currentToken) return true;
    const stockId = (item.stock_id || '').toLowerCase();
    const certNo = (item.cert_num || item.certificate_no || '').toLowerCase();
    const shape = (item.shape || '').toLowerCase();
    return stockId.includes(currentToken) || certNo.includes(currentToken) || shape.includes(currentToken);
  });

  // Requirement 1: If there are no matching codes, show "No matched codes found"
  if (matchingItems.length === 0) {
    badge.textContent = '0 Matches';
    list.innerHTML = `<div class="dropdown-empty-state">No matched codes found</div>`;
    dropdown.style.display = 'flex';
    return;
  }

  badge.textContent = `${matchingItems.length} Found`;
  list.innerHTML = '';

  // Render matching stones
  matchingItems.slice(0, 10).forEach(item => {
    // Check if this stone code is already added in the search bar
    const itemStockIdLower = (item.stock_id || '').toLowerCase();
    const isAlreadyInSearch = existingCodesSet.has(itemStockIdLower);

    // Cross-reference with INVENTORY_DATABASE for complete diamond properties
    const invItem = INVENTORY_DATABASE.find(d => d.stock_id && d.stock_id.toLowerCase() === itemStockIdLower) || {};
    const merged = { ...item, ...invItem };

    const card = document.createElement('div');
    card.className = `dropdown-preview-card ${isAlreadyInSearch ? 'is-already-added' : ''}`;

    const isVerified = (item.status === 'VERIFIED' || !item.is_dispute);
    let statusClass = isVerified ? 'preview-status-verified' : 'preview-status-dispute';
    let statusText = isVerified ? 'IN VIEW • VERIFIED' : 'IN VIEW • DISPUTE';

    if (isAlreadyInSearch) {
      statusClass = 'preview-status-added';
      statusText = 'ALREADY IN SEARCH';
    }

    // Highlight matching portion of code
    let displayCode = escapeHtml(item.stock_id);
    if (currentToken && !isAlreadyInSearch) {
      const idx = item.stock_id.toLowerCase().indexOf(currentToken);
      if (idx !== -1) {
        const matchEnd = idx + currentToken.length;
        displayCode = 
          escapeHtml(item.stock_id.substring(0, idx)) +
          `<span class="highlight-match">${escapeHtml(item.stock_id.substring(idx, matchEnd))}</span>` +
          escapeHtml(item.stock_id.substring(matchEnd));
      }
    }

    // Properties chips
    const properties = [
      { label: 'Shape', val: merged.shape },
      { label: 'Carat', val: merged.carat ? (typeof merged.carat === 'number' ? merged.carat.toFixed(2) + ' ct' : merged.carat) : null },
      { label: 'Color', val: merged.color },
      { label: 'Clarity', val: merged.clarity },
      { label: 'Cut', val: merged.cut },
      { label: 'Polish', val: merged.polish },
      { label: 'Sym', val: merged.symmetry },
      { label: 'Lab', val: merged.lab },
      { label: 'Cert #', val: merged.certificate_no || merged.cert_num }
    ].filter(p => p.val && p.val !== '--');

    const chipsHtml = properties.map(p => `
      <span class="prop-chip">
        <span class="prop-label">${escapeHtml(p.label)}</span>
        <span class="prop-value">${escapeHtml(String(p.val))}</span>
      </span>
    `).join('');

    card.innerHTML = `
      <div class="dropdown-preview-top">
        <span class="preview-code-id">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path d="M7 7h.01M17 7h.01M7 17h.01M17 17h.01"/>
          </svg>
          ${displayCode}
        </span>
        <span class="preview-status-pill ${statusClass}">${statusText}</span>
      </div>
      <div class="dropdown-preview-properties">
        ${chipsHtml || '<span style="font-size:0.72rem; color:var(--text-dim);">No CRM specifications (Unregistered)</span>'}
      </div>
    `;

    // Requirement 2: If code already available in search, we cannot add it again
    if (!isAlreadyInSearch) {
      card.addEventListener('click', () => {
        selectInViewCode(item.stock_id);
      });
    } else {
      card.style.opacity = '0.55';
      card.style.cursor = 'not-allowed';
      card.title = `Code '${item.stock_id}' is already present in your search list.`;
    }

    list.appendChild(card);
  });

  dropdown.style.display = 'flex';
}

function selectInViewCode(codeToInsert) {
  const searchInput = document.getElementById('global-search-input');
  if (!searchInput) return;

  const rawVal = searchInput.value;
  const trimmedToInsert = codeToInsert.trim();
  const lowerToInsert = trimmedToInsert.toLowerCase();

  // Guard against duplicate addition
  const existingTokens = rawVal
    .split(/[\n,;]+/)
    .map(t => t.trim().toLowerCase())
    .filter(Boolean);

  if (existingTokens.includes(lowerToInsert)) {
    // Already in search, do not duplicate
    hideInViewAutocompleteDropdown();
    return;
  }

  const cursorPosition = searchInput.selectionStart || rawVal.length;
  const textBeforeCursor = rawVal.slice(0, cursorPosition);
  const textAfterCursor = rawVal.slice(cursorPosition);

  // Split tokens before cursor
  const tokens = textBeforeCursor.split(/[\n,;]+/);
  // Replace the active typing token with the chosen code
  tokens[tokens.length - 1] = trimmedToInsert;

  // Build clean comma-separated list of unique codes
  const uniqueBefore = [];
  const seen = new Set();
  tokens.forEach(t => {
    const clean = t.trim();
    if (clean && !seen.has(clean.toLowerCase())) {
      seen.add(clean.toLowerCase());
      uniqueBefore.push(clean);
    }
  });

  // Also clean afterCursor to prevent trailing duplicate
  const tokensAfter = textAfterCursor
    .split(/[\n,;]+/)
    .map(t => t.trim())
    .filter(t => t && !seen.has(t.toLowerCase()));

  const allTokens = [...uniqueBefore, ...tokensAfter];
  const finalValue = allTokens.join(', ') + (allTokens.length > 0 ? ', ' : '');

  searchInput.value = finalValue;
  searchInput.focus();

  // Move cursor to end
  searchInput.setSelectionRange(finalValue.length, finalValue.length);

  // Hide dropdown and trigger canvas preview
  hideInViewAutocompleteDropdown();
  const searchClear = document.getElementById('search-clear-btn');
  if (searchClear) searchClear.style.display = 'block';

  renderSurface();
}


