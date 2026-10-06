import time, random
from fb_edit import FBEdit
from firewall_v7 import FW
from anti_ban_v3 import ANTIBAN


class FBAutoEdit:
    def __init__(self):
        self.edit = FBEdit()
        self.fw = FW["fb"]

    def _delay(self, base, cookie):
        d = max(3.0, base * random.uniform(0.9, 1.4))
        if ANTIBAN.is_sleep_hour():
            d += random.uniform(5.0, 15.0)
        return d

    def auto_bio(self, cookie, bios, delay, stop_event, on_log=None):
        i = 0
        while not stop_event.is_set():
            b = bios[i % len(bios)]
            i += 1
            try:
                self.edit.set_bio(cookie, b)
                if on_log:
                    on_log(f"✅ bio={b[:30]}")
            except Exception as e:
                if on_log:
                    on_log(f"❌ {e}")
            time.sleep(self._delay(delay, cookie))
            self.fw.behavior.maybe_break()

    def auto_avatar(self, cookie, urls, delay, stop_event, on_log=None):
        i = 0
        while not stop_event.is_set():
            u = urls[i % len(urls)]
            i += 1
            try:
                self.edit.set_avatar(cookie, image_url=u)
                if on_log:
                    on_log(f"✅ avatar={u[:40]}")
            except Exception as e:
                if on_log:
                    on_log(f"❌ {e}")
            time.sleep(self._delay(delay * 2, cookie))
            self.fw.behavior.maybe_break()

    def auto_cover(self, cookie, urls, delay, stop_event, on_log=None):
        i = 0
        while not stop_event.is_set():
            u = urls[i % len(urls)]
            i += 1
            try:
                self.edit.set_cover(cookie, image_url=u)
                if on_log:
                    on_log(f"✅ cover={u[:40]}")
            except Exception as e:
                if on_log:
                    on_log(f"❌ {e}")
            time.sleep(self._delay(delay * 2, cookie))
            self.fw.behavior.maybe_break()

    def auto_story(self, cookie, texts, delay, stop_event, on_log=None):
        i = 0
        while not stop_event.is_set():
            t = texts[i % len(texts)]
            i += 1
            try:
                self.edit.set_story(cookie, text=t)
                if on_log:
                    on_log(f"✅ story={t[:30]}")
            except Exception as e:
                if on_log:
                    on_log(f"❌ {e}")
            time.sleep(self._delay(delay, cookie))
            self.fw.behavior.maybe_break()
