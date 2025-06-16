#!/usr/bin/env python3
import os
import sys
import re
import random
import base64
import asyncio
import functools

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo         # Python 3.9+
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
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

admin_state: dict[int, str] = {}
# — Constants & State —
MAX_SIZE   = 10 * 1024 * 1024  # 10MB
user_state = {}                # user_id → "encrypt" or "decrypt"

# at the top of your file
def requires_premium(func):
    @functools.wraps(func)
    async def wrapper(client, update):
        # figure out the user & how to reply
        if isinstance(update, Message):
            uid = update.from_user.id
            deny = lambda: update.reply("⛔ Redeem a key first with `/redeem <key>`.") 
        elif isinstance(update, CallbackQuery):
            uid = update.from_user.id
            deny = lambda: update.answer("⛔ Redeem a key first with `/redeem <key>`.", show_alert=True)
        else:
            # shouldn’t happen
            return

        # do the access check
        if not await check_user_access(uid):
            return await deny()

        # user is premium, run the real handler
        return await func(client, update)

    return wrapper

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

# — /menu command —
@app.on_message(filters.command("menu") & filters.private)
@requires_premium
async def menu_cmd(_, m: Message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Encrypt", callback_data="menu_encrypt"),
         InlineKeyboardButton("🔓 Decrypt", callback_data="menu_decrypt")],
        [InlineKeyboardButton("🔍 Search", callback_data="menu_search"),
         InlineKeyboardButton("➖ Remove URLs", callback_data="menu_removeurl"),
         InlineKeyboardButton("➗ Remove Dupe", callback_data="menu_removedupe"),
         InlineKeyboardButton("🔗 Merge Files", callback_data="menu_merge")],
        [InlineKeyboardButton("🆔 My Info", callback_data="menu_myinfo")]
    ])
    await m.reply("♨️ XENO PREMIUM BOT ♨️\nChoose an action:", reply_markup=kb)

# — Callback button handlers —
@app.on_callback_query(filters.regex("^menu_encrypt$"))
@requires_premium
async def on_encrypt_cb(_, cq: CallbackQuery):
    await cq.answer("Encrypt mode activated!")
    await cq.message.edit_reply_markup(None)
    user_state[cq.from_user.id] = "encrypt"
    await cq.message.reply("📂 Send a `.py` or `.txt` file (max 10MB) to encrypt.")

@app.on_callback_query(filters.regex("^menu_decrypt$"))
@requires_premium
async def on_decrypt_cb(_, cq: CallbackQuery):
    await cq.answer("Decrypt mode activated!")
    await cq.message.edit_reply_markup(None)
    user_state[cq.from_user.id] = "decrypt"
    await cq.message.reply("📂 Send an encrypted `.py` or `.txt` file to decrypt.")

@app.on_callback_query(filters.regex("^menu_search$"))
@requires_premium
async def on_search_cb(_, cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_reply_markup(None)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Roblox", callback_data="keyword_roblox")],
        [InlineKeyboardButton("🔥 Mobile Legends", callback_data="keyword_mobilelegends")],
        [InlineKeyboardButton("💳 Codashop", callback_data="keyword_codashop")],
        [InlineKeyboardButton("🛡 Garena", callback_data="expand_garena")],
        [InlineKeyboardButton("🌐 Social Media", callback_data="expand_socmeds")],
        [InlineKeyboardButton("✉️ Email Prov", callback_data="expand_emails")],
        [InlineKeyboardButton("🎮 Gaming", callback_data="expand_gaming")],
    ])
    await cq.message.reply("🔎 DATABASE SEARCH\n\n📌 Choose a keyword:", reply_markup=kb)

@app.on_callback_query(filters.regex("^menu_removeurl$"))
@requires_premium
async def on_removeurl_cb(_, cq: CallbackQuery):
    await cq.answer("Remove-URLs mode activated!")
    await cq.message.edit_reply_markup(None)
    user_state[cq.from_user.id] = "removeurl"
    await cq.message.reply("📂 Send a file containing URLs to remove.")

@app.on_callback_query(filters.regex("^menu_merge$"))
@requires_premium
async def on_merge_cb(_, cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_reply_markup(None)
    user_state[cq.from_user.id] = "merge"
    await cq.message.reply(
        "📂 Send multiple `.txt` files. I'll merge them without duplicates. "
        "When done, type `/done`."
    )

@app.on_callback_query(filters.regex("^menu_removedupe$"))
@requires_premium
async def on_removedupe_cb(_, cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_reply_markup(None)
    user_state[cq.from_user.id] = "removedupe"
    await cq.message.reply("📂 Send a `.txt` file—I'll strip duplicate lines!")

@app.on_callback_query(filters.regex("^menu_myinfo$"))
@requires_premium
async def on_myinfo_cb(_, cq: CallbackQuery):
    await cq.answer()
    uid = cq.from_user.id
    resp = supabase.table("xeno_keys") \
        .select("key, expiry") \
        .eq("redeemed_by", uid).eq("banned", False) \
        .limit(1).execute()
    rows = resp.data or []
    if not rows:
        return await cq.answer("❌ You haven’t redeemed a key yet.", show_alert=True)

    info = rows[0]
    expiry_utc = datetime.fromisoformat(info["expiry"].replace("Z","+00:00"))
    now_utc    = datetime.now(timezone.utc)
    manila     = ZoneInfo("Asia/Manila")
    expiry_ph  = expiry_utc.astimezone(manila)

    secs = int((expiry_utc - now_utc).total_seconds())
    days, rem  = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _    = divmod(rem, 60)
    dur = days and f"{days}d {hours}h {mins}m" or hours and f"{hours}h {mins}m" or f"{mins}m"

    text = (
        f"🆔 Your Key: {info['key']}\n"
        f"📅 Expires on (PH): {expiry_ph:%Y-%m-%d %H:%M:%S}\n"
        f"⏳ Time left: {dur}"
    )
    await cq.message.edit_text(text)

# — Unified file handler —
@app.on_message(filters.document & filters.private)
@requires_premium
async def file_handler(bot: Client, m: Message):
    uid  = m.from_user.id
    mode = user_state.get(uid)
    if not mode:
        return await m.reply("⚠️ First choose action via /menu.")

    if mode == "encrypt":
        await do_encrypt(bot, m);   user_state.pop(uid, None)
    elif mode == "decrypt":
        await do_decrypt(bot, m);   user_state.pop(uid, None)
    elif mode == "removeurl":
        await process_removeurl_file(bot, m); user_state.pop(uid, None)
    elif mode == "removedupe":
        await process_remove_dupe_file(bot, m); user_state.pop(uid, None)
    elif mode == "merge":
        await handle_merge_file(bot, m)

# — File operation helpers —
async def do_encrypt(bot, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only .py/.txt allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large.")
    prog = await m.reply("⏳ Downloading…")
    path = await bot.download_media(m)
    await prog.edit("🔐 Encrypting…")
    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        b64 = base64.b64encode(raw.encode()).decode()
        out_fn = f"encrypted_{doc.file_name}"
        with open(out_fn, "w", encoding="utf-8") as f:
            f.write(f"import base64\nexec(base64.b64decode('{b64}').decode())")
        await bot.send_document(m.chat.id, out_fn, caption="✅ Encrypted!")
    except Exception as e:
        await prog.edit(f"❌ Encryption error: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(out_fn): os.remove(out_fn)

async def do_decrypt(bot, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only .py/.txt allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large.")
    prog = await m.reply("⏳ Downloading…")
    path = await bot.download_media(m)
    await prog.edit("🔓 Decrypting…")
    try:
        content = open(path, "r", encoding="utf-8", errors="ignore").read()
        mobj = re.search(r"b64decode\('(.+?)'\)", content)
        if not mobj: raise ValueError("No payload.")
        dec = base64.b64decode(mobj.group(1)).decode()
        out_fn = f"decrypted_{doc.file_name}"
        with open(out_fn, "w", encoding="utf-8") as f: f.write(dec)
        await bot.send_document(m.chat.id, out_fn, caption="✅ Decrypted!")
    except Exception as e:
        await prog.edit(f"❌ Decryption error: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(out_fn): os.remove(out_fn)

async def process_removeurl_file(bot, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".txt", ".py")):
        return await m.reply("❌ Only .txt/.py allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large.")
    prog = await m.reply("⏳ Downloading…")
    path = await bot.download_media(m)
    await prog.edit("➖ Removing prefixes…")
    cleaned = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.rstrip("\n").split(":")
            if len(parts) >= 2:
                cleaned.append(":".join(parts[-2:]))
    out_fn = f"removed_url_of_{doc.file_name}"
    with open(out_fn, "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned))
    await bot.send_document(m.chat.id, out_fn, caption="✅ URLs stripped—user:pass only.")
    await prog.delete()
    os.remove(path); os.remove(out_fn)

async def process_remove_dupe_file(bot: Client, m: Message):
    file = m.document
    if not file.file_name.lower().endswith(".txt"):
        return await m.reply("❌ Only `.txt` supported.")
    if file.file_size > MAX_SIZE:
        return await m.reply("❌ File too large.")

    prog = await m.reply("⏳ Downloading…")
    path = await bot.download_media(m)
    await prog.edit("♻️ Removing duplicates…")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]

    seen = set()
    unique = []
    for l in lines:
        if l not in seen:
            seen.add(l)
            unique.append(l)

    if len(unique) == len(lines):
        await prog.edit("✅ No duplicates found.")
        os.remove(path)
        return

    out_fn = f"no_dupes_{file.file_name}"
    with open(out_fn, "w", encoding="utf-8") as f:
        f.write("\n".join(unique))

    await bot.send_document(m.chat.id, out_fn, caption="✅ Duplicates removed!")
    # cleanup
    await prog.delete()
    os.remove(path)
    os.remove(out_fn)

merge_sessions: dict[int, set[str]] = {}

async def handle_merge_file(bot, m: Message):
    uid = m.from_user.id
    if user_state.get(uid) != "merge": return
    doc = m.document
    if not doc.file_name.lower().endswith(".txt"):
        return await m.reply("❌ Only `.txt` allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large.")
    path = await bot.download_media(m)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = {ln.strip() for ln in f if ln.strip()}
    os.remove(path)
    session = merge_sessions.setdefault(uid, set())
    session.update(lines)
    await m.reply(f"✅ Added! Total unique lines: {len(session)}.\nSend more or `/done`.")

@app.on_message(filters.command("done") & filters.private)
@requires_premium
async def finish_merge(_, m: Message):
    uid     = m.from_user.id
    session = merge_sessions.pop(uid, None)
    user_state.pop(uid, None)
    if not session:
        return await m.reply("⚠️ No merge in progress—use `/menu` first.")
    out_fn = "merged_results.txt"
    with open(out_fn, "w", encoding="utf-8") as f:
        f.write("\n".join(session))
    await _.send_document(m.chat.id, out_fn, caption="✅ Here’s your merged file!")
    os.remove(out_fn)

# — Search submenus —
@app.on_callback_query(filters.regex("^expand_garena$"))
async def expand_garena(_, cq: CallbackQuery):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Garena.com",      callback_data="keyword_garena.com")],
        [InlineKeyboardButton("🔐 100082",          callback_data="keyword_100082")],
        [InlineKeyboardButton("🔐 100055",          callback_data="keyword_100055")],
        [InlineKeyboardButton("🛡 Authgop",          callback_data="keyword_authgop.garena.com")],
        [InlineKeyboardButton("🔐 Gaslite",          callback_data="keyword_gaslite")],
        [InlineKeyboardButton("🔙 Back",             callback_data="back_to_main")],
    ])
    await cq.message.edit_text("🛡 GARENA SUB-KEYWORDS:", reply_markup=kb)

@app.on_callback_query(filters.regex("^expand_socmeds$"))
async def expand_socmeds(_, cq: CallbackQuery):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Facebook",         callback_data="keyword_facebook.com")],
        [InlineKeyboardButton("📸 Instagram",        callback_data="keyword_instagram.com")],
        [InlineKeyboardButton("📱 WhatsApp",         callback_data="keyword_whatsapp.com")],
        [InlineKeyboardButton("🐦 Twitter",          callback_data="keyword_twitter.com")],
        [InlineKeyboardButton("💬 Discord",          callback_data="keyword_discord.com")],
        [InlineKeyboardButton("🔙 Back",             callback_data="back_to_main")],
    ])
    await cq.message.edit_text("🌐 SOCIAL MEDIA OPTIONS:", reply_markup=kb)

@app.on_callback_query(filters.regex("^expand_emails$"))
async def expand_emails(_, cq: CallbackQuery):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📧 Gmail",            callback_data="keyword_google.com")],
        [InlineKeyboardButton("📧 Yahoo",            callback_data="keyword_yahoo.com")],
        [InlineKeyboardButton("📧 Outlook",          callback_data="keyword_outlook.com")],
        [InlineKeyboardButton("🔙 Back",             callback_data="back_to_main")],
    ])
    await cq.message.edit_text("✉️ EMAIL PROVIDERS:", reply_markup=kb)

@app.on_callback_query(filters.regex("^expand_gaming$"))
async def expand_gaming(_, cq: CallbackQuery):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Riot",            callback_data="keyword_riotgames.com")],
        [InlineKeyboardButton("🎮 Battle.net",       callback_data="keyword_battle.net")],
        [InlineKeyboardButton("🎮 Minecraft",        callback_data="keyword_minecraft.net")],
        [InlineKeyboardButton("🎮 Supercell",        callback_data="keyword_supercell.com")],
        [InlineKeyboardButton("🎮 Wargaming",        callback_data="keyword_wargaming.net")],        
        [InlineKeyboardButton("🔙 Back",             callback_data="back_to_main")],
    ])
    await cq.message.edit_text("🎮 GAMING OPTIONS:", reply_markup=kb)

@app.on_callback_query(filters.regex("^back_to_main$"))
async def back_to_main(_, cq: CallbackQuery):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Roblox",          callback_data="keyword_roblox")],
        [InlineKeyboardButton("🔥 Mobile Legends",  callback_data="keyword_mobilelegends")],
        [InlineKeyboardButton("💳 Codashop",         callback_data="keyword_codashop")],
        [InlineKeyboardButton("🛡 Garena",           callback_data="expand_garena")],
        [InlineKeyboardButton("🌐 Social Media",     callback_data="expand_socmeds")],
        [InlineKeyboardButton("✉️ Email Providers", callback_data="expand_emails")],
        [InlineKeyboardButton("🎮 Gaming",           callback_data="expand_gaming")],
    ])
    await cq.message.edit_text("🔎 DATABASE SEARCH\n\n📌 Choose a keyword:", reply_markup=kb)

@app.on_callback_query(filters.regex("^keyword_"))
async def ask_format(_, cq: CallbackQuery):
    keyword = cq.data.split("_",1)[1]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ User:Pass only", callback_data=f"format_{keyword}_userpass")],
        [InlineKeyboardButton("🌍 Include URLs",    callback_data=f"format_{keyword}_full")],
    ])
    await cq.message.edit_text(
        f"🔎 Keyword: `{keyword}`\nChoose output format:", reply_markup=kb
    )

@app.on_callback_query(filters.regex("^format_"))
async def perform_search(_, cq: CallbackQuery):
    _, keyword, fmt = cq.data.split("_",2)
    include_urls = (fmt == "full")
    await cq.answer("⏳ Searching…")
    resp = supabase.from_("xeno").select("line").ilike("line", f"%{keyword}%").execute()
    rows = resp.data or []
    if not rows:
        return await cq.message.edit_text("❌ No matches found.")
    all_lines = [r["line"] for r in rows]
    count     = min(len(all_lines), random.randint(100,110))
    selected  = random.sample(all_lines, count)
    # optional dedupe tracking
    used_file = "no_dupes.txt"
    used = set(open(used_file).read().splitlines()) if os.path.exists(used_file) else set()
    with open(used_file, "a") as f:
        for L in selected:
            if L not in used:
                f.write(L + "\n")
    # write results
    os.makedirs("Generated", exist_ok=True)
    result_path = f"Generated/premium_{keyword}.txt"
    with open(result_path, "w", encoding="utf-8") as f:
        for L in selected:
            if include_urls:
                f.write(L + "\n")
            else:
                parts = L.split(":")
                f.write(":".join(parts[-2:]) + "\n")
    # preview
    preview = selected[:5]
    if not include_urls:
        preview = [":".join(l.split(":")[-2:]) for l in preview]
    preview_text = "\n".join(preview) + ("\n..." if len(selected)>5 else "")
    label = "🌍 Full (URLs)" if include_urls else "✅ User:Pass"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download Results",
            callback_data=f"download_results_{os.path.basename(result_path)}_{keyword}")],
        [InlineKeyboardButton("📋 Copy Code",
            callback_data=f"copy_code_{os.path.basename(result_path)}_{keyword}")],
    ])
    await cq.message.edit_text(
        f"🔎 PREMIUM `{keyword}`\n📄 Format: {label}\n📌 Matches: `{len(selected)}`\n\n"
        f"🔹 Preview:\n```\n{preview_text}\n```", reply_markup=kb
    )

@app.on_callback_query(filters.regex("^copy_code_"))
async def copy_results_text(_, cq: CallbackQuery):
    # strip off the "copy_code_" prefix, then split once at the final "_"
    payload = cq.data[len("copy_code_"):]
    filename, keyword = payload.rsplit("_", 1)

    path = f"Generated/{filename}"
    if os.path.exists(path):
        content = open(path, "r", encoding="utf-8").read()
        if len(content) > 4096:
            content = content[:4090] + "...\n[Truncated]"
        await cq.message.reply(
            f"<b>Results for:</b> <code>{keyword}</code>\n<pre>{content}</pre>",
            parse_mode="HTML"
        )
        os.remove(path)

    # remove the inline‐keyboard
    await cq.message.delete()

@app.on_callback_query(filters.regex("^download_results_"))
async def download_results_file(_, cq: CallbackQuery):
    # strip off the "download_results_" prefix, then split once at the final "_"
    payload = cq.data[len("download_results_"):]
    filename, keyword = payload.rsplit("_", 1)

    path = f"Generated/{filename}"
    if os.path.exists(path):
        await cq.message.reply_document(
            document=path,
            caption=f"📄 PREMIUM results for `{keyword}`"
        )
        os.remove(path)

    # remove the inline‐keyboard
    await cq.message.delete()

# — /redeem (enforce one-key-per-user) —
@app.on_message(filters.command("redeem") & filters.private)
async def redeem_cmd(_, m: Message):
    parts = m.text.strip().split()
    if len(parts) != 2:
        return await m.reply(
            "❌ Usage: /redeem KEY\n"
            "Example: /redeem XENO-ABCDEFG1234",
            quote=True
        )

    uid = m.from_user.id
    now = datetime.now(timezone.utc)

    # 1) prevent multiple active keys
    resp0 = supabase.table("xeno_keys") \
        .select("expiry") \
        .eq("redeemed_by", uid) \
        .eq("banned", False) \
        .execute()

    for row in (resp0.data or []):
        exp = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
        if exp > now:
            return await m.reply(
                "❌ You already have an active key.",
                quote=True
            )

    # 2) redeem the requested key
    key = parts[1].upper()
    try:
        resp = supabase.table("xeno_keys") \
            .select("*") \
            .eq("key", key) \
            .execute()

        if not resp.data:
            return await m.reply("❌ Invalid key.", quote=True)

        row = resp.data[0]
        if row.get("redeemed_by"):
            return await m.reply("❌ That key is already redeemed.", quote=True)

        exp = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
        if exp < now:
            return await m.reply("❌ Key expired.", quote=True)

        supabase.table("xeno_keys") \
            .update({"redeemed_by": uid}) \
            .eq("key", key) \
            .execute()

        await m.reply(
            f"✅ Redeemed! Your key is valid until {exp}.",
            quote=True
        )

    except Exception as e:
        print(f"[ERROR] redeem failed: {e}")
        await m.reply("❌ Something went wrong. Try again later.", quote=True)


# at top of file, add this import
from pyrogram.errors import MessageNotModified

# in‐memory admin flow state
admin_state: dict[int, str] = {}

# helper to start a flow: clears buttons (safely), sets state, sends prompt
async def start_flow(cq: CallbackQuery, flow: str, prompt: str):
    await cq.answer()
    try:
        await cq.message.edit_reply_markup(None)
    except MessageNotModified:
        # already had no buttons, ignore
        pass
    admin_state[cq.from_user.id] = flow
    await cq.message.reply(prompt)

# ─── at top ───
KEYWORDS = [
    "100082", "100055", "gaslite", "garena",
    "authgop", "roblox", "codashop", "mtacc",
    "facebook.com","instagram.com","whatsapp.com",
    "twitter.com","discord.com",
    "google.com","yahoo.com","outlook.com",
    "riotgames.com","battle.net","minecraft.net",
    "supercell.com","wargaming.net"
]

# ─── extend your admin menu ───
@app.on_message(filters.command("adminmenu") & filters.private & filters.user(ADMIN_ID))
async def adminmenu_cmd(_, m: Message):
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Generate Key",   callback_data="admin_genkey"),
            InlineKeyboardButton("❌ Remove Key",     callback_data="admin_removekey"),
        ],
        [
            InlineKeyboardButton("⌛ Remove Expired", callback_data="admin_remove_expired"),
            InlineKeyboardButton("🗓 Extend Key",     callback_data="admin_extend_key"),
        ],
        [
            InlineKeyboardButton("⛔ Ban User",       callback_data="admin_ban_user"),
            InlineKeyboardButton("✔️ Unban User",     callback_data="admin_unban_user"),
            InlineKeyboardButton("📋 Show Banlist",   callback_data="admin_show_banlist"),
            InlineKeyboardButton("📈 Show Stats",     callback_data="admin_show_stats"),
        ],
        # ← NEW LINE
        [
            InlineKeyboardButton("🔎 Check total lines", callback_data="admin_check_lines"),
        ],
    ])
    await m.reply("🛠 Admin Menu – choose an action:", reply_markup=kb)


# Generate Key →
@app.on_callback_query(filters.regex("^admin_genkey$") & filters.user(ADMIN_ID))
async def admin_genkey_cb(_, cq: CallbackQuery):
    await start_flow(cq, "await_duration",
        "🛠 Enter duration for the new key (e.g. 1d, 12h, 30m):"
    )


# Remove Key →
@app.on_callback_query(filters.regex("^admin_removekey$") & filters.user(ADMIN_ID))
async def admin_removekey_cb(_, cq: CallbackQuery):
    await start_flow(cq, "await_remove_key",
        "🛠 Send the exact key to remove (e.g. XENO-ABCDEFG1234):"
    )


# Remove Expired →
@app.on_callback_query(filters.regex("^admin_remove_expired$") & filters.user(ADMIN_ID))
async def admin_remove_expired_cb(_, cq: CallbackQuery):
    await cq.answer()
    # buttons were already cleared in start_flow, but remove here too in case
    try:
        await cq.message.edit_reply_markup(None)
    except MessageNotModified:
        pass

    now     = datetime.now(timezone.utc)
    removed = 0
    for row in (supabase.table("xeno_keys")
                     .select("key, expiry")
                     .execute().data or []):
        exp = datetime.fromisoformat(row["expiry"].replace("Z", "+00:00"))
        if exp < now:
            supabase.table("xeno_keys") \
                .delete() \
                .eq("key", row["key"]) \
                .execute()
            removed += 1

    await cq.message.reply(f"✅ Removed {removed} expired key(s).")


# Extend Key →
@app.on_callback_query(filters.regex("^admin_extend_key$") & filters.user(ADMIN_ID))
async def admin_extend_key_cb(_, cq: CallbackQuery):
    await start_flow(cq, "await_extend_key",
        "🗓 Send `<KEY> <DURATION>`\nExample: XENO-ABCDEFG1234 1d"
    )


# Ban User →
@app.on_callback_query(filters.regex("^admin_ban_user$") & filters.user(ADMIN_ID))
async def admin_ban_user_cb(_, cq: CallbackQuery):
    await start_flow(cq, "await_ban_user",
        "⛔ Send the Telegram user_id to ban (marks all their keys):"
    )


# Unban User →
@app.on_callback_query(filters.regex("^admin_unban_user$") & filters.user(ADMIN_ID))
async def admin_unban_user_cb(_, cq: CallbackQuery):
    await start_flow(cq, "await_unban_user",
        "✔️ Send the Telegram user_id to unban (clears banned flag):"
    )


# Show Banlist →
@app.on_callback_query(filters.regex("^admin_show_banlist$") & filters.user(ADMIN_ID))
async def admin_show_banlist_cb(_, cq: CallbackQuery):
    await cq.answer()
    try:
        await cq.message.edit_reply_markup(None)
    except MessageNotModified:
        pass

    resp = supabase.table("xeno_keys") \
        .select("redeemed_by") \
        .eq("banned", True) \
        .execute()

    users = sorted({r["redeemed_by"] for r in (resp.data or []) if r["redeemed_by"]})
    if not users:
        await cq.message.reply("✅ No users are currently banned.")
    else:
        lines = "\n".join(f"- `{uid}`" for uid in users)
        await cq.message.reply(f"🚫 Banned users:\n{lines}")

# ─── handler for “Check total lines” ───
@app.on_callback_query(filters.regex("^admin_check_lines$") & filters.user(ADMIN_ID))
async def admin_check_lines_cb(_, cq: CallbackQuery):
    await cq.answer()  # remove spinner
    try:
        # 1) gather counts
        counts = {}
        for kw in KEYWORDS:
            res = (
                supabase
                .table("entries")
                .select("id", count="exact")
                .ilike("line", f"%{kw}%")
                .execute()
            )
            counts[kw] = res.count or 0

        # 2) build a two-column box
        headers = ["Keyword", "Lines"]
        rows = [[kw, str(counts[kw])] for kw in KEYWORDS]

        # compute column widths
        cols = [headers] + rows
        w0 = max(len(r[0]) for r in cols)
        w1 = max(len(r[1]) for r in cols)

        top = f"╔{'═'*(w0+2)}╤{'═'*(w1+2)}╗"
        hdr = f"║ {headers[0].ljust(w0)} │ {headers[1].rjust(w1)} ║"
        sep = f"╠{'═'*(w0+2)}╪{'═'*(w1+2)}╣"
        body = "\n".join(
            f"║ {kw.ljust(w0)} │ {lines.rjust(w1)} ║"
            for kw, lines in rows
        )
        bot = f"╚{'═'*(w0+2)}╧{'═'*(w1+2)}╝"

        table = "\n".join([top, hdr, sep, body, bot])
        await cq.message.reply(f"🔍 TOTAL LINES STATUS:\n{table}")

    except Exception as e:
        await cq.message.reply(f"❌ Error checking lines:\n{e}")
        
# — single text-handler for all multi-step flows —
@app.on_message(filters.text & filters.private & filters.user(ADMIN_ID))
async def admin_flow_handler(_, m: Message):
    flow = admin_state.get(m.from_user.id)

    # 1) Generate Key
    if flow == "await_duration":
        code  = m.text.strip()
        delta = parse_duration(code)
        if delta.total_seconds() <= 0:
            return await m.reply("❌ Invalid duration. Enter 1d, 12h, or 30m.", quote=True)

        key    = "XENO-" + "".join(random.choices(
                     "ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=10))
        now    = datetime.now(timezone.utc)
        expiry = now + delta

        supabase.table("xeno_keys").insert({
            "key":         key,
            "expiry":      expiry.isoformat(),
            "redeemed_by": None,
            "owner_id":    ADMIN_ID,
            "created":     now.isoformat(),
            "duration":    code,
            "banned":      False
        }).execute()

        await m.reply(
            f"✅ Generated Key: {key}\n"
            f"Expires at: {expiry}\n"
            f"Redeem with: /redeem {key}",
            quote=True
        )

    # 2) Remove Key
    elif flow == "await_remove_key":
        key = m.text.strip().upper()
        resp = supabase.table("xeno_keys").select("key").eq("key", key).execute()
        if not resp.data:
            return await m.reply("❌ No such key found.", quote=True)
        supabase.table("xeno_keys").delete().eq("key", key).execute()
        await m.reply(f"✅ Key {key} removed.", quote=True)

    # 3) Extend Key
    elif flow == "await_extend_key":
        parts = m.text.strip().split(maxsplit=1)
        if len(parts) != 2:
            return await m.reply("❌ Usage: KEY DURATION\nExample: XENO-ABC123 1d", quote=True)
        key_str, dur = parts[0].upper(), parts[1]
        delta = parse_duration(dur)
        if delta.total_seconds() <= 0:
            return await m.reply("❌ Invalid duration. Enter 1d, 12h, or 30m.", quote=True)

        resp = supabase.table("xeno_keys").select("expiry").eq("key", key_str).execute()
        if not resp.data:
            return await m.reply("❌ Key not found.", quote=True)

        old_exp = datetime.fromisoformat(resp.data[0]["expiry"].replace("Z","+00:00"))
        new_exp = old_exp + delta
        supabase.table("xeno_keys") \
            .update({"expiry": new_exp.isoformat()}) \
            .eq("key", key_str).execute()

        await m.reply(
            f"✅ Extended {key_str} by {dur}\n"
            f"Old expiry: {old_exp}\n"
            f"New expiry: {new_exp}",
            quote=True
        )

    # 4) Ban User
    elif flow == "await_ban_user":
        try:
            target = int(m.text.strip())
        except ValueError:
            return await m.reply("❌ Invalid user_id. Numeric only.", quote=True)

        resp = supabase.table("xeno_keys") \
            .update({"banned": True}) \
            .eq("redeemed_by", target) \
            .execute()
        count = len(resp.data or [])
        msg   = f"✅ User `{target}` banned. Marked {count} key(s)." if count else "⚠️ No redeemed keys for that user."
        await m.reply(msg, quote=True)

    # 5) Unban User
    elif flow == "await_unban_user":
        try:
            target = int(m.text.strip())
        except ValueError:
            return await m.reply("❌ Invalid user_id. Numeric only.", quote=True)

        resp = supabase.table("xeno_keys") \
            .update({"banned": False}) \
            .eq("redeemed_by", target) \
            .execute()
        count = len(resp.data or [])
        msg   = f"✅ User `{target}` unbanned. Cleared {count} key(s)." if count else "⚠️ No banned keys for that user."
        await m.reply(msg, quote=True)

    # clear the flow state
    admin_state.pop(m.from_user.id, None)

# 6) Handle the “Show Stats” callback
@app.on_callback_query(filters.regex("^admin_show_stats$") & filters.user(ADMIN_ID))
async def admin_show_stats_cb(_, cq: CallbackQuery):
    await cq.answer()
    try:
        await cq.message.edit_reply_markup(None)
    except:
        pass

    # fetch all keys
    resp = supabase.table("xeno_keys").select("*").execute()
    rows = resp.data or []

    total_keys    = len(rows)
    redeemed_rows = [r for r in rows if r.get("redeemed_by")]
    unredeemed    = total_keys - len(redeemed_rows)
    now           = datetime.now(timezone.utc)

    # build a plain‐text report
    lines = [
        "📊 BOT STATS",
        "",
        f"🔑 Total keys: {total_keys}",
        f"✅ Redeemed:    {len(redeemed_rows)}",
        f"❌ Unredeemed:  {unredeemed}",
        "",
        "👤 Redeemed Users:",
        ""
    ]

    for r in redeemed_rows:
        key    = r["key"]
        uid    = r["redeemed_by"]
        expiry = datetime.fromisoformat(r["expiry"].replace("Z","+00:00"))
        rem    = expiry - now
        if rem.total_seconds() <= 0:
            left = "Expired"
        else:
            days, rem_secs = divmod(int(rem.total_seconds()), 86400)
            hrs, rem_secs  = divmod(rem_secs, 3600)
            mins, _        = divmod(rem_secs, 60)
            left = (f"{days}d {hrs}h {mins}m" if days
                   else f"{hrs}h {mins}m" if hrs
                   else f"{mins}m")

        try:
            user = await cq.client.get_users(uid)
            uname = "@" + user.username if user.username else "(no username)"
        except:
            uname = "(unknown)"

        lines += [
            f"- {uid} {uname}",
            f"   • Key:    {key}",
            f"   • Expires: {expiry}",
            f"   • Left:    {left}",
            ""
        ]

    report = "\n".join(lines)

    # if too long, send as a file
    if len(report) > 4000:
        with open("stats.txt", "w", encoding="utf-8") as f:
            f.write(report)
        await cq.message.reply_document("stats.txt", caption="📊 Full stats")
        os.remove("stats.txt")
    else:
        await cq.message.reply(report)
        
if __name__ == "__main__":
    app.run()
