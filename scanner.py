import cv2
import numpy as np
import zxingcpp
from concurrent.futures import ProcessPoolExecutor
import time

def decode_worker(crop_info):
    """
    Worker function to decode a single barcode crop.
    crop_info: (image_data, offset_x, offset_y)
    """
    image, ox, oy = crop_info
    try:
        # zxing-cpp works best with grayscale for DataMatrix
        results = zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.DataMatrix)
        decoded_items = []
        for res in results:
            pos = res.position
            global_pos = []
            for p in [pos.top_left, pos.top_right, pos.bottom_right, pos.bottom_left]:
                global_pos.append((p.x + ox, p.y + oy))
            
            cx = sum(p[0] for p in global_pos) / 4
            cy = sum(p[1] for p in global_pos) / 4
            
            decoded_items.append({
                'data': res.text,
                'center': (cx, cy),
                'points': global_pos
            })
        return decoded_items
    except Exception:
        return []

class Scanner:
    def __init__(self, num_workers=4):
        self.num_workers = num_workers
        self.inventory = {}  # data -> {center, points}
        self.last_frame = None

    def detect_blobs(self, frame):
        """
        Stage 1: Find candidate regions for DataMatrix codes.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # We try two thresholding methods: 
        # 1. Standard Global (Otsu) - good for high contrast
        # 2. Adaptive - good for uneven lighting
        _, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                      cv2.THRESH_BINARY, 15, 2)
        
        # Also try inverted for white-on-black vs black-on-white
        thresh3 = cv2.bitwise_not(thresh1)
        
        candidates = []
        h_img, w_img = frame.shape[:2]
        
        for t in [thresh1, thresh2, thresh3]:
            contours, _ = cv2.findContours(t, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                if 20 < w < 200 and 20 < h < 200:
                    # Pad Quiet Zone
                    pad = 10
                    x1, y1 = max(0, x-pad), max(0, y-pad)
                    x2, y2 = min(w_img, x+w+pad), min(h_img, y+h+pad)
                    
                    crop = gray[y1:y2, x1:x2]
                    # Avoid duplicates by checking overlap? 
                    # For simplicity, just add them. zxingcpp is fast enough.
                    candidates.append((crop, x1, y1))
                    
        return candidates

    def scan_frame(self, frame):
        start_time = time.time()
        candidates = self.detect_blobs(frame)
        
        all_results = []
        if candidates:
            with ProcessPoolExecutor(max_workers=self.num_workers) as executor:
                results = list(executor.map(decode_worker, candidates))
                for res_list in results:
                    all_results.extend(res_list)

        new_inventory = {}
        for item in all_results:
            new_inventory[item['data']] = {
                'center': item['center'],
                'points': item['points']
            }
        
        self.inventory = new_inventory
        self.last_frame = frame.copy()
        
        print(f"Scanned {len(new_inventory)} unique codes in {time.time() - start_time:.3f}s")
        return self.inventory

    def get_code_position(self, code_data):
        return self.inventory.get(code_data)

    def detect_motion(self, current_frame, threshold=50000):
        if self.last_frame is None: return True
        diff = cv2.absdiff(cv2.cvtColor(self.last_frame, cv2.COLOR_BGR2GRAY), 
                          cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY))
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        return np.sum(thresh) > threshold
