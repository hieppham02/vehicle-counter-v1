"""
gui/stats_dialog.py
────────────────────
Loads ui/StatsForm.ui and populates 4 matplotlib charts.
Non-blocking QDialog – stays open while video detection runs.
"""

import os
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge
import numpy as np
from io import BytesIO

from PyQt6.QtWidgets import QDialog, QMessageBox
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6 import uic

from services.data_exporter import DataExporter

CLASS_VI   = {"car": "Ô tô", "bus": "Xe buýt", "truck": "Xe tải", "motorbike": "Xe máy"}
COLORS     = ["#8BE9FD", "#50FA7B", "#FF79C6", "#F1FA8C"]
PANEL      = "#1E1F29"
CLR_MAP    = {"car": "#8BE9FD", "bus": "#50FA7B", "truck": "#FF79C6", "motorbike": "#F1FA8C"}


def _fig_to_qpixmap(fig) -> QPixmap:
    buf = BytesIO()
    fig.savefig(buf, format='png', facecolor=fig.get_facecolor(),
                bbox_inches='tight', dpi=120)
    buf.seek(0)
    pix = QPixmap()
    pix.loadFromData(buf.read())
    buf.close()
    return pix


def _styled(fig, ax):
    fig.patch.set_facecolor(PANEL)
    if ax:
        ax.set_facecolor(PANEL)
        ax.tick_params(colors='#C8C8D4', labelsize=10)
        for sp in ax.spines.values():
            sp.set_color('#44475A')
    return ax


class StatsDialog(QDialog):
    """Standalone stats window backed by ui/StatsForm.ui."""

    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), '..', 'ui', 'StatsForm.ui')
        uic.loadUi(ui_path, self)

        self.setModal(False)

        # Keep counts + trend history
        self._counts: dict = {}
        self._trend_history = {"car": [], "bus": [], "truck": [], "motorbike": []}
        self._trend_times: list = []

        # Chart image label map
        self._chart_labels = {
            "hist":  self.lbl_chart_hist,
            "gauge": self.lbl_chart_gauge,
            "pie":   self.lbl_chart_pie,
            "barh":  self.lbl_chart_barh,
        }

        # Connect buttons
        self.btn_export_hist.clicked.connect(self._do_export)
        self.btn_export_gauge.clicked.connect(self._do_export)
        self.btn_export_pie.clicked.connect(self._do_export)
        self.btn_export_barh.clicked.connect(self._do_export)

        # Auto-refresh timer (500 ms)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    # ── Data feed ──────────────────────────────────────────────────────
    def push_counts(self, counts: dict):
        """Called by MainWindow whenever stats arrive."""
        self._counts = counts
        if not counts:
            return
        data = next(iter(counts.values()))
        self._trend_times.append(time.time())
        for k in self._trend_history:
            self._trend_history[k].append(data.get(k, 0))
        if len(self._trend_times) > 80:
            self._trend_times = self._trend_times[-80:]
            for k in self._trend_history:
                self._trend_history[k] = self._trend_history[k][-80:]

    # ── Refresh ────────────────────────────────────────────────────────
    def _refresh(self):
        if not self.isVisible() or not self._counts:
            return
        data   = next(iter(self._counts.values()))
        keys   = list(data.keys())
        values = [data.get(k, 0) for k in keys]
        labels = [CLASS_VI.get(k, k) for k in keys]
        colors = COLORS[:len(keys)]

        self._draw_hist()
        self._draw_gauge()
        self._draw_pie(labels, values, colors)
        self._draw_barh(labels, values, colors)

    # ── Chart helpers ──────────────────────────────────────────────────
    def _set_chart(self, name: str, fig):
        pix = _fig_to_qpixmap(fig)
        plt.close(fig)
        lbl = self._chart_labels[name]
        w   = max(lbl.width(), 10)
        h   = max(lbl.height(), 10)
        lbl.setPixmap(pix.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))

    def _make_fig(self, w=5.5, h=3.6):
        fig, ax = plt.subplots(figsize=(w, h))
        _styled(fig, ax)
        return fig, ax

    def _draw_hist(self):
        fig, ax = self._make_fig()
        n = len(self._trend_times)
        if n < 2:
            plt.close(fig)
            return

        # Tính tổng lưu lượng theo từng chu kỳ (mỗi điểm là tổng số xe)
        # Sử dụng stacked bar để biểu thị hist
        xs = list(range(n))
        bottoms = np.zeros(n)
        for key, col in CLR_MAP.items():
            hist = np.array(self._trend_history.get(key, []))
            if len(hist) > 0:
                ax.bar(xs[-len(hist):], hist, bottom=bottoms[-len(hist):],
                        label=CLASS_VI.get(key, key), color=col, width=0.8)
                bottoms[-len(hist):] += hist

        ax.set_ylabel("Số lượng xe", color='#C8C8D4', fontsize=10)
        ax.set_xlabel("Chu kỳ thời gian", color='#C8C8D4', fontsize=10)
        ax.grid(axis='y', color='#44475A', linestyle='--', alpha=0.4)
        ax.legend(facecolor='#1E1F29', labelcolor='white', fontsize=9, loc='upper left')
        fig.tight_layout()
        self._set_chart("hist", fig)

    def _draw_gauge(self):
        fig, ax = self._make_fig()
        ax.axis('off')
        
        # Calculate vehicles per minute
        vpm = 0
        if len(self._trend_times) >= 20:
            dt = self._trend_times[-1] - self._trend_times[-20]
            if dt > 0:
                # Sum of deltas
                deltas = 0
                for k in CLR_MAP.keys():
                    h = self._trend_history.get(k, [])
                    if len(h) >= 20:
                        deltas += max(0, h[-1] - h[-20])
                vpm = (deltas / dt) * 60

        val = min(vpm, 100) # max 100 vpm
        
        # Gauge colors: Green (0-20), Yellow (20-50), Red (50-100)
        colors = ['#50FA7B', '#F1FA8C', '#FF5555']
        
        # Draw background arcs
        theta = np.linspace(0, np.pi, 100)
        ax.plot(np.cos(theta), np.sin(theta), color='#44475A', linewidth=20)
        
        # Draw value arc
        end_angle = np.pi * (1 - (val/100))
        val_theta = np.linspace(end_angle, np.pi, int(val) if val > 1 else 2)
        
        if val > 50:
            c = colors[2]
            status = "ÙN TẮC"
            c_text = colors[2]
        elif val > 20:
            c = colors[1]
            status = "ĐÔNG ĐÚC"
            c_text = colors[1]
        else:
            c = colors[0]
            status = "THÔNG THOÁNG"
            c_text = colors[0]
            
        ax.plot(np.cos(val_theta), np.sin(val_theta), color=c, linewidth=20)
        
        # Draw needle
        ax.plot([0, 0.8 * np.cos(end_angle)], [0, 0.8 * np.sin(end_angle)], color='white', linewidth=4)
        ax.plot(0, 0, marker='o', color='white', markersize=12)
        
        ax.text(0, -0.25, f"{int(vpm)} xe/phút", ha='center', va='center', color='white', fontsize=18, fontweight='bold')
        ax.text(0, -0.45, status, ha='center', va='center', color=c_text, fontsize=14, fontweight='bold')
        
        ax.set_xlim(-1.2, 1.2)
        ax.set_ylim(-0.6, 1.2)
        fig.tight_layout()
        self._set_chart("gauge", fig)

    def _draw_pie(self, labels, values, colors):
        fig, ax = self._make_fig()
        ax.axis('equal')
        ax.pie([v or 0.001 for v in values], labels=labels, colors=colors,
               autopct='%1.1f%%', startangle=140,
               textprops={'color': 'white', 'fontsize': 11},
               wedgeprops={'edgecolor': '#1E1F29', 'linewidth': 2})
        fig.tight_layout()
        self._set_chart("pie", fig)
        
    def _draw_barh(self, labels, values, colors):
        fig, ax = self._make_fig()
        bars = ax.barh(labels, values, color=colors, height=0.5)
        ax.set_xlabel("Số lượng xe", color='#C8C8D4', fontsize=10)
        for bar in bars:
            ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                    str(int(bar.get_width())), va='center', color='white',
                    fontsize=10, fontweight='bold')
        ax.grid(axis='x', color='#44475A', linestyle='--', alpha=0.5)
        fig.tight_layout()
        self._set_chart("barh", fig)

    # ── Export ─────────────────────────────────────────────────────────
    def _do_export(self):
        if not self._counts:
            QMessageBox.warning(self, "Chú ý", "Chưa có dữ liệu để xuất.")
            return
        path = DataExporter.export_csv(self._counts)
        if path:
            QMessageBox.information(self, "Xuất CSV", f"Đã lưu tại:\n{path}")
        else:
            QMessageBox.warning(self, "Lỗi", "Không thể xuất file CSV.")

    def closeEvent(self, event):
        event.ignore()
        self.hide()
