import cv2
import time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage
from core.logger import logger
from core.config import config
from models.yolo_model import YoloDetector
from analytics.counter import VehicleCounter
from services.video_stream import VideoStream
from utils.drawing import draw_boxes, draw_counting_lines

# Max resolution to send to UI - reduces pixmap scaling time
UI_FRAME_MAX_W = 860

class VideoWorker(QThread):
    frame_ready    = pyqtSignal(QImage)
    stats_updated  = pyqtSignal(dict)
    fps_updated    = pyqtSignal(float)
    progress_updated = pyqtSignal(int, int)
    finished       = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, video_path: str):
        super().__init__()
        self.video_path = video_path
        self.running = False
        self.paused  = False
        self._speed  = 1.0    # playback multiplier (0.25 – 2.0)
        self._imgsz  = 480    # inference resolution (changeable at runtime)

        try:
            self.detector = YoloDetector()
            self.counter  = VehicleCounter()
        except Exception as e:
            logger.error(f"Failed to initialize models: {e}")
            self.error_occurred.emit(str(e))

    # ─── helpers ─────────────────────────────────────────────
    @staticmethod
    def _to_qimage(frame: np.ndarray) -> QImage:
        """Convert BGR numpy frame → QImage efficiently."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()

    @staticmethod
    def _resize_for_ui(frame: np.ndarray) -> np.ndarray:
        """Downscale frame if it's wider than UI_FRAME_MAX_W."""
        h, w = frame.shape[:2]
        if w > UI_FRAME_MAX_W:
            scale = UI_FRAME_MAX_W / w
            new_w = UI_FRAME_MAX_W
            new_h = int(h * scale)
            return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        return frame

    # ─── main loop ───────────────────────────────────────────
    def run(self):
        self.running = True
        try:
            stream = VideoStream(self.video_path).start()
            total_frames    = stream.total_frames
            current_frame_idx = 0

            # EWM filter for FPS display
            fps_ema = 0.0

            # Time-based throttle for stats/progress (send max 5/s)
            last_ui_time = 0.0
            UI_THROTTLE_S = 0.2   # seconds between stat/progress emits

            prev_infer_time = time.perf_counter()

            while self.running:
                if self.paused:
                    time.sleep(0.05)
                    continue

                if not stream.more():
                    break

                frame = stream.read()
                if frame is None:
                    time.sleep(0.005)
                    continue

                current_frame_idx += 1

                # ── Inference (this is the heavy part – GPU bound) ──
                tracks = self.detector.track(frame)

                # ── Analytics ──
                self.counter.update(tracks)

                if config.hide_counted:
                    tracks = [t for t in tracks if not self.counter.has_crossed(t['track_id'])]

                # ── Draw on frame ──
                frame = draw_counting_lines(frame, config.counting_lines)
                frame = draw_boxes(frame, tracks)

                # ── FPS ──
                now = time.perf_counter()
                dt  = now - prev_infer_time
                prev_infer_time = now
                fps_raw = 1.0 / (dt + 1e-9)
                fps_ema = 0.85 * fps_ema + 0.15 * fps_raw   # smooth

                # ── Apply runtime imgsz to detector ──
                self.detector.current_imgsz = self._imgsz

                # ── Emit frame to UI (always, but resize first) ──
                small_frame = self._resize_for_ui(frame)
                qt_img = self._to_qimage(small_frame)
                self.frame_ready.emit(qt_img)

                # ── Speed control: insert sleep to slow down playback ──
                if self._speed < 1.0:
                    time.sleep((1.0 / self._speed - 1.0) * dt * 0.5)

                # ── Throttle stats / progress ──
                if (now - last_ui_time) >= UI_THROTTLE_S:
                    last_ui_time = now
                    self.stats_updated.emit(dict(self.counter.get_counts()))
                    self.fps_updated.emit(fps_ema)
                    self.progress_updated.emit(current_frame_idx, total_frames)

            stream.stop()
            self.finished.emit()

        except Exception as e:
            logger.error(f"Error in VideoWorker: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
        finally:
            self.running = False

    def stop(self):
        self.running = False
        self.wait()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def set_speed(self, speed: float):
        """Adjust playback speed multiplier (0.25 – 2.0)."""
        self._speed = max(0.25, min(2.0, speed))

    def set_imgsz(self, imgsz: int):
        """Change inference resolution on-the-fly."""
        self._imgsz = imgsz
        self.detector.current_imgsz = imgsz
