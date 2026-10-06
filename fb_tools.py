import re, json, time, random
from firewall_v6 import FW
from anti_ban_v2 import ANTIBAN
from fb_token import TOKEN_GRABBER
from rate_balancer import get as rate_get


class Facebook:
    def __init__(self):
        self.fw = FW["fb"]

    def check(self, cookie):
        try:
            r = self.fw.get("https://mbasic.facebook.com/profile.php",
                            cookie=cookie)
            if not r or r.status_code != 200:
                ANTIBAN.report(cookie, False)
                return None
            name = re.search(r'<title>(.*?)</title>', r.text)
            uid = re.search(r"c_user=(\d+)", cookie)
            ANTIBAN.report(cookie, True)
            return {"name": name.group(1).strip() if name else "?",
                    "uid": uid.group(1) if uid else "?"}
        except Exception:
            return None

    def get_threads(self, cookie, limit=500):
        m = re.search(r"c_user=(\d+)", cookie)
        if not m: return {"error":"Thiếu c_user"}
        uid = m.group(1)
        tok = TOKEN_GRABBER.grab(cookie)
        if not tok: return {"error":"Không lấy token"}
        form = {
            "av": uid, "__user": uid, "fb_dtsg": tok.fb_dtsg,
            "jazoest": tok.jazoest, "__a":"1", "__req":"1b",
            "__rev":"1015919737", "__comet_req":"15",
            "__spin_r":"999999999", "__spin_b":"trunk",
            "__spin_t": str(int(time.time())),
            "queries": json.dumps({"o0":{
                "doc_id":"3336396659757871",
                "query_params":{"limit":limit,"before":None,"tags":["INBOX"],
                                "includeDeliveryReceipts":False,"includeSeqID":True}}}),
        }
        h = {"Content-Type":"application/x-www-form-urlencoded",
             "X-FB-Friendly-Name":"MessengerThreadListQuery"}
        r = self.fw.post("https://www.facebook.com/api/graphqlbatch/",
                         cookie=cookie, data=form, headers=h)
        if not r: return {"error":"Request fail"}
        try:
            raw = r.text.split('{"successful_results"')[0]
            data = json.loads(raw)
            nodes = data["o0"]["data"]["viewer"]["message_threads"]["nodes"]
            out = [{"thread_id": n["thread_key"]["thread_fbid"],
                    "thread_name": n.get("name") or "Không tên"}
                   for n in nodes if n.get("thread_key") and n["thread_key"].get("thread_fbid")]
            return out
        except Exception as e:
            return {"error": str(e)}

    def send(self, cookie, box_id, text, custom_delay=None):
        """Gửi tin có behavior. custom_delay override rate."""
        if ANTIBAN.is_disabled(cookie):
            return None
        if ANTIBAN.in_cooldown(cookie) > 0:
            return None

        tok = TOKEN_GRABBER.grab(cookie)
        if not tok: return None

        # Behavior: đọc + gõ
        self.fw.behavior.pre_send()
        text = self.fw.behavior.entropy_mask(
            self.fw.behavior.vary(
                self.fw.behavior.typo(
                    self.fw.behavior.humanize(text))))
        typing = self.fw.behavior.typing(text)

        ts = int(time.time() * 1000)
        data = {
            "thread_fbid": box_id, "action_type": "ma-type:user-generated-message",
            "body": text, "client": "mercury", "author": f"fbid:{tok.user_id}",
            "timestamp": ts, "offline_threading_id": ts, "message_id": ts,
            "source": "source:chat:web", "ephemeral_ttl_mode": "0",
            "__user": tok.user_id, "__a": "1", "__req": "1b", "__rev": "1015919737",
            "fb_dtsg": tok.fb_dtsg, "jazoest": tok.jazoest,
        }
        h = {"Origin":"https://www.facebook.com",
             "Referer": f"https://www.facebook.com/messages/t/{box_id}",
             "Content-Type":"application/x-www-form-urlencoded"}

        # Đợi typing time nhưng không quá dài
        time.sleep(min(typing, 4.0))

        r = self.fw.post("https://www.facebook.com/messaging/send/",
                         cookie=cookie, data=data, headers=h)
        ok = bool(r and r.status_code == 200)
        ANTIBAN.report(cookie, ok)
        ANTIBAN.register_request()
        return r

    def spam_loop(self, cookie, boxes, messages, delay,
                  stop_event, on_log=None):
        """
        Xả tin siêu nhanh, an toàn min 3s.
        delay là delay user nhập, sẽ tự clamp >= 3.
        """
        # Clamp min 3s
        user_delay = max(3.0, float(delay))

        # Warmup requirement
        if ANTIBAN.needs_warmup(cookie):
            if on_log: on_log("⚠️ Cookie mới — warmup...")
            from cookie_guard_v2 import GUARD2
            GUARD2.warm_fb(cookie)
            ANTIBAN.mark_warm(cookie)

        i = 0
        consecutive_ok = 0
        while not stop_event.is_set():
            # Nếu cookie bị disable → dừng
            if ANTIBAN.is_disabled(cookie):
                if on_log: on_log("🚫 Cookie bị disable — dừng task")
                return

            # Cooldown → chờ
            cd = ANTIBAN.in_cooldown(cookie)
            if cd > 0:
                if on_log: on_log(f"💤 Cooldown {cd:.0f}s")
                for _ in range(int(cd)):
                    if stop_event.is_set(): return
                    time.sleep(1)
                continue

            for box in boxes:
                if stop_event.is_set(): return

                msg = messages[i % len(messages)]; i += 1
                try:
                    r = self.send(cookie, box, msg)
                    if r and r.status_code == 200:
                        consecutive_ok += 1
                        if on_log:
                            on_log(f"✅ [{consecutive_ok}] {box}: {msg[:25]}")
                    else:
                        consecutive_ok = 0
                        if on_log:
                            on_log(f"❌ {box}")
                except Exception as e:
                    if on_log: on_log(f"⚠️ {box}: {e}")

                # Delay thực tế — luôn >= 3s, có jitter ±30%
                actual_delay = max(3.0, user_delay * random.uniform(0.9, 1.35))
                # Nếu đang trong giai đoạn ok liên tục, có thể rút ngắn tới 3s
                if consecutive_ok > 5 and user_delay > 3.0:
                    actual_delay = max(3.0, user_delay * random.uniform(0.75, 1.0))

                for _ in range(int(actual_delay)):
                    if stop_event.is_set(): return
                    time.sleep(1)
                # giây lẻ
                frac = actual_delay - int(actual_delay)
                if frac > 0 and not stop_event.is_set():
                    time.sleep(frac)

                # Behavior break
                self.fw.behavior.maybe_break()