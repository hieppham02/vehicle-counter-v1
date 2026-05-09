import sys
import cv2
from PyQt6 import QtWidgets, uic
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import QTimer
from ultralytics import YOLO
import resource_rc

class MainApp:
    def __init__(self):
        self.window = uic.loadUi("./UI/detect-statistic.ui")

        # 🔥 LOGO
        self.logo = self.window.findChild(QtWidgets.QLabel, "src_image")
        if self.logo:
            self.logo.setPixmap(QPixmap("./UI/logo.png"))
            self.logo.setScaledContents(True)

        # 🔥 VIDEO LABEL
        self.video_label = self.window.findChild(QtWidgets.QLabel, "src_video")

        # load video
        self.cap = cv2.VideoCapture("./Test/test.mkv")

        # 🔥 MODEL (nhẹ cho mượt)
        self.model = YOLO("epoch36.pt")  # đổi best.pt nếu muốn

        # 🔥 frame skip để tăng FPS
        self.frame_count = 0

        # 🔥 timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(20)  # ~50 FPS UI

    def update_frame(self):
        try:
            ret, frame = self.cap.read()
            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                return

            # 🔥 resize (tăng FPS mạnh)
            frame = cv2.resize(frame, (640, 480))

            self.frame_count += 1

            # 🔥 chỉ detect mỗi 2 frame
            if self.frame_count % 2 == 0:
                self.results = self.model.track(
                    frame,
                    persist=True,
                    conf=0.4,
                    tracker="bytetrack.yaml",
                    verbose=False
                )

            # nếu chưa có kết quả thì bỏ qua
            if hasattr(self, "results"):
                frame = self.results[0].plot()

            # convert sang Qt
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape

            qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

            self.video_label.setPixmap(QPixmap.fromImage(qt_img))

        except Exception as e:
            print("ERROR:", e)

    def show(self):
        self.window.show()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    main = MainApp()
    main.show()

    sys.exit(app.exec())