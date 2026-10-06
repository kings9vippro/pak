"""FB Token Grabber — cache 1h, không die cookie."""
import re, json, time, random, threading, hashlib
from dataclasses import dataclass
from typing import Optional, Dict
from firewall_v7 import FW
from cookie_guard_v3 import GUARD3


@dataclass
class FBToken:
    access_token: str = ""
    fb_dtsg: str = ""
    lsd: str = ""
    jazoest: str = ""
    user_id: str = ""
    cookie: str = ""
    fetched_at: float = 0.0
    ttl: float = 3600.0

    def is_valid(self) -> bool:
        return bool(self.access_token) and (time.time() - self.fetched_at) < self.ttl

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "fb_dtsg": self.fb_dtsg,
            "lsd": self.lsd,
            "jazoest": self.jazoest,
            "user_id": self.user_id,
            "fetched_at": self.fetched_at,
            "ttl": self.ttl,
        }


class FBTokenGrabber:
    _cache: Dict[str, FBToken] = {}
    _lock = threading.Lock()
    _fetch_lock = threading.Lock()

    def __init__(self):
        self.fw = FW["fb"]

    def grab(self, cookie: str, force: bool = False) -> Optional[FBToken]:
        key = self._key(cookie)
        with self._lock:
            t = self._cache.get(key)
        if t and t.is_valid() and not force:
            return t
        with self._fetch_lock:
            with self._lock:
                t = self._cache.get(key)
            if t and t.is_valid() and not force:
                return t
            new = self._fetch(cookie)
            if new:
                with self._lock:
                    self._cache[key] = new
            return new

    def quick(self, cookie: str) -> Optional[dict]:
        t = self.grab(cookie)
        return t.to_dict() if t else None

    def invalidate(self, cookie: str):
        with self._lock:
            self._cache.pop(self._key(cookie), None)

    @staticmethod
    def _key(cookie: str) -> str:
        c = re.search(r"c_user=(\d+)", cookie)
        x = re.search(r"xs=([^;]+)", cookie)
        raw = f"{c.group(1) if c else '0'}|{x.group(1) if x else ''}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _fetch(self, cookie: str) -> Optional[FBToken]:
        h = {"Cookie": cookie}
        r = self.fw.get("https://www.facebook.com/", cookie=cookie)
        if not r or r.status_code != 200:
            return None
        html = r.text

        fb_dtsg = self._grab(html, [
            r'"token":"(.*?)"',
            r'name="fb_dtsg" value="(.*?)"',
            r'"DTSGInitialData".*?"token":"(.*?)"',
        ])
        lsd = self._grab(html, [
            r'"LSD",\[\],{"token":"(.*?)"',
            r'name="lsd" value="(.*?)"',
        ])
        jazoest = self._grab(html, [r'jazoest=(\d+)', r'name="jazoest" value="(\d+)"'])
        uid = self._grab(html, [r'"USER_ID":"(\d+)"', r'"userID":"(\d+)"'])

        if not fb_dtsg:
            return None

        time.sleep(random.uniform(0.6, 1.6))

        access_token = ""
        for url in (
            "https://business.facebook.com/content_management",
            "https://business.facebook.com/business_locations",
        ):
            try:
                rr = self.fw.get(url, cookie=cookie)
                if rr and rr.status_code == 200:
                    at = re.search(r'"accessToken":"(.*?)"', rr.text)
                    if at:
                        access_token = at.group(1)
                        break
            except Exception:
                continue
            time.sleep(random.uniform(0.5, 1.2))

        if not access_token:
            access_token = cookie

        return FBToken(
            access_token=access_token,
            fb_dtsg=fb_dtsg,
            lsd=lsd or fb_dtsg,
            jazoest=jazoest or "22036",
            user_id=uid or "0",
            cookie=cookie,
            fetched_at=time.time(),
            ttl=3600.0,
        )

    @staticmethod
    def _grab(html: str, patterns) -> str:
        for p in patterns:
            m = re.search(p, html)
            if m:
                return m.group(1)
        return ""


TOKEN_GRABBER = FBTokenGrabber()
