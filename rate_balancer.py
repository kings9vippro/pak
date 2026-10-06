"""Chỉnh delay spam. Min 3s."""
import os, json, threading

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
PATH = os.path.join(DATA_DIR, "rate_config.json")
_lock = threading.Lock()
MIN_SAFE_DELAY = 3.0

DEFAULTS = {
    "fb_send": 4.0,
    "fb_edit": 30.0,
    "zalo_send": 3.0,
    "zalo_color": 3.0,
    "zalo_theme": 10.0,
    "discord_send": 3.0,
    "telegram_send": 3.0,
    "gmail_send": 10.0,
    "sms_send": 5.0,
    "ig_send": 8.0,
    "wechat_send": 4.0,
}


def _load():
    if not os.path.exists(PATH):
        return dict(DEFAULTS)
    try:
        with open(PATH, encoding="utf-8") as f:
            d = json.load(f)
        for k, v in DEFAULTS.items():
            d.setdefault(k, v)
        return d
    except Exception:
        return dict(DEFAULTS)


def _save(d):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def get(key: str, default=None) -> float:
    with _lock:
        return _load().get(key, default if default is not None else DEFAULTS.get(key, 3.0))


def set_(key: str, value: float):
    with _lock:
        d = _load()
        d[key] = max(MIN_SAFE_DELAY, float(value))
        _save(d)


def all_() -> dict:
    with _lock:
        return _load()


def reset():
    with _lock:
        _save(dict(DEFAULTS))
