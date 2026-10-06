import re, time, random, string, hashlib, json
from datetime import datetime

try:
    from fake_useragent import UserAgent
    _UA = UserAgent()
    def random_ua():
        try: return _UA.random
        except: return _fallback_ua()
except Exception:
    def random_ua(): return _fallback_ua()

def _fallback_ua():
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    ]
    return random.choice(uas)

def get_uptime(start: datetime) -> str:
    e = (datetime.now() - start).total_seconds()
    h, r = divmod(int(e), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def parse_cookie_string(s: str) -> dict:
    out = {}
    for p in s.split(";"):
        if "=" in p:
            k, v = p.strip().split("=", 1)
            out[k] = v
    return out

def cookie_to_string(d: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in d.items())

def gen_device_id() -> str:
    return hashlib.md5(str(random.random()).encode()).hexdigest()[:16]

def gen_imei() -> str:
    return "".join(random.choices(string.digits, k=15))

def jitter(base: float, f: float = 0.4) -> float:
    return base * random.uniform(1 - f, 1 + f)

def now_ms() -> int:
    return int(time.time() * 1000)

def safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict): return default
        cur = cur.get(k)
        if cur is None: return default
    return cur
