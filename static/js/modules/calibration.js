/**
 * LUXE-TRACE - Calibration Interactive Controller
 * Single snapshot capture, 4-point alignment UI, homography coordinate mapping
 */

function checkCalibrationStatus() {
  fetch('/api/calibration/status')
    .then(res => res.json())
    .then(data => {
      isSystemCalibrated = Boolean(data.is_calibrated);
      updateCalibrationUI(isSystemCalibrated);
    })
    .catch(err => {
      console.warn('[Calibration] Could not check status from backend:', err);
      updateCalibrationUI(false);
    });
}

function updateCalibrationUI(calibrated) {
  isSystemCalibrated = calibrated;
  const statusLabel = document.getElementById('header-calib-status');
  const pill = statusLabel ? statusLabel.closest('.status-pill') : null;
  const highlightBtn = document.getElementById('btn-project-highlight');

  if (statusLabel) {
    statusLabel.textContent = calibrated ? 'ALIGNED' : 'NOT CALIBRATED';
  }

  if (pill) {
    if (calibrated) {
      pill.style.borderColor = 'rgba(16, 185, 129, 0.4)';
      pill.style.background = 'rgba(16, 185, 129, 0.1)';
      pill.title = 'Projector homography matrix is loaded and active.';
    } else {
      pill.style.borderColor = 'rgba(245, 158, 11, 0.4)';
      pill.style.background = 'rgba(245, 158, 11, 0.1)';
      pill.title = 'No calibration saved. Projection highlighting is disabled until calibrated.';
    }
  }

  if (highlightBtn) {
    if (calibrated) {
      highlightBtn.style.opacity = '1.0';
      highlightBtn.style.cursor = 'pointer';
      highlightBtn.title = 'Project highlight onto active matches';
    } else {
      highlightBtn.style.opacity = '0.45';
      highlightBtn.style.cursor = 'not-allowed';
      highlightBtn.title = 'Projector not calibrated. Click Re-Calibrate in sidebar to enable.';
    }
  }
}

function initCalibrationCanvas() {
  resizeCanvas(calibrationCanvas);
  resetCalibration();

  // Load a single static snapshot frame from the real camera
  calibSnapshotImg = new Image();
  fetch(`/api/camera/snapshot?t=${Date.now()}`)
    .then(res => {
      const rawW = parseInt(res.headers.get("X-Raw-Width")) || 1920;
      const rawH = parseInt(res.headers.get("X-Raw-Height")) || 1080;
      calibRawDimensions = { width: rawW, height: rawH };
      return res.blob();
    })
    .then(blob => {
      calibSnapshotImg.src = URL.createObjectURL(blob);
      calibSnapshotImg.onload = () => {
        renderCalibrationView();
      };
    })
    .catch(err => {
      console.error("[Calibration] Failed to fetch camera snapshot:", err);
      calibSnapshotImg = null;
      renderCalibrationView();
    });

  if (!calibrationCanvas) return;

  calibrationCanvas.onclick = (e) => {
    if (recordedCalibPoints.length >= 4) return;
    const rect = calibrationCanvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    // Convert display canvas coordinates to raw camera frame coordinates
    const scaleX = calibRawDimensions.width / rect.width;
    const scaleY = calibRawDimensions.height / rect.height;
    const rawX = Math.round(clickX * scaleX);
    const rawY = Math.round(clickY * scaleY);

    // Save display coordinates for drawing overlay, and raw coordinates for homography computation
    recordedCalibPoints.push({
      displayX: clickX,
      displayY: clickY,
      x: rawX,
      y: rawY
    });

    updateCalibrationStepUI();
    renderCalibrationView();
  };

  calibrationCanvas.onmousemove = (e) => {
    const rect = calibrationCanvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    const scaleX = calibRawDimensions.width / rect.width;
    const scaleY = calibRawDimensions.height / rect.height;
    const rawX = Math.round(clickX * scaleX);
    const rawY = Math.round(clickY * scaleY);
    const coordsPreview = document.getElementById('calib-coords-preview');
    if (coordsPreview) {
      coordsPreview.textContent = `Pointer: [Cam X: ${rawX}, Cam Y: ${rawY}]`;
    }
  };

  renderCalibrationView();
}

function resetCalibration() {
  recordedCalibPoints = [];
  updateCalibrationStepUI();
  renderCalibrationView();
}

function updateCalibrationStepUI() {
  const count = recordedCalibPoints.length;
  const countElem = document.getElementById('calib-points-count');
  if (countElem) countElem.textContent = `Points: ${count} / 4`;
  const saveBtn = document.getElementById('btn-save-calibration');
  const tagElem = document.getElementById('calib-step-tag');
  const instructionElem = document.getElementById('calib-instruction');

  if (count < 4) {
    const currentStep = CALIBRATION_STEPS[count];
    if (tagElem) tagElem.textContent = currentStep.tag;
    if (instructionElem) instructionElem.innerHTML = `Click on projector reference <strong>Point ${count + 1}: ${currentStep.name}</strong> on the camera canvas below.`;
    if (saveBtn) saveBtn.disabled = true;
  } else {
    if (tagElem) tagElem.textContent = 'CALIBRATION COMPLETE';
    if (instructionElem) instructionElem.innerHTML = `All 4 reference points collected! Ready to compute 3x3 Homography Matrix.`;
    if (saveBtn) saveBtn.disabled = false;
  }
}

function renderCalibrationView() {
  if (!calibrationCtx || !calibrationCanvas) return;
  const rect = calibrationCanvas.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;
  calibrationCtx.clearRect(0, 0, w, h);

  // 1. Draw the actual camera snapshot as background
  if (calibSnapshotImg && calibSnapshotImg.complete && calibSnapshotImg.naturalWidth > 0) {
    calibrationCtx.drawImage(calibSnapshotImg, 0, 0, w, h);
  } else {
    // Dark placeholder while loading snapshot
    calibrationCtx.fillStyle = '#080a0f';
    calibrationCtx.fillRect(0, 0, w, h);
    calibrationCtx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    calibrationCtx.font = '14px JetBrains Mono';
    calibrationCtx.textAlign = 'center';
    calibrationCtx.fillText('Loading camera snapshot...', w / 2, h / 2);
    calibrationCtx.textAlign = 'left';
  }

  // 2. Subtle coordinate grid overlay
  calibrationCtx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  calibrationCtx.lineWidth = 1;
  for (let x = 0; x < w; x += 60) {
    calibrationCtx.beginPath();
    calibrationCtx.moveTo(x, 0);
    calibrationCtx.lineTo(x, h);
    calibrationCtx.stroke();
  }
  for (let y = 0; y < h; y += 60) {
    calibrationCtx.beginPath();
    calibrationCtx.moveTo(0, y);
    calibrationCtx.lineTo(w, y);
    calibrationCtx.stroke();
  }

  // 3. Draw connecting polygon between registered points
  if (recordedCalibPoints.length > 1) {
    calibrationCtx.beginPath();
    calibrationCtx.moveTo(recordedCalibPoints[0].displayX, recordedCalibPoints[0].displayY);
    for (let i = 1; i < recordedCalibPoints.length; i++) {
      calibrationCtx.lineTo(recordedCalibPoints[i].displayX, recordedCalibPoints[i].displayY);
    }
    if (recordedCalibPoints.length === 4) {
      calibrationCtx.closePath();
      calibrationCtx.fillStyle = 'rgba(99, 102, 241, 0.15)';
      calibrationCtx.fill();
    }
    calibrationCtx.strokeStyle = '#6366f1';
    calibrationCtx.lineWidth = 2;
    calibrationCtx.stroke();
  }

  // 4. Draw high-visibility target crosshairs for recorded points
  recordedCalibPoints.forEach((pt, i) => {
    const dx = pt.displayX;
    const dy = pt.displayY;

    // Glowing circle
    calibrationCtx.beginPath();
    calibrationCtx.arc(dx, dy, 7, 0, Math.PI * 2);
    calibrationCtx.fillStyle = '#06b6d4';
    calibrationCtx.fill();
    calibrationCtx.strokeStyle = '#ffffff';
    calibrationCtx.lineWidth = 2;
    calibrationCtx.stroke();

    // Crosshairs
    calibrationCtx.beginPath();
    calibrationCtx.moveTo(dx - 14, dy);
    calibrationCtx.lineTo(dx + 14, dy);
    calibrationCtx.moveTo(dx, dy - 14);
    calibrationCtx.lineTo(dx, dy + 14);
    calibrationCtx.strokeStyle = '#06b6d4';
    calibrationCtx.lineWidth = 1.5;
    calibrationCtx.stroke();

    // Label with raw camera pixel coordinates
    calibrationCtx.font = '700 12px JetBrains Mono';
    calibrationCtx.fillStyle = '#06b6d4';
    calibrationCtx.fillText(`P${i + 1} (${pt.x}, ${pt.y})`, dx + 12, dy - 8);
  });
}
