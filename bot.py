#!/usr/bin/env python3
import os
import sys
import re
import random
import base64
import asyncio

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
missing = [n for n, v in [
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
except SupabaseException as e:
    print(f"[FATAL] Supabase refused key: {e}")
    sys.exit(1)
except Exception as e:
    print(f"[FATAL] Unexpected Supabase error: {e}")
    sys.exit(1)

# — Init Bot —
app = Client(
    "xeno_premium_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# — Constants & State —
MAX_SIZE   = 10 * 1024 * 1024  # 10MB
user_state = {}                # user_id → "encrypt" or "decrypt"

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
    """Return True if user has any valid (non-banned, non-expired) key."""
    now = datetime.now(timezone.utc)
    try:
        resp = supabase.table("xeno_keys") \
            .select("expiry, banned") \
            .eq("redeemed_by", uid) \
            .eq("banned", False) \
            .execute()
        for row in (resp.data or []):
            expiry = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
            if expiry > now:
                return True
    except Exception as e:
        print(f"[ERROR] access check failed for {uid}: {e}")
    return False

# — /start —
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(_, m: Message):
    uid = m.from_user.id
    if await check_user_access(uid):
        await m.reply("✅ Welcome back! Use /menu to see commands.")
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Buy Key", url="https://t.me/@xeeeenooo1")]
        ])
        await m.reply("👋 You need a premium key. Buy one below:", reply_markup=kb)

# — /menu —
@app.on_message(filters.command("menu") & filters.private)
async def menu_cmd(_, m: Message):
    uid = m.from_user.id
    if not await check_user_access(uid):
        return await m.reply("⛔ You need to redeem a key first (`/redeem <key>`).")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Encrypt", callback_data="menu_encrypt")],
        [InlineKeyboardButton("🔓 Decrypt", callback_data="menu_decrypt")],
        [InlineKeyboardButton("👥 Refer",   callback_data="menu_refer")],
    ])
    await m.reply("♨️ XENO PREMIUM BOT ♨️\nChoose an action:", reply_markup=kb)

# — Encrypt button —
# — Encrypt button —
@app.on_callback_query(filters.regex("^menu_encrypt$"))
async def on_encrypt_cb(bot: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    print(f"[HANDLER] Encrypt button pressed by {uid}")
    await cq.answer("Encrypt mode activated!")
    # ◀─ Clear the buttons from the original /menu message
    await cq.message.edit_reply_markup(None)

    if not await check_user_access(uid):
        return await cq.message.reply("⛔ You need to redeem a key first (`/redeem <key>`).")

    user_state[uid] = "encrypt"
    await cq.message.reply("📂 Send a `.py` or `.txt` file (max 10MB) to encrypt.")
    print(f"[HANDLER] Encrypt prompt sent to {uid}")


# — Decrypt button —
@app.on_callback_query(filters.regex("^menu_decrypt$"))
async def on_decrypt_cb(bot: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    print(f"[HANDLER] Decrypt button pressed by {uid}")
    await cq.answer("Decrypt mode activated!")
    # ◀─ Clear the buttons from the original /menu message
    await cq.message.edit_reply_markup(None)

    if not await check_user_access(uid):
        return await cq.message.reply("⛔ You need to redeem a key first (`/redeem <key>`).")

    user_state[uid] = "decrypt"
    await cq.message.reply("📂 Send an encrypted `.py` or `.txt` file to decrypt.")
    print(f"[HANDLER] Decrypt prompt sent to {uid}")

# — Fallback commands —
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
    uid  = m.from_user.id
    mode = user_state.pop(uid, None)
    if not mode:
        return await m.reply("⚠️ First choose Encrypt or Decrypt via /menu.")
    if mode == "encrypt":
        await do_encrypt(bot, m)
    else:
        await do_decrypt(bot, m)

async def do_encrypt(bot: Client, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only `.py` or `.txt` files are allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large (max 10MB).")
    prog = await m.reply("⏳ Downloading...")
    path = await bot.download_media(m)
    await prog.edit("🔐 Encrypting...")
    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        b64 = base64.b64encode(raw.encode()).decode()
        payload = f"import base64\nexec(base64.b64decode('{b64}').decode('utf-8'))\n"
        out_fn = f"encrypted_{doc.file_name}"
        with open(out_fn, "w", encoding="utf-8") as f:
            f.write(payload)
        await bot.send_document(m.chat.id, out_fn, caption="✅ Encrypted file ready.")
    except Exception as e:
        await prog.edit(f"❌ Encryption error: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(out_fn): os.remove(out_fn)

async def do_decrypt(bot: Client, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only `.py` or `.txt` files are allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large (max 10MB).")
    prog = await m.reply("⏳ Downloading...")
    path = await bot.download_media(m)
    await prog.edit("🔓 Decrypting...")
    try:
        content = open(path, "r", encoding="utf-8", errors="ignore").read()
        mobj    = re.search(r"base64\.b64decode\('(.+?)'\)", content)
        if not mobj:
            raise ValueError("No encrypted payload found.")
        decoded = base64.b64decode(mobj.group(1)).decode("utf-8")
        out_fn  = f"decrypted_{doc.file_name}"
        with open(out_fn, "w", encoding="utf-8") as f:
            f.write(decoded)
        await bot.send_document(m.chat.id, out_fn, caption="✅ Decrypted file ready.")
    except Exception as e:
        await prog.edit(f"❌ Decryption error: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(out_fn): os.remove(out_fn)

# — Admin: /genkey & /generate —
@app.on_message(filters.command(["genkey","generate"]) & filters.private & filters.user(ADMIN_ID))
async def genkey_cmd(_, m: Message):
    parts = m.text.strip().split()
    if len(parts) != 2:
        return await m.reply("❌ Usage: `/genkey <duration>`", quote=True)
    delta = parse_duration(parts[1])
    if delta.total_seconds() <= 0:
        return await m.reply("❌ Invalid duration. Use `1d`, `12h`, or `30m`.", quote=True)
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
        print(f"[ERROR] key insert: {e}")
        await m.reply("❌ Failed to generate key. Try again later.")

# — /redeem —
@app.on_message(filters.command("redeem") & filters.private)
async def redeem_cmd(_, m: Message):
    parts = m.text.strip().split()
    if len(parts) != 2:
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
        print(f"[ERROR] redeem failed: {e}")
        await m.reply("❌ Something went wrong. Try again later.")

if __name__ == "__main__":
    app.run()
