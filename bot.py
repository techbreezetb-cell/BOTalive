# bot.py - Final with /admin00 command restricted to OWNER_ID
import telebot
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, timedelta

# ==== BOT CONFIG ====
BOT_TOKEN = "8136580879:AAEAGXS1VT7kFPJ0NaDD39OgM38QCd-f0Hw"
OWNER_ID = 8126299341  # Your Telegram ID (change accordingly)

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

# Channels table (join channels, withdraw channel etc)
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

# ==== DB MIGRATIONS / ENSURE COLUMNS ====
def ensure_withdrawal_columns():
    try:
        cursor.execute("SELECT channel_chat_id FROM withdrawals LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE withdrawals ADD COLUMN channel_chat_id TEXT")
    try:
        cursor.execute("SELECT channel_message_id FROM withdrawals LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE withdrawals ADD COLUMN channel_message_id INTEGER")
    try:
        cursor.execute("SELECT paid_at FROM withdrawals LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE withdrawals ADD COLUMN paid_at TEXT")
    conn.commit()

ensure_withdrawal_columns()

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

def add_admin(user_id):
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()

def remove_admin(user_id):
    cursor.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()

def bot_active():
    status = get_setting("bot_status")
    return status != "stopped"

def add_user_if_not_exists(user_id):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

# ==== INITIAL DEFAULT SETTINGS ====
if get_setting('bot_status') is None:
    set_setting('bot_status', 'running')
if get_setting('bonus_amount') is None:
    set_setting('bonus_amount', '1')
if get_setting('bonus_cooldown') is None:
    set_setting('bonus_cooldown', '24')
if get_setting('refer_amount') is None:
    set_setting('refer_amount', '0.5')
if get_setting('withdraw_min') is None:
    set_setting('withdraw_min', '10')
if get_setting('withdraw_max') is None:
    set_setting('withdraw_max', '1000')

# ==== ADMIN PANEL / HELP ====
@bot.message_handler(commands=['admin00'])
def admin_panel(message):
    user_id = message.from_user.id
    if user_id != OWNER_ID:   # Only owner can open
        return
    help_text = (
        "Admin Panel Commands:\n"
        "/addadmin <user_id>\n"
        "/removeadmin <user_id>\n"
        "/listadmins\n\n"
        "/setbonus <amount> <cooldown_hours>\n"
        "/setrefer <amount>\n\n"
        "/addxlink <description> <url>\n"
        "/removexlink <id>\n"
        "/listxlinks\n\n"
        "/addchannel <name> <type>\n"
        "/removechannel <name>\n\n"
        "/broadcast <message>\n"
        "/bot_stop  /bot_start\n\n"
        "/block <user_id>  /unblock <user_id>\n"
        "/addbal <user_id> <amount>  /removebal <user_id> <amount>\n\n"
        "/list_withdrawals [status]\n"
        "/post_withdrawal <withdrawal_id>\n"
        "/setwithdraw <withdrawal_id> <pending|paying|paid>\n\n"
        "/set_withdraw_channel <channel_name>\n"
    )
    bot.reply_to(message, help_text)

# ==== RUN BOT ====
print("Fully Advanced Dynamic Bot is Running with /admin00...")
bot.polling(none_stop=True)
