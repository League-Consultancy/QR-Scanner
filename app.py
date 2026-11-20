#!/usr/bin/env python3
"""
LUXE-TRACE - Optical Inventory & Picking Engine
Flask Web Application Server & Background Vision Engine
"""

import os
import sys
import time
import signal
import threading
import cv2
import numpy as np
from datetime import timedelta
from flask import Flask, render_template, jsonify, request, Response, session, redirect, url_for

from scanner import Scanner
from calibration import CalibrationManager
from inventory_manager import InventoryManager
from auth_manager import AuthManager
import history_logger

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)
app.secret_key = os.environ.get("SECRET_KEY", "luxetrace-super-secret-key-2026-optical-engine")
app.permanent_session_lifetime = timedelta(hours=12)

# ==============================================================================
# 1. HARDWARE / BACKGROUND DETECTION STATE & THREAD
# ==============================================================================
scanner = Scanner(num_workers=4)
calibration_mgr = CalibrationManager()
inventory_mgr = InventoryManager()
auth_mgr = AuthManager()

# Local dictionary keeping all detected records & presence timestamps
detected_inventory = {}
inventory_lock = threading.Lock()

# Target codes currently requested to be highlighted by the projector (dict: code -> (B, G, R))
marked_codes = {}
marked_codes_lock = threading.Lock()

# Projector display dimensions & second screen coordinates
PROJECTOR_WIDTH = int(os.environ.get("PROJECTOR_WIDTH", 1920))
PROJECTOR_HEIGHT = int(os.environ.get("PROJECTOR_HEIGHT", 1080))
PROJECTOR_X_OFFSET = int(os.environ.get("PROJECTOR_X_OFFSET", 1920))  # Default: placed on second display to the right of primary
PROJECTOR_Y_OFFSET = int(os.environ.get("PROJECTOR_Y_OFFSET", 0))

# Global thread control & frame cache
capture_running = True
latest_frame = None
frame_lock = threading.Lock()
frame_counter = 0

def projector_display_loop(window_name="LUXE-TRACE Projector"):
    """
    Dedicated fullscreen projector display thread:
    - Runs a continuous loop showing a pure black 1080p canvas.
    - Inspects marked_codes and draws perspective-mapped bounding boxes for present items.
    - Displays on the secondary monitor/projector screen via cv2.imshow.
    """
    print("[Projector Engine] Initializing projector display window...")

    try:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        # Position window on second monitor before entering fullscreen
        cv2.moveWindow(window_name, PROJECTOR_X_OFFSET, PROJECTOR_Y_OFFSET)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    except Exception as e:
        print(f"[Projector Engine] Window positioning warning: {e}")

    while capture_running:
        # 1. Create pure black 1080p canvas (RGB 0,0,0)
        proj_canvas = np.zeros((PROJECTOR_HEIGHT, PROJECTOR_WIDTH, 3), dtype=np.uint8)

        # 2. Check which codes are marked for highlight (code -> (B, G, R))
        with marked_codes_lock:
            active_targets = dict(marked_codes)

        if active_targets and calibration_mgr.homography_matrix is not None:
            # Normalize active targets for flexible lookup (lowercase -> (original_code, (B, G, R)))
            norm_targets = {str(c).strip().lower(): (c, color) for c, color in active_targets.items()}

            with inventory_lock:
                for detected_code, item in detected_inventory.items():
                    norm_code = str(detected_code).strip().lower()
                    color_tuple = None
                    if detected_code in active_targets:
                        color_tuple = active_targets[detected_code]
                    elif norm_code in norm_targets:
                        color_tuple = norm_targets[norm_code][1]

                    if color_tuple and item.get('status') == 'present' and 'points' in item:
                        cam_points = item['points']
                        # Map 4K camera bounding quadrilateral to 1080p projector coordinates
                        proj_poly = calibration_mgr.map_polygon(cam_points)

                        if proj_poly is not None and len(proj_poly) == 4:
                            # Light up the entire QR code area with the assigned batch BGR color
                            box_bgr = tuple(int(c) for c in color_tuple)
                            cv2.fillPoly(proj_canvas, [proj_poly], color=box_bgr)
                            # Draw crisp outer boundary to keep edges sharp
                            cv2.polylines(proj_canvas, [proj_poly], isClosed=True, color=box_bgr, thickness=2)

                            # Center target point
                            cx = int(sum(pt[0] for pt in proj_poly) / 4.0)
                            cy = int(sum(pt[1] for pt in proj_poly) / 4.0)
                            cv2.circle(proj_canvas, (cx, cy), 4, (255, 255, 255), -1)

        try:
            cv2.imshow(window_name, proj_canvas)
            key = cv2.waitKey(16) & 0xFF  # ~60 FPS refresh
            if key == 27:  # ESC to exit projector window if pressed
                break
        except Exception as e:
            # Headless or display error fallback
            time.sleep(0.05)

    try:
        cv2.destroyWindow(window_name)
    except Exception:
        pass
    print("[Projector Engine] Projector display thread terminated.")

def inventory_auto_sync_loop(interval_seconds=900):
    """
    Background worker thread:
    - Runs automatically every 15 minutes (900 seconds)
    - Syncs latest certified/on-hand diamond records from DiamDash CRM API
    - Updates local memory and persistent cache
    """
    print(f"[Inventory Auto-Sync] Service initialized (recurring interval = {interval_seconds // 60} minutes).")
    
    # Wait a few seconds after startup before the first background sync
    time.sleep(10)
    
    while capture_running:
        print("[Inventory Auto-Sync] Starting scheduled 15-minute inventory synchronization...")
        try:
            res = inventory_mgr.sync_from_crm(status="on_hand")
            if res.get("status") == "success":
                print(f"[Inventory Auto-Sync] Periodic sync completed successfully. Synced {res.get('count')} diamonds.")
            else:
                print(f"[Inventory Auto-Sync] Notice: Sync returned status: {res.get('message')}")
        except Exception as e:
            print(f"[Inventory Auto-Sync] Error during periodic sync: {e}")

        # Sleep in small slices to allow clean thread shutdown
        elapsed = 0
        while elapsed < interval_seconds and capture_running:
            time.sleep(2)
            elapsed += 2

    print("[Inventory Auto-Sync] Service terminated.")

def background_detection_loop(camera_index=1, interval=5):
    """
    Indefinite background thread:
    - Captures frames from the camera
    - Every 5th frame, runs multi-code detection
    - Updates local detected_inventory dictionary
    """
    global latest_frame, frame_counter, detected_inventory

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[Vision Engine] Warning: Camera {camera_index} unavailable. Running synthetic loop.")
        cap = None

    print(f"[Vision Engine] Background indefinite capture started (interval={interval} frames).")

    while capture_running:
        frame = None
        if cap is not None:
            ret, captured = cap.read()
            if ret:
                frame = captured
            else:
                time.sleep(0.01)
                continue
        else:
            # Fallback synthetic frame if no physical camera connected
            synthetic = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(synthetic, "SYNTHETIC FEED - WAITING FOR CAMERA", (360, 360),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (120, 120, 120), 2)
            frame = synthetic
            time.sleep(0.033)

        with frame_lock:
            latest_frame = frame

        frame_counter += 1

        # Every 5th frame, perform detection and update local dictionary
        if frame_counter % interval == 0:
            try:
                detections = scanner.scan_frame(frame)
                now = time.time()
                formatted_now = time.strftime('%H:%M:%S', time.localtime(now))

                with inventory_lock:
                    # Update or add newly detected codes
                    for item in detections:
                        code = item['data']
                        if code not in detected_inventory:
                            detected_inventory[code] = {
                                'code': code,
                                'center': item['center'],
                                'points': item['points'],
                                'format': item['format'],
                                'first_seen': formatted_now,
                                'first_seen_ts': now,
                                'last_seen': formatted_now,
                                'last_seen_ts': now,
                                'left_ts': None,
                                'status': 'present'
                            }
                            print(f"[Vision Engine] Code Entered: {code} at {formatted_now}")
                            history_logger.log_event("ENTER", code, now)
                        else:
                            rec = detected_inventory[code]
                            # If code was previously marked left:
                            if rec.get('status') == 'left':
                                left_ts = rec.get('left_ts')
                                # 5-Second Debounce Glitch Filter:
                                # If the code reappears within 5 seconds of leaving, keep it in the same loop!
                                if left_ts and (now - left_ts <= 5.0):
                                    print(f"[Vision Engine] Code {code} reappeared within 5s ({round(now - left_ts, 1)}s) - resuming active session without splitting.")
                                    # Tell history_logger to discard the premature LEAVE event
                                    history_logger.undo_leave_event(code)
                                else:
                                    rec['first_seen'] = formatted_now
                                    rec['first_seen_ts'] = now
                                    print(f"[Vision Engine] Code Re-Entered: {code} at {formatted_now}")
                                    history_logger.log_event("ENTER", code, now)

                            # Update position, last seen timestamp, and reset left_ts
                            rec['center'] = item['center']
                            rec['points'] = item['points']
                            rec['last_seen'] = formatted_now
                            rec['last_seen_ts'] = now
                            rec['left_ts'] = None
                            rec['status'] = 'present'

                    # Mark items not seen in current frame as 'left' if absent for > 5.0s
                    for code, record in list(detected_inventory.items()):
                        if record['status'] == 'present' and (now - record['last_seen_ts'] > 5.0):
                            record['status'] = 'left'
                            record['left_ts'] = now
                            print(f"[Vision Engine] Code Left: {code} at {formatted_now}")
                            history_logger.log_event("LEAVE", code, now)

            except Exception as e:
                print(f"[Vision Engine] Error during scan_frame: {e}")

    if cap:
        cap.release()
    print("[Vision Engine] Background capture terminated.")

# ==============================================================================
# 2. AUTHENTICATION & ACCESS CONTROL
# ==============================================================================
@app.before_request
def require_login():
    # Allow public access only to login page and static assets
    if request.path == "/login" or request.path.startswith("/static/"):
        return None

    # Check if user session exists
    if not session.get("user"):
        # For API and stream requests, return 401 Unauthorized JSON
        if request.path.startswith("/api/") or request.path.startswith("/video/"):
            return jsonify({
                "status": "error",
                "message": "Authentication required. Please sign in.",
                "code": 401
            }), 401
        # For browser page views, redirect to login page
        next_target = request.full_path if request.query_string else request.path
        return redirect(url_for("login", next=next_target))

@app.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in, redirect directly to dashboard
    if session.get("user"):
        return redirect(url_for("index"))

    next_url = request.args.get("next") or request.form.get("next") or "/"
    # Security: Prevent open redirect vulnerability
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"

    error = None
    success = request.args.get("created") and "Account created successfully! Please sign in." or None
    username = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = auth_mgr.verify_user(username, password)
        if user:
            session.permanent = True
            session["user"] = user
            print(f"[Auth Guard] User '{user['username']}' logged in successfully.")
            return redirect(next_url)
        else:
            error = "Invalid username or password. Please try again."

    return render_template("login.html", error=error, success=success, username=username, next_url=next_url)

@app.route("/register", methods=["GET", "POST"])
def register():
    # Public self-registration is closed - redirect to login with notification
    return redirect(url_for("login"))

@app.route("/logout", methods=["GET", "POST"])
def logout():
    user = session.pop("user", None)
    if user:
        print(f"[Auth Guard] User '{user.get('username')}' logged out.")
    session.clear()
    return redirect(url_for("login"))

# ==============================================================================
# 3. SETTINGS & USER MANAGEMENT APIS
# ==============================================================================
@app.route("/api/auth/me", methods=["GET"])
def get_current_user():
    user = session.get("user")
    if not user:
        return jsonify({"status": "error", "message": "Not authenticated."}), 401
    return jsonify({"status": "success", "user": user})

@app.route("/api/auth/change-password", methods=["POST"])
def change_password():
    user = session.get("user")
    if not user:
        return jsonify({"status": "error", "message": "Authentication required."}), 401

    payload = request.get_json(silent=True) or {}
    current_pass = payload.get("current_password", "")
    new_pass = payload.get("new_password", "")

    if not current_pass or not new_pass:
        return jsonify({"status": "error", "message": "Current and new passwords are required."}), 400

    if len(new_pass) < 6:
        return jsonify({"status": "error", "message": "New password must be at least 6 characters."}), 400

    res = auth_mgr.change_password(user["username"], current_pass, new_pass)
    status_code = 200 if res.get("status") == "success" else 400
    return jsonify(res), status_code

@app.route("/api/admin/users", methods=["GET"])
def list_admin_users():
    user = session.get("user")
    if not user or user.get("role") != "admin":
        return jsonify({"status": "error", "message": "Administrator privileges required."}), 403

    users = auth_mgr.get_all_users()
    return jsonify({
        "status": "success",
        "users": users,
        "current_user": user["username"]
    })

@app.route("/api/admin/users", methods=["POST"])
def create_admin_user():
    user = session.get("user")
    if not user or user.get("role") != "admin":
        return jsonify({"status": "error", "message": "Administrator privileges required."}), 403

    payload = request.get_json(silent=True) or {}
    new_username = payload.get("username", "")
    new_password = payload.get("password", "")
    role = payload.get("role", "operator")

    res = auth_mgr.add_user(new_username, new_password, role=role)
    status_code = 200 if res.get("status") == "success" else 400
    return jsonify(res), status_code

@app.route("/api/admin/users/<username>", methods=["DELETE"])
def delete_admin_user(username):
    user = session.get("user")
    if not user or user.get("role") != "admin":
        return jsonify({"status": "error", "message": "Administrator privileges required."}), 403

    res = auth_mgr.delete_user(username, current_username=user["username"])
    status_code = 200 if res.get("status") == "success" else 400
    return jsonify(res), status_code

# ==============================================================================
# 3. FRONTEND SINGLE ROUTE & LIVE CAMERA FEED
# ==============================================================================
@app.route("/")
def index():
    return render_template("index.html")

def generate_camera_stream():
    """
    Downsamples the 4K live camera frame to 720p (1280x720) and streams MJPEG.
    Terminates cleanly when the client disconnects or closes the modal.
    """
    while capture_running:
        with frame_lock:
            frame_to_send = latest_frame.copy() if latest_frame is not None else None

        if frame_to_send is not None:
            # Resize 4K frame to 720p (1280 x 720) for minimal network load
            frame_720p = cv2.resize(frame_to_send, (1280, 720), interpolation=cv2.INTER_LINEAR)
            
            # Encode as JPEG with quality 70
            success, encoded_jpeg = cv2.imencode('.jpg', frame_720p, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if success:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + encoded_jpeg.tobytes() + b'\r\n')

        time.sleep(0.04)  # ~25 FPS

@app.route("/video/feed")
def video_feed():
    """Serves pure 720p live camera stream to frontend modal."""
    return Response(
        generate_camera_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/api/camera/snapshot", methods=["GET"])
def get_camera_snapshot():
    """
    Returns a single JPEG snapshot of the current camera frame for calibration.
    Includes headers for raw camera dimensions and preview dimensions.
    """
    with frame_lock:
        if latest_frame is None:
            return jsonify({"status": "error", "message": "No camera frame available"}), 503
        frame = latest_frame.copy()

    raw_h, raw_w = frame.shape[:2]
    # Resize to 1280x720 for fast network transfer
    preview = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_LINEAR)
    success, encoded_jpg = cv2.imencode('.jpg', preview, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not success:
        return jsonify({"status": "error", "message": "Snapshot encoding failed"}), 500

    resp = Response(encoded_jpg.tobytes(), mimetype="image/jpeg")
    resp.headers["Access-Control-Expose-Headers"] = "X-Raw-Width, X-Raw-Height, X-Preview-Width, X-Preview-Height"
    resp.headers["X-Raw-Width"] = str(raw_w)
    resp.headers["X-Raw-Height"] = str(raw_h)
    resp.headers["X-Preview-Width"] = "1280"
    resp.headers["X-Preview-Height"] = "720"
    return resp

# ==============================================================================
# 3. FEATURE ENDPOINTS
# ==============================================================================

# Feature 2: Camera-Projector Calibration
@app.route("/api/calibration/save", methods=["POST"])
def save_calibration():
    """Receives 4 camera-projector point pairs and computes homography."""
    data = request.get_json(silent=True) or {}
    cam_pts = data.get("camera_points", [])
    proj_pts = data.get("projector_points", [])

    if len(cam_pts) >= 4 and len(proj_pts) >= 4:
        c_coords = [[p['x'], p['y']] for p in cam_pts[:4]]
        p_coords = [[p['x'], p['y']] for p in proj_pts[:4]]
        h = calibration_mgr.calculate_homography(c_coords, p_coords)
        return jsonify({
            "status": "success",
            "message": "Calibration matrix saved successfully." if h is not None else "Homography computation failed.",
            "is_calibrated": h is not None
        })

    return jsonify({"status": "error", "message": "At least 4 point pairs required."}), 400

@app.route("/api/calibration/status", methods=["GET"])
def get_calibration_status():
    """Checks if calibration matrix is loaded."""
    is_calibrated = calibration_mgr.homography_matrix is not None
    return jsonify({
        "status": "success",
        "is_calibrated": is_calibrated
    })

# Feature 3 & 6: Search & Multi-Code Highlight Projector Mapping
@app.route("/api/projector/highlight", methods=["POST"])
def project_highlight():
    if calibration_mgr.homography_matrix is None:
        return jsonify({
            "status": "error",
            "message": "Projector not calibrated. Please run Calibration from the sidebar first."
        }), 400

    payload = request.get_json(silent=True) or {}
    print(f"[Projector Highlight API] Payload: {payload}")

    # Mode: 'append' (default to keep prior searches) or 'replace'
    mode = payload.get("mode", "append")
    # Color provided in payload (BGR order: [B, G, R]), default to Emerald Green (0, 255, 128)
    color = tuple(payload.get("color", [0, 255, 128]))

    codes_to_highlight = payload.get("codes", [])

    # If batches dictionary mapping code -> [B, G, R] is provided directly
    batches = payload.get("batches")

    with marked_codes_lock:
        if mode == "replace":
            marked_codes.clear()

        if batches and isinstance(batches, dict):
            for c, col in batches.items():
                marked_codes[str(c).strip()] = tuple(col)
        else:
            for c in codes_to_highlight:
                c_str = str(c).strip()
                if c_str:
                    marked_codes[c_str] = color

    return jsonify({
        "status": "success",
        "total_marked_codes": len(marked_codes)
    })

@app.route("/api/projector/clear", methods=["POST"])
def clear_projector_highlight():
    """Clears all currently highlighted codes from the projector feed."""
    with marked_codes_lock:
        marked_codes.clear()
    return jsonify({
        "status": "success",
        "message": "All projector highlights cleared."
    })

# Feature 4: Filter Query Endpoint
@app.route("/api/inventory/filter", methods=["POST"])
def filter_inventory():
    """
    Receives attribute filters (Shape, Carat, Color, Clarity, Cut, etc.),
    queries synced inventory to find matching stock IDs, and marks them
    for continuous projector highlight.
    """
    filters = request.get_json(silent=True) or {}
    print(f"[API Triggered] POST /api/inventory/filter with filters: {filters}")

    # Match against synced inventory database
    matching_ids = inventory_mgr.match_filters(filters)

    # Automatically set matching codes to be projected on the table (default Cyan (255, 200, 0))
    with marked_codes_lock:
        marked_codes.clear()
        for mid in matching_ids:
            marked_codes[str(mid).strip()] = (255, 200, 0)

    # Determine which of the matching stones are currently present on the surface
    with inventory_lock:
        present_matched = [
            code for code in matching_ids
            if code in detected_inventory and detected_inventory[code]['status'] == 'present'
        ]

    return jsonify({
        "status": "success",
        "matched_total_count": len(matching_ids),
        "present_on_table_count": len(present_matched),
        "matching_codes": matching_ids,
        "present_codes": present_matched
    })

# Feature 5: Inventory Sync
@app.route("/api/inventory/sync", methods=["POST"])
def sync_inventory():
    """
    Synchronizes on-hand diamonds from the DiamDash CRM API and updates local cache.
    """
    payload = request.get_json(silent=True) or {}
    token = payload.get("token")
    status = payload.get("status", "on_hand")
    if token:
        res = inventory_mgr.sync_from_crm(status=status, token=token)
    else:
        res = inventory_mgr.sync_from_crm(status=status)

    return jsonify(res)

@app.route("/api/inventory/status", methods=["GET"])
def get_inventory_status():
    """Returns metadata about the active inventory state."""
    return jsonify({
        "status": "success",
        "data": inventory_mgr.get_status_info()
    })

@app.route("/api/inventory/items", methods=["GET"])
def get_inventory_items():
    """Returns the full list of synced inventory diamonds."""
    items = inventory_mgr.get_all_items()
    return jsonify({
        "status": "success",
        "count": len(items),
        "items": items
    })

@app.route("/api/inventory/options", methods=["GET"])
def get_inventory_options():
    """Returns unique categorical filter options and carat ranges from synced inventory."""
    opts = inventory_mgr.get_filter_options()
    return jsonify({
        "status": "success",
        "options": opts
    })

# Sub-feature 2: Inventory vs Frame Reconciliation & Export Report
@app.route("/api/reports/reconcile", methods=["GET"])
def get_reconciliation_report():
    """
    Performs live reconciliation comparing physically present codes on the table
    against the synced DiamDash CRM inventory.
    Categorizes items into:
      1. Verified Items: Present in frame AND exists in CRM inventory
      2. Dispute Items: Present in frame BUT absent from CRM inventory (unregistered)
      3. Absent Items: Present in CRM inventory BUT absent from table frame
    """
    now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    crm_inventory = inventory_mgr.get_all_items()
    crm_index = {item["stock_id"]: item for item in crm_inventory}

    with inventory_lock:
        # Get all codes currently active and physically visible on the table
        present_records = [
            rec for rec in detected_inventory.values()
            if rec.get('status') == 'present'
        ]

    verified_items = []
    dispute_items = []
    present_stock_ids = set()

    for rec in present_records:
        stock_id = rec.get('code')
        present_stock_ids.add(stock_id)

        diamond_info = inventory_mgr.get_item(stock_id)
        if diamond_info:
            # Diamond is legitimately cataloged in CRM inventory
            verified_items.append({
                "stock_id": diamond_info.get("stock_id", stock_id),
                "shape": diamond_info.get("shape", "--"),
                "carat": diamond_info.get("ct") or diamond_info.get("carat", "--"),
                "color": diamond_info.get("color", "--"),
                "original_color": diamond_info.get("original_color"),
                "fancy_color": diamond_info.get("fancy_color"),
                "clarity": diamond_info.get("clarity", "--"),
                "cut": diamond_info.get("cut") or "--",
                "polish": diamond_info.get("polish", "--"),
                "symm": diamond_info.get("symm", "--"),
                "fluo": diamond_info.get("fluo", "--"),
                "lab": diamond_info.get("lab", "--"),
                "certificate_no": diamond_info.get("cert_number") or diamond_info.get("certificate_no", "--"),
                "measurements": diamond_info.get("measurements", "--"),
                "location": diamond_info.get("location", "--"),
                "first_seen": rec.get("first_seen", "--"),
                "last_seen": rec.get("last_seen", "--"),
                "status": "VERIFIED"
            })
        else:
            # Code found on surface has NO record in CRM inventory (dispute)
            center = rec.get("center", (0, 0))
            dispute_items.append({
                "stock_id": stock_id,
                "center": [round(center[0], 1), round(center[1], 1)],
                "first_seen": rec.get("first_seen", "--"),
                "last_seen": rec.get("last_seen", "--"),
                "format": rec.get("format", "DataMatrix"),
                "status": "DISPUTE",
                "reason": "Physically present on surface but absent from CRM inventory"
            })

    # Missing from view (present in on-hand inventory but absent from physical surface)
    missing_items = []
    for item in crm_inventory:
        sid = item["stock_id"]
        is_seen = any(
            (inventory_mgr.get_item(p) or {}).get("stock_id") == sid or p == sid
            for p in present_stock_ids
        )
        if not is_seen:
            missing_items.append({
                "stock_id": sid,
                "shape": item.get("shape", "--"),
                "carat": item.get("ct") or item.get("carat", "--"),
                "color": item.get("color", "--"),
                "original_color": item.get("original_color"),
                "fancy_color": item.get("fancy_color"),
                "clarity": item.get("clarity", "--"),
                "cut": item.get("cut") or "--",
                "polish": item.get("polish", "--"),
                "symm": item.get("symm", "--"),
                "fluo": item.get("fluo", "--"),
                "lab": item.get("lab", "--"),
                "certificate_no": item.get("cert_number") or item.get("certificate_no", "--"),
                "measurements": item.get("measurements", "--"),
                "location": item.get("location", "Store"),
                "status": "MISSING_FROM_VIEW"
            })

    return jsonify({
        "status": "success",
        "timestamp": now,
        "summary": {
            "inventory_total": len(crm_inventory),
            "frame_total": len(present_records),
            "verified_count": len(verified_items),
            "missing_count": len(missing_items),
            "dispute_count": len(dispute_items),
            "absent_count": len(missing_items)
        },
        "verified_items": verified_items,
        "missing_items": missing_items,
        "dispute_items": dispute_items,
        "absent_codes": [m["stock_id"] for m in missing_items]
    })

# ==============================================================================
# 5. AUDIT & SCAN HISTORY QUERY ENDPOINT
# ==============================================================================
@app.route("/api/history", methods=["GET"])
def get_history():
    """
    Query historical detection records across daily log files.
    Query parameters:
      - start_date: YYYY-MM-DD (defaults to today)
      - end_date: YYYY-MM-DD (defaults to today)
      - code: Optional specific Stock ID / Diamond Code
    Enforces max 62-day (~2 month) date window.
    """
    today_str = time.strftime("%Y-%m-%d")
    start_date = request.args.get("start_date", today_str).strip()
    end_date = request.args.get("end_date", today_str).strip()
    specific_code = request.args.get("code", "").strip() or None

    res = history_logger.query_history(start_date, end_date, specific_code=specific_code, max_days=62)
    if "error" in res:
        return jsonify({"status": "error", "message": res["error"]}), 400

    # Enrich with CRM metadata if present
    for s in res.get("sessions", []):
        code = s.get("code")
        info = inventory_mgr.get_item(code)
        if info:
            s["crm_status"] = "VERIFIED"
            s["shape"] = info.get("shape", "--")
            s["carat"] = info.get("carat", "--")
            s["color"] = info.get("color", "--")
            s["clarity"] = info.get("clarity", "--")
        else:
            s["crm_status"] = "DISPUTE"
            s["shape"] = "--"
            s["carat"] = "--"
            s["color"] = "--"
            s["clarity"] = "--"

    return jsonify(res)

def shutdown_system(signum=None, frame=None):
    """Immediate and complete shutdown handler for Ctrl+C and SIGTERM."""
    global capture_running
    if not capture_running:
        return
    capture_running = False
    print("\n[System Shutdown] Stopping background threads and releasing hardware resources...")

    try:
        scanner.close()
    except Exception:
        pass

    try:
        cv2.destroyAllWindows()
    except Exception:
        pass

    print("[System Shutdown] All threads and hardware handles closed cleanly. Exiting.")
    # Use os._exit(0) to bypass Python atexit join hangs with multiprocessing / threads
    os._exit(0)

# Register OS signal handlers for graceful Ctrl+C (SIGINT) and kill (SIGTERM)
signal.signal(signal.SIGINT, shutdown_system)
signal.signal(signal.SIGTERM, shutdown_system)

if __name__ == "__main__":
    # 1. Start camera detection thread
    detection_thread = threading.Thread(target=background_detection_loop, args=(0, 5), daemon=True)
    detection_thread.start()

    # 2. Start continuous 1080p projector display thread (fullscreen on 2nd monitor)
    projector_thread = threading.Thread(target=projector_display_loop, daemon=True)
    projector_thread.start()

    # 3. Start automatic recurring inventory synchronization thread (every 15 minutes)
    sync_thread = threading.Thread(target=inventory_auto_sync_loop, args=(900,), daemon=True)
    sync_thread.start()

    port = int(os.environ.get("PORT", 5000))
    print(f"\n💎 LUXE-TRACE Web Server started at http://localhost:{port}\n")
    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    finally:
        shutdown_system()
