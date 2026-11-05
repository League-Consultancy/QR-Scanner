/**
 * LUXE-TRACE - Surface Canvas, Highlighting & Canvas Sizing
 */

function setupCanvases() {
  calibrationCanvas = document.getElementById('calibration-canvas');
  if (calibrationCanvas) calibrationCtx = calibrationCanvas.getContext('2d');
  
  cameraStreamCanvas = document.getElementById('camera-stream-canvas');
  if (cameraStreamCanvas) cameraStreamCtx = cameraStreamCanvas.getContext('2d');
}

function resizeCanvas(canvas) {
  if (!canvas || !canvas.parentElement) return;
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * window.devicePixelRatio;
  canvas.height = rect.height * window.devicePixelRatio;
  const ctx = canvas.getContext('2d');
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
}

function triggerPulseHighlight() {
  highlightPulse = 1.0;
  function anim() {
    highlightPulse -= 0.03;
    renderSurface();
    if (highlightPulse > 0) {
      requestAnimationFrame(anim);
    } else {
      highlightPulse = 0;
      renderSurface();
    }
  }
  requestAnimationFrame(anim);
}

function simulateStonesOnTable() {
  // Pick random inventory stones + 1 rogue/disputed code
  const shuffled = [...INVENTORY_DATABASE].sort(() => 0.5 - Math.random());
  const selected = shuffled.slice(0, 6);

  const now = new Date();
  activeStonesOnTable = selected.map((inv, idx) => ({
    stock_id: inv.stock_id,
    x: 120 + (idx % 3) * 220 + Math.random() * 30,
    y: 100 + Math.floor(idx / 3) * 160 + Math.random() * 20,
    first_seen: now.toLocaleTimeString(),
    is_dispute: false,
    details: inv
  }));

  // Add 1 rogue/dispute code
  activeStonesOnTable.push({
    stock_id: "UNKNOWN-999",
    x: 480,
    y: 260,
    first_seen: now.toLocaleTimeString(),
    is_dispute: true,
    details: null
  });

  updateAuditMetrics();
}

function updateAuditMetrics() {
  const elInFrame = document.getElementById('stat-in-frame');
  const elMatched = document.getElementById('stat-matched');
  const elDisputes = document.getElementById('stat-disputes');
  const hint = document.getElementById('dispute-hint');

  if (elInFrame && elMatched && elDisputes) {
    const inFrame = activeStonesOnTable.length;
    const disputes = activeStonesOnTable.filter(s => s.is_dispute).length;
    const matched = inFrame - disputes;

    elInFrame.textContent = inFrame;
    elMatched.textContent = matched;
    elDisputes.textContent = disputes;

    if (hint) {
      if (disputes > 0) {
        hint.innerHTML = `<span style="color: var(--rose-accent);">⚠ ${disputes} rogue/unregistered code(s) on desk!</span>`;
      } else {
        hint.textContent = "● System in sync: No rogue codes.";
      }
    }
  }

  // Update empty state display (if element exists)
  const empty = document.getElementById('surface-empty');
  if (empty) {
    empty.style.display = activeStonesOnTable.length === 0 ? 'block' : 'none';
  }
}

function renderSurface() {
  if (!surfaceCanvas || !surfaceCtx || !surfaceCanvas.parentElement) return;
  const width = surfaceCanvas.parentElement.clientWidth;
  const height = surfaceCanvas.parentElement.clientHeight;

  surfaceCtx.clearRect(0, 0, width, height);

  // Draw background grid lines (Projector alignment visual)
  surfaceCtx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
  surfaceCtx.lineWidth = 1;
  const gridSize = 40;
  for (let x = 0; x < width; x += gridSize) {
    surfaceCtx.beginPath();
    surfaceCtx.moveTo(x, 0);
    surfaceCtx.lineTo(x, height);
    surfaceCtx.stroke();
  }
  for (let y = 0; y < height; y += gridSize) {
    surfaceCtx.beginPath();
    surfaceCtx.moveTo(0, y);
    surfaceCtx.lineTo(width, y);
    surfaceCtx.stroke();
  }

  // Matching items based on committed filters & search
  const matchingInventory = getMatchingInventoryItems(committedFilters);
  const matchingStockIds = new Set(matchingInventory.map(i => i.stock_id));

  // Render each stone
  activeStonesOnTable.forEach(stone => {
    // Determine color styling for this stone
    const assignedBatchColor = codeColorMap[stone.stock_id] || codeColorMap[stone.stock_id.toLowerCase()];
    const isTargetMatched = matchingStockIds.has(stone.stock_id) || Boolean(assignedBatchColor);
    const isDispute = stone.is_dispute;

    // Default match color is Emerald Green, or custom batch color if assigned
    const activeColorHex = isDispute ? '#f43f5e' : (assignedBatchColor ? assignedBatchColor.hex : (isTargetMatched ? '#10b981' : '#64748b'));

    // Draw Data Matrix bounding box simulation
    surfaceCtx.save();
    surfaceCtx.translate(stone.x, stone.y);

    const boxSize = 54;
    surfaceCtx.strokeStyle = activeColorHex;
    surfaceCtx.lineWidth = isTargetMatched ? 2.5 : 1.5;

    // Light up whole area when highlighted/matched
    if (isTargetMatched) {
      surfaceCtx.save();
      surfaceCtx.fillStyle = activeColorHex;
      surfaceCtx.globalAlpha = 0.35;
      surfaceCtx.fillRect(-boxSize/2, -boxSize/2, boxSize, boxSize);
      surfaceCtx.restore();
    }

    surfaceCtx.strokeRect(-boxSize/2, -boxSize/2, boxSize, boxSize);

    // If highlighted match or active pulse, draw radiant glow rings
    if (isTargetMatched || highlightPulse > 0) {
      const pulseRadius = (boxSize / 1.5) + (highlightPulse * 24);
      surfaceCtx.beginPath();
      surfaceCtx.arc(0, 0, pulseRadius, 0, Math.PI * 2);
      surfaceCtx.strokeStyle = isTargetMatched ? activeColorHex : 'rgba(99, 102, 241, 0.3)';
      surfaceCtx.lineWidth = 2;
      surfaceCtx.stroke();

      // Corner target brackets
      const bracketLen = 8;
      surfaceCtx.strokeStyle = activeColorHex;
      surfaceCtx.beginPath();
      // TL
      surfaceCtx.moveTo(-boxSize/2 - 4, -boxSize/2 + bracketLen);
      surfaceCtx.lineTo(-boxSize/2 - 4, -boxSize/2 - 4);
      surfaceCtx.lineTo(-boxSize/2 + bracketLen, -boxSize/2 - 4);
      // TR
      surfaceCtx.moveTo(boxSize/2 + 4 - bracketLen, -boxSize/2 - 4);
      surfaceCtx.lineTo(boxSize/2 + 4, -boxSize/2 - 4);
      surfaceCtx.lineTo(boxSize/2 + 4, -boxSize/2 + bracketLen);
      surfaceCtx.stroke();
    }

    // Label Text
    surfaceCtx.font = '600 11px JetBrains Mono, monospace';
    surfaceCtx.fillStyle = activeColorHex;
    surfaceCtx.textAlign = 'center';
    surfaceCtx.fillText(stone.stock_id, 0, boxSize/2 + 16);

    if (stone.details) {
      surfaceCtx.font = '500 9px Plus Jakarta Sans, sans-serif';
      surfaceCtx.fillStyle = '#64748b';
      surfaceCtx.fillText(`${stone.details.shape} • ${stone.details.carat}ct • ${stone.details.color}`, 0, boxSize/2 + 28);
    } else if (isDispute) {
      surfaceCtx.font = '700 9px Plus Jakarta Sans, sans-serif';
      surfaceCtx.fillStyle = '#f43f5e';
      surfaceCtx.fillText(`DISPUTE / ROGUE`, 0, boxSize/2 + 28);
    }

    surfaceCtx.restore();
  });
}
