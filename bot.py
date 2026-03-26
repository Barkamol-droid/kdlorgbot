# -*- coding: utf-8 -*-
import os
import re
import json
import time
import shutil
import logging
from datetime import datetime

import telebot
import yt_dlp
from telebot import types

# =========================
# SOZLAMALAR
# =========================
import os

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi")

SIGNATURE = "by KayimovProg"
ADMIN_IDS = [356421765]

# Test uchun vaqtincha [] qilib turish mumkin
CHANNELS = []

DOWNLOAD_FOLDER = "downloads"
USERS_FILE = "users.json"
COOKIES_FILE = "cookies.txt"
MAX_MEDIA_GROUP = 10

# obuna cache (tezlik uchun)
SUB_CACHE_TTL = 120
sub_cache = {}

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=6)
broadcast_mode = {}

MENU_BUTTONS = {"📥 Yuklash", "ℹ️ Yordam", "📊 Statistika", "📢 Reklama yuborish"}

# =========================
# JSON
# =========================
def ensure_file(filename, default_data):
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)

def load_json(filename, default_data):
    ensure_file(filename, default_data)
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_data

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# =========================
# USERLAR
# =========================
def save_user(user_id):
    users = load_json(USERS_FILE, [])
    if user_id not in users:
        users.append(user_id)
        save_json(USERS_FILE, users)

def get_users():
    return load_json(USERS_FILE, [])

# =========================
# YORDAMCHI
# =========================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]+', "", name).strip()

def get_ffmpeg_location():
    return shutil.which("ffmpeg")

def user_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📥 Yuklash", "ℹ️ Yordam")
    return kb

def admin_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📥 Yuklash", "ℹ️ Yordam")
    kb.row("📊 Statistika", "📢 Reklama yuborish")
    return kb

def sub_keyboard():
    kb = types.InlineKeyboardMarkup()
    for ch in CHANNELS:
        kb.add(
            types.InlineKeyboardButton(
                text=f"➕ {ch}",
                url=f"https://t.me/{ch.replace('@', '')}"
            )
        )
    kb.add(types.InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub"))
    return kb

def check_sub(user_id):
    """
    Cache bilan tezlashtirilgan obuna tekshiruv.
    Xato bo'lsa bot to'xtab qolmasin deb True qaytariladi.
    """
    if not CHANNELS:
        return True

    now = time.time()
    cached = sub_cache.get(user_id)
    if cached and now - cached["time"] < SUB_CACHE_TTL:
        return cached["status"]

    for ch in CHANNELS:
        try:
            member = bot.get_chat_member(ch, user_id)
            status = getattr(member, "status", "")
            if status not in ["member", "administrator", "creator"]:
                sub_cache[user_id] = {"status": False, "time": now}
                return False
        except Exception as e:
            print(f"Obuna tekshirish xatoligi {ch}: {e}")
            sub_cache[user_id] = {"status": True, "time": now}
            return True

    sub_cache[user_id] = {"status": True, "time": now}
    return True

def start_text():
    return (
        "👋 Salom!\n\n"
        "Menga YouTube / TikTok / Instagram link yuboring.\n"
        "Men video yoki rasmni yuklab beraman.\n\n"
        f"⚡ {SIGNATURE}"
    )

def help_text():
    return (
        "📌 Bot imkoniyatlari:\n\n"
        "• YouTube video yuklash\n"
        "• TikTok video yuklash\n"
        "• Instagram reel / post / carousel yuklash\n"
        "• Rasm va video yuborish\n\n"
        "Foydalanish:\n"
        "1. Link yuborasiz\n"
        "2. Bot mediani yuklaydi\n"
        "3. Sizga tayyor holatda yuboradi\n\n"
        f"⚡ {SIGNATURE}"
    )

# =========================
# MEDIA YUKLASH
# =========================
def build_ydl_opts():
    ffmpeg_location = get_ffmpeg_location()

    opts = {
        "outtmpl": os.path.join(DOWNLOAD_FOLDER, "%(title).60s_%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "nocheckcertificate": True,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "concurrent_fragment_downloads": 4,
        "http_chunk_size": 10485760,
        "format": "mp4/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
    }

    if ffmpeg_location:
        opts["ffmpeg_location"] = ffmpeg_location

    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE

    return opts

def find_downloaded_file(base_without_ext: str):
    exts = [".mp4", ".mkv", ".webm", ".mov", ".jpg", ".jpeg", ".png", ".webp"]
    for ext in exts:
        test = base_without_ext + ext
        if os.path.exists(test):
            return test
    return None

def detect_media_type(filepath: str):
    ext = os.path.splitext(filepath)[1].lower()
    return "photo" if ext in [".jpg", ".jpeg", ".png", ".webp"] else "video"

def clean_and_fix_path(path: str):
    if not path or not os.path.exists(path):
        return path

    folder = os.path.dirname(path)
    filename = os.path.basename(path)
    clean_name = safe_filename(filename)
    clean_path = os.path.join(folder, clean_name)

    if path != clean_path:
        try:
            os.rename(path, clean_path)
            return clean_path
        except Exception:
            return path
    return path

def extract_entries(url: str):
    ydl_opts = build_ydl_opts()
    results = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise Exception("Media topilmadi yoki yuklab bo‘lmadi.")

        entries = info.get("entries") if isinstance(info, dict) else None
        if entries:
            for entry in entries:
                if not entry:
                    continue

                filepath = None
                requested_downloads = entry.get("requested_downloads") or []
                if requested_downloads:
                    filepath = requested_downloads[0].get("filepath")

                if not filepath:
                    filepath = ydl.prepare_filename(entry)

                if filepath and not os.path.exists(filepath):
                    found = find_downloaded_file(os.path.splitext(filepath)[0])
                    if found:
                        filepath = found

                if filepath and os.path.exists(filepath):
                    filepath = clean_and_fix_path(filepath)
                    results.append({
                        "path": filepath,
                        "type": detect_media_type(filepath)
                    })
        else:
            filepath = None
            requested_downloads = info.get("requested_downloads") or []

            if requested_downloads:
                filepath = requested_downloads[0].get("filepath")

            if not filepath:
                filepath = ydl.prepare_filename(info)

            if filepath and not os.path.exists(filepath):
                found = find_downloaded_file(os.path.splitext(filepath)[0])
                if found:
                    filepath = found

            if filepath and os.path.exists(filepath):
                filepath = clean_and_fix_path(filepath)
                results.append({
                    "path": filepath,
                    "type": detect_media_type(filepath)
                })

    if not results:
        raise Exception("Media yuklanmadi.")

    return results

# =========================
# YUBORISH
# =========================
def send_single_media(chat_id, item):
    path = item["path"]
    if item["type"] == "photo":
        with open(path, "rb") as f:
            bot.send_photo(chat_id, f, caption=f"✅ Tayyor\n\n⚡ {SIGNATURE}")
    else:
        with open(path, "rb") as f:
            bot.send_video(chat_id, f, caption=f"✅ Tayyor\n\n⚡ {SIGNATURE}")

def send_media_group(chat_id, items):
    media_group = []
    files_to_close = []

    try:
        for i, item in enumerate(items[:MAX_MEDIA_GROUP]):
            f = open(item["path"], "rb")
            files_to_close.append(f)
            caption = f"✅ Tayyor\n\n⚡ {SIGNATURE}" if i == 0 else ""

            if item["type"] == "photo":
                media_group.append(types.InputMediaPhoto(f, caption=caption))
            else:
                media_group.append(types.InputMediaVideo(f, caption=caption))

        if len(media_group) >= 2:
            bot.send_media_group(chat_id, media_group)
        elif len(media_group) == 1:
            files_to_close[0].close()
            files_to_close = []
            send_single_media(chat_id, items[0])

    finally:
        for f in files_to_close:
            try:
                f.close()
            except Exception:
                pass

def cleanup_files(items):
    for item in items:
        path = item.get("path")
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

# =========================
# START
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    save_user(message.from_user.id)
    menu = admin_menu() if is_admin(message.from_user.id) else user_menu()

    try:
        subscribed = check_sub(message.from_user.id)
    except Exception as e:
        print(f"/start check_sub xatolik: {e}")
        subscribed = True

    if not subscribed:
        bot.send_message(
            message.chat.id,
            "📢 Botdan foydalanish uchun kanallarga obuna bo‘ling:",
            reply_markup=sub_keyboard()
        )
        return

    bot.send_message(message.chat.id, start_text(), reply_markup=menu)

# =========================
# CALLBACK
# =========================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "check_sub":
        try:
            subscribed = check_sub(call.from_user.id)
        except Exception as e:
            print(f"callback check_sub xatolik: {e}")
            subscribed = True

        if subscribed:
            menu = admin_menu() if is_admin(call.from_user.id) else user_menu()
            bot.answer_callback_query(call.id, "Obuna tasdiqlandi ✅")
            bot.send_message(
                call.message.chat.id,
                "✅ Obuna tasdiqlandi.\n\n" + start_text(),
                reply_markup=menu
            )
        else:
            bot.answer_callback_query(call.id, "Hali obuna bo‘lmagansiz ❌")

# =========================
# ADMIN
# =========================
@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        return

    bot.send_message(
        message.chat.id,
        "👑 Admin panel\n\n"
        "📊 Statistika\n"
        "📢 Reklama yuborish\n\n"
        f"⚡ {SIGNATURE}",
        reply_markup=admin_menu()
    )

@bot.message_handler(commands=["stats"])
def stats_command(message):
    if not is_admin(message.from_user.id):
        return

    users = get_users()
    bot.send_message(
        message.chat.id,
        f"📊 Bot statistikasi\n\n"
        f"👥 Userlar: {len(users)}\n"
        f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"⚡ {SIGNATURE}"
    )

@bot.message_handler(commands=["sendall"])
def sendall_command(message):
    if not is_admin(message.from_user.id):
        return

    text = message.text.replace("/sendall", "", 1).strip()
    if text:
        send_broadcast(message.chat.id, text)
    else:
        broadcast_mode[message.from_user.id] = True
        bot.send_message(
            message.chat.id,
            f"📢 Reklama matnini yuboring.\n\nBekor qilish: /cancel\n\n⚡ {SIGNATURE}"
        )

@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    if message.from_user.id in broadcast_mode:
        broadcast_mode.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, f"❌ Bekor qilindi\n\n⚡ {SIGNATURE}")

def send_broadcast(chat_id, text):
    users = get_users()
    sent = 0
    failed = 0

    bot.send_message(chat_id, f"⏳ Reklama yuborilmoqda...\n\n⚡ {SIGNATURE}")

    for uid in users:
        try:
            bot.send_message(uid, f"{text}\n\n⚡ {SIGNATURE}")
            sent += 1
            time.sleep(0.02)
        except Exception:
            failed += 1

    bot.send_message(
        chat_id,
        f"✅ Tugadi\n\nYuborildi: {sent}\nXatolik: {failed}\n\n⚡ {SIGNATURE}"
    )

# =========================
# MENU
# =========================
@bot.message_handler(func=lambda m: m.text == "ℹ️ Yordam")
def help_button(message):
    bot.send_message(message.chat.id, help_text())

@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def stats_button(message):
    if not is_admin(message.from_user.id):
        return
    users = get_users()
    bot.send_message(
        message.chat.id,
        f"📊 Bot statistikasi\n\n👥 Userlar: {len(users)}\n\n⚡ {SIGNATURE}"
    )

@bot.message_handler(func=lambda m: m.text == "📢 Reklama yuborish")
def reklama_button(message):
    if not is_admin(message.from_user.id):
        return
    broadcast_mode[message.from_user.id] = True
    bot.send_message(
        message.chat.id,
        f"📢 Reklama matnini yuboring.\n\nBekor qilish: /cancel\n\n⚡ {SIGNATURE}"
    )

@bot.message_handler(func=lambda m: m.text == "📥 Yuklash")
def yuklash_button(message):
    bot.send_message(
        message.chat.id,
        "🔗 Link yuboring.\n\nMen video yoki rasmni tez yuklab beraman.\n\n"
        f"⚡ {SIGNATURE}"
    )

# =========================
# ASOSIY LOGIKA
# =========================
@bot.message_handler(content_types=["text"])
def all_messages(message):
    save_user(message.from_user.id)
    text = (message.text or "").strip()

    if text.startswith("/"):
        return

    if is_admin(message.from_user.id) and broadcast_mode.get(message.from_user.id):
        broadcast_mode.pop(message.from_user.id, None)
        send_broadcast(message.chat.id, text)
        return

    if text in MENU_BUTTONS:
        return

    try:
        subscribed = check_sub(message.from_user.id)
    except Exception as e:
        print(f"all_messages check_sub xatolik: {e}")
        subscribed = True

    if not subscribed:
        bot.send_message(
            message.chat.id,
            "📢 Botdan foydalanish uchun kanallarga obuna bo‘ling:",
            reply_markup=sub_keyboard()
        )
        return

    if not (text.startswith("http://") or text.startswith("https://")):
        bot.reply_to(message, f"❌ Iltimos, to‘g‘ri link yuboring.\n\n⚡ {SIGNATURE}")
        return

    wait_msg = bot.reply_to(message, f"⏳ Yuklanmoqda...\n\n⚡ {SIGNATURE}")
    items = []

    try:
        items = extract_entries(text)

        if len(items) == 1:
            send_single_media(message.chat.id, items[0])
        else:
            for i in range(0, len(items), MAX_MEDIA_GROUP):
                chunk = items[i:i + MAX_MEDIA_GROUP]
                if len(chunk) == 1:
                    send_single_media(message.chat.id, chunk[0])
                else:
                    send_media_group(message.chat.id, chunk)

        try:
            bot.delete_message(message.chat.id, wait_msg.message_id)
        except Exception:
            pass

    except Exception as e:
        logging.exception("Xatolik")
        bot.reply_to(message, f"❌ Xatolik:\n{str(e)}\n\n⚡ {SIGNATURE}")

    finally:
        cleanup_files(items)

print("Bot tayyor...")

while True:
    try:
        bot.infinity_polling(
            skip_pending=True,
            timeout=15,
            long_polling_timeout=15
        )
    except Exception as e:
        print(f"Polling xatoligi: {e}")
        time.sleep(3)
