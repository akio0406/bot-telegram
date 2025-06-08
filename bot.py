from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timezone
from supabase import create_client  # ✅ You were missing this
import os

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

app.run()
