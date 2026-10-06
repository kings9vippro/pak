# ============================================================
# cookie_guard_v3.py — Bảo vệ cookie không die
# - Backup ra file .bak
# - Warm định kỳ 30 phút
# - Health check per-cookie
# ============================================================
import os
import time
import threading
import hashlib
import random
from typing import Optional

DATA_DIR = os.environ.get("DATA_DIR", "/tmp/alb_data")
os.makedirs(DATA_DIR, exist_ok=True)


class CookieGuardV3:
    def __init__(self):
        self.health = {}
        self.lock = threading.Lock()
        self.warm_threads = {}

    @staticmethod
    def _hash(c: str) -> str:
        return hashlib.md5(c.encode()).hexdigest()[:12]

    # ---------- Backup ----------
    @staticmethod
    def backup(cookie: str, tag: str = "fb") -> str:
        """Lưu cookie ra file .bak."""
        h = CookieGuardV3._hash(cookie)
        p = os.path.join(DATA_DIR, f"{tag}_{h}.bak")
        with open(p, "w") as f:
            f.write(cookie)
        return p

    @staticmethod
    def load_backup(path: str) -> Optional[str]:
        try:
            with open(path) as f:
                return f.read().strip()
        except Exception:
            return None

    @staticmethod
    def list_backups(tag: str = "fb"):
        out = []
        for f in os.listdir(DATA_DIR):
            if f.startswith(f"{tag}_") and f.endswith(".bak"):
                out.append(os.path.join(DATA_DIR, f))
        return out

    # ---------- Warm ----------
    @staticmethod
    def warm_fb(cookie: str):
        """Truy cập vài trang FB nhẹ để giữ session sống."""
        from firewall_v7 import FW
        fw = FW["fb"]
        urls = [
            "https://www.facebook.com/",
            "https://www.facebook.com/messages/t/",
            "https://www.facebook.com/notifications",
        ]
        try:
            for u in urls:
                fw.get(u, headers={"Cookie": cookie}, timeout=15)
                time.sleep(random.uniform(2.0, 4.5))
        except Exception:
            pass

    def start_warm_loop(self, cookie: str, tag: str, interval: int,
                        stop_event: threading.Event):
        """Chạy warm định kỳ trong thread riêng."""
        h = self._hash(cookie)
        with self.lock:
            if h in self.warm_threads and self.warm_threads[h].is_alive():
                return

            def loop():
                while not stop_event.is_set():
                    try:
                        if tag == "fb":
                            CookieGuardV3.warm_fb(cookie)
                        CookieGuardV3.backup(cookie, tag)
                    except Exception:
                        pass
                    for _ in range(interval):
                        if stop_event.is_set():
                            return
                        time.sleep(1)

            t = threading.Thread(target=loop, daemon=True)
            self.warm_threads[h] = t
            t.start()

    # ---------- Health ----------
    def record(self, cookie: str, ok: bool):
        h = self._hash(cookie)
        with self.lock:
            d = self.health.setdefault(h, {"ok": 0, "fail": 0, "last": 0})
            if ok:
                d["ok"] += 1
            else:
                d["fail"] += 1
            d["last"] = time.time()

    def health_percent(self, cookie: str) -> float:
        """Tỉ lệ thành công %."""
        h = self._hash(cookie)
        with self.lock:
            d = self.health.get(h, {"ok": 0, "fail": 0, "last": 0})
            total = d["ok"] + d["fail"]
            if total == 0:
                return 100.0
            return (d["ok"] / total) * 100.0

    def is_safe(self, cookie: str) -> bool:
        """Cookie có an toàn không (ok > 40%)."""
        h = self._hash(cookie)
        with self.lock:
            d = self.health.get(h, {"ok": 0, "fail": 0, "last": 0})
            total = d["ok"] + d["fail"]
            if total < 5:
                return True
            return (d["ok"] / total) > 0.4


GUARD3 = CookieGuardV3()
