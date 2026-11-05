/**
 * LUXE-TRACE - Optical Inventory & Picking Engine
 * Global State & Constants
 */

// Authoritative Diamond Inventory (Loaded dynamically from Backend / DiamDash CRM)
var INVENTORY_DATABASE = [];

// Active items currently placed on the table/seen by camera
var activeStonesOnTable = [];

// Filter States
var committedFilters = {};
var draftFilters = {};

// Calibration State (4 points: TL, TR, BR, BL)
var CALIBRATION_STEPS = [
  { name: "Top-Left (TL)", tag: "STEP 1 OF 4", projX: 0, projY: 0 },
  { name: "Top-Right (TR)", tag: "STEP 2 OF 4", projX: 1920, projY: 0 },
  { name: "Bottom-Right (BR)", tag: "STEP 3 OF 4", projX: 1920, projY: 1080 },
  { name: "Bottom-Left (BL)", tag: "STEP 4 OF 4", projX: 0, projY: 1080 }
];
var recordedCalibPoints = [];

// Animation / Canvas handles
var surfaceCanvas = null, surfaceCtx = null;
var calibrationCanvas = null, calibrationCtx = null;
var cameraStreamCanvas = null, cameraStreamCtx = null;
var streamAnimId = null;

// Calibration verification state
var isSystemCalibrated = false;

// Calibration snapshot state
var calibSnapshotImg = null;
var calibRawDimensions = { width: 1980, height: 1080 };

// Sidebar & History State
var invSearchFilterText = '';
var latestInViewData = null;
var historySessionsData = [];

// Pulse highlight animation trigger level
var highlightPulse = 0;

// Vibrant highlight color palette for consecutive search batches
// Each entry provides:
// - hex: Web UI hex color for badges, surface canvas glow, and brackets
// - bgr: OpenCV Projector drawing tuple [B, G, R]
// - name: Human-readable label for user badge
var HIGHLIGHT_PALETTES = [
  { name: 'Emerald Green', hex: '#10b981', bgr: [129, 255, 16], bgLight: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.4)' },
  { name: 'Electric Cyan', hex: '#06b6d4', bgr: [255, 200, 0],   bgLight: 'rgba(6, 182, 212, 0.15)', border: 'rgba(6, 182, 212, 0.4)' },
  { name: 'Vibrant Amber', hex: '#f59e0b', bgr: [0, 165, 255],   bgLight: 'rgba(245, 158, 11, 0.15)', border: 'rgba(245, 158, 11, 0.4)' },
  { name: 'Neon Violet',   hex: '#a855f7', bgr: [247, 85, 168],  bgLight: 'rgba(168, 85, 247, 0.15)', border: 'rgba(168, 85, 247, 0.4)' },
  { name: 'Coral Pink',    hex: '#f43f5e', bgr: [94, 63, 244],   bgLight: 'rgba(244, 63, 94, 0.15)',  border: 'rgba(244, 63, 94, 0.4)' },
  { name: 'Electric Blue', hex: '#3b82f6', bgr: [246, 130, 59],  bgLight: 'rgba(59, 130, 246, 0.15)', border: 'rgba(59, 130, 246, 0.4)' }
];

// Active multi-search highlight batches
// Each batch: { id, label, codes: [...], color: { name, hex, bgr, ... } }
var activeHighlightBatches = [];
// Fast lookup map: normalized_code -> colorObject
var codeColorMap = {};

// Selected code IDs from the Filter Matching Diamonds section
var selectedFilterMatchCodes = new Set();

/**
 * Global utility to escape HTML characters
 */
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
