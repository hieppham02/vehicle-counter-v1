"""
gui/line_editor.py
──────────────────
Interactive overlay widget that lets users click-drag to reposition the
counting line on the video frame.

Usage:
    self.line_editor = LineEditorOverlay(parent=self.src_video)
    self.line_editor.line_changed.connect(self._on_line_changed)
    self.line_editor.start_edit()   # enter edit mode
    self.line_editor.stop_edit()    # leave edit mode
"""

from PyQt6.QtWidgets import QWidget, QLabel, QRubberBand
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QCursor


class LineEditorOverlay(QWidget):
    """Transparent overlay drawn on top of the video label.
    Emits *line_changed(pt1, pt2)* in **video pixel space** after the user
    releases the mouse.
    """

    line_changed = pyqtSignal(tuple, tuple)   # pt1 (x,y), pt2 (x,y) in VIDEO coords

    def __init__(self, video_label: QLabel):
        super().__init__(video_label)
        self._video_label = video_label
        self._editing      = False
        self._dragging     = False

        # Points in *widget* space (px within this overlay)
        self._p1: QPoint | None = None
        self._p2: QPoint | None = None

        # Points in *video frame* space (will be emitted)
        self._vid_p1: tuple = (0, 400)
        self._vid_p2: tuple = (1280, 400)

        # Video frame resolution (updated by main window whenever a frame arrives)
        self.video_w: int = 1280
        self.video_h: int = 720

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setMouseTracking(True)
        self.hide()

    # ── public API ────────────────────────────────────────
    def start_edit(self):
        self._editing = True
        self.resize(self._video_label.size())
        self.move(0, 0)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.show()
        self.raise_()
        self.update()

    def stop_edit(self):
        self._editing = False
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.hide()

    def set_initial_line(self, pt1: tuple, pt2: tuple):
        """Set the initial line position in video-pixel space."""
        self._vid_p1 = pt1
        self._vid_p2 = pt2
        self._update_widget_points()
        self.update()

    def update_video_size(self, w: int, h: int):
        self.video_w = w
        self.video_h = h

    # ── coordinate mapping ─────────────────────────────────
    def _video_to_widget(self, vx: int, vy: int) -> QPoint:
        """Map video-pixel coords → overlay-widget coords."""
        lw = self._video_label.width()
        lh = self._video_label.height()
        scale = min(lw / self.video_w, lh / self.video_h)
        off_x = (lw - self.video_w * scale) / 2
        off_y = (lh - self.video_h * scale) / 2
        return QPoint(int(vx * scale + off_x), int(vy * scale + off_y))

    def _widget_to_video(self, wx: int, wy: int) -> tuple:
        """Map overlay-widget coords → video-pixel coords."""
        lw = self._video_label.width()
        lh = self._video_label.height()
        scale = min(lw / self.video_w, lh / self.video_h)
        off_x = (lw - self.video_w * scale) / 2
        off_y = (lh - self.video_h * scale) / 2
        vx = int((wx - off_x) / scale)
        vy = int((wy - off_y) / scale)
        vx = max(0, min(self.video_w, vx))
        vy = max(0, min(self.video_h, vy))
        return (vx, vy)

    def _update_widget_points(self):
        self._p1 = self._video_to_widget(*self._vid_p1)
        self._p2 = self._video_to_widget(*self._vid_p2)

    # ── events ─────────────────────────────────────────────
    def resizeEvent(self, event):
        self.resize(self._video_label.size())
        self._update_widget_points()
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if not self._editing:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._p1 = event.pos()
            self._p2 = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._p2 = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if not self._dragging:
            return
        self._dragging = False
        self._p2 = event.pos()
        # Convert to video space
        self._vid_p1 = self._widget_to_video(self._p1.x(), self._p1.y())
        self._vid_p2 = self._widget_to_video(self._p2.x(), self._p2.y())
        self.update()
        self.line_changed.emit(self._vid_p1, self._vid_p2)

    def paintEvent(self, event):
        if not self._editing or self._p1 is None or self._p2 is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Semi-transparent dark overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        # The line
        pen = QPen(QColor("#FFD700"), 3, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawLine(self._p1, self._p2)

        # Endpoint circles
        painter.setBrush(QColor("#FFD700"))
        painter.drawEllipse(self._p1, 7, 7)
        painter.drawEllipse(self._p2, 7, 7)

        # Instruction label
        painter.setPen(QColor("white"))
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(10, 24, "✏️ Kéo để vẽ đường đếm  |  Nhấn 'Xác nhận' để lưu")

        # Coordinate tooltip
        coord_txt = (f"A({self._vid_p1[0]},{self._vid_p1[1]}) → "
                     f"B({self._vid_p2[0]},{self._vid_p2[1]})")
        painter.setPen(QColor("#FFD700"))
        font2 = QFont("Segoe UI", 9)
        painter.setFont(font2)
        painter.drawText(10, self.height() - 10, coord_txt)

        painter.end()
