# Courier Desktop

Windows desktop client for the Laravel courier cabinet. Built with Python 3.11+ and PySide6.

## Included in this first implementation

- Login using phone or email + password; optional tenant ID/slug to disambiguate accounts.
- Split login screen with a live process log (connection, authentication, token storage and errors); secrets are never written to the log.
- Laravel Sanctum personal access token authentication (token stored in Windows Credential Manager through `keyring`).
- Dashboard counters and courier online/offline status.
- Available, active and completed orders with date filters.
- Accept order, update order status and confirm delivery.
- Auto-refresh and sound notification for newly available orders.
- Courier settings and selected shop list.
- PHP API controller, routes and Sanctum integration notes.

The Vue dashboard also contains chat, payment link generation, delivery-price calculator, admin courier assignment and acquiring settings. Those depend on additional services/components and are not silently mocked in this starter. The API contract leaves room to add them in the next pass.

## Run on Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Set the Laravel URL in the login screen. No browser session or Laravel cookies are reused.

## Build EXE

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name CourierDesktop --add-data "assets;assets" main.py
```

Output: `dist/CourierDesktop/CourierDesktop.exe` (or one-folder build). Test on a clean Windows machine before distribution.

## Laravel installation

See `laravel/INSTALL.md`. Copy the controller and route definitions into the Laravel project, enable Sanctum for `TenantUser`, and verify the actual courier role name. This package does not include or modify the user's Laravel project automatically.


### Автосохранение формы входа

Поля адреса сервера, API-префикса, логина и Tenant сохраняются в `%APPDATA%\\CourierDesktop\\settings.ini` при каждом изменении. При следующем запуске они автоматически восстанавливаются. Пароль хранится отдельно в Windows Credential Manager, а не в открытом INI-файле. Токен авторизации также остаётся в защищённом хранилище Windows.


### Дополнения интерфейса

- Убран статус «На линии» — в рабочем процессе он не используется.
- Добавлена полоска обратного отсчёта до следующего автообновления заказов.
- В рабочей панели добавлен журнал действий, ошибок и запросов.
- Нажатие на строку заказа открывает окно с полным JSON-ответом API; тот же JSON записывается в журнал для отладки.
- В настройках можно выбрать WAV-файл оповещения и проверить его воспроизведение. По умолчанию используется `assets/new_order.wav`.
- Параметры автообновления, звука, путь к WAV и выбранные магазины сохраняются в `settings.ini`.

Файл уведомления выбирается в формате WAV (поддерживается `QSoundEffect`); выбранный путь и остальные настройки хранятся в `%APPDATA%\\CourierDesktop\\settings.ini`.


### Детали заказа и калькулятор доставки

- Окно заказа разделено на вкладки «Заказ» и «JSON и отладка».
- Визуальная вкладка показывает клиента, адрес, координаты, суммы, примечания и полный список товаров с заведениями, количеством и стоимостью.
- Кнопка «Рассчитать доставку на карте» открывает MapLibre-карту. Можно искать адрес через Nominatim, выбирать точку кликом по карте или использовать геолокацию.
- Расстояние и стоимость запрашиваются у Laravel API (`POST /api/desktop/shops/{id}/calculate-delivery`); локального приблизительного расчёта тарифов нет.
- Ссылка на оплату создаётся через `POST /api/desktop/shops/{id}/payment-link`; QR формируется локально.
- API списка заведений дополнен координатами `shop_coords` и настройками карты. Если у заведения координаты не заданы, калькулятор покажет предупреждение — фиктивные координаты не подставляются.
- Для карты требуется интернет-соединение. Используется MapTiler style и Nominatim geocoding; ключ карты берётся из настроек заведения (`map_tiler`) или из встроенного значения по умолчанию.

## Самостоятельный калькулятор доставки

В главном окне доступна отдельная кнопка **«Калькулятор доставки»**. Расчёт не связан с заказом и не создаёт/не изменяет заказ.

1. Выберите доступное заведение — его настройки доставки (зоны, базовая цена, тариф за километр) используются сервером.
2. Точка отправления по умолчанию берётся из `shop_coords` выбранного заведения. При необходимости можно найти другой адрес отправления.
3. Укажите адрес назначения через поиск либо выберите его на карте.
4. Для выбора обеих точек непосредственно на карте переключите поле «Клик по карте задаёт» между отправлением и назначением.
5. Нажмите «Рассчитать стоимость». Расстояние и цена рассчитываются отдельным Laravel-контроллером `DeliveryCalculationController`.

Новый API endpoint: `POST /api/desktop/delivery-calculator/shops/{shopId}/calculate`.
Он принимает `origin_lat`, `origin_lng`, `destination_lat`, `destination_lng` и необязательные подписи адресов. Тарифная конфигурация читается только из настроек выбранного Tenant. Проверяется доступ курьера по `assigned_shops`, `settings.delivery_shops` или собственному `tenant_id` (либо права super admin).


## Окна и запуск

Окно входа, основная рабочая панель и самостоятельный калькулятор доставки открываются развёрнутыми на весь доступный экран (Windows Maximized, без перехода в эксклюзивный полноэкранный режим). Для окон включены стандартные кнопки сворачивания, разворачивания и закрытия. Вспомогательные диалоги остаются компактными, но также имеют кнопку сворачивания.

Если в консоли Qt WebEngine появляется `net_error -202` / `ERR_CERT_AUTHORITY_INVALID`, это ошибка проверки доверия SSL-сертификата внешнего ресурса карты. Приложение не отключает проверку сертификатов. Проверьте дату и время Windows, обновления Windows/корневых сертификатов, а также HTTPS-фильтрацию антивируса или корпоративного прокси. Если используется прокси с инспекцией HTTPS, его корневой сертификат должен быть установлен в доверенные корневые центры сертификации Windows.

### Вкладка «Калькулятор доставки»

Калькулятор встроен непосредственно во вкладки главного окна (не открывает отдельное диалоговое окно). Карта расположена слева, панель выбора заведения, адресов, расчёта, результата и оплаты — справа. В правой панели внизу доступен журнал обмена с API: параметры запроса, полный JSON успешного ответа и подробности HTTP/API-ошибок.

Расчёт выполняется по координатам, полученным геокодером или выбранным кликом на карте. После успешного поиска адреса поле автоматически заменяется нормализованным адресом; расчёт не блокируется из-за различий между введённой строкой и нормализованным адресом.
