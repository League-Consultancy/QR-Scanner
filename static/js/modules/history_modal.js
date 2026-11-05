/**
 * LUXE-TRACE - Scan History & Daily Log Timeline Controller
 * Querying date ranges, timeline table rendering, CSV export
 */

function initHistoryModal() {
  const startDateInput = document.getElementById('history-start-date');
  const endDateInput = document.getElementById('history-end-date');
  const queryBtn = document.getElementById('btn-query-history');
  const exportBtn = document.getElementById('btn-export-history-csv');
  const presetBtns = document.querySelectorAll('.preset-btn');

  // Set default dates to Today
  const today = new Date().toISOString().split('T')[0];
  if (startDateInput && !startDateInput.value) startDateInput.value = today;
  if (endDateInput && !endDateInput.value) endDateInput.value = today;

  // Preset Handlers
  presetBtns.forEach(btn => {
    btn.onclick = () => {
      presetBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const preset = btn.dataset.preset;
      const now = new Date();
      let start = new Date();
      let end = new Date();

      if (preset === 'today') {
        start = now;
        end = now;
      } else if (preset === 'yesterday') {
        start.setDate(now.getDate() - 1);
        end.setDate(now.getDate() - 1);
      } else if (preset === 'week') {
        start.setDate(now.getDate() - 7);
        end = now;
      } else if (preset === 'month') {
        start.setDate(now.getDate() - 30);
        end = now;
      }

      if (startDateInput) startDateInput.value = start.toISOString().split('T')[0];
      if (endDateInput) endDateInput.value = end.toISOString().split('T')[0];
      queryHistoryData();
    };
  });

  if (queryBtn) {
    queryBtn.onclick = () => {
      presetBtns.forEach(b => b.classList.remove('active'));
      queryHistoryData();
    };
  }

  if (exportBtn) {
    exportBtn.onclick = exportHistoryCSV;
  }

  // Load initial today's data
  queryHistoryData();
}

function queryHistoryData() {
  const startInput = document.getElementById('history-start-date');
  const endInput = document.getElementById('history-end-date');
  const codeInput = document.getElementById('history-filter-code');
  const tbody = document.getElementById('tbl-history-results-body');

  const startDate = startInput ? startInput.value : '';
  const endDate = endInput ? endInput.value : '';
  const specificCode = (codeInput ? codeInput.value : '').trim();

  if (!startDate || !endDate) {
    alert("Please select both start and end dates.");
    return;
  }

  // Check 60-day limit
  const d1 = new Date(startDate);
  const d2 = new Date(endDate);
  const diffDays = Math.ceil(Math.abs(d2 - d1) / (1000 * 60 * 60 * 24)) + 1;

  if (diffDays > 62) {
    alert(`Selected range is ${diffDays} days. The maximum allowable query range is 60 days (approx. 2 months). Please narrow your date range.`);
    return;
  }

  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="6" class="history-loading-cell">Searching history logs from ${startDate} to ${endDate}...</td></tr>`;
  }

  let url = `/api/history?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`;
  if (specificCode) {
    url += `&code=${encodeURIComponent(specificCode)}`;
  }

  fetch(url)
    .then(res => res.json())
    .then(data => {
      if (data.status === 'error') {
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="history-loading-cell" style="color:var(--rose-accent);">${escapeHtml(data.message)}</td></tr>`;
        return;
      }

      historySessionsData = data.sessions || [];
      renderHistoryTable(data);
    })
    .catch(err => {
      console.error('[History] Error querying history:', err);
      if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="history-loading-cell" style="color:var(--rose-accent);">Failed to load history records. Please check server logs.</td></tr>`;
    });
}

function renderHistoryTable(data) {
  const tbody = document.getElementById('tbl-history-results-body');
  const statVisits = document.getElementById('hist-stat-visits');
  const statUnique = document.getElementById('hist-stat-unique');
  const statDwell = document.getElementById('hist-stat-dwell');
  const statActive = document.getElementById('hist-stat-active');

  const sessions = data.sessions || [];
  if (statVisits) statVisits.textContent = data.total_records || 0;
  if (statUnique) statUnique.textContent = data.total_unique_codes || 0;
  if (statDwell) statDwell.textContent = data.total_dwell_formatted || '--';

  const activeCount = sessions.filter(s => s.status === 'ACTIVE').length;
  if (statActive) statActive.textContent = activeCount;

  if (!tbody) return;

  if (sessions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="history-loading-cell">No scan records found for the selected date range and filter criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = '';
  sessions.forEach(s => {
    const tr = document.createElement('tr');

    const isActive = (s.status === 'ACTIVE');
    const crmTag = s.crm_status === 'VERIFIED'
      ? `<span style="color:var(--emerald-accent); font-weight:700;">VERIFIED</span>`
      : `<span style="color:var(--rose-accent); font-weight:700;">DISPUTE</span>`;

    const shapeCarat = (s.shape && s.shape !== '--')
      ? `${s.shape} • ${s.carat}ct (${s.color || ''})`
      : crmTag;

    // Requirement: Status column removed, only active stones indicated in Time Out
    tr.innerHTML = `
      <td>
        <div class="hist-code-cell" title="Click to filter this code">
          <span>${escapeHtml(s.code)}</span>
        </div>
      </td>
      <td>${s.date}</td>
      <td><strong>${s.in}</strong></td>
      <td>${isActive ? '<span style="color:var(--emerald-accent); font-weight:700;">Active Now</span>' : s.out}</td>
      <td>${s.duration}</td>
      <td style="color:var(--text-muted);">${shapeCarat}</td>
    `;

    // Click on code row to focus that specific diamond
    const codeCell = tr.querySelector('.hist-code-cell');
    if (codeCell) {
      codeCell.addEventListener('click', () => {
        const filterInput = document.getElementById('history-filter-code');
        if (filterInput) filterInput.value = s.code;
        queryHistoryData();
      });
    }

    tbody.appendChild(tr);
  });
}

function exportHistoryCSV() {
  if (!historySessionsData || historySessionsData.length === 0) {
    alert("No history records to export. Please run a query with matching results first.");
    return;
  }

  // Requirement: Removed Status from CSV header and rows
  const headers = ["Diamond_Code", "Date", "Time_In", "Time_Out", "Duration", "Shape", "Carat", "Color", "Clarity", "CRM_Status"];
  const rows = [headers.join(",")];

  historySessionsData.forEach(s => {
    const row = [
      `"${s.code || ''}"`,
      `"${s.date || ''}"`,
      `"${s.in || ''}"`,
      `"${s.status === 'ACTIVE' ? 'Active Now' : (s.out || '')}"`,
      `"${s.duration || ''}"`,
      `"${s.shape || ''}"`,
      `"${s.carat || ''}"`,
      `"${s.color || ''}"`,
      `"${s.clarity || ''}"`,
      `"${s.crm_status || ''}"`
    ];
    rows.push(row.join(","));
  });

  const csvContent = "data:text/csv;charset=utf-8," + rows.join("\n");
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", `luxe_trace_history_${new Date().toISOString().split('T')[0]}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
