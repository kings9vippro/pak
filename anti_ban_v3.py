# ============================================================
# anti_ban_v3.py — Chống ban chuyên sâu FB + Zalo
# - Warmup bắt buộc cho cookie mới
# - Risk score realtime
# - Auto cooldown khi fail streak
# - Traffic shaping max 150 req/h
# - Biological rhythm (delay thêm vào 0h-6h sáng)
# ============================================================
import time
import threading
import hashlib
from collections import deque
from dataclasses import dataclass, field


@dataclass
class CookieMeta:
    """Metadata theo dõi 1 cookie."""
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
    request_count: int = 0
    hour_bucket: list = field(default_factory=list)


class AntiBan:
    def __init__(self):
        self.metas = {}
        self.lock = threading.Lock()
        self.max_per_hour = 150

    def _hash(self, c: str) -> str:
        return hashlib.md5(c.encode()).hexdigest()[:12]

    def register(self, cookie: str) -> CookieMeta:
        """Đăng ký cookie, trả meta."""
        h = self._hash(cookie)
        with self.lock:
            if h not in self.metas:
                self.metas[h] = CookieMeta(cookie=cookie)
            return self.metas[h]

    # ---------- Warmup ----------
    def needs_warmup(self, cookie: str, min_warm_age: float = 300) -> bool:
        """Cookie mới cần warm trước 5 phút."""
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

    # ---------- Risk ----------
    def get_risk_score(self, cookie: str) -> float:
        """Điểm rủi ro 0.0-1.0."""
        m = self.register(cookie)
        with self.lock:
            total = m.ok_count + m.fail_count
            if total == 0:
                return 0.0
            fail_rate = m.fail_count / total
            streak_factor = min(1.0, m.fail_streak / 5)
            return min(1.0, fail_rate * 0.7 + streak_factor * 0.3)

    def suggest_cooldown(self, cookie: str) -> int:
        r = self.get_risk_score(cookie)
        if r > 0.8:
            return 900
        if r > 0.6:
            return 300
        if r > 0.4:
            return 60
        return 0

    # ---------- Report ----------
    def report(self, cookie: str, ok: bool):
        """Ghi nhận kết quả, tự động cooldown/disable nếu cần."""
        m = self.register(cookie)
        with self.lock:
            m.request_count += 1
            if ok:
                m.ok_count += 1
                m.fail_streak = 0
            else:
                m.fail_count += 1
                m.fail_streak += 1
            # 5 lần fail liên tiếp → cooldown 5 phút
            if m.fail_streak >= 5:
                m.cooldown_until = time.time() + 300
                m.fail_streak = 0
            # Tổng fail >= 15 và tỉ lệ ok thấp → disable 1h
            if m.fail_count >= 15 and (m.ok_count / max(m.fail_count, 1)) < 0.2:
                m.cooldown_until = time.time() + 3600
                m.disabled = True

    def is_disabled(self, cookie: str) -> bool:
        m = self.register(cookie)
        with self.lock:
            if not m.disabled:
                return False
            if time.time() > m.cooldown_until:
                m.disabled = False
                m.fail_count = 0
                m.ok_count = 0
                return False
            return True

    # ---------- Traffic shaping ----------
    def register_request(self, cookie: str):
        m = self.register(cookie)
        with self.lock:
            now = time.time()
            m.hour_bucket = [t for t in m.hour_bucket if now - t < 3600]
            m.hour_bucket.append(now)

    def should_slow(self, cookie: str) -> bool:
        m = self.register(cookie)
        with self.lock:
            return len(m.hour_bucket) > self.max_per_hour

    # ---------- Biological rhythm ----------
    @staticmethod
    def is_sleep_hour() -> bool:
        """0h-6h sáng: ít người dùng hoạt động."""
        h = time.localtime().tm_hour
        return 0 <= h < 6

    def biological_delay(self, cookie: str) -> float:
        if self.is_sleep_hour():
            return random.uniform(5.0, 15.0)
        return 0.0


import random  # noqa: E402
ANTIBAN = AntiBan()
