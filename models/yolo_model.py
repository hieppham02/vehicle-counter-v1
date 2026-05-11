import os
from ultralytics import YOLO
import numpy as np
from core.logger import logger
from core.config import config
from typing import List, Dict

class YoloDetector:
    def __init__(self, model_path: str = None):
        if model_path is None:
            model_path = config.model_path
        
        try:
            logger.info(f"Loading model from {model_path}...")
            self.model = YOLO(model_path)
            # classes: 2=car, 3=motorcycle, 5=bus, 7=truck
            self.target_classes = config.target_classes
            self.class_names = self.model.names
            self.current_imgsz = 480   # default; updated at runtime by worker
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise e

    def track(self, frame: np.ndarray) -> List[Dict]:
        """
        Run inference and tracking on a single frame.
        Returns a list of tracked objects.
        """
        # Use custom tracker config (track_buffer=60 for better occlusion recovery)
        _tracker_cfg = os.path.join(
            os.path.dirname(__file__), '..', 'configs', 'bytetrack_custom.yaml'
        )
        results = self.model.track(
            source=frame,
            persist=True,
            tracker=_tracker_cfg,
            conf=config.confidence_threshold,
            iou=config.iou_threshold,
            classes=self.target_classes,
            verbose=False,
            half=True,
            imgsz=self.current_imgsz,
        )
        
        tracks = []
        if len(results) > 0:
            result = results[0]
            if result.boxes is not None and result.boxes.id is not None:
                boxes = result.boxes.xyxy.cpu().numpy()
                track_ids = result.boxes.id.int().cpu().tolist()
                class_ids = result.boxes.cls.int().cpu().tolist()
                confs = result.boxes.conf.cpu().numpy()
                
                for box, track_id, cls_id, conf in zip(boxes, track_ids, class_ids, confs):
                    tracks.append({
                        'bbox': box,
                        'track_id': track_id,
                        'class_id': cls_id,
                        'class_name': self.class_names[cls_id],
                        'confidence': conf
                    })
        return tracks
