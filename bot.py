import telebot
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, timedelta

# ==== BOT CONFIG ====
BOT_TOKEN = "8136580879:AAEAGXS1VT7kFPJ0NaDD39OgM38QCd-f0Hw"
OWNER_ID = 8126299341  # Your Telegram ID

bot = telebot.TeleBot(BOT_TOKEN)

# ==== DATABASE SETUP ====
conn = sqlite3.connect("usdt_full_dynamic_bot.db", check_same_thread=False)
cursor = conn.cursor()

# Users table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0,
    referrer INTEGER,
    last_bonus TEXT,
    is_blocked INTEGER DEFAULT 0
)
""")

# Settings table
cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

# Admins table
cursor.execute("""
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
)
""")

# Channels table
cursor.execute("""
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    type TEXT
)
""")

# X/Twitter links table
cursor.execute("""
CREATE TABLE IF NOT EXISTS x_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link TEXT,
    description TEXT
)
""")

# X click tracking
cursor.execute("""
CREATE TABLE IF NOT EXISTS x_clicks (
    user_id INTEGER,
    x_id INTEGER,
    clicked_at TEXT,
    PRIMARY KEY (user_id, x_id)
)
""")

# Withdrawals table
cursor.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    status TEXT,
    requested_at TEXT
)
""")

# Support messages table
cursor.execute("""
CREATE TABLE IF NOT EXISTS support (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message TEXT,
    reply TEXT,
    time TEXT
)
""")

conn.commit()

# ==== HELPER FUNCTIONS ====
def get_setting(key):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))
    conn.commit()

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    cursor.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
    return cursor.fetchone() is not None

def bot_active():
    status = get_setting("bot_status")
    return status != "stopped"

# ==== MAIN MENU ====
def send_main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("📊 Balance"), KeyboardButton("👥 Refer"))
    markup.row(KeyboardButton("🎁 Bonus"), KeyboardButton("💸 Withdraw"))
    markup.row(KeyboardButton("📩 Support"), KeyboardButton("📝 X/Links"))
    bot.send_message(user_id, "Main Menu:", reply_markup=markup)

# ==== START COMMAND ====
@bot.message_handler(commands=['start'])
def start(message):
    if not bot_active():
        return
    user_id = message.chat.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

    cursor.execute("SELECT name FROM channels WHERE type='join'")
    join_channels = cursor.fetchall()
    if join_channels:
        markup = InlineKeyboardMarkup()
        for ch in join_channels:
            markup.add(InlineKeyboardButton(f"Join {ch[0]}", url=f"https://t.me/{ch[0]}"))
        markup.add(InlineKeyboardButton("✅ I've Joined", callback_data="check_join"))
        bot.send_message(user_id, "Welcome! Please join all required channels:", reply_markup=markup)
    else:
        bot.send_message(user_id, "Welcome! Admin has not set join channels yet.")

# ==== CHECK JOIN ====
@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join(call):
    user_id = call.from_user.id
    cursor.execute("SELECT name FROM channels WHERE type='join'")
    join_channels = cursor.fetchall()
    joined_all = True
    for ch in join_channels:
        try:
            member = bot.get_chat_member(f"@{ch[0]}", user_id)
            if member.status not in ["member","administrator","creator"]:
                joined_all = False
                break
        except:
            joined_all = False
    if joined_all:
        bot.answer_callback_query(call.id, "✅ You joined all channels!")
        send_main_menu(user_id)
    else:
        bot.answer_callback_query(call.id, "❌ Please join all channels first")

# ==== MENU HANDLER ====
@bot.message_handler(func=lambda m: True)
def menu_handler(message):
    if not bot_active():
        return
    user_id = message.chat.id
    text = message.text

    cursor.execute("SELECT is_blocked FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row and row[0]:
        bot.send_message(user_id, "❌ You are blocked.")
        return

    # ---- User Options ----
    if text == "📊 Balance":
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        bal = cursor.fetchone()[0]
        bot.send_message(user_id, f"💰 Your balance: {bal} USDT")

    elif text == "👥 Refer":
        ref_link = f"https://t.me/YOUR_BOT?start={user_id}"
        bot.send_message(user_id, f"Your referral link:\n{ref_link}")

    elif text == "🎁 Bonus":
        cursor.execute("SELECT last_bonus FROM users WHERE user_id=?", (user_id,))
        last = cursor.fetchone()[0]
        now = datetime.utcnow()
        bonus_cooldown = int(get_setting('bonus_cooldown') or 24)
        bonus_amount = float(get_setting('bonus_amount') or 1)
        if last:
            last_time = datetime.strptime(last, '%Y-%m-%d %H:%M:%S')
            if now - last_time < timedelta(hours=bonus_cooldown):
                bot.send_message(user_id, f"⏳ Bonus claimed. Try after {(timedelta(hours=bonus_cooldown) - (now - last_time))}")
                return
        cursor.execute("UPDATE users SET balance=balance+?, last_bonus=? WHERE user_id=?",
                    (bonus_amount, now.strftime('%Y-%m-%d %H:%M:%S'), user_id))
        conn.commit()
        bot.send_message(user_id, f"🎉 You received {bonus_amount} USDT bonus!")

    elif text == "💸 Withdraw":
        bot.send_message(user_id, "Send withdrawal request using /withdraw <amount>")

    elif text == "📩 Support":
        bot.send_message(user_id, "Send support message using /support <your message>")

    elif text == "📝 X/Links":
        cursor.execute("SELECT id, description, link FROM x_links")
        links = cursor.fetchall()
        if not links:
            bot.send_message(user_id, "No X/Twitter links set by admin.")
            return
        markup = InlineKeyboardMarkup()
        for l in links:
            markup.add(InlineKeyboardButton(f"{l[1]}", url=l[2], callback_data=f"x_{l[0]}"))
        bot.send_message(user_id, "Check these links:", reply_markup=markup)

# ==== TRACK X LINK CLICK ====
@bot.callback_query_handler(func=lambda call: call.data.startswith('x_'))
def x_click(call):
    x_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    cursor.execute("INSERT OR IGNORE INTO x_clicks (user_id, x_id, clicked_at) VALUES (?,?,?)",
                (user_id, x_id, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    bot.answer_callback_query(call.id, "✅ Tracked your click!")

# ==== ADMIN BOT CONTROL ====
@bot.message_handler(commands=['bot_stop','bot_start'])
def bot_control(message):
    if not is_admin(message.from_user.id):
        return
    cmd = message.text.strip()
    if cmd == '/bot_stop':
        set_setting('bot_status','stopped')
        bot.reply_to(message,'✅ Bot stopped.')
    elif cmd == '/bot_start':
        set_setting('bot_status','running')
        bot.reply_to(message,'✅ Bot started.')

# ==== WITHDRAW COMMAND ====
@bot.message_handler(commands=['withdraw'])
def withdraw(message):
    user_id = message.chat.id
    if not bot_active():
        return
    try:
        amount = float(message.text.split()[1])
        min_w = float(get_setting('withdraw_min') or 10)
        max_w = float(get_setting('withdraw_max') or 1000)
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        balance = cursor.fetchone()[0]
        if amount < min_w or amount > max_w or amount > balance:
            bot.reply_to(message, f"Invalid withdrawal. Min: {min_w}, Max: {max_w}, Your balance: {balance}")
            return
        cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, user_id))
        cursor.execute("INSERT INTO withdrawals (user_id, amount, status, requested_at) VALUES (?,?,?,?)",
                    (user_id, amount, 'pending', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        bot.reply_to(message, f"✅ Withdrawal request of {amount} USDT submitted.")
    except:
        bot.reply_to(message, "Usage: /withdraw <amount>")

# ==== SUPPORT COMMAND ====
@bot.message_handler(commands=['support'])
def support(message):
    user_id = message.chat.id
    msg_text = ' '.join(message.text.split()[1:])
    if not msg_text:
        bot.reply_to(message, "Usage: /support <your message>")
        return
    cursor.execute("INSERT INTO support (user_id,message,time) VALUES (?,?,?)",
                (user_id, msg_text, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    bot.reply_to(message, "✅ Support message sent. Admins will reply soon.")

# ==== RUN BOT ====
print("Fully Advanced Dynamic Bot is Running...")
bot.polling(none_stop=True)
