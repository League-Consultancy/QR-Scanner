from flask import Flask, render_template, Response, request
from flask_socketio import SocketIO, emit
import cv2
import numpy as np
import threading
import time
from scanner import Scanner
from calibration import CalibrationManager

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize components
scanner = Scanner(num_workers=2)
calibration = CalibrationManager()
camera = cv2.VideoCapture(1)  # Use 0 for default camera
# camera.set(cv2.CAP_PROP_FPS,2)
camera.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)

# State
current_frame = None
is_scanning = False
last_scan_time = 0
current_search_query = None
show_calibration_markers = False

def camera_loop():
    global current_frame
    while True:
        success, frame = camera.read()
        if success:
            current_frame = frame
        # Yield briefly so the CPU isn't pegged, but fast enough to prevent OpenCV queue lag
        time.sleep(0.01)

def processing_loop():
    global is_scanning, last_scan_time
    while True:
        frame_to_process = current_frame
        if frame_to_process is not None and not is_scanning:
            if time.time() - last_scan_time > 5:
                print("Running scheduled 5-second scan...")
                threading.Thread(target=perform_scan, args=(frame_to_process.copy(),)).start()
        time.sleep(1.0)

def perform_scan(frame):
    global is_scanning, last_scan_time
    is_scanning = True
    scanner.scan_frame(frame)
    is_scanning = False
    last_scan_time = time.time()
    # Notify admin that scan is done
    socketio.emit('scan_complete', {'count': len(scanner.inventory)}, namespace='/admin')

@app.route('/')
def admin():
    return render_template('admin.html')

def gen_frames():
    global current_search_query
    while True:
        if current_frame is not None:
            # We resize for preview to save bandwidth
            preview = cv2.resize(current_frame, (960, 540))
            
            # Draw marked matrix barcodes from scanner inventory
            h_orig, w_orig = current_frame.shape[:2]
            h_prev, w_prev = preview.shape[:2]
            
            scale_x = w_prev / w_orig if w_orig > 0 else 1.0
            scale_y = h_prev / h_orig if h_orig > 0 else 1.0
            
            try:
                # Thread-safe copy of inventory
                inventory_copy = dict(scanner.inventory)
                for code_data, info in inventory_copy.items():
                    points = info.get('points', [])
                    if len(points) == 4:
                        # Scale coordinates to preview size
                        pts = np.array([[int(p[0] * scale_x), int(p[1] * scale_y)] for p in points], dtype=np.int32)
                        
                        # Use Red/Orange for the currently searched code, Green/Accent for others
                        # BGR: Green-Cyan (#00ff88) is (136, 255, 0)
                        # BGR: Red-Orange (#ff4444) is (68, 68, 255)
                        if current_search_query and str(code_data) == str(current_search_query):
                            color = (68, 68, 255)
                            thickness = 3
                        else:
                            color = (136, 255, 0)
                            thickness = 2
                            
                        # Draw bounding polygon
                        cv2.polylines(preview, [pts], isClosed=True, color=color, thickness=thickness)
                        
                        # Draw text
                        # cv2.putText(preview, text_str, (text_x, text_y), font, font_scale, color, text_thickness, cv2.LINE_AA)
            except Exception as e:
                print(f"Error drawing overlay: {e}")

            ret, buffer = cv2.imencode('.jpg', preview, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# SocketIO Events
@socketio.on('connect', namespace='/admin')
def admin_connect():
    print('Admin connected')

@socketio.on('calibrate', namespace='/admin')
def handle_calibration(data):
    global show_calibration_markers
    # data: {'camera_pts': [[x,y], ...], 'projector_pts': [[x,y], ...]}
    print("Received calibration data")
    calibration.calculate_homography(data['camera_pts'], data['projector_pts'])
    show_calibration_markers = False
    emit('status', {'msg': 'Calibration saved'}, namespace='/admin')

@socketio.on('request_calibration_markers', namespace='/admin')
def handle_cal_markers():
    global show_calibration_markers
    print("Projecting calibration markers")
    show_calibration_markers = True

@socketio.on('search', namespace='/admin')
def handle_search(data):
    global current_search_query
    # data: {'query': 'CODE123'}
    query = data.get('query')
    current_search_query = query
    pos = scanner.get_code_position(query)
    
    if pos:
        # Map camera coordinates to projector coordinates
        cx, cy = pos['center']
        h_orig, w_orig = current_frame.shape[:2] if current_frame is not None else (2160, 3840)
        cx_cal = cx * (1920.0 / w_orig)
        cy_cal = cy * (1080.0 / h_orig)
        proj_pos = calibration.map_point(cx_cal, cy_cal)
        
        if proj_pos:
            print(f"Highlighting {query} at {proj_pos}")
            emit('search_result', {'found': True, 'pos': proj_pos}, namespace='/admin')
        else:
            emit('search_result', {'found': False, 'msg': 'Calibration missing'}, namespace='/admin')
    else:
        emit('search_result', {'found': False, 'msg': 'Code not found'}, namespace='/admin')

@socketio.on('clear_highlight', namespace='/admin')
def handle_clear():
    global current_search_query, show_calibration_markers
    current_search_query = None
    show_calibration_markers = False

def main_gui_loop():
    global current_frame, current_search_query, show_calibration_markers
    
    PROJECTOR_MONITOR_INDEX = 1 
    window_name = "Projector_Output"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(window_name, 1920 * PROJECTOR_MONITOR_INDEX, 0)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    
    while True:
        # Create a black frame for projection (1920x1080 space)
        black_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        if show_calibration_markers:
            # Draw 4 calibration crosses (offset by 20 pixels inside corners)
            # Top-Left (20, 20), Top-Right (1900, 20), Bottom-Right (1900, 1060), Bottom-Left (20, 1060)
            cross_color = (0, 255, 0) # Green BGR
            # Top-Left
            cv2.line(black_frame, (0, 20), (40, 20), cross_color, 2)
            cv2.line(black_frame, (20, 0), (20, 40), cross_color, 2)
            # Top-Right
            cv2.line(black_frame, (1880, 20), (1920, 20), cross_color, 2)
            cv2.line(black_frame, (1900, 0), (1900, 40), cross_color, 2)
            # Bottom-Right (Center at 1900, 1060)
            cv2.line(black_frame, (1880, 1060), (1920, 1060), cross_color, 2)
            cv2.line(black_frame, (1900, 1040), (1900, 1080), cross_color, 2)
            # Bottom-Left (Center at 20, 1060)
            cv2.line(black_frame, (0, 1060), (40, 1060), cross_color, 2)
            cv2.line(black_frame, (20, 1040), (20, 1080), cross_color, 2)
            
            # Calibration crosses are drawn raw (no warp)
            cv2.imshow(window_name, black_frame)
        else:
            # Draw scanned outlines from inventory (in camera coordinates)
            if current_frame is not None:
                h_orig, w_orig = current_frame.shape[:2]
                scale_x = 1920.0 / w_orig if w_orig > 0 else 1.0
                scale_y = 1080.0 / h_orig if h_orig > 0 else 1.0
                
                try:
                    inventory_copy = dict(scanner.inventory)
                    for code_data, info in inventory_copy.items():
                        points = info.get('points', [])
                        if len(points) == 4:
                            pts = np.array([[int(p[0] * scale_x), int(p[1] * scale_y)] for p in points], dtype=np.int32)
                            
                            if current_search_query and str(code_data) == str(current_search_query):
                                color = (68, 68, 255) # Red-orange
                                thickness = 4
                                
                                # Draw target circle indicator
                                cx, cy = info.get('center', (0, 0))
                                cx_scaled = int(cx * scale_x)
                                cy_scaled = int(cy * scale_y)
                                cv2.circle(black_frame, (cx_scaled, cy_scaled), 40, (68, 68, 255), 3)
                            else:
                                color = (136, 255, 0) # Green-cyan
                                thickness = 2
                                
                            cv2.polylines(black_frame, [pts], isClosed=True, color=color, thickness=thickness)
                except Exception as e:
                    print(f"Error drawing on black_frame: {e}")
            
            # Warp perspective using the homography matrix
            if calibration.homography_matrix is not None:
                warped = cv2.warpPerspective(black_frame, calibration.homography_matrix, (1920, 1080))
            else:
                warped = np.zeros((1080, 1920, 3), dtype=np.uint8)
                cv2.putText(warped, "Not Calibrated", (800, 540), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
                
            cv2.imshow(window_name, warped)
            
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        time.sleep(0.03)

if __name__ == '__main__':
    # Start background threads for camera and processing
    threading.Thread(target=camera_loop, daemon=True).start()
    threading.Thread(target=processing_loop, daemon=True).start()
    
    # Start Flask-SocketIO in a background thread
    threading.Thread(
        target=lambda: socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False),
        daemon=True
    ).start()
    
    print("ScanMatrix GUI Controller active at http://localhost:5000")
    
    # Run the native projector GUI loop on the main thread
    main_gui_loop()
