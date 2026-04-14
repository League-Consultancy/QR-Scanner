from flask import Flask, render_template, Response, request
from flask_socketio import SocketIO, emit
import cv2
import threading
import time
from scanner import Scanner
from calibration import CalibrationManager

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Initialize components
scanner = Scanner(num_workers=4)
calibration = CalibrationManager()
camera = cv2.VideoCapture(0)  # Use 0 for default camera
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

# State
current_frame = None
is_scanning = False
last_scan_time = 0

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

def gen_frames():
    while True:
        if current_frame is not None:
            # We resize for preview to save bandwidth
            preview = cv2.resize(current_frame, (960, 540))
            ret, buffer = cv2.imencode('.jpg', preview)
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
    emit('status', {'msg': 'Calibration saved'}, namespace='/admin')

@socketio.on('request_calibration_markers', namespace='/admin')
def handle_cal_markers():
    print("Projecting calibration markers")
    socketio.emit('show_calibration', {}, namespace='/projector')

@socketio.on('search', namespace='/admin')
def handle_search(data):
    # data: {'query': 'CODE123'}
    query = data.get('query')
    pos = scanner.get_code_position(query)
    
    if pos:
        # Map camera coordinates to projector coordinates
        cx, cy = pos['center']
        proj_pos = calibration.map_point(cx, cy)
        
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
    socketio.emit('clear', {}, namespace='/projector')

if __name__ == '__main__':
    # Start camera thread
    threading.Thread(target=camera_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
