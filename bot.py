#!/usr/bin/env python3
import os, sys, re, random, base64, asyncio
from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, SupabaseException

# — Load ENV —
API_ID    = int(os.getenv("API_ID", "0"))
API_HASH  = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# — Fail fast on missing ENV —
missing = [n for n,v in [
    ("API_ID", API_ID),
    ("API_HASH", API_HASH),
    ("BOT_TOKEN", BOT_TOKEN),
    ("ADMIN_ID", ADMIN_ID),
    ("SUPABASE_URL", SUPABASE_URL),
    ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_KEY),
] if not v]
if missing:
    print(f"[FATAL] Missing environment vars: {', '.join(missing)}")
    sys.exit(1)

# — Init Supabase & smoke-test —
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase.table("xeno_keys").select("key").limit(1).execute()
    print("[OK] Supabase connection established")
except Exception as e:
    print(f"[FATAL] Could not connect to Supabase: {e}")
    sys.exit(1)

# — Init Bot —
app = Client("xeno_premium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

MAX_SIZE   = 10 * 1024 * 1024  # 10MB
user_state = {}                # { user_id: "encrypt"|"decrypt" }

# — Helpers —
def parse_duration(code: str) -> timedelta:
    try:
        unit = code[-1].lower()
        val  = int(code[:-1])
        return {"m": timedelta(minutes=val),
                "h": timedelta(hours=val),
                "d": timedelta(days=val)}.get(unit, timedelta())
    except:
        return timedelta()

async def check_user_access(uid: int) -> bool:
    """Return True if user has any non-expired, non-banned key."""
    now = datetime.now(timezone.utc)
    try:
        resp = supabase.table("xeno_keys") \
            .select("expiry, banned") \
            .eq("redeemed_by", uid) \
            .eq("banned", False) \
            .execute()
        for row in resp.data or []:
            exp = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
            if exp > now:
                return True
    except Exception as e:
        print(f"[ERROR] access check failed for {uid}: {e}")
    return False

# — Catch *all* button clicks, log + guard —
@app.on_callback_query()
async def _all_cq_handler(bot: Client, cq: CallbackQuery):
    data = cq.data or "<no-data>"
    uid  = cq.from_user.id
    print(f"[CQ] User {uid} pressed `{data}`")
    # remove spinner
    await cq.answer()

    # guard encrypt/decrypt buttons
    if data in ("menu_encrypt", "menu_decrypt"):
        if not await check_user_access(uid):
            return await cq.message.reply("⛔ You need to redeem a key first (`/redeem <key>`).")

    # let the specific handlers run below

# — /start —
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(_, m: Message):
    uid = m.from_user.id
    if await check_user_access(uid):
        return await m.reply("✅ You already have access! Type /menu to see commands.")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔑 Buy Key", url="https://t.me/@xeeeenooo1")]])
    await m.reply("👋 You need a premium key. Buy one below:", reply_markup=kb)

# — /menu —
@app.on_message(filters.command("menu") & filters.private)
async def menu_cmd(_, m: Message):
    uid = m.from_user.id
    if not await check_user_access(uid):
        return await m.reply("⛔ You need a valid key. Redeem with `/redeem <key>`.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Encrypt", callback_data="menu_encrypt")],
        [InlineKeyboardButton("🔓 Decrypt", callback_data="menu_decrypt")],
        [InlineKeyboardButton("👥 Refer",   callback_data="menu_refer")],
    ])
    await m.reply("♨️ XENO PREMIUM BOT ♨️\nChoose an action:", reply_markup=kb)

# — Encrypt button pressed —
@app.on_callback_query(filters.regex("^menu_encrypt$"))
async def on_encrypt_cb(_, cq: CallbackQuery):
    user_state[cq.from_user.id] = "encrypt"
    await cq.message.reply("📂 Send a `.py` or `.txt` file (max 10MB) to encrypt.")

# — Decrypt button pressed —
@app.on_callback_query(filters.regex("^menu_decrypt$"))
async def on_decrypt_cb(_, cq: CallbackQuery):
    user_state[cq.from_user.id] = "decrypt"
    await cq.message.reply("📂 Send an encrypted `.py` or `.txt` file to decrypt.")

# — `/encrypt` & `/decrypt` commands as fallback —
@app.on_message(filters.command("encrypt") & filters.private)
async def cmd_encrypt(_, m: Message):
    user_state[m.from_user.id] = "encrypt"
    await m.reply("📂 Send a `.py` or `.txt` file (max 10MB) to encrypt.")

@app.on_message(filters.command("decrypt") & filters.private)
async def cmd_decrypt(_, m: Message):
    user_state[m.from_user.id] = "decrypt"
    await m.reply("📂 Send the encrypted `.py` or `.txt` file to decrypt.")

# — File handler —
@app.on_message(filters.document & filters.private)
async def file_handler(bot: Client, m: Message):
    mode = user_state.pop(m.from_user.id, None)
    if not mode:
        return await m.reply("⚠️ First choose Encrypt or Decrypt via /menu.")
    if mode == "encrypt":
        await do_encrypt(bot, m)
    else:
        await do_decrypt(bot, m)

# — Encryption logic —
async def do_encrypt(bot: Client, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only `.py` or `.txt` files are allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large. Max size is 10MB.")

    prog = await m.reply("⏳ Downloading...")
    path = await bot.download_media(m)
    await prog.edit("🔐 Encrypting...")

    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        b64 = base64.b64encode(raw.encode()).decode()
        output = f"import base64\nexec(base64.b64decode('{b64}').decode('utf-8'))\n"
        fn = f"encrypted_{doc.file_name}"
        with open(fn, "w", encoding="utf-8") as f:
            f.write(output)
        await bot.send_document(m.chat.id, fn, caption="✅ Encrypted file ready.")
    except Exception as e:
        await prog.edit(f"❌ Encryption error: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(fn): os.remove(fn)

# — Decryption logic —
async def do_decrypt(bot: Client, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only `.py` or `.txt` files are allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large. Max size is 10MB.")

    prog = await m.reply("⏳ Downloading...")
    path = await bot.download_media(m)
    await prog.edit("🔓 Decrypting...")

    try:
        content = open(path, "r", encoding="utf-8", errors="ignore").read()
        mobj    = re.search(r"base64\.b64decode\('(.+?)'\)", content)
        if not mobj:
            raise ValueError("No encrypted payload.")
        dec = base64.b64decode(mobj.group(1)).decode("utf-8")
        fn  = f"decrypted_{doc.file_name}"
        with open(fn, "w", encoding="utf-8") as f:
            f.write(dec)
        await bot.send_document(m.chat.id, fn, caption="✅ Decrypted file ready.")
    except Exception as e:
        await prog.edit(f"❌ Decryption error: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(fn): os.remove(fn)

# — Admin: /genkey or /generate —
@app.on_message(filters.command(["genkey","generate"]) & filters.private & filters.user(ADMIN_ID))
async def genkey_cmd(_, m: Message):
    parts = m.text.split()
    if len(parts) != 2:
        return await m.reply("❌ Usage: `/genkey <duration>`", quote=True)
    delta = parse_duration(parts[1])
    if delta.total_seconds() <= 0:
        return await m.reply("❌ Invalid duration. Use `1d`, `12h`, `30m`.", quote=True)

    key    = "XENO-" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=10))
    now    = datetime.now(timezone.utc)
    expiry = now + delta
    try:
        supabase.table("xeno_keys").insert({
            "key": key,
            "expiry": expiry.isoformat(),
            "redeemed_by": None,
            "owner_id": ADMIN_ID,
            "created": now.isoformat(),
            "duration": parts[1],
            "banned": False
        }).execute()
        await m.reply(f"✅ Key: `{key}`\nExpires: `{expiry}`\nRedeem with `/redeem {key}`")
    except Exception as e:
        print("[ERROR] key insert:", e)
        await m.reply("❌ Failed to generate key. Try again later.")

# — /redeem cmd —
@app.on_message(filters.command("redeem") & filters.private)
async def redeem_cmd(_, m: Message):
    parts = m.text.split()
    if len(parts)!=2:
        return await m.reply("❌ Usage: `/redeem <key>`", quote=True)
    key = parts[1].upper()
    now = datetime.now(timezone.utc)
    try:
        resp = supabase.table("xeno_keys").select("*").eq("key", key).execute()
        if not resp.data:
            return await m.reply("❌ Invalid key.")
        row = resp.data[0]
        if row.get("redeemed_by"):
            return await m.reply("❌ Already redeemed.")
        exp = datetime.fromisoformat(row["expiry"].replace("Z","+00:00"))
        if exp < now:
            return await m.reply("❌ Key expired.")
        supabase.table("xeno_keys") \
            .update({"redeemed_by": m.from_user.id}) \
            .eq("key", key).execute()
        await m.reply(f"✅ Redeemed! Valid until {exp}\nUse /menu now.")
    except Exception as e:
        print("[ERROR] redeem failed:", e)
        await m.reply("❌ Something went wrong. Try again later.")

if __name__ == "__main__":
    app.run()
