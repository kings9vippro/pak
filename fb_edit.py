import json, time, random
from firewall_v7 import FW
from fb_token import TOKEN_GRABBER


class FBEdit:
    def __init__(self):
        self.fw = FW["fb"]

    def _headers(self, cookie):
        return {
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.facebook.com",
            "Referer": "https://www.facebook.com/",
        }

    def _graphql(self, cookie, friendly, variables, doc_id):
        tok = TOKEN_GRABBER.grab(cookie)
        if not tok:
            return None
        data = {
            "av": tok.user_id,
            "__user": tok.user_id,
            "fb_dtsg": tok.fb_dtsg,
            "lsd": tok.lsd,
            "jazoest": tok.jazoest,
            "__a": "1", "__req": "1b", "__rev": "1015919737",
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": friendly,
            "server_timestamps": "true",
            "doc_id": doc_id,
            "variables": json.dumps(variables),
        }
        h = self._headers(cookie)
        h["X-FB-Friendly-Name"] = friendly
        self.fw.behavior.pre_send()
        time.sleep(random.uniform(0.5, 1.5))
        r = self.fw.post("https://www.facebook.com/api/graphql/",
                         cookie=cookie, data=data, headers=h)
        if not r:
            return None
        try:
            txt = r.text
            if txt.startswith("for (;;);"):
                txt = txt[9:]
            return json.loads(txt)
        except Exception:
            return {"_raw": r.text[:300]}

    def set_bio(self, cookie, text):
        tok = TOKEN_GRABBER.grab(cookie)
        if not tok:
            return None
        return self._graphql(cookie, "ProfileCometBioSaveMutation", {
            "input": {
                "bio": text,
                "actor_id": tok.user_id,
                "client_mutation_id": str(random.randint(10000, 99999)),
                "bio_entities": None,
            }
        }, "6766531750937525")

    def set_name(self, cookie, first, middle, last, password=""):
        tok = TOKEN_GRABBER.grab(cookie)
        if not tok:
            return None
        return self._graphql(cookie, "ProfileCometSetNameMutation", {
            "input": {
                "first_name": first,
                "middle_name": middle,
                "last_name": last,
                "password": password,
                "actor_id": tok.user_id,
                "client_mutation_id": str(random.randint(10000, 99999)),
            }
        }, "6205262395697366")

    def set_story(self, cookie, text="", photo_id=None):
        tok = TOKEN_GRABBER.grab(cookie)
        if not tok:
            return None
        att = []
        if photo_id:
            att.append({"photo": {"id": photo_id}})
        return self._graphql(cookie, "ComposerStoryCreateMutation", {
            "input": {
                "attachments": att,
                "audience": {"privacy": {
                    "allow": [], "base_state": "EVERYONE",
                    "deny": [], "tag_expansion_state": "UNSPECIFIED",
                }},
                "message": {"ranges": [], "text": text},
                "actor_id": tok.user_id,
                "client_mutation_id": str(random.randint(10000, 99999)),
                "source": "WWW",
                "logging": {"composer_session_id": str(random.randint(10**9, 10**10))},
                "tracking": [None],
            }
        }, "7679274433406034")

    def set_avatar(self, cookie, image_url=None, image_bytes=None):
        pid = self._upload_photo(cookie, image_url, image_bytes)
        if not pid:
            return {"error": "Upload fail"}
        tok = TOKEN_GRABBER.grab(cookie)
        return self._graphql(cookie, "ProfilePicUpdateMutation", {
            "input": {
                "profile_picture_id": pid,
                "actor_id": tok.user_id,
                "client_mutation_id": str(random.randint(10000, 99999)),
            }
        }, "1696467079100051")

    def set_cover(self, cookie, image_url=None, image_bytes=None):
        pid = self._upload_photo(cookie, image_url, image_bytes)
        if not pid:
            return {"error": "Upload fail"}
        tok = TOKEN_GRABBER.grab(cookie)
        return self._graphql(cookie, "ProfileCometCoverPhotoUpdateMutation", {
            "input": {
                "photo_id": pid,
                "focus_x": 0.5, "focus_y": 0.5,
                "actor_id": tok.user_id,
                "client_mutation_id": str(random.randint(10000, 99999)),
            }
        }, "8431558881232338")

    def set_theme(self, cookie, thread_id, theme_id):
        tok = TOKEN_GRABBER.grab(cookie)
        if not tok:
            return None
        return self._graphql(cookie, "MessengerThreadThemeUpdateMutation", {
            "input": {
                "thread_fbid": thread_id,
                "theme_fbid": theme_id,
                "source": None,
                "sync_group": 1,
            }
        }, "6118370971053421")

    def set_emoji(self, cookie, thread_id, emoji):
        tok = TOKEN_GRABBER.grab(cookie)
        if not tok:
            return None
        return self._graphql(cookie, "MessengerThreadEmojiUpdateMutation", {
            "input": {
                "thread_fbid": thread_id,
                "emoji": emoji,
                "source": "MESSENGER",
                "sync_group": 1,
                "actor_id": tok.user_id,
                "client_mutation_id": str(random.randint(10000, 99999)),
            }
        }, "6767568687480178")

    def set_nickname(self, cookie, thread_id, user_id, nickname):
        tok = TOKEN_GRABBER.grab(cookie)
        if not tok:
            return None
        return self._graphql(cookie, "MessengerGroupSetNicknameMutation", {
            "input": {
                "thread_fbid": thread_id,
                "participant_id": user_id,
                "nickname": nickname,
                "actor_id": tok.user_id,
                "client_mutation_id": str(random.randint(10000, 99999)),
            }
        }, "2775574761710307")

    def _upload_photo(self, cookie, image_url=None, image_bytes=None):
        import requests as _r
        if image_url and not image_bytes:
            try:
                image_bytes = _r.get(image_url, timeout=20).content
            except Exception:
                return None
        if not image_bytes:
            return None
        tok = TOKEN_GRABBER.grab(cookie)
        if not tok:
            return None
        headers = {
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://www.facebook.com",
            "Referer": "https://www.facebook.com/",
        }
        params = {
            "av": tok.user_id, "__user": tok.user_id,
            "__a": "1", "__req": "z", "__rev": "1015919737",
            "fb_dtsg": tok.fb_dtsg, "jazoest": tok.jazoest,
            "__comet_req": "15",
        }
        files = {"upload_1024": ("image.jpg", image_bytes, "image/jpeg")}
        r = self.fw.post("https://www.facebook.com/ajax/mercury/upload.php",
                         cookie=cookie, headers=headers, params=params, files=files)
        if not r:
            return None
        try:
            data = json.loads(r.text.replace("for (;;);", ""))
            meta = data.get("payload", {}).get("metadata", {})
            for k, v in meta.items():
                if v.get("image_id"):
                    return v["image_id"]
                if v.get("photo_id"):
                    return v["photo_id"]
        except Exception:
            pass
        return None
