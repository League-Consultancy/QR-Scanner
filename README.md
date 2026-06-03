# ScanMatrix: QR & DataMatrix Projection Mapping Scanner

ScanMatrix is a tool that detects barcodes using a camera and projects highlight boxes directly onto the physical objects in real-time.

---

## 1. Setup
Run the setup script to install `uv` (if needed), Python 3.12.13, and all dependencies:
```bash
./setup.sh
```

---

## 2. Run the App
Start the system by running the launch script:
```bash
./run.sh
```
* This opens the **fullscreen projector output** on your secondary screen.
* This starts the **Web Control Panel** at: `http://localhost:5000` (or `http://<your-ip-address>:5000` from any tablet/phone on the network).

---

## 3. How to Use

### Step A: Calibrate
1. Open the Web Control Panel.
2. Click **Start Calibration** (this displays green crosses on the projector screen).
3. On the web page video preview, click the center of the projected crosses in order:
   * **Top-Left**
   * **Top-Right**
   * **Bottom-Right**
   * **Bottom-Left**

### Step B: Search and Highlight
1. Place barcodes under the camera. The scanner automatically indexes them every 5 seconds.
2. In the Search bar on the web page, type the barcode value and click **Find**.
3. The projector will instantly highlight the physical item on the board.
4. Click **Clear** to remove the highlight.
