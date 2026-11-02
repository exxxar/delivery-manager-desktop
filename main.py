import sys
from PySide6.QtWidgets import QApplication
from app.config import APP_NAME
from app.storage import LocalStorage
from app.ui import LoginWindow, STYLE

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLE)
    storage = LocalStorage()
    login = LoginWindow(storage)
    login.showMaximized()
    sys.exit(app.exec())
