# ============================================================
# BOT BY ANH KHÔI — ALB FORGE v7.2
# Telegram: 8845944331:AAEN9CM-mui0Ga_HFENi9I52EcxsWtgg8Sk
# Admin: 6094686933
# Chạy trên Render Free dưới dạng Web Service (có HTTP server giả)
# ============================================================
import os
import re
import sys
import json
import time
import random
import threading
import asyncio
import warnings
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

warnings.filterwarnings("ignore")

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from telegram.constants import ParseMode

from utils import get_uptime, gen_imei
from firewall_v7 import FW
from anti_ban_v3 import ANTIBAN
from cookie_guard_v3 import GUARD3
from rate_balancer import (
    get as rate_get, set_ as rate_set, all_ as rate_all,
    reset as rate_reset, MIN_SAFE_DELAY
)
from fb_token import TOKEN_GRABBER
from fb_tools import Facebook
from fb_edit import FBEdit
from fb_profile_auto import FBAutoEdit
from zalo_qr import ZaloQRLogin, QR_TTL
from zalo_tools import Zalo, ZALO_TEXT_COLORS
from zalo_theme import (
    ZaloTheme, ZALO_TEXT_COLORS as ZTC, ZALO_NAME_COLORS, ZALO_THEMES
)
from data_store import COOKIES, CONFIG
from cookie_guide import (
    COOKIE_FB, COOKIE_ZALO, COOKIE_DISCORD, COOKIE_TELEGRAM,
    COOKIE_GMAIL, COOKIE_IG, COOKIE_WECHAT, COOKIE_SMS
)
import redteam
import cool_features


# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "8845944331:AAEN9CM-mui0Ga_HFENi9I52EcxsWtgg8Sk"
)
ADMIN_IDS = [
    int(x) for x in
    os.environ.get("ADMIN_IDS", "6094686933").split(",")
    if x.strip().isdigit()
]
DATA_DIR = os.environ.get("DATA_DIR", "/tmp/alb_data")
os.makedirs(DATA_DIR, exist_ok=True)


# ============================================================
# FAKE HTTP SERVER — Giữ Render Free không kill worker
# Render yêu cầu Web Service phải bind PORT và trả HTTP 200 OK
# ============================================================
class _HealthHandler(BaseHTTPRequestHandler):
    """Handler trả 200 OK cho mọi request."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "5")
        self.end_headers()
        self.wfile.write(b"alive")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        # Tắt log spam từ HTTP server
        pass


def _start_health_server():
    """Chạy HTTP server trên port Render cấp."""
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        print(f"[HEALTH] HTTP server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"[HEALTH] Lỗi start server: {e}")


# ============================================================
# TASK MANAGER
# ============================================================
class Task:
    __slots__ = ("id", "type", "owner", "stop", "start", "thread", "meta")

    def __init__(self, id, type, owner, meta=None):
        self.id = id
        self.type = type
        self.owner = owner
        self.stop = threading.Event()
        self.start = datetime.now()
        self.thread = None
        self.meta = meta or {}

    def uptime(self):
        return get_uptime(self.start)


class Tasks:
    def __init__(self):
        self.d = {}
        self.lock = threading.Lock()

    def add(self, t):
        with self.lock:
            self.d[t.id] = t

    def remove(self, tid):
        with self.lock:
            t = self.d.pop(tid, None)
            if t:
                t.stop.set()
            return t

    def by_owner(self, o):
        with self.lock:
            return [t for t in self.d.values() if t.owner == o]

    def all(self):
        with self.lock:
            return list(self.d.values())


TASKS = Tasks()


def new_tid(p):
    return f"{p}_{int(time.time()*1000)}"


# ============================================================
# MENU
# ============================================================
MAIN_KB = [
    [InlineKeyboardButton("📘 Facebook", callback_data="m_fb"),
     InlineKeyboardButton("📞 Zalo", callback_data="m_zalo")],
    [InlineKeyboardButton("✏ FB Edit", callback_data="m_fb_edit"),
     InlineKeyboardButton("🎨 Zalo Theme", callback_data="m_zalo_theme")],
    [InlineKeyboardButton("🎮 Discord", callback_data="m_discord"),
     InlineKeyboardButton("📢 Telegram", callback_data="m_telegram")],
    [InlineKeyboardButton("✉ Gmail", callback_data="m_gmail"),
     InlineKeyboardButton("📲 SMS", callback_data="m_sms")],
    [InlineKeyboardButton("📷 Instagram", callback_data="m_ig"),
     InlineKeyboardButton("💼 WeChat", callback_data="m_wechat")],
    [InlineKeyboardButton("🛡 Firewall", callback_data="m_fw"),
     InlineKeyboardButton("⚙ Rate", callback_data="m_rate")],
    [InlineKeyboardButton("🔒 Cookie Guard", callback_data="m_guard"),
     InlineKeyboardButton("💾 Cookie Store", callback_data="m_ck")],
    [InlineKeyboardButton("📖 Guide", callback_data="m_guide"),
     InlineKeyboardButton("🔥 Cool", callback_data="m_cool")],
    [InlineKeyboardButton("🔴 RedTeam", callback_data="m_rt"),
     InlineKeyboardButton("📋 Tasks", callback_data="m_tasks")],
]

MENU_TEXT = {
    "m_fb": (
        "📘 *Facebook Firewall*\n\n"
        "`/fb_check <cookie>`\n"
        "`/fb_token <cookie>`\n"
        "`/fb_threads <cookie>`\n"
        "`/fb_send <cookie>|<box>|<msg>`\n"
        "`/fb_spam <cookie>|<box1,box2>|<msg1;msg2>|<delay>`"
    ),
    "m_fb_edit": (
        "✏ *FB Edit*\n\n"
        "`/fb_bio <cookie>|<text>`\n"
        "`/fb_name <cookie>|<first>|<middle>|<last>|<pass>`\n"
        "`/fb_avatar <cookie>|<img_url>`\n"
        "`/fb_cover <cookie>|<img_url>`\n"
        "`/fb_story <cookie>|<text>`\n"
        "`/fb_theme <cookie>|<thread>|<theme_id>`\n"
        "`/fb_emoji <cookie>|<thread>|<emoji>`\n"
        "`/fb_nick <cookie>|<thread>|<user>|<nick>`\n"
        "`/fb_auto_bio <cookie>|<bio1;bio2>|<delay>`\n"
        "`/fb_auto_avatar <cookie>|<url1;url2>|<delay>`\n"
        "`/fb_auto_cover <cookie>|<url1;url2>|<delay>`\n"
        "`/fb_auto_story <cookie>|<txt1;txt2>|<delay>`"
    ),
    "m_zalo": (
        "📞 *Zalo Firewall*\n\n"
        "`/zalo_qr` — QR login 120s\n"
        "`/zalo_check <imei>|<cookie>`\n"
        "`/zalo_groups <imei>|<cookie>`\n"
        "`/zalo_spam <imei>|<cookie>|<gid1,gid2>|<msg1;msg2>|<delay>`\n"
        "_Auto đổi màu chữ mỗi dòng. Delay min 3s._"
    ),
    "m_zalo_theme": (
        "🎨 *Zalo Theme/Color*\n\n"
        "`/zalo_color_list`\n"
        "`/zalo_color <imei>|<cookie>|<gid>|<msg1;msg2>|<delay>`\n"
        "`/zalo_namecolor <imei>|<cookie>|<gid>|<user>|<color>`\n"
        "`/zalo_theme <imei>|<cookie>|<gid>|<theme_id>`\n"
        "`/zalo_auto_theme <imei>|<cookie>|<gid>|<delay>`"
    ),
    "m_discord": "🎮 `/discord_spam <token>|<channel>|<msg1;msg2>|<delay>`",
    "m_telegram": "📢 `/tele_spam <bot_token>|<chat>|<msg1;msg2>|<delay>`",
    "m_gmail": "✉ `/gmail_spam <email>|<app_pass>|<to>|<msg1;msg2>|<delay>`",
    "m_sms": "📲 `/sms_spam <phone>`",
    "m_ig": "📷 `/ig_spam <sessionid>|<thread_ids>|<msg1;msg2>|<delay>`",
    "m_wechat": "💼 `/wechat_spam <corpid>|<secret>|<agent>|<user>|<msg1;msg2>|<delay>`",
    "m_fw": (
        "🛡 *FIREWALL v7 — 7 LỚP*\n\n"
        "`/fw_status`\n"
        "`/fw_reset`\n"
        "`/fw_antiban <cookie>`\n"
        "`/fw_risk <cookie>`"
    ),
    "m_rate": (
        f"⚙ *RATE CONFIG* (min {MIN_SAFE_DELAY}s)\n\n"
        "`/rate`\n`/rate_set <key> <giây>`\n`/rate_reset`\n`/rate_clear <key>`"
    ),
    "m_guard": (
        "🔒 *Cookie Guard*\n\n"
        "`/guard_status <cookie>`\n"
        "`/guard_backup`\n"
        "`/guard_warm <cookie>`\n"
        "`/guard_safe <cookie>`"
    ),
    "m_ck": (
        "💾 *Cookie Store*\n\n"
        "`/save_fb <cookie>`\n"
        "`/save_zalo <imei>|<cookie_json>`\n"
        "`/list_ck`\n"
        "`/del_ck <fb|zalo> <index>`\n"
        "`/warm_ck`"
    ),
    "m_guide": (
        "📖 `/cookie_fb` `/cookie_zalo` `/cookie_discord`\n"
        "`/cookie_telegram` `/cookie_gmail` `/cookie_ig`\n"
        "`/cookie_wechat` `/cookie_sms`"
    ),
    "m_cool": (
        "🔥 *Cool Features*\n\n"
        "`/nick` — random nick\n"
        "`/uid_extract <text>`\n"
        "`/ip_info`\n"
        "`/zombie <cookie>|<box>|<msg1;msg2>` — 5-15' / lần\n"
        "`/bomb <cookie>|<box>|<msg>|<delay>`\n"
        "`/backup_all`"
    ),
    "m_rt": (
        "🔴 *RedTeam Sim*\n\n"
        "`/rt_worm <hosts>`\n`/rt_dropper <name>`\n"
        "`/rt_c2 <id>|<json>`\n`/rt_keylog <text>`\n"
        "`/rt_ransom <files>`\n`/rt_phish <fb|zalo>`\n"
        "`/rt_exploit <url>`"
    ),
    "m_tasks": "📋 `/tasks` `/stop <n>` `/stop_all`",
}


# ============================================================
# DECORATOR
# ============================================================
def admin_only(func):
    async def w(update, ctx):
        if update.effective_user.id not in ADMIN_IDS:
            if update.message:
                await update.message.reply_text(
                    "⛔ Không có quyền. Bot by Anh Khôi.")
            return
        return await func(update, ctx)
    return w


# ============================================================
# START / MENU
# ============================================================
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Không có quyền.")
        return
    await update.message.reply_text(
        "🔥 *ALB FORGE v7.2*\n"
        "_Bot by Anh Khôi_\n"
        "_7-Layer Firewall — Anti-Ban Elite_\n\n"
        "Chọn chức năng:",
        reply_markup=InlineKeyboardMarkup(MAIN_KB),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cb_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data in MENU_TEXT:
        await q.edit_message_text(MENU_TEXT[q.data], parse_mode=ParseMode.MARKDOWN)
    elif q.data == "m_tasks":
        tasks = TASKS.by_owner(q.from_user.id)
        if not tasks:
            await q.edit_message_text("📭 Không có task.")
            return
        text = "*📋 Tasks:*\n\n"
        for i, t in enumerate(tasks, 1):
            text += f"`{i}.` [{t.type}] {t.uptime()}\n"
        text += "\n`/stop <n>` `/stop_all`"
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)


# ============================================================
# FIREWALL
# ============================================================
@admin_only
async def cmd_fw_status(update, ctx):
    text = "*🛡 FIREWALL v7 — 7 LỚP*\n\n"
    for name, fw in FW.items():
        text += fw.report() + "\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_fw_reset(update, ctx):
    for fw in FW.values():
        with fw.lock:
            fw.stats = {"ok": 0, "fail": 0, "blocked": 0, "banned": 0,
                        "cb": 0, "captcha": 0, "anomaly": 0}
    await update.message.reply_text("✅ Reset firewall stats.")


@admin_only
async def cmd_fw_antiban(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /fw_antiban <cookie>")
        return
    cookie = update.message.text.split(" ", 1)[1].strip()
    m = ANTIBAN.register(cookie)
    risk = ANTIBAN.get_risk_score(cookie)
    txt = (
        f"🛡 *Anti-Ban Cookie:*\n"
        f"• OK: `{m.ok_count}`\n"
        f"• Fail: `{m.fail_count}`\n"
        f"• Fail streak: `{m.fail_streak}`\n"
        f"• Disabled: `{m.disabled}`\n"
        f"• Cooldown left: `{ANTIBAN.in_cooldown(cookie):.0f}s`\n"
        f"• Warm count: `{m.warm_count}`\n"
        f"• Risk score: `{risk:.2f}`\n"
        f"• Suggest cooldown: `{ANTIBAN.suggest_cooldown(cookie)}s`\n"
        f"• Requests (1h): `{len(m.hour_bucket)}`"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_fw_risk(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /fw_risk <cookie>")
        return
    cookie = update.message.text.split(" ", 1)[1].strip()
    risk = ANTIBAN.get_risk_score(cookie)
    bar = "█" * int(risk * 20) + "░" * (20 - int(risk * 20))
    await update.message.reply_text(
        f"📊 Risk: `{risk:.2f}`\n`{bar}`",
        parse_mode=ParseMode.MARKDOWN)


# ============================================================
# RATE
# ============================================================
@admin_only
async def cmd_rate(update, ctx):
    d = rate_all()
    text = f"*⚙ RATE CONFIG* (min {MIN_SAFE_DELAY}s)\n\n"
    for k, v in d.items():
        text += f"`{k}` = `{v}`s\n"
    text += "\n`/rate_set <key> <giây>`"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_rate_set(update, ctx):
    if len(ctx.args) < 2:
        await update.message.reply_text("Cú pháp: /rate_set <key> <giây>")
        return
    try:
        v = float(ctx.args[1])
        if v < MIN_SAFE_DELAY:
            await update.message.reply_text(
                f"⚠️ Min an toàn là `{MIN_SAFE_DELAY}s`. Đã tự nâng.",
                parse_mode=ParseMode.MARKDOWN)
        rate_set(ctx.args[0], v)
        await update.message.reply_text(
            f"✅ `{ctx.args[0]}` = `{max(v, MIN_SAFE_DELAY)}`s",
            parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_rate_reset(update, ctx):
    rate_reset()
    await update.message.reply_text("✅ Reset rate.")


@admin_only
async def cmd_rate_clear(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /rate_clear <key>")
        return
    key = ctx.args[0]
    for fw_k, fw in FW.items():
        if key.startswith(fw_k):
            fw.rate.manual = None
    await update.message.reply_text(
        f"✅ Cleared `{key}`", parse_mode=ParseMode.MARKDOWN)


# ============================================================
# COOKIE GUARD
# ============================================================
@admin_only
async def cmd_guard_status(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /guard_status <cookie>")
        return
    cookie = update.message.text.split(" ", 1)[1].strip()
    pct = GUARD3.health_percent(cookie)
    safe = GUARD3.is_safe(cookie)
    await update.message.reply_text(
        f"🔒 Health: `{pct:.1f}%`\nSafe: `{safe}`",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_guard_backup(update, ctx):
    res = cool_features.auto_backup_all()
    await update.message.reply_text(
        f"✅ Backup xong: `{json.dumps(res)}`",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_guard_warm(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /guard_warm <cookie>")
        return
    cookie = update.message.text.split(" ", 1)[1].strip()
    threading.Thread(target=GUARD3.warm_fb, args=(cookie,), daemon=True).start()
    await update.message.reply_text("🔥 Đang warm cookie...")


@admin_only
async def cmd_guard_safe(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /guard_safe <cookie>")
        return
    cookie = update.message.text.split(" ", 1)[1].strip()
    safe = GUARD3.is_safe(cookie)
    pct = GUARD3.health_percent(cookie)
    await update.message.reply_text(
        f"{'✅' if safe else '⚠️'} Safe: `{safe}` | Health: `{pct:.1f}%`",
        parse_mode=ParseMode.MARKDOWN)


# ============================================================
# COOKIE GUIDE
# ============================================================
@admin_only
async def cmd_cookie_fb(u, c):
    await u.message.reply_text(COOKIE_FB)


@admin_only
async def cmd_cookie_zalo(u, c):
    await u.message.reply_text(COOKIE_ZALO)


@admin_only
async def cmd_cookie_discord(u, c):
    await u.message.reply_text(COOKIE_DISCORD)


@admin_only
async def cmd_cookie_telegram(u, c):
    await u.message.reply_text(COOKIE_TELEGRAM)


@admin_only
async def cmd_cookie_gmail(u, c):
    await u.message.reply_text(COOKIE_GMAIL)


@admin_only
async def cmd_cookie_ig(u, c):
    await u.message.reply_text(COOKIE_IG)


@admin_only
async def cmd_cookie_wechat(u, c):
    await u.message.reply_text(COOKIE_WECHAT)


@admin_only
async def cmd_cookie_sms(u, c):
    await u.message.reply_text(COOKIE_SMS)


# ============================================================
# FACEBOOK
# ============================================================
@admin_only
async def cmd_fb_check(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /fb_check <cookie>")
        return
    cookie = update.message.text.split(" ", 1)[1].strip()
    info = Facebook().check(cookie)
    if info:
        await update.message.reply_text(
            f"✅ Cookie sống\n👤 {info['name']}\n🆔 {info['uid']}")
    else:
        await update.message.reply_text("❌ Cookie chết")


@admin_only
async def cmd_fb_token(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /fb_token <cookie>")
        return
    cookie = update.message.text.split(" ", 1)[1].strip()
    t0 = time.time()
    tok = TOKEN_GRABBER.grab(cookie)
    if not tok:
        await update.message.reply_text("❌ Không lấy token.")
        return
    await update.message.reply_text(
        f"✅ *Token* ({time.time()-t0:.2f}s)\n"
        f"🆔 `{tok.user_id}`\n"
        f"🔑 fb_dtsg `{tok.fb_dtsg[:24]}...`\n"
        f"🔐 access_token `{tok.access_token[:32]}...`\n"
        f"⏳ TTL `{tok.ttl:.0f}s`",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_fb_threads(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /fb_threads <cookie>")
        return
    cookie = update.message.text.split(" ", 1)[1].strip()
    res = Facebook().get_threads(cookie)
    if isinstance(res, dict):
        await update.message.reply_text(f"❌ {res.get('error')}")
        return
    text = f"📦 *{len(res)} box:*\n\n"
    for i, t in enumerate(res[:50], 1):
        text += f"`{i}.` {t['thread_name'][:40]} — `{t['thread_id']}`\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_fb_send(update, ctx):
    text = update.message.text.replace("/fb_send ", "", 1)
    p = text.split("|")
    if len(p) < 3:
        await update.message.reply_text("Cú pháp: /fb_send <cookie>|<box>|<msg>")
        return
    r = Facebook().send(p[0].strip(), p[1].strip(), "|".join(p[2:]).strip())
    await update.message.reply_text(
        f"{'✅' if r and r.status_code == 200 else '❌'}")


@admin_only
async def cmd_fb_spam(update, ctx):
    text = update.message.text.replace("/fb_spam ", "", 1)
    p = text.split("|")
    if len(p) < 4:
        await update.message.reply_text(
            "Cú pháp: /fb_spam <cookie>|<box1,box2>|<msg1;msg2>|<delay>")
        return
    cookie = p[0].strip()
    boxes = [x.strip() for x in p[1].split(",") if x.strip()]
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = float(p[3].strip())
    task = Task(new_tid("fb_spam"), "fb_spam", update.effective_user.id)
    fb = Facebook()

    def w():
        fb.spam_loop(cookie, boxes, msgs, delay, task.stop,
                     on_log=lambda m: print(f"[{task.id}] {m}"))

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await update.message.reply_text(
        f"✅ Task `{task.id}` | {len(boxes)} box | delay {max(3.0, delay)}s",
        parse_mode=ParseMode.MARKDOWN)


# ============================================================
# FB EDIT
# ============================================================
@admin_only
async def cmd_fb_bio(u, c):
    t = u.message.text.replace("/fb_bio ", "", 1)
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /fb_bio <cookie>|<text>")
        return
    ck, bio = t.split("|", 1)
    r = FBEdit().set_bio(ck.strip(), bio.strip())
    await u.message.reply_text(f"{'✅' if r else '❌'}")


@admin_only
async def cmd_fb_name(u, c):
    t = u.message.text.replace("/fb_name ", "", 1)
    p = t.split("|")
    if len(p) < 5:
        await u.message.reply_text(
            "Cú pháp: /fb_name <cookie>|<first>|<middle>|<last>|<pass>")
        return
    r = FBEdit().set_name(p[0].strip(), p[1].strip(), p[2].strip(),
                          p[3].strip(), p[4].strip())
    await u.message.reply_text(f"{'✅' if r else '❌'}")


@admin_only
async def cmd_fb_avatar(u, c):
    t = u.message.text.replace("/fb_avatar ", "", 1)
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /fb_avatar <cookie>|<img_url>")
        return
    ck, url = t.split("|", 1)
    r = FBEdit().set_avatar(ck.strip(), image_url=url.strip())
    await u.message.reply_text(f"{'✅' if r else '❌'}")


@admin_only
async def cmd_fb_cover(u, c):
    t = u.message.text.replace("/fb_cover ", "", 1)
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /fb_cover <cookie>|<img_url>")
        return
    ck, url = t.split("|", 1)
    r = FBEdit().set_cover(ck.strip(), image_url=url.strip())
    await u.message.reply_text(f"{'✅' if r else '❌'}")


@admin_only
async def cmd_fb_story(u, c):
    t = u.message.text.replace("/fb_story ", "", 1)
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /fb_story <cookie>|<text>")
        return
    ck, s = t.split("|", 1)
    r = FBEdit().set_story(ck.strip(), text=s.strip())
    await u.message.reply_text(f"{'✅' if r else '❌'}")


@admin_only
async def cmd_fb_theme(u, c):
    t = u.message.text.replace("/fb_theme ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "Cú pháp: /fb_theme <cookie>|<thread>|<theme_id>")
        return
    r = FBEdit().set_theme(p[0].strip(), p[1].strip(), p[2].strip())
    await u.message.reply_text(f"{'✅' if r else '❌'}")


@admin_only
async def cmd_fb_emoji(u, c):
    t = u.message.text.replace("/fb_emoji ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "Cú pháp: /fb_emoji <cookie>|<thread>|<emoji>")
        return
    r = FBEdit().set_emoji(p[0].strip(), p[1].strip(), p[2].strip())
    await u.message.reply_text(f"{'✅' if r else '❌'}")


@admin_only
async def cmd_fb_nick(u, c):
    t = u.message.text.replace("/fb_nick ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /fb_nick <cookie>|<thread>|<user>|<nick>")
        return
    r = FBEdit().set_nickname(p[0].strip(), p[1].strip(),
                              p[2].strip(), p[3].strip())
    await u.message.reply_text(f"{'✅' if r else '❌'}")


@admin_only
async def cmd_fb_auto_bio(u, c):
    t = u.message.text.replace("/fb_auto_bio ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "Cú pháp: /fb_auto_bio <cookie>|<bio1;bio2>|<delay>")
        return
    ck = p[0].strip()
    bios = [x.strip() for x in p[1].split(";") if x.strip()]
    delay = float(p[2].strip())
    task = Task(new_tid("fb_auto_bio"), "fb_auto_bio", u.effective_user.id)
    a = FBAutoEdit()
    task.thread = threading.Thread(
        target=lambda: a.auto_bio(ck, bios, delay, task.stop,
                                  on_log=lambda m: print(f"[{task.id}] {m}")),
        daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_fb_auto_avatar(u, c):
    t = u.message.text.replace("/fb_auto_avatar ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "Cú pháp: /fb_auto_avatar <cookie>|<url1;url2>|<delay>")
        return
    ck = p[0].strip()
    urls = [x.strip() for x in p[1].split(";") if x.strip()]
    delay = float(p[2].strip())
    task = Task(new_tid("fb_auto_avatar"), "fb_auto_avatar", u.effective_user.id)
    a = FBAutoEdit()
    task.thread = threading.Thread(
        target=lambda: a.auto_avatar(ck, urls, delay, task.stop,
                                     on_log=lambda m: print(f"[{task.id}] {m}")),
        daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_fb_auto_cover(u, c):
    t = u.message.text.replace("/fb_auto_cover ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "Cú pháp: /fb_auto_cover <cookie>|<url1;url2>|<delay>")
        return
    ck = p[0].strip()
    urls = [x.strip() for x in p[1].split(";") if x.strip()]
    delay = float(p[2].strip())
    task = Task(new_tid("fb_auto_cover"), "fb_auto_cover", u.effective_user.id)
    a = FBAutoEdit()
    task.thread = threading.Thread(
        target=lambda: a.auto_cover(ck, urls, delay, task.stop,
                                    on_log=lambda m: print(f"[{task.id}] {m}")),
        daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_fb_auto_story(u, c):
    t = u.message.text.replace("/fb_auto_story ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "Cú pháp: /fb_auto_story <cookie>|<txt1;txt2>|<delay>")
        return
    ck = p[0].strip()
    texts = [x.strip() for x in p[1].split(";") if x.strip()]
    delay = float(p[2].strip())
    task = Task(new_tid("fb_auto_story"), "fb_auto_story", u.effective_user.id)
    a = FBAutoEdit()
    task.thread = threading.Thread(
        target=lambda: a.auto_story(ck, texts, delay, task.stop,
                                    on_log=lambda m: print(f"[{task.id}] {m}")),
        daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


# ============================================================
# ZALO
# ============================================================
@admin_only
async def cmd_zalo_qr(update, ctx):
    qr = ZaloQRLogin()
    info = qr.create_qr()
    await update.message.reply_photo(
        photo=info["qr_image"],
        caption=f"📷 Quét QR bằng app Zalo.\n⏱ Hết hạn: *{QR_TTL}s*",
        parse_mode=ParseMode.MARKDOWN,
    )
    result_box = {}
    threading.Thread(
        target=lambda: result_box.update({"r": qr.poll_login(info["qr_id"])}),
        daemon=True
    ).start()
    for _ in range(QR_TTL):
        await asyncio.sleep(1)
        if "r" in result_box:
            break
    res = result_box.get("r")
    if not res or "error" in res:
        await update.message.reply_text(
            f"❌ {res.get('error') if res else 'Timeout'}")
        return
    imei = res.get("imei") or gen_imei()
    cookies = res.get("cookies", {})
    payload = {"imei": imei, "cookies": cookies}
    with open(os.path.join(DATA_DIR, f"zalo_{update.effective_user.id}.json"), "w") as f:
        json.dump(payload, f, ensure_ascii=False)
    # Gửi cookie KHÔNG dùng ``` để tránh lỗi markdown
    cookie_str = json.dumps(cookies, indent=2)
    await update.message.reply_text(
        f"✅ Đăng nhập Zalo!\n*IMEI:* `{imei}`\n\n*Cookie:*\n{cookie_str}",
    )


@admin_only
async def cmd_zalo_check(u, c):
    t = u.message.text.replace("/zalo_check ", "", 1)
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /zalo_check <imei>|<cookie_json>")
        return
    imei, ck = t.split("|", 1)
    try:
        z = Zalo(imei.strip(), json.loads(ck))
        await u.message.reply_text(f"✅ Zalo OK! UID: {z.uid}")
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_zalo_groups(u, c):
    t = u.message.text.replace("/zalo_groups ", "", 1)
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /zalo_groups <imei>|<cookie_json>")
        return
    imei, ck = t.split("|", 1)
    try:
        z = Zalo(imei.strip(), json.loads(ck))
        gs = z.groups()
        msg = f"📦 *{len(gs)} nhóm:*\n\n"
        for i, g in enumerate(gs[:60], 1):
            msg += f"`{i}.` {g['name'][:40]} — `{g['id']}`\n"
        await u.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_zalo_spam(u, c):
    t = u.message.text.replace("/zalo_spam ", "", 1)
    p = t.split("|")
    if len(p) < 5:
        await u.message.reply_text(
            "Cú pháp: /zalo_spam <imei>|<cookie>|<gid1,gid2>|<msg1;msg2>|<delay>\n"
            "Auto đổi màu chữ mỗi dòng, min 3s.")
        return
    imei = p[0].strip()
    cookies = json.loads(p[1].strip())
    targets = [x.strip() for x in p[2].split(",") if x.strip()]
    msgs = [x.strip() for x in p[3].split(";") if x.strip()]
    delay = float(p[4].strip())
    task = Task(new_tid("zalo_spam"), "zalo_spam", u.effective_user.id)

    def w():
        try:
            z = Zalo(imei, cookies)
            z.spam_loop_colored(targets, msgs, delay, True, task.stop,
                                on_log=lambda m: print(f"[{task.id}] {m}"))
        except Exception as e:
            print(f"[zalo_spam] {e}")

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(
        f"✅ Task `{task.id}` | Auto màu mỗi dòng | Delay min 3s",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_zalo_color_list(u, c):
    text = "*🎨 Bảng màu Zalo:*\n\n"
    for i, col in enumerate(ZTC, 1):
        text += f"`{i}.` {col['name']} — `{col['code']}`\n"
    text += "\n*Màu name:* `" + "` `".join(ZALO_NAME_COLORS) + "`\n\n"
    text += "*Themes:*\n"
    for t in ZALO_THEMES:
        text += f"• `{t['id']}` — {t['name']}\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_zalo_color(u, c):
    t = u.message.text.replace("/zalo_color ", "", 1)
    p = t.split("|")
    if len(p) < 5:
        await u.message.reply_text(
            "Cú pháp: /zalo_color <imei>|<cookie>|<gid>|<msg1;msg2>|<delay>")
        return
    try:
        z = Zalo(p[0].strip(), json.loads(p[1].strip()))
        th = ZaloTheme(z)
        gid = p[2].strip()
        msgs = [x.strip() for x in p[3].split(";") if x.strip()]
        delay = float(p[4].strip())
        task = Task(new_tid("zalo_color"), "zalo_color", u.effective_user.id)

        def w():
            th.auto_color_loop(gid, msgs, delay, task.stop, True,
                               on_log=lambda m: print(f"[{task.id}] {m}"))

        task.thread = threading.Thread(target=w, daemon=True)
        TASKS.add(task)
        task.thread.start()
        await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_zalo_namecolor(u, c):
    t = u.message.text.replace("/zalo_namecolor ", "", 1)
    p = t.split("|")
    if len(p) < 5:
        await u.message.reply_text(
            "Cú pháp: /zalo_namecolor <imei>|<cookie>|<gid>|<user>|<color>")
        return
    try:
        z = Zalo(p[0].strip(), json.loads(p[1].strip()))
        r = ZaloTheme(z).set_name_color(p[2].strip(), p[3].strip(), p[4].strip())
        await u.message.reply_text(f"{'✅' if r else '❌'}")
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_zalo_theme(u, c):
    t = u.message.text.replace("/zalo_theme ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /zalo_theme <imei>|<cookie>|<gid>|<theme_id>")
        return
    try:
        z = Zalo(p[0].strip(), json.loads(p[1].strip()))
        r = ZaloTheme(z).set_theme(p[2].strip(), p[3].strip())
        await u.message.reply_text(f"{'✅' if r else '❌'}")
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


@admin_only
async def cmd_zalo_auto_theme(u, c):
    t = u.message.text.replace("/zalo_auto_theme ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /zalo_auto_theme <imei>|<cookie>|<gid>|<delay>")
        return
    try:
        z = Zalo(p[0].strip(), json.loads(p[1].strip()))
        th = ZaloTheme(z)
        gid = p[2].strip()
        delay = float(p[3].strip())
        task = Task(new_tid("zalo_auto_theme"), "zalo_auto_theme", u.effective_user.id)

        def w():
            th.auto_theme_loop(gid, delay, task.stop,
                               on_log=lambda m: print(f"[{task.id}] {m}"))

        task.thread = threading.Thread(target=w, daemon=True)
        TASKS.add(task)
        task.thread.start()
        await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await u.message.reply_text(f"❌ {e}")


# ============================================================
# DISCORD / TELEGRAM / GMAIL / SMS / IG / WECHAT
# ============================================================
@admin_only
async def cmd_discord_spam(u, c):
    t = u.message.text.replace("/discord_spam ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /discord_spam <token>|<channel>|<msg1;msg2>|<delay>")
        return
    token, ch = p[0].strip(), p[1].strip()
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(3.0, float(p[3].strip()))
    task = Task(new_tid("discord"), "discord", u.effective_user.id)

    def w():
        i = 0
        while not task.stop.is_set():
            m = msgs[i % len(msgs)]
            i += 1
            FW["discord"].post(
                f"https://discord.com/api/v10/channels/{ch}/messages",
                json={"content": m},
                headers={"Authorization": token,
                         "Content-Type": "application/json"})
            time.sleep(delay * random.uniform(0.85, 1.25))
            FW["discord"].behavior.maybe_break()

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_tele_spam(u, c):
    t = u.message.text.replace("/tele_spam ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /tele_spam <token>|<chat>|<msg1;msg2>|<delay>")
        return
    token, ch = p[0].strip(), p[1].strip()
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(3.0, float(p[3].strip()))
    task = Task(new_tid("tele"), "telegram", u.effective_user.id)

    def w():
        i = 0
        while not task.stop.is_set():
            m = msgs[i % len(msgs)]
            i += 1
            try:
                FW["telegram"].post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data={"chat_id": ch, "text": m})
            except Exception:
                pass
            time.sleep(delay)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_gmail_spam(u, c):
    t = u.message.text.replace("/gmail_spam ", "", 1)
    p = t.split("|")
    if len(p) < 5:
        await u.message.reply_text(
            "Cú pháp: /gmail_spam <email>|<pass>|<to>|<msg1;msg2>|<delay>")
        return
    # Import ở đầu hàm để tránh lỗi syntax
    import smtplib
    import ssl as _ssl
    from email.mime.text import MIMEText

    email_ = p[0].strip()
    pw = p[1].strip()
    to = p[2].strip()
    msgs = [x.strip() for x in p[3].split(";") if x.strip()]
    delay = max(10.0, float(p[4].strip()))

    task = Task(new_tid("gmail"), "gmail", u.effective_user.id)

    def w():
        i = 0
        while not task.stop.is_set():
            m = msgs[i % len(msgs)]
            i += 1
            try:
                ctx = _ssl.create_default_context()
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
                    s.login(email_, pw)
                    msg = MIMEText(m)
                    msg["From"] = email_
                    msg["To"] = to
                    msg["Subject"] = " "
                    s.sendmail(email_, to, msg.as_string())
            except Exception as e:
                print(f"[gmail] {e}")
            time.sleep(delay)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_sms_spam(u, c):
    if not c.args:
        await u.message.reply_text("Cú pháp: /sms_spam <phone>")
        return
    phone = c.args[0].strip()
    try:
        from spm import run as run_sms
    except ImportError:
        await u.message.reply_text(
            "❌ Thiếu spm.py — tải file OTP từ nguồn của bạn và đặt vào thư mục.")
        return
    task = Task(new_tid("sms"), "sms", u.effective_user.id)

    def w():
        i = 1
        while not task.stop.is_set():
            try:
                run_sms(phone, i)
                i += 1
            except Exception as e:
                print(f"[sms] {e}")

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_ig_spam(u, c):
    t = u.message.text.replace("/ig_spam ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /ig_spam <sessionid>|<threads>|<msgs>|<delay>")
        return
    sid = p[0].strip()
    tids = [x.strip() for x in p[1].split(",") if x.strip()]
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    delay = max(8.0, float(p[3].strip()))
    task = Task(new_tid("ig"), "ig", u.effective_user.id)

    def w():
        i = 0
        while not task.stop.is_set():
            for tid in tids:
                if task.stop.is_set():
                    return
                m = msgs[i % len(msgs)]
                i += 1
                try:
                    FW["ig"].post(
                        "https://i.instagram.com/api/v1/direct_v2/threads/broadcast/text/",
                        data={"text": m,
                              "thread_ids": f"[{tid}]",
                              "action": "send_item"},
                        headers={"Cookie": f"sessionid={sid}",
                                 "X-IG-App-ID": "1217981644879628",
                                 "Content-Type": "application/x-www-form-urlencoded"})
                except Exception:
                    pass
                time.sleep(delay)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_wechat_spam(u, c):
    t = u.message.text.replace("/wechat_spam ", "", 1)
    p = t.split("|")
    if len(p) < 6:
        await u.message.reply_text(
            "Cú pháp: /wechat_spam <corpid>|<secret>|<agent>|<user>|<msgs>|<delay>")
        return
    import requests as rq
    corpid = p[0].strip()
    secret = p[1].strip()
    agent = p[2].strip()
    user = p[3].strip()
    msgs = [x.strip() for x in p[4].split(";") if x.strip()]
    delay = max(4.0, float(p[5].strip()))
    task = Task(new_tid("wechat"), "wechat", u.effective_user.id)

    def w():
        token = ""
        i = 0
        last_refresh = 0
        while not task.stop.is_set():
            if time.time() - last_refresh > 7000 or not token:
                try:
                    token = rq.get(
                        f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
                        f"?corpid={corpid}&corpsecret={secret}"
                    ).json().get("access_token", "")
                    last_refresh = time.time()
                except Exception:
                    pass
            m = msgs[i % len(msgs)]
            i += 1
            try:
                rq.post(
                    f"https://qyapi.weixin.qq.com/cgi-bin/message/send"
                    f"?access_token={token}",
                    json={"touser": user, "msgtype": "text",
                          "agentid": agent, "text": {"content": m}, "safe": 0})
            except Exception:
                pass
            time.sleep(delay)

    task.thread = threading.Thread(target=w, daemon=True)
    TASKS.add(task)
    task.thread.start()
    await u.message.reply_text(f"✅ Task `{task.id}`", parse_mode=ParseMode.MARKDOWN)


# ============================================================
# COOKIE STORAGE
# ============================================================
@admin_only
async def cmd_save_fb(u, c):
    ck = u.message.text.replace("/save_fb ", "", 1).strip()
    uid = str(u.effective_user.id)
    d = COOKIES.get(uid, {})
    lst = d.get("fb", [])
    lst.append(ck)
    d["fb"] = lst
    COOKIES.set(uid, d)
    GUARD3.backup(ck, "fb")
    stop = threading.Event()
    GUARD3.start_warm_loop(ck, "fb", interval=1800, stop_event=stop)
    await u.message.reply_text(
        f"✅ Đã lưu FB + bật warm. Tổng: `{len(lst)}`",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_save_zalo(u, c):
    t = u.message.text.replace("/save_zalo ", "", 1).strip()
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /save_zalo <imei>|<cookie_json>")
        return
    imei, ck = t.split("|", 1)
    uid = str(u.effective_user.id)
    d = COOKIES.get(uid, {})
    lst = d.get("zalo", [])
    lst.append({"imei": imei.strip(), "cookies": json.loads(ck.strip())})
    d["zalo"] = lst
    COOKIES.set(uid, d)
    await u.message.reply_text(
        f"✅ Đã lưu Zalo. Tổng: `{len(lst)}`",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_list_ck(u, c):
    uid = str(u.effective_user.id)
    d = COOKIES.get(uid, {})
    fb = d.get("fb", [])
    z = d.get("zalo", [])
    if not fb and not z:
        await u.message.reply_text("📭 Chưa có cookie.")
        return
    text = "*📂 Cookie đã lưu:*\n\n"
    if fb:
        text += "*Facebook:*\n"
        for i, x in enumerate(fb, 1):
            text += f"`{i}.` `{x[:40]}...`\n"
    if z:
        text += "\n*Zalo:*\n"
        for i, x in enumerate(z, 1):
            text += f"`{i}.` imei=`{x['imei']}`\n"
    text += "\n`/del_ck <fb|zalo> <index>`"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_del_ck(u, c):
    if len(c.args) < 2:
        await u.message.reply_text("Cú pháp: /del_ck <fb|zalo> <index>")
        return
    kind, idx = c.args[0].lower(), int(c.args[1]) - 1
    uid = str(u.effective_user.id)
    d = COOKIES.get(uid, {})
    lst = d.get(kind, [])
    if 0 <= idx < len(lst):
        lst.pop(idx)
        d[kind] = lst
        COOKIES.set(uid, d)
        await u.message.reply_text("✅ Đã xóa.")
    else:
        await u.message.reply_text("❌ Index không hợp lệ.")


@admin_only
async def cmd_warm_ck(u, c):
    uid = str(u.effective_user.id)
    d = COOKIES.get(uid, {})
    fb = d.get("fb", [])
    if not fb:
        await u.message.reply_text("❌ Không có FB cookie.")
        return
    for ck in fb:
        threading.Thread(target=GUARD3.warm_fb, args=(ck,), daemon=True).start()
    await u.message.reply_text(
        f"🔥 Đang warm `{len(fb)}` cookie FB...",
        parse_mode=ParseMode.MARKDOWN)


# ============================================================
# COOL FEATURES
# ============================================================
@admin_only
async def cmd_nick(u, c):
    await u.message.reply_text(
        f"🎭 Nick: `{cool_features.random_nick()}`",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_uid_extract(u, c):
    t = u.message.text.replace("/uid_extract ", "", 1)
    uids = cool_features.extract_uids_from_text(t)
    if not uids:
        await u.message.reply_text("❌ Không tìm thấy UID.")
        return
    text = f"🔍 Tìm thấy `{len(uids)}` UID:\n\n"
    for x in uids[:30]:
        text += f"`{x}`\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_ip_info(u, c):
    info = cool_features.ip_info()
    # Không dùng ``` để tránh lỗi markdown
    await u.message.reply_text(
        json.dumps(info, indent=2, ensure_ascii=False))


@admin_only
async def cmd_zombie(u, c):
    t = u.message.text.replace("/zombie ", "", 1)
    p = t.split("|")
    if len(p) < 3:
        await u.message.reply_text(
            "Cú pháp: /zombie <cookie>|<box>|<msg1;msg2>")
        return
    ck, box = p[0].strip(), p[1].strip()
    msgs = [x.strip() for x in p[2].split(";") if x.strip()]
    task = Task(new_tid("zombie"), "zombie", u.effective_user.id)
    fb = Facebook()

    def send_fn(t, m):
        fb.send(ck, t, m)

    z = cool_features.ZombieSpam(send_fn, [box], msgs,
                                 min_delay=300, max_delay=900)
    task.stop = z.stop
    z.start()
    TASKS.add(task)
    await u.message.reply_text(
        f"✅ Zombie `{task.id}` (5-15 phút / lần)",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_bomb(u, c):
    t = u.message.text.replace("/bomb ", "", 1)
    p = t.split("|")
    if len(p) < 4:
        await u.message.reply_text(
            "Cú pháp: /bomb <cookie>|<box>|<msg>|<delay_s>")
        return
    ck, box, msg, delay = p[0].strip(), p[1].strip(), p[2].strip(), float(p[3].strip())
    fb = Facebook()
    cool_features.schedule_send(lambda t_, m_: fb.send(ck, t_, m_),
                                box, msg, delay)
    await u.message.reply_text(
        f"⏰ Sẽ gửi sau `{delay}s`.", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_backup_all(u, c):
    res = cool_features.auto_backup_all()
    await u.message.reply_text(
        f"✅ Backup xong: `{json.dumps(res)}`",
        parse_mode=ParseMode.MARKDOWN)


# ============================================================
# TASKS
# ============================================================
@admin_only
async def cmd_tasks(u, c):
    tasks = TASKS.by_owner(u.effective_user.id)
    if not tasks:
        await u.message.reply_text("📭 Không có task.")
        return
    text = "*📋 Tasks:*\n\n"
    for i, t in enumerate(tasks, 1):
        text += f"`{i}.` [{t.type}] {t.uptime()}\n"
    text += "\n`/stop <n>` `/stop_all`"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_stop(u, c):
    if not c.args or not c.args[0].isdigit():
        await u.message.reply_text("Cú pháp: /stop <n>")
        return
    i = int(c.args[0]) - 1
    tasks = TASKS.by_owner(u.effective_user.id)
    if 0 <= i < len(tasks):
        TASKS.remove(tasks[i].id)
        await u.message.reply_text("✅ Đã dừng.")
    else:
        await u.message.reply_text("❌ Số không hợp lệ.")


@admin_only
async def cmd_stop_all(u, c):
    tasks = TASKS.by_owner(u.effective_user.id)
    for t in tasks:
        TASKS.remove(t.id)
    await u.message.reply_text(
        f"✅ Đã dừng `{len(tasks)}` task.", parse_mode=ParseMode.MARKDOWN)


# ============================================================
# RED TEAM
# ============================================================
@admin_only
async def cmd_rt_worm(u, c):
    if not c.args:
        await u.message.reply_text("Cú pháp: /rt_worm <host1,host2>")
        return
    hosts = [x.strip() for x in c.args[0].split(",")]
    w = redteam.WormSim(hosts)
    out = w.scan() + w.propagate("payload.bin")
    await u.message.reply_text("🧪 *Worm Sim:*\n" + "\n".join(out))


@admin_only
async def cmd_rt_dropper(u, c):
    name = c.args[0] if c.args else "stage1.bin"
    d = redteam.DropperSim()
    p = d.stage(name, redteam.build_marker(name))
    await u.message.reply_text(f"🧪 Saved: `{p}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_rt_c2(u, c):
    t = u.message.text.replace("/rt_c2 ", "", 1)
    if "|" not in t:
        await u.message.reply_text("Cú pháp: /rt_c2 <id>|<json>")
        return
    i, d = t.split("|", 1)
    try:
        data = json.loads(d)
    except Exception:
        data = {"raw": d}
    redteam.C2Sim().beacon(i.strip(), data)
    await u.message.reply_text(
        f"🧪 Beacon logged: `{i.strip()}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_rt_keylog(u, c):
    t = " ".join(c.args) if c.args else ""
    k = redteam.KeyloggerSim()
    k.feed(t)
    await u.message.reply_text(
        f"🧪 Keylog: `{k.dump()}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_rt_ransom(u, c):
    files = [x for x in c.args if os.path.isfile(x)]
    r = redteam.RansomSim().encrypt_demo(files)
    await u.message.reply_text(
        f"🧪 Note: `{r['note']}` Files: `{len(r['files'])}`",
        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_rt_phish(u, c):
    t = c.args[0] if c.args else "fb"
    p = redteam.gen_phish(t)
    await u.message.reply_text(
        f"🧪 Phish: `{p}`", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_rt_exploit(u, c):
    if not c.args:
        await u.message.reply_text("Cú pháp: /rt_exploit <url>")
        return
    res = redteam.ExploitSim().scan_web(c.args[0])
    text = "🧪 *Exploit Sim:*\n\n"
    for r in res:
        text += f"• {r['vuln']} — {r['url']}\n"
    await u.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ============================================================
# POST INIT
# ============================================================
async def post_init(app):
    print("[POST_INIT] Bắt đầu setup...")
    try:
        cmds = [
            ("start", "Menu chính"),
            ("fw_status", "Firewall 7 lớp"),
            ("fw_reset", "Reset firewall"),
            ("fw_antiban", "Anti-ban cookie"),
            ("fw_risk", "Risk score"),
            ("rate", "Rate config"),
            ("rate_set", "Chỉnh rate"),
            ("rate_reset", "Reset rate"),
            ("rate_clear", "Clear manual"),
            ("guard_status", "Guard health"),
            ("guard_backup", "Backup all cookie"),
            ("guard_warm", "Warm cookie"),
            ("guard_safe", "Cookie safe check"),
            ("cookie_fb", "Guide FB"),
            ("cookie_zalo", "Guide Zalo"),
            ("cookie_discord", "Guide Discord"),
            ("cookie_telegram", "Guide Telegram"),
            ("cookie_gmail", "Guide Gmail"),
            ("cookie_ig", "Guide IG"),
            ("cookie_wechat", "Guide WeChat"),
            ("cookie_sms", "Guide SMS"),
            ("fb_check", "Check FB"),
            ("fb_token", "Token FB"),
            ("fb_threads", "Box FB"),
            ("fb_send", "Send FB"),
            ("fb_spam", "Spam FB"),
            ("fb_bio", "Bio"),
            ("fb_name", "Name"),
            ("fb_avatar", "Avatar"),
            ("fb_cover", "Cover"),
            ("fb_story", "Story"),
            ("fb_theme", "Theme FB"),
            ("fb_emoji", "Emoji FB"),
            ("fb_nick", "Nick FB"),
            ("fb_auto_bio", "Auto bio"),
            ("fb_auto_avatar", "Auto avatar"),
            ("fb_auto_cover", "Auto cover"),
            ("fb_auto_story", "Auto story"),
            ("zalo_qr", "QR login Zalo"),
            ("zalo_check", "Check Zalo"),
            ("zalo_groups", "Groups Zalo"),
            ("zalo_spam", "Spam Zalo auto màu"),
            ("zalo_color_list", "Bảng màu Zalo"),
            ("zalo_color", "Spam màu Zalo"),
            ("zalo_namecolor", "Màu tên Zalo"),
            ("zalo_theme", "Theme Zalo"),
            ("zalo_auto_theme", "Auto theme Zalo"),
            ("discord_spam", "Spam Discord"),
            ("tele_spam", "Spam Telegram"),
            ("gmail_spam", "Spam Gmail"),
            ("sms_spam", "Spam SMS"),
            ("ig_spam", "Spam IG"),
            ("wechat_spam", "Spam WeChat"),
            ("save_fb", "Lưu FB"),
            ("save_zalo", "Lưu Zalo"),
            ("list_ck", "List cookie"),
            ("del_ck", "Xóa cookie"),
            ("warm_ck", "Warm cookie"),
            ("nick", "Random nick"),
            ("uid_extract", "Trích UID"),
            ("ip_info", "Info IP"),
            ("zombie", "Zombie spam"),
            ("bomb", "Time bomb"),
            ("backup_all", "Backup tất cả"),
            ("tasks", "Tasks"),
            ("stop", "Dừng task"),
            ("stop_all", "Dừng hết"),
            ("rt_worm", "Worm sim"),
            ("rt_dropper", "Dropper"),
            ("rt_c2", "C2"),
            ("rt_keylog", "Keylog"),
            ("rt_ransom", "Ransom"),
            ("rt_phish", "Phish"),
            ("rt_exploit", "Exploit sim"),
        ]
        await app.bot.set_my_commands([BotCommand(n, d) for n, d in cmds])
        print("[POST_INIT] Commands set OK")
    except Exception as e:
        print(f"[POST_INIT] Lỗi commands: {e}")

    try:
        for uid, d in COOKIES.all().items():
            for ck in d.get("fb", []):
                stop = threading.Event()
                GUARD3.start_warm_loop(ck, "fb", interval=1800, stop_event=stop)
        print("[POST_INIT] Warm loops OK")
    except Exception as e:
        print(f"[POST_INIT] Lỗi warm: {e}")

    print("[BOT] Ready. Bot by Anh Khôi.")


# ============================================================
# MAIN
# ============================================================
def main():
    # ---------- Fix event loop ----------
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # ---------- Start HTTP server để Render không kill ----------
    threading.Thread(target=_start_health_server, daemon=True).start()
    time.sleep(0.5)

    # ---------- Xóa webhook lần 1 ----------
    try:
        import requests as _r
        resp = _r.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": "true"},
            timeout=10
        )
        print(f"[MAIN] deleteWebhook: {resp.status_code} - {resp.text[:120]}")
    except Exception as e:
        print(f"[MAIN] Không xóa được webhook: {e}")

    # ---------- Verify token ----------
    try:
        import requests as _r
        resp = _r.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getMe",
            timeout=10
        )
        data = resp.json()
        if data.get("ok"):
            bot_info = data["result"]
            print(f"[MAIN] ✅ Bot OK: @{bot_info.get('username')} (ID: {bot_info.get('id')})")
        else:
            print(f"[MAIN] ❌ Token lỗi: {data}")
            return
    except Exception as e:
        print(f"[MAIN] ❌ Không verify token: {e}")
        return

    # ---------- Xóa webhook lần 2 ----------
    try:
        import requests as _r
        time.sleep(2)
        resp = _r.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": "true"},
            timeout=10
        )
        print(f"[MAIN] deleteWebhook lần 2: {resp.status_code}")
    except Exception as e:
        print(f"[MAIN] Không xóa được webhook lần 2: {e}")

    # ---------- Build app ----------
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # ---------- Handlers ----------
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(cb_menu))

    app.add_handler(CommandHandler("fw_status", cmd_fw_status))
    app.add_handler(CommandHandler("fw_reset", cmd_fw_reset))
    app.add_handler(CommandHandler("fw_antiban", cmd_fw_antiban))
    app.add_handler(CommandHandler("fw_risk", cmd_fw_risk))

    app.add_handler(CommandHandler("rate", cmd_rate))
    app.add_handler(CommandHandler("rate_set", cmd_rate_set))
    app.add_handler(CommandHandler("rate_reset", cmd_rate_reset))
    app.add_handler(CommandHandler("rate_clear", cmd_rate_clear))

    app.add_handler(CommandHandler("guard_status", cmd_guard_status))
    app.add_handler(CommandHandler("guard_backup", cmd_guard_backup))
    app.add_handler(CommandHandler("guard_warm", cmd_guard_warm))
    app.add_handler(CommandHandler("guard_safe", cmd_guard_safe))

    app.add_handler(CommandHandler("cookie_fb", cmd_cookie_fb))
    app.add_handler(CommandHandler("cookie_zalo", cmd_cookie_zalo))
    app.add_handler(CommandHandler("cookie_discord", cmd_cookie_discord))
    app.add_handler(CommandHandler("cookie_telegram", cmd_cookie_telegram))
    app.add_handler(CommandHandler("cookie_gmail", cmd_cookie_gmail))
    app.add_handler(CommandHandler("cookie_ig", cmd_cookie_ig))
    app.add_handler(CommandHandler("cookie_wechat", cmd_cookie_wechat))
    app.add_handler(CommandHandler("cookie_sms", cmd_cookie_sms))

    app.add_handler(CommandHandler("fb_check", cmd_fb_check))
    app.add_handler(CommandHandler("fb_token", cmd_fb_token))
    app.add_handler(CommandHandler("fb_threads", cmd_fb_threads))
    app.add_handler(CommandHandler("fb_send", cmd_fb_send))
    app.add_handler(CommandHandler("fb_spam", cmd_fb_spam))
    app.add_handler(CommandHandler("fb_bio", cmd_fb_bio))
    app.add_handler(CommandHandler("fb_name", cmd_fb_name))
    app.add_handler(CommandHandler("fb_avatar", cmd_fb_avatar))
    app.add_handler(CommandHandler("fb_cover", cmd_fb_cover))
    app.add_handler(CommandHandler("fb_story", cmd_fb_story))
    app.add_handler(CommandHandler("fb_theme", cmd_fb_theme))
    app.add_handler(CommandHandler("fb_emoji", cmd_fb_emoji))
    app.add_handler(CommandHandler("fb_nick", cmd_fb_nick))
    app.add_handler(CommandHandler("fb_auto_bio", cmd_fb_auto_bio))
    app.add_handler(CommandHandler("fb_auto_avatar", cmd_fb_auto_avatar))
    app.add_handler(CommandHandler("fb_auto_cover", cmd_fb_auto_cover))
    app.add_handler(CommandHandler("fb_auto_story", cmd_fb_auto_story))

    app.add_handler(CommandHandler("zalo_qr", cmd_zalo_qr))
    app.add_handler(CommandHandler("zalo_check", cmd_zalo_check))
    app.add_handler(CommandHandler("zalo_groups", cmd_zalo_groups))
    app.add_handler(CommandHandler("zalo_spam", cmd_zalo_spam))
    app.add_handler(CommandHandler("zalo_color_list", cmd_zalo_color_list))
    app.add_handler(CommandHandler("zalo_color", cmd_zalo_color))
    app.add_handler(CommandHandler("zalo_namecolor", cmd_zalo_namecolor))
    app.add_handler(CommandHandler("zalo_theme", cmd_zalo_theme))
    app.add_handler(CommandHandler("zalo_auto_theme", cmd_zalo_auto_theme))

    app.add_handler(CommandHandler("discord_spam", cmd_discord_spam))
    app.add_handler(CommandHandler("tele_spam", cmd_tele_spam))
    app.add_handler(CommandHandler("gmail_spam", cmd_gmail_spam))
    app.add_handler(CommandHandler("sms_spam", cmd_sms_spam))
    app.add_handler(CommandHandler("ig_spam", cmd_ig_spam))
    app.add_handler(CommandHandler("wechat_spam", cmd_wechat_spam))

    app.add_handler(CommandHandler("save_fb", cmd_save_fb))
    app.add_handler(CommandHandler("save_zalo", cmd_save_zalo))
    app.add_handler(CommandHandler("list_ck", cmd_list_ck))
    app.add_handler(CommandHandler("del_ck", cmd_del_ck))
    app.add_handler(CommandHandler("warm_ck", cmd_warm_ck))

    app.add_handler(CommandHandler("nick", cmd_nick))
    app.add_handler(CommandHandler("uid_extract", cmd_uid_extract))
    app.add_handler(CommandHandler("ip_info", cmd_ip_info))
    app.add_handler(CommandHandler("zombie", cmd_zombie))
    app.add_handler(CommandHandler("bomb", cmd_bomb))
    app.add_handler(CommandHandler("backup_all", cmd_backup_all))

    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("stop_all", cmd_stop_all))

    app.add_handler(CommandHandler("rt_worm", cmd_rt_worm))
    app.add_handler(CommandHandler("rt_dropper", cmd_rt_dropper))
    app.add_handler(CommandHandler("rt_c2", cmd_rt_c2))
    app.add_handler(CommandHandler("rt_keylog", cmd_rt_keylog))
    app.add_handler(CommandHandler("rt_ransom", cmd_rt_ransom))
    app.add_handler(CommandHandler("rt_phish", cmd_rt_phish))
    app.add_handler(CommandHandler("rt_exploit", cmd_rt_exploit))

    print("[ALB] Bot by Anh Khôi — starting v7.2...")
    app.run_polling(
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=30,
    )


if __name__ == "__main__":
    main()
