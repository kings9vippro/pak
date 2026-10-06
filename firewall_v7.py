# ============================================================
# firewall_v7.py — 7 LỚP TƯỜNG LỬA ANTI-BAN
# L1: Request Shaper — sắp header theo thứ tự Chrome
# L2: Fingerprint Pool — giữ fingerprint ổn định per-cookie
# L3: Behavior Engine — typing rhythm, reading, break
# L4: Rate Balancer — min 3s, adaptive 3-120s
# L5: Multi-Tier Circuit Breaker — 3 tầng cooldown
# L6: Cookie Guard Base — rate limit riêng từng cookie
# L7: Anomaly Detector — phát hiện latency/status bất thường
# ============================================================
import time
import random
import threading
import hashlib
from collections import deque
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils import jitter


# ============================================================
# L1 — REQUEST SHAPER: sắp header đúng thứ tự Chrome
# ============================================================
class RequestShaper:
    HEADER_ORDER = [
        "Host", "Connection", "Content-Length",
        "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
        "Upgrade-Insecure-Requests", "User-Agent", "Accept",
        "Sec-Fetch-Site", "Sec-Fetch-Mode", "Sec-Fetch-User",
        "Sec-Fetch-Dest", "Referer", "Accept-Encoding",
        "Accept-Language", "Cookie", "Origin", "DNT",
        "X-FB-Friendly-Name", "X-FB-LSD",
    ]

    def shape(self, headers: dict) -> dict:
        """Sắp lại header theo thứ tự Chrome để tránh bị detect."""
        out = {}
        for k in self.HEADER_ORDER:
            if k in headers:
                out[k] = headers[k]
        for k, v in headers.items():
            if k not in out:
                out[k] = v
        return out


# ============================================================
# L2 — FINGERPRINT POOL: 9 platform, giữ ổn định per-cookie
# ============================================================
class FingerprintPool:
    PLAT = [
        ("Windows NT 10.0; Win64; x64", False, "Windows"),
        ("Windows NT 10.0; WOW64", False, "Windows"),
        ("Macintosh; Intel Mac OS X 10_15_7", False, "macOS"),
        ("Macintosh; Intel Mac OS X 13_6_1", False, "macOS"),
        ("X11; Linux x86_64", False, "Linux"),
        ("iPhone; CPU iPhone OS 17_2 like Mac OS X", True, "iOS"),
        ("iPhone; CPU iPhone OS 16_7 like Mac OS X", True, "iOS"),
        ("Linux; Android 14; SM-S918B", True, "Android"),
        ("Linux; Android 13; Pixel 7", True, "Android"),
    ]
    CHROME = ["120.0.0.0", "121.0.0.0", "122.0.0.0", "123.0.0.0",
              "124.0.0.0", "125.0.0.0", "126.0.0.0"]
    EDGE = ["120.0.0.0", "121.0.0.0", "122.0.0.0"]
    RES = ["1920x1080", "2560x1440", "1366x768", "1440x900",
           "3840x2160", "390x844", "414x896", "360x780"]
    TZ = ["Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Singapore"]

    def _gen(self) -> dict:
        """Sinh 1 fingerprint ngẫu nhiên."""
        p, mobile, brand = random.choice(self.PLAT)
        is_edge = (not mobile) and random.random() < 0.2
        if is_edge:
            v = random.choice(self.EDGE)
            ua = (f"Mozilla/5.0 ({p}) AppleWebKit/537.36 "
                  f"(KHTML, like Gecko) Chrome/{v} Safari/537.36 Edg/{v}")
            browser = "Edge"
        else:
            v = random.choice(self.CHROME)
            ua = (f"Mozilla/5.0 ({p}) AppleWebKit/537.36 "
                  f"(KHTML, like Gecko) Chrome/{v} "
                  f"{'Mobile ' if mobile else ''}Safari/537.36")
            browser = "Chrome"
        return {
            "ua": ua, "brand": brand, "mobile": mobile,
            "browser": browser, "chrome_v": v,
            "res": random.choice(self.RES),
            "lang": random.choice(["vi-VN,vi;q=0.9", "en-US,en;q=0.9"]),
            "tz": random.choice(self.TZ),
            "device_id": hashlib.md5(str(random.random()).encode()).hexdigest()[:16],
        }

    def headers(self, fp: dict, extra: dict = None) -> dict:
        """Sinh header từ fingerprint."""
        h = {
            "User-Agent": fp["ua"],
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,image/apng,*/*;q=0.8"),
            "Accept-Language": fp["lang"],
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "sec-ch-ua": f'"Chromium";v="{fp["brand"]}", "Not A;Brand";v="24"',
            "sec-ch-ua-mobile": "?1" if fp["mobile"] else "?0",
            "sec-ch-ua-platform": f'"{fp["brand"]}"',
            "sec-ch-prefers-color-scheme": random.choice(["light", "dark"]),
        }
        if extra:
            h.update(extra)
        return h


# ============================================================
# L3 — BEHAVIOR ENGINE: giả lập người thật
# ============================================================
class Behavior:
    TYPING_SLOW = (0.10, 0.25)
    TYPING_FAST = (0.025, 0.07)
    READING = (0.8, 3.5)
    BREAK = 0.06
    BREAK_T = (8, 45)
    LONG_BREAK = 0.012
    LONG_T = (90, 480)

    @staticmethod
    def typing(text: str) -> float:
        """Tính thời gian gõ phím cho đoạn text."""
        n = len(text)
        if n == 0:
            return 0.5
        head = min(5, n) * random.uniform(*Behavior.TYPING_SLOW)
        mid = max(0, n - 10) * random.uniform(*Behavior.TYPING_FAST)
        tail = min(5, n) * random.uniform(*Behavior.TYPING_SLOW)
        punct = sum(1 for c in text if c in ".,!?;:") * 0.25
        return head + mid + tail + punct

    @staticmethod
    def pre_send():
        """Delay trước khi gửi (giả lập đọc tin)."""
        time.sleep(random.uniform(*Behavior.READING))

    @staticmethod
    def maybe_break():
        """Xác suất nghỉ ngắn/dài như người thật."""
        r = random.random()
        if r < Behavior.LONG_BREAK:
            time.sleep(random.uniform(*Behavior.LONG_T))
        elif r < Behavior.BREAK:
            time.sleep(random.uniform(*Behavior.BREAK_T))

    @staticmethod
    def humanize(text: str) -> str:
        """Thêm emoji, dấu câu, biến thể để tránh pattern."""
        v = [text]
        if random.random() < 0.35:
            v.append(f"{text} {random.choice('😀😅🤣😏😎🙃😹🤔😐🥲👍🔥💯❤️✨')}")
        if random.random() < 0.4:
            v.append(f"{text}{random.choice(['...', '..', '!', '?', '!!', '~'])}")
        if random.random() < 0.15:
            v.append(text.replace(" ", "  ", 1))
        if random.random() < 0.08:
            v.append(text.upper() if random.random() < 0.5 else text.lower())
        return random.choice(v)

    @staticmethod
    def typo(t: str, p=0.05) -> str:
        """Thêm lỗi chính tả nhỏ."""
        if random.random() > p:
            return t
        chars = list(t)
        for _ in range(random.randint(1, 2)):
            i = random.randint(0, len(chars) - 1)
            if chars[i].isalpha():
                chars[i] = random.choice("abcdefghijklmnopqrstuvwxyz")
        return "".join(chars)

    @staticmethod
    def vary(t: str) -> str:
        """Biến đổi độ dài tin nhắn."""
        r = random.random()
        if r < 0.2:
            return t[:max(1, len(t) // 2)]
        if r < 0.35:
            return t + " " + random.choice(["ok", "ừ", "hmm", "...", ":)))"])
        return t

    @staticmethod
    def entropy_mask(t: str) -> str:
        """Chèn ký tự zero-width để tránh hash-detect."""
        if random.random() < 0.12:
            zw = random.choice(["\u200b", "\u200c", "\u200d", "\ufeff"])
            pos = random.randint(1, max(1, len(t) - 1))
            t = t[:pos] + zw + t[pos:]
        return t


# ============================================================
# L4 — RATE BALANCER: min 3s, adaptive 3-120s
# ============================================================
class RateBalancer:
    MIN_DELAY = 3.0
    MAX_DELAY = 120.0

    def __init__(self, base_delay=3.0):
        self.base = max(self.MIN_DELAY, base_delay)
        self.current = self.base
        self.window = deque(maxlen=30)
        self.last_adj = time.time()
        self.lock = threading.Lock()
        self.manual = None

    def set_manual(self, v: float):
        with self.lock:
            self.manual = max(self.MIN_DELAY, min(self.MAX_DELAY, v))
            self.current = self.manual

    def record(self, ok: bool):
        """Ghi kết quả request, tự điều chỉnh delay."""
        with self.lock:
            self.window.append(ok)
            if self.manual is not None:
                self.current = self.manual
                return
            if len(self.window) >= 8 and time.time() - self.last_adj > 5:
                rate = sum(self.window) / len(self.window)
                if rate < 0.5:
                    self.current = min(self.MAX_DELAY, self.current * 1.8)
                elif rate < 0.8:
                    self.current = min(self.MAX_DELAY, self.current * 1.2)
                elif rate > 0.95:
                    self.current = max(self.MIN_DELAY, self.current * 0.85)
                self.last_adj = time.time()

    def wait(self):
        with self.lock:
            d = self.current
        time.sleep(jitter(d, 0.25))


# ============================================================
# L5 — MULTI-TIER CIRCUIT BREAKER: 3 tầng cooldown
# ============================================================
class MultiCircuit:
    def __init__(self, thresholds=(0.6, 0.75, 0.9), window=25,
                 cooldowns=(60, 300, 900)):
        self.thresholds = thresholds
        self.window = window
        self.cooldowns = cooldowns
        self.results = deque(maxlen=window)
        self.opened_at = None
        self.tier = 0

    def record(self, ok: bool):
        self.results.append(ok)
        if self._should_open():
            self.opened_at = time.time()
            self.tier = min(self.tier + 1, len(self.thresholds) - 1)
            print(f"[CB] Open tier {self.tier}")

    def _should_open(self) -> bool:
        if self.opened_at:
            cd = self.cooldowns[self.tier]
            if time.time() - self.opened_at > cd:
                self.opened_at = None
                self.tier = max(0, self.tier - 1)
                self.results.clear()
                return False
            return True
        if len(self.results) < self.window:
            return False
        fail = 1 - sum(self.results) / len(self.results)
        return fail >= self.thresholds[self.tier]

    def is_open(self) -> bool:
        return bool(self.opened_at)

    def wait_if_open(self):
        while self.is_open():
            time.sleep(2)


# ============================================================
# L6 — COOKIE GUARD BASE: rate limit riêng từng cookie
# ============================================================
class CookieGuardBase:
    def __init__(self):
        self.limits = {}
        self.lock = threading.Lock()

    def _hash(self, c: str) -> str:
        return hashlib.md5(c.encode()).hexdigest()[:12]

    def wait(self, cookie: str, base_delay: float):
        h = self._hash(cookie)
        with self.lock:
            if h not in self.limits:
                self.limits[h] = RateBalancer(base_delay)
            b = self.limits[h]
        b.wait()

    def record(self, cookie: str, ok: bool, base_delay: float):
        h = self._hash(cookie)
        with self.lock:
            b = self.limits.setdefault(h, RateBalancer(base_delay))
        b.record(ok)


# ============================================================
# L7 — ANOMALY DETECTOR: phát hiện bất thường
# ============================================================
class Anomaly:
    def __init__(self):
        self.history = deque(maxlen=50)
        self.lock = threading.Lock()

    def record(self, latency: float, status: int):
        with self.lock:
            self.history.append((latency, status))

    def is_anomaly(self) -> bool:
        """True nếu >50% request gần đây fail hoặc latency cao."""
        with self.lock:
            if len(self.history) < 15:
                return False
            avg_status = sum(1 for h in self.history if h[1] >= 400) / len(self.history)
            avg_lat = sum(h[0] for h in self.history) / len(self.history)
            return avg_status > 0.5 or avg_lat > 35


# ============================================================
# BAN DETECTOR: nhận diện tín hiệu ban
# ============================================================
class BanDetector:
    SIGNALS = {
        "checkpoint": ["checkpoint", "xác minh danh tính", "verify your identity",
                       "xác minh tài khoản"],
        "blocked": ["temporarily blocked", "bị chặn tạm thời",
                    "unusual activity", "bất thường", "tài khoản bị tạm khóa"],
        "disabled": ["account disabled", "vô hiệu hóa", "suspended",
                     "tài khoản bị vô hiệu"],
        "captcha": ["captcha", "recaptcha", "are you human", "xác minh bạn là người"],
        "honeypot": ["honeypot", "canary", "bait"],
    }

    @staticmethod
    def check(txt: str, code: int) -> Optional[str]:
        if not txt:
            return None
        t = txt.lower()
        for sig, kws in BanDetector.SIGNALS.items():
            for kw in kws:
                if kw in t:
                    return sig
        if code in (401, 403):
            return "forbidden"
        if code == 429:
            return "rate_limit"
        return None


# ============================================================
# CORE FIREWALL: gộp 7 lớp lại
# ============================================================
class Firewall:
    name = "base"
    BASE_DELAY = 3.0
    RETRY = 4
    BACKOFF = 1.5

    def __init__(self):
        self.shaper = RequestShaper()
        self.fp_pool = FingerprintPool()
        self.behavior = Behavior()
        self.rate = RateBalancer(self.BASE_DELAY)
        self.cb = MultiCircuit()
        self.cookie_guard = CookieGuardBase()
        self.anomaly = Anomaly()
        self.lock = threading.Lock()
        self.stats = {"ok": 0, "fail": 0, "blocked": 0, "banned": 0,
                      "cb": 0, "captcha": 0, "anomaly": 0}
        # Fingerprint cố định per-cookie
        self.cookie_fp = {}
        self.fp_lock = threading.Lock()

    def _fp_for(self, cookie: str) -> dict:
        """Lấy fingerprint cho cookie, giữ ổn định."""
        if not cookie:
            return self.fp_pool._gen()
        h = hashlib.md5(cookie.encode()).hexdigest()[:12]
        with self.fp_lock:
            if h not in self.cookie_fp:
                self.cookie_fp[h] = self.fp_pool._gen()
            # Xoay nhẹ 0.5% để tránh pattern
            if random.random() < 0.005:
                self.cookie_fp[h] = self.fp_pool._gen()
            return self.cookie_fp[h]

    def _headers(self, cookie=None, extra=None):
        fp = self._fp_for(cookie)
        h = self.fp_pool.headers(fp, extra)
        return self.shaper.shape(h)

    def request(self, method, url, cookie=None, **kw):
        """Request với đầy đủ 7 lớp bảo vệ."""
        # L5: chờ nếu circuit đang mở
        self.cb.wait_if_open()

        headers = self._headers(cookie, kw.pop("headers", {}))
        timeout = kw.pop("timeout", 25)
        sess = kw.pop("session", None) or requests.Session()

        # Adapter an toàn, fallback nếu lỗi
        try:
            ad = HTTPAdapter(max_retries=Retry(total=0),
                             pool_connections=5, pool_maxsize=10)
        except TypeError:
            ad = HTTPAdapter(max_retries=Retry(total=0))
        sess.mount("https://", ad)
        sess.mount("http://", ad)

        if cookie and "Cookie" not in headers:
            headers["Cookie"] = cookie

        # Retry loop
        for attempt in range(self.RETRY):
            # L4/L6: chờ delay
            if cookie:
                self.cookie_guard.wait(cookie, self.BASE_DELAY)
            else:
                self.rate.wait()

            # L3: break ngẫu nhiên
            if attempt:
                self.behavior.maybe_break()

            try:
                t0 = time.time()
                r = sess.request(method, url, headers=headers,
                                 timeout=timeout, verify=False, **kw)
                dt = time.time() - t0

                # L7: ghi anomaly
                self.anomaly.record(dt, r.status_code)
                if self.anomaly.is_anomaly():
                    with self.lock:
                        self.stats["anomaly"] += 1
                    if cookie:
                        self.cookie_guard.record(cookie, False, self.BASE_DELAY)
                    self.cb.record(False)
                    time.sleep(random.uniform(8, 20))

                # Detect ban
                ban = BanDetector.check(r.text, r.status_code)
                if ban in ("checkpoint", "disabled", "blocked", "honeypot"):
                    with self.lock:
                        self.stats["banned"] += 1
                    if cookie:
                        self.cookie_guard.record(cookie, False, self.BASE_DELAY)
                    self.cb.record(False)
                    time.sleep(random.uniform(10, 30))
                    continue
                if ban == "captcha":
                    with self.lock:
                        self.stats["captcha"] += 1
                    if cookie:
                        self.cookie_guard.record(cookie, False, self.BASE_DELAY)
                    self.cb.record(False)
                    time.sleep(random.uniform(20, 45))
                    continue

                # Thành công
                if r.status_code in (200, 201, 204):
                    with self.lock:
                        self.stats["ok"] += 1
                    if cookie:
                        self.cookie_guard.record(cookie, True, self.BASE_DELAY)
                    else:
                        self.rate.record(True)
                    self.cb.record(True)
                    return r

                # Rate limit / forbidden
                if r.status_code in (429, 403, 419):
                    with self.lock:
                        self.stats["blocked"] += 1
                    if cookie:
                        self.cookie_guard.record(cookie, False, self.BASE_DELAY)
                    self.cb.record(False)
                    w = self.BACKOFF * (2 ** attempt) * random.uniform(1.5, 2.5)
                    time.sleep(min(w, 120))
                    continue

                self.cb.record(False)
                if cookie:
                    self.cookie_guard.record(cookie, False, self.BASE_DELAY)
            except Exception:
                self.cb.record(False)

            # Exponential backoff
            time.sleep(self.BACKOFF * (2 ** attempt) * random.uniform(0.8, 1.2))

        with self.lock:
            self.stats["fail"] += 1
        return None

    def get(self, u, **k):
        return self.request("GET", u, **k)

    def post(self, u, **k):
        return self.request("POST", u, **k)

    def report(self):
        """Báo cáo trạng thái firewall."""
        with self.lock:
            s = self.stats
        cb = f"OPEN-T{self.cb.tier}" if self.cb.is_open() else "OK"
        man = self.rate.manual
        note = f" (manual {man}s)" if man else ""
        return (f"🛡 *{self.name}* OK:`{s['ok']}` Fail:`{s['fail']}` "
                f"Block:`{s['blocked']}` Ban:`{s['banned']}` Captcha:`{s['captcha']}` "
                f"Anomaly:`{s['anomaly']}` "
                f"| Delay:`{self.rate.current:.1f}s`{note} CB:`{cb}`")


# ============================================================
# CÁC APP FIREWALL CỤ THỂ
# ============================================================
class FBFW(Firewall):
    name = "Facebook"
    BASE_DELAY = 4.0
    RETRY = 5
    BACKOFF = 2.0


class ZaloFW(Firewall):
    name = "Zalo"
    BASE_DELAY = 3.0
    RETRY = 3
    BACKOFF = 1.2


class DiscordFW(Firewall):
    name = "Discord"
    BASE_DELAY = 3.0
    RETRY = 3
    BACKOFF = 1.0


class TelegramFW(Firewall):
    name = "Telegram"
    BASE_DELAY = 3.0
    RETRY = 4
    BACKOFF = 2.5


class GmailFW(Firewall):
    name = "Gmail"
    BASE_DELAY = 10.0
    RETRY = 2
    BACKOFF = 6.0


class IGFW(Firewall):
    name = "Instagram"
    BASE_DELAY = 8.0
    RETRY = 3
    BACKOFF = 3.0


class WeChatFW(Firewall):
    name = "WeChat"
    BASE_DELAY = 4.0
    RETRY = 3
    BACKOFF = 2.0


class SMSFW(Firewall):
    name = "SMS"
    BASE_DELAY = 5.0
    RETRY = 2
    BACKOFF = 3.0


# ----- Registry toàn cục -----
FW = {
    "fb": FBFW(),
    "zalo": ZaloFW(),
    "discord": DiscordFW(),
    "telegram": TelegramFW(),
    "gmail": GmailFW(),
    "ig": IGFW(),
    "wechat": WeChatFW(),
    "sms": SMSFW(),
}
