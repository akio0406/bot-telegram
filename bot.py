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
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBzeGphZ3pkbGNyeHRvbm1lenBtIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NDIwNDM2OCwiZXhwIjoyMDU5NzgwMzY4fQ.9-UTy_y0qDEfK6N0n_YspX3BcY3CVMb2bk9tPaiddWU"

# === Initialize Supabase Client ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === Initialize Pyrogram Bot ===
app = Client("log_search_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def check_user_access(user_id):
    now = datetime.now(timezone.utc)
    try:
        response = supabase.table("xeno_keys") \
            .select("expiry, banned") \
            .eq("redeemed_by", user_id) \
            .eq("banned", False) \
            .execute()

        rows = response.data
        if not rows:
            return False

        for row in rows:
            expiry = datetime.fromisoformat(row["expiry"].replace('Z', '+00:00'))
            if expiry > now:
                return True
        return False

    except Exception as e:
        print(f"[ERROR] check_user_access failed for user {user_id}: {e}")
        return False

def parse_duration(code):
    try:
        unit = code[-1]
        value = int(code[:-1])
        if unit == 'm':
            return timedelta(minutes=value)
        elif unit == 'h':
            return timedelta(hours=value)
        elif unit == 'd':
            return timedelta(days=value)
    except:
        return timedelta(seconds=0)

def restricted():
    async def decorator_filter(client, update, _=None):
        user_id = (
            update.from_user.id
            if isinstance(update, (Message, CallbackQuery)) else None
        )
        if not user_id:
            print("[restricted] No user_id found in update.")
            return False

        def query():
            try:
                res = supabase.from_("xeno_keys") \
                    .select("banned") \
                    .eq("redeemed_by", user_id) \
                    .eq("banned", False) \
                    .limit(1) \
                    .execute()
                # res.data is the usual field but sometimes might be a dict
                data = res.data if hasattr(res, "data") else res.get("data")
                return data
            except Exception as e:
                print(f"[restricted] Exception querying supabase for user {user_id}: {e}")
                return None

        data = await asyncio.to_thread(query)
        has_access = bool(data)
        print(f"[restricted] Access check for user {user_id}: {has_access}")
        return has_access

    return filters.create(decorator_filter)
    
import base64
import os
import re
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

user_state = {}  # Tracks which user is encrypting or decrypting
MAX_SIZE = 10 * 1024 * 1024  # 10 MB file size limit

# Debug all callbacks (optional)
@app.on_callback_query()
async def debug_all_callbacks(client, cb):
    print(f"[DEBUG] Callback received: {cb.data} from user {cb.from_user.id}")
    await cb.answer()  # Just answer to remove "loading"

# /menu command — shows User Menu
@app.on_message(filters.command("menu") & filters.private)
async def show_command(client, message):
    user_id = message.from_user.id
    print(f"[DEBUG] Menu command received from user {user_id}")  # Debug log
    if not await check_user_access(user_id):
        print(f"[DEBUG] User {user_id} does not have access")  # Debug log
        return await message.reply("⛔ You need to redeem a valid key first.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Encrypt", callback_data="menu_encrypt")],
        [InlineKeyboardButton("🔓 Decrypt", callback_data="menu_decrypt")],
        [InlineKeyboardButton("📂 Upload", callback_data="menu_upload")],
        [InlineKeyboardButton("🔍 Search", callback_data="menu_search")],
        [InlineKeyboardButton("📊 My Info", callback_data="menu_myinfo")],
        [InlineKeyboardButton("👥 Refer", callback_data="menu_refer")],
    ])
    await message.reply("♨️ XENO PREMIUM BOT ♨️\n\n🔹Available Commands🔹", reply_markup=keyboard)

# Encrypt button callback
# Encrypt button callback
@app.on_callback_query(filters.regex("^menu_encrypt$") & restricted())
async def cb_encrypt(client, cb):
    print(f"[DEBUG] Encrypt callback triggered for user {cb.from_user.id}")  # Debug log
    await cb.answer("You selected Encrypt.")
    user_state[cb.from_user.id] = "encrypt"
    print(f"[DEBUG] User state updated: {user_state}")  # Debug log
    await cb.message.reply("📂 Send a `.py` or `.txt` file (max 10MB) to encrypt.")

# Decrypt button callback
@app.on_callback_query(filters.regex("^menu_decrypt$") & restricted())
async def cb_decrypt(client, cb):
    print(f"[DEBUG] Decrypt callback triggered for user {cb.from_user.id}")  # Debug log
    await cb.answer("You selected Decrypt.")
    user_state[cb.from_user.id] = "decrypt"
    print(f"[DEBUG] User state updated: {user_state}")  # Debug log
    await cb.message.reply("📂 Send the encrypted `.py` or `.txt` file to decrypt.")

# Encrypt command
@app.on_message(filters.command("encrypt") & filters.private & restricted())
async def encrypt_command(client, message):
    print(f"[DEBUG] Encrypt command received from user {message.from_user.id}")  # Debug log
    user_state[message.from_user.id] = "encrypt"
    await message.reply("📂 Send a `.py` or `.txt` file (max 10MB) to encrypt.")

# Decrypt command
@app.on_message(filters.command("decrypt") & filters.private & restricted())
async def decrypt_command(client, message):
    print(f"[DEBUG] Decrypt command received from user {message.from_user.id}")  # Debug log
    user_state[message.from_user.id] = "decrypt"
    await message.reply("📂 Send the encrypted `.py` or `.txt` file to decrypt.")

# File handler
@app.on_message(filters.document & filters.private)
async def handle_uploaded_file(client, message: Message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    print(f"[DEBUG] File received from user {user_id} with state {state}")  # Debug log
    if not state:
        return await message.reply("⚠️ Please choose encrypt or decrypt first using /menu.")

    if state == "encrypt":
        await encrypt_file(client, message)
    elif state == "decrypt":
        await decrypt_file(client, message)

# Encryption logic
async def encrypt_file(client, message):
    user_id = message.from_user.id
    print(f"[DEBUG] Encrypting file for user {user_id}")  # Debug log
    user_state.pop(user_id, None)

    doc = message.document
    file_name = doc.file_name

    if not (file_name.endswith(".py") or file_name.endswith(".txt")):
        return await message.reply("❌ Only `.py` or `.txt` files are allowed.")
    if doc.file_size > MAX_SIZE:
        return await message.reply("❌ File too large. Max size is 10MB.")

    progress = await message.reply("⏳ Downloading...")
    path = await client.download_media(message)
    await progress.edit("🔐 Encrypting...")

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        encoded = base64.b64encode(raw.encode()).decode()
        encrypted = f"import base64\nexec(base64.b64decode('{encoded}').decode('utf-8'))\n"
    except Exception as e:
        print(f"[DEBUG] Encryption failed for user {user_id}: {e}")  # Debug log
        await progress.edit(f"❌ Encryption failed: {e}")
        os.remove(path)
        return

    out_file = f"encrypted_{file_name}"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(encrypted)

    await client.send_document(message.chat.id, document=out_file, caption="✅ Encrypted file ready.")
    await progress.delete()
    os.remove(path)
    os.remove(out_file)

# Decryption logic
async def decrypt_file(client, message):
    user_id = message.from_user.id
    print(f"[DEBUG] Decrypting file for user {user_id}")  # Debug log
    user_state.pop(user_id, None)

    doc = message.document
    file_name = doc.file_name

    if not (file_name.endswith(".py") or file_name.endswith(".txt")):
        return await message.reply("❌ Only `.py` or `.txt` files are allowed.")
    if doc.file_size > MAX_SIZE:
        return await message.reply("❌ File too large. Max size is 10MB.")

    progress = await message.reply("⏳ Downloading...")
    path = await client.download_media(message)
    await progress.edit("🔓 Decrypting...")

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        match = re.search(r"base64\.b64decode\('(.+?)'\)", content)
        if not match:
            raise ValueError("Encrypted content not found.")
        decoded = base64.b64decode(match.group(1)).decode("utf-8")
    except Exception as e:
        print(f"[DEBUG] Decryption failed for user {user_id}: {e}")  # Debug log
        await progress.edit(f"❌ Decryption failed: {e}")
        os.remove(path)
        return

    out_file = f"decrypted_{file_name}"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(decoded)

    await client.send_document(message.chat.id, document=out_file, caption="✅ Decrypted file ready.")
    await progress.delete()
    os.remove(path)
    os.remove(out_file)

@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    now = datetime.now(timezone.utc)

    try:
        # Query keys redeemed by this user and not banned
        response = supabase.table("xeno_keys") \
            .select("expiry, banned") \
            .eq("redeemed_by", user_id) \
            .eq("banned", False) \
            .execute()

        rows = response.data
        print(f"[INFO] /start check for user {user_id}: found {len(rows)} keys")

        if rows:
            for row in rows:
                expiry = datetime.fromisoformat(row['expiry'].replace('Z', '+00:00'))
                if expiry > now:
                    await message.reply(
                        "✅ ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ʜᴀᴠᴇ ᴀᴄᴄᴇꜱꜱ ᴇɴᴛᴇʀ /menu ᴛᴏ ꜱᴇᴇ ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅꜱ"
                    )
                    return

    except Exception as e:
        print(f"[ERROR] Supabase /start access check failed for user {user_id}: {e}")
        await message.reply("❌ Error checking access. Please try again later.")
        return

    # No valid access
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 ʙᴜʏ ᴋᴇʏ", url="https://t.me/@xeeeenooo1")]
    ])
    await message.reply(
        "👋 ᴡᴇʟᴄᴏᴍᴇ ʏᴏᴜ ɴᴇᴇᴅ ᴀ ᴋᴇʏ ᴛᴏ ᴀᴄᴄᴇꜱꜱ ᴛʜᴇ ʙᴏᴛ",
        reply_markup=keyboard
    )
    
@app.on_message(filters.command("genkey") & filters.private & filters.user(ADMIN_ID))
async def manual_genkey_command(client, message):
    args = message.text.split()

    if len(args) != 2:
        return await message.reply("❌ Usage: `/genkey <duration>`\nExample: `/genkey 1d`, `/genkey 30m`, `/genkey 12h`", quote=True)

    duration_code = args[1]
    delta = parse_duration(duration_code)
    if delta.total_seconds() <= 0:
        return await message.reply("❌ Invalid duration format. Use `1d`, `12h`, or `30m`.", quote=True)

    try:
        key = "XENO-" + ''.join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=10))
        now = datetime.now(timezone.utc)
        expiry = now + delta

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
            f"✅ ɴᴇᴡ ᴋᴇʏ ɢᴇɴᴇʀᴀᴛᴇᴅ\n"
            f"━━━━━━━━━━━━\n"
            f"🔐 ᴋᴇʏ: `{key}`\n"
            f"⏳ ᴅᴜʀᴀᴛɪᴏɴ: `{duration_code}`\n"
            f"📅 ᴇxᴘɪʀᴇꜱ ᴏɴ: `{expiry}`\n\n"
            f"━━━━━━━━━━━━\n"
            f"🔑 ʜᴏᴡ ᴛᴏ ʀᴇᴅᴇᴇᴍ\n"
            f"1. ᴛʏᴘᴇ `/redeem`\n"
            f"2. ꜱᴇɴᴅ ᴛʜᴇ ᴋᴇʏ: `{key}`"
        )
    except Exception as e:
        print("[ERROR] Failed to insert key:", e)
        await message.reply("❌ Failed to generate key. Try again later.")

@app.on_message(filters.command("redeem") & filters.private)
async def redeem_command(client, message):
    args = message.text.split()
    if len(args) != 2:
        return await message.reply("❌ Usage: `/redeem <key>`\nExample: `/redeem XENO-ABC123XYZ9`", quote=True)

    input_key = args[1].strip().upper()
    user_id = message.from_user.id
    now = datetime.now(timezone.utc)

    try:
        response = supabase.table("xeno_keys") \
            .select("*") \
            .eq("key", input_key) \
            .execute()

        if not response.data:
            return await message.reply("❌ Invalid key.")

        key_data = response.data[0]

        if key_data["redeemed_by"]:
            return await message.reply("❌ This key has already been redeemed.")

        expiry = datetime.fromisoformat(key_data["expiry"].replace('Z', '+00:00'))
        if expiry < now:
            return await message.reply("❌ This key is expired.")

        supabase.table("xeno_keys").update({
            "redeemed_by": user_id
        }).eq("key", input_key).execute()

        await message.reply(
            f"✅ sᴜᴄᴄᴇssғᴜʟʟʏ ʀᴇᴅᴇᴇᴍᴇᴅ ᴋᴇʏ\n"
            f"🔐 ᴋᴇʏ: `{input_key}`\n"
            f"⏳ ᴇxᴘɪʀᴇꜱ: `{expiry}`\n\n"
            f"✅ ʏᴏᴜ ɴᴏᴡ ʜᴀᴠᴇ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss.\nᴛʏᴘᴇ /menu ᴛᴏ ᴠɪᴇᴡ ᴄᴏᴍᴍᴀɴᴅꜱ."
        )
    except Exception as e:
        print("[ERROR] Redeem failed:", e)
        await message.reply("❌ Something went wrong. Please try again.")
    
if __name__ == "__main__":
    app.run()

