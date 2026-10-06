# ============================================================
# utils.py — Tiện ích dùng chung
# ============================================================
import re
import time
import random
import string
import hashlib
from datetime import datetime

# ----- Fallback UA list (nếu fake_useragent lỗi) -----
_FALLBACK_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

# ----- Thử dùng fake_useragent, nếu không có thì dùng fallback -----
try:
    from fake_useragent import UserAgent
    _UA = UserAgent()
    def random_ua():
        try:
            return _UA.random
        except Exception:
            return random.choice(_FALLBACK_UAS)
except Exception:
    def random_ua():
        return random.choice(_FALLBACK_UAS)


def get_uptime(start: datetime) -> str:
    """Trả về uptime dạng HH:MM:SS từ thời điểm start."""
    e = (datetime.now() - start).total_seconds()
    h, r = divmod(int(e), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_cookie_string(s: str) -> dict:
    """Parse chuỗi cookie dạng 'a=1; b=2' thành dict."""
    out = {}
    for p in s.split(";"):
        if "=" in p:
            k, v = p.strip().split("=", 1)
            out[k] = v
    return out


def cookie_to_string(d: dict) -> str:
    """Ngược lại: dict → chuỗi cookie."""
    return "; ".join(f"{k}={v}" for k, v in d.items())


def gen_device_id() -> str:
    """Sinh device ID 16 ký tự."""
    return hashlib.md5(str(random.random()).encode()).hexdigest()[:16]


def gen_imei() -> str:
    """Sinh IMEI 15 số."""
    return "".join(random.choices(string.digits, k=15))


def jitter(base: float, f: float = 0.4) -> float:
    """Thêm jitter ±f vào giá trị base."""
    return base * random.uniform(1 - f, 1 + f)


def now_ms() -> int:
    """Timestamp mili giây."""
    return int(time.time() * 1000)
