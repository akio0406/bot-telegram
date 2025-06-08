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

app.run()
