COOKIE_FB = """
📘 *LẤY COOKIE FACEBOOK*

*Cần:* `c_user`, `xs`, `datr`, `fr`, `sb`, `presence`

*Kiwi Browser (điện thoại):*
1. Cài Kiwi + ext "Cookie Editor"
2. facebook.com → login
3. Extension → Export → Copy JSON

*HTTP Canary (Android):*
1. Cài cert → bật VPN → mở FB
2. Bắt request → copy header Cookie

*PC:*
F12 → Network → F5 → Request Headers → cookie

*Test:* `/fb_check <cookie>`
"""

COOKIE_ZALO = """
📞 *LẤY COOKIE ZALO*

*Cách 1 — QR (khuyến nghị):*
`/zalo_qr` → quét 120s → bot lưu cookie

*Cách 2 — Thủ công:*
1. Kiwi → chat.zalo.me → login
2. Cookie Editor → Export
3. Cần: `zpw_sek`, `zpw_ver=645`, `zpw_type=30`

*IMEI:* từ Zalo PC Settings hoặc dùng `000000000000000`
"""

COOKIE_DISCORD = """
🎮 *TOKEN DISCORD*
PC: discord.com → F12 → Console → paste:
