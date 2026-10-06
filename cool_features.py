# ============================================================
# cool_features.py — Chức năng lạ và xịn
# ============================================================
import time
import random
import threading
import json
import os

NICK_PREFIX = ["Cô đơn", "Bạc", "Tuyết", "Hắc", "Thanh", "Ngọc", "Hoàng", "Kim", "Mộc", "Thủy"]
NICK_MID = ["Vô", "Bất", "Thiên", "Địa", "Long", "Phượng", "Kỳ", "Tuyết"]
NICK_TAIL = ["Tử", "Thần", "Vương", "Kiếm", "Đao", "Kiều", "Nhi", "Ca"]


def random_nick():
    """Sinh nick ngẫu nhiên."""
    return f"{random.choice(NICK_PREFIX)} {random.choice(NICK_MID)} {random.choice(NICK_TAIL)}"


class ZombieSpam:
    """Spam chậm 5-15 phút/lần (tránh detection)."""

    def __init__(self, send_fn, targets, msgs, min_delay=300, max_delay=900):
        self.send_fn = send_fn
        self.targets = targets
        self.msgs = msgs
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        i = 0
        while not self.stop.is_set():
            for t in self.targets:
                if self.stop.is_set():
                    return
                msg = self.msgs[i % len(self.msgs)]
                i += 1
                try:
                    self.send_fn(t, msg)
                except Exception:
                    pass
                d = random.uniform(self.min_delay, self.max_delay)
                for _ in range(int(d)):
                    if self.stop.is_set():
                        return
                    time.sleep(1)


def schedule_send(send_fn, target, msg, delay_seconds):
    """Hẹn giờ gửi tin."""
    def _run():
        time.sleep(delay_seconds)
        try:
            send_fn(target, msg)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def extract_uids_from_text(text):
    """Tìm UID (15-17 số) trong text."""
    import re
    return list(set(re.findall(r'\b\d{15,17}\b', text)))


def auto_backup_all():
    """Backup tất cả cookie đã lưu."""
    from cookie_guard_v3 import GUARD3
    from data_store import COOKIES
    out = {}
    for uid, d in COOKIES.all().items():
        fb_list = d.get("fb", [])
        for c in fb_list:
            GUARD3.backup(c, "fb")
        z_list = d.get("zalo", [])
        for z in z_list:
            GUARD3.backup(json.dumps(z), "zalo")
        out[uid] = {"fb": len(fb_list), "zalo": len(z_list)}
    return out


def ip_info():
    """Lấy thông tin IP server."""
    try:
        import requests
        return requests.get("https://ipinfo.io/json", timeout=10).json()
    except Exception:
        return {"error": "fail"}


def gen_random_msg(n=1):
    """Sinh tin nhắn random."""
    words = ["alo", "hi", "hú", "ê", "này", "vcl", "tr", "oke", "cay", "thua",
             "chạy đi", "nhanh", "hăng", "im", "nói đi", "kệ", "nhây", "chill",
             "lỏ", "quạo"]
    return [random.choice(words) for _ in range(n)]
