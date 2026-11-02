from datetime import date
import sys
import json
import html
import io
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QDate, QDateTime, QTimer, QObject, Signal, Slot
from PySide6.QtGui import QFont, QPixmap, QColor, QBrush
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QSpinBox, QGroupBox, QFormLayout, QDateEdit, QComboBox,
    QDialog, QListWidget, QListWidgetItem, QAbstractItemView, QDoubleSpinBox, QTextEdit, QFrame, QProgressBar, QFileDialog, QScrollArea, QGridLayout, QGroupBox, QTabWidget, QTableWidget, QTableWidgetItem, QAbstractButton, QSplitter, QSizePolicy, QLayout)
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
import qrcode
import requests
from .api import ApiError
from .storage import LocalStorage
from .poller import OrderPoller

STYLE = """
QWidget { background:#101827; color:#e8eef8; font-family:'Segoe UI'; font-size:10pt; }
QMainWindow { background:#0b1220; }\nQFrame#loginPanel { background:#121e30; border:1px solid #263850; border-radius:16px; }\nQFrame#logPanel { background:#0d1726; border:1px solid #263850; border-radius:16px; }\nQTextEdit#processLog { background:#09111d; color:#dbeafe; border:1px solid #1e3048; border-radius:10px; padding:12px; font-family:Consolas; font-size:9pt; }
QLabel#title { font-size:20pt; font-weight:700; color:#ffffff; }
QLabel#muted { color:#91a0b8; }
QGroupBox { border:1px solid #26344a; border-radius:12px; margin-top:12px; padding:14px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; color:#a9bdd9; }
QLineEdit, QSpinBox, QDateEdit, QComboBox { background:#172338; border:1px solid #30425d; border-radius:8px; padding:9px; color:#fff; }
QPushButton { background:#2563eb; border:0; border-radius:8px; padding:9px 14px; color:white; font-weight:600; }
QPushButton:hover { background:#3478ff; }
QPushButton:disabled { background:#35445b; color:#8996aa; }
QPushButton#secondary { background:#25344b; }
QPushButton#danger { background:#a83245; }
QTabWidget::pane { border:1px solid #26344a; border-radius:10px; top:-1px; }
QTabBar::tab { background:#172338; padding:11px 18px; margin-right:4px; border-top-left-radius:8px; border-top-right-radius:8px; }
QTabBar::tab:selected { background:#2563eb; }
QTableWidget { background:#121d2e; alternate-background-color:#172338; gridline-color:#26344a; border:1px solid #26344a; border-radius:8px; selection-background-color:#264c82; }
QHeaderView::section { background:#1c2a40; color:#cbd7e8; padding:9px; border:0; font-weight:600; }
QCheckBox { spacing:8px; }
"""


def prepare_window(window, maximize=False):
    """Добавляет стандартные кнопки Windows и при необходимости открывает окно развёрнутым."""
    flags = window.windowFlags()
    flags |= Qt.WindowType.WindowMinimizeButtonHint
    flags |= Qt.WindowType.WindowMaximizeButtonHint
    flags |= Qt.WindowType.WindowCloseButtonHint
    window.setWindowFlags(flags)
    if maximize:
        window.setWindowState(window.windowState() | Qt.WindowState.WindowMaximized)


class LoginWindow(QWidget):
    def __init__(self, storage):
        super().__init__()
        prepare_window(self, maximize=True)
        self.storage = storage
        self.api = None
        self.setWindowTitle("Courier Desktop — Вход")
        self.setMinimumSize(900, 570)
        self.resize(1040, 650)

        root = QHBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(22)

        form_panel = QFrame()
        form_panel.setObjectName("loginPanel")
        form_panel.setMinimumWidth(390)
        form_panel.setMaximumWidth(440)
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(28, 28, 28, 28)
        form_layout.setSpacing(12)

        eyebrow = QLabel("COURIER DESKTOP")
        eyebrow.setStyleSheet("color:#60a5fa;font-size:9pt;font-weight:700;letter-spacing:2px;")
        title = QLabel("Добро пожаловать")
        title.setObjectName("title")
        subtitle = QLabel("Войдите, чтобы подключиться к кабинету курьера")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        form_layout.addWidget(eyebrow)
        form_layout.addSpacing(10)
        form_layout.addWidget(title)
        form_layout.addWidget(subtitle)
        form_layout.addSpacing(12)

        self.url = QLineEdit(storage.get("api_url", "https://example.com"))
        self.url.setPlaceholderText("https://ваш-домен.ru")
        self.prefix = QLineEdit(storage.get("api_prefix", "/api/desktop"))
        self.prefix.setPlaceholderText("/api/desktop")
        self.login = QLineEdit(storage.get("last_login", ""))
        self.login.setPlaceholderText("Телефон или email")
        self.tenant = QLineEdit(storage.get("tenant", ""))
        self.tenant.setPlaceholderText("Tenant ID или slug (если требуется)")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Пароль")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setText(storage.get_saved_login_password())

        # Сохраняем обычные поля сразу после каждого изменения.
        self.url.textChanged.connect(lambda value: self.storage.set("api_url", value))
        self.prefix.textChanged.connect(lambda value: self.storage.set("api_prefix", value))
        self.login.textChanged.connect(lambda value: self.storage.set("last_login", value))
        self.tenant.textChanged.connect(lambda value: self.storage.set("tenant", value))

        # Пароль сохраняется с небольшой задержкой в системное защищённое хранилище.
        self._password_save_timer = QTimer(self)
        self._password_save_timer.setSingleShot(True)
        self._password_save_timer.setInterval(600)
        self._password_save_timer.timeout.connect(self._save_login_password)
        self.password.textChanged.connect(lambda _value: self._password_save_timer.start())

        for label, widget in [
            ("Адрес сервера", self.url),
            ("Префикс API", self.prefix),
            ("Логин", self.login),
            ("Tenant (необязательно)", self.tenant),
            ("Пароль", self.password),
        ]:
            caption = QLabel(label)
            caption.setStyleSheet("color:#a9bdd9;font-size:9pt;font-weight:600;")
            form_layout.addWidget(caption)
            form_layout.addWidget(widget)

        self.btn = QPushButton("Войти в систему")
        self.btn.setMinimumHeight(44)
        self.btn.clicked.connect(self.do_login)
        form_layout.addSpacing(8)
        form_layout.addWidget(self.btn)
        form_layout.addStretch()
        secure_note = QLabel("Защищённое подключение · Bearer token")
        secure_note.setObjectName("muted")
        secure_note.setStyleSheet("font-size:8pt;")
        form_layout.addWidget(secure_note)

        log_panel = QFrame()
        log_panel.setObjectName("logPanel")
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(22, 22, 22, 22)
        log_layout.setSpacing(12)

        log_header = QHBoxLayout()
        log_title_box = QVBoxLayout()
        log_title = QLabel("Журнал подключения")
        log_title.setStyleSheet("font-size:14pt;font-weight:700;color:#f1f5f9;")
        log_subtitle = QLabel("Системные события авторизации в реальном времени")
        log_subtitle.setObjectName("muted")
        log_title_box.addWidget(log_title)
        log_title_box.addWidget(log_subtitle)
        log_header.addLayout(log_title_box)
        log_header.addStretch()
        self.connection_badge = QLabel("● ОЖИДАНИЕ")
        self.connection_badge.setStyleSheet(
            "background:#263449;color:#a9bdd9;padding:7px 10px;border-radius:8px;"
            "font-size:8pt;font-weight:700;"
        )
        log_header.addWidget(self.connection_badge)
        log_layout.addLayout(log_header)

        self.process_log = QTextEdit()
        self.process_log.setReadOnly(True)
        self.process_log.setObjectName("processLog")
        self.process_log.setPlaceholderText("События подключения появятся здесь...")
        self.process_log.document().setMaximumBlockCount(300)
        log_layout.addWidget(self.process_log, 1)

        log_footer = QHBoxLayout()
        self.log_hint = QLabel("Пароль хранится отдельно в защищённом хранилище Windows.")
        self.log_hint.setObjectName("muted")
        clear_log = QPushButton("Очистить")
        clear_log.setObjectName("secondary")
        clear_log.clicked.connect(self.process_log.clear)
        log_footer.addWidget(self.log_hint)
        log_footer.addStretch()
        log_footer.addWidget(clear_log)
        log_layout.addLayout(log_footer)

        root.addWidget(form_panel, 0)
        root.addWidget(log_panel, 1)

        self.password.returnPressed.connect(self.do_login)
        self.write_log("Приложение запущено. Ожидание ввода учётных данных.", "info")

    def _save_login_password(self):
        saved = self.storage.set_saved_login_password(self.password.text())
        if not saved:
            self.write_log(
                "Не удалось сохранить пароль в защищённом хранилище Windows; остальные поля сохранены.",
                "warning"
            )

    def write_log(self, message, level="info"):
        colors = {
            "info": "#93c5fd",
            "success": "#6ee7b7",
            "warning": "#fcd34d",
            "error": "#fca5a5",
            "system": "#94a3b8",
        }
        color = colors.get(level, colors["info"])
        timestamp = QDateTime.currentDateTime().toString("HH:mm:ss")
        self.process_log.append(
            f'<span style="color:#64748b">[{timestamp}]</span> '
            f'<span style="color:{color};font-weight:600">{message}</span>'
        )
        bar = self.process_log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_connection_state(self, text, color):
        self.connection_badge.setText(f"● {text}")
        self.connection_badge.setStyleSheet(
            f"background:#263449;color:{color};padding:7px 10px;border-radius:8px;"
            "font-size:8pt;font-weight:700;"
        )

    def do_login(self):
        from .api import ApiClient

        server = self.url.text().strip().rstrip("/")
        prefix = self.prefix.text().strip() or "/api/desktop"
        login = self.login.text().strip()
        password = self.password.text()
        if self._password_save_timer.isActive():
            self._password_save_timer.stop()
            self._save_login_password()

        if not server or not login or not password:
            self.write_log("Заполните адрес сервера, логин и пароль.", "warning")
            QMessageBox.information(self, "Не все данные заполнены",
                                    "Укажите адрес сервера, логин и пароль.")
            return

        self.btn.setEnabled(False)
        self.btn.setText("Подключение...")
        self.set_connection_state("ПОДКЛЮЧЕНИЕ", "#fcd34d")
        self.write_log(f"Подготовка подключения к серверу: {server}", "info")
        self.write_log(f"Используется API-префикс: {prefix}", "system")
        self.write_log("Отправка запроса авторизации. Секретные данные скрыты.", "info")

        try:
            self.api = ApiClient(server, prefix)
            result = self.api.login(login, password, self.tenant.text().strip() or None)
            self.write_log("Сервер принял запрос авторизации.", "success")

            data = result.get("data", {})
            token = data.get("token")
            if not token:
                raise RuntimeError("Сервер не вернул токен авторизации.")

            user = data.get("user", {})
            identity = str(user.get("id") or login)
            self.write_log("Получен токен доступа.", "success")
            self.storage.set_token(identity, token)
            self.write_log("Токен сохранён в защищённом хранилище Windows.", "success")

            self.storage.set("identity", identity)
            self.storage.set("api_url", server)
            self.storage.set("api_prefix", prefix)
            self.storage.set("tenant", self.tenant.text().strip())
            self.storage.set("last_login", login)
            self.api.set_token(token)

            display_name = user.get("name") or login
            self.write_log(f"Пользователь подтверждён: {display_name}.", "success")
            self.write_log("Авторизация завершена. Открываем рабочую панель.", "success")
            self.set_connection_state("УСПЕШНО", "#6ee7b7")

            self.main = MainWindow(self.api, self.storage, user, identity)
            self.main.showMaximized()
            self.close()

        except Exception as exc:
            safe_error = str(exc).replace("<", "&lt;").replace(">", "&gt;")
            self.write_log(f"Ошибка авторизации: {safe_error}", "error")
            self.set_connection_state("ОШИБКА", "#fca5a5")
            QMessageBox.critical(self, "Ошибка входа", str(exc))
        finally:
            self.btn.setEnabled(True)
            self.btn.setText("Войти в систему")


class MapBridge(QObject):
    pointSelected = Signal(float, float)
    mapReady = Signal()

    @Slot(float, float)
    def pointSelectedFromMap(self, lat, lng):
        self.pointSelected.emit(float(lat), float(lng))

    @Slot()
    def readyFromMap(self):
        self.mapReady.emit()


class DeliveryCalculatorWidget(QWidget):
    MAPTILER_DEFAULT_KEY = "l7t0HU7CqsgOKgS9rtvU"

    def __init__(self, api, storage, order=None, shops=None, parent=None):
        super().__init__(parent)
        self.api, self.storage, self.order = api, storage, (order or {})
        self.shops = shops or []
        self.source_lat = self.source_lng = None
        self.source_address = ""
        self.map_pick_target = "destination"
        self.selected_shop = None
        self.destination_lat = None
        self.destination_lng = None
        self.selected_address = ""
        self.calc_result = None
        self.payment_url = None
        self.map_loaded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Калькулятор доставки")
        title.setStyleSheet("font-size:18pt;font-weight:700;color:#fff;")
        subtitle = QLabel("Самостоятельный расчёт маршрута по тарифам выбранного заведения. Заказ не создаётся.")
        subtitle.setObjectName("muted")
        title_box.addWidget(title); title_box.addWidget(subtitle)
        header.addLayout(title_box); header.addStretch()
        self.map_status = QLabel("Загрузка карты…")
        self.map_status.setObjectName("muted")
        header.addWidget(self.map_status)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        map_panel = QFrame()
        map_panel.setObjectName("logPanel")
        map_layout = QVBoxLayout(map_panel)
        map_layout.setContentsMargins(6, 6, 6, 6)
        map_title = QLabel("Карта маршрута")
        map_title.setStyleSheet("font-weight:700;color:#cbd5e1;padding:4px;")
        map_layout.addWidget(map_title)
        self.map_view = QWebEngineView()
        web_settings = self.map_view.settings()
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.map_view.loadFinished.connect(self._on_map_document_loaded)
        map_layout.addWidget(self.map_view, 1)
        map_legend = QLabel("🔵 Отправление     🔴 Назначение · Выберите точку кликом по карте")
        map_legend.setObjectName("muted")
        map_layout.addWidget(map_legend)
        splitter.addWidget(map_panel)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_panel = QWidget()
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(8, 4, 8, 4)
        right.setSpacing(9)

        shop_box = QGroupBox("Заведение и тариф")
        shop_form = QFormLayout(shop_box)
        self.shop_combo = QComboBox()
        self.shop_combo.setMinimumHeight(36)
        self.shop_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.shop_combo.currentIndexChanged.connect(self.on_shop_changed)
        shop_row = QHBoxLayout()
        shop_row.addWidget(self.shop_combo, 1)
        self.refresh_shops_btn = QPushButton("Обновить")
        self.refresh_shops_btn.setObjectName("secondary")
        self.refresh_shops_btn.clicked.connect(self.refresh_shops)
        shop_row.addWidget(self.refresh_shops_btn)
        shop_form.addRow("Заведение", shop_row)
        self.shops_status_label = QLabel("Загрузка списка заведений…")
        self.shops_status_label.setObjectName("muted")
        self.shops_status_label.setWordWrap(True)
        shop_form.addRow("Доступ", self.shops_status_label)
        self.shop_coords_hint = QLabel("Координаты заведения не загружены")
        self.shop_coords_hint.setObjectName("muted")
        shop_form.addRow("Координаты", self.shop_coords_hint)
        right.addWidget(shop_box)

        origin_box = QGroupBox("Откуда")
        origin_layout = QVBoxLayout(origin_box)
        origin_row = QHBoxLayout()
        self.origin_search = QLineEdit()
        self.origin_search.setPlaceholderText("Адрес отправления / заведения")
        self.origin_search.returnPressed.connect(self.search_origin_address)
        self.origin_search_btn = QPushButton("Найти")
        self.origin_search_btn.setObjectName("secondary")
        self.origin_search_btn.clicked.connect(self.search_origin_address)
        origin_row.addWidget(self.origin_search, 1); origin_row.addWidget(self.origin_search_btn)
        origin_layout.addLayout(origin_row)
        self.origin_coords_label = QLabel("Будут использованы координаты выбранного заведения; точку можно изменить на карте")
        self.origin_coords_label.setObjectName("muted"); self.origin_coords_label.setWordWrap(True)
        origin_layout.addWidget(self.origin_coords_label)
        right.addWidget(origin_box)

        address_box = QGroupBox("Куда")
        address_layout = QVBoxLayout(address_box)
        search_row = QHBoxLayout()
        self.address_search = QLineEdit()
        self.address_search.setPlaceholderText("Город, улица, дом или адрес доставки")
        self.address_search.returnPressed.connect(self.search_address)
        self.search_btn = QPushButton("Найти")
        self.search_btn.clicked.connect(self.search_address)
        search_row.addWidget(self.address_search, 1); search_row.addWidget(self.search_btn)
        self.geo_btn = QPushButton("Моё местоположение")
        self.geo_btn.setObjectName("secondary")
        self.geo_btn.clicked.connect(self.use_my_location)
        search_row.addWidget(self.geo_btn)
        address_layout.addLayout(search_row)
        pick_row = QHBoxLayout()
        pick_row.addWidget(QLabel("Клик по карте задаёт:"))
        self.map_pick_combo = QComboBox()
        self.map_pick_combo.addItem("Точку назначения", "destination")
        self.map_pick_combo.addItem("Точку отправления", "origin")
        self.map_pick_combo.currentIndexChanged.connect(lambda _i: setattr(self, "map_pick_target", self.map_pick_combo.currentData()))
        pick_row.addWidget(self.map_pick_combo); pick_row.addStretch()
        address_layout.addLayout(pick_row)
        self.selected_address_label = QLabel("Точка назначения не выбрана")
        self.selected_address_label.setObjectName("muted"); self.selected_address_label.setWordWrap(True)
        address_layout.addWidget(self.selected_address_label)
        right.addWidget(address_box)

        calc_row = QHBoxLayout()
        self.calculate_btn = QPushButton("Рассчитать стоимость")
        self.calculate_btn.setMinimumHeight(42)
        self.calculate_btn.clicked.connect(self.calculate_delivery)
        calc_row.addWidget(self.calculate_btn)
        self.result_label = QLabel("Укажите обе точки и выполните расчёт.")
        self.result_label.setObjectName("muted"); self.result_label.setWordWrap(True)
        calc_row.addWidget(self.result_label, 1)
        right.addLayout(calc_row)

        self.breakdown_box = QGroupBox("Результат расчёта")
        breakdown = QFormLayout(self.breakdown_box)
        self.distance_value = QLabel("—"); self.price_value = QLabel("—")
        self.zone_value = QLabel("—"); self.rate_value = QLabel("—")
        self.distance_cost_value = QLabel("—"); self.base_value = QLabel("—")
        self.outside_value = QLabel("—")
        for label in (self.price_value, self.distance_value):
            label.setStyleSheet("font-size:14pt;font-weight:700;color:#6ee7b7;")
        breakdown.addRow("Расстояние", self.distance_value)
        breakdown.addRow("Стоимость доставки", self.price_value)
        breakdown.addRow("Тарифная зона", self.zone_value)
        breakdown.addRow("Базовая стоимость зоны", self.base_value)
        breakdown.addRow("Тариф за километр", self.rate_value)
        breakdown.addRow("Стоимость расстояния", self.distance_cost_value)
        breakdown.addRow("За пределами зон", self.outside_value)
        self.breakdown_box.setVisible(False)
        right.addWidget(self.breakdown_box)

        self.payment_box = QGroupBox("Оплата доставки")
        payment_layout = QHBoxLayout(self.payment_box)
        self.payment_btn = QPushButton("Сгенерировать ссылку на оплату")
        self.payment_btn.clicked.connect(self.generate_payment_link)
        payment_layout.addWidget(self.payment_btn)
        self.qr_label = QLabel(); self.qr_label.setFixedSize(120, 120)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet("background:#fff;border-radius:8px;"); self.qr_label.setVisible(False)
        payment_layout.addWidget(self.qr_label)
        payment_right = QVBoxLayout()
        self.payment_link = QLineEdit(); self.payment_link.setReadOnly(True)
        self.payment_link.setPlaceholderText("Ссылка появится после генерации")
        payment_right.addWidget(self.payment_link)
        self.copy_payment_btn = QPushButton("Копировать ссылку")
        self.copy_payment_btn.setObjectName("secondary")
        self.copy_payment_btn.clicked.connect(self.copy_payment_link)
        self.copy_payment_btn.setEnabled(False)
        payment_right.addWidget(self.copy_payment_btn)
        payment_layout.addLayout(payment_right, 1)
        self.payment_box.setVisible(False)
        right.addWidget(self.payment_box)

        log_box = QGroupBox("Журнал обмена с сервером")
        log_layout = QVBoxLayout(log_box)
        self.api_log = QTextEdit()
        self.api_log.setReadOnly(True)
        self.api_log.setMinimumHeight(150)
        self.api_log.setMaximumHeight(230)
        self.api_log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.api_log.setStyleSheet("font-family:Consolas;font-size:8pt;background:#09111d;color:#dbeafe;")
        self.api_log.setPlaceholderText("Здесь появятся URL, параметры запроса, HTTP-ответ и ошибки расчёта.")
        log_layout.addWidget(self.api_log)
        log_actions = QHBoxLayout()
        clear_log = QPushButton("Очистить журнал"); clear_log.setObjectName("secondary")
        clear_log.clicked.connect(self.api_log.clear)
        log_actions.addStretch(); log_actions.addWidget(clear_log)
        log_layout.addLayout(log_actions)
        api_log_page = QWidget()
        api_log_layout = QVBoxLayout(api_log_page)
        api_log_layout.addWidget(log_box, 1)

        right.addStretch()
        scroll.setWidget(right_panel)
        right_tabs = QTabWidget()
        right_tabs.addTab(scroll, "Расчёт")
        right_tabs.addTab(api_log_page, "Журнал API")
        splitter.addWidget(right_tabs)
        splitter.setStretchFactor(0, 5); splitter.setStretchFactor(1, 4)
        splitter.setSizes([650, 520])
        root.addWidget(splitter, 1)

        self.bridge = MapBridge()
        self.bridge.pointSelected.connect(self.on_map_point_selected)
        self.bridge.mapReady.connect(self.on_map_ready)
        self.channel = QWebChannel(self.map_view.page())
        self.channel.registerObject("bridge", self.bridge)
        self.map_view.page().setWebChannel(self.channel)
        self.map_view.page().featurePermissionRequested.connect(self.handle_feature_permission)
        self._populate_shops()
        self._load_map()
        if self.order.get("lat") is not None and self.order.get("lng") is not None:
            self.destination_lat = float(self.order["lat"])
            self.destination_lng = float(self.order["lng"])
            self.selected_address = self.order.get("address") or ""
            self.selected_address_label.setText(self.selected_address or "Координаты заказа")
            self.map_status.setText("Используются координаты из заказа. Можно выбрать другую точку.")
            if self.selected_address:
                self.address_search.setText(self.selected_address)

    def log_api(self, title, payload=None, level="INFO"):
        from datetime import datetime
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.api_log.append(f"[{stamp}] {level} · {title}")
        if payload is not None:
            try:
                rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            except Exception:
                rendered = str(payload)
            self.api_log.append(rendered)
        self.api_log.append("─" * 72)

    def set_shops(self, shops):
        self.shops = shops or []
        self._populate_shops()

    def refresh_shops(self):
        """Refresh the shop list through the owning MainWindow."""
        host = self.window()
        loader = getattr(host, "_load_calculator_shops", None)
        if not callable(loader):
            self.log_api(
                "Не найден обработчик обновления списка заведений",
                {"widget": type(self).__name__, "window": type(host).__name__},
                "ERROR",
            )
            self.shops_status_label.setText("Не удалось найти обработчик загрузки заведений.")
            return

        self.refresh_shops_btn.setEnabled(False)
        self.refresh_shops_btn.setText("Загрузка…")
        try:
            shops = loader(show_error=True)
            self.log_api(
                "Обновление списка заведений завершено",
                {"count": len(shops or [])},
                "SUCCESS" if shops else "WARNING",
            )
        except Exception as exc:
            self.log_api("Ошибка обновления списка заведений", {"error": str(exc)}, "ERROR")
            self.shops_status_label.setText(f"Ошибка загрузки заведений: {exc}")
        finally:
            self.refresh_shops_btn.setEnabled(True)
            self.refresh_shops_btn.setText("Обновить")

    def set_order(self, order):
        self.order = order or {}
        lat, lng = self.order.get("lat"), self.order.get("lng")
        if lat is not None and lng is not None:
            try:
                self.destination_lat, self.destination_lng = float(lat), float(lng)
                self.selected_address = self.order.get("address") or ""
                self.address_search.setText(self.selected_address)
                self.selected_address_label.setText(self.selected_address or f"{self.destination_lat:.6f}, {self.destination_lng:.6f}")
                self._clear_calculation()
                if self.map_loaded:
                    self.map_view.page().runJavaScript(f"setDestination({self.destination_lng}, {self.destination_lat});")
            except (TypeError, ValueError):
                pass

    def on_tab_activated(self):
        if self.map_loaded:
            self.map_view.page().runJavaScript("setTimeout(function(){if(map){map.resize();}},150);")

    def _populate_shops(self):
        product_details = self.order.get("product_details") or {}
        products = product_details.get("products") or []
        preferred_ids = []
        for candidate in [self.order.get("tenant_id"), (self.order.get("tenant") or {}).get("id")]:
            if candidate is not None:
                try: preferred_ids.append(int(candidate))
                except (TypeError, ValueError): pass
        for product in products:
            try:
                pid = int(product.get("tenant_id"))
                if pid not in preferred_ids: preferred_ids.append(pid)
            except (TypeError, ValueError):
                pass

        by_id = {int(shop["id"]): shop for shop in self.shops if shop.get("id") is not None}
        self.shop_combo.setEnabled(bool(self.shops))
        self.shop_combo.clear()
        for shop in self.shops:
            label = shop.get("name") or f"Заведение {shop.get('id')}"
            self.shop_combo.addItem(label, shop)
        selected_index = -1
        for preferred in preferred_ids:
            if preferred in by_id:
                selected_index = next((i for i in range(self.shop_combo.count())
                                       if int((self.shop_combo.itemData(i) or {}).get("id", -1)) == preferred), -1)
                if selected_index >= 0: break
        if selected_index >= 0:
            self.shop_combo.setCurrentIndex(selected_index)
        elif self.shop_combo.count():
            self.shop_combo.setCurrentIndex(0)
        if not self.shops:
            self.shop_combo.addItem("Нет доступных заведений — нажмите «Обновить»", None)
            self.shop_combo.setEnabled(False)
            self.calculate_btn.setEnabled(False)
            self.shops_status_label.setText("Сервер не вернул доступные заведения. Обновите список или проверьте журнал API.")
            self.shop_coords_hint.setText("Нет данных о координатах")
        else:
            self.shop_combo.setEnabled(True)
            self.calculate_btn.setEnabled(True)
            self.shops_status_label.setText(f"Доступно заведений: {len(self.shops)}")

    @staticmethod
    def _parse_coords(value):
        if not value:
            return None
        try:
            if isinstance(value, str):
                parts = [p.strip() for p in value.split(",")]
                if len(parts) >= 2:
                    lat, lng = float(parts[0]), float(parts[1])
                else:
                    parsed = json.loads(value)
                    return DeliveryCalculatorWidget._parse_coords(parsed)
            elif isinstance(value, (list, tuple)) and len(value) >= 2:
                lat, lng = float(value[0]), float(value[1])
            elif isinstance(value, dict):
                lat = float(value.get("lat"))
                lng = float(value.get("lng", value.get("lon")))
            else:
                return None
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return None

    def _current_shop(self):
        return self.shop_combo.currentData()

    def on_shop_changed(self, _index):
        shop = self._current_shop()
        self.selected_shop = shop
        coords = self._parse_coords((shop or {}).get("shop_coords"))
        self.source_lat, self.source_lng = coords if coords else (None, None)
        self.source_address = (shop or {}).get("address") or ""
        self.origin_search.setText(self.source_address)
        if coords:
            lat, lng = coords
            self.shop_coords_hint.setText(f"{lat:.6f}, {lng:.6f}")
            self.origin_coords_label.setText(f"Координаты отправления: {lat:.6f}, {lng:.6f}. Можно указать другой адрес или выбрать точку на карте.")
            self.calculate_btn.setEnabled(True)
            if self.map_loaded:
                self.map_view.page().runJavaScript(f"setShopMarker({lng}, {lat}, true);")
        else:
            self.shop_coords_hint.setText("Координаты не указаны в настройках заведения")
            self.calculate_btn.setEnabled(False)
            if self.map_loaded:
                self.map_view.page().runJavaScript("setShopMarker(null, null, false);")
        self._clear_calculation()
        if self.map_loaded and coords:
            lat, lng = coords
            self.map_view.page().runJavaScript(f"flyToPoint({lng}, {lat}, 13);")

    def _load_map(self):
        shop = self._current_shop() or {}
        shop_coords = self._parse_coords(shop.get("shop_coords"))
        order_coords = None
        if self.order.get("lat") is not None and self.order.get("lng") is not None:
            try: order_coords = (float(self.order["lat"]), float(self.order["lng"]))
            except (TypeError, ValueError): pass
        center = shop_coords or order_coords
        if center:
            lat, lng = center
            center_json = json.dumps([lng, lat])
            zoom = 13
        else:
            center_json = json.dumps([0, 20])
            zoom = 2
        map_key = (shop or {}).get("map_tiler") or self.storage.get("map_tiler_key", self.MAPTILER_DEFAULT_KEY)
        html_doc = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<style>
html,body,#map{height:100%;width:100%;margin:0;background:#0d1726;overflow:hidden}
.maplibregl-ctrl-group{border-radius:9px!important;overflow:hidden}
.shop-pin,.delivery-pin{width:34px;height:34px;border:2px solid white;border-radius:50% 50% 50% 0;transform:rotate(-45deg);box-shadow:0 3px 12px #0006}
.shop-pin{background:#2563eb}.delivery-pin{background:#ef4444}
#hint{position:absolute;bottom:12px;left:50%;transform:translateX(-50%);z-index:3;background:#fff;color:#334155;padding:7px 13px;border-radius:18px;font:12px Segoe UI;white-space:nowrap;box-shadow:0 2px 9px #0003;max-width:90%;overflow:hidden;text-overflow:ellipsis}
#map-error{display:none;position:absolute;inset:12px 12px auto 12px;z-index:10;background:#3b1820;color:#ffe4e6;border:1px solid #9f3447;border-radius:10px;padding:12px;font:13px Segoe UI;white-space:normal;box-shadow:0 4px 18px #0007}
#map-error button{margin-left:8px;padding:5px 10px;border:0;border-radius:6px;background:#ef4444;color:white;cursor:pointer}
</style></head><body><div id="map"></div><div id="hint">Загрузка карты…</div><div id="map-error"></div>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
let bridge=null, map=null, shopMarker=null, deliveryMarker=null, styleFallbackUsed=false, mapReady=false;
window.addEventListener('error',function(e){if(!mapReady)showMapError('Ошибка JavaScript карты: '+(e.message||'неизвестная ошибка'),retryMap);});
function showMapError(message, retry){
  const box=document.getElementById('map-error'); box.style.display='block';
  box.textContent=message;
  if(retry){const b=document.createElement('button');b.textContent='Повторить';b.onclick=retry;box.appendChild(b);}
  document.getElementById('hint').textContent='Карта не загрузилась';
}
function hideMapError(){document.getElementById('map-error').style.display='none';}
function loadMapLibre(){
  if(window.maplibregl){initMap();return;}
  const sources=[
    'https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.js',
    'https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js'
  ];
  let index=0;
  function next(){
    if(index>=sources.length){showMapError('Не удалось загрузить библиотеку карты. Проверьте подключение к интернету или доступ к CDN.');return;}
    const script=document.createElement('script');script.src=sources[index++];script.onload=()=>{
      if(window.maplibregl)initMap();else next();
    };script.onerror=next;document.head.appendChild(script);
  }
  next();
}
function markerElement(cls){let el=document.createElement('div');el.className=cls;return el;}
function initMap(){
  try{
    if(!window.maplibregl){showMapError('Библиотека MapLibre недоступна.');return;}
    map=new maplibregl.Map({container:'map',style:'https://api.maptiler.com/maps/streets/style.json?key=__MAP_KEY__',center:__CENTER__,zoom:__ZOOM__,attributionControl:true});
    map.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right');
    map.on('load',function(){
      mapReady=true;hideMapError();document.getElementById('hint').textContent='Выберите тип точки выше и нажмите на карту';
      if(__SHOP_COORDS__){setShopMarker(__SHOP_COORDS__[1],__SHOP_COORDS__[0],false);}
      if(__DEST_COORDS__){setDeliveryMarker(__DEST_COORDS__[1],__DEST_COORDS__[0],false);}
      setTimeout(function(){try{map.resize();}catch(e){}},150);
      notifyBridgeReady();
    });
    map.on('error',function(e){
      const msg=(e&&e.error&&e.error.message)?e.error.message:'ошибка загрузки картографических данных';
      if(!mapReady && !styleFallbackUsed){
        styleFallbackUsed=true;
        document.getElementById('hint').textContent='Переключаемся на резервную карту…';
        try{map.setStyle('https://tiles.openfreemap.org/styles/liberty');return;}catch(_){ }
      }
      if(!mapReady)showMapError('Не удалось загрузить карту: '+msg, retryMap);
    });
    map.on('click',function(e){if(bridge)bridge.pointSelectedFromMap(e.lngLat.lat,e.lngLat.lng);});
    setTimeout(function(){if(!mapReady && !styleFallbackUsed){styleFallbackUsed=true;try{map.setStyle('https://tiles.openfreemap.org/styles/liberty');}catch(e){showMapError('Не удалось загрузить стиль карты: '+e.message,retryMap);}}},12000);
  }catch(e){showMapError('Ошибка запуска карты: '+e.message,retryMap);}
}
function retryMap(){
  hideMapError();document.getElementById('hint').textContent='Повторная загрузка карты…';
  mapReady=false;styleFallbackUsed=false;
  try{if(map){map.remove();map=null;}}catch(e){}
  loadMapLibre();
}
function setShopMarker(lng,lat,move){
  if(!map||!window.maplibregl)return;
  if(shopMarker){shopMarker.remove();shopMarker=null;}
  if(lng===null||lat===null)return;
  shopMarker=new maplibregl.Marker({element:markerElement('shop-pin'),anchor:'bottom'}).setLngLat([lng,lat]).addTo(map);
  if(move)map.flyTo({center:[lng,lat],zoom:13,duration:700});
}
function setDeliveryMarker(lng,lat,move){
  if(!map||!window.maplibregl)return;
  if(deliveryMarker){deliveryMarker.remove();deliveryMarker=null;}
  deliveryMarker=new maplibregl.Marker({element:markerElement('delivery-pin'),anchor:'bottom'}).setLngLat([lng,lat]).addTo(map);
  if(move)map.flyTo({center:[lng,lat],zoom:16,duration:700});
}
function setDestination(lng,lat){setDeliveryMarker(lng,lat,true);}
function flyToPoint(lng,lat,zoom){if(map)map.flyTo({center:[lng,lat],zoom:zoom||14,duration:700});}
function locateMe(){
  if(!navigator.geolocation){alert('Геолокация не поддерживается');return;}
  navigator.geolocation.getCurrentPosition(function(p){if(bridge)bridge.pointSelectedFromMap(p.coords.latitude,p.coords.longitude);},function(e){alert('Не удалось определить местоположение: '+e.message);},{enableHighAccuracy:true,timeout:10000});
}
let bridgeConnected=false;
function notifyBridgeReady(){if(bridge && mapReady){try{bridge.readyFromMap();}catch(e){console.warn('Qt bridge callback failed',e);}}}
function connectQtBridge(attempt){
  attempt=attempt||0;
  if(bridgeConnected)return;
  if(window.QWebChannel && window.qt && qt.webChannelTransport){
    try{
      new QWebChannel(qt.webChannelTransport,function(channel){
        bridge=channel.objects.bridge;bridgeConnected=true;notifyBridgeReady();
      });
      return;
    }catch(e){console.warn('QWebChannel init delayed',e);}
  }
  if(attempt<100){setTimeout(function(){connectQtBridge(attempt+1);},100);}
  else{showMapError('Не удалось подключить интерфейс карты к приложению Qt. Нажмите «Повторить».',retryMap);}
}
// Инициализируем карту независимо от готовности Qt bridge: загрузка карты не должна
// зависеть от момента появления qwebchannel.js / qt.webChannelTransport.
setTimeout(loadMapLibre,0);
connectQtBridge(0);
</script></body></html>"""
        html_doc = html_doc.replace("__MAP_KEY__", str(map_key))
        html_doc = html_doc.replace("__CENTER__", center_json).replace("__ZOOM__", str(zoom))
        html_doc = html_doc.replace("__SHOP_COORDS__", json.dumps(list(shop_coords) if shop_coords else None))
        html_doc = html_doc.replace("__DEST_COORDS__", json.dumps(list(order_coords) if order_coords else None))
        self.map_view.setHtml(html_doc, QUrl("https://localhost/"))

    def _on_map_document_loaded(self, ok):
        if not ok:
            self.map_status.setText("Не удалось открыть страницу карты. Проверьте компоненты Qt WebEngine.")
            return
        # Qt WebEngine иногда сообщает loadFinished раньше окончательного layout.
        QTimer.singleShot(250, lambda: self.map_view.page().runJavaScript("if(window.map){map.resize();}"))

    def on_map_ready(self):
        self.map_loaded = True
        shop = self._current_shop() or {}
        coords = (self.source_lat, self.source_lng) if self.source_lat is not None else self._parse_coords(shop.get("shop_coords"))
        if coords:
            lat, lng = coords
            self.source_lat, self.source_lng = lat, lng
            self.map_view.page().runJavaScript(f"setShopMarker({lng}, {lat}, false);")
            self.map_status.setText("Синяя метка — отправление, красная — назначение. Выберите тип точки и кликните по карте.")
        else:
            self.map_status.setText("У заведения нет координат. Добавьте shop_coords в настройках Tenant, чтобы расчёт был доступен.")
        if self.destination_lat is not None and self.destination_lng is not None:
            self.map_view.page().runJavaScript(f"setDestination({self.destination_lng}, {self.destination_lat});")

    def handle_feature_permission(self, origin, feature):
        if feature == QWebEnginePage.Feature.Geolocation:
            self.map_view.page().setFeaturePermission(
                origin, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
            )

    def on_map_point_selected(self, lat, lng):
        lat, lng = float(lat), float(lng)
        self._clear_calculation()
        if self.map_pick_target == "origin":
            self.source_lat, self.source_lng = lat, lng
            self.calculate_btn.setEnabled(True)
            self.map_view.page().runJavaScript(f"setShopMarker({lng}, {lat}, true);")
            self.origin_coords_label.setText(f"Точка отправления: {lat:.6f}, {lng:.6f}. Определяем адрес…")
            self.map_status.setText("Выбрана точка отправления. Определяем адрес…")
            self._reverse_geocode(lat, lng, "origin")
        else:
            self.destination_lat, self.destination_lng = lat, lng
            self.map_view.page().runJavaScript(f"setDestination({lng}, {lat});")
            self.map_status.setText(f"Выбраны координаты назначения: {lat:.6f}, {lng:.6f}. Определяем адрес…")
            self._reverse_geocode(lat, lng, "destination")

    def _reverse_geocode(self, lat, lng, target="destination"):
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"format":"jsonv2","lat":lat,"lon":lng,"addressdetails":1},
                headers={"User-Agent":"CourierDesktop/1.0 (delivery address picker)"},
                timeout=12
            )
            response.raise_for_status()
            data = response.json()
            addr = data.get("address") or {}
            city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or ""
            road = addr.get("road") or addr.get("pedestrian") or addr.get("residential") or ""
            house = addr.get("house_number") or ""
            formatted = ", ".join(part for part in [city, road, house] if part)
            formatted = formatted or data.get("display_name") or f"{lat:.6f}, {lng:.6f}"
            if target == "origin":
                self.source_address = formatted; self.origin_search.setText(formatted)
                self.origin_coords_label.setText(f"Отправление: {formatted} · {lat:.6f}, {lng:.6f}")
            else:
                self.selected_address = formatted; self.address_search.setText(formatted)
                self.selected_address_label.setText(formatted); self.map_status.setText("Точка назначения выбрана.")
        except Exception as exc:
            formatted = f"{lat:.6f}, {lng:.6f}"
            if target == "origin":
                self.source_address = formatted; self.origin_search.setText(formatted)
                self.origin_coords_label.setText(f"Отправление: {formatted}")
            else:
                self.selected_address = formatted; self.address_search.setText(formatted)
                self.selected_address_label.setText(formatted); self.map_status.setText(f"Координаты выбраны; адрес не определён: {exc}")

    def search_origin_address(self):
        query = self.origin_search.text().strip()
        if not query: return
        self.origin_search_btn.setEnabled(False); self.origin_search_btn.setText("Поиск…")
        try:
            response = requests.get("https://nominatim.openstreetmap.org/search",
                params={"format":"jsonv2","q":query,"addressdetails":1,"limit":1},
                headers={"User-Agent":"CourierDesktop/1.0 (delivery address picker)"}, timeout=12)
            response.raise_for_status(); results = response.json()
            if not results:
                QMessageBox.information(self, "Адрес не найден", "Уточните адрес отправления и попробуйте снова."); return
            item = results[0]; self.source_lat=float(item["lat"]); self.source_lng=float(item["lon"])
            addr=item.get("address") or {}; city=addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or ""
            road=addr.get("road") or addr.get("pedestrian") or addr.get("residential") or ""; house=addr.get("house_number") or ""
            self.source_address=", ".join(x for x in [city,road,house] if x) or item.get("display_name",query)
            self.calculate_btn.setEnabled(True)
            self.origin_search.setText(self.source_address)
            self.origin_coords_label.setText(f"Отправление: {self.source_address} · {self.source_lat:.6f}, {self.source_lng:.6f}")
            self.map_status.setText("Адрес отправления найден.")
            self.log_api("Геокодирование адреса отправления", {"query": query, "formatted_address": self.source_address, "lat": self.source_lat, "lng": self.source_lng})
            self._clear_calculation()
            if self.map_loaded: self.map_view.page().runJavaScript(f"setShopMarker({self.source_lng}, {self.source_lat}, true);")
        except Exception as exc: QMessageBox.warning(self,"Ошибка поиска адреса",str(exc))
        finally: self.origin_search_btn.setEnabled(True); self.origin_search_btn.setText("Найти отправление")

    def search_address(self):
        query = self.address_search.text().strip()
        if not query:
            return
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Поиск…")
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"format":"jsonv2","q":query,"addressdetails":1,"limit":1},
                headers={"User-Agent":"CourierDesktop/1.0 (delivery address picker)"},
                timeout=12
            )
            response.raise_for_status()
            data = response.json()
            if not data:
                QMessageBox.information(self, "Адрес не найден", "Уточните адрес и попробуйте снова.")
                return
            item = data[0]
            lat, lng = float(item["lat"]), float(item["lon"])
            addr = item.get("address") or {}
            city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or ""
            road = addr.get("road") or addr.get("pedestrian") or addr.get("residential") or ""
            house = addr.get("house_number") or ""
            self.selected_address = ", ".join(part for part in [city, road, house] if part) or item.get("display_name", query)
            self.address_search.setText(self.selected_address)
            self.destination_lat, self.destination_lng = lat, lng
            self.selected_address_label.setText(self.selected_address)
            self._clear_calculation()
            self.map_view.page().runJavaScript(f"setDestination({lng}, {lat});")
            self.map_status.setText(f"Адрес найден: {lat:.6f}, {lng:.6f}")
            self.log_api("Геокодирование адреса назначения", {"query": query, "formatted_address": self.selected_address, "lat": lat, "lng": lng})
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка поиска", str(exc))
        finally:
            self.search_btn.setEnabled(True)
            self.search_btn.setText("Найти адрес")

    def use_my_location(self):
        if self.map_loaded:
            self.map_view.page().runJavaScript("locateMe();")
        else:
            QMessageBox.information(self, "Карта", "Карта ещё загружается.")

    def _clear_calculation(self):
        self.calc_result = None
        self.payment_url = None
        self.breakdown_box.setVisible(False)
        self.payment_box.setVisible(False)

    def calculate_delivery(self):
        shop = self._current_shop()
        if not shop:
            QMessageBox.warning(self, "Заведение", "Нет доступного заведения для расчёта.")
            return
        if self.source_lat is None or self.source_lng is None:
            QMessageBox.information(self, "Точка отправления", "Укажите адрес отправления или выберите точку на карте.")
            return
        if self.destination_lat is None or self.destination_lng is None:
            QMessageBox.information(self, "Точка доставки", "Выберите точку на карте или найдите адрес.")
            return
        if not self.selected_address and not self.address_search.text().strip():
            QMessageBox.information(self, "Адрес", "Укажите адрес доставки или выберите точку на карте.")
            return
        if not self.source_address:
            self.source_address = self.origin_search.text().strip() or f"{self.source_lat:.6f}, {self.source_lng:.6f}"
        if not self.selected_address:
            self.selected_address = self.address_search.text().strip() or f"{self.destination_lat:.6f}, {self.destination_lng:.6f}"

        request_payload = {
            "shop_id": int(shop["id"]),
            "origin_lat": self.source_lat, "origin_lng": self.source_lng,
            "destination_lat": self.destination_lat, "destination_lng": self.destination_lng,
            "origin_address": self.source_address,
            "destination_address": self.selected_address,
        }
        self.log_api("POST /delivery-calculator/shops/{shop_id}/calculate · запрос", request_payload)
        self.calculate_btn.setEnabled(False)
        self.calculate_btn.setText("Рассчитываем…")
        try:
            result = self.api.calculate_delivery_route(
                request_payload["shop_id"], self.source_lat, self.source_lng,
                self.destination_lat, self.destination_lng,
                self.source_address, self.selected_address
            )
            self.log_api("Ответ API · расчёт доставки", result, "SUCCESS")
            self.calc_result = result.get("data") or {}
            breakdown = self.calc_result.get("breakdown") or {}
            self.distance_value.setText(f"{float(self.calc_result.get('distance_km', 0)):.2f} км")
            self.price_value.setText(f"{float(self.calc_result.get('delivery_price', 0)):,.2f} ₽".replace(",", " "))
            self.zone_value.setText(str(breakdown.get("zone_name", "—")))
            self.base_value.setText(f"{float(breakdown.get('base_price', 0)):.2f} ₽")
            self.rate_value.setText(f"{float(breakdown.get('price_per_km', 0)):.2f} ₽/км")
            self.distance_cost_value.setText(f"{float(breakdown.get('distance_cost', 0)):.2f} ₽")
            self.outside_value.setText("Да" if self.calc_result.get("is_outside_zones") else "Нет")
            self.breakdown_box.setVisible(True)
            self.payment_box.setVisible(True)
            self.result_label.setText("Расчёт выполнен сервером по настройкам выбранного заведения.")
            self.map_status.setText(f"Расчёт для {shop.get('name')} выполнен: {self.calc_result.get('distance_km')} км.")
        except Exception as exc:
            self.log_api("Ошибка расчёта доставки", {"error": str(exc), "request": request_payload}, "ERROR")
            self.map_status.setText(f"Ошибка расчёта: {exc}")
            QMessageBox.warning(self, "Не удалось рассчитать доставку", str(exc))
        finally:
            self.calculate_btn.setEnabled(True)
            self.calculate_btn.setText("Рассчитать стоимость")

    def generate_payment_link(self):
        if not self.calc_result:
            return
        shop = self._current_shop()
        self.payment_btn.setEnabled(False)
        self.payment_btn.setText("Создаём ссылку…")
        try:
            result = self.api.generate_shop_payment_link(
                int(shop["id"]), float(self.calc_result.get("delivery_price", 0)),
                f"Оплата доставки из {shop.get('name') or 'заведения'}"
            )
            self.payment_url = (result.get("data") or {}).get("url")
            if not self.payment_url:
                raise RuntimeError("Сервер не вернул платёжную ссылку.")
            self.payment_link.setText(self.payment_url)
            qr = qrcode.make(self.payment_url)
            buffer = io.BytesIO()
            qr.save(buffer, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue(), "PNG")
            self.qr_label.setPixmap(pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.qr_label.setVisible(True)
            self.copy_payment_btn.setEnabled(True)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка оплаты", str(exc))
        finally:
            self.payment_btn.setEnabled(True)
            self.payment_btn.setText("Сгенерировать ссылку на оплату")

    def copy_payment_link(self):
        if self.payment_url:
            QApplication.clipboard().setText(self.payment_url)
            self.copy_payment_btn.setText("Скопировано")
            QTimer.singleShot(1800, lambda: self.copy_payment_btn.setText("Копировать ссылку"))


class MainWindow(QMainWindow):
    def __init__(self, api, storage, user, identity):
        super().__init__()
        prepare_window(self, maximize=True)
        self.api, self.storage, self.user, self.identity = api, storage, user, identity
        self._new_order_ids = set()
        self.setWindowTitle("Courier Desktop")
        self.resize(1180, 780)
        self.asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"
        self.default_sound_path = self.asset_root / "new_order.wav"
        self.sound = QSoundEffect(self)
        self.sound.setVolume(.65)
        self._set_sound_source(self.storage.get("sound_path", str(self.default_sound_path)))

        central = QWidget(); self.setCentralWidget(central); root = QVBoxLayout(central); root.setContentsMargins(22,18,22,18); root.setSpacing(12)
        # Не позволяем сумме минимальных высот вложенных блоков превышать рабочую область экрана.
        root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setMinimumSize(900, 650)
        top = QHBoxLayout(); heading = QVBoxLayout()
        self.title = QLabel("Кабинет курьера"); self.title.setObjectName("title")
        self.subtitle = QLabel(f"{user.get('name','Курьер')} · {user.get('phone') or user.get('email') or ''}"); self.subtitle.setObjectName("muted")
        heading.addWidget(self.title); heading.addWidget(self.subtitle); top.addLayout(heading); top.addStretch()
        self.refresh_caption = QLabel("Обновление не запущено")
        self.refresh_caption.setObjectName("muted")
        top.addWidget(self.refresh_caption)
        calc_open = QPushButton("Калькулятор доставки")
        calc_open.setObjectName("secondary")
        calc_open.clicked.connect(self.show_delivery_calculator_tab)
        top.addWidget(calc_open)
        logout = QPushButton("Выйти"); logout.setObjectName("secondary"); logout.clicked.connect(self.logout); top.addWidget(logout)
        root.addLayout(top)

        self.refresh_progress = QProgressBar()
        self.refresh_progress.setTextVisible(False)
        self.refresh_progress.setFixedHeight(7)
        self.refresh_progress.setRange(0, 30)
        self.refresh_progress.setValue(0)
        self.refresh_progress.setStyleSheet(
            "QProgressBar{background:#1b2a40;border:0;border-radius:3px;}"
            "QProgressBar::chunk{background:#3b82f6;border-radius:3px;}"
        )
        root.addWidget(self.refresh_progress)
        self._refresh_elapsed = 0
        self._refresh_interval = 30
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self._tick_refresh_progress)
        # Статистика больше не занимает место над рабочими вкладками:
        # layout будет размещён на отдельной вкладке «Информация».
        self.metrics = QHBoxLayout()
        self.metric_labels = {}
        for key, caption in [("earned","Заработано за месяц"),("available","Доступные заказы"),("active","Мои текущие"),("completed","Завершённые")]:
            group = QGroupBox(caption); box=QVBoxLayout(group); val=QLabel("—"); val.setStyleSheet("font-size:22pt;font-weight:700;color:#fff"); box.addWidget(val); self.metrics.addWidget(group); self.metric_labels[key]=val
        self.tabs = QTabWidget(); root.addWidget(self.tabs,1)
        self.tables = {}
        for key, caption in [("available","Доступные"),("active","Мои текущие"),("completed","Завершённые")]:
            page=QWidget(); lay=QVBoxLayout(page)
            filters=QHBoxLayout(); start=QDateEdit(); start.setCalendarPopup(True); start.setDate(QDate.currentDate()); end=QDateEdit(); end.setCalendarPopup(True); end.setDate(QDate.currentDate())
            filters.addWidget(QLabel("С")); filters.addWidget(start); filters.addWidget(QLabel("По")); filters.addWidget(end)
            refresh=QPushButton("Обновить"); refresh.setObjectName("secondary"); refresh.clicked.connect(lambda _=False,k=key,s=start,e=end:self.load_orders(k,s.date().toString("yyyy-MM-dd"),e.date().toString("yyyy-MM-dd")))
            filters.addWidget(refresh); filters.addStretch(); lay.addLayout(filters)
            table=QTableWidget(0,7); table.setHorizontalHeaderLabels(["№","Заведение","Адрес","Получатель","Телефон","Сумма","Доставка"])
            table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch); table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setAlternatingRowColors(True)
            lay.addWidget(table); actions=QHBoxLayout(); actions.addStretch()
            if key=="available":
                edit=QPushButton("Изменить стоимость"); edit.setObjectName("secondary"); edit.clicked.connect(lambda _=False,t=table:self.edit_selected(t)); actions.addWidget(edit)
                accept=QPushButton("Принять выбранный заказ"); accept.clicked.connect(lambda _=False,t=table:self.accept_selected(t)); actions.addWidget(accept)
            elif key=="active":
                status=QComboBox(); status.addItem("Готовится",5); status.addItem("Готов к доставке",4); status.addItem("В доставке",1); actions.addWidget(status)
                change=QPushButton("Изменить статус"); change.clicked.connect(lambda _=False,t=table,c=status:self.change_selected(t,c.currentData())); actions.addWidget(change)
                done=QPushButton("Подтвердить доставку"); done.setObjectName("danger"); done.clicked.connect(lambda _=False,t=table:self.confirm_selected(t)); actions.addWidget(done)
            lay.addLayout(actions); self.tabs.addTab(page,caption); self.tables[key]=table
            table.cellClicked.connect(lambda row, col, t=table: self.show_order_details(t, row))

        self.delivery_calculator = DeliveryCalculatorWidget(self.api, self.storage, None, [], self)
        self.delivery_calculator_tab_index = self.tabs.addTab(self.delivery_calculator, "Калькулятор доставки")
        self.tabs.currentChanged.connect(self._on_main_tab_changed)

        # Отдельная вкладка с журналом освобождает место для рабочих таблиц.
        self.action_log = QTextEdit()
        self.action_log.setReadOnly(True)
        self.action_log.document().setMaximumBlockCount(1500)
        self.action_log.setPlaceholderText("Здесь отображаются действия, обновления, ответы API и ошибки.")
        self.action_log.setStyleSheet("font-family:Consolas;font-size:9pt;background:#09111d;color:#dbeafe;")
        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_layout.addWidget(self.action_log, 1)
        log_actions = QHBoxLayout()
        clear_log = QPushButton("Очистить журнал")
        clear_log.setObjectName("secondary")
        clear_log.clicked.connect(self.action_log.clear)
        log_actions.addStretch()
        log_actions.addWidget(clear_log)
        log_layout.addLayout(log_actions)
        self.tabs.addTab(log_page, "Журнал")

        info_page = QWidget()
        info_layout = QVBoxLayout(info_page)
        info_layout.setContentsMargins(14, 14, 14, 14)
        info_layout.addLayout(self.metrics)
        info_layout.addWidget(QLabel("Сводная информация по работе курьера обновляется вместе с данными панели."))
        info_layout.addStretch(1)
        self.tabs.addTab(info_page, "Информация")
        self.write_action_log("Рабочая панель открыта.", "success")

        # Вкладка настроек прокручивается целиком: элементы управления не сжимаются
        # при небольшом размере окна или масштабировании Windows.
        self.settings_page = QWidget()
        settings_page_layout = QVBoxLayout(self.settings_page)
        settings_page_layout.setContentsMargins(0, 0, 0, 0)
        settings_scroll = QScrollArea()
        settings_scroll.setObjectName("settingsScroll")
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        settings_content = QWidget()
        sl = QVBoxLayout(settings_content)
        sl.setContentsMargins(8, 8, 12, 8)
        sl.setSpacing(14)

        box = QGroupBox("Оповещения и обновление")
        form = QFormLayout(box)
        form.setContentsMargins(16, 22, 16, 16)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.auto = QCheckBox("Автоматически обновлять доступные заказы")
        self.auto.setMinimumHeight(34)
        self.sound_enabled = QCheckBox("Звуковое оповещение о новых заказах")
        self.sound_enabled.setMinimumHeight(34)
        self.interval = QSpinBox()
        self.interval.setRange(30, 3600)
        self.interval.setSuffix(" сек.")
        self.interval.setMinimumWidth(150)
        self.interval.setMinimumHeight(38)
        form.addRow(self.auto)
        form.addRow("Интервал обновления", self.interval)
        form.addRow(self.sound_enabled)

        sound_row = QHBoxLayout()
        sound_row.setSpacing(10)
        self.sound_path_label = QLabel("Звук по умолчанию")
        self.sound_path_label.setObjectName("muted")
        self.sound_path_label.setWordWrap(True)
        self.sound_path_label.setMinimumWidth(180)
        choose_sound = QPushButton("Выбрать WAV…")
        choose_sound.setObjectName("secondary")
        choose_sound.setMinimumWidth(145)
        choose_sound.setMinimumHeight(40)
        choose_sound.clicked.connect(self.choose_sound_file)
        test_sound = QPushButton("Проверить")
        test_sound.setMinimumWidth(110)
        test_sound.setMinimumHeight(40)
        test_sound.clicked.connect(self.test_sound)
        sound_row.addWidget(self.sound_path_label, 1)
        sound_row.addWidget(choose_sound, 0)
        sound_row.addWidget(test_sound, 0)
        form.addRow("Файл оповещения", sound_row)
        sl.addWidget(box)

        self.shops_list = QListWidget()
        self.shops_list.setMinimumHeight(190)
        self.shops_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        shops_box = QGroupBox("Магазины, от которых получать заказы")
        shops_l = QVBoxLayout(shops_box)
        shops_l.addWidget(self.shops_list)
        sl.addWidget(shops_box)

        save = QPushButton("Сохранить настройки")
        save.setMinimumHeight(44)
        save.setMinimumWidth(190)
        save.clicked.connect(self.save_settings)
        sl.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        sl.addStretch(1)

        settings_scroll.setWidget(settings_content)
        settings_page_layout.addWidget(settings_scroll)
        self.tabs.addTab(self.settings_page, "Настройки")
        self.statusBar().showMessage("Подключено")
        self.poller=None
        self.load_dashboard(); self.load_all_orders(); self.load_settings()
        self.start_poller()

    def show_error(self, exc): QMessageBox.warning(self,"Ошибка",str(exc))
    def load_dashboard(self):
        try:
            d=self.api.dashboard().get("data",{}).get("deliveryman",{})
            self.metric_labels["earned"].setText(f"{float(d.get('earned',0)):,.0f} ₽".replace(","," "))
            self.metric_labels["available"].setText(str(d.get("available_orders_count",0))); self.metric_labels["active"].setText(str(d.get("active_orders_count",0))); self.metric_labels["completed"].setText(str(d.get("completed_orders_count",0)))
        except Exception as exc:
            self.write_action_log(f"Ошибка обновления сводки: {exc}", "error")
            self.show_error(exc)
    def load_all_orders(self):
        today=date.today().isoformat()
        for key in self.tables: self.load_orders(key,today,today)
    def write_action_log(self, message, level="info"):
        colors = {"info": "#93c5fd", "success": "#6ee7b7", "warning": "#fcd34d", "error": "#fca5a5"}
        color = colors.get(level, colors["info"])
        stamp = QDateTime.currentDateTime().toString("HH:mm:ss")
        safe = html.escape(str(message)).replace("\n", "<br>")
        self.action_log.append(
            f'<span style="color:#64748b">[{stamp}]</span> '
            f'<span style="color:{color}">{safe}</span>'
        )
        bar = self.action_log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_sound_source(self, path):
        candidate = Path(path).expanduser() if path else self.default_sound_path
        if not candidate.exists():
            candidate = self.default_sound_path
            self.storage.set("sound_path", str(candidate))
        self.active_sound_path = candidate
        self.sound.setSource(QUrl.fromLocalFile(str(candidate)))
        if hasattr(self, "sound_path_label"):
            self.sound_path_label.setText(candidate.name if candidate == self.default_sound_path else str(candidate))

    def choose_sound_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите звук уведомления", str(Path.home()),
            "Аудиофайлы WAV (*.wav)"
        )
        if not path:
            return
        self._set_sound_source(path)
        self.storage.set("sound_path", path)
        self.write_action_log(f"Выбран файл звукового оповещения: {path}", "success")

    def test_sound(self):
        if not self.active_sound_path.exists():
            self.write_action_log("Файл звукового оповещения не найден.", "error")
            return
        self.sound.play()
        self.write_action_log(f"Тест звукового оповещения: {self.active_sound_path}", "info")

    def _tick_refresh_progress(self):
        if not self.auto.isChecked():
            self.refresh_progress.setValue(0)
            self.refresh_caption.setText("Автообновление выключено")
            return
        self._refresh_elapsed = min(self._refresh_elapsed + 1, self._refresh_interval)
        self.refresh_progress.setMaximum(self._refresh_interval)
        self.refresh_progress.setValue(self._refresh_elapsed)
        remaining = max(0, self._refresh_interval - self._refresh_elapsed)
        self.refresh_caption.setText(f"Следующее обновление через {remaining} сек.")

    def _reset_refresh_progress(self):
        self._refresh_elapsed = 0
        if hasattr(self, "refresh_progress"):
            self.refresh_progress.setValue(0)
            if self.auto.isChecked():
                self.refresh_caption.setText(f"Обновлено · интервал {self._refresh_interval} сек.")

    def _fill_orders_table(self, table, rows, highlight_ids=None):
        highlight_ids = highlight_ids or set()
        table.setRowCount(len(rows))
        for i, order in enumerate(rows):
            tenant = order.get("tenant_name") or (order.get("tenant") or {}).get("name") or "—"
            values = [order.get("id"), tenant, order.get("address"), order.get("receiver_name"),
                      order.get("receiver_phone"), order.get("summary_price", order.get("order_price", 0)),
                      order.get("delivery_price", 0)]
            is_new = order.get("id") is not None and int(order["id"]) in highlight_ids
            for j, value in enumerate(values):
                cell = QTableWidgetItem(str(value if value is not None else "—"))
                if is_new:
                    cell.setBackground(QBrush(QColor("#7f1d1d")))
                    cell.setForeground(QBrush(QColor("#fff1f2")))
                    cell.setToolTip("Новый заказ — поступил после предыдущего обновления")
                table.setItem(i, j, cell)
            table.item(i, 0).setData(Qt.UserRole, order)
        table.resizeRowsToContents()

    def load_orders(self, kind, date_from, date_to):
        self.write_action_log(f"Запрос списка «{kind}»: {date_from} — {date_to}")
        try:
            rows = self.api.orders(kind, date_from, date_to).get("data", [])
            if not isinstance(rows, list):
                raise RuntimeError("Сервер вернул некорректный формат списка заказов.")
            table = self.tables[kind]
            self._fill_orders_table(table, rows, self._new_order_ids if kind == "available" else set())
            self.write_action_log(f"Получено заказов в разделе «{kind}»: {len(rows)}", "success")
            if kind == "available":
                self._reset_refresh_progress()
        except Exception as exc:
            self.write_action_log(f"Ошибка загрузки «{kind}»: {exc}", "error")
            self.show_error(exc)


    @staticmethod
    def _money(value):
        try:
            return f"{float(value or 0):,.2f} ₽".replace(",", " ")
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def _order_status_label(status):
        return {
            0: "Новый заказ", 1: "В доставке", 2: "Завершён",
            3: "Отменён", 4: "Готов к доставке", 5: "Готовится"
        }.get(status, f"Статус {status}")

    def show_order_details(self, table, row):
        item = table.item(row, 0)
        if not item:
            return
        order = item.data(Qt.UserRole)
        if not isinstance(order, dict):
            return

        order_id = order.get("id", "—")
        payload = json.dumps(order, ensure_ascii=False, indent=2, default=str)
        stamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        self.write_action_log(f"Открыты детали заказа №{order_id}. JSON заказа добавлен в журнал.", "info")
        self.write_action_log(payload, "info")

        dialog = QDialog(self)
        prepare_window(dialog, maximize=False)
        dialog.setWindowTitle(f"Заказ №{order_id} — подробная информация")
        dialog.resize(1040, 780)
        dialog.setMinimumSize(850, 620)
        root = QVBoxLayout(dialog)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(f"Заказ №{order_id}")
        title.setStyleSheet("font-size:20pt;font-weight:700;color:#fff;")
        status = QLabel(self._order_status_label(order.get("status")))
        status.setStyleSheet("background:#233a59;color:#bfdbfe;padding:6px 11px;border-radius:9px;font-weight:700;")
        title_box.addWidget(title)
        title_box.addWidget(QLabel(f"Создан: {order.get('created_at') or '—'}"))
        top.addLayout(title_box)
        top.addStretch()
        top.addWidget(status)
        root.addLayout(top)

        tabs = QTabWidget()
        visual_tab = QWidget()
        visual_layout = QVBoxLayout(visual_tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)

        # Summary cards
        metrics = QGridLayout()
        metric_values = [
            ("Сумма товаров", self._money(order.get("order_price", order.get("summary_price")))),
            ("Доставка", self._money(order.get("delivery_price"))),
            ("Расстояние", f"{order.get('distance_km') or order.get('delivery_range') or '—'} км"),
            ("Итого", self._money(float(order.get("order_price", order.get("summary_price", 0)) or 0) + float(order.get("delivery_price", 0) or 0))),
        ]
        for index, (caption, value) in enumerate(metric_values):
            card = QFrame()
            card.setStyleSheet("QFrame{background:#17263b;border:1px solid #30425d;border-radius:12px;}")
            card_layout = QVBoxLayout(card)
            small = QLabel(caption)
            small.setObjectName("muted")
            big = QLabel(value)
            big.setStyleSheet("font-size:15pt;font-weight:700;color:#f8fafc;")
            card_layout.addWidget(small)
            card_layout.addWidget(big)
            metrics.addWidget(card, 0, index)
        content_layout.addLayout(metrics)

        customer_box = QGroupBox("Получатель и доставка")
        customer_form = QFormLayout(customer_box)
        customer_form.addRow("Получатель", QLabel(str(order.get("receiver_name") or "—")))
        customer_form.addRow("Телефон", QLabel(str(order.get("receiver_phone") or "—")))
        address_label = QLabel(str(order.get("address") or "Адрес не указан"))
        address_label.setWordWrap(True)
        customer_form.addRow("Адрес", address_label)
        customer_form.addRow("Координаты", QLabel(
            f"{order.get('lat') or '—'}, {order.get('lng') or '—'}"
        ))
        customer_form.addRow("Диалог", QLabel(str(order.get("dialog_id") or "—")))
        info = QLabel(str(order.get("info") or "Дополнительная информация отсутствует"))
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        customer_form.addRow("Примечания", info)
        content_layout.addWidget(customer_box)

        products_box = QGroupBox("Состав заказа")
        products_layout = QVBoxLayout(products_box)
        product_data = order.get("product_details") or {}
        products = product_data.get("products") or []
        source = product_data.get("from") or order.get("tenant_name") or "Источник не указан"
        products_layout.addWidget(QLabel(f"Источник заказа: {source}"))
        if products:
            product_table = QTableWidget(len(products), 5)
            product_table.setHorizontalHeaderLabels(["Товар", "Заведение", "Кол-во", "Цена за шт.", "Сумма"])
            product_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            product_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            product_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            for i, product in enumerate(products):
                name = product.get("name") or product.get("title") or "Товар"
                ingredients = product.get("ingredients") or []
                components = product.get("components") or []
                extras = []
                for ingredient in ingredients:
                    if isinstance(ingredient, dict):
                        extras.append(ingredient.get("name", ""))
                for component in components:
                    if isinstance(component, dict):
                        extras.append(component.get("name") or component.get("title") or "")
                comment = product.get("comment")
                if comment: extras.append(f"Комментарий: {comment}")
                if extras:
                    name += "\n" + ", ".join(x for x in extras if x)
                shop_name = product.get("tenant_name") or "—"
                count = product.get("count", 1)
                unit = product.get("unit_price", product.get("price", 0))
                total = product.get("price", float(unit or 0) * float(count or 1))
                values = [name, shop_name, str(count), self._money(unit), self._money(total)]
                for j, value in enumerate(values):
                    cell = QTableWidgetItem(str(value))
                    if j == 0: cell.setToolTip(str(value))
                    product_table.setItem(i, j, cell)
            product_table.resizeRowsToContents()
            product_table.setMinimumHeight(min(360, 70 + len(products) * 48))
            products_layout.addWidget(product_table)
        else:
            products_layout.addWidget(QLabel("Детализация товаров в ответе API отсутствует."))
        content_layout.addWidget(products_box)

        shop_groups = {}
        for product in products:
            shop_name = product.get("tenant_name") or "Без названия заведения"
            shop_groups.setdefault(shop_name, []).append(product)
        if len(shop_groups) > 1:
            group_box = QGroupBox("Заказ из нескольких заведений")
            group_layout = QVBoxLayout(group_box)
            for shop_name, rows in shop_groups.items():
                total_qty = sum(float(p.get("count") or 0) for p in rows)
                group_layout.addWidget(QLabel(f"• {shop_name}: {len(rows)} поз., {total_qty:g} шт."))
            content_layout.addWidget(group_box)

        content_layout.addStretch()
        scroll.setWidget(content)
        visual_layout.addWidget(scroll)
        calc_row = QHBoxLayout()
        calculate_btn = QPushButton("Рассчитать доставку на карте")
        calculate_btn.setMinimumHeight(42)
        calculate_btn.clicked.connect(lambda: (dialog.accept(), QTimer.singleShot(0, lambda: self.open_delivery_calculator(order))))
        calc_row.addWidget(calculate_btn)
        calc_row.addStretch()
        visual_layout.addLayout(calc_row)
        tabs.addTab(visual_tab, "Заказ")

        debug_tab = QWidget()
        debug_layout = QVBoxLayout(debug_tab)
        debug_caption = QLabel(f"Сырой ответ API · просмотр открыт {stamp}. Поля ниже соответствуют фактическому JSON.")
        debug_caption.setObjectName("muted")
        debug_layout.addWidget(debug_caption)
        debug_text = QTextEdit()
        debug_text.setReadOnly(True)
        debug_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        debug_text.setStyleSheet("font-family:Consolas;font-size:9pt;background:#09111d;color:#dbeafe;")
        debug_text.setPlainText(
            f"[{stamp}] Открыт заказ №{order_id}\n"
            f"[{stamp}] В ответе API {len(order)} полей.\n\n{payload}"
        )
        debug_layout.addWidget(debug_text, 1)
        tabs.addTab(debug_tab, "JSON и отладка")
        root.addWidget(tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close = QPushButton("Закрыть")
        close.clicked.connect(dialog.accept)
        footer.addWidget(close)
        root.addLayout(footer)
        dialog.exec()

    @staticmethod
    def _normalise_shops_payload(response):
        """Нормализует Laravel JSON, в том числе вложенные data/resource-обёртки."""
        meta = {}
        node = response
        # API может вернуть data.shops, data.data.shops или data.data как список.
        for _ in range(5):
            if isinstance(node, list):
                shops = node
                break
            if not isinstance(node, dict):
                shops = []
                break
            for key in ("is_restricted", "access_source", "assigned_ids", "selected_ids", "message"):
                if key in node:
                    meta[key] = node[key]
            if isinstance(node.get("shops"), list):
                shops = node["shops"]
                break
            if isinstance(node.get("items"), list):
                shops = node["items"]
                break
            if isinstance(node.get("data"), (dict, list)):
                node = node["data"]
                continue
            # Иногда коллекция сериализуется как объект с числовыми ключами.
            numeric_values = [v for k, v in node.items() if str(k).isdigit() and isinstance(v, dict)]
            if numeric_values and all(v.get("id") is not None for v in numeric_values):
                shops = numeric_values
            else:
                shops = []
            break
        else:
            shops = []
        clean = []
        seen = set()
        for shop in shops if isinstance(shops, list) else []:
            if not isinstance(shop, dict) or shop.get("id") is None:
                continue
            try:
                sid = int(shop["id"])
            except (TypeError, ValueError):
                continue
            if sid not in seen:
                clean.append(shop)
                seen.add(sid)
        return {"shops": clean, **meta}

    def _load_calculator_shops(self, show_error=False):
        cached = getattr(self, "shops_payload", {}) or {}
        response = None
        try:
            response = self.api.get_shops()
            payload = self._normalise_shops_payload(response)
            self.shops_payload = payload
            shops = payload.get("shops", [])
            diagnostic = {
                "success": response.get("success") if isinstance(response, dict) else None,
                "count": len(shops),
                "is_restricted": payload.get("is_restricted"),
                "access_source": payload.get("access_source"),
                "assigned_ids": payload.get("assigned_ids"),
                "selected_ids": payload.get("selected_ids"),
                "response": response,
            }
            self.write_action_log(
                "Ответ API списка заведений: " + json.dumps(diagnostic, ensure_ascii=False, default=str),
                "success" if shops else "warning"
            )
            if hasattr(self, "delivery_calculator"):
                self.delivery_calculator.log_api("Ответ API списка заведений", diagnostic, "SUCCESS" if shops else "WARNING")
            if not shops:
                self.write_action_log(
                    "Сервер ответил успешно, но список заведений пуст. Проверьте meta пользователя, права и фильтр is_active в Tenant.",
                    "warning"
                )
        except Exception as exc:
            shops = cached.get("shops", [])
            self.write_action_log(f"Ошибка обновления списка заведений: {exc}", "error")
            if not shops and show_error:
                QMessageBox.warning(self, "Калькулятор доставки", f"Не удалось загрузить заведения: {exc}")
        self.delivery_calculator.set_shops(shops)
        return shops

    def show_delivery_calculator_tab(self):
        # Даже при пустом ответе открываем вкладку: пользователь увидит диагностику
        # и сможет повторить загрузку кнопкой рядом с выбором заведения.
        self._load_calculator_shops(show_error=False)
        self.tabs.setCurrentIndex(self.delivery_calculator_tab_index)
        self.delivery_calculator.on_tab_activated()

    def _on_main_tab_changed(self, index):
        if index == getattr(self, "delivery_calculator_tab_index", -1):
            self.delivery_calculator.on_tab_activated()

    def open_standalone_delivery_calculator(self):
        self.show_delivery_calculator_tab()

    def open_delivery_calculator(self, order, parent_dialog=None):
        shops = self._load_calculator_shops()
        if not shops:
            return
        self.delivery_calculator.set_order(order)
        self.tabs.setCurrentIndex(self.delivery_calculator_tab_index)
        self.delivery_calculator.on_tab_activated()
        self.write_action_log(f"Открыта вкладка расчёта доставки из карточки заказа №{order.get('id')}.")

    def selected_order(self, table):
        row=table.currentRow()
        return table.item(row,0).data(Qt.UserRole) if row>=0 and table.item(row,0) else None
    def accept_selected(self, table):
        o=self.selected_order(table)
        if not o: return QMessageBox.information(self,"Заказ","Выберите заказ в таблице")
        try:
            self.write_action_log(f"Принят заказ №{o['id']}.")
            self.api.accept_order(o["id"]); self.load_dashboard(); self.load_all_orders(); self.tabs.setCurrentIndex(1)
            self.write_action_log(f"Заказ №{o['id']} принят.", "success")
        except Exception as exc:
            self.write_action_log(f"Ошибка принятия заказа №{o['id']}: {exc}", "error")
            self.show_error(exc)
    def edit_selected(self, table):
        o=self.selected_order(table)
        if not o: return QMessageBox.information(self,"Заказ","Выберите заказ в таблице")
        dialog=QDialog(self); prepare_window(dialog, maximize=False); dialog.setWindowTitle(f"Заказ №{o['id']} — стоимость доставки"); dialog.resize(380,220)
        layout=QVBoxLayout(dialog); form=QFormLayout()
        distance=QDoubleSpinBox(); distance.setRange(0,10000); distance.setDecimals(2); distance.setValue(float(o.get("distance_km") or 0)); distance.setSuffix(" км")
        price=QDoubleSpinBox(); price.setRange(0,10000000); price.setDecimals(2); price.setValue(float(o.get("delivery_price") or 0)); price.setSuffix(" ₽")
        form.addRow("Расстояние",distance); form.addRow("Стоимость доставки",price); layout.addLayout(form)
        save=QPushButton("Сохранить"); cancel=QPushButton("Отмена"); row=QHBoxLayout(); row.addWidget(cancel); row.addWidget(save); layout.addLayout(row)
        cancel.clicked.connect(dialog.reject)
        def submit():
            try:
                self.write_action_log(f"Изменение параметров заказа №{o['id']}: расстояние {distance.value()} км, доставка {price.value()} ₽")
                self.api.update_order_details(o["id"],distance.value(),price.value()); dialog.accept(); self.load_all_orders(); self.load_dashboard()
                self.write_action_log(f"Параметры заказа №{o['id']} сохранены.", "success")
            except Exception as exc:
                self.write_action_log(f"Ошибка изменения заказа №{o['id']}: {exc}", "error")
                self.show_error(exc)
        save.clicked.connect(submit); dialog.exec()
    def change_selected(self, table, status):
        o=self.selected_order(table)
        if not o: return QMessageBox.information(self,"Заказ","Выберите заказ в таблице")
        try:
            self.write_action_log(f"Изменение статуса заказа №{o['id']} на {int(status)}")
            self.api.change_status(o["id"],int(status)); self.load_dashboard(); self.load_all_orders()
            self.write_action_log(f"Статус заказа №{o['id']} изменён.", "success")
        except Exception as exc:
            self.write_action_log(f"Ошибка смены статуса заказа №{o['id']}: {exc}", "error")
            self.show_error(exc)
    def confirm_selected(self, table):
        o=self.selected_order(table)
        if not o: return QMessageBox.information(self,"Заказ","Выберите заказ в таблице")
        if QMessageBox.question(self,"Подтверждение",f"Подтвердить доставку заказа №{o['id']}?")!=QMessageBox.Yes: return
        try:
            self.write_action_log(f"Подтверждение доставки заказа №{o['id']}")
            self.api.confirm_delivery(o["id"]); self.load_dashboard(); self.load_all_orders()
            self.write_action_log(f"Доставка заказа №{o['id']} подтверждена.", "success")
        except Exception as exc:
            self.write_action_log(f"Ошибка подтверждения заказа №{o['id']}: {exc}", "error")
            self.show_error(exc)
    def _save_local_preferences(self):
        self.storage.set("auto_refresh", str(self.auto.isChecked()).lower())
        self.storage.set("refresh_interval", str(self.interval.value()))
        self.storage.set("sound_enabled", str(self.sound_enabled.isChecked()).lower())
        self.storage.set("sound_path", str(self.active_sound_path))
        self._refresh_interval = self.interval.value()
        self.refresh_progress.setMaximum(self._refresh_interval)

    def load_settings(self):
        try:
            remote = self.api.get_settings().get("data", {})
            # Локальные значения из INI имеют приоритет: настройки не теряются при перезапуске.
            auto_default = str(remote.get("auto_refresh", False)).lower()
            sound_default = str(remote.get("sound_enabled", True)).lower()
            self.auto.setChecked(self.storage.get("auto_refresh", auto_default) == "true")
            self.interval.setValue(max(30, int(self.storage.get("refresh_interval", str(remote.get("refresh_interval", 30))))))
            self.sound_enabled.setChecked(self.storage.get("sound_enabled", sound_default) == "true")
            self._refresh_interval = self.interval.value()
            self.refresh_progress.setMaximum(self._refresh_interval)
            self.sound_path_label.setText(
                self.active_sound_path.name if self.active_sound_path == self.default_sound_path else str(self.active_sound_path)
            )

            shops_response = self.api.get_shops()
            self.shops_payload = self._normalise_shops_payload(shops_response)
            self.write_action_log(
                f"Загрузка заведений: получено {len(self.shops_payload.get('shops', []))}; "
                f"ограниченный доступ: {self.shops_payload.get('is_restricted', 'не указан')}; "
                f"источник прав: {self.shops_payload.get('access_source', 'не указан')}",
                "success" if self.shops_payload.get("shops") else "warning"
            )
            self.shops_list.clear()
            saved_ids = self.storage.get("selected_shop_ids", "")
            if saved_ids:
                selected = set()
                for part in saved_ids.split(","):
                    try: selected.add(int(part))
                    except ValueError: pass
            else:
                selected=set(map(int,self.shops_payload.get("selected_ids",[])))
            for shop in self.shops_payload.get("shops",[]):
                item=QListWidgetItem(shop.get("name",f"Магазин {shop.get('id')}"))
                item.setData(Qt.UserRole,shop["id"])
                item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if int(shop["id"]) in selected else Qt.Unchecked)
                self.shops_list.addItem(item)

            self.auto.toggled.connect(self._save_local_preferences)
            self.sound_enabled.toggled.connect(self._save_local_preferences)
            self.interval.valueChanged.connect(self._save_local_preferences)
            self.write_action_log("Настройки восстановлены из settings.ini.", "success")
        except Exception as exc:
            self.write_action_log(f"Не удалось загрузить настройки: {exc}", "error")
            self.show_error(exc)

    def save_settings(self):
        try:
            self._save_local_preferences()
            self.api.save_settings({"auto_refresh":self.auto.isChecked(),"refresh_interval":self.interval.value(),"sound_enabled":self.sound_enabled.isChecked()})
            ids=[self.shops_list.item(i).data(Qt.UserRole) for i in range(self.shops_list.count()) if self.shops_list.item(i).checkState()==Qt.Checked]
            self.api.save_shops(ids)
            self.storage.set("selected_shop_ids", ",".join(map(str, ids)))
            if self.poller:
                self.poller.stop(); self.poller = None
            self.start_poller()
            self.write_action_log("Настройки сохранены в INI и отправлены на сервер.", "success")
            QMessageBox.information(self,"Настройки","Настройки сохранены")
        except Exception as exc:
            self.write_action_log(f"Ошибка сохранения настроек: {exc}", "error")
            self.show_error(exc)
    def start_poller(self):
        try:
            if self.auto.isChecked():
                self._refresh_interval = self.interval.value()
                self.refresh_progress.setMaximum(self._refresh_interval)
                self.refresh_timer.start()
                self.refresh_caption.setText(f"Автообновление · интервал {self._refresh_interval} сек.")
                self.poller=OrderPoller(self.api,self._refresh_interval,self)
                self.poller.orders_ready.connect(self.on_polled_orders)
                self.poller.new_orders.connect(self.on_new_orders)
                self.poller.poll_error.connect(self.on_poll_error)
                self.poller.start()
            else:
                self.refresh_timer.stop()
                self.refresh_progress.setValue(0)
                self.refresh_caption.setText("Автообновление выключено")
        except Exception as exc:
            self.write_action_log(f"Не удалось запустить автообновление: {exc}", "error")

    def on_poll_error(self, message):
        self.statusBar().showMessage(message, 5000)
        self.write_action_log(f"Ошибка автообновления: {message}", "error")
    def on_polled_orders(self, rows):
        table = self.tables["available"]
        if not isinstance(rows, list):
            self.write_action_log("Автообновление пропущено: сервер вернул некорректный список.", "warning")
            return
        # Пустой ответ фонового запроса не должен внезапно очищать рабочий список.
        # Ручная кнопка «Обновить» по-прежнему показывает фактический пустой результат.
        if not rows and table.rowCount() > 0:
            self._reset_refresh_progress()
            self.write_action_log(
                "Фоновый запрос вернул 0 заказов; предыдущий список оставлен на экране. "
                "Проверьте список кнопкой «Обновить», если нужно синхронизировать его полностью.",
                "warning"
            )
            return
        current_ids = {int(o["id"]) for o in rows if o.get("id") is not None}
        self._new_order_ids.intersection_update(current_ids)
        self._fill_orders_table(table, rows, self._new_order_ids)
        self._reset_refresh_progress()
        self.write_action_log(f"Фоновое обновление: получено доступных заказов — {len(rows)}.", "success")

    def on_new_orders(self, order_ids):
        ids = {int(value) for value in order_ids}
        self._new_order_ids.update(ids)
        count = len(ids)
        # Сразу выделяем новые позиции, не дожидаясь следующего цикла.
        rows = []
        table = self.tables["available"]
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            order = item.data(Qt.UserRole) if item else None
            if order:
                rows.append(order)
        if rows:
            self._fill_orders_table(table, rows, self._new_order_ids)
        if self.sound_enabled.isChecked():
            self.sound.play()
            self.write_action_log(f"Новое поступление: {count}. Воспроизведено звуковое оповещение.", "success")
        else:
            self.write_action_log(f"Поступило новых заказов: {count}. Звук отключён.", "warning")
        self.statusBar().showMessage(f"Новых заказов: {count}", 10000)
        self.load_dashboard()
    def logout(self):
        self.refresh_timer.stop()
        if self.poller: self.poller.stop()
        try: self.api.logout()
        except Exception: pass
        self.storage.delete_token(self.identity)
        self.login=LoginWindow(self.storage); self.login.showMaximized(); self.close()
    def closeEvent(self,event):
        self.refresh_timer.stop()
        if self.poller: self.poller.stop()
        event.accept()
