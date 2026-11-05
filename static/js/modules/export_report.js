/**
 * LUXE-TRACE - Custom Export Report Flow & Compiler
 * Scopes: full reconciliation, missing only, disputes only, verified only
 */

function runCustomExportFlow(scope = 'full', includeMetrics = true, autoPrint = true) {
  const configScreen = document.getElementById('export-config-screen');
  const loader = document.getElementById('export-loader');
  const report = document.getElementById('export-report');

  if (configScreen) configScreen.style.display = 'none';
  if (loader) loader.style.display = 'flex';
  if (report) report.style.display = 'none';

  console.log(`[API Call] Requesting reconciliation data for scope: ${scope}`);
  fetch('/api/reports/reconcile')
    .then(res => res.json())
    .then(data => {
      if (loader) loader.style.display = 'none';
      if (report) report.style.display = 'block';

      compileCustomReportData(data, scope, includeMetrics);

      if (autoPrint) {
        setTimeout(() => {
          window.print();
        }, 150);
      }
    })
    .catch(err => {
      console.error('[API Error] /api/reports/reconcile:', err);
      if (loader) loader.style.display = 'none';
      if (report) report.style.display = 'block';
      compileCustomReportData(null, scope, includeMetrics);
    });
}

function compileCustomReportData(realData, scope = 'full', includeMetrics = true) {
  const timestamp = realData && realData.timestamp ? realData.timestamp : new Date().toLocaleString();
  const timestampElem = document.getElementById('report-timestamp');
  if (timestampElem) timestampElem.textContent = `Generated: ${timestamp}`;

  // 1. Configure Title & Scope Sub-Header
  const titleElem = document.getElementById('report-main-title');
  const scopeMetaElem = document.getElementById('report-scope-meta');

  const titles = {
    'full': 'LUXE-TRACE INVENTORY RECONCILIATION REPORT',
    'missing': 'LUXE-TRACE MISSING DIAMONDS AUDIT REPORT',
    'disputes': 'LUXE-TRACE DISPUTE & UNREGISTERED CODES REPORT',
    'verified': 'LUXE-TRACE VERIFIED DIAMOND STOCK MANIFEST'
  };

  const scopeLabels = {
    'full': 'Scope: Full Reconciliation Audit (All 3 States)',
    'missing': 'Scope: State 2 Audit (Missing from Table Surface)',
    'disputes': 'Scope: State 3 Audit (Rogue & Unregistered Codes)',
    'verified': 'Scope: State 1 Manifest (Verified Diamonds On Surface)'
  };

  if (titleElem) titleElem.textContent = titles[scope] || titles['full'];
  if (scopeMetaElem) scopeMetaElem.textContent = scopeLabels[scope] || scopeLabels['full'];

  // 2. Metrics Strip Visibility
  const statsStrip = document.getElementById('rpt-stats-strip');
  if (statsStrip) {
    statsStrip.style.display = includeMetrics ? 'grid' : 'none';
  }

  // Section handles
  const verifiedSection = document.getElementById('rpt-verified-section');
  const missingSection = document.getElementById('rpt-missing-section');
  const disputesSection = document.getElementById('rpt-disputes-section');

  // Configure section visibility according to chosen scope
  if (verifiedSection) verifiedSection.style.display = (scope === 'full' || scope === 'verified') ? 'block' : 'none';
  if (missingSection) missingSection.style.display = (scope === 'full' || scope === 'missing') ? 'block' : 'none';
  if (disputesSection) disputesSection.style.display = (scope === 'full' || scope === 'disputes') ? 'block' : 'none';

  if (realData && realData.summary) {
    const s = realData.summary;
    const invEl = document.getElementById('rpt-total-inv');
    const matchedEl = document.getElementById('rpt-total-matched');
    const missingEl = document.getElementById('rpt-total-missing');
    const disputesEl = document.getElementById('rpt-total-disputes');

    if (invEl) invEl.textContent = s.inventory_total;
    if (matchedEl) matchedEl.textContent = s.verified_count;
    if (missingEl) missingEl.textContent = s.missing_count || s.absent_count || 0;
    if (disputesEl) disputesEl.textContent = s.dispute_count;

    // Populate Table 1: State 1 - In Frame (Verified)
    const frameTbody = document.getElementById('tbl-frame-codes-body');
    if (frameTbody) {
      frameTbody.innerHTML = '';
      const verifiedItems = realData.verified_items || [];

      if (verifiedItems.length === 0) {
        frameTbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted); text-align:center;">No verified codes currently present on table surface.</td></tr>';
      } else {
        verifiedItems.forEach(item => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><strong>${escapeHtml(item.stock_id)}</strong></td>
            <td>${escapeHtml(item.shape || '--')}</td>
            <td>${item.carat ? item.carat + ' ct' : '--'}</td>
            <td>${escapeHtml(item.color || '--')}</td>
            <td>${escapeHtml(item.clarity || '--')}</td>
            <td>${escapeHtml(item.first_seen || '--')}</td>
            <td><span style="color:var(--emerald-accent); font-weight:700;">VERIFIED</span></td>
          `;
          frameTbody.appendChild(tr);
        });
      }
    }

    // Populate Table 2: State 2 - Missing from Surface (In Inventory, Absent in View)
    const missingTbody = document.getElementById('tbl-missing-codes-body');
    if (missingTbody) {
      missingTbody.innerHTML = '';
      const missingItems = realData.missing_items || [];

      if (missingItems.length === 0) {
        missingTbody.innerHTML = '<tr><td colspan="7" style="color:var(--emerald-accent); text-align:center;">All inventory diamonds are accounted for on the surface. Zero missing items.</td></tr>';
      } else {
        missingItems.forEach(item => {
          const tr = document.createElement('tr');
          const colorClarity = [item.color, item.clarity].filter(Boolean).join(' / ') || '--';
          tr.innerHTML = `
            <td><strong style="color:var(--amber-accent);">${escapeHtml(item.stock_id)}</strong></td>
            <td>${escapeHtml(item.shape || '--')}</td>
            <td>${item.carat ? item.carat + ' ct' : '--'}</td>
            <td>${escapeHtml(colorClarity)}</td>
            <td>${escapeHtml(item.certificate_no || '--')}</td>
            <td>${escapeHtml(item.location || 'Vault / Tray')}</td>
            <td><span style="color:var(--amber-accent); font-weight:700;">MISSING FROM VIEW</span></td>
          `;
          missingTbody.appendChild(tr);
        });
      }
    }

    // Populate Table 3: State 3 - Disputes (Unregistered Codes in View)
    const disputeTbody = document.getElementById('tbl-disputes-body');
    if (disputeTbody) {
      disputeTbody.innerHTML = '';
      const disputeItems = realData.dispute_items || [];

      if (disputeItems.length === 0) {
        disputeTbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted); text-align:center;">No dispute codes detected on surface. All present codes match inventory.</td></tr>';
      } else {
        disputeItems.forEach(d => {
          const tr = document.createElement('tr');
          const posText = d.center ? `X: ${d.center[0]}, Y: ${d.center[1]}` : '--';
          tr.innerHTML = `
            <td><strong style="color:var(--rose-accent);">${escapeHtml(d.stock_id)}</strong></td>
            <td>${escapeHtml(posText)}</td>
            <td>${escapeHtml(d.first_seen || '--')}</td>
            <td><span style="color:var(--rose-accent); font-weight:700;">${escapeHtml(d.reason || 'Code physically present on table but absent from CRM Inventory.')}</span></td>
          `;
          disputeTbody.appendChild(tr);
        });
      }
    }
  } else {
    // Fallback if network fails
    const invEl = document.getElementById('rpt-total-inv');
    const matchedEl = document.getElementById('rpt-total-matched');
    const missingEl = document.getElementById('rpt-total-missing');
    const disputesEl = document.getElementById('rpt-total-disputes');

    if (invEl) invEl.textContent = '--';
    if (matchedEl) matchedEl.textContent = '--';
    if (missingEl) missingEl.textContent = '--';
    if (disputesEl) disputesEl.textContent = '--';
  }
}
