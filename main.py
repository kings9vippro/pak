# ============================================================
# BOT BY ANH KHÔI — ALB FORGE v8.1
# Telegram: 8845944331:AAEN9CM-mui0Ga_HFENi9I52EcxsWtgg8Sk
# Admin: 6094686933
# All-in-one: Zalo QR + Rotate acc + Nhây + Anti-ban v4
# Đã fix lỗi Playwright Chromium path
# ============================================================

# ============ IMPORTS ============
import os
import sys
import re
import json
import time
import random
import threading
import asyncio
import warnings
import hashlib
import base64
import string
import subprocess
from io import BytesIO
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Dict, List

warnings.filterwarnings("ignore")

import requests
import qrcode
from Crypto.Cipher import AES

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from telegram.constants import ParseMode


# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "8845944331:AAEN9CM-mui0Ga_HFENi9I52EcxsWtgg8Sk"
)
ADMIN_IDS = [
    int(x) for x in
    os.environ.get("ADMIN_IDS", "6094686933").split(",")
    if x.strip().isdigit()
]
DATA_DIR = os.environ.get("DATA_DIR", "/tmp/alb_data")
os.makedirs(DATA_DIR, exist_ok=True)

QR_TTL = 120
MIN_SAFE_DELAY = 3.0


# ============================================================
# HTTP SERVER GIẢ — Giữ Render Free không kill worker
# ============================================================
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "5")
        self.end_headers()
        self.wfile.write(b"alive")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _start_health_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        print(f"[HEALTH] HTTP server on port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"[HEALTH] Lỗi: {e}")


# ============================================================
# UTILS
# ============================================================
_FALLBACK_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def random_ua():
    return random.choice(_FALLBACK_UAS)


def get_uptime(start: datetime) -> str:
    e = (datetime.now() - start).total_seconds()
    h, r = divmod(int(e), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def gen_imei() -> str:
    return "".join(random.choices(string.digits, k=15))


def jitter(base: float, f: float = 0.4) -> float:
    return base * random.uniform(1 - f, 1 + f)


# ============================================================
# TASK MANAGER
# ============================================================
class Task:
    __slots__ = ("id", "type", "owner", "stop", "start", "thread", "meta")

    def __init__(self, id, type, owner, meta=None):
        self.id = id
        self.type = type
        self.owner = owner
        self.stop = threading.Event()
        self.start = datetime.now()
        self.thread = None
        self.meta = meta or {}

    def uptime(self):
        return get_uptime(self.start)


class Tasks:
    def __init__(self):
        self.d = {}
        self.lock = threading.Lock()

    def add(self, t):
        with self.lock:
            self.d[t.id] = t

    def remove(self, tid):
        with self.lock:
            t = self.d.pop(tid, None)
            if t:
                t.stop.set()
            return t

    def by_owner(self, o):
        with self.lock:
            return [t for t in self.d.values() if t.owner == o]


TASKS = Tasks()


def new_tid(p):
    return f"{p}_{int(time.time()*1000)}"


# ============================================================
# FIREWALL v7 — 7 lớp
# ============================================================
class RequestShaper:
    ORDER = [
        "Host", "Connection", "Content-Length",
        "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
        "Upgrade-Insecure-Requests", "User-Agent", "Accept",
        "Sec-Fetch-Site", "Sec-Fetch-Mode", "Sec-Fetch-User",
        "Sec-Fetch-Dest", "Referer", "Accept-Encoding",
        "Accept-Language", "Cookie", "Origin", "DNT",
        "X-FB-Friendly-Name", "X-FB-LSD",
    ]

    def shape(self, headers):
        out = {}
        for k in self.ORDER:
            if k in headers:
                out[k] = headers[k]
        for k, v in headers.items():
            if k not in out:
                out[k] = v
        return out


class FingerprintPool:
    PLAT = [
        ("Windows NT 10.0; Win64; x64", False, "Windows"),
        ("Macintosh; Intel Mac OS X 10_15_7", False, "macOS"),
        ("X11; Linux x86_64", False, "Linux"),
        ("iPhone; CPU iPhone OS 17_2 like Mac OS X", True, "iOS"),
        ("Linux; Android 14; SM-S918B", True, "Android"),
    ]
    CHROME = ["120.0.0.0", "121.0.0.0", "122.0.0.0", "123.0.0.0", "124.0.0.0"]

    def _gen(self):
        p, mobile, brand = random.choice(self.PLAT)
        v = random.choice(self.CHROME)
        if mobile:
            ua = f"Mozilla/5.0 ({p}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Mobile Safari/537.36"
        else:
            ua = f"Mozilla/5.0 ({p}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36"
        return {
            "ua": ua, "brand": brand, "mobile": mobile, "chrome_v": v,
            "lang": random.choice(["vi-VN,vi;q=0.9", "en-US,en;q=0.9"]),
        }

    def headers(self, fp, extra=None):
        h = {
            "User-Agent": fp["ua"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": fp["lang"],
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
            "sec-ch-ua": f'"Chromium";v="{fp["brand"]}", "Not A;Brand";v="24"',
            "sec-ch-ua-mobile": "?1" if fp["mobile"] else "?0",
            "sec-ch-ua-platform": f'"{fp["brand"]}"',
        }
        if extra:
            h.update(extra)
        return h


class Behavior:
    @staticmethod
    def typing(text):
        n = len(text)
        if n == 0:
            return 0.5
        return min(4.0, n * random.uniform(0.03, 0.09))

    @staticmethod
    def pre_send():
        time.sleep(random.uniform(0.8, 3.0))

    @staticmethod
    def maybe_break():
        r = random.random()
        if r < 0.012:
            time.sleep(random.uniform(90, 480))
        elif r < 0.06:
            time.sleep(random.uniform(8, 45))

    @staticmethod
    def humanize(text):
        v = [text]
        if random.random() < 0.35:
            v.append(f"{text} {random.choice('😀😅🤣😏😎🙃😹👍🔥')}")
        if random.random() < 0.4:
            v.append(f"{text}{random.choice(['...', '..', '!', '?', '!!'])}")
        if random.random() < 0.15:
            v.append(text.replace(" ", "  ", 1))
        return random.choice(v)

    @staticmethod
    def typo(t, p=0.05):
        if random.random() > p:
            return t
        chars = list(t)
        for _ in range(random.randint(1, 2)):
            i = random.randint(0, len(chars) - 1)
            if chars[i].isalpha():
                chars[i] = random.choice("abcdefghijklmnopqrstuvwxyz")
        return "".join(chars)

    @staticmethod
    def vary(t):
        r = random.random()
        if r < 0.2:
            return t[:max(1, len(t) // 2)]
        if r < 0.35:
            return t + " " + random.choice(["ok", "ừ", "hmm", "..."])
        return t

    @staticmethod
    def entropy_mask(t):
        if random.random() < 0.12:
            zw = random.choice(["\u200b", "\u200c", "\u200d", "\ufeff"])
            pos = random.randint(1, max(1, len(t) - 1))
            t = t[:pos] + zw + t[pos:]
        return t


class MultiCircuit:
    def __init__(self):
        self.results = deque(maxlen=25)
        self.opened_at = None

    def record(self, ok):
        self.results.append(ok)
        if self._should_open():
            self.opened_at = time.time()

    def _should_open(self):
        if self.opened_at:
            if time.time() - self.opened_at > 60:
                self.opened_at = None
                self.results.clear()
                return False
            return True
        if len(self.results) < 20:
            return False
        fail = 1 - sum(self.results) / len(self.results)
        return fail >= 0.6

    def is_open(self):
        return bool(self.opened_at)


class Firewall:
    name = "base"
    BASE_DELAY = 3.0
    RETRY = 4
    BACKOFF = 1.5

    def __init__(self):
        self.shaper = RequestShaper()
        self.fp_pool = FingerprintPool()
        self.behavior = Behavior()
        self.cb = MultiCircuit()
        self.lock = threading.Lock()
        self.stats = {"ok": 0, "fail": 0}
        self.cookie_fp = {}

    def _fp_for(self, cookie):
        if not cookie:
            return self.fp_pool._gen()
        h = hashlib.md5(cookie.encode()).hexdigest()[:12]
        with self.lock:
            if h not in self.cookie_fp:
                self.cookie_fp[h] = self.fp_pool._gen()
            if random.random() < 0.005:
                self.cookie_fp[h] = self.fp_pool._gen()
            return self.cookie_fp[h]

    def request(self, method, url, cookie=None, **kw):
        while self.cb.is_open():
            time.sleep(2)

        headers = self.shaper.shape(
            self.fp_pool.headers(self._fp_for(cookie), kw.pop("headers", {}))
        )
        timeout = kw.pop("timeout", 25)

        if cookie and "Cookie" not in headers:
            headers["Cookie"] = cookie

        for attempt in range(self.RETRY):
            time.sleep(jitter(self.BASE_DELAY, 0.25))
            try:
                r = requests.request(method, url, headers=headers,
                                     timeout=timeout, verify=False, **kw)
                if r.status_code in (200, 201, 204):
                    with self.lock:
                        self.stats["ok"] += 1
                    self.cb.record(True)
                    return r
                if r.status_code in (429, 403):
                    self.cb.record(False)
                    time.sleep(min(60, self.BACKOFF * (2 ** attempt)))
                    continue
                self.cb.record(False)
            except Exception:
                self.cb.record(False)
            time.sleep(self.BACKOFF * (2 ** attempt))

        with self.lock:
            self.stats["fail"] += 1
        return None

    def get(self, u, **k):
        return self.request("GET", u, **k)

    def post(self, u, **k):
        return self.request("POST", u, **k)

    def report(self):
        with self.lock:
            s = self.stats
        cb = "OPEN" if self.cb.is_open() else "OK"
        return f"🛡 *{self.name}* OK:`{s['ok']}` Fail:`{s['fail']}` CB:`{cb}`"


class FBFW(Firewall):
    name = "Facebook"
    BASE_DELAY = 4.0
    RETRY = 5


class ZaloFW(Firewall):
    name = "Zalo"
    BASE_DELAY = 3.0


class DiscordFW(Firewall):
    name = "Discord"
    BASE_DELAY = 3.0


class TelegramFW(Firewall):
    name = "Telegram"
    BASE_DELAY = 3.0


class GmailFW(Firewall):
    name = "Gmail"
    BASE_DELAY = 10.0


class IGFW(Firewall):
    name = "Instagram"
    BASE_DELAY = 8.0


class WeChatFW(Firewall):
    name = "WeChat"
    BASE_DELAY = 4.0


class SMSFW(Firewall):
    name = "SMS"
    BASE_DELAY = 5.0


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


# ============================================================
# ANTI-BAN v4 — Học hành vi từng acc
# ============================================================
@dataclass
class AccBehavior:
    uid: str
    ok: int = 0
    fail: int = 0
    streak_fail: int = 0
    cooldown_until: float = 0
    risk: float = 0.0
    current_delay: float = 3.0
    hourly_count: dict = field(default_factory=dict)


class AntiBanV4:
    MAX_PER_HOUR = 120
    DELAY_MIN = 3.0
    DELAY_MAX = 120.0

    def __init__(self):
        self.behavior = {}
        self.lock = threading.Lock()

    def _get(self, uid):
        with self.lock:
            if uid not in self.behavior:
                self.behavior[uid] = AccBehavior(uid=uid)
            return self.behavior[uid]

    def record(self, uid, ok):
        b = self._get(uid)
        with self.lock:
            now = time.time()
            if ok:
                b.ok += 1
                b.streak_fail = 0
            else:
                b.fail += 1
                b.streak_fail += 1
            h = time.localtime(now).tm_hour
            b.hourly_count[h] = b.hourly_count.get(h, 0) + 1
            total = b.ok + b.fail
            if total > 0:
                b.risk = min(1.0, (b.fail / total) * 0.6 +
                             min(1.0, b.streak_fail / 5) * 0.4)
            if b.streak_fail >= 5:
                b.cooldown_until = now + 300
                b.streak_fail = 0
            if b.fail >= 15 and b.ok / max(b.fail, 1) < 0.2:
                b.cooldown_until = now + 1800
            base = self.DELAY_MIN
            if b.risk > 0.7:
                base = 30
            elif b.risk > 0.5:
                base = 15
            elif b.risk > 0.3:
                base = 8
            if b.hourly_count.get(h, 0) > self.MAX_PER_HOUR:
                base *= 2
            b.current_delay = min(self.DELAY_MAX, base)

    def in_cooldown(self, uid):
        b = self._get(uid)
        with self.lock:
            return max(0.0, b.cooldown_until - time.time())

    def get_delay(self, uid):
        b = self._get(uid)
        with self.lock:
            return b.current_delay

    def get_risk(self, uid):
        b = self._get(uid)
        with self.lock:
            return b.risk

    def is_sleep_hour(self):
        return 0 <= time.localtime().tm_hour < 6

    def sleep_delay(self):
        return random.uniform(5, 15) if self.is_sleep_hour() else 0.0

    def stats(self, uid):
        b = self._get(uid)
        with self.lock:
            return {
                "uid": uid, "ok": b.ok, "fail": b.fail, "risk": b.risk,
                "cooldown_left": max(0, b.cooldown_until - time.time()),
                "current_delay": b.current_delay,
            }


ANTIBAN4 = AntiBanV4()


# ============================================================
# ACCOUNT POOL
# ============================================================
class AccountPool:
    def __init__(self):
        self.accounts = []
        self.lock = threading.Lock()
        self.cooldown_until = {}

    def add(self, imei, cookies, label=None):
        with self.lock:
            uid = cookies.get("zalo_u_id") or imei
            for a in self.accounts:
                if a["uid"] == uid:
                    return False
            self.accounts.append({
                "uid": uid, "imei": imei, "cookies": cookies,
                "label": label or uid[:8], "enabled": True,
                "ok_count": 0, "fail_count": 0, "last_used": 0,
            })
            return True

    def list_all(self):
        with self.lock:
            return list(self.accounts)

    def size(self):
        with self.lock:
            return len([a for a in self.accounts if a["enabled"]])

    def next_account(self, min_gap=1.0):
        with self.lock:
            if not self.accounts:
                return None
            now = time.time()
            enabled = [a for a in self.accounts if a["enabled"]]
            enabled.sort(key=lambda a: a["last_used"])
            for acc in enabled:
                if self.cooldown_until.get(acc["uid"], 0) > now:
                    continue
                if now - acc["last_used"] < min_gap:
                    continue
                acc["last_used"] = now
                return acc
            return None

    def report_ok(self, uid):
        with self.lock:
            for a in self.accounts:
                if a["uid"] == uid:
                    a["ok_count"] += 1
                    break

    def report_fail(self, uid, cooldown=60):
        with self.lock:
            for a in self.accounts:
                if a["uid"] == uid:
                    a["fail_count"] += 1
                    if a["fail_count"] % 3 == 0:
                        self.cooldown_until[uid] = time.time() + cooldown
                    if a["fail_count"] >= 10 and a["ok_count"] / max(a["fail_count"], 1) < 0.2:
                        a["enabled"] = False
                    break


POOL = AccountPool()


# ============================================================
# COOKIE VAULT
# ============================================================
class CookieVault:
    def __init__(self):
        self.path = os.path.join(DATA_DIR, "vault.json")
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return {"accounts": []}
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"accounts": []}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add(self, uid, imei, cookies, label="", platform="zalo"):
        with self.lock:
            for a in self.data["accounts"]:
                if a.get("uid") == uid and a.get("platform") == platform:
                    return False
            self.data["accounts"].append({
                "uid": uid, "imei": imei, "cookies": cookies,
                "label": label or uid[:8], "platform": platform,
                "added_at": time.time(),
            })
            self._save()
            return True

    def list_all(self, platform=None):
        with self.lock:
            if platform:
                return [a for a in self.data["accounts"] if a["platform"] == platform]
            return list(self.data["accounts"])

    def remove(self, uid, platform="zalo"):
        with self.lock:
            before = len(self.data["accounts"])
            self.data["accounts"] = [
                a for a in self.data["accounts"]
                if not (a["uid"] == uid and a["platform"] == platform)
            ]
            if len(self.data["accounts"]) < before:
                self._save()
                return True
            return False


VAULT = CookieVault()


# ============================================================
# ZALO TOOLS
# ============================================================
ZALO_TEXT_COLORS = [
    {"name": "Đỏ", "code": "red"},
    {"name": "Hồng", "code": "pink"},
    {"name": "Tím", "code": "purple"},
    {"name": "Xanh dương", "code": "blue"},
    {"name": "Xanh biển", "code": "ocean"},
    {"name": "Xanh lá", "code": "green"},
    {"name": "Vàng", "code": "yellow"},
    {"name": "Cam", "code": "orange"},
    {"name": "Nâu", "code": "brown"},
    {"name": "Đen", "code": "black"},
    {"name": "Xám", "code": "gray"},
    {"name": "Trắng", "code": "white"},
]


class Zalo:
    def __init__(self, imei, cookies):
        self.imei = imei
        self.cookies = cookies
        self.fw = FW["zalo"]
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://chat.zalo.me",
            "Referer": "https://chat.zalo.me/",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        })
        self.s.cookies.update(cookies)
        self.uid = None
        self.secret_key = None
        self._login()

    def _login(self):
        r = self.s.get(
            "https://wpa.chat.zalo.me/api/login/getLoginInfo",
            params={"imei": self.imei, "type": 30,
                    "client_version": 645, "ts": int(time.time() * 1000)},
            timeout=20,
        )
        d = r.json()
        ud = d.get("data")
        if not isinstance(ud, dict):
            raise Exception("Cookie/IMEI sai")
        self.uid = ud.get("send2me_id")
        self.secret_key = ud.get("zpw_enk")
        if not self.secret_key:
            raise Exception("Không lấy được secret_key")

    def _enc(self, params):
        key = base64.b64decode(self.secret_key)
        cipher = AES.new(key, AES.MODE_CBC, bytes(16))
        pt = json.dumps(params).encode()
        pad = AES.block_size - len(pt) % AES.block_size
        pt += bytes([pad]) * pad
        return base64.b64encode(cipher.encrypt(pt)).decode()

    def _dec(self, enc):
        key = base64.b64decode(self.secret_key)
        cipher = AES.new(key, AES.MODE_CBC, bytes(16))
        d = cipher.decrypt(base64.b64decode(enc))
        return d[:-d[-1]].decode("utf-8", "ignore")

    def groups(self):
        r = self.s.get(
            "https://tt-group-wpa.chat.zalo.me/api/group/getlg/v4",
            params={"zpw_ver": 645, "zpw_type": 30}, timeout=20,
        )
        dec = self._dec(r.json()["data"])
        grid = json.loads(dec).get("data", {}).get("gridVerMap", {})
        out = []
        for gid in grid:
            info = self.group_info(gid)
            out.append({"id": gid, "name": info["name"],
                        "members": info["totalMember"]})
        return out

    def group_info(self, gid):
        enc = self._enc({"gridVerMap": json.dumps({str(gid): 0})})
        r = self.s.post(
            "https://tt-group-wpa.chat.zalo.me/api/group/getmg-v2",
            params={"zpw_ver": 645, "zpw_type": 30},
            data={"params": enc}, timeout=20,
        )
        dec = self._dec(r.json()["data"])
        info = json.loads(dec).get("data", {}).get("gridInfoMap", {}).get(str(gid), {})
        return {"name": info.get("name", "?"),
                "totalMember": info.get("totalMember", "?")}

    def send(self, msg, thread_id, is_group=True, color=None):
        url = ("https://tt-group-wpa.chat.zalo.me/api/group/sendmsg"
               if is_group
               else "https://tt-chat2-wpa.chat.zalo.me/api/message/sms")
        pl = {"message": msg, "clientId": str(int(time.time() * 1000)),
              "imei": self.imei}
        if color:
            pl["msgColor"] = color
        if is_group:
            pl["visibility"] = 0
            pl["grid"] = str(thread_id)
        else:
            pl["toid"] = str(thread_id)
        enc = self._enc(pl)
        return self.s.post(url, params={"zpw_ver": 645, "zpw_type": 30},
                           data={"params": enc}, timeout=20)

    def set_typing(self, thread_id, is_group=True):
        if is_group:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/typing"
            pl = {"grid": str(thread_id), "imei": self.imei}
        else:
            url = "https://tt-chat1-wpa.chat.zalo.me/api/message/typing"
            pl = {"toid": str(thread_id), "destType": 3, "imei": self.imei}
        enc = self._enc(pl)
        try:
            self.s.post(url, params={"zpw_ver": 645, "zpw_type": 30},
                        data={"params": enc}, timeout=10)
        except Exception:
            pass


# ============================================================
# ZALO QR — Playwright (auto-install Chromium nếu thiếu)
# ============================================================
class ZaloQRLogin:
    def __init__(self):
        self.browser = None
        self.page = None
        self.playwright = None

    async def _start(self):
        # --- Đảm bảo có playwright ---
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("[QR] Playwright chưa cài → pip install...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                check=True,
            )
            from playwright.async_api import async_playwright

        # --- Thử launch, nếu thiếu Chromium thì cài rồi thử lại ---
        last_err = None
        for attempt in range(2):
            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-blink-features=AutomationControlled",
                        "--window-size=600,800",
                    ],
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "Executable doesn't exist" in err_str and attempt == 0:
                    print("[QR] Chromium chưa có → tự cài...")
                    try:
                        subprocess.run(
                            [sys.executable, "-m", "playwright", "install", "chromium"],
                            timeout=300,
                            check=True,
                        )
                        print("[QR] Đã cài Chromium xong, thử lại...")
                    except Exception as e2:
                        print(f"[QR] Không cài được: {e2}")
                    try:
                        if self.playwright:
                            await self.playwright.stop()
                    except Exception:
                        pass
                    continue
                raise

        if last_err:
            raise last_err

        ctx = await self.browser.new_context(
            viewport={"width": 600, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="vi-VN",
        )
        self.page = await ctx.new_page()

    async def create_qr(self):
        try:
            await self._start()
            await self.page.goto("https://chat.zalo.me/",
                                 wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            try:
                btn = await self.page.wait_for_selector("text=/QR|Quét mã/i",
                                                       timeout=5000)
                await btn.click()
                await asyncio.sleep(2)
            except Exception:
                pass
            await asyncio.sleep(3)

            png = await self.page.screenshot(full_page=False)
            try:
                from PIL import Image
                img = Image.open(BytesIO(png))
                w, h = img.size
                img = img.crop((int(w * 0.15), int(h * 0.15),
                                int(w * 0.85), int(h * 0.85)))
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                png = buf.getvalue()
            except Exception:
                pass

            return {
                "qr_id": hashlib.md5(str(time.time()).encode()).hexdigest(),
                "qr_image": BytesIO(png),
                "ttl": QR_TTL,
            }
        except Exception as e:
            await self._close()
            return {"error": f"Lỗi tạo QR: {e}"}

    async def poll_login(self, qr_id=None, stop_event=None):
        start = time.time()
        while time.time() - start < QR_TTL:
            if stop_event and stop_event.is_set():
                return {"error": "Stopped"}
            try:
                url = self.page.url
                if "chat.zalo.me" in url and "login" not in url:
                    return await self._extract()
                if "id.zalo.me" in url and "account" not in url:
                    return await self._extract()
            except Exception:
                pass
            await asyncio.sleep(2)
        await self._close()
        return {"error": "Hết hạn QR (120s)"}

    async def _extract(self):
        try:
            await asyncio.sleep(3)
            cookies = await self.page.context.cookies()
            ck = {}
            for c in cookies:
                if "zalo" in c.get("domain", ""):
                    ck[c["name"]] = c["value"]
            imei = ""
            for k in ["imei", "zpw_imei", "device_id"]:
                try:
                    v = await self.page.evaluate(f"localStorage.getItem('{k}')")
                    if v:
                        imei = v
                        break
                except Exception:
                    pass
            secret = ""
            for k in ["zpw_enk", "secret_key"]:
                try:
                    v = await self.page.evaluate(f"localStorage.getItem('{k}')")
                    if v:
                        secret = v
                        break
                except Exception:
                    pass
            await self._close()
            if not ck:
                return {"error": "Không lấy được cookie"}
            return {
                "cookies": ck, "secret_key": secret,
                "uid": ck.get("zalo_u_id", ""),
                "imei": imei or "000000000000000",
            }
        except Exception as e:
            await self._close()
            return {"error": f"Extract: {e}"}

    async def _close(self):
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============================================================
# FACEBOOK TOOLS
# ============================================================
class Facebook:
    def __init__(self):
        self.fw = FW["fb"]

    def check(self, cookie):
        try:
            r = self.fw.get("https://mbasic.facebook.com/profile.php",
                            cookie=cookie)
            if not r or r.status_code != 200:
                return None
            name = re.search(r'<title>(.*?)</title>', r.text)
            uid = re.search(r"c_user=(\d+)", cookie)
            return {"name": name.group(1).strip() if name else "?",
                    "uid": uid.group(1) if uid else "?"}
        except Exception:
            return None

    def send(self, cookie, box_id, text):
        m = re.search(r"c_user=(\d+)", cookie)
        if not m:
            return None
        uid = m.group(1)
        h = {"Cookie": cookie}
        r = self.fw.get("https://www.facebook.com/", headers=h)
        if not r:
            return None
        fb_dtsg = re.search(r'"token":"(.*?)"', r.text)
        if not fb_dtsg:
            fb_dtsg = re.search(r'name="fb_dtsg" value="(.*?)"', r.text)
        if not fb_dtsg:
            return None
        fb_dtsg = fb_dtsg.group(1)
        jazoest = re.search(r'jazoest=(\d+)', r.text)
        jazoest = jazoest.group(1) if jazoest else "22036"

        self.fw.behavior.pre_send()
        text = self.fw.behavior.entropy_mask(
            self.fw.behavior.vary(
                self.fw.behavior.typo(
                    self.fw.behavior.humanize(text))))

        ts = int(time.time() * 1000)
        data = {
            "thread_fbid": box_id,
            "action_type": "ma-type:user-generated-message",
            "body": text,
            "client": "mercury",
            "author": f"fbid:{uid}",
            "timestamp": ts,
            "offline_threading_id": ts,
            "message_id": ts,
            "source": "source:chat:web",
            "ephemeral_ttl_mode": "0",
            "__user": uid, "__a": "1", "__req": "1b", "__rev": "1015919737",
            "fb_dtsg": fb_dtsg, "jazoest": jazoest,
        }
        h2 = {
            "Cookie": cookie,
            "Origin": "https://www.facebook.com",
            "Referer": f"https://www.facebook.com/messages/t/{box_id}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        time.sleep(min(self.fw.behavior.typing(text), 4.0))
        return self.fw.post("https://www.facebook.com/messaging/send/",
                            data=data, headers=h2)


# ============================================================
# ZALO ROTATE SPAM
# ============================================================
class ZaloRotateSpam:
    def __init__(self, targets, messages, min_gap=1.0, use_color=True):
        self.targets = targets
        self.messages = messages
        self.min_gap = max(1.0, min_gap)
        self.use_color = use_color
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        i_msg = 0
        i_color = 0
        i_target = 0
        color_codes = [c["code"] for c in ZALO_TEXT_COLORS]

        while not self.stop.is_set():
            acc = POOL.next_account(min_gap=self.min_gap)
            if not acc:
                time.sleep(1)
                continue

            uid = acc["uid"]
            if ANTIBAN4.in_cooldown(uid) > 0:
                time.sleep(1)
                continue

            target = self.targets[i_target % len(self.targets)]
            i_target += 1
            msg = self.messages[i_msg % len(self.messages)]
            i_msg += 1
            color = color_codes[i_color % len(color_codes)] if self.use_color else None
            i_color += 1

            try:
                z = Zalo(acc["imei"], acc["cookies"])
                FW["zalo"].behavior.pre_send()
                msg_h = FW["zalo"].behavior.humanize(msg)
                msg_h = FW["zalo"].behavior.entropy_mask(
                    FW["zalo"].behavior.vary(
                        FW["zalo"].behavior.typo(msg_h)))
                z.set_typing(target, is_group=True)
                time.sleep(min(FW["zalo"].behavior.typing(msg_h), 3.0))
                r = z.send(msg_h, target, is_group=True, color=color)
                ok = bool(r and r.status_code == 200)
                ANTIBAN4.record(uid, ok)
                if ok:
                    POOL.report_ok(uid)
                else:
                    POOL.report_fail(uid)
                print(f"[ROTATE] {acc['label']} → {target} [{'✅' if ok else '❌'}] {msg_h[:30]}")
            except Exception as e:
                ANTIBAN4.record(uid, False)
                POOL.report_fail(uid)
                print(f"[ROTATE] Lỗi {acc['label']}: {e}")

            delay = max(self.min_gap, ANTIBAN4.get_delay(uid))
            delay += ANTIBAN4.sleep_delay()
            delay *= random.uniform(0.9, 1.2)
            end = time.time() + delay
            while time.time() < end:
                if self.stop.is_set():
                    return
                time.sleep(0.1)


# ============================================================
# ZALO NHÂY / TAG / NGÔN
# ============================================================
class ZaloNhay(ZaloRotateSpam):
    def __init__(self, targets, messages, min_gap=1.0, tag_user=None):
        super().__init__(targets, messages, min_gap, use_color=False)
        self.tag_user = tag_user

    def _run(self):
        i = 0
        while not self.stop.is_set():
            for target in self.targets:
                if self.stop.is_set():
                    return
                acc = POOL.next_account(min_gap=self.min_gap)
                if not acc:
                    time.sleep(1)
                    continue
                uid = acc["uid"]
                if ANTIBAN4.in_cooldown(uid) > 0:
                    continue

                msg = self.messages[i % len(self.messages)]
                i += 1
                try:
                    z = Zalo(acc["imei"], acc["cookies"])
                    FW["zalo"].behavior.pre_send()
                    if self.tag_user:
                        msg_send = f"@{self.tag_user} {msg}"
                    else:
                        msg_send = FW["zalo"].behavior.humanize(msg)
                    z.set_typing(target, is_group=True)
                    time.sleep(min(FW["zalo"].behavior.typing(msg_send), 3.0))
                    r = z.send(msg_send, target, is_group=True)
                    ok = bool(r and r.status_code == 200)
                    ANTIBAN4.record(uid, ok)
                    if ok:
                        POOL.report_ok(uid)
                    else:
                        POOL.report_fail(uid)
                    print(f"[NHAY] {acc['label']} → {target} [{'✅' if ok else '❌'}]")
                except Exception as e:
                    ANTIBAN4.record(uid, False)
                    POOL.report_fail(uid)
                    print(f"[NHAY] Lỗi: {e}")

                delay = max(self.min_gap, ANTIBAN4.get_delay(uid))
                delay *= random.uniform(0.9, 1.3)
                end = time.time() + delay
                while time.time() < end:
                    if self.stop.is_set():
                        return
                    time.sleep(0.1)


# ============================================================
# COOKIE GUIDE
# ============================================================
COOKIE_FB = """📘 LẤY COOKIE FACEBOOK

Cần: c_user, xs, datr, fr, sb

Kiwi Browser (Android):
1. Cài Kiwi + extension Cookie Editor
2. facebook.com → login
3. Extension → Export JSON → Copy

Test: /fb_check <cookie>
"""

COOKIE_ZALO = """📞 LẤY COOKIE ZALO

Cách 1 — QR (khuyến nghị):
/zalo_qr → quét 120s → bot tự lưu cookie + IMEI

Cách 2 — Thủ công:
1. Kiwi → chat.zalo.me → login
2. Cookie Editor → Export
3. Cần: zpw_sek, zpw_ver=645, zpw_type=30

Gửi bot:
/add_acc <imei>|<cookie_json>
"""

COOKIE_DISCORD = "🎮 Discord: F12 → Console → lấy token"


# ============================================================
# MENU
# ============================================================
MAIN_KB = [
    [InlineKeyboardButton("📘 Facebook", callback_data="m_fb"),
     InlineKeyboardButton("📞 Zalo", callback_data="m_zalo")],
    [InlineKeyboardButton("🎯 Rotate acc", callback_data="m_rotate"),
     InlineKeyboardButton("🎭 Treo nhây", callback_data="m_nhay")],
    [InlineKeyboardButton("🔐 Acc pool", callback_data="m_pool"),
     InlineKeyboardButton("🎮 Discord", callback_data="m_discord")],
    [InlineKeyboardButton("📢 Telegram", callback_data="m_telegram"),
     InlineKeyboardButton("✉ Gmail", callback_data="m_gmail")],
    [InlineKeyboardButton("📲 SMS", callback_data="m_sms"),
     InlineKeyboardButton("📷 Instagram", callback_data="m_ig")],
    [InlineKeyboardButton("💼 WeChat", callback_data="m_wechat"),
     InlineKeyboardButton("🛡 Firewall", callback_data="m_fw")],
    [InlineKeyboardButton("⚙ Rate", callback_data="m_rate"),
     InlineKeyboardButton("📖 Guide", callback_data="m_guide")],
    [InlineKeyboardButton("📋 Tasks", callback_data="m_tasks"),
     InlineKeyboardButton("🔥 Cool", callback_data="m_cool")],
]

MENU_TEXT = {
    "m_fb": ("📘 *Facebook*\n\n"
             "`/fb_check <cookie>`\n"
             "`/fb_send <cookie>|<box>|<msg>`\n"
             "`/fb_spam <cookie>|<box1,box2>|<msg1;msg2>|<delay>`"),
    "m_zalo": ("📞 *Zalo*\n\n"
               "`/zalo_qr` — QR login\n"
               "`/zalo_check <imei>|<cookie>`\n"
               "`/zalo_groups <imei>|<cookie>`\n"
               "`/zalo_spam <imei>|<cookie>|<gid>|<msg>|<delay>`"),
    "m_rotate": ("🎯 *Rotate đa acc*\n\n"
                 "`/add_acc <imei>|<cookie_json>|<label>`\n"
                 "`/list_acc`\n"
                 "`/zalo_rotate <gid1,gid2>|<msg1;msg2>|<min_gap>`\n"
                 "_Mỗi 1s đổi acc luân phiên — không trùng_"),
    "m_nhay": ("🎭 *Treo nhây*\n\n"
               "`/zalo_nhay <gid1,gid2>|<msg1;msg2>|<gap>`\n"
               "`/zalo_tag <gid>|<msg>|<tag_user>|<gap>`\n"
               "`/zalo_ngon <gid>|<msg_dài1;msg_dài2>|<gap>`"),
    "m_pool": ("🔐 *Acc Pool*\n\n"
               "`/list_acc` — xem pool\n"
               "`/acc_risk <uid>` — risk score\n"
               "`/vault` — xem vault\n"
               "`/del_acc <uid>` — xóa acc"),
    "m_discord": "🎮 `/discord_spam <token>|<channel>|<msg1;msg2>|<delay>`",
    "m_telegram": "📢 `/tele_spam <token>|<chat>|<msg1;msg2>|<delay>`",
    "m_gmail": "✉ `/gmail_spam <email>|<pass>|<to>|<msg1;msg2>|<delay>`",
    "m_sms": "📲 `/sms_spam <phone>`",
    "m_ig": "📷 `/ig_spam <sessionid>|<thread_ids>|<msg1;msg2>|<delay>`",
    "m_wechat": "💼 `/wechat_spam <corpid>|<secret>|<agent>|<user>|<msgs>|<delay>`",
    "m_fw": "🛡 `/fw_status` `/fw_reset`",
    "m_rate": f"⚙ Delay min {MIN_SAFE_DELAY}s. Dùng /rate để xem.",
    "m_guide": "📖 `/cookie_fb` `/cookie_zalo` `/cookie_discord`",
    "m_cool": "🔥 `/nick` `/uid_extract` `/ip_info` `/backup_all`",
    "m_tasks": "📋 `/tasks` `/stop <n>` `/stop_all`",
}


def admin_only(func):
    async def w(update, ctx):
        if update.effective_user.id not in ADMIN_IDS:
            if update.message:
                await update.message.reply_text("⛔ Không có quyền. Bot by Anh Khôi.")
            return
        return await func(update, ctx)
    return w


# ============================================================
# HANDLERS - START
# ============================================================
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Không có quyền.")
        return
    await update.message.reply_text(
        "🔥 *ALB FORGE v8.1*\n"
        "_Bot by Anh Khôi_\n"
        f"_Pool: {POOL.size()} acc_\n\n"
        "Chọn chức năng:",
        reply_markup=InlineKeyboardMarkup(MAIN_KB),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cb_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data in MENU_TEXT:
        await q.edit_message_text(MENU_TEXT[q.data], parse_mode=ParseMode.MARKDOWN)
    elif q.data == "m_tasks":
        tasks = TASKS.by_owner(q.from_user.id)
        if not tasks:
            await q.edit_message_text("📭 Không có task.")
            return
        text = "*📋 Tasks:*\n\n"
        for i, t in enumerate(tasks, 1):
            text += f"`{i}.` [{t.type}] {t.uptime()}\n"
        text += "\n`/stop <n>` `/stop_all`"
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)


# ============================================================
# HANDLERS - ZALO QR
# ============================================================
@admin_only
async def cmd_zalo_qr(update, ctx):
    await update.message.reply_text("⏳ Đang khởi động browser... (5-15s lần đầu)")

    qr = ZaloQRLogin()
    try:
        info = await asyncio.get_event_loop().run_in_executor(
            None, lambda: run_async(qr.create_qr())
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi tạo QR: {e}")
        return

    if "error" in info:
        await update.message.reply_text(f"❌ {info['error']}")
        return

    await update.message.reply_photo(
        photo=info["qr_image"],
        caption=(
            f"📷 *Quét QR bằng app Zalo*\n\n"
            f"1. Mở Zalo → biểu tượng QR (góc phải trên)\n"
            f"2. Quét ảnh trên\n"
            f"3. Bấm *Đồng ý* trên điện thoại\n\n"
            f"⏱ Hết hạn: *{info['ttl']}s*\n"
            f"⏳ Đang chờ quét..."
        ),
        parse_mode=ParseMode.MARKDOWN,
    )

    result_box = {}

    def _poll():
        try:
            res = run_async(qr.poll_login(info["qr_id"]))
            result_box["r"] = res
        except Exception as e:
            result_box["r"] = {"error": str(e)}

    threading.Thread(target=_poll, daemon=True).start()

    for _ in range(info["ttl"]):
        await asyncio.sleep(1)
        if "r" in result_box:
            break

    res = result_box.get("r")
    if not res or "error" in res:
        await update.message.reply_text(
            f"❌ {res.get('error') if res else 'Timeout'}"
        )
        return

    imei = res.get("imei") or gen_imei()
    cookies = res.get("cookies", {})
    uid = cookies.get("zalo_u_id") or imei
    label = f"acc{POOL.size() + 1}"

    VAULT.add(uid, imei, cookies, label, "zalo")
    POOL.add(imei, cookies, label)

    cookie_str = json.dumps(cookies, indent=2, ensure_ascii=False)
    await update.message.reply_text(
        f"✅ *ĐĂNG NHẬP ZALO THÀNH CÔNG!*\n\n"
        f"🏷 Label: `{label}`\n"
        f"🆔 IMEI: `{imei}`\n"
        f"👤 UID: `{uid}`\n\n"
        f"🍪 Cookie:\n{cookie_str}\n\n"
        f"📊 Pool: *{POOL.size()} acc*\n"
        f"Dùng `/zalo_rotate` để bắt đầu."
    )


# ============================================================
# HANDLERS - ADD/LIST ACC
# ============================================================
@admin_only
async def cmd_add_acc(u, c):
    t = u.message.text.replace("/add_acc ", "", 1)
    p = t.split("|")
    if len(p) < 2:
        await u.message.reply_text(
            "Cú pháp: /add_acc <imei>|<cookie_json>|<label>"
        )
        return
    imei = p[0].strip()
    try:
        cookies = json.loads(p[1].strip())
    except Exception as e:
        await u.message.reply_text(f"❌ Cookie JSON sai: {e}")
        return
    label = p[2].strip() if len(p) > 2 else f"acc{POOL.size() + 1}"
    uid = cookies.get("zalo_u_id") or imei

    ok_pool = POOL.add(imei, cookies, label)
    VAULT.add(uid, imei, cookies, label, "zalo")

    if ok_pool:
        await u.message.reply_text(
            f"✅ Đã thêm `{label}` | Pool: `{POOL.size()}` acc",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await u.message.reply_text("⚠️ Acc đã tồn tại.")


@admin_only
async def cmd_list_acc(u, c):
    accs = POOL.list_all()
    if not accs:
        await u.message.reply_text("📭 Pool trống.")
        return
    text = f"📋 *Pool: {len(accs)} acc*\n\n"
    for i, a in enumerate(accs, 1):
        risk = ANTIBAN4.get_risk(a["uid"])
        cd = ANTIBAN4.in_cooldown(a["uid"])
        text += (
            f"`{i}.` *{a['label']}* "
            f"| OK:`{a['ok_count']}` Fail:`{a['fail_count']}` "
            f"| Risk:`{risk:.2f}` CD:`{cd:.0f}s` "
            f"| {'✅' if a['enabled'] else '❌'}\n"
        )
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_del_acc(u, c):
    if not c.args:
        await u.message.reply_text("Cú pháp: /del_acc <uid>")
        return
    uid = c.args[0].strip()
    VAULT.remove(uid, "zalo")
    with POOL.lock:
        POOL.accounts = [a for a in POOL.accounts if a["uid"] != uid]
    await u.message.reply_text(f"✅ Đã xóa `{uid}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_vault(u, c):
    accs = VAULT.list_all("zalo")
    if not accs:
        await u.message.reply_text("📭 Vault trống.")
        return
    text = f"🔐 *Vault: {len(accs)} acc*\n\n"
    for i, a in enumerate(accs[:30], 1):
        text += f"`{i}.` {a['label']} | UID: `{a['uid'][:16]}`\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_acc_risk(u, c):
    if not c.args:
        await u.message.reply_text("Cú pháp: /acc_risk <uid>")
        return
    st = ANTIBAN4.stats(c.args[0].strip())
    await u.message.reply_text(
        f"📊 *Acc Risk:*\n"
        f"• UID: `{st['uid']}`\n"
        f"• OK: `{st['ok']}`\n"
        f"• Fail: `{st['fail']}`\n"
        f"• Risk: `{st['risk']:.2f}`\n"
        f"• Cooldown: `{st['cooldown_left']:.0f}s`\n"
        f"• Delay: `{st['current_delay']:.1f}s`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ============================================================
# HANDLERS - ROTATE / NHÂY / TAG
# ============================================================
@admin_only
async def cmd_zalo_rotate(u, c):
    t = u.message.text.replace("/zalo_rotate ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "Cú pháp: /zalo_rotate <gid1,gid2>|<msg1;msg2>|<min_gap>"
        )
        return
    if POOL.size() == 0:
        await u.message.reply_text("❌ Pool trống. Dùng /zalo_qr trước.")
        return
    targets = [x.strip() for x in p[0].split(",") if x.strip()]
    msgs = [x.strip() for x in p[1].split(";") if x.strip()]
    min_gap = max(1.0, float(p[2].strip()))

    task = Task(new_tid("zalo_rotate"), "zalo_rotate", u.effective_user.id)
    spam = ZaloRotateSpam(targets, msgs, min_gap)
    task.stop = spam.stop
    spam.start()
    TASKS.add(task)

    await u.message.reply_text(
        f"✅ *Rotate task* `{task.id}`\n"
        f"• Targets: `{len(targets)}`\n"
        f"• Pool: `{POOL.size()}` acc\n"
        f"• Min gap: `{min_gap}s`\n"
        f"• Mỗi 1s đổi acc luân phiên — không trùng.",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_zalo_nhay(u, c):
    t = u.message.text.replace("/zalo_nhay ", "", 1)
    p = t.split("|")
    if len(p) < 2:
        await u.message.reply_text(
            "Cú pháp: /zalo_nhay <gid1,gid2>|<msg1;msg2>|<min_gap>"
        )
        return
    if POOL.size() == 0:
        await u.message.reply_text("❌ Pool trống.")
        return
    targets = [x.strip() for x in p[0].split(",") if x.strip()]
    msgs = [x.strip() for x in p[1].split(";") if x.strip()]
    min_gap = max(1.0, float(p[2].strip())) if len(p) > 2 else 1.0

    task = Task(new_tid("zalo_nhay"), "zalo_nhay", u.effective_user.id)
    nhay = ZaloNhay(targets, msgs, min_gap)
    task.stop = nhay.stop
    nhay.start()
    TASKS.add(task)
    await u.message.reply_text(
        f"✅ Nhây task `{task.id}`", parse_mode=ParseMode.MARKDOWN
    )


@admin_only
async def cmd_zalo_tag(u, c):
    t = u.message.text.replace("/zalo_tag ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "Cú pháp: /zalo_tag <gid1,gid2>|<msg1;msg2>|<tag_user>|<min_gap>"
        )
        return
    if POOL.size() == 0:
        await u.message.reply_text("❌ Pool trống.")
        return
    targets = [x.strip() for x in p[0].split(",") if x.strip()]
    msgs = [x.strip() for x in p[1].split(";") if x.strip()]
    tag_user = p[2].strip()
    min_gap = max(1.0, float(p[3].strip())) if len(p) > 3 else 1.0

    task = Task(new_tid("zalo_tag"), "zalo_tag", u.effective_user.id)
    tag = ZaloNhay(targets, msgs, min_gap, tag_user=tag_user)
    task.stop = tag.stop
    tag.start()
    TASKS.add(task)
    await u.message.reply_text(
        f"✅ Tag task `{task.id}` → @{tag_user}",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_zalo_ngon(u, c):
    t = u.message.text.replace("/zalo_ngon ", "", 1)
    p = t.split("|")
    if len(p) < 2:
        await u.message.reply_text(
            "Cú pháp: /zalo_ngon <gid>|<msg_dài1;msg_dài2>|<min_gap>"
        )
        return
    if POOL.size() == 0:
        await u.message.reply_text("❌ Pool trống.")
        return
    targets = [x.strip() for x in p[0].split(",") if x.strip()]
    msgs = [x.strip() for x in p[1].split(";") if x.strip()]
    min_gap = max(1.0, float(p[2].strip())) if len(p) > 2 else 1.0

    task = Task(new_tid("zalo_ngon"), "zalo_ngon", u.effective_user.id)
    ngon = ZaloNhay(targets, msgs, min_gap)
    task.stop = ngon.stop
    ngon.start()
    TASKS.add(task)
    await u.message.reply_text(
        f"✅ Ngôn task `{task.id}`", parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# HANDLERS - ZALO BASIC
# ============================================================
@admin_only
async def cmd_zalo_check(u, c):
    t = u.message.text.replace("/zalo_check ", "", 1)
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /zalo_check <imei>|<cookie>")
        return
    imei, ck = t.split("|", 1)
    try:
        z = Zalo(imei.strip(), json.loads(ck))
        await u.message.reply_text(f"✅ Zalo OK! UID: {z.uid}")
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_zalo_groups(u, c):
    t = u.message.text.replace("/zalo_groups ", "", 1)
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /zalo_groups <imei>|<cookie>")
        return
    imei, ck = t.split("|", 1)
    try:
        z = Zalo(imei.strip(), json.loads(ck))
        gs = z.groups()
        msg = f"📦 *{len(gs)} nhóm:*\n\n"
        for i, g in enumerate(gs[:60], 1):
            msg += f"`{i}.` {g['name'][:40]} — `{g['id']}`\n"
        await u.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_zalo_color_list(u, c):
    text = "*🎨 Bảng màu Zalo:*\n\n"
    for i, col in enumerate(ZALO_TEXT_COLORS, 1):
        text += f"`{i}.` {col['name']} — `{col['code']}`\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_zalo_spam(u, c):
    t = u.message.text.replace("/zalo_spam ", "", 1)
    p = t.split("|")
    if len(p) < 5:
        await u.message.reply_text(
            "Cú pháp: /zalo_spam <imei>|<cookie>|<gid>|<msg1;msg2>|<delay>"
        )
        return
    imei = p[0].strip()
    cookies = json.loads(p[1].strip())
    targets = [x.strip() for x in p[2].split(",") if x.strip()]
    msgs = [x.strip() for x in p[3].split(";") if x.strip()]
    delay = max(3.0, float(p[4].strip()))
    task = Task(new_tid("zalo_spam"), "zalo_spam", u.effective_user.id)

    def w():
        try:
            z = Zalo(imei, cookies)
            while not task.stop.is_set():
                for tid in targets:
                    if task.stop.is_set():
                        return
                    for msg in msgs:
                        if task.stop.is_set():
                            return
                        z.set_typing(tid, True)
                        time.sleep(random.uniform(1.5, 3))
                        r = z.send(msg, tid, True)
                        print(f"[zalo_spam] {tid}: {'✅' if r and r.status_code == 200 else '❌'}")
                        time.sleep(delay)
        except Exception as e:
            print(f"[zalo_spam] {e}")

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


# ============================================================
# HANDLERS - FACEBOOK
# ============================================================
@admin_only
async def cmd_fb_check(u, c):
    cookie = u.message.text.replace("/fb_check ", "", 1).strip()
    info = Facebook().check(cookie)
    if info:
        await u.message.reply_text(
            f"✅ Cookie sống\n👤 {info['name']}\n🆔 {info['uid']}"
        )
    else:
        await u.message.reply_text("❌ Cookie chết")


@admin_only
async def cmd_fb_send(u, c):
    text = u.message.text.replace("/fb_send ", "", 1)
    p = text.split("|")
    if len(p) < 3:
        await u.message.reply_text("Cú pháp: /fb_send <cookie>|<box>|<msg>")
        return
    r = Facebook().send(p[0].strip(), p[1].strip(), "|".join(p[2:]).strip())
    await u.message.reply_text(f"{'✅' if r and r.status_code == 200 else '❌'}")


@admin_only
async def cmd_fb_spam(u, c):
    text = u.message.text.replace("/fb_spam ", "", 1)
    p = text.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /fb_spam <cookie>|<box1,box2>|<msg1;msg2>|<delay>"
        )
        return
    cookie = p[0].strip()
    boxes = [x.strip() for x in p[1].split(",") if x.strip()]
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(3.0, float(p[3].strip()))
    task = Task(new_tid("fb_spam"), "fb_spam", u.effective_user.id)
    fb = Facebook()

    def w():
        i = 0
        while not task.stop.is_set():
            for box in boxes:
                if task.stop.is_set():
                    return
                msg = msgs[i % len(msgs)]
                i += 1
                fb.send(cookie, box, msg)
                time.sleep(delay * random.uniform(0.9, 1.3))
                FW["fb"].behavior.maybe_break()

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_fb_threads(u, c):
    await u.message.reply_text(
        "ℹ️ Dùng /fb_send trực tiếp với box ID."
    )


# ============================================================
# HANDLERS - DISCORD / TELEGRAM / GMAIL / SMS / IG / WECHAT
# ============================================================
@admin_only
async def cmd_discord_spam(u, c):
    t = u.message.text.replace("/discord_spam ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /discord_spam <token>|<channel>|<msg1;msg2>|<delay>"
        )
        return
    token, ch = p[0].strip(), p[1].strip()
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(3.0, float(p[3].strip()))
    task = Task(new_tid("discord"), "discord", u.effective_user.id)

    def w():
        i = 0
        while not task.stop.is_set():
            m = msgs[i % len(msgs)]
            i += 1
            FW["discord"].post(
                f"https://discord.com/api/v10/channels/{ch}/messages",
                json={"content": m},
                headers={"Authorization": token, "Content-Type": "application/json"},
            )
            time.sleep(delay)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_tele_spam(u, c):
    t = u.message.text.replace("/tele_spam ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /tele_spam <token>|<chat>|<msg1;msg2>|<delay>"
        )
        return
    token, ch = p[0].strip(), p[1].strip()
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(3.0, float(p[3].strip()))
    task = Task(new_tid("tele"), "telegram", u.effective_user.id)

    def w():
        i = 0
        while not task.stop.is_set():
            m = msgs[i % len(msgs)]
            i += 1
            try:
                FW["telegram"].post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data={"chat_id": ch, "text": m},
                )
            except Exception:
                pass
            time.sleep(delay)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_gmail_spam(u, c):
    t = u.message.text.replace("/gmail_spam ", "", 1)
    p = t.split("|")
    if len(p) < 5:
        await u.message.reply_text(
            "Cú pháp: /gmail_spam <email>|<pass>|<to>|<msg1;msg2>|<delay>"
        )
        return
    import smtplib
    import ssl as _ssl
    from email.mime.text import MIMEText

    email_ = p[0].strip()
    pw = p[1].strip()
    to = p[2].strip()
    msgs = [x.strip() for x in p[3].split(";") if x.strip()]
    delay = max(10.0, float(p[4].strip()))
    task = Task(new_tid("gmail"), "gmail", u.effective_user.id)

    def w():
        i = 0
        while not task.stop.is_set():
            m = msgs[i % len(msgs)]
            i += 1
            try:
                ctx = _ssl.create_default_context()
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
                    s.login(email_, pw)
                    msg = MIMEText(m)
                    msg["From"] = email_
                    msg["To"] = to
                    msg["Subject"] = " "
                    s.sendmail(email_, to, msg.as_string())
            except Exception as e:
                print(f"[gmail] {e}")
            time.sleep(delay)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_sms_spam(u, c):
    if not c.args:
        await u.message.reply_text("Cú pháp: /sms_spam <phone>")
        return
    phone = c.args[0].strip()
    if POOL.size() == 0:
        await u.message.reply_text("❌ Pool trống. Dùng /zalo_qr trước.")
        return

    task = Task(new_tid("sms"), "sms", u.effective_user.id)

    def w():
        while not task.stop.is_set():
            acc = POOL.next_account(min_gap=1.0)
            if not acc:
                time.sleep(1)
                continue
            try:
                z = Zalo(acc["imei"], acc["cookies"])
                msg = f"OTP: {random.randint(100000, 999999)}"
                print(f"[sms] {acc['label']} → {phone}: {msg}")
            except Exception as e:
                print(f"[sms] {e}")
            time.sleep(5)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(
        f"✅ Task SMS `{task.id}` cho `{phone}`",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_ig_spam(u, c):
    t = u.message.text.replace("/ig_spam ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /ig_spam <sessionid>|<threads>|<msgs>|<delay>"
        )
        return
    sid = p[0].strip()
    tids = [x.strip() for x in p[1].split(",") if x.strip()]
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(8.0, float(p[3].strip()))
    task = Task(new_tid("ig"), "ig", u.effective_user.id)

    def w():
        i = 0
        while not task.stop.is_set():
            for tid in tids:
                if task.stop.is_set():
                    return
                m = msgs[i % len(msgs)]
                i += 1
                try:
                    FW["ig"].post(
                        "https://i.instagram.com/api/v1/direct_v2/threads/broadcast/text/",
                        data={"text": m, "thread_ids": f"[{tid}]",
                              "action": "send_item"},
                        headers={"Cookie": f"sessionid={sid}",
                                 "X-IG-App-ID": "1217981644879628",
                                 "Content-Type": "application/x-www-form-urlencoded"},
                    )
                except Exception:
                    pass
                time.sleep(delay)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_wechat_spam(u, c):
    t = u.message.text.replace("/wechat_spam ", "", 1)
    p = t.split("|")
    if len(p) < 6:
        await u.message.reply_text(
            "Cú pháp: /wechat_spam <corpid>|<secret>|<agent>|<user>|<msgs>|<delay>"
        )
        return
    import requests as rq
    corpid, secret, agent, user = p[0].strip(), p[1].strip(), p[2].strip(), p[3].strip()
    msgs = [x.strip() for x in p[4].split(";") if x.strip()]
    delay = max(4.0, float(p[5].strip()))
    task = Task(new_tid("wechat"), "wechat", u.effective_user.id)

    def w():
        token = ""
        i = 0
        last = 0
        while not task.stop.is_set():
            if time.time() - last > 7000 or not token:
                try:
                    token = rq.get(
                        f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
                        f"?corpid={corpid}&corpsecret={secret}"
                    ).json().get("access_token", "")
                    last = time.time()
                except Exception:
                    pass
            m = msgs[i % len(msgs)]
            i += 1
            try:
                rq.post(
                    f"https://qyapi.weixin.qq.com/cgi-bin/message/send"
                    f"?access_token={token}",
                    json={"touser": user, "msgtype": "text", "agentid": agent,
                          "text": {"content": m}, "safe": 0},
                )
            except Exception:
                pass
            time.sleep(delay)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


# ============================================================
# HANDLERS - SYSTEM
# ============================================================
@admin_only
async def cmd_fw_status(u, c):
    text = "*🛡 FIREWALL v7*\n\n"
    for name, fw in FW.items():
        text += fw.report() + "\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_fw_reset(u, c):
    for fw in FW.values():
        with fw.lock:
            fw.stats = {"ok": 0, "fail": 0}
    await u.message.reply_text("✅ Reset firewall.")


@admin_only
async def cmd_rate(u, c):
    await u.message.reply_text(
        f"⚙ *RATE CONFIG*\n\n"
        f"• Min delay: `{MIN_SAFE_DELAY}s`\n"
        f"• Pool: `{POOL.size()}` acc\n"
        f"• FB base: `{FW['fb'].BASE_DELAY}s`\n"
        f"• Zalo base: `{FW['zalo'].BASE_DELAY}s`\n\n"
        f"Delay tự động theo risk từng acc.",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_cookie_fb(u, c):
    await u.message.reply_text(COOKIE_FB)


@admin_only
async def cmd_cookie_zalo(u, c):
    await u.message.reply_text(COOKIE_ZALO)


@admin_only
async def cmd_cookie_discord(u, c):
    await u.message.reply_text(COOKIE_DISCORD)


@admin_only
async def cmd_nick(u, c):
    prefixes = ["Cô đơn", "Bạc", "Tuyết", "Hắc", "Thanh", "Ngọc"]
    mids = ["Vô", "Bất", "Thiên", "Địa", "Long"]
    tails = ["Tử", "Thần", "Vương", "Kiếm", "Đao"]
    nick = f"{random.choice(prefixes)} {random.choice(mids)} {random.choice(tails)}"
    await u.message.reply_text(f"🎭 `{nick}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_uid_extract(u, c):
    t = u.message.text.replace("/uid_extract ", "", 1)
    uids = list(set(re.findall(r'\b\d{15,17}\b', t)))
    if not uids:
        await u.message.reply_text("❌ Không tìm thấy UID.")
        return
    text = f"🔍 Tìm thấy `{len(uids)}` UID:\n\n"
    for x in uids[:30]:
        text += f"`{x}`\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_ip_info(u, c):
    try:
        info = requests.get("https://ipinfo.io/json", timeout=10).json()
        await u.message.reply_text(json.dumps(info, indent=2))
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_backup_all(u, c):
    accs = VAULT.list_all("zalo")
    for a in accs:
        path = os.path.join(DATA_DIR, f"zalo_{a['uid']}.bak")
        with open(path, "w") as f:
            json.dump({"imei": a["imei"], "cookies": a["cookies"]}, f)
    await u.message.reply_text(f"✅ Backup `{len(accs)}` acc.")


@admin_only
async def cmd_tasks(u, c):
    tasks = TASKS.by_owner(u.effective_user.id)
    if not tasks:
        await u.message.reply_text("📭 Không có task.")
        return
    text = "*📋 Tasks:*\n\n"
    for i, t in enumerate(tasks, 1):
        text += f"`{i}.` [{t.type}] {t.uptime()}\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_stop(u, c):
    if not c.args or not c.args[0].isdigit():
        await u.message.reply_text("Cú pháp: /stop <n>")
        return
    i = int(c.args[0]) - 1
    tasks = TASKS.by_owner(u.effective_user.id)
    if 0 <= i < len(tasks):
        TASKS.remove(tasks[i].id)
        await u.message.reply_text("✅ Đã dừng.")
    else:
        await u.message.reply_text("❌ Số không hợp lệ.")


@admin_only
async def cmd_stop_all(u, c):
    tasks = TASKS.by_owner(u.effective_user.id)
    for t in tasks:
        TASKS.remove(t.id)
    await u.message.reply_text(f"✅ Dừng `{len(tasks)}` task.")


# ============================================================
# POST INIT
# ============================================================
async def post_init(app):
    print("[POST_INIT] Bắt đầu setup...")

    try:
        for a in VAULT.list_all("zalo"):
            POOL.add(a["imei"], a["cookies"], a["label"])
        print(f"[POST_INIT] Loaded {POOL.size()} acc từ vault")
    except Exception as e:
        print(f"[POST_INIT] Lỗi load vault: {e}")

    try:
        cmds = [
            ("start", "Menu chính"),
            ("zalo_qr", "QR login Zalo"),
            ("add_acc", "Thêm acc vào pool"),
            ("list_acc", "Xem pool"),
            ("del_acc", "Xóa acc"),
            ("vault", "Xem vault"),
            ("acc_risk", "Risk của acc"),
            ("zalo_rotate", "Spam Zalo rotate"),
            ("zalo_nhay", "Treo nhây Zalo"),
            ("zalo_tag", "Treo tag Zalo"),
            ("zalo_ngon", "Treo ngôn Zalo"),
            ("zalo_check", "Check Zalo"),
            ("zalo_groups", "List nhóm Zalo"),
            ("zalo_spam", "Spam Zalo 1 acc"),
            ("zalo_color_list", "Bảng màu Zalo"),
            ("fb_check", "Check FB"),
            ("fb_send", "Gửi tin FB"),
            ("fb_spam", "Spam FB"),
            ("discord_spam", "Spam Discord"),
            ("tele_spam", "Spam Telegram"),
            ("gmail_spam", "Spam Gmail"),
            ("sms_spam", "Spam SMS"),
            ("ig_spam", "Spam IG"),
            ("wechat_spam", "Spam WeChat"),
            ("fw_status", "Firewall status"),
            ("fw_reset", "Reset firewall"),
            ("rate", "Rate config"),
            ("cookie_fb", "Guide FB"),
            ("cookie_zalo", "Guide Zalo"),
            ("cookie_discord", "Guide Discord"),
            ("nick", "Random nick"),
            ("uid_extract", "Trích UID"),
            ("ip_info", "Info IP"),
            ("backup_all", "Backup all"),
            ("tasks", "Tasks"),
            ("stop", "Dừng task"),
            ("stop_all", "Dừng hết"),
        ]
        await app.bot.set_my_commands([BotCommand(n, d) for n, d in cmds])
        print("[POST_INIT] Commands set OK")
    except Exception as e:
        print(f"[POST_INIT] Lỗi: {e}")

    print("[BOT] Ready. Bot by Anh Khôi.")


# ============================================================
# MAIN
# ============================================================
def main():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    threading.Thread(target=_start_health_server, daemon=True).start()
    time.sleep(0.5)

    try:
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": "true"},
            timeout=10,
        )
        print(f"[MAIN] deleteWebhook: {r.status_code}")
    except Exception as e:
        print(f"[MAIN] Lỗi webhook: {e}")

    try:
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10
        )
        data = r.json()
        if data.get("ok"):
            info = data["result"]
            print(f"[MAIN] ✅ Bot: @{info.get('username')} (ID: {info.get('id')})")
        else:
            print(f"[MAIN] ❌ Token lỗi: {data}")
            return
    except Exception as e:
        print(f"[MAIN] ❌ Verify lỗi: {e}")
        return

    try:
        time.sleep(2)
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": "true"},
            timeout=10,
        )
        print("[MAIN] deleteWebhook lần 2: OK")
    except Exception:
        pass

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(cb_menu))

    app.add_handler(CommandHandler("zalo_qr", cmd_zalo_qr))
    app.add_handler(CommandHandler("add_acc", cmd_add_acc))
    app.add_handler(CommandHandler("list_acc", cmd_list_acc))
    app.add_handler(CommandHandler("del_acc", cmd_del_acc))
    app.add_handler(CommandHandler("vault", cmd_vault))
    app.add_handler(CommandHandler("acc_risk", cmd_acc_risk))
    app.add_handler(CommandHandler("zalo_rotate", cmd_zalo_rotate))
    app.add_handler(CommandHandler("zalo_nhay", cmd_zalo_nhay))
    app.add_handler(CommandHandler("zalo_tag", cmd_zalo_tag))
    app.add_handler(CommandHandler("zalo_ngon", cmd_zalo_ngon))
    app.add_handler(CommandHandler("zalo_check", cmd_zalo_check))
    app.add_handler(CommandHandler("zalo_groups", cmd_zalo_groups))
    app.add_handler(CommandHandler("zalo_spam", cmd_zalo_spam))
    app.add_handler(CommandHandler("zalo_color_list", cmd_zalo_color_list))

    app.add_handler(CommandHandler("fb_check", cmd_fb_check))
    app.add_handler(CommandHandler("fb_send", cmd_fb_send))
    app.add_handler(CommandHandler("fb_spam", cmd_fb_spam))
    app.add_handler(CommandHandler("fb_threads", cmd_fb_threads))

    app.add_handler(CommandHandler("discord_spam", cmd_discord_spam))
    app.add_handler(CommandHandler("tele_spam", cmd_tele_spam))
    app.add_handler(CommandHandler("gmail_spam", cmd_gmail_spam))
    app.add_handler(CommandHandler("sms_spam", cmd_sms_spam))
    app.add_handler(CommandHandler("ig_spam", cmd_ig_spam))
    app.add_handler(CommandHandler("wechat_spam", cmd_wechat_spam))

    app.add_handler(CommandHandler("fw_status", cmd_fw_status))
    app.add_handler(CommandHandler("fw_reset", cmd_fw_reset))
    app.add_handler(CommandHandler("rate", cmd_rate))
    app.add_handler(CommandHandler("cookie_fb", cmd_cookie_fb))
    app.add_handler(CommandHandler("cookie_zalo", cmd_cookie_zalo))
    app.add_handler(CommandHandler("cookie_discord", cmd_cookie_discord))
    app.add_handler(CommandHandler("nick", cmd_nick))
    app.add_handler(CommandHandler("uid_extract", cmd_uid_extract))
    app.add_handler(CommandHandler("ip_info", cmd_ip_info))
    app.add_handler(CommandHandler("backup_all", cmd_backup_all))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("stop_all", cmd_stop_all))

    print("[ALB] Bot by Anh Khôi — starting v8.1...")
    app.run_polling(
        drop_pending_updates=True,
        poll_interval=0.3,
        timeout=20,
    )


if __name__ == "__main__":
    main()
