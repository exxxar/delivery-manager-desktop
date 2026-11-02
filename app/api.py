import requests

class ApiError(Exception):
    pass

class ApiClient:
    def __init__(self, base_url: str, prefix: str = "/api/desktop"):
        self.base_url = base_url.rstrip("/")
        self.prefix = "/" + prefix.strip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "CourierDesktop/1.0"})
        self.timeout = 18

    def set_token(self, token):
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            self.session.headers.pop("Authorization", None)

    def request(self, method, path, **kwargs):
        url = f"{self.base_url}{self.prefix}{path}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise ApiError(f"Не удалось связаться с сервером: {exc}") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            message = payload.get("message") or payload.get("error") or f"Ошибка HTTP {response.status_code}"
            if response.status_code == 401:
                message = "Сессия истекла. Войдите повторно."
            details = __import__("json").dumps(payload, ensure_ascii=False, default=str)
            raise ApiError(f"HTTP {response.status_code}: {message} | Ответ сервера: {details}")
        if payload.get("success") is False:
            raise ApiError(payload.get("message") or payload.get("error") or "Операция не выполнена")
        return payload

    def login(self, login, password, tenant=None):
        data = {"login": login, "password": password}
        if tenant:
            data["tenant"] = tenant
        return self.request("POST", "/auth/login", json=data)

    def me(self): return self.request("GET", "/auth/me")
    def logout(self): return self.request("POST", "/auth/logout")
    def dashboard(self): return self.request("GET", "/dashboard")
    def orders(self, kind, date_from, date_to):
        return self.request("GET", f"/orders/{kind}", params={"date_from": date_from, "date_to": date_to})
    def accept_order(self, order_id): return self.request("POST", f"/orders/{order_id}/accept")
    def change_status(self, order_id, status): return self.request("PATCH", f"/orders/{order_id}/status", json={"status": status})
    def confirm_delivery(self, order_id): return self.request("POST", f"/orders/{order_id}/confirm-delivery")
    def update_order_details(self, order_id, distance_km, delivery_price):
        return self.request("PUT", f"/orders/{order_id}/details", json={"distance_km": distance_km, "delivery_price": delivery_price})
    def toggle_online(self, is_online): return self.request("PATCH", "/status", json={"is_online": is_online})
    def get_settings(self): return self.request("GET", "/settings")
    def save_settings(self, settings): return self.request("PUT", "/settings", json=settings)
    def get_shops(self): return self.request("GET", "/shops")
    def save_shops(self, ids): return self.request("PUT", "/shops", json={"shop_ids": ids})
    def calculate_shop_delivery(self, shop_id, lat, lng):
        return self.request("POST", f"/shops/{shop_id}/calculate-delivery", json={"lat": lat, "lng": lng})
    def calculate_delivery_route(self, shop_id, origin_lat, origin_lng, destination_lat, destination_lng,
                                 origin_address=None, destination_address=None):
        return self.request("POST", f"/delivery-calculator/shops/{shop_id}/calculate", json={
            "origin_lat": origin_lat, "origin_lng": origin_lng,
            "destination_lat": destination_lat, "destination_lng": destination_lng,
            "origin_address": origin_address, "destination_address": destination_address,
        })
    def generate_shop_payment_link(self, shop_id, amount, description):
        return self.request("POST", f"/shops/{shop_id}/payment-link", json={"amount": amount, "description": description})
