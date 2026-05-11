"""
gui/main_window.py  –  Vehicle Counter & Traffic Analytics System
Only dynamic content here: video frames, chart images, status values.
All static widgets are defined in ui/MainForm.ui.
"""

import os
import cv2
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO

from PyQt6.QtWidgets import QMainWindow, QFileDialog, QMessageBox, QSizePolicy, QLabel, QDialog, QApplication
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6 import uic
import qtawesome as qta
import logging

from core.logger import logger
from core.config import config
from gui.workers import VideoWorker
from gui.stats_dialog import StatsDialog
from gui.line_editor import LineEditorOverlay
from services.data_exporter import DataExporter


class YoutubeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi('ui/YoutubeForm.ui', self)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        
    def get_url(self):
        return self.txt_url.text().strip()

# ── palette (for chart rendering only) ──────────────────────────────────────
CLASS_VI = {"car": "Ô tô", "bus": "Xe buýt", "truck": "Xe tải", "motorbike": "Xe máy"}
COLORS   = ["#8BE9FD", "#50FA7B", "#FF79C6", "#F1FA8C"]
CLR_MAP  = {"car": "#8BE9FD", "bus": "#50FA7B", "truck": "#FF79C6", "motorbike": "#F1FA8C"}
BG_CHART = "#2F3142"

_SPEED_MAP = {1: 0.25, 2: 0.5, 3: 0.75, 4: 1.0, 5: 1.25, 6: 1.5, 7: 1.75, 8: 2.0}
_RES_MAP   = {0: 320, 1: 480, 2: 640, 3: 736}


def _fig_to_pixmap(fig) -> QPixmap:
    buf = BytesIO()
    fig.savefig(buf, format='png', facecolor=fig.get_facecolor(),
                bbox_inches='tight', dpi=150)
    buf.seek(0)
    pix = QPixmap()
    pix.loadFromData(buf.read())
    buf.close()
    return pix


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        import os
        ui_path = os.path.join(os.path.dirname(__file__), '..', 'ui', 'MainForm.ui')
        uic.loadUi(ui_path, self)

        # Runtime state
        self.worker: VideoWorker | None = None
        self.current_video_path: str | None = None
        self.current_counts: dict = {}
        self.video_fps: float = 30.0
        self._frame_w: int = 1280
        self._frame_h: int = 720
        self._edit_mode = False
        self._line_confirmed = False
        self._pending_pt1: tuple | None = None
        self._pending_pt2: tuple | None = None
        self._trend_history: dict = {k: [] for k in CLASS_VI}

        # Chart refresh timer (500 ms)
        self._chart_timer = QTimer(self)
        self._chart_timer.setInterval(500)
        self._chart_timer.timeout.connect(self._refresh_charts)
        self._chart_needs_update = False

        self._stats_dialog = StatsDialog(self)

        self._setup_dynamic()
        self._connect_signals()
        self._apply_icons()

        icon_path = os.path.join(os.path.dirname(__file__), '..', 'resource', 'logo.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            self.setWindowIcon(qta.icon('fa5s.car', color='#8BE9FD'))

    # ──────────────────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────────
    def _setup_dynamic(self):
        # Make src_video expand to fill its container
        # self.src_video.setSizePolicy(
        #     QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Line editor overlay (transparent, sits on top of src_video)
        self._line_editor = LineEditorOverlay(self.src_video)
        self._line_editor.line_changed.connect(self._on_line_dragged)
        self._line_editor.set_initial_line(
            config.counting_lines[0].pt1,
            config.counting_lines[0].pt2,
        )

        # Initialise status labels from saved config
        cfg = config.counting_lines[0]
        self.lbl_val_line.setText(
            f"({cfg.pt1[0]},{cfg.pt1[1]})→({cfg.pt2[0]},{cfg.pt2[1]})")

        # combo default index
        self.combo_resolution.setCurrentIndex(1)   # 480
        
        # Init AI sliders from config
        self.slider_conf.setValue(int(config.confidence_threshold * 100))
        self.slider_iou.setValue(int(config.iou_threshold * 100))
        self.lbl_val_conf.setText(f"{config.confidence_threshold:.2f}")
        self.lbl_val_iou.setText(f"{config.iou_threshold:.2f}")
        self.chk_hide_counted.setChecked(config.hide_counted)

        self._chart_timer.start()

    # ──────────────────────────────────────────────────────────────────────────
    # ICONS  (FontAwesome via QtAwesome)
    # ──────────────────────────────────────────────────────────────────────────
    def _apply_icons(self):
        """Set FontAwesome icons on summary cards and window title bar."""
        def ic(name, color='white'):
            return qta.icon(name, color=color, scale_factor=1.0)

        # Summary icons (1 uniform color: #8BE9FD)
        color_unified = '#8BE9FD'
        self.lbl_icon_car.setPixmap(ic('fa5s.car', color_unified).pixmap(22, 22))
        self.lbl_icon_bus.setPixmap(ic('fa5s.bus', color_unified).pixmap(22, 22))
        self.lbl_icon_truck.setPixmap(ic('fa5s.truck', color_unified).pixmap(22, 22))
        self.lbl_icon_motorbike.setPixmap(ic('fa5s.motorcycle', color_unified).pixmap(22, 22))

        # Window title-bar icon
        self.setWindowIcon(ic('fa5s.traffic-light', '#8BE9FD'))

    # ──────────────────────────────────────────────────────────────────────────
    # SIGNALS
    # ──────────────────────────────────────────────────────────────────────────
    def _connect_signals(self):
        self.btn_load_video.clicked.connect(self._load_video)
        self.btn_load_youtube.clicked.connect(self._load_youtube)
        self.btn_start.clicked.connect(self._start_detection)
        self.btn_pause.clicked.connect(self._pause_detection)
        self.btn_stop.clicked.connect(self._stop_detection)
        self.btn_edit_line.clicked.connect(self._toggle_edit_line)
        self.btn_confirm_line.clicked.connect(self._confirm_line)
        self.btn_stats.clicked.connect(self._open_stats)
        self.slider_speed.valueChanged.connect(self._on_speed_changed)
        self.combo_resolution.currentIndexChanged.connect(self._on_resolution_changed)
        
        self.slider_conf.valueChanged.connect(self._on_conf_changed)
        self.slider_iou.valueChanged.connect(self._on_iou_changed)
        self.chk_hide_counted.stateChanged.connect(self._on_hide_counted_changed)

    def _open_stats(self):
        self._stats_dialog.show()
        self._stats_dialog.raise_()
        self._stats_dialog.activateWindow()

    def _on_conf_changed(self, val: int):
        conf = val / 100.0
        config.confidence_threshold = conf
        self.lbl_val_conf.setText(f"{conf:.2f}")

    def _on_iou_changed(self, val: int):
        iou = val / 100.0
        config.iou_threshold = iou
        self.lbl_val_iou.setText(f"{iou:.2f}")

    def _on_hide_counted_changed(self, state: int):
        config.hide_counted = (state != 0)

    # ──────────────────────────────────────────────────────────────────────────
    # SPEED / RESOLUTION
    # ──────────────────────────────────────────────────────────────────────────
    def _on_speed_changed(self, val: int):
        speed = _SPEED_MAP.get(val, 1.0)
        self.lbl_speed_val.setText(f"{speed:.2f}×")
        if self.worker:
            self.worker.set_speed(speed)

    def _on_resolution_changed(self, idx: int):
        res = _RES_MAP.get(idx, 480)
        if self.worker:
            self.worker.set_imgsz(res)

    # ──────────────────────────────────────────────────────────────────────────
    # LINE EDITOR
    # ──────────────────────────────────────────────────────────────────────────
    def _toggle_edit_line(self):
        if not self._edit_mode:
            self._edit_mode = True
            self._line_editor.update_video_size(self._frame_w, self._frame_h)
            self._line_editor.start_edit()
            self.btn_edit_line.setText("Huỷ")
            self.btn_confirm_line.setVisible(True)
            self.lbl_line_coords.setText("Kéo chuột trên video để vẽ line mới...")
        else:
            self._cancel_edit_line()

    def _cancel_edit_line(self):
        self._edit_mode = False
        self._line_editor.stop_edit()
        self.btn_edit_line.setText("✏️ Vẽ lại đường line")
        self.btn_confirm_line.setVisible(False)
        self._pending_pt1 = self._pending_pt2 = None
        self.lbl_line_coords.setText("Nhấn 'Vẽ lại' rồi kéo trên video")

    def _on_line_dragged(self, pt1: tuple, pt2: tuple):
        self._pending_pt1 = pt1
        self._pending_pt2 = pt2
        self.lbl_line_coords.setText(f"A{pt1} → B{pt2}\n(Nhấn 'Xác nhận' để lưu)")

    def _confirm_line(self):
        if self._pending_pt1 is None:
            QMessageBox.warning(self, "Chú ý", "Vui lòng vẽ đường line trên video trước.")
            return
        from core.config import LineConfig
        config.counting_lines = [
            LineConfig(name="", color=(255, 140, 0),
                       pt1=self._pending_pt1, pt2=self._pending_pt2)
        ]
        config.save()
        if self.worker:
            self.worker.counter.reset()
        self.lbl_val_line.setText(
            f"({self._pending_pt1[0]},{self._pending_pt1[1]})"
            f"→({self._pending_pt2[0]},{self._pending_pt2[1]})")
        self._cancel_edit_line()
        self._line_confirmed = True
        self.btn_start.setEnabled(True)
        QMessageBox.information(self, "Đã lưu",
            "Đường đếm xe đã được lưu!\nBạn có thể nhấn Bắt đầu.")

    # ──────────────────────────────────────────────────────────────────────────
    # VIDEO CONTROLS
    # ──────────────────────────────────────────────────────────────────────────
    def _prepare_video_source(self, path: str):
        self.current_video_path = path
        logger.info(f"Loaded video source: {path}")

        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            self.video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            self._frame_w  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._frame_h  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            ok, frame = cap.read()
            if ok:
                self._show_cv_frame(frame)
            cap.release()

        self._line_editor.update_video_size(self._frame_w, self._frame_h)
        self._line_confirmed = False
        self.btn_start.setEnabled(False)
        self._toggle_edit_line()
        QMessageBox.information(self, "Vẽ đường đếm xe",
            "📐 Video đã tải xong!\n\n"
            "Vui lòng KÉO CHUỘT trên màn hình video để vẽ\n"
            "đường đếm xe phù hợp với góc camera,\n"
            "sau đó nhấn Xác nhận")

    def _load_video(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Mở video", config.video_dir,
            "Video Files (*.mp4 *.avi *.mkv);;All Files (*)")
        if not file_name:
            return
        self._prepare_video_source(file_name)

    def _load_youtube(self):
        dlg = YoutubeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
            
        url = dlg.get_url()
        if not url:
            return
            
        import yt_dlp
        ydl_opts = {'format': 'best[ext=mp4]/best', 'quiet': True}
        
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url.strip(), download=False)
                stream_url = info.get('url', None)
                if not stream_url:
                    raise Exception("Không tìm thấy link stream.")
            QApplication.restoreOverrideCursor()
            self._prepare_video_source(stream_url)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Lỗi", f"Không thể tải video từ YouTube:\n{e}")

    def _start_detection(self):
        if not self.current_video_path:
            return
        if self.worker and self.worker.paused:
            self.worker.resume()
            self.btn_pause.setEnabled(True)
            self.btn_start.setEnabled(False)
            return

        self.worker = VideoWorker(self.current_video_path)
        self.worker.frame_ready.connect(self._on_frame)
        self.worker.stats_updated.connect(self._on_stats)
        self.worker.fps_updated.connect(self._on_fps)
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error_occurred.connect(self._on_error)
        # Apply current UI settings
        self.worker.set_speed(_SPEED_MAP.get(self.slider_speed.value(), 1.0))
        self.worker.set_imgsz(_RES_MAP.get(self.combo_resolution.currentIndex(), 480))
        self.worker.start()

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.btn_load_video.setEnabled(False)

    def _pause_detection(self):
        if self.worker:
            self.worker.pause()
            self.btn_pause.setEnabled(False)
            self.btn_start.setEnabled(True)

    def _stop_detection(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self._on_finished()

    # ──────────────────────────────────────────────────────────────────────────
    # SIGNAL HANDLERS
    # ──────────────────────────────────────────────────────────────────────────
    def _show_cv_frame(self, frame: np.ndarray):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        self._on_frame(qt_img)

    def _on_frame(self, qt_img: QImage):
        pix = QPixmap.fromImage(qt_img)
        vw  = self.src_video.width()  or pix.width()
        vh  = self.src_video.height() or pix.height()
        self.src_video.setPixmap(
            pix.scaled(vw, vh, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.FastTransformation))
        if self._edit_mode:
            self._line_editor.resize(self.src_video.size())

    def _on_stats(self, counts: dict):
        self.current_counts = counts
        if not counts:
            return
        data  = next(iter(counts.values()))
        total = sum(data.values())

        # Update summary cards
        self.lbl_num_car.setText(str(data.get("car", 0)))
        self.lbl_num_bus.setText(str(data.get("bus", 0)))
        self.lbl_num_truck.setText(str(data.get("truck", 0)))
        self.lbl_num_motorbike.setText(str(data.get("motorbike", 0)))

        # Update status panel
        self.lbl_val_total.setText(str(total))
        if self.worker and hasattr(self.worker, 'counter'):
            self.lbl_val_objects.setText(str(len(self.worker.counter.track_history)))

        self._chart_needs_update = True

    def _on_fps(self, fps: float):
        self.lbl_val_fps.setText(f"{fps:.1f}")
        parts = self.lbl_info.text().split("|")
        if len(parts) >= 2:
            self.lbl_info.setText(
                f"{parts[0].strip()} | {parts[1].strip()} | FPS: {fps:.1f}")

    def _on_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        if current > 0:
            fps = self.video_fps or 30.0
            cur = current / fps
            rem = max(0, total / fps - cur)

            def fmt(s):
                m, sec = divmod(int(s), 60)
                h, m   = divmod(m, 60)
                return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

            parts   = self.lbl_info.text().split("|")
            fps_str = parts[2].strip() if len(parts) >= 3 else "FPS: 0.0"
            self.lbl_info.setText(f"Time: {fmt(cur)} | Remaining: {fmt(rem)} | {fps_str}")

    def _on_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_load_video.setEnabled(True)
        self.progress_bar.setValue(0)

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Lỗi", msg)
        self._on_finished()

    # ──────────────────────────────────────────────────────────────────────────
    # LEFT PANEL CHARTS
    # ──────────────────────────────────────────────────────────────────────────
    def _refresh_charts(self):
        if not self._chart_needs_update or not self.current_counts:
            return
        self._chart_needs_update = False

        self._stats_dialog.push_counts(self.current_counts)

        data   = next(iter(self.current_counts.values()))
        keys   = list(data.keys())
        values = [data.get(k, 0) for k in keys]
        labels = [CLASS_VI.get(k, k) for k in keys]
        
        N = len(labels)
        if N < 3:
            return
            
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        vals   = values + [values[0]]
        angles += angles[:1]
        
        fig = plt.figure(figsize=(3.5, 3.5))
        fig.patch.set_facecolor(BG_CHART)
        ax = fig.add_subplot(111, polar=True)
        ax.set_facecolor(BG_CHART)
        ax.tick_params(colors='#C8C8D4', labelsize=10)
        ax.spines['polar'].set_color('#44475A')
        ax.set_thetagrids(np.degrees(angles[:-1]), labels, color='white', fontsize=10)
        ax.plot(angles, vals, color='#8BE9FD', linewidth=2.0, marker='o', markersize=8, markeredgecolor='white', markeredgewidth=1)
        ax.fill(angles, vals, color='#8BE9FD', alpha=0.3)
        fig.tight_layout(pad=1.5)
        
        pix = _fig_to_pixmap(fig)
        plt.close(fig)
        w = max(self.lbl_chart_radar.width(), 10)
        h = max(self.lbl_chart_radar.height(), 10)
        self.lbl_chart_radar.setPixmap(pix.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation))
    # ──────────────────────────────────────────────────────────────────────────
    # EXPORT
    # ──────────────────────────────────────────────────────────────────────────
    def _do_export(self):
        if not self.current_counts:
            QMessageBox.warning(self, "Chú ý", "Chưa có dữ liệu để xuất.")
            return
        path = DataExporter.export_csv(self.current_counts)
        if path:
            QMessageBox.information(self, "Xuất CSV", f"Đã lưu tại:\n{path}")
        else:
            QMessageBox.warning(self, "Lỗi", "Không thể xuất file CSV.")
