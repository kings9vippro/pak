import time, json, base64, random, threading, hashlib
from io import BytesIO
import requests
import qrcode

QR_TTL = 120


class ZaloQRLogin:
    BASE = "https://id.zalo.me"

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            "Origin": "https://id.zalo.me",
            "Referer": "https://id.zalo.me/account",
            "Content-Type": "application/x-www-form-urlencoded",
        })

    @staticmethod
    def _device_id():
        return hashlib.md5(str(random.random()).encode()).hexdigest()

    def create_qr(self):
        qr_id = hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()
        exp = int(time.time()) + QR_TTL
        qr_content = f"zalologin://token={qr_id}&exp={exp}"
        img = qrcode.make(qr_content)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return {
            "qr_id": qr_id,
            "qr_image": buf,
            "qr_content": qr_content,
            "exp": exp,
            "ttl": QR_TTL,
        }

    def poll_login(self, qr_id, on_status=None, stop_event=None):
        start = time.time()
        while time.time() - start < QR_TTL:
            if stop_event and stop_event.is_set():
                return {"error": "Stopped"}
            try:
                r = self.s.get(f"{self.BASE}/account/qr/check",
                               params={"token": qr_id}, timeout=15)
                d = r.json()
                status = d.get("data", {}).get("status", 0)
                if on_status:
                    on_status(status)
                if status == 2:
                    return self._finalize(qr_id)
                elif status == -1:
                    return {"error": "Từ chối"}
                elif status == -2:
                    return {"error": "Hết hạn"}
            except Exception:
                pass
            time.sleep(2)
        return {"error": "Timeout"}

    def _finalize(self, qr_id):
        try:
            imei = self._device_id()
            r = self.s.post(f"{self.BASE}/account/qr/login",
                            data={"token": qr_id, "imei": imei}, timeout=15)
            data = r.json()
            return {
                "cookies": self.s.cookies.get_dict(),
                "secret_key": data.get("data", {}).get("zpw_enk"),
                "uid": data.get("data", {}).get("uid"),
                "imei": data.get("data", {}).get("imei") or imei,
            }
        except Exception as e:
            return {"error": str(e)}
