/**
 * LUXE-TRACE - Sidebar Codes Tracker
 * Manages 'In View' live codes stream, 'Master Inventory' list, and search cross-linking
 */

function setupSidebarCodesTracker() {
  const tabInview = document.getElementById('tab-btn-inview');
  const tabInv = document.getElementById('tab-btn-inventory');
  const contentInview = document.getElementById('tab-content-inview');
  const contentInv = document.getElementById('tab-content-inventory');
  const invSearchInput = document.getElementById('sidebar-inv-search');

  if (tabInview && tabInv && contentInview && contentInv) {
    tabInview.addEventListener('click', () => {
      tabInview.classList.add('active');
      tabInv.classList.remove('active');
      contentInview.classList.add('active');
      contentInv.classList.remove('active');
    });

    tabInv.addEventListener('click', () => {
      tabInv.classList.add('active');
      tabInview.classList.remove('active');
      contentInv.classList.add('active');
      contentInview.classList.remove('active');
    });
  }

  if (invSearchInput) {
    invSearchInput.addEventListener('input', (e) => {
      invSearchFilterText = (e.target.value || '').trim().toLowerCase();
      renderSidebarInventoryCodes();
    });
  }

  // Initial fetch and start continuous polling for In-View codes every 2.5 seconds
  pollInViewCodes();
  setInterval(pollInViewCodes, 2500);
}

function pollInViewCodes() {
  fetch('/api/reports/reconcile')
    .then(res => res.json())
    .then(data => {
      renderSidebarInViewCodes(data);
    })
    .catch(err => {
      console.warn('[Sidebar] Error polling in-view codes:', err);
    });
}

function renderSidebarInViewCodes(data) {
  latestInViewData = data;
  const container = document.getElementById('list-inview-codes');
  const badge = document.getElementById('badge-inview-count');
  if (!container || !badge) return;

  const verified = (data && data.verified_items) ? data.verified_items : [];
  const disputes = (data && data.dispute_items) ? data.dispute_items : [];
  const totalInView = verified.length + disputes.length;

  badge.textContent = totalInView;

  if (totalInView === 0) {
    container.innerHTML = '<div class="codes-empty-state">No codes currently detected in camera view</div>';
    return;
  }

  container.innerHTML = '';

  // Render Verified Items
  verified.forEach(item => {
    const card = document.createElement('div');
    card.className = 'code-item-card';
    card.title = `Click to filter: ${item.stock_id}`;
    
    const caratStr = item.carat ? `${item.carat}ct` : '';
    const shapeStr = item.shape || '';
    const subParts = [shapeStr, caratStr].filter(Boolean).join(' • ');

    card.innerHTML = `
      <div class="code-item-main">
        <span class="code-item-id">${escapeHtml(item.stock_id)}</span>
        <span class="code-item-sub">${escapeHtml(subParts || 'Active')}</span>
      </div>
      <span class="code-status-pill code-status-verified">VERIFIED</span>
    `;

    card.addEventListener('click', () => {
      focusCodeInGlobalSearch(item.stock_id);
    });

    container.appendChild(card);
  });

  // Render Dispute Items (Unregistered or Unknown in view)
  disputes.forEach(item => {
    const card = document.createElement('div');
    card.className = 'code-item-card';
    card.title = `Dispute code: ${item.stock_id}`;

    card.innerHTML = `
      <div class="code-item-main">
        <span class="code-item-id" style="color:var(--rose-accent);">${escapeHtml(item.stock_id)}</span>
        <span class="code-item-sub">Not in CRM</span>
      </div>
      <span class="code-status-pill code-status-dispute">DISPUTE</span>
    `;

    card.addEventListener('click', () => {
      focusCodeInGlobalSearch(item.stock_id);
    });

    container.appendChild(card);
  });
}

function renderSidebarInventoryCodes() {
  const container = document.getElementById('list-inventory-codes');
  const badge = document.getElementById('badge-inv-count');
  if (!container || !badge) return;

  const items = INVENTORY_DATABASE || [];
  badge.textContent = items.length;

  const filtered = items.filter(d => {
    if (!invSearchFilterText) return true;
    const sId = (d.stock_id || '').toLowerCase();
    const cert = (d.cert_num || d.certificate_no || '').toLowerCase();
    const shape = (d.shape || '').toLowerCase();
    return sId.includes(invSearchFilterText) || cert.includes(invSearchFilterText) || shape.includes(invSearchFilterText);
  });

  if (filtered.length === 0) {
    if (items.length === 0) {
      container.innerHTML = '<div class="codes-empty-state">No inventory items loaded</div>';
    } else {
      container.innerHTML = '<div class="codes-empty-state">No codes match filter</div>';
    }
    return;
  }

  container.innerHTML = '';

  filtered.forEach(item => {
    const card = document.createElement('div');
    card.className = 'code-item-card';
    card.title = `Stock ID: ${item.stock_id} | Click to filter`;

    const caratVal = item.ct || item.carat;
    const caratStr = caratVal ? `${Number(caratVal).toFixed(2)}ct` : '';
    const colorDisplay = item.fancy_color ? `Fancy ${item.fancy_color}` : item.color;
    const colorClarity = [colorDisplay, item.clarity].filter(Boolean).join(' ');
    const subParts = [item.shape, caratStr, colorClarity, item.measurements].filter(Boolean).join(' • ');

    card.innerHTML = `
      <div class="code-item-main">
        <span class="code-item-id">${escapeHtml(item.stock_id)}</span>
        <span class="code-item-sub">${escapeHtml(subParts || 'Master Inventory')}</span>
      </div>
      <span class="code-status-pill code-status-inventory">ON HAND</span>
    `;

    card.addEventListener('click', () => {
      focusCodeInGlobalSearch(item.stock_id);
    });

    container.appendChild(card);
  });
}

function focusCodeInGlobalSearch(code) {
  const globalInput = document.getElementById('global-search-input');
  if (globalInput) {
    globalInput.value = code;
    globalInput.dispatchEvent(new Event('input', { bubbles: true }));
    globalInput.focus();
  }
}
