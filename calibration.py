import cv2
import numpy as np
import json
import os

class CalibrationManager:
    def __init__(self, config_path='./calibration.json'):
        self.config_path = config_path
        self.homography_matrix = None
        self.load_calibration()

    def calculate_homography(self, camera_pts, projector_pts):
        """
        camera_pts: List of [x, y] coordinates from the camera feed
        projector_pts: List of [x, y] coordinates from the physical projector screen
        """
        if len(camera_pts) < 4 or len(projector_pts) < 4:
            print("[Calibration] Error: At least 4 point pairs are required for homography calculation.")
            return None

        src_pts = np.array(camera_pts, dtype=np.float32)
        dst_pts = np.array(projector_pts, dtype=np.float32)
        
        # Calculate Homography Matrix
        h, status = cv2.findHomography(src_pts, dst_pts)
        if h is None:
            print("[Calibration] Error: Homography calculation failed.")
            return None

        self.homography_matrix = h
        print(f"[Calibration] Saved homography matrix to {self.config_path}:\n{self.homography_matrix}")
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.homography_matrix.tolist(), f, indent=2)
        except Exception as e:
            print(f"[Calibration] Exception saving calibration JSON: {e}")

        return h

    def map_point(self, x, y):
        """
        Maps a camera coordinate (x, y) to a physical projector coordinate.
        """
        if self.homography_matrix is None:
            return None
            
        point = np.array([[[float(x), float(y)]]], dtype=np.float32)
        try:
            mapped_point = cv2.perspectiveTransform(point, self.homography_matrix)
            res = mapped_point[0][0].tolist()
            return [round(res[0], 2), round(res[1], 2)]
        except Exception as e:
            print(f"[Calibration] Error transforming point ({x}, {y}): {e}")
            return None

    def map_polygon(self, points):
        """
        Maps a list of camera coordinates [[x1, y1], [x2, y2], ...] to projector coordinates.
        Returns a numpy array of shape (N, 2) with integer coordinates for cv2 drawing, or None.
        """
        if self.homography_matrix is None or not points:
            return None

        try:
            pts = np.array([points], dtype=np.float32)
            mapped = cv2.perspectiveTransform(pts, self.homography_matrix)
            return mapped[0].astype(np.int32)
        except Exception as e:
            print(f"[Calibration] Error transforming polygon points: {e}")
            return None

    def load_calibration(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    self.homography_matrix = np.array(data, dtype=np.float64)
                    print(f"[Calibration] Loaded calibration from {self.config_path}")
            except Exception as e:
                print(f"[Calibration] Failed loading calibration file {self.config_path}: {e}")
                self.homography_matrix = None
        else:
            print("[Calibration] No existing calibration file found. Run calibration from Web UI.")

