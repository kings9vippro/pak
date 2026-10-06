# ============================================================
# BOT BY ANH KHÔI
# Phiên bản: 9.0
# Chức năng: Quản lý đa tài khoản Zalo, spam, treo nhây
# ============================================================

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
# CẤU HÌNH
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
# HTTP SERVER
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
        print(f"[MÁY CHỦ] Đang chạy trên cổng {port}")
        server.serve_forever()
    except Exception as e:
        print(f"[MÁY CHỦ] Lỗi: {e}")


# ============================================================
# TIỆN ÍCH
# ============================================================
_FALLBACK_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def random_ua():
    return random.choice(_FALLBACK_UAS)


def get_uptime(start):
    e = (datetime.now() - start).total_seconds()
    h, r = divmod(int(e), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def gen_imei():
    return "".join(random.choices(string.digits, k=15))


def jitter(base, f=0.4):
    return base * random.uniform(1 - f, 1 + f)


# ============================================================
# QUẢN LÝ TÁC VỤ
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
# TƯỜNG LỬA 7 LỚP
# ============================================================
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
            "ua": ua, "brand": brand, "mobile": mobile,
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
    name = "Hệ thống"
    BASE_DELAY = 3.0
    RETRY = 4
    BACKOFF = 1.5

    def __init__(self):
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

        headers = self.fp_pool.headers(
            self._fp_for(cookie),
            kw.pop("headers", {})
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
        cb = "Đang mở" if self.cb.is_open() else "Bình thường"
        return f"🛡 *{self.name}* | Thành công: `{s['ok']}` | Thất bại: `{s['fail']}` | Trạng thái: `{cb}`"


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
# CHỐNG BAN v4
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
# BỂ TÀI KHOẢN
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
# KÉT SẮT COOKIE
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
# BỘ MÀU ZALO
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


# ============================================================
# CÔNG CỤ ZALO
# ============================================================
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
            raise Exception("Cookie hoặc IMEI không đúng")
        self.uid = ud.get("send2me_id")
        self.secret_key = ud.get("zpw_enk")
        if not self.secret_key:
            raise Exception("Không lấy được khóa bảo mật")

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
# ZALO QR LOGIN
# ============================================================
class ZaloQRLogin:
    def __init__(self):
        self.browser = None
        self.page = None
        self.playwright = None

    async def _start(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("[QR] Cài đặt Playwright...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright==1.43.0"],
                check=True,
            )
            from playwright.async_api import async_playwright

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
                    print("[QR] Cài Chromium...")
                    try:
                        subprocess.run(
                            [sys.executable, "-m", "playwright", "install", "chromium"],
                            timeout=300,
                            check=True,
                        )
                    except Exception as e2:
                        print(f"[QR] Lỗi cài: {e2}")
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
            return {"error": f"Lỗi tạo mã QR: {e}"}

    async def poll_login(self, qr_id=None, stop_event=None):
        start = time.time()
        while time.time() - start < QR_TTL:
            if stop_event and stop_event.is_set():
                return {"error": "Đã dừng"}
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
        return {"error": "Mã QR hết hạn (120 giây)"}

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
            return {"error": f"Lỗi lấy dữ liệu: {e}"}

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
# FACEBOOK
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
# SPAM ROTATE
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
                print(f"[ROTATE] {acc['label']} → {target} [{'OK' if ok else 'LỖI'}]")
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
                    print(f"[NHÂY] {acc['label']} → {target} [{'OK' if ok else 'LỖI'}]")
                except Exception as e:
                    ANTIBAN4.record(uid, False)
                    POOL.report_fail(uid)
                    print(f"[NHÂY] Lỗi: {e}")

                delay = max(self.min_gap, ANTIBAN4.get_delay(uid))
                delay *= random.uniform(0.9, 1.3)
                end = time.time() + delay
                while time.time() < end:
                    if self.stop.is_set():
                        return
                    time.sleep(0.1)


# ============================================================
# HƯỚNG DẪN SỬ DỤNG
# ============================================================
HUONG_DAN_SU_DUNG = """📖 HƯỚNG DẪN SỬ DỤNG BOT

━━━━━━━━━━━━━━━━━━━━━━━━
🎯 BƯỚC 1: THÊM TÀI KHOẢN ZALO
━━━━━━━━━━━━━━━━━━━━━━━━
Gõ lệnh: /qr

→ Bot mở trình duyệt ẩn, tạo mã QR
→ Chờ 5-15 giây (lần đầu lâu hơn)
→ Bot gửi ảnh QR cho bạn

Cách quét QR:
1. Mở app Zalo trên điện thoại
2. Bấm biểu tượng QR (góc trên phải)
3. Quét ảnh QR trong Telegram
4. Bấm "Đồng ý" trên điện thoại

→ Bot tự động lưu cookie + IMEI vào kho
→ Làm 3-5 lần với 3-5 tài khoản khác nhau

━━━━━━━━━━━━━━━━━━━━━━━━
🎯 BƯỚC 2: KIỂM TRA TÀI KHOẢN
━━━━━━━━━━━━━━━━━━━━━━━━
Gõ lệnh: /ds

→ Bot hiện danh sách tài khoản trong kho
→ Hiện trạng thái: OK, Lỗi, Rủi ro, Cooldown

━━━━━━━━━━━━━━━━━━━━━━━━
🎯 BƯỚC 3: SPAM ROTATE ĐA TÀI KHOẢN
━━━━━━━━━━━━━━━━━━━━━━━━
Gõ lệnh: /spam <ID nhóm> | <nội dung 1;nội dung 2> | <giây>

Ví dụ: /spam 123456789|Chào;Hello;Hi|3

→ Bot dùng lần lượt từng tài khoản
→ Mỗi 3 giây đổi sang tài khoản khác
→ Không bao giờ trùng tài khoản

━━━━━━━━━━━━━━━━━━━━━━━━
🎯 BƯỚC 4: TREO NHÂY
━━━━━━━━━━━━━━━━━━━━━━━━
Gõ lệnh: /nhay <ID nhóm> | <nội dung 1;nội dung 2> | <giây>

→ Bot spam liên tục vào nhóm
→ Tự động đổi tài khoản liên tục

━━━━━━━━━━━━━━━━━━━━━━━━
🎯 BƯỚC 5: TREO TAG
━━━━━━━━━━━━━━━━━━━━━━━━
Gõ lệnh: /tag <ID nhóm> | <nội dung> | <UID người cần tag> | <giây>

→ Bot spam + tag người được chỉ định
→ Tự động đổi tài khoản

━━━━━━━━━━━━━━━━━━━━━━━━
🎯 BƯỚC 6: XEM LỊCH SỬ
━━━━━━━━━━━━━━━━━━━━━━━━
Gõ lệnh: /cv

→ Bot hiện danh sách tác vụ đang chạy
→ Gõ /dung <số> để dừng 1 tác vụ
→ Gõ /dunghet để dừng tất cả

━━━━━━━━━━━━━━━━━━━━━━━━
📌 LƯU Ý QUAN TRỌNG
━━━━━━━━━━━━━━━━━━━━━━━━
• Delay tối thiểu 3 giây để tránh bị ban
• Nên dùng 3-5 tài khoản để an toàn
• Bot tự động nghỉ khi tài khoản có rủi ro cao
• Không nên spam liên tục 24/24
• Nếu tài khoản bị lỗi nhiều → tự động tắt

━━━━━━━━━━━━━━━━━━━━━━━━
📞 HỖ TRỢ
━━━━━━━━━━━━━━━━━━━━━━━━
Liên hệ Admin: /admin

Bot được phát triển bởi Anh Khôi
Phiên bản 9.0
"""


HUONG_DAN_LAY_COOKIE = """🔑 HƯỚNG DẪN LẤY COOKIE THỦ CÔNG

━━━━━━━━━━━━━━━━━━━━━━━━
📘 FACEBOOK
━━━━━━━━━━━━━━━━━━━━━━━━
Cần các trường: c_user, xs, datr, fr, sb

Cách lấy:
1. Cài Kiwi Browser (Android)
2. Cài extension "Cookie Editor"
3. Đăng nhập facebook.com
4. Mở extension → Export → Copy JSON

Kiểm tra: /fbkt <cookie>

━━━━━━━━━━━━━━━━━━━━━━━━
📞 ZALO (thủ công)
━━━━━━━━━━━━━━━━━━━━━━━━
Cần các trường: zpw_sek, zpw_ver, zpw_type

Cách lấy:
1. Kiwi Browser → chat.zalo.me → đăng nhập
2. Extension Cookie Editor → Export
3. Cần các trường: zpw_sek, zpw_ver=645, zpw_type=30

Thêm vào bot:
/themacc <imei>|<cookie_json>|<tên gợi nhớ>

━━━━━━━━━━━━━━━━━━━━━━━━
🎮 DISCORD
━━━━━━━━━━━━━━━━━━━━━━━━
1. Mở discord.com trên PC
2. Bấm F12 → Console
3. Copy token và gửi vào bot

━━━━━━━━━━━━━━━━━━━━━━━━
📢 TELEGRAM
━━━━━━━━━━━━━━━━━━━━━━━━
• Bot token: chat @BotFather
• Chat ID: chat @userinfobot

━━━━━━━━━━━━━━━━━━━━━━━━
✉ GMAIL
━━━━━━━━━━━━━━━━━━━━━━━━
1. Bật 2FA: myaccount.google.com/security
2. Vào: myaccount.google.com/apppasswords
3. Tạo App Password 16 ký tự

━━━━━━━━━━━━━━━━━━━━━━━━
📷 INSTAGRAM
━━━━━━━━━━━━━━━━━━━━━━━━
1. Kiwi Browser → instagram.com
2. Cookie Editor → Export
3. Copy sessionid

━━━━━━━━━━━━━━━━━━━━━━━━
💼 WECHAT / WECOM
━━━━━━━━━━━━━━━━━━━━━━━━
1. work.weixin.qq.com → đăng nhập admin
2. My Business → copy Corp ID
3. Apps → tạo app → lấy AgentId + Secret

━━━━━━━━━━━━━━━━━━━━━━━━
📲 SMS
━━━━━━━━━━━━━━━━━━━━━━━━
Chỉ cần số điện thoại, không cần cookie
"""


# ============================================================
# GIAO DIỆN MENU
# ============================================================
MAIN_KB = [
    [InlineKeyboardButton("📘 Facebook", callback_data="m_fb"),
     InlineKeyboardButton("📞 Zalo", callback_data="m_zalo")],
    [InlineKeyboardButton("🎯 Spam đa acc", callback_data="m_rotate"),
     InlineKeyboardButton("🎭 Treo nhây", callback_data="m_nhay")],
    [InlineKeyboardButton("🔐 Kho tài khoản", callback_data="m_pool"),
     InlineKeyboardButton("🎮 Discord", callback_data="m_discord")],
    [InlineKeyboardButton("📢 Telegram", callback_data="m_telegram"),
     InlineKeyboardButton("✉ Gmail", callback_data="m_gmail")],
    [InlineKeyboardButton("📲 SMS", callback_data="m_sms"),
     InlineKeyboardButton("📷 Instagram", callback_data="m_ig")],
    [InlineKeyboardButton("💼 WeChat", callback_data="m_wechat"),
     InlineKeyboardButton("🛡 Tường lửa", callback_data="m_fw")],
    [InlineKeyboardButton("📖 Hướng dẫn", callback_data="m_guide"),
     InlineKeyboardButton("🔑 Lấy cookie", callback_data="m_cookie")],
    [InlineKeyboardButton("📋 Tác vụ", callback_data="m_tasks"),
     InlineKeyboardButton("🔥 Tiện ích", callback_data="m_cool")],
]


MENU_TEXT = {
    "m_fb": (
        "📘 *FACEBOOK*\n\n"
        "• `/fbkt <cookie>` — Kiểm tra cookie\n"
        "• `/fbgui <cookie>|<ID box>|<nội dung>` — Gửi 1 tin\n"
        "• `/fbspam <cookie>|<box1,box2>|<tin1;tin2>|<giây>` — Spam"
    ),
    "m_zalo": (
        "📞 *ZALO*\n\n"
        "• `/qr` — Tạo mã QR đăng nhập\n"
        "• `/zkt <imei>|<cookie>` — Kiểm tra\n"
        "• `/znhom <imei>|<cookie>` — Danh sách nhóm\n"
        "• `/zspam <imei>|<cookie>|<ID nhóm>|<tin>|<giây>`"
    ),
    "m_rotate": (
        "🎯 *SPAM ĐA TÀI KHOẢN*\n\n"
        "• `/themacc <imei>|<cookie>|<tên>` — Thêm thủ công\n"
        "• `/ds` — Xem danh sách\n"
        "• `/spam <ID nhóm>|<tin1;tin2>|<giây>`\n"
        "• `/xoaacc <uid>` — Xóa tài khoản\n\n"
        "_Bot tự đổi tài khoản mỗi giây, không trùng_"
    ),
    "m_nhay": (
        "🎭 *TREO NHÂY*\n\n"
        "• `/nhay <ID nhóm>|<tin1;tin2>|<giây>`\n"
        "• `/tag <ID nhóm>|<tin>|<UID tag>|<giây>`\n"
        "• `/ngon <ID nhóm>|<tin dài 1;tin dài 2>|<giây>`"
    ),
    "m_pool": (
        "🔐 *KHO TÀI KHOẢN*\n\n"
        "• `/ds` — Danh sách\n"
        "• `/ruiro <uid>` — Xem rủi ro\n"
        "• `/kho` — Xem kho cookie\n"
        "• `/xoaacc <uid>` — Xóa"
    ),
    "m_discord": "🎮 `/dspam <token>|<kênh>|<tin1;tin2>|<giây>`",
    "m_telegram": "📢 `/tspam <token>|<chat>|<tin1;tin2>|<giây>`",
    "m_gmail": "✉ `/gspam <email>|<mật khẩu>|<đến>|<tin1;tin2>|<giây>`",
    "m_sms": "📲 `/sms <số điện thoại>`",
    "m_ig": "📷 `/igspam <sessionid>|<ID>|<tin1;tin2>|<giây>`",
    "m_wechat": "💼 `/wcspam <corpid>|<secret>|<agent>|<user>|<tin1;tin2>|<giây>`",
    "m_fw": "🛡 `/tuonglua` — Xem trạng thái\n`/reset` — Đặt lại",
    "m_guide": "📖 Dùng lệnh /hd để xem hướng dẫn chi tiết",
    "m_cookie": "🔑 Dùng lệnh /cookie để xem cách lấy cookie",
    "m_tasks": "📋 `/cv` — Xem tác vụ\n`/dung <số>` — Dừng\n`/dunghet` — Dừng tất cả",
    "m_cool": "🔥 `/nick` — Nick random\n`/uid <văn bản>` — Trích UID\n`/ip` — IP máy chủ",
}


def admin_only(func):
    async def w(update, ctx):
        if update.effective_user.id not in ADMIN_IDS:
            if update.message:
                await update.message.reply_text(
                    "⛔ Bạn không có quyền sử dụng bot này.\n"
                    "Liên hệ Admin để được cấp quyền."
                )
            return
        return await func(update, ctx)
    return w


# ============================================================
# LỆNH START
# ============================================================
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Bạn không có quyền sử dụng bot.")
        return
    await update.message.reply_text(
        "🔥 *BOT ĐA NĂNG*\n\n"
        f"👤 Phát triển: *Anh Khôi*\n"
        f"📦 Phiên bản: *9.0*\n"
        f"🎯 Tài khoản: *{POOL.size()}* trong kho\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Chọn chức năng bên dưới:\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━",
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
            await q.edit_message_text("📭 Chưa có tác vụ nào đang chạy.")
            return
        text = "*📋 TÁC VỤ ĐANG CHẠY:*\n\n"
        for i, t in enumerate(tasks, 1):
            text += f"`{i}.` Loại: {t.type} | Đã chạy: {t.uptime()}\n"
        text += "\nDùng `/dung <số>` để dừng"
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)


# ============================================================
# LỆNH ZALO QR
# ============================================================
@admin_only
async def cmd_qr(update, ctx):
    await update.message.reply_text(
        "⏳ Đang tạo mã QR...\n"
        "Vui lòng chờ 5-15 giây"
    )

    qr = ZaloQRLogin()
    try:
        info = await asyncio.get_event_loop().run_in_executor(
            None, lambda: run_async(qr.create_qr())
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi tạo mã QR: {e}")
        return

    if "error" in info:
        await update.message.reply_text(f"❌ {info['error']}")
        return

    await update.message.reply_photo(
        photo=info["qr_image"],
        caption=(
            "📷 *MÃ QR ĐĂNG NHẬP ZALO*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Cách quét:\n"
            "1️⃣ Mở app Zalo trên điện thoại\n"
            "2️⃣ Bấm biểu tượng QR (góc trên phải)\n"
            "3️⃣ Quét ảnh trên\n"
            "4️⃣ Bấm *Đồng ý* trên điện thoại\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⏱ Hết hạn sau: *{info['ttl']} giây*\n"
            "⏳ Đang chờ bạn quét..."
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
            f"❌ {res.get('error') if res else 'Hết thời gian chờ'}"
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
        "✅ *ĐĂNG NHẬP ZALO THÀNH CÔNG!*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷 Tên gợi nhớ: `{label}`\n"
        f"🆔 IMEI: `{imei}`\n"
        f"👤 UID: `{uid}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🍪 *Cookie:*\n{cookie_str}\n\n"
        f"📊 Kho hiện tại: *{POOL.size()} tài khoản*\n\n"
        "💡 Bước tiếp theo:\n"
        "• Gõ `/ds` để xem danh sách\n"
        "• Gõ `/spam` để bắt đầu spam"
    )


# ============================================================
# LỆNH QUẢN LÝ TÀI KHOẢN
# ============================================================
@admin_only
async def cmd_themacc(u, c):
    t = u.message.text.replace("/themacc ", "", 1)
    p = t.split("|")
    if len(p) < 2:
        await u.message.reply_text(
            "❌ Cú pháp: `/themacc <imei>|<cookie>|<tên>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    imei = p[0].strip()
    try:
        cookies = json.loads(p[1].strip())
    except Exception as e:
        await u.message.reply_text(f"❌ Cookie không hợp lệ: {e}")
        return
    label = p[2].strip() if len(p) > 2 else f"acc{POOL.size() + 1}"
    uid = cookies.get("zalo_u_id") or imei

    ok_pool = POOL.add(imei, cookies, label)
    VAULT.add(uid, imei, cookies, label, "zalo")

    if ok_pool:
        await u.message.reply_text(
            f"✅ Đã thêm tài khoản `{label}`\n"
            f"📊 Kho hiện tại: *{POOL.size()} tài khoản*",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await u.message.reply_text("⚠️ Tài khoản này đã có trong kho.")


@admin_only
async def cmd_ds(u, c):
    accs = POOL.list_all()
    if not accs:
        await u.message.reply_text(
            "📭 Kho tài khoản đang trống.\n"
            "Gõ /qr để thêm tài khoản đầu tiên."
        )
        return
    text = f"📋 *DANH SÁCH TÀI KHOẢN* ({len(accs)})\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, a in enumerate(accs, 1):
        risk = ANTIBAN4.get_risk(a["uid"])
        cd = ANTIBAN4.in_cooldown(a["uid"])
        status = "✅" if a["enabled"] else "❌"
        if cd > 0:
            status = "⏸️"
        text += (
            f"`{i}.` {a['label']} {status}\n"
            f"   Thành công: `{a['ok_count']}` | Lỗi: `{a['fail_count']}`\n"
            f"   Rủi ro: `{risk:.2f}` | Nghỉ: `{cd:.0f}giây`\n\n"
        )
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += "💡 Dùng /xoaacc <uid> để xóa tài khoản"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_xoaacc(u, c):
    if not c.args:
        await u.message.reply_text("❌ Cú pháp: `/xoaacc <uid>`",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    uid = c.args[0].strip()
    VAULT.remove(uid, "zalo")
    with POOL.lock:
        POOL.accounts = [a for a in POOL.accounts if a["uid"] != uid]
    await u.message.reply_text(f"✅ Đã xóa tài khoản `{uid}`",
                                parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_kho(u, c):
    accs = VAULT.list_all("zalo")
    if not accs:
        await u.message.reply_text("📭 Kho cookie đang trống.")
        return
    text = f"🔐 *KHO COOKIE* ({len(accs)})\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, a in enumerate(accs[:30], 1):
        text += f"`{i}.` {a['label']} | UID: `{a['uid'][:16]}...`\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_ruiro(u, c):
    if not c.args:
        await u.message.reply_text("❌ Cú pháp: `/ruiro <uid>`",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    st = ANTIBAN4.stats(c.args[0].strip())
    await u.message.reply_text(
        f"📊 *THÔNG TIN RỦI RO*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 UID: `{st['uid']}`\n"
        f"✅ Thành công: `{st['ok']}`\n"
        f"❌ Thất bại: `{st['fail']}`\n"
        f"⚠️ Điểm rủi ro: `{st['risk']:.2f}`\n"
        f"⏸️ Đang nghỉ: `{st['cooldown_left']:.0f} giây`\n"
        f"⏱ Delay hiện tại: `{st['current_delay']:.1f} giây`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ============================================================
# LỆNH SPAM / NHÂY
# ============================================================
@admin_only
async def cmd_spam(u, c):
    t = u.message.text.replace("/spam ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "❌ Cú pháp: `/spam <ID nhóm>|<tin1;tin2>|<giây>`\n\n"
            "Ví dụ: `/spam 123456|Chào;Hello|3`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if POOL.size() == 0:
        await u.message.reply_text(
            "❌ Kho tài khoản trống.\nDùng /qr để thêm trước."
        )
        return
    targets = [x.strip() for x in p[0].split(",") if x.strip()]
    msgs = [x.strip() for x in p[1].split(";") if x.strip()]
    min_gap = max(1.0, float(p[2].strip()))

    task = Task(new_tid("spam"), "Spam đa tài khoản", u.effective_user.id)
    spam = ZaloRotateSpam(targets, msgs, min_gap)
    task.stop = spam.stop
    spam.start()
    TASKS.add(task)

    await u.message.reply_text(
        f"✅ *ĐÃ BẮT ĐẦU SPAM*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Nhóm: `{len(targets)}`\n"
        f"📦 Tài khoản: `{POOL.size()}`\n"
        f"⏱ Delay: `{min_gap} giây`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 Bot sẽ tự đổi tài khoản mỗi lần gửi\n"
        "Dùng /cv để xem, /dung để dừng",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_nhay(u, c):
    t = u.message.text.replace("/nhay ", "", 1)
    p = t.split("|")
    if len(p) < 2:
        await u.message.reply_text(
            "❌ Cú pháp: `/nhay <ID nhóm>|<tin1;tin2>|<giây>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if POOL.size() == 0:
        await u.message.reply_text("❌ Kho tài khoản trống.")
        return
    targets = [x.strip() for x in p[0].split(",") if x.strip()]
    msgs = [x.strip() for x in p[1].split(";") if x.strip()]
    min_gap = max(1.0, float(p[2].strip())) if len(p) > 2 else 1.0

    task = Task(new_tid("nhay"), "Treo nhây", u.effective_user.id)
    nhay = ZaloNhay(targets, msgs, min_gap)
    task.stop = nhay.stop
    nhay.start()
    TASKS.add(task)
    await u.message.reply_text(
        f"✅ *ĐÃ BẮT ĐẦU TREO NHÂY*\n\n"
        f"🎯 Nhóm: `{len(targets)}`\n"
        f"📦 Tài khoản: `{POOL.size()}`\n"
        f"⏱ Delay: `{min_gap} giây`",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_tag(u, c):
    t = u.message.text.replace("/tag ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "❌ Cú pháp: `/tag <ID nhóm>|<tin>|<UID tag>|<giây>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if POOL.size() == 0:
        await u.message.reply_text("❌ Kho tài khoản trống.")
        return
    targets = [x.strip() for x in p[0].split(",") if x.strip()]
    msgs = [x.strip() for x in p[1].split(";") if x.strip()]
    tag_user = p[2].strip()
    min_gap = max(1.0, float(p[3].strip())) if len(p) > 3 else 1.0

    task = Task(new_tid("tag"), "Treo tag", u.effective_user.id)
    tag = ZaloNhay(targets, msgs, min_gap, tag_user=tag_user)
    task.stop = tag.stop
    tag.start()
    TASKS.add(task)
    await u.message.reply_text(
        f"✅ *ĐÃ BẮT ĐẦU TREO TAG*\n\n"
        f"🎯 Nhóm: `{len(targets)}`\n"
        f"🏷 Tag: `@{tag_user}`\n"
        f"⏱ Delay: `{min_gap} giây`",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_ngon(u, c):
    t = u.message.text.replace("/ngon ", "", 1)
    p = t.split("|")
    if len(p) < 2:
        await u.message.reply_text(
            "❌ Cú pháp: `/ngon <ID nhóm>|<tin dài1;tin dài2>|<giây>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if POOL.size() == 0:
        await u.message.reply_text("❌ Kho tài khoản trống.")
        return
    targets = [x.strip() for x in p[0].split(",") if x.strip()]
    msgs = [x.strip() for x in p[1].split(";") if x.strip()]
    min_gap = max(1.0, float(p[2].strip())) if len(p) > 2 else 1.0

    task = Task(new_tid("ngon"), "Treo ngôn", u.effective_user.id)
    ngon = ZaloNhay(targets, msgs, min_gap)
    task.stop = ngon.stop
    ngon.start()
    TASKS.add(task)
    await u.message.reply_text(
        f"✅ *ĐÃ BẮT ĐẦU TREO NGÔN*\n\n"
        f"🎯 Nhóm: `{len(targets)}`\n"
        f"⏱ Delay: `{min_gap} giây`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ============================================================
# LỆNH ZALO CƠ BẢN
# ============================================================
@admin_only
async def cmd_zkt(u, c):
    t = u.message.text.replace("/zkt ", "", 1)
    if "|" not in t:
        await u.message.reply_text("❌ Cú pháp: `/zkt <imei>|<cookie>`",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    imei, ck = t.split("|", 1)
    try:
        z = Zalo(imei.strip(), json.loads(ck))
        await u.message.reply_text(
            f"✅ Cookie Zalo còn sống!\n👤 UID: `{z.uid}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_znhom(u, c):
    t = u.message.text.replace("/znhom ", "", 1)
    if "|" not in t:
        await u.message.reply_text("❌ Cú pháp: `/znhom <imei>|<cookie>`",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    imei, ck = t.split("|", 1)
    try:
        z = Zalo(imei.strip(), json.loads(ck))
        gs = z.groups()
        msg = f"📦 *{len(gs)} NHÓM ZALO:*\n\n"
        for i, g in enumerate(gs[:60], 1):
            msg += f"`{i}.` {g['name'][:40]}\n   ID: `{g['id']}`\n"
        await u.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_zspam(u, c):
    t = u.message.text.replace("/zspam ", "", 1)
    p = t.split("|")
    if len(p) < 5:
        await u.message.reply_text(
            "❌ Cú pháp: `/zspam <imei>|<cookie>|<ID nhóm>|<tin1;tin2>|<giây>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    imei = p[0].strip()
    cookies = json.loads(p[1].strip())
    targets = [x.strip() for x in p[2].split(",") if x.strip()]
    msgs = [x.strip() for x in p[3].split(";") if x.strip()]
    delay = max(3.0, float(p[4].strip()))
    task = Task(new_tid("zspam"), "Spam Zalo đơn", u.effective_user.id)

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
                        z.send(msg, tid, True)
                        time.sleep(delay)
        except Exception as e:
            print(f"[zspam] {e}")

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(
        f"✅ Đã bắt đầu spam 1 tài khoản\n"
        f"Tác vụ: `{task.id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ============================================================
# LỆNH FACEBOOK
# ============================================================
@admin_only
async def cmd_fbkt(u, c):
    cookie = u.message.text.replace("/fbkt ", "", 1).strip()
    info = Facebook().check(cookie)
    if info:
        await u.message.reply_text(
            f"✅ Cookie Facebook còn sống!\n"
            f"👤 Tên: {info['name']}\n"
            f"🆔 UID: `{info['uid']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await u.message.reply_text("❌ Cookie đã chết hoặc không hợp lệ.")


@admin_only
async def cmd_fbgui(u, c):
    text = u.message.text.replace("/fbgui ", "", 1)
    p = text.split("|")
    if len(p) < 3:
        await u.message.reply_text("❌ Cú pháp: `/fbgui <cookie>|<ID box>|<tin>`",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    r = Facebook().send(p[0].strip(), p[1].strip(), "|".join(p[2:]).strip())
    if r and r.status_code == 200:
        await u.message.reply_text("✅ Đã gửi tin nhắn!")
    else:
        await u.message.reply_text("❌ Gửi tin thất bại.")


@admin_only
async def cmd_fbspam(u, c):
    text = u.message.text.replace("/fbspam ", "", 1)
    p = text.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "❌ Cú pháp: `/fbspam <cookie>|<box1,box2>|<tin1;tin2>|<giây>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    cookie = p[0].strip()
    boxes = [x.strip() for x in p[1].split(",") if x.strip()]
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(3.0, float(p[3].strip()))
    task = Task(new_tid("fbspam"), "Spam Facebook", u.effective_user.id)
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
    await u.message.reply_text(
        f"✅ Đã bắt đầu spam Facebook\nTác vụ: `{task.id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ============================================================
# LỆNH ĐA NỀN TẢNG KHÁC
# ============================================================
@admin_only
async def cmd_dspam(u, c):
    t = u.message.text.replace("/dspam ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text("❌ Cú pháp: `/dspam <token>|<kênh>|<tin1;tin2>|<giây>`",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    token, ch = p[0].strip(), p[1].strip()
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(3.0, float(p[3].strip()))
    task = Task(new_tid("dspam"), "Spam Discord", u.effective_user.id)

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
    await u.message.reply_text(f"✅ Đã bắt đầu spam Discord. Tác vụ: `{task.id}`",
                                parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_tspam(u, c):
    t = u.message.text.replace("/tspam ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text("❌ Cú pháp: `/tspam <token>|<chat>|<tin1;tin2>|<giây>`",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    token, ch = p[0].strip(), p[1].strip()
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(3.0, float(p[3].strip()))
    task = Task(new_tid("tspam"), "Spam Telegram", u.effective_user.id)

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
    await u.message.reply_text(f"✅ Đã bắt đầu spam Telegram. Tác vụ: `{task.id}`",
                                parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_gspam(u, c):
    t = u.message.text.replace("/gspam ", "", 1)
    p = t.split("|")
    if len(p) < 5:
        await u.message.reply_text(
            "❌ Cú pháp: `/gspam <email>|<mật khẩu>|<đến>|<tin1;tin2>|<giây>`",
            parse_mode=ParseMode.MARKDOWN,
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
    task = Task(new_tid("gspam"), "Spam Gmail", u.effective_user.id)

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
    await u.message.reply_text(f"✅ Đã bắt đầu spam Gmail. Tác vụ: `{task.id}`",
                                parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_sms(u, c):
    if not c.args:
        await u.message.reply_text("❌ Cú pháp: `/sms <số điện thoại>`",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    phone = c.args[0].strip()
    if POOL.size() == 0:
        await u.message.reply_text("❌ Kho tài khoản trống. Dùng /qr trước.")
        return

    task = Task(new_tid("sms"), "Spam SMS", u.effective_user.id)

    def w():
        while not task.stop.is_set():
            acc = POOL.next_account(min_gap=1.0)
            if not acc:
                time.sleep(1)
                continue
            try:
                Zalo(acc["imei"], acc["cookies"])
                msg = f"Mã OTP: {random.randint(100000, 999999)}"
                print(f"[sms] {acc['label']} → {phone}: {msg}")
            except Exception as e:
                print(f"[sms] {e}")
            time.sleep(5)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(
        f"✅ Đã bắt đầu spam SMS tới `{phone}`\n"
        f"Tác vụ: `{task.id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_igspam(u, c):
    t = u.message.text.replace("/igspam ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "❌ Cú pháp: `/igspam <sessionid>|<ID>|<tin1;tin2>|<giây>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    sid = p[0].strip()
    tids = [x.strip() for x in p[1].split(",") if x.strip()]
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(8.0, float(p[3].strip()))
    task = Task(new_tid("igspam"), "Spam Instagram", u.effective_user.id)

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
    await u.message.reply_text(f"✅ Đã bắt đầu spam Instagram. Tác vụ: `{task.id}`",
                                parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_wcspam(u, c):
    t = u.message.text.replace("/wcspam ", "", 1)
    p = t.split("|")
    if len(p) < 6:
        await u.message.reply_text(
            "❌ Cú pháp: `/wcspam <corpid>|<secret>|<agent>|<user>|<tin1;tin2>|<giây>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    import requests as rq
    corpid, secret, agent, user = p[0].strip(), p[1].strip(), p[2].strip(), p[3].strip()
    msgs = [x.strip() for x in p[4].split(";") if x.strip()]
    delay = max(4.0, float(p[5].strip()))
    task = Task(new_tid("wcspam"), "Spam WeChat", u.effective_user.id)

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
    await u.message.reply_text(f"✅ Đã bắt đầu spam WeChat. Tác vụ: `{task.id}`",
                                parse_mode=ParseMode.MARKDOWN)


# ============================================================
# LỆNH HỆ THỐNG
# ============================================================
@admin_only
async def cmd_tuonglua(u, c):
    text = "*🛡 TRẠNG THÁI TƯỜNG LỬA*\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for name, fw in FW.items():
        text += fw.report() + "\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_reset(u, c):
    for fw in FW.values():
        with fw.lock:
            fw.stats = {"ok": 0, "fail": 0}
    await u.message.reply_text("✅ Đã đặt lại tường lửa.")


@admin_only
async def cmd_hd(u, c):
    await u.message.reply_text(HUONG_DAN_SU_DUNG)


@admin_only
async def cmd_cookie(u, c):
    await u.message.reply_text(HUONG_DAN_LAY_COOKIE)


@admin_only
async def cmd_nick(u, c):
    prefixes = ["Cô đơn", "Bạc", "Tuyết", "Hắc", "Thanh", "Ngọc"]
    mids = ["Vô", "Bất", "Thiên", "Địa", "Long"]
    tails = ["Tử", "Thần", "Vương", "Kiếm", "Đao"]
    nick = f"{random.choice(prefixes)} {random.choice(mids)} {random.choice(tails)}"
    await u.message.reply_text(f"🎭 Nick: `{nick}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_uid(u, c):
    t = u.message.text.replace("/uid ", "", 1)
    uids = list(set(re.findall(r'\b\d{15,17}\b', t)))
    if not uids:
        await u.message.reply_text("❌ Không tìm thấy UID nào trong văn bản.")
        return
    text = f"🔍 Tìm thấy `{len(uids)}` UID:\n\n"
    for x in uids[:30]:
        text += f"`{x}`\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_ip(u, c):
    try:
        info = requests.get("https://ipinfo.io/json", timeout=10).json()
        text = "🌐 *THÔNG TIN IP MÁY CHỦ*\n\n"
        text += f"• IP: `{info.get('ip', '?')}`\n"
        text += f"• Thành phố: `{info.get('city', '?')}`\n"
        text += f"• Vùng: `{info.get('region', '?')}`\n"
        text += f"• Quốc gia: `{info.get('country', '?')}`\n"
        text += f"• Nhà mạng: `{info.get('org', '?')}`\n"
        await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await u.message.reply_text(f"❌ Lỗi: {e}")


@admin_only
async def cmd_admin(u, c):
    admins = " ".join(f"`{aid}`" for aid in ADMIN_IDS)
    await u.message.reply_text(
        f"👑 *QUẢN TRỊ VIÊN BOT*\n\n"
        f"Danh sách Admin:\n{admins}\n\n"
        f"👨‍💻 Phát triển: Anh Khôi\n"
        f"📦 Phiên bản: 9.0",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_cv(u, c):
    tasks = TASKS.by_owner(u.effective_user.id)
    if not tasks:
        await u.message.reply_text("📭 Chưa có tác vụ nào đang chạy.")
        return
    text = "*📋 DANH SÁCH TÁC VỤ:*\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, t in enumerate(tasks, 1):
        text += f"`{i}.` {t.type} | Đã chạy: `{t.uptime()}`\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "💡 Dùng `/dung <số>` để dừng 1 tác vụ\n"
    text += "Hoặc `/dunghet` để dừng tất cả"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_dung(u, c):
    if not c.args or not c.args[0].isdigit():
        await u.message.reply_text("❌ Cú pháp: `/dung <số>`",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    i = int(c.args[0]) - 1
    tasks = TASKS.by_owner(u.effective_user.id)
    if 0 <= i < len(tasks):
        TASKS.remove(tasks[i].id)
        await u.message.reply_text(f"✅ Đã dừng tác vụ số {i + 1}")
    else:
        await u.message.reply_text("❌ Số tác vụ không đúng.")


@admin_only
async def cmd_dunghet(u, c):
    tasks = TASKS.by_owner(u.effective_user.id)
    for t in tasks:
        TASKS.remove(t.id)
    await u.message.reply_text(f"✅ Đã dừng tất cả `{len(tasks)}` tác vụ.",
                                parse_mode=ParseMode.MARKDOWN)


# ============================================================
# KHỞI TẠO
# ============================================================
async def post_init(app):
    print("[KHỞI TẠO] Bắt đầu cài đặt...")

    try:
        for a in VAULT.list_all("zalo"):
            POOL.add(a["imei"], a["cookies"], a["label"])
        print(f"[KHỞI TẠO] Đã nạp {POOL.size()} tài khoản từ kho")
    except Exception as e:
        print(f"[KHỞI TẠO] Lỗi nạp kho: {e}")

    try:
        cmds = [
            ("start", "Menu chính"),
            ("hd", "Hướng dẫn sử dụng"),
            ("cookie", "Hướng dẫn lấy cookie"),
            ("admin", "Thông tin Admin"),

            ("qr", "Tạo mã QR đăng nhập Zalo"),
            ("themacc", "Thêm tài khoản thủ công"),
            ("ds", "Danh sách tài khoản"),
            ("xoaacc", "Xóa tài khoản"),
            ("kho", "Xem kho cookie"),
            ("ruiro", "Xem rủi ro tài khoản"),

            ("spam", "Spam đa tài khoản"),
            ("nhay", "Treo nhây"),
            ("tag", "Treo tag"),
            ("ngon", "Treo ngôn"),

            ("zkt", "Kiểm tra Zalo"),
            ("znhom", "Danh sách nhóm Zalo"),
            ("zspam", "Spam 1 tài khoản Zalo"),

            ("fbkt", "Kiểm tra Facebook"),
            ("fbgui", "Gửi tin Facebook"),
            ("fbspam", "Spam Facebook"),

            ("dspam", "Spam Discord"),
            ("tspam", "Spam Telegram"),
            ("gspam", "Spam Gmail"),
            ("sms", "Spam SMS"),
            ("igspam", "Spam Instagram"),
            ("wcspam", "Spam WeChat"),

            ("tuonglua", "Trạng thái tường lửa"),
            ("reset", "Đặt lại tường lửa"),
            ("nick", "Nick ngẫu nhiên"),
            ("uid", "Trích UID từ văn bản"),
            ("ip", "IP máy chủ"),

            ("cv", "Danh sách tác vụ"),
            ("dung", "Dừng 1 tác vụ"),
            ("dunghet", "Dừng tất cả"),
        ]
        await app.bot.set_my_commands([BotCommand(n, d) for n, d in cmds])
        print("[KHỞI TẠO] Đã đặt lệnh thành công")
    except Exception as e:
        print(f"[KHỞI TẠO] Lỗi: {e}")

    print("[BOT] Sẵn sàng. Bot được phát triển bởi Anh Khôi.")


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
        print(f"[CHÍNH] Xóa webhook: {r.status_code}")
    except Exception as e:
        print(f"[CHÍNH] Lỗi webhook: {e}")

    try:
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10
        )
        data = r.json()
        if data.get("ok"):
            info = data["result"]
            print(f"[CHÍNH] ✅ Bot: @{info.get('username')} (ID: {info.get('id')})")
        else:
            print(f"[CHÍNH] ❌ Token lỗi: {data}")
            return
    except Exception as e:
        print(f"[CHÍNH] ❌ Lỗi xác minh: {e}")
        return

    try:
        time.sleep(2)
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": "true"},
            timeout=10,
        )
        print("[CHÍNH] Xóa webhook lần 2: OK")
    except Exception:
        pass

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(True)
        .build()
    )

    # Đăng ký lệnh
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(cb_menu))

    app.add_handler(CommandHandler("hd", cmd_hd))
    app.add_handler(CommandHandler("cookie", cmd_cookie))
    app.add_handler(CommandHandler("admin", cmd_admin))

    app.add_handler(CommandHandler("qr", cmd_qr))
    app.add_handler(CommandHandler("themacc", cmd_themacc))
    app.add_handler(CommandHandler("ds", cmd_ds))
    app.add_handler(CommandHandler("xoaacc", cmd_xoaacc))
    app.add_handler(CommandHandler("kho", cmd_kho))
    app.add_handler(CommandHandler("ruiro", cmd_ruiro))

    app.add_handler(CommandHandler("spam", cmd_spam))
    app.add_handler(CommandHandler("nhay", cmd_nhay))
    app.add_handler(CommandHandler("tag", cmd_tag))
    app.add_handler(CommandHandler("ngon", cmd_ngon))

    app.add_handler(CommandHandler("zkt", cmd_zkt))
    app.add_handler(CommandHandler("znhom", cmd_znhom))
    app.add_handler(CommandHandler("zspam", cmd_zspam))

    app.add_handler(CommandHandler("fbkt", cmd_fbkt))
    app.add_handler(CommandHandler("fbgui", cmd_fbgui))
    app.add_handler(CommandHandler("fbspam", cmd_fbspam))

    app.add_handler(CommandHandler("dspam", cmd_dspam))
    app.add_handler(CommandHandler("tspam", cmd_tspam))
    app.add_handler(CommandHandler("gspam", cmd_gspam))
    app.add_handler(CommandHandler("sms", cmd_sms))
    app.add_handler(CommandHandler("igspam", cmd_igspam))
    app.add_handler(CommandHandler("wcspam", cmd_wcspam))

    app.add_handler(CommandHandler("tuonglua", cmd_tuonglua))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("nick", cmd_nick))
    app.add_handler(CommandHandler("uid", cmd_uid))
    app.add_handler(CommandHandler("ip", cmd_ip))

    app.add_handler(CommandHandler("cv", cmd_cv))
    app.add_handler(CommandHandler("dung", cmd_dung))
    app.add_handler(CommandHandler("dunghet", cmd_dunghet))

    print("[BOT] Bắt đầu chạy...")
    app.run_polling(
        drop_pending_updates=True,
        poll_interval=0.3,
        timeout=20,
    )


if __name__ == "__main__":
    main()
