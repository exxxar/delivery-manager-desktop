from pathlib import Path
import os

APP_NAME = "Courier Desktop"
APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "CourierDesktop"
APP_DIR.mkdir(parents=True, exist_ok=True)
INI_PATH = APP_DIR / "settings.ini"
DB_PATH = APP_DIR / "settings.sqlite3"  # резерв для совместимости
KEYRING_SERVICE = "CourierDesktop"
API_PREFIX_DEFAULT = "/api/desktop"
