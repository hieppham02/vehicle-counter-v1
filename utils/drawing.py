import cv2
import numpy as np
from typing import Tuple, List, Dict
from core.config import LineConfig

# Standard colors
COLORS = {
    "red": (0, 0, 255),
    "blue": (255, 0, 0),
    "green": (0, 255, 0),
    "yellow": (0, 255, 255),
    "white": (255, 255, 255),
    "black": (0, 0, 0)
}

CLASS_VI = {
    "car": "O to",
    "bus": "Xe buyt",
    "truck": "Xe tai",
    "motorbike": "Xe may"
}

def draw_boxes(frame: np.ndarray, tracks: List[Dict]) -> np.ndarray:
    """
    Draw bounding boxes, IDs, and labels on the frame.
    tracks: List of dicts with keys 'bbox', 'track_id', 'class_name', 'confidence'
    """
    for track in tracks:
        x1, y1, x2, y2 = map(int, track['bbox'])
        track_id = track.get('track_id', -1)
        cls_name = track.get('class_name', 'Unknown')
        
        # Translate to Vietnamese (unaccented for cv2.putText compatibility)
        cls_name_vi = CLASS_VI.get(cls_name, cls_name)
        
        # Color based on class (simple hash)
        color_idx = hash(cls_name) % 255
        color = (color_idx, 255 - color_idx, (color_idx * 2) % 255)
        
        # Draw box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Draw label
        label = f"{cls_name_vi} #{track_id}"
        font_scale = 0.5
        thickness = 1
        (label_width, label_height), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        
        # Background for text
        cv2.rectangle(frame, (x1, y1 - label_height - 5), (x1 + label_width, y1), color, -1)
        cv2.putText(frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, font_scale, COLORS["white"], thickness)
        
        # Draw centroid
        cx, cy = int((x1+x2)/2), int((y1+y2)/2)
        cv2.circle(frame, (cx, cy), 4, COLORS["green"], -1)
        
    return frame

def draw_counting_lines(frame: np.ndarray, lines: List[LineConfig]) -> np.ndarray:
    """Draw counting lines with their names."""
    for line in lines:
        cv2.line(frame, line.pt1, line.pt2, line.color, 2)
        cv2.putText(frame, line.name, (line.pt1[0], line.pt1[1] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, line.color, 2)
    return frame
