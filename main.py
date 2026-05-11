import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from core.logger import logger
from gui.main_window import MainWindow

def main():
    logger.info("Starting Vehicle Counter & Traffic Analytics System...")
    app = QApplication(sys.argv)   
    
    app.setStyle("Fusion")

    try:
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logger.error(f"Failed to start application: {e}")

if __name__ == "__main__":
    main()