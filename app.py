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
scanner = Scanner(num_workers=8)
calibration = CalibrationManager()
camera = cv2.VideoCapture(4)  # Use 0 for default camera
camera.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)

# State
current_frame = None
is_scanning = False
last_scan_time = 0
current_search_query = None

def camera_loop():
    global current_frame, is_scanning, last_scan_time
    while True:
        success, frame = camera.read()
        if success:
            current_frame = frame
            
            # Auto-rescan if motion detected (and not currently scanning)
            if not is_scanning and (time.time() - last_scan_time > 5):
                if scanner.detect_motion(frame):
                    print("Motion detected, triggering rescan...")
                    threading.Thread(target=perform_scan, args=(frame.copy(),)).start()
        
        time.sleep(0.03)  # ~30 FPS

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

@app.route('/projector')
def projector():
    return render_template('projector.html')

def gen_projector_frames():
    global current_search_query
    while True:
        if current_frame is not None:
            # Resize camera frame to 1920x1080 (the coordinate space used for homography)
            frame_resized = cv2.resize(current_frame, (1920, 1080))
            
            # Draw marked matrix barcodes from scanner inventory scaled to 1920x1080
            h_orig, w_orig = current_frame.shape[:2]
            scale_x = 1920.0 / w_orig if w_orig > 0 else 1.0
            scale_y = 1080.0 / h_orig if h_orig > 0 else 1.0
            
            try:
                # Thread-safe copy of inventory
                inventory_copy = dict(scanner.inventory)
                for code_data, info in inventory_copy.items():
                    points = info.get('points', [])
                    if len(points) == 4:
                        pts = np.array([[int(p[0] * scale_x), int(p[1] * scale_y)] for p in points], dtype=np.int32)
                        
                        if current_search_query and str(code_data) == str(current_search_query):
                            color = (68, 68, 255)
                            thickness = 3
                        else:
                            color = (136, 255, 0)
                            thickness = 2
                            
                        # Draw bounding polygon
                        cv2.polylines(frame_resized, [pts], isClosed=True, color=color, thickness=thickness)
            except Exception as e:
                print(f"Error drawing projector overlay: {e}")

            # Warp the frame using the homography matrix
            if calibration.homography_matrix is not None:
                warped = cv2.warpPerspective(frame_resized, calibration.homography_matrix, (1920, 1080))
            else:
                # If not calibrated, display a blank black frame (or a grid/message)
                warped = np.zeros((1080, 1920, 3), dtype=np.uint8)
                cv2.putText(warped, "Not Calibrated", (800, 540), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)

            ret, buffer = cv2.imencode('.jpg', warped)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
        time.sleep(0.05)

@app.route('/projector_feed')
def projector_feed():
    return Response(gen_projector_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

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

            ret, buffer = cv2.imencode('.jpg',  preview)
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

@socketio.on('connect', namespace='/projector')
def projector_connect():
    print('Projector connected')

@socketio.on('calibrate', namespace='/admin')
def handle_calibration(data):
    # data: {'camera_pts': [[x,y], ...], 'projector_pts': [[x,y], ...]}
    print("Received calibration data")
    calibration.calculate_homography(data['camera_pts'], data['projector_pts'])
    socketio.emit('clear', {}, namespace='/projector')
    emit('status', {'msg': 'Calibration saved'}, namespace='/admin')

@socketio.on('request_calibration_markers', namespace='/admin')
def handle_cal_markers():
    print("Projecting calibration markers")
    socketio.emit('show_calibration', {}, namespace='/projector')

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
            socketio.emit('highlight', {'x': proj_pos[0], 'y': proj_pos[1]}, namespace='/projector')
            emit('search_result', {'found': True, 'pos': proj_pos}, namespace='/admin')
        else:
            emit('search_result', {'found': False, 'msg': 'Calibration missing'}, namespace='/admin')
    else:
        emit('search_result', {'found': False, 'msg': 'Code not found'}, namespace='/admin')

@socketio.on('clear_highlight', namespace='/admin')
def handle_clear():
    global current_search_query
    current_search_query = None
    socketio.emit('clear', {}, namespace='/projector')

if __name__ == '__main__':
    # Start camera thread
    threading.Thread(target=camera_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
