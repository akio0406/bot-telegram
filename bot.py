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

# — /menu command —
@app.on_message(filters.command("menu") & filters.private)
async def menu_cmd(_, m: Message):
    if not await check_user_access(m.from_user.id):
        return await m.reply("⛔ Redeem a key first with `/redeem <key>`.")
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔐 Encrypt",            callback_data="menu_encrypt"),
            InlineKeyboardButton("🔓 Decrypt",            callback_data="menu_decrypt")
        ],
        [
            InlineKeyboardButton("🔍 Search",             callback_data="menu_search"),
            InlineKeyboardButton("➖ Remove URLs",         callback_data="menu_removeurl"),
            InlineKeyboardButton("➗ Remove Duplicates",   callback_data="menu_removedupe"),
            InlineKeyboardButton("🔗 Merge Files",         callback_data="menu_merge")
        ],
        [
            InlineKeyboardButton("👥 Refer",              callback_data="menu_refer")
        ],
    ])
    await m.reply(
        "♨️ XENO PREMIUM BOT ♨️\nChoose an action:",
        reply_markup=kb
    )

# — Encrypt button —
@app.on_callback_query(filters.regex("^menu_encrypt$"))
async def on_encrypt_cb(_, cq: CallbackQuery):
    uid = cq.from_user.id
    await cq.answer("Encrypt mode activated!")
    await cq.message.edit_reply_markup(None)
    if not await check_user_access(uid):
        return await cq.message.reply("⛔ Redeem a key first (`/redeem <key>`).")
    user_state[uid] = "encrypt"
    await cq.message.reply("📂 Send a `.py` or `.txt` file (max 10MB) to encrypt.")

# — Decrypt button —
@app.on_callback_query(filters.regex("^menu_decrypt$"))
async def on_decrypt_cb(_, cq: CallbackQuery):
    uid = cq.from_user.id
    await cq.answer("Decrypt mode activated!")
    await cq.message.edit_reply_markup(None)
    if not await check_user_access(uid):
        return await cq.message.reply("⛔ Redeem a key first (`/redeem <key>`).")
    user_state[uid] = "decrypt"
    await cq.message.reply("📂 Send an encrypted `.py` or `.txt` file to decrypt.")

# — Search button —
@app.on_callback_query(filters.regex("^menu_search$"))
async def on_search_cb(_, cq: CallbackQuery):
    uid = cq.from_user.id
    await cq.answer()
    await cq.message.edit_reply_markup(None)
    if not await check_user_access(uid):
        return await cq.message.reply("⛔ Redeem a key first (`/redeem <key>`).")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Roblox",          callback_data="keyword_roblox")],
        [InlineKeyboardButton("🔥 Mobile Legends",  callback_data="keyword_mobilelegends")],
        [InlineKeyboardButton("💳 Codashop",         callback_data="keyword_codashop")],
        [InlineKeyboardButton("🛡 Garena",           callback_data="expand_garena")],
        [InlineKeyboardButton("🌐 Social Media",     callback_data="expand_socmeds")],
        [InlineKeyboardButton("✉️ Email Providers", callback_data="expand_emails")],
        [InlineKeyboardButton("🎮 Gaming",           callback_data="expand_gaming")],
    ])
    await cq.message.reply(
        "🔎 DATABASE SEARCH\n\n📌 Choose a keyword to search:",
        reply_markup=kb
    )

# — Remove URLs button —
@app.on_callback_query(filters.regex("^menu_removeurl$"))
async def on_removeurl_cb(_, cq: CallbackQuery):
    uid = cq.from_user.id
    await cq.answer("Remove-URLs mode activated!")
    await cq.message.edit_reply_markup(None)
    if not await check_user_access(uid):
        return await cq.message.reply("⛔ Redeem a key first (`/redeem <key>`).")
    user_state[uid] = "removeurl"
    await cq.message.reply("📂 Send a file containing URLs to remove.")

# — Merge button —
@app.on_callback_query(filters.regex("^menu_merge$") & restricted())
async def on_merge_cb(_, cq: CallbackQuery):
    uid = cq.from_user.id
    await cq.answer()
    await cq.message.edit_reply_markup(None)
    if not await check_user_access(uid):
        return await cq.message.reply("⛔ Redeem a key first (`/redeem <key>`).")

    user_state[uid] = "merge"
    await cq.message.reply(
        "📂 Send multiple `.txt` files (max 10MB each). I’ll merge them without duplicates. "
        "When you’re done, type `/done`."
    )

# — Remove Dupe —
@app.on_callback_query(filters.regex("^menu_removedupe$"))
async def on_removedupe_cb(_, cq: CallbackQuery):
    uid = cq.from_user.id
    await cq.answer()
    await cq.message.edit_reply_markup(None)
    if not await check_user_access(uid):
        return await cq.message.reply("⛔ Redeem a key first (`/redeem <key>`).")
    user_state[uid] = "removedupe"
    await cq.message.reply(
      "📂 Send a `.txt` file (max 10MB) — I’ll strip out all duplicate lines for you!"
    )

# — Fallback commands —
@app.on_message(filters.command("encrypt") & filters.private)
async def cmd_encrypt(_, m: Message):
    user_state[m.from_user.id] = "encrypt"
    await m.reply("📂 Send a `.py` or `.txt` file to encrypt.")

@app.on_message(filters.command("decrypt") & filters.private)
async def cmd_decrypt(_, m: Message):
    user_state[m.from_user.id] = "decrypt"
    await m.reply("📂 Send an encrypted `.py` or `.txt` file to decrypt.")

@app.on_message(filters.command("removeurl") & filters.private)
async def remove_url_command(_, m: Message):
    user_state[m.from_user.id] = "removeurl"
    await m.reply("📂 Send a file containing URLs to remove.")

# — Unified file handler —
@app.on_message(filters.document & filters.private)
async def file_handler(bot: Client, m: Message):
    uid  = m.from_user.id
    mode = user_state.pop(uid, None)
    if not mode:
        return await m.reply(
            "⚠️ First choose Encrypt, Decrypt, Search, Remove URLs, Remove Duplicates or Merge via /menu."
        )

    if mode == "encrypt":
        await do_encrypt(bot, m)
    elif mode == "decrypt":
        await do_decrypt(bot, m)
    elif mode == "removeurl":
        await process_removeurl_file(bot, m)
    elif mode == "removedupe":
        await process_remove_dupe_file(bot, m)
    elif mode == "merge":
        await handle_merge_file(bot, m)

async def do_encrypt(bot: Client, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only .py/.txt allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large (max 10MB).")
    prog = await m.reply("⏳ Downloading…")
    path = await bot.download_media(m)
    await prog.edit("🔐 Encrypting…")
    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        b64 = base64.b64encode(raw.encode()).decode()
        out_fn = f"encrypted_{doc.file_name}"
        with open(out_fn, "w", encoding="utf-8") as f:
            f.write(f"import base64\nexec(base64.b64decode('{b64}').decode())\n")
        await bot.send_document(m.chat.id, out_fn, caption="✅ Encrypted!")
    except Exception as e:
        await prog.edit(f"❌ Encryption error: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(out_fn): os.remove(out_fn)

async def do_decrypt(bot: Client, m: Message):
    doc = m.document
    if not doc.file_name.lower().endswith((".py", ".txt")):
        return await m.reply("❌ Only .py/.txt allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large (max 10MB).")
    prog = await m.reply("⏳ Downloading…")
    path = await bot.download_media(m)
    await prog.edit("🔓 Decrypting…")
    try:
        content = open(path, "r", encoding="utf-8", errors="ignore").read()
        mobj = re.search(r"b64decode\('(.+?)'\)", content)
        if not mobj:
            raise ValueError("No payload.")
        dec = base64.b64decode(mobj.group(1)).decode()
        out_fn = f"decrypted_{doc.file_name}"
        with open(out_fn, "w", encoding="utf-8") as f:
            f.write(dec)
        await bot.send_document(m.chat.id, out_fn, caption="✅ Decrypted!")
    except Exception as e:
        await prog.edit(f"❌ Decryption error: {e}")
    finally:
        await prog.delete()
        os.remove(path)
        if os.path.exists(out_fn): os.remove(out_fn)

async def process_removeurl_file(bot: Client, m: Message):
    """Strip prefixes so only user:pass remains, write to removed_url_of_<filename>."""
    doc = m.document
    if not doc.file_name.lower().endswith((".txt", ".py")):
        return await m.reply("❌ Only .txt/.py allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large (max 10MB).")

    prog = await m.reply("⏳ Downloading…")
    path = await bot.download_media(m)
    await prog.edit("➖ Removing prefixes…")

    # Read & clean
    cleaned_lines = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split(":")
            # if there's at least user:pass, grab the last two segments
            if len(parts) >= 2:
                cleaned = ":".join(parts[-2:])
                cleaned_lines.append(cleaned)

async def process_remove_dupe_file(bot: Client, m: Message):
    file = m.document
    if not file.file_name.lower().endswith(".txt"):
        return await m.reply("❌ Only `.txt` files supported.")
    if file.file_size > MAX_SIZE:
        return await m.reply("❌ File too large (max 10MB).")

    prog = await m.reply("⏳ Downloading…")
    path = await bot.download_media(m)
    await prog.edit("♻️ Removing duplicates…")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]

    seen = set()
    unique = []
    for l in lines:
        if l not in seen:
            seen.add(l)
            unique.append(l)

    # if nothing changed
    if len(unique) == len(lines):
        await prog.edit("✅ No duplicates found.")
        os.remove(path)
        return

    out_fn = f"no_dupes_{file.file_name}"
    with open(out_fn, "w", encoding="utf-8") as f:
        f.write("\n".join(unique))

    await bot.send_document(
      m.chat.id, out_fn,
      caption="✅ Duplicates removed!"
    )
    # cleanup
    await prog.delete()
    os.remove(path)
    os.remove(out_fn)

    # Build output filename
    out_fn = f"removed_url_of_{doc.file_name}"
    with open(out_fn, "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned_lines))

    # Send back
    await bot.send_document(m.chat.id, out_fn,
        caption="✅ Prefixes removed – only user:pass remain."
    )

    # cleanup
    await prog.delete()
    os.remove(path)
    os.remove(out_fn)

# in global scope:
merge_sessions: dict[int, set[str]] = {}

async def handle_merge_file(bot: Client, m: Message):
    user_id = m.from_user.id
    if user_state.get(user_id) != "merge":
        return

    doc = m.document
    if not doc.file_name.lower().endswith(".txt"):
        return await m.reply("❌ Only `.txt` allowed.")
    if doc.file_size > MAX_SIZE:
        return await m.reply("❌ File too large (max 10MB).")

    path = await bot.download_media(m)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = {ln.strip() for ln in f if ln.strip()}
    os.remove(path)

    session = merge_sessions.setdefault(user_id, set())
    session.update(lines)

    await m.reply(f"✅ Added! Total unique lines so far: {len(session)}.\n"
                  "Send more `.txt` or type `/done` to finish.")

@app.on_message(filters.command("done") & filters.private)
async def finish_merge(client: Client, m: Message):
    user_id = m.from_user.id
    session = merge_sessions.pop(user_id, None)
    user_state.pop(user_id, None)

    if not session:
        return await m.reply("⚠️ No files merged. Use /menu → Merge first.")

    out_fn = "merged_results.txt"
    with open(out_fn, "w", encoding="utf-8") as f:
        f.write("\n".join(session))

    await client.send_document(m.chat.id, out_fn, caption="✅ Here’s your merged file!")
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
    _, _, filename, keyword = cq.data.split("_",3)
    path = f"Generated/{filename}"
    if os.path.exists(path):
        content = open(path,"r",encoding="utf-8").read()
        if len(content)>4096:
            content = content[:4090]+"...\n[Truncated]"
        await cq.message.reply(
            f"<b>Results for:</b> <code>{keyword}</code>\n<pre>{content}</pre>",
            parse_mode="HTML"
        )
        os.remove(path)
    await cq.message.delete()

@app.on_callback_query(filters.regex("^download_results_"))
async def download_results_file(_, cq: CallbackQuery):
    _, _, filename, keyword = cq.data.split("_",3)
    path = f"Generated/{filename}"
    if os.path.exists(path):
        await cq.message.reply_document(
            document=path,
            caption=f"📄 PREMIUM results for `{keyword}`"
        )
        os.remove(path)
    await cq.message.delete()

@app.on_message(filters.command(["genkey","generate"]) & filters.private & filters.user(ADMIN_ID))
async def genkey_cmd(_, m: Message):
    parts = m.text.strip().split()
    if len(parts) != 2:
        return await m.reply("❌ Usage: `/genkey <duration>`", quote=True)
    delta = parse_duration(parts[1])
    if delta.total_seconds() <= 0:
        return await m.reply("❌ Invalid duration. Use `1d`,`12h`,`30m`.", quote=True)
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
