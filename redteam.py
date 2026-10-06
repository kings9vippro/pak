# ============================================================
# redteam.py — Red Team Sim (không payload thật)
# ============================================================
import os
import time
import base64


class WormSim:
    def __init__(self, hosts):
        self.hosts = hosts
        self.log = []

    def scan(self):
        for h in self.hosts:
            self.log.append(f"[scan] {h} port 445 (SIMULATED)")
            time.sleep(0.05)
        return self.log

    def propagate(self, name):
        for h in self.hosts:
            self.log.append(f"[propagate] {name} → {h} (SIMULATED)")
        return self.log


class DropperSim:
    def __init__(self, d="./lab"):
        os.makedirs(d, exist_ok=True)
        self.d = d

    def stage(self, name, content):
        p = os.path.join(self.d, name)
        with open(p, "wb") as f:
            f.write(content)
        return p


class C2Sim:
    def __init__(self):
        self.beacons = []

    def beacon(self, id, data):
        self.beacons.append({"id": id, "data": data, "ts": time.time()})
        return {"status": "logged"}


class KeyloggerSim:
    def __init__(self):
        self.buf = []

    def feed(self, k):
        self.buf.append(k)
        self.buf = self.buf[-500:]

    def dump(self):
        return "".join(self.buf)


class RansomSim:
    def __init__(self, d="./lab/ransom"):
        os.makedirs(d, exist_ok=True)
        self.d = d

    def encrypt_demo(self, files):
        key = os.urandom(32)
        note = os.path.join(self.d, "README_LOCKED.txt")
        with open(note, "w") as f:
            f.write("SIMULATION. Key: " + key.hex())
        out = []
        for fp in files:
            if not os.path.isfile(fp):
                continue
            try:
                dst = os.path.join(self.d, os.path.basename(fp) + ".locked")
                with open(fp, "rb") as r, open(dst, "wb") as w:
                    w.write(base64.b64encode(r.read()))
                out.append(dst)
            except Exception:
                pass
        return {"note": note, "files": out}


# ----- PHISH TEMPLATE (KHÔNG có dấu ``` bên trong) -----
PHISH_FB = ("<html><body><form>"
            "<input name='email'>"
            "<input name='pass' type='password'>"
            "<button>Login</button>"
            "</form><!--SIM--></body></html>")

PHISH_ZALO = ("<html><body><form>"
              "<input name='phone'>"
              "<input name='pass' type='password'>"
              "<button>Đăng nhập</button>"
              "</form><!--SIM--></body></html>")

PHISH_TPL = {
    "fb": PHISH_FB,
    "zalo": PHISH_ZALO,
}


def gen_phish(t, out="./lab/phish.html"):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(PHISH_TPL.get(t, "<html>sim</html>"))
    return out


class ExploitSim:
    def scan_web(self, url):
        return [{"vuln": v, "url": url, "status": "SIMULATED"}
                for v in ["SQLi", "XSS", "LFI", "RCE"]]


def build_marker(name, text="SIMULATION"):
    return b"PK\x03\x04" + f"# {name} {text}\n".encode() + os.urandom(64)
