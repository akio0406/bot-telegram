#!/usr/bin/env python3
# XenoBot.py — Updated to use ENV vars & service_role key

import os
import sys
import re
import random
import base64
import asyncio

from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv           # pip install python-dotenv
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from supabase import create_client, SupabaseException

# — Load environment variables from .env (optional for local testing) —
load_dotenv()

# — Configuration from ENV —
API_ID    = int(os.getenv("API_ID", "0"))
API_HASH  = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# — Validate critical ENV vars —
missing = []
for name, val in [
    ("API_ID", API_ID),
    ("API_HASH", API_HASH),
    ("BOT_TOKEN", BOT_TOKEN),
    ("ADMIN_ID", ADMIN_ID),
    ("SUPABASE_URL", SUPABASE_URL),
    ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_KEY),
]:
    if not val:
        missing.append(name)
if missing:
    print(f"[FATAL] Missing environment variables: {', '.join(missing)}")
    sys.exit(1)

# — Initialize Supabase & smoke-test the connection —
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    # quick read to confirm credentials
    supabase.table("xeno_keys").select("key").limit(1).execute()
    print("[OK] Supabase connection established")
except SupabaseException as e:
    print(f"[FATAL] Supabase refused key: {e}")
    sys.exit(1)
except Exception as e:
    print(f"[FATAL] Unexpected Supabase error: {e}")
    sys.exit(1)

# — Initialize Pyrogram Bot —
app = Client(
    "xeno_premium_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# — Constants & State —
MAX_SIZE   = 10 * 1024 * 1024   # 10MB
user_state = {}                 # track whether user is encrypting/decrypting

# — Helpers — 
def parse_duration(code: str) -> timedelta:
    try:
        unit = code[-1].lower()
        val  = int(code[:-1])
        return {
            "m": timedelta(minutes=val),
            "h": timedelta(hours=val),
            "d": timedelta(days=val),
        }.get(unit, timedelta())
    except:
        return timedelta()

async def check_user_access(user_id: int) -> bool:
    """Return True if user has at least one non-expired, non-banned key."""
    now = datetime.now(timezone.utc)
    try:
        resp = supabase.table("xeno_keys") \
            .select("expiry, banned") \
            .eq("redeemed_by", user_id) \
            .eq("banned", False) \
            .execute()
        rows = resp.data or []
        for row in rows:
            expiry = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
            if expiry > now:
                return True
    except Exception as e:
        print(f"[ERROR] check_user_access({user_id}) failed: {e}")
    return False

def restricted():
    """Filter to allow only users with a valid key."""
    async def _inner(client, update, _):
        uid = getattr(update.from_user, "id", None)
        if not uid:
            return False
        def query():
            try:
                r = supabase.from_("xeno_keys") \
                    .select("banned") \
                    .eq("redeemed_by", uid) \
                    .eq("banned", False) \
                    .limit(1).execute()
                return getattr(r, "data", r.get("data", []))
            except:
                return []
        data = await asyncio.to_thread(query)
        return bool(data)
    return filters.create(_inner)

# — Generic debug for callbacks —
@app.on_callback_query()
async def _debug_cb(client, cq: CallbackQuery):
    print(f"[DEBUG] Callback `{cq.data}` from {cq.from_user.id}")
    await cq.answer()

# — Bot Handlers —

@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    uid = message.from_user.id
    if await check_user_access(uid):
        await message.reply("✅ Welcome back! Use /menu to see available commands.")
    else:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔑 Buy Key", url="https://t.me/@xeeeenooo1")]])
        await message.reply("👋 You need a premium key. Buy one below:", reply_markup=kb)

@app.on_message(filters.command("menu") & filters.private)
async def menu_cmd(client, message: Message):
    uid = message.from_user.id
    if not await check_user_access(uid):
        return await message.reply("⛔ You need to redeem a valid key first (`/redeem <key>`).")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Encrypt", callback_data="menu_encrypt")],
        [InlineKeyboardButton("🔓 Decrypt", callback_data="menu_decrypt")],
        [InlineKeyboardButton("👥 Refer",   callback_data="menu_refer")],
    ])
    await message.reply("♨️ XENO PREMIUM BOT ♨️\nChoose an action:", reply_markup=kb)

@app.on_callback_query(filters.regex("^(menu_encrypt|menu_decrypt)$") & restricted())
async def _cb_mode(client, cq: CallbackQuery):
    mode = "encrypt" if cq.data.endswith("encrypt") else "decrypt"
    user_state[cq.from_user.id] = mode
    await cq.answer(f"{mode.title()} mode selected.")
    prompt = (
        "📂 Send a .py or .txt file to encrypt."
        if mode == "encrypt"
        else "📂 Send an encrypted .py/.txt file to decrypt."
    )
    await cq.message.reply(prompt)

@app.on_message(filters.command("encrypt") & filters.private & restricted())
async def cmd_encrypt(client, message: Message):
    user_state[message.from_user.id] = "encrypt"
    await message.reply("📂 Send a .py or .txt file to encrypt.")

@app.on_message(filters.command("decrypt") & filters.private & restricted())
async def cmd_decrypt(client, message: Message):
    user_state[message.from_user.id] = "decrypt"
    await message.reply("📂 Send the encrypted .py/.txt file to decrypt.")

@app.on_message(filters.document & filters.private)
async def doc_handler(client, message: Message):
    uid   = message.from_user.id
    mode  = user_state.pop(uid, None)
    if not mode:
        return await message.reply("⚠️ First choose encrypt/decrypt with /menu.")
    if mode == "encrypt":
        await _encrypt_file(client, message)
    else:
        await _decrypt_file(client, message)

async def _encrypt_file(client, message: Message):
    doc = message.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await message.reply("❌ Only .py or .txt files allowed.")
    if doc.file_size > MAX_SIZE:
        return await message.reply("❌ File too large; 10MB max.")
    progress = await message.reply("⏳ Downloading…")
    path     = await client.download_media(message)
    await progress.edit("🔐 Encrypting…")
    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        b64 = base64.b64encode(raw.encode()).decode()
        code = f"import base64\nexec(base64.b64decode('{b64}').decode('utf-8'))\n"
        out  = f"encrypted_{doc.file_name}"
        with open(out, "w", encoding="utf-8") as f:
            f.write(code)
        await client.send_document(message.chat.id, out, caption="✅ Here’s your encrypted file.")
    except Exception as e:
        await progress.edit(f"❌ Encryption failed: {e}")
    finally:
        await progress.delete()
        os.remove(path)
        if os.path.exists(out):
            os.remove(out)

async def _decrypt_file(client, message: Message):
    doc = message.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await message.reply("❌ Only .py or .txt files allowed.")
    if doc.file_size > MAX_SIZE:
        return await message.reply("❌ File too large; 10MB max.")
    progress = await message.reply("⏳ Downloading…")
    path     = await client.download_media(message)
    await progress.edit("🔓 Decrypting…")
    try:
        content = open(path, "r", encoding="utf-8", errors="ignore").read()
        m = re.search(r"base64\.b64decode\('(.+?)'\)", content)
        if not m:
            raise ValueError("No encrypted payload found.")
        decoded = base64.b64decode(m.group(1)).decode("utf-8")
        out     = f"decrypted_{doc.file_name}"
        with open(out, "w", encoding="utf-8") as f:
            f.write(decoded)
        await client.send_document(message.chat.id, out, caption="✅ Here’s your decrypted file.")
    except Exception as e:
        await progress.edit(f"❌ Decryption failed: {e}")
    finally:
        await progress.delete()
        os.remove(path)
        if os.path.exists(out):
            os.remove(out)

@app.on_message(
    filters.command(["genkey", "generate"]) &
    filters.private &
    filters.user(ADMIN_ID)
)
async def genkey_cmd(client, message: Message):
    parts = message.text.strip().split()
    if len(parts) != 2:
        return await message.reply(
            "❌ Usage: `/genkey <duration>` or `/generate <duration>`\n"
            "Examples: `/genkey 1d`, `/generate 30m`, `/genkey 12h`",
            quote=True
        )
    delta = parse_duration(parts[1])
    if delta.total_seconds() <= 0:
        return await message.reply("❌ Invalid duration. Use like `1d`, `12h`, `30m`.", quote=True)
    key    = "XENO-" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=10))
    now    = datetime.now(timezone.utc)
    expiry = now + delta
    try:
        supabase.table("xeno_keys").insert({
            "key":         key,
            "expiry":      expiry.isoformat(),
            "redeemed_by": None,
            "owner_id":    ADMIN_ID,
            "created":     now.isoformat(),
            "duration":    parts[1],
            "banned":      False
        }).execute()
        await message.reply(
            f"✅ New key generated:\n"
            f"🔐 `{key}`\n"
            f"⏳ `{parts[1]}` (expires {expiry})\n\n"
            f"Redeem with: `/redeem {key}`"
        )
    except Exception as e:
        print(f"[ERROR] Key insert failed: {e}")
        await message.reply("❌ Failed to generate key. Try again later.")

@app.on_message(filters.command("redeem") & filters.private)
async def redeem_cmd(client, message: Message):
    parts = message.text.strip().split()
    if len(parts) != 2:
        return await message.reply("❌ Usage: `/redeem <key>`", quote=True)
    k   = parts[1].upper()
    now = datetime.now(timezone.utc)
    try:
        resp = supabase.table("xeno_keys").select("*").eq("key", k).execute()
        if not resp.data:
            return await message.reply("❌ Invalid key.")
        row = resp.data[0]
        if row.get("redeemed_by"):
            return await message.reply("❌ This key was already redeemed.")
        exp = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
        if exp < now:
            return await message.reply("❌ This key has expired.")
        supabase.table("xeno_keys") \
            .update({"redeemed_by": message.from_user.id}) \
            .eq("key", k).execute()
        await message.reply(f"✅ Key redeemed! Valid until {exp}\nUse /menu now.")
    except Exception as e:
        print(f"[ERROR] Redeem failed: {e}")
        await message.reply("❌ Something went wrong. Try again later.")

if __name__ == "__main__":
    app.run()
