import os, json, threading

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


class Store:
    def __init__(self, name):
        self.path = os.path.join(DATA_DIR, f"{name}.json")
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, k, d=None):
        with self.lock:
            return self.data.get(k, d)

    def set(self, k, v):
        with self.lock:
            self.data[k] = v
            self._save()

    def delete(self, k):
        with self.lock:
            self.data.pop(k, None)
            self._save()

    def all(self):
        with self.lock:
            return dict(self.data)


COOKIES = Store("cookies")
CONFIG = Store("config")
