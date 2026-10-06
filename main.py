# ============ IMPORT ============
from firewall_v6 import FW
from anti_ban_v2 import ANTIBAN
from cookie_guard_v2 import GUARD2
from rate_balancer import get as rate_get, set_ as rate_set, all_ as rate_all, reset as rate_reset, MIN_SAFE_DELAY
from zalo_tools import Zalo, ZALO_TEXT_COLORS
from zalo_theme import ZaloTheme

# ============ MENU UPDATE ============
MENU_TEXT["m_fw"] = (
    "🛡 *FIREWALL v6 — 7 LỚP*\n\n"
    "`/fw_status` — trạng thái\n"
    "`/fw_reset` — reset\n"
    "`/fw_antibан <cookie>` — trạng thái anti-ban cookie\n"
)

MENU_TEXT["m_rate"] = (
    f"⚙ *RATE CONFIG* (min {MIN_SAFE_DELAY}s)\n\n"
    "`/rate` xem\n"
    "`/rate_set <key> <giây>` — chỉnh\n"
    "`/rate_reset`\n"
    "`/rate_clear <key>` — xóa manual\n"
)

MENU_TEXT["m_zalo"] = (
    "📞 *Zalo*\n\n"
    "`/zalo_qr`\n"
    "`/zalo_check <imei>|<cookie>`\n"
    "`/zalo_groups <imei>|<cookie>`\n"
    "`/zalo_spam <imei>|<cookie>|<gid1,gid2>|<msg1;msg2>|<delay>` — auto đổi màu mỗi dòng"
)

# ============ CÁC HANDLER MỚI ============
@admin_only
async def cmd_fw_antiban(update, ctx):
    """Trạng thái anti-ban của 1 cookie."""
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /fw_antiban <cookie>"); return
    cookie = update.message.text.split(" ", 1)[1].strip()
    m = ANTIBAN.register(cookie)
    txt = (
        f"🛡 *Anti-Ban Cookie:*\n"
        f"• OK: `{m.ok_count}`\n"
        f"• Fail: `{m.fail_count}`\n"
        f"• Fail streak: `{m.fail_streak}`\n"
        f"• Disabled: `{m.disabled}`\n"
        f"• Cooldown left: `{ANTIBAN.in_cooldown(cookie):.0f}s`\n"
        f"• Warm count: `{m.warm_count}`\n"
        f"• Needs warmup: `{ANTIBAN.needs_warmup(cookie)}`\n"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)

@admin_only
async def cmd_rate_clear(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Cú pháp: /rate_clear <key>"); return
    from firewall_v6 import FW
    key_map = {"fb": "fb_send", "zalo": "zalo_send"}
    # clear manual nếu có
    rate_key = ctx.args[0]
    rate_set(rate_key, rate_get(rate_key))  # vẫn set giá trị mặc định
    # Tắt manual
    for fw_key, fw in FW.items():
        if rate_key.startswith(fw_key):
            fw.rate.manual = None
    await update.message.reply_text(f"✅ Đã xóa manual cho `{rate_key}`", parse_mode=ParseMode.MARKDOWN)

# ============ UPDATE ZALO SPAM (auto color) ============
@admin_only
async def cmd_zalo_spam(u, c):
    t = u.message.text.replace("/zalo_spam ", "", 1)
    p = t if len(p) < 5:
        await u.message.reply_text(
            "Cú pháp: /zalo_spam <imei>|<cookie>|<gid1,gid2>|<msg1;msg2>|<delay>\n"
            "Mỗi tin gửi đi tự động đổi màu chữ.")
        return
    imei = p[0].strip(); cookies = json.loads(p[1].strip())
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
    TASKS.add(task); task.thread.start()
    await u.message.reply_text(
        f"✅ Task `{task.id}` — Auto đổi màu mỗi dòng | Delay min 3s",
        parse_mode=ParseMode.MARKDOWN)

# ============ AUTO WARM COOKIE KHI START ============
async def post_init(app):
    """Tự động warm tất cả cookie khi bot khởi động."""
    from data_store import COOKIES
    for uid, d in COOKIES.all().items():
        for ck in d.get("fb", []):
            stop = threading.Event()
            GUARD2.start_warm_loop(ck, "fb", interval=1800, stop_event=stop)
    # set commands
    from telegram import BotCommand
    cmds = [
        ("start","Menu chính"),
        ("fw_status","Firewall status"), ("fw_reset","Reset"),
        ("fw_antiban","Anti-ban cookie"), ("rate","Rate config"),
        ("rate_set","Chỉnh rate"), ("rate_reset","Reset rate"),
        ("rate_clear","Clear manual"),
        # ... (giữ các lệnh cũ)
    ]
    await app.bot.set_my_commands([BotCommand(n, d) for n, d in cmds])

# ============ ĐĂNG KÝ HANDLER ============
def register_handlers(app):
    app.add_handler(CommandHandler("fw_antiban", cmd_fw_antiban))
    app.add_handler(CommandHandler("rate_clear", cmd_rate_clear))
    # ... các handler cũ