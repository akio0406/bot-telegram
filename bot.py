import os
import re
import random
import base64
import asyncio
from datetime import datetime, timedelta, timezone

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

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

# /menu command — shows User Menu
@app.on_message(filters.command("menu") & filters.private)
async def show_command(client, message, edit=False, from_id=None):
    user_id = from_id or message.from_user.id
    if not await check_user_access(user_id):
        return await message.reply("⛔ ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ʀᴇᴅᴇᴇᴍ ᴀ ᴠᴀʟɪᴅ ᴋᴇʏ ꜰɪʀꜱᴛ.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 ᴇɴᴄʀʏᴘᴛ", callback_data="menu_encrypt")],
        [InlineKeyboardButton("🔓 ᴅᴇᴄʀʏᴘᴛ", callback_data="menu_decrypt")],
        [InlineKeyboardButton("🧹 ʀᴇᴍᴏᴠᴇ ᴜʀʟꜱ", callback_data="menu_removeurl")],
        [InlineKeyboardButton("🧹 ʀᴇᴍᴏᴠᴇ ᴅᴜᴘʟɪᴄᴀᴛᴇꜱ", callback_data="menu_removedupe")],
        [InlineKeyboardButton("📂 ᴍᴇʀɢᴇ ꜰɪʟᴇꜱ", callback_data="menu_merge")],
        [InlineKeyboardButton("📊 ᴄᴏᴜɴᴛ ʟɪɴᴇꜱ", callback_data="menu_countlines")],
        [InlineKeyboardButton("🔎 ɢᴇɴᴇʀᴀᴛᴇ", callback_data="gen_menu")],
        [InlineKeyboardButton("📌 ᴋᴇʏ ꜱᴛᴀᴛᴜꜱ", callback_data="menu_status")],
        [InlineKeyboardButton("🔍 ꜱᴇᴀʀᴄʜ", callback_data="menu_search")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ ᴛᴏ ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅꜱ", callback_data="admin_menu")]
    ])

    await message.reply(
        "♨️ ᙭EᑎO ᑭᖇEᗰIᑌᗰ ᗷOT ♨️\n\n🔹ᴀᴠᴀɪʟᴀʙʟᴇ ᴄᴏᴍᴍᴀɴᴅꜱ🔹",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^admin_menu$"))
async def show_admin_buttons(client, cb):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer("⛔ ᴀᴅᴍɪɴ ᴏɴʟʏ.", show_alert=True)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 ɢᴇɴᴇʀᴀᴛᴇ ᴋᴇʏ", callback_data="admin_genkey")],
        [InlineKeyboardButton("🗑 ᴅᴇʟᴇᴛᴇ ᴋᴇʏ", callback_data="admin_deletekey")],
        [InlineKeyboardButton("📆 ʀᴇᴍᴏᴠᴇ ᴇxᴘɪʀᴇᴅ ᴋᴇʏꜱ", callback_data="admin_remove_expired")],
        [InlineKeyboardButton("📊 ꜱʜᴏᴡ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ", callback_data="admin_stats")],
        [InlineKeyboardButton("⏳ ᴇxᴛᴇɴᴅ ᴋᴇʏ", callback_data="admin_extendkey")],
        [InlineKeyboardButton("🚫 ʙᴀɴ ᴜꜱᴇʀ", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ ᴜɴʙᴀɴ ᴜꜱᴇʀ", callback_data="admin_unban")],
        [InlineKeyboardButton("📋 ᴠɪᴇᴡ ʙᴀɴʟɪꜱᴛ", callback_data="admin_banlist")],
        [InlineKeyboardButton("🗑 ᴅᴇʟᴇᴛᴇ ᴀʟʟ ᴋᴇʏꜱ", callback_data="admin_deleteall")],
        [InlineKeyboardButton("🎁 ɢʀᴀɴᴛ ᴀᴄᴄᴇꜱꜱ", callback_data="admin_grant")],
        [InlineKeyboardButton("🔁 ᴛʀᴀɴꜱꜰᴇʀ ᴋᴇʏ", callback_data="admin_transfer")],
        [InlineKeyboardButton("📢 ꜱᴇɴᴅ ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛ", callback_data="admin_announce")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ ᴛᴏ ᴜꜱᴇʀ ᴍᴇɴᴜ", callback_data="user_menu")]
    ])

    await cb.message.edit_text(
        "👑 **ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ** 👑\n\nᴘʟᴇᴀꜱᴇ ᴄʜᴏᴏꜱᴇ ᴀɴ ᴀᴄᴛɪᴏɴ ʙᴇʟᴏᴡ:",
        reply_markup=keyboard
    )

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

def restricted():
    async def decorator_filter(client, update, _=None):
        # Determine user ID based on update type
        if isinstance(update, Message):
            user_id = update.from_user.id
        elif isinstance(update, CallbackQuery):
            user_id = update.from_user.id
        else:
            return False  # Unknown type or no user

        def query():
            res = supabase.from_("xeno_keys") \
                .select("banned") \
                .eq("redeemed_by", user_id) \
                .eq("banned", False) \
                .limit(1) \
                .execute()
            return res.data if hasattr(res, "data") else res.get("data")

        data = await asyncio.to_thread(query)
        return bool(data)

    return filters.create(decorator_filter)
    
user_state = {}
MAX_SIZE = 10485760  # example max size in bytes (10 MB)

@app.on_message(filters.command("encrypt") & filters.private & restricted())
async def encrypt_command(client, message):
    user_state[message.from_user.id] = "encrypt"
    await message.reply("📂 ꜱᴇɴᴅ ᴀ `.py` ᴏʀ `.txt` ꜰɪʟᴇ (ᴍᴀx 10ᴍʙ) ᴛᴏ ᴇɴᴄʀʏᴘᴛ.")

@app.on_message(filters.command("decrypt") & filters.private & restricted())
async def decrypt_command(client, message):
    user_state[message.from_user.id] = "decrypt"
    await message.reply("📂 ꜱᴇɴᴅ ᴀ `.py` ᴏʀ `.txt` ꜰɪʟᴇ ᴛʜᴀᴛ ᴡᴀꜱ ᴇɴᴄʀʏᴘᴛᴇᴅ ᴛᴏ ᴅᴇᴄʀʏᴘᴛ ɪᴛ.")

@app.on_callback_query(filters.regex("^menu_encrypt$") & restricted())
async def cb_encrypt(client, cb):
    if not check_user_access(cb.from_user.id):
        return await cb.answer("⛔ ɴᴏ ᴀᴄᴄᴇꜱꜱ. ᴘʟᴇᴀꜱᴇ ʀᴇᴅᴇᴇᴍ ᴀ ᴋᴇʏ.", show_alert=True)
    user_state[cb.from_user.id] = "encrypt"
    await cb.message.reply("📂 ꜱᴇɴᴅ ᴀ .py ᴏʀ .txt ꜰɪʟᴇ ᴛᴏ ᴇɴᴄʀʏᴘᴛ.")

@app.on_callback_query(filters.regex("^menu_decrypt$") & restricted())
async def cb_decrypt(client, cb):
    if not check_user_access(cb.from_user.id):
        return await cb.answer("⛔ ɴᴏ ᴀᴄᴄᴇꜱꜱ. ᴘʟᴇᴀꜱᴇ ʀᴇᴅᴇᴇᴍ ᴀ ᴋᴇʏ.", show_alert=True)
    user_state[cb.from_user.id] = "decrypt"
    await cb.message.reply("📂 ꜱᴇɴᴅ ᴛʜᴇ ᴇɴᴄʀʏᴘᴛᴇᴅ .py ᴏʀ .txt ꜰɪʟᴇ ᴛᴏ ᴅᴇᴄʀʏᴘᴛ.")

@app.on_message(filters.document)
async def handle_uploaded_file(client, message: Message):
    user_id = message.from_user.id
    state = user_state.get(user_id)

    if state == "encrypt":
        await encrypt_file(client, message)
    elif state == "decrypt":
        await decrypt_file(client, message)

async def encrypt_file(client, message):
    user_id = message.from_user.id
    user_state.pop(user_id, None)

    doc = message.document
    file_name = doc.file_name
    if not (file_name.endswith(".py") or file_name.endswith(".txt")):
        return await message.reply("❌ ᴏɴʟʏ `.py` ᴏʀ `.txt` ꜰɪʟᴇꜱ ᴀʀᴇ ᴀʟʟᴏᴡᴇᴅ.")
    if doc.file_size > MAX_SIZE:
        return await message.reply("❌ ꜰɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ. ᴍᴀx ꜱɪᴢᴇ ɪꜱ 10ᴍʙ.")

    progress = await message.reply("⏳ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...")
    path = await client.download_media(message)
    await progress.edit("🔐 ᴇɴᴄʀʏᴘᴛɪɴɢ...")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    encoded = base64.b64encode(raw.encode()).decode()
    encrypted = f"import base64\nexec(base64.b64decode('{encoded}').decode('utf-8'))\n"

    out_file = f"ᴇɴᴄʀʏᴘᴛᴇᴅ_{file_name}"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(encrypted)

    await client.send_document(message.chat.id, document=out_file, caption="✅ ᴇɴᴄʀʏᴘᴛᴇᴅ ꜰɪʟᴇ ʀᴇᴀᴅʏ.")
    await progress.delete()
    os.remove(path)
    os.remove(out_file)

async def decrypt_file(client, message):
    user_id = message.from_user.id
    user_state.pop(user_id, None)

    doc = message.document
    file_name = doc.file_name
    if not (file_name.endswith(".py") or file_name.endswith(".txt")):
        return await message.reply("❌ ᴏɴʟʏ `.py` ᴏʀ `.txt` ꜰɪʟᴇꜱ ᴀʀᴇ ᴀʟʟᴏᴡᴇᴅ.")
    if doc.file_size > MAX_SIZE:
        return await message.reply("❌ ꜰɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ. ᴍᴀx ꜱɪᴢᴇ ɪꜱ 10ᴍʙ.")

    progress = await message.reply("⏳ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...")
    path = await client.download_media(message)
    await progress.edit("🔓 ᴅᴇᴄʀʏᴘᴛɪɴɢ...")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    match = re.search(r"base64\.b64decode\('(.+?)'\)", content)
    if not match:
        os.remove(path)
        return await progress.edit("❌ ᴇɴᴄʀʏᴘᴛᴇᴅ ᴄᴏɴᴛᴇɴᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ.")

    try:
        decoded = base64.b64decode(match.group(1)).decode("utf-8")
    except Exception as e:
        os.remove(path)
        return await progress.edit(f"❌ ᴅᴇᴄʀʏᴘᴛɪᴏɴ ꜰᴀɪʟᴇᴅ: {e}")

    out_file = f"ᴅᴇᴄʀʏᴘᴛᴇᴅ_{file_name}"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(decoded)

    await client.send_document(message.chat.id, document=out_file, caption="✅ ᴅᴇᴄʀʏᴘᴛᴇᴅ ꜰɪʟᴇ ɪꜱ ʀᴇᴀᴅʏ.")
    await progress.delete()
    os.remove(path)
    os.remove(out_file)
    
app.run()
