import os
import re
import random
import base64
import asyncio
from datetime import datetime, timedelta, timezone

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from supabase import create_client

# === Config ===
API_ID = 26024182
API_HASH = "19af4be4f201f1b2749ef3896c42e089"
BOT_TOKEN = "7796863520:AAEuYaU_FUh-PutGjlZTGjapOSIFxqi4gFU"
ADMIN_ID = 5110224851

SUPABASE_URL = "https://psxjagzdlcrxtonmezpm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBzeGphZ3pkbGNyeHRvbm1lenBtIiwicm9sZSI6InNlcnZpY2NlX3JvbGUiLCJpYXQiOjE3NDQyMDQzNjgsImV4cCI6MjA1OTc4MDM2OH0.9-UTy_y0qDEfK6N0n_YspX3BcY3CVMb2bk9tPaiddWU"

# === Initialize Supabase Client ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === Initialize Pyrogram Bot ===
app = Client("log_search_bot",
             api_id=API_ID,
             api_hash=API_HASH,
             bot_token=BOT_TOKEN)

# === Helpers ===

async def check_user_access(user_id):
    now = datetime.now(timezone.utc)
    try:
        resp = supabase.table("xeno_keys") \
            .select("expiry, banned") \
            .eq("redeemed_by", user_id) \
            .eq("banned", False) \
            .execute()
        rows = resp.data
        if not rows:
            return False

        for row in rows:
            expiry = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
            if expiry > now:
                return True
        return False

    except Exception as e:
        print(f"[ERROR] check_user_access failed for {user_id}: {e}")
        return False


def parse_duration(code: str) -> timedelta:
    try:
        unit = code[-1]
        value = int(code[:-1])
        if unit == "m":
            return timedelta(minutes=value)
        if unit == "h":
            return timedelta(hours=value)
        if unit == "d":
            return timedelta(days=value)
    except:
        pass
    return timedelta(seconds=0)


def restricted():
    """Filter decorator to ensure user has a valid, non-expired, non-banned key."""
    async def decorator_filter(client, update, _=None):
        user_id = (
            update.from_user.id
            if isinstance(update, (Message, CallbackQuery))
            else None
        )
        if not user_id:
            return False

        def query():
            try:
                res = supabase.from_("xeno_keys") \
                    .select("banned") \
                    .eq("redeemed_by", user_id) \
                    .eq("banned", False) \
                    .limit(1) \
                    .execute()
                return getattr(res, "data", res.get("data", []))
            except Exception as e:
                print(f"[restricted] Supabase query failed for {user_id}: {e}")
                return []

        data = await asyncio.to_thread(query)
        has_access = bool(data)
        print(f"[restricted] Access for {user_id}: {has_access}")
        return has_access

    return filters.create(decorator_filter)


# Track user flow state: either 'encrypt' or 'decrypt'
user_state = {}
MAX_SIZE = 10 * 1024 * 1024  # 10MB


# === Generic Debugging for Callbacks ===
@app.on_callback_query()
async def debug_all_callbacks(client, cb: CallbackQuery):
    print(f"[DEBUG] Callback: {cb.data} from {cb.from_user.id}")
    await cb.answer()


# === Bot Handlers ===

@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    user_id = message.from_user.id
    now = datetime.now(timezone.utc)

    try:
        resp = supabase.table("xeno_keys") \
            .select("expiry, banned") \
            .eq("redeemed_by", user_id) \
            .eq("banned", False) \
            .execute()
        rows = resp.data or []
        print(f"[INFO] /start: {len(rows)} keys for {user_id}")

        for row in rows:
            expiry = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
            if expiry > now:
                return await message.reply(
                    "✅ You already have access! Type /menu to view commands."
                )

    except Exception as e:
        print(f"[ERROR] /start access check failed: {e}")
        return await message.reply("❌ Error validating access. Try again later.")

    # No valid key found
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Buy Key", url="https://t.me/@xeeeenooo1")]
    ])
    await message.reply(
        "👋 You need a premium key to use this bot. Buy one below:",
        reply_markup=keyboard
    )


@app.on_message(filters.command("menu") & filters.private)
async def show_command(client, message: Message):
    user_id = message.from_user.id
    if not await check_user_access(user_id):
        return await message.reply("⛔ You need to redeem a valid key first.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Encrypt", callback_data="menu_encrypt")],
        [InlineKeyboardButton("🔓 Decrypt", callback_data="menu_decrypt")],
        [InlineKeyboardButton("📂 Upload", callback_data="menu_upload")],
        [InlineKeyboardButton("🔍 Search", callback_data="menu_search")],
        [InlineKeyboardButton("📊 My Info", callback_data="menu_myinfo")],
        [InlineKeyboardButton("👥 Refer", callback_data="menu_refer")],
    ])
    await message.reply("♨️ XENO PREMIUM BOT ♨️\n\n🔹Available Commands🔹", reply_markup=kb)


@app.on_callback_query(filters.regex("^menu_encrypt$") & restricted())
async def cb_encrypt(client, cb: CallbackQuery):
    await cb.answer("Encrypt selected.")
    user_state[cb.from_user.id] = "encrypt"
    await cb.message.reply("📂 Send a `.py` or `.txt` file (max 10MB) to encrypt.")


@app.on_callback_query(filters.regex("^menu_decrypt$") & restricted())
async def cb_decrypt(client, cb: CallbackQuery):
    await cb.answer("Decrypt selected.")
    user_state[cb.from_user.id] = "decrypt"
    await cb.message.reply("📂 Send the encrypted `.py` or `.txt` file to decrypt.")


@app.on_message(filters.command("encrypt") & filters.private & restricted())
async def encrypt_command(client, message: Message):
    user_state[message.from_user.id] = "encrypt"
    await message.reply("📂 Send a `.py` or `.txt` file (max 10MB) to encrypt.")


@app.on_message(filters.command("decrypt") & filters.private & restricted())
async def decrypt_command(client, message: Message):
    user_state[message.from_user.id] = "decrypt"
    await message.reply("📂 Send the encrypted `.py` or `.txt` file to decrypt.")


@app.on_message(filters.document & filters.private)
async def handle_uploaded_file(client, message: Message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    if not state:
        return await message.reply("⚠️ Please choose encrypt or decrypt first via /menu.")
    if state == "encrypt":
        await encrypt_file(client, message)
    else:
        await decrypt_file(client, message)


async def encrypt_file(client, message: Message):
    user_id = message.from_user.id
    user_state.pop(user_id, None)

    doc = message.document
    if not (doc.file_name.endswith((".py", ".txt"))):
        return await message.reply("❌ Only .py or .txt files allowed.")
    if doc.file_size > MAX_SIZE:
        return await message.reply("❌ File too large; 10MB max.")

    m = await message.reply("⏳ Downloading...")
    path = await client.download_media(message)
    await m.edit("🔐 Encrypting...")

    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        encoded = base64.b64encode(raw.encode()).decode()
        encrypted = (
            "import base64\n"
            f"exec(base64.b64decode('{encoded}').decode('utf-8'))\n"
        )
    except Exception as e:
        await m.edit(f"❌ Encryption failed: {e}")
        os.remove(path)
        return

    out = f"encrypted_{doc.file_name}"
    with open(out, "w", encoding="utf-8") as f:
        f.write(encrypted)

    await client.send_document(message.chat.id, document=out, caption="✅ Here’s your encrypted file.")
    await m.delete()
    os.remove(path)
    os.remove(out)


async def decrypt_file(client, message: Message):
    user_id = message.from_user.id
    user_state.pop(user_id, None)

    doc = message.document
    if not (doc.file_name.endswith((".py", ".txt"))):
        return await message.reply("❌ Only .py or .txt files allowed.")
    if doc.file_size > MAX_SIZE:
        return await message.reply("❌ File too large; 10MB max.")

    m = await message.reply("⏳ Downloading...")
    path = await client.download_media(message)
    await m.edit("🔓 Decrypting...")

    try:
        content = open(path, "r", encoding="utf-8", errors="ignore").read()
        match = re.search(r"base64\.b64decode\('(.+?)'\)", content)
        if not match:
            raise ValueError("No encrypted payload found.")
        decoded = base64.b64decode(match.group(1)).decode("utf-8")
    except Exception as e:
        await m.edit(f"❌ Decryption failed: {e}")
        os.remove(path)
        return

    out = f"decrypted_{doc.file_name}"
    with open(out, "w", encoding="utf-8") as f:
        f.write(decoded)

    await client.send_document(message.chat.id, document=out, caption="✅ Here’s your decrypted file.")
    await m.delete()
    os.remove(path)
    os.remove(out)


@app.on_message(
    filters.command(["genkey", "generate"])
    & filters.private
    & filters.user(ADMIN_ID)
)
async def manual_genkey_command(client, message: Message):
    """
    Admin-only key generator.
    Accessible via both /genkey and /generate.
    """
    args = message.text.strip().split()
    if len(args) != 2:
        return await message.reply(
            "❌ Usage: `/genkey <duration>` or `/generate <duration>`\n"
            "Examples: `/genkey 1d`, `/generate 30m`, `/genkey 12h`",
            quote=True
        )

    duration_code = args[1]
    delta = parse_duration(duration_code)
    if delta.total_seconds() <= 0:
        return await message.reply("❌ Invalid duration. Use like `1d`, `12h`, or `30m`.", quote=True)

    key = "XENO-" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=10))
    now = datetime.now(timezone.utc)
    expiry = now + delta

    try:
        supabase.table("xeno_keys").insert({
            "key": key,
            "expiry": expiry.isoformat(),
            "redeemed_by": None,
            "owner_id": ADMIN_ID,
            "created": now.isoformat(),
            "duration": duration_code,
            "banned": False
        }).execute()

        await message.reply(
            f"✅ New key generated:\n"
            f"🔐 Key: `{key}`\n"
            f"⏳ Duration: `{duration_code}`\n"
            f"📅 Expires on: `{expiry}`\n\n"
            f"To redeem: type `/redeem {key}`"
        )
    except Exception as e:
        print(f"[ERROR] Key insert failed: {e}")
        await message.reply("❌ Failed to generate key. Try again later.")


@app.on_message(filters.command("redeem") & filters.private)
async def redeem_command(client, message: Message):
    args = message.text.strip().split()
    if len(args) != 2:
        return await message.reply(
            "❌ Usage: `/redeem <key>`\nExample: `/redeem XENO-ABC123XYZ9`",
            quote=True
        )

    input_key = args[1].upper()
    user_id = message.from_user.id
    now = datetime.now(timezone.utc)

    try:
        resp = supabase.table("xeno_keys") \
            .select("*") \
            .eq("key", input_key) \
            .execute()

        if not resp.data:
            return await message.reply("❌ Invalid key.")

        key_data = resp.data[0]
        if key_data.get("redeemed_by"):
            return await message.reply("❌ This key was already redeemed.")
        expiry = datetime.fromisoformat(key_data["expiry"].replace("Z", "+00:00"))
        if expiry < now:
            return await message.reply("❌ This key has expired.")

        supabase.table("xeno_keys") \
            .update({"redeemed_by": user_id}) \
            .eq("key", input_key) \
            .execute()

        await message.reply(
            f"✅ Key redeemed!\n"
            f"🔐 `{input_key}` valid until `{expiry}`\n\n"
            f"You now have premium access. Type /menu to see commands."
        )
    except Exception as e:
        print(f"[ERROR] Redeem failed: {e}")
        await message.reply("❌ Something went wrong. Try again later.")


if __name__ == "__main__":
    app.run()
