"""
ANTI-BAN v2.0 — Phòng ban chuyên sâu
- Fingerprint consistency (giữ ổn định, không đổi liên tục)
- Session rotation (không dùng 1 session quá lâu)
- Warmup requirement (không spam ngay sau khi thêm cookie)
- Cooldown sau fail (nghỉ dài nếu detect)
- Behavior clustering (gộp nhiều tin thành 1 đợt)
- Traffic shaping (giãn cách random)
- Cookie age tracking (không dùng cookie quá cũ)
"""
import time, random, threading, hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class CookieMeta:
    cookie: str
    added_at: float = field(default_factory=time.time)
    last_used: float = 0.0
    last_warm: float = 0.0
    warm_count: int = 0
    fail_streak: int = 0
    ok_count: int = 0
    fail_count: int = 0
    disabled: bool = False
    cooldown_until: float = 0.0


class AntiBan:
    def __init__(self):
        self.metas = {}
        self.lock = threading.Lock()
        self.hourly = deque(maxlen=3600)   # lưu timestamp các request
        self.daily_sent = {}

    # ---------- Cookie age ----------
    def register(self, cookie: str) -> CookieMeta:
        h = self._hash(cookie)
        with self.lock:
            if h not in self.metas:
                self.metas[h] = CookieMeta(cookie=cookie)
            return self.metas[h]

    def _hash(self, c: str) -> str:
        return hashlib.md5(c.encode()).hexdigest()[:12]

    # ---------- Warmup requirement ----------
    def needs_warmup(self, cookie: str, min_warm_age: float = 300) -> bool:
        """
        Cookie mới (chưa warm > 5 phút) → cần warm trước khi spam.
        """
        m = self.register(cookie)
        return (time.time() - m.last_warm) > min_warm_age

    def mark_warm(self, cookie: str):
        m = self.register(cookie)
        with self.lock:
            m.last_warm = time.time()
            m.warm_count += 1

    # ---------- Cooldown ----------
    def cooldown(self, cookie: str, seconds: float):
        m = self.register(cookie)
        with self.lock:
            m.cooldown_until = max(m.cooldown_until, time.time() + seconds)

    def in_cooldown(self, cookie: str) -> float:
        m = self.register(cookie)
        with self.lock:
            left = m.cooldown_until - time.time()
            return max(0.0, left)

    # ---------- Fail streak ----------
    def report(self, cookie: str, ok: bool):
        m = self.register(cookie)
        with self.lock:
            if ok:
                m.ok_count += 1
                m.fail_streak = 0
            else:
                m.fail_count += 1
                m.fail_streak += 1
            # Nếu fail 5 lần liên tiếp → cooldown 5 phút
            if m.fail_streak >= 5:
                m.cooldown_until = time.time() + 300
                m.fail_streak = 0
            # Nếu fail 15 lần tổng và tỉ lệ ok thấp → disable 1h
            if m.fail_count >= 15 and (m.ok_count / max(m.fail_count, 1)) < 0.2:
                m.cooldown_until = time.time() + 3600
                m.disabled = True

    def is_disabled(self, cookie: str) -> bool:
        m = self.register(cookie)
        with self.lock:
            if not m.disabled: return False
            if time.time() > m.cooldown_until:
                m.disabled = False
                m.fail_count = 0
                m.ok_count = 0
                return False
            return True

    # ---------- Traffic shaping ----------
    def register_request(self):
        with self.lock:
            self.hourly.append(time.time())

    def hourly_rate(self) -> int:
        with self.lock:
            cutoff = time.time() - 3600
            self.hourly = deque([t for t in self.hourly if t > cutoff], maxlen=3600)
            return len(self.hourly)

    def should_slow_down(self, max_per_hour: int = 200) -> bool:
        return self.hourly_rate() > max_per_hour

    # ---------- Session rotation ----------
    def rotate_session_after(self, n: int = 50):
        """Báo cần đổi session sau N request."""
        # Logic này được dùng ở tầng Firewall.request nếu cần
        return random.randint(n // 2, n * 2)


ANTIBAN = AntiBan()