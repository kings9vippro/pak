# ============================================================
# cookie_guide.py — Hướng dẫn lấy cookie các app
# KHÔNG dùng backtick 3 lần bên trong string để tránh lỗi syntax
# ============================================================

COOKIE_FB = """📘 LẤY COOKIE FACEBOOK

Cần: c_user, xs, datr, fr, sb, presence

Cách 1 — Kiwi Browser (điện thoại):
1. Cài Kiwi Browser + extension Cookie Editor
2. Mở facebook.com → đăng nhập
3. Mở extension → Export → Copy JSON

Cách 2 — HTTP Canary (Android):
1. Cài HTTP Canary → cài cert
2. Bật VPN Canary → mở app FB
3. Bắt request graph.facebook.com
4. Copy header Cookie

Cách 3 — PC:
1. F12 → tab Network → F5
2. Chọn request đầu tiên
3. Request Headers → cookie → copy

Test: /fb_check <cookie>
"""


COOKIE_ZALO = """📞 LẤY COOKIE ZALO

Cách 1 — QR Login (khuyến nghị):
- Dùng lệnh /zalo_qr trong bot
- Bot hiển thị QR (hết hạn 120s)
- Quét bằng app Zalo → bot tự lấy cookie

Cách 2 — Thủ công:
1. Kiwi Browser → chat.zalo.me → login
2. Cookie Editor → Export JSON
3. Cần: zpw_sek, zpw_ver=645, zpw_type=30

IMEI:
- Lấy từ Zalo PC → Settings → About
- Hoặc dùng mặc định: 000000000000000

Định dạng gửi bot:
/zalo_check <imei>|<cookie_json>
"""


COOKIE_DISCORD = """🎮 LẤY TOKEN DISCORD

PC:
1. Mở discord.com → F12 → Console
2. Paste đoạn script lấy token
3. Copy token (dạng MTIz...)

Mobile:
Dùng Kiwi Browser + extension Discord Token Login
"""


COOKIE_TELEGRAM = """📢 LẤY TELEGRAM

Bot token:
1. Chat @BotFather
2. Gõ /newbot
3. Đặt tên → copy token

Chat ID:
1. Chat @userinfobot
2. Bot trả về ID của bạn
"""


COOKIE_GMAIL = """✉ LẤY GMAIL APP PASSWORD

1. Bật 2FA: myaccount.google.com/security
2. Vào myaccount.google.com/apppasswords
3. Chọn Mail → Other → đặt tên Bot
4. Copy 16 ký tự app password

Dùng cho lệnh:
/gmail_spam <email>|<app_pass>|<to>|<msg1;msg2>|<delay>
"""


COOKIE_IG = """📷 LẤY COOKIE INSTAGRAM

Cần: sessionid, csrftoken, ds_user_id

Cách 1 — Kiwi Browser:
1. Kiwi → instagram.com → login
2. Cookie Editor → Export
3. Copy sessionid

Cách 2 — PC:
1. F12 → Application → Cookies
2. Tìm sessionid → copy

Dùng cho lệnh:
/ig_spam <sessionid>|<thread_ids>|<msg1;msg2>|<delay>
"""


COOKIE_WECHAT = """💼 LẤY WECHAT / WECOM

1. Vào work.weixin.qq.com → đăng nhập admin
2. My Business → copy Corp ID
3. Apps → tạo app mới:
   - Lấy AgentId
   - Lấy Secret

Dùng cho lệnh:
/wechat_spam <corpid>|<secret>|<agent>|<user>|<msgs>|<delay>
"""


COOKIE_SMS = """📲 LẤY SMS

Không cần cookie.
Chỉ cần số điện thoại.

Dùng cho lệnh:
/sms_spam <phone>
"""
