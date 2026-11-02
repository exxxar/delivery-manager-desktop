import configparser
import sqlite3
from pathlib import Path

import keyring
from keyring.errors import KeyringError

from .config import INI_PATH, DB_PATH, KEYRING_SERVICE


class LocalStorage:
    """Настройки приложения в INI, секреты — в Windows Credential Manager."""

    def __init__(self):
        self.path = Path(INI_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config = configparser.ConfigParser(interpolation=None)
        self._load()

    def _load(self):
        self.config = configparser.ConfigParser(interpolation=None)
        if self.path.exists():
            self.config.read(self.path, encoding="utf-8")
        if not self.config.has_section("login"):
            self.config.add_section("login")
        self._migrate_legacy_sqlite_settings()

    def _migrate_legacy_sqlite_settings(self):
        # Подхватываем значения из старой версии, где настройки лежали в SQLite.
        legacy_db = Path(DB_PATH)
        if not legacy_db.exists():
            return
        try:
            with sqlite3.connect(legacy_db) as db:
                table = db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
                ).fetchone()
                if not table:
                    return
                rows = db.execute("SELECT key, value FROM settings").fetchall()
            changed = False
            for key, value in rows:
                if not self.config.has_option("login", key):
                    self.config.set("login", key, str(value))
                    changed = True
            if changed:
                self._save()
        except sqlite3.Error:
            # Старую БД не трогаем: приложение продолжит работу с INI.
            pass

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            self.config.write(file)
        tmp_path.replace(self.path)

    def get(self, key, default=None):
        return self.config.get("login", key, fallback=default)

    def set(self, key, value):
        if not self.config.has_section("login"):
            self.config.add_section("login")
        self.config.set("login", key, str(value))
        self._save()

    def get_saved_login_password(self):
        try:
            return keyring.get_password(KEYRING_SERVICE, "login_form_password") or ""
        except Exception:
            return ""

    def set_saved_login_password(self, password):
        try:
            if password:
                keyring.set_password(KEYRING_SERVICE, "login_form_password", password)
            else:
                try:
                    keyring.delete_password(KEYRING_SERVICE, "login_form_password")
                except Exception:
                    pass
            return True
        except Exception:
            return False

    def get_token(self, username):
        try:
            return keyring.get_password(KEYRING_SERVICE, username)
        except Exception:
            return None

    def set_token(self, username, token):
        keyring.set_password(KEYRING_SERVICE, username, token)

    def delete_token(self, username):
        try:
            keyring.delete_password(KEYRING_SERVICE, username)
        except Exception:
            pass
