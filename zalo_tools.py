import json, time, base64, random
import requests
from Crypto.Cipher import AES
from firewall_v7 import FW
from anti_ban_v3 import ANTIBAN
from cookie_guard_v3 import GUARD3

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
            out.append({"id": gid, "name": info["name"], "members": info["totalMember"]})
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
        return {"name": info.get("name", "?"), "totalMember": info.get("totalMember", "?")}

    def send(self, msg, thread_id, is_group=True, color=None):
        url = ("https://tt-group-wpa.chat.zalo.me/api/group/sendmsg"
               if is_group
               else "https://tt-chat2-wpa.chat.zalo.me/api/message/sms")
        pl = {
            "message": msg,
            "clientId": str(int(time.time() * 1000)),
            "imei": self.imei,
        }
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

    def spam_loop_colored(self, targets, messages, delay, is_group,
                          stop_event, colors=None, on_log=None):
        """Xả tin + auto đổi màu. Min 3s + anti-ban."""
        user_delay = max(3.0, float(delay))
        color_codes = [c["code"] for c in (colors or ZALO_TEXT_COLORS)]
        i = 0
        color_idx = 0
        consecutive_ok = 0

        while not stop_event.is_set():
            for tid in targets:
                if stop_event.is_set():
                    return
                msg = messages[i % len(messages)]
                i += 1
                color = color_codes[color_idx % len(color_codes)]
                color_idx += 1

                self.fw.behavior.pre_send()
                msg_h = self.fw.behavior.humanize(msg)
                msg_h = self.fw.behavior.entropy_mask(
                    self.fw.behavior.vary(
                        self.fw.behavior.typo(msg_h)))
                try:
                    self.set_typing(tid, is_group)
                    time.sleep(min(self.fw.behavior.typing(msg_h), 4.0))
                    r = self.send(msg_h, tid, is_group, color=color)
                    if r and r.status_code == 200:
                        consecutive_ok += 1
                        if on_log:
                            on_log(f"✅ [{color}] {tid}: {msg_h[:25]}")
                    else:
                        consecutive_ok = 0
                        if on_log:
                            on_log(f"❌ {tid}")
                except Exception as e:
                    if on_log:
                        on_log(f"⚠️ {tid}: {e}")

                actual = max(3.0, user_delay * random.uniform(0.9, 1.35))
                if consecutive_ok > 5 and user_delay > 3.0:
                    actual = max(3.0, user_delay * random.uniform(0.75, 1.0))
                if ANTIBAN.is_sleep_hour():
                    actual += random.uniform(5.0, 15.0)

                for _ in range(int(actual)):
                    if stop_event.is_set():
                        return
                    time.sleep(1)
                frac = actual - int(actual)
                if frac > 0 and not stop_event.is_set():
                    time.sleep(frac)

                self.fw.behavior.maybe_break()

    def spam_loop(self, targets, messages, delay, is_group, stop_event, on_log=None):
        self.spam_loop_colored(targets, messages, delay, is_group,
                               stop_event, colors=[{"code": None}], on_log=on_log)
