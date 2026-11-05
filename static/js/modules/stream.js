/**
 * LUXE-TRACE - Live Camera Stream Controller
 * Connects to /video/feed 720p MJPEG stream and manages stream lifecycle
 */

function startRealCameraStream() {
  const liveImg = document.getElementById('camera-stream-img');
  if (liveImg) {
    // Set src to /video/feed to initiate the 720p MJPEG stream
    liveImg.src = '/video/feed';
  }

  // Update detection count meta
  fetch('/api/reports/reconcile')
    .then(res => res.json())
    .then(data => {
      const count = (data && data.summary) ? data.summary.frame_total : 0;
      const countElem = document.getElementById('feed-detection-count');
      if (countElem) {
        countElem.textContent = `${count} Codes`;
      }
    })
    .catch(() => {});
}

function stopRealCameraStream() {
  const liveImg = document.getElementById('camera-stream-img');
  if (liveImg) {
    // Setting src to empty string immediately closes the browser TCP socket,
    // which triggers Flask generator cleanup and stops network transmission completely.
    liveImg.src = '';
  }
}
