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
        projector_pts: List of [x, y] coordinates from the projector screen
        """
        src_pts = np.array(camera_pts, dtype=np.float32)
        dst_pts = np.array(projector_pts, dtype=np.float32)
        
        # Calculate Homography Matrix
        h, status = cv2.findHomography(src_pts, dst_pts)
        self.homography_matrix = h
        print("saved calibration data at",self.homography_matrix.tolist())
        with open(self.config_path, 'w') as f:
            json.dump(self.homography_matrix.tolist(), f)
        return h

    def map_point(self, x, y):
        """
        Maps a camera coordinate (x, y) to a projector coordinate.
        """
        if self.homography_matrix is None:
            return None
            
        point = np.array([[[x, y]]], dtype=np.float32)
        mapped_point = cv2.perspectiveTransform(point, self.homography_matrix)
        return mapped_point[0][0].tolist()

    def load_calibration(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                self.homography_matrix = np.array(json.load(f))
                print(f"Loaded calibration from {self.config_path}")
        else:
            print("No calibration found.")
