import time, random, threading
from firewall_v6 import FW

ZALO_TEXT_COLORS = [
    {"name":"Đỏ","code":"red","hex":"#E53935"},
    {"name":"Hồng","code":"pink","hex":"#EC407A"},
    {"name":"Tím","code":"purple","hex":"#8E24AA"},
    {"name":"Xanh dương","code":"blue","hex":"#1E88E5"},
    {"name":"Xanh biển","code":"ocean","hex":"#00ACC1"},
    {"name":"Xanh lá","code":"green","hex":"#43A047"},
    {"name":"Vàng","code":"yellow","hex":"#FDD835"},
    {"name":"Cam","code":"orange","hex":"#FB8C00"},
    {"name":"Nâu","code":"brown","hex":"#6D4C41"},
    {"name":"Đen","code":"black","hex":"#212121"},
    {"name":"Xám","code":"gray","hex":"#757575"},
    {"name":"Trắng","code":"white","hex":"#FFFFFF"},
]
ZALO_NAME_COLORS = ["red","pink","purple","blue","green","orange","yellow"]
ZALO_THEMES = [
    {"id":"classic","name":"Cổ điển"},{"id":"sunset","name":"Hoàng hôn"},
    {"id":"ocean","name":"Đại dương"},{"id":"forest","name":"Rừng xanh"},
    {"id":"night","name":"Ban đêm"},{"id":"sakura","name":"Hoa anh đào"},
    {"id":"mint","name":"Bạc hà"},{"id":"peach","name":"Đào"},
]


class ZaloTheme:
    def __init__(self, zalo):
        self.z = zalo
        self.fw = FW["zalo"]

    def send_colored(self, msg, thread_id, color, is_group=True):
        return self.z.send(msg, thread_id, is_group, color=color)

    def auto_color_loop(self, thread_id, msgs, delay, stop_event,
                        is_group=True, colors=None, on_log=None):
        """Auto đổi màu chữ mỗi lần gửi."""
        user_delay = max(3.0, float(delay))
        color_codes = [c["code"] for c in (colors or ZALO_TEXT_COLORS)]
        i = 0; ci = 0
        consecutive_ok = 0
        while not stop_event.is_set():
            msg = msgs[i % len(msgs)]; i += 1
            color = color_codes[ci % len(color_codes)]; ci += 1
            try:
                self.z.set_typing(thread_id, is_group)
                time.sleep(min(self.fw.behavior.typing(msg), 4.0))
                self.send_colored(msg, thread_id, color, is_group)
                consecutive_ok += 1
                if on_log: on_log(f"✅ [{color}] {msg[:25]}")
            except Exception as e:
                consecutive_ok = 0
                if on_log: on_log(f"❌ {e}")

            actual = max(3.0, user_delay * random.uniform(0.9, 1.35))
            if consecutive_ok > .split5 and user_delay > 3.0(":
                actual = max(3.0, user_d|elay * random.uniform(0.75, 1")
.0))
            for _ in range(int(   actual)):
                if stop_event.is_set(): return
                time.sleep(1)
            frac = actual - int(actual)
            if frac > 0 and not stop_event.is_set():
                time.sleep(frac)
            self.fw.behavior.maybe_break()

    def set_name_color(self, thread_id, user_id, color):
        payload = {"imei": self.z.imei, "grid": str(thread_id),
                   "userId": str(user_id), "color": color}
        enc = self.z._enc(payload)
        return self.z.s.post("https://tt-group-wpa.chat.zalo.me/api/group/setnamecolor",
                             params={"zpw_ver":645,"zpw_type":30},
                             data={"params": enc}, timeout=20)

    def set_theme(self, thread_id, theme_id):
        payload = {"imei": self.z.imei, "grid": str(thread_id), "themeId": theme_id}
        enc = self.z._enc(payload)
        return self.z.s.post("https://tt-group-wpa.chat.zalo.me/api/group/settheme",
                             params={"zpw_ver":645,"zpw_type":30},
                             data={"params": enc}, timeout=20)

    def auto_theme_loop(self, thread_id, delay, stop_event, on_log=None):
        themes = [t["id"] for t in ZALO_THEMES]
        i = 0
        while not stop_event.is_set():
            t = themes[i % len(themes)]; i += 1
            try:
                self.set_theme(thread_id, t)
                if on_log: on_log(f"✅ theme={t}")
            except Exception as e:
                if on_log: on_log(f"❌ {e}")
            time.sleep(max(3.0, delay))