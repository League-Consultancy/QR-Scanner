import cv2
import time
from scanner import Scanner
import numpy as np
from calibration import CalibrationManager
from threading import Thread

# Initialize components
scanner = Scanner(num_workers=8)
calibration = CalibrationManager()


PROJECTOR_MONITOR_INDEX = 1 
window_name = "Projector_Output"
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.moveWindow(window_name, 1920 * PROJECTOR_MONITOR_INDEX, 0)
cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)


camera = cv2.VideoCapture(4)  # Use 0 for default camera
camera.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)

# State
current_frame = None
is_scanning = False
last_scan_time = 0
current_search_query = None

# Generate scan
def perform_scan(frame):
    global is_scanning, last_scan_time
    is_scanning = True
    inventory = scanner.scan_frame(frame)
    is_scanning = False
    last_scan_time = time.time()
    # Notify admin that scan is done
    print('scan_complete', {'count': len(inventory)})

def capture_thread():
    while True:
        success, frame = camera.read()
        if success:
            current_frame = frame
            if not is_scanning and (time.time() - last_scan_time > 5):
                if scanner.detect_motion(frame):
                    print("Motion detected, triggering rescan...")
                    perform_scan(frame)

            frame_resized = cv2.resize(current_frame, (1920, 1080))
            black_frame = np.zeros((3840,2160,3),dtype=np.uint8)
            h_orig, w_orig = current_frame.shape[:2]
            scale_x = 1920.0 / w_orig if w_orig > 0 else 1.0
            scale_y = 1080.0 / h_orig if h_orig > 0 else 1.0
            inventory_copy = dict(scanner.inventory)
            for code_data, info in inventory_copy.items():
                points = info.get('points', [])
                if len(points) == 4:
                    pts = np.array([[int(float(p[0]) * scale_x), int(float(p[1]) * scale_y)] for p in points], dtype=np.int32)
                    if current_search_query and str(code_data) == str(current_search_query):
                        color = (68, 68, 255)
                        thickness = 3
                    else:
                        color = (0,255,0)
                        thickness = 2
                    cv2.polylines(black_frame, [pts], isClosed=True, color=color, thickness=thickness)

            if calibration.homography_matrix is not None:
                warped = cv2.warpPerspective(black_frame, calibration.homography_matrix, (1920, 1080))
            else:
                # If not calibrated, display a blank black frame (or a grid/message)
                warped = np.zeros((1920, 1080, 3), dtype=np.uint8)
                cv2.putText(warped, "Not Calibrated", (1600, 1100), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255), 3)

            cv2.imshow(window_name, warped)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    camera.release()
    cv2.destroyAllWindows()

from flask import Flask, request, render_template_string, jsonify
import logging

# Disable Flask request logging to keep the console output clean
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>ScanMatrix Controller</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: linear-gradient(135deg, #0b0f19 0%, #111827 100%);
            --panel: rgba(17, 24, 39, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --text: #f3f4f6;
            --accent: #6366f1;
            --accent-hover: #4f46e5;
            --accent-glow: rgba(99, 102, 241, 0.4);
        }
        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg);
            color: var(--text);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
        }
        .container {
            background: var(--panel);
            backdrop-filter: blur(20px);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 40px;
            width: 450px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
        }
        h2 {
            margin-bottom: 24px;
            font-weight: 700;
            background: linear-gradient(135deg, #ffffff, #9ca3af);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .search-box {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        input {
            flex: 1;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--card-border);
            border-radius: 10px;
            padding: 14px 18px;
            color: var(--text);
            font-family: inherit;
            outline: none;
            font-size: 16px;
            transition: all 0.3s;
        }
        input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 8px var(--accent-glow);
        }
        button {
            font-family: inherit;
            font-size: 15px;
            font-weight: 600;
            border-radius: 10px;
            padding: 14px 24px;
            cursor: pointer;
            transition: all 0.3s;
            outline: none;
        }
        .btn-search {
            background: linear-gradient(135deg, var(--accent), var(--accent-hover));
            border: none;
            color: white;
            box-shadow: 0 4px 12px var(--accent-glow);
        }
        .btn-search:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px var(--accent-glow);
        }
        .btn-clear {
            background: transparent;
            border: 1px solid var(--card-border);
            color: #ef4444;
        }
        .btn-clear:hover {
            border-color: #ef4444;
            background: rgba(239, 68, 68, 0.05);
        }
        .status {
            font-size: 14px;
            color: #9ca3af;
            margin-top: 10px;
        }
        .highlighted {
            color: #f97316;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>Matrix Finder Controller</h2>
        <div class="search-box">
            <input type="text" id="query" placeholder="Enter Serial # to search..." onkeydown="if(event.key === 'Enter') search()">
            <button class="btn-search" onclick="search()">Search</button>
        </div>
        <button class="btn-clear" style="width: 100%;" onclick="clearSearch()">Clear Highlight</button>
        <div class="status" id="status">No active search</div>
    </div>
    <script>
        function search() {
            const q = document.getElementById('query').value.trim();
            if (!q) return;
            fetch('/search?q=' + encodeURIComponent(q))
            .then(res => res.json())
            .then(data => {
                document.getElementById('status').innerHTML = 'Highlighting: <span class="highlighted">' + q + '</span>';
            });
        }
        function clearSearch() {
            document.getElementById('query').value = '';
            fetch('/search?q=')
            .then(res => res.json())
            .then(data => {
                document.getElementById('status').innerText = 'No active search';
            });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/search')
def search():
    global current_search_query
    q = request.args.get('q', '').strip()
    current_search_query = q if q else None
    return jsonify(success=True, query=current_search_query)

def start_server():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# Start web control server in a background thread
web_thread = Thread(target=start_server, daemon=True)
web_thread.start()

print("ScanMatrix GUI Controller active at http://localhost:5000")

# Run the camera capture and projector GUI loop on the main thread
capture_thread()


