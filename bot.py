#!/usr/bin/env python3
# XenoBot.py — Loads all secrets from ENV, no python-dotenv import required in production

import os
import sys
import re
import random
import base64
import asyncio

from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from supabase import create_client, SupabaseException

# — Optional local .env support — uncomment if you install python-dotenv locally
# from dotenv import load_dotenv
# load_dotenv()

# — Load from ENV —
API_ID    = int(os.getenv("API_ID", "0"))
API_HASH  = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# — Fail if any critical var is missing —
missing = [name for name,val in [
    ("API_ID", API_ID),
    ("API_HASH", API_HASH),
    ("BOT_TOKEN", BOT_TOKEN),
    ("ADMIN_ID", ADMIN_ID),
    ("SUPABASE_URL", SUPABASE_URL),
    ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_KEY)
] if not val]
if missing:
    print(f"[FATAL] Missing environment vars: {', '.join(missing)}")
    sys.exit(1)

# — Initialize Supabase & smoke-test the creds —
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

# — Initialize Pyrogram Bot —
app = Client(
    "xeno_premium_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# — Constants & State —
MAX_SIZE   = 10 * 1024 * 1024   # 10MB
user_state = {}                 # track per-user 'encrypt' or 'decrypt'

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
    now = datetime.now(timezone.utc)
    try:
        resp = supabase.table("xeno_keys") \
            .select("expiry, banned") \
            .eq("redeemed_by", user_id) \
            .eq("banned", False) \
            .execute()
        for row in (resp.data or []):
            exp = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
            if exp > now:
                return True
    except Exception as e:
        print(f"[ERROR] check_user_access({user_id}): {e}")
    return False

def restricted():
    async def _inner(_, update, __):
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
        return bool(await asyncio.to_thread(query))
    return filters.create(_inner)

# — Debug all callbacks —
@app.on_callback_query()
async def _debug_cb(_, cq: CallbackQuery):
    print(f"[DEBUG] Callback `{cq.data}` from {cq.from_user.id}")
    await cq.answer()

# — /start handler —
@app.on_message(filters.command("start") & filters.private)
async def start(_, m: Message):
    uid = m.from_user.id
    if await check_user_access(uid):
        await m.reply("✅ Welcome back! Use /menu to see commands.")
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Buy Key", url="https://t.me/@xeeeenooo1")]
        ])
        await m.reply("👋 You need a premium key. Buy one below:", reply_markup=kb)

# — /menu handler —
@app.on_message(filters.command("menu") & filters.private)
async def menu_cmd(_, m: Message):
    if not await check_user_access(m.from_user.id):
        return await m.reply("⛔ You need to redeem a key via `/redeem <key>` first.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Encrypt", callback_data="menu_encrypt")],
        [InlineKeyboardButton("🔓 Decrypt", callback_data="menu_decrypt")],
        [InlineKeyboardButton("👥 Refer",   callback_data="menu_refer")],
    ])
    await m.reply("♨️ XENO PREMIUM BOT ♨️\nChoose an action:", reply_markup=kb)

# — callback for choosing encrypt/decrypt —
@app.on_callback_query(filters.regex("^(menu_encrypt|menu_decrypt)$") & restricted())
async def _cb_mode(_, cq: CallbackQuery):
    mode = "encrypt" if cq.data.endswith("encrypt") else "decrypt"
    user_state[cq.from_user.id] = mode
    await cq.answer(f"{mode.title()} mode")
    prompt = (
        "📂 Send a .py or .txt file to encrypt."
        if mode=="encrypt"
        else "📂 Send an encrypted .py/.txt file to decrypt."
    )
    await cq.message.reply(prompt)

# — /encrypt and /decrypt commands —
@app.on_message(filters.command("encrypt") & filters.private & restricted())
async def cmd_encrypt(_, m: Message):
    user_state[m.from_user.id] = "encrypt"
    await m.reply("📂 Send a .py or .txt file to encrypt.")

@app.on_message(filters.command("decrypt") & filters.private & restricted())
async def cmd_decrypt(_, m: Message):
    user_state[m.from_user.id] = "decrypt"
    await m.reply("📂 Send the encrypted .py/.txt file to decrypt.")

# — receiving a file —
@app.on_message(filters.document & filters.private)
async def doc_handler(c, m: Message):
    mode = user_state.pop(m.from_user.id, None)
    if not mode:
        return await m.reply("⚠️ Choose encrypt/decrypt first with /menu.")
    if mode=="encrypt":
        await _encrypt_file(c, m)
    else:
        await _decrypt_file(c, m)

async def _encrypt_file(c, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only .py or .txt allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ Max 10MB.")
    prog = await m.reply("⏳ Downloading…")
    path = await c.download_media(m)
    await prog.edit("🔐 Encrypting…")
    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        b64 = base64.b64encode(raw.encode()).decode()
        code = f"import base64\nexec(base64.b64decode('{b64}').decode('utf-8'))\n"
        out  = f"encrypted_{doc.file_name}"
        open(out, "w", encoding="utf-8").write(code)
        await c.send_document(m.chat.id, out, caption="✅ Encrypted file ready.")
    except Exception as e:
        await prog.edit(f"❌ Encryption failed: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(out): os.remove(out)

async def _decrypt_file(c, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only .py or .txt allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ Max 10MB.")
    prog = await m.reply("⏳ Downloading…")
    path = await c.download_media(m)
    await prog.edit("🔓 Decrypting…")
    try:
        content = open(path, "r", encoding="utf-8", errors="ignore").read()
        match   = re.search(r"base64\.b64decode\('(.+?)'\)", content)
        if not match:
            raise ValueError("No encrypted payload.")
        dec     = base64.b64decode(match.group(1)).decode("utf-8")
        out     = f"decrypted_{doc.file_name}"
        open(out, "w", encoding="utf-8").write(dec)
        await c.send_document(m.chat.id, out, caption="✅ Decrypted file ready.")
    except Exception as e:
        await prog.edit(f"❌ Decryption failed: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(out): os.remove(out)

# — /genkey & /generate for admin only —
@app.on_message(
    filters.command(["genkey","generate"]) &
    filters.private &
    filters.user(ADMIN_ID)
)
async def genkey_cmd(_, m: Message):
    parts = m.text.strip().split()
    if len(parts)!=2:
        return await m.reply(
            "❌ Usage: `/genkey <duration>` or `/generate <duration>`\n"
            "Examples: `/genkey 1d`, `/generate 30m`, `/genkey 12h`",
            quote=True
        )
    delta = parse_duration(parts[1])
    if delta.total_seconds()<=0:
        return await m.reply("❌ Invalid duration. Use `1d`, `12h`, or `30m`.", quote=True)
    key    = "XENO-"+"".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=10))
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
        await m.reply(
            f"✅ New key:\n🔐 `{key}`\n⏳ `{parts[1]}` (expires {expiry})\n\n"
            f"Redeem with: `/redeem {key}`"
        )
    except Exception as e:
        print(f"[ERROR] Key insert failed: {e}")
        await m.reply("❌ Failed to generate key.")

# — /redeem command —
@app.on_message(filters.command("redeem") & filters.private)
async def redeem_cmd(_, m: Message):
    parts = m.text.strip().split()
    if len(parts)!=2:
        return await m.reply("❌ Usage: `/redeem <key>`", quote=True)
    k   = parts[1].upper()
    now = datetime.now(timezone.utc)
    try:
        resp = supabase.table("xeno_keys").select("*").eq("key", k).execute()
        if not resp.data:
            return await m.reply("❌ Invalid key.")
        row = resp.data[0]
        if row.get("redeemed_by"):
            return await m.reply("❌ Already redeemed.")
        exp = datetime.fromisoformat(row["expiry"].replace("Z","+00:00"))
        if exp < now:
            return await m.reply("❌ Key expired.")
        supabase.table("xeno_keys").update({"redeemed_by": m.from_user.id}).eq("key", k).execute()
        await m.reply(f"✅ Redeemed! Valid until {exp}\nUse /menu now.")
    except Exception as e:
        print(f"[ERROR] Redeem failed: {e}")
        await m.reply("❌ Something went wrong.")

if __name__ == "__main__":
    app.run()
