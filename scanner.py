import cv2
import numpy as np
import zxingcpp
from concurrent.futures import ThreadPoolExecutor
import time

def decode_worker(crop_info):
    """
    Worker function to decode a single barcode crop.
    crop_info: (image_data, offset_x, offset_y)
    """
    image, ox, oy = crop_info
    try:
        results = zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.DataMatrix)
        decoded_items = []
        for res in results:
            pos = res.position
            global_pos = []
            for p in [pos.top_left, pos.top_right, pos.bottom_right, pos.bottom_left]:
                global_pos.append((float(p.x + ox), float(p.y + oy)))
            
            cx = sum(p[0] for p in global_pos) / 4.0
            cy = sum(p[1] for p in global_pos) / 4.0
            
            decoded_items.append({
                'data': res.text,
                'center': (cx, cy),
                'points': global_pos,
                'format': str(res.format)
            })
        return decoded_items
    except Exception:
        return []

class Scanner:
    """
    Pure vision detection engine.
    Receives raw frames, extracts candidate ROIs, and decodes Data Matrix codes.
    Does not manage camera hardware or presence lifecycle.
    """
    def __init__(self, num_workers=4):
        self.num_workers = num_workers
        self.executor = ThreadPoolExecutor(max_workers=self.num_workers)

    def detect_blobs(self, frame):
        """
        Stage 1: Find candidate regions for DataMatrix codes.
        Optimized with aspect ratio, area filtering, and ROI deduplication.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        h_img, w_img = gray.shape[:2]
        
        # Dual Otsu thresholding
        _, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh2 = cv2.bitwise_not(thresh1)
        
        candidates = []
        seen_rois = set()
        
        for t in [thresh1, thresh2]:
            contours, _ = cv2.findContours(t, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                
                # Filter out obvious non-barcode contours (area & square aspect ratio filter)
                if 18 < w < 400 and 18 < h < 400:
                    aspect_ratio = float(w) / h
                    if 0.5 <= aspect_ratio <= 2.0:
                        # Pad Quiet Zone
                        pad = 12
                        x1, y1 = max(0, x - pad), max(0, y - pad)
                        x2, y2 = min(w_img, x + w + pad), min(h_img, y + h + pad)
                        
                        # Deduplicate overlapping ROIs using a grid hash key
                        grid_key = (x1 // 15, y1 // 15, (x2 - x1) // 15, (y2 - y1) // 15)
                        if grid_key not in seen_rois:
                            seen_rois.add(grid_key)
                            crop = gray[y1:y2, x1:x2]
                            candidates.append((crop, x1, y1))
                            
        return candidates

    def scan_frame(self, frame):
        """
        Performs detection on a single frame and returns list of decoded item dictionaries.
        """
        candidates = self.detect_blobs(frame)
        all_results = []
        if candidates and self.executor:
            try:
                results = list(self.executor.map(decode_worker, candidates))
                for res_list in results:
                    all_results.extend(res_list)
            except Exception:
                pass

        return all_results

    def close(self):
        """Cleanly terminates worker threads without hanging or socket holding."""
        if self.executor:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            self.executor = None