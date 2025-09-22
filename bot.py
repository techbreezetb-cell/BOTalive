# bot.py - Updated and Enhanced Version
import telebot
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, timedelta
import re

# ==== BOT CONFIG ====
BOT_TOKEN = "8136580879:AAEMXj7nMnaUd8_R39xXbDJAJ2EJNeYPUas"
OWNER_ID = 8126299341  # Your Telegram ID (change accordingly)

bot = telebot.TeleBot(BOT_TOKEN)

# ==== DATABASE SETUP ====
conn = sqlite3.connect("usdt_full_dynamic_bot.db", check_same_thread=False)
cursor = conn.cursor()

# Users table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance REAL DEFAULT 0,
    referrer INTEGER,
    last_bonus TEXT,
    is_blocked INTEGER DEFAULT 0,
    wallet_address TEXT,
    refer_activated INTEGER DEFAULT 0
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
    channel_name TEXT,
    channel_id TEXT,
    type TEXT
)
""")

# Social media links table
cursor.execute("""
CREATE TABLE IF NOT EXISTS social_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link TEXT,
    description TEXT
)
""")

# Social media click tracking
cursor.execute("""
CREATE TABLE IF NOT EXISTS social_clicks (
    user_id INTEGER,
    social_id INTEGER,
    clicked_at TEXT,
    PRIMARY KEY (user_id, social_id)
)
""")

# Withdrawals table
cursor.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    status TEXT DEFAULT 'pending',
    requested_at TEXT,
    wallet_address TEXT,
    channel_chat_id TEXT,
    channel_message_id INTEGER
)
""")

# Bot stats table
cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_stats (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

conn.commit()

# ==== HELPER FUNCTIONS ====
def get_setting(key):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, str(value)))
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

def add_user_if_not_exists(user_id, username, first_name):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?,?,?)", (user_id, username, first_name))
    conn.commit()

def get_user_link(user_id):
    cursor.execute("SELECT username, first_name FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    if user and user[0]:
        return f"@{user[0]}"
    elif user and user[1]:
        return f"<a href='tg://user?id={user_id}'>{user[1]}</a>"
    return f"<a href='tg://user?id={user_id}'>User {user_id}</a>"

def get_join_channels():
    cursor.execute("SELECT channel_name, channel_id FROM channels WHERE type='join'")
    return cursor.fetchall()

def get_social_links():
    cursor.execute("SELECT id, description, link FROM social_links")
    return cursor.fetchall()

def get_withdrawal_channel_id():
    cursor.execute("SELECT channel_id FROM channels WHERE type='withdrawal'")
    row = cursor.fetchone()
    return row[0] if row else None

def is_member_of_channels(user_id):
    channels = get_join_channels()
    for channel_name, channel_id in channels:
        try:
            member = bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except telebot.apihelper.ApiException:
            # Handle cases where the bot is not an admin or channel ID is invalid
            print(f"Could not check membership for channel {channel_id}")
            return False
    return True

def has_clicked_social(user_id):
    links = get_social_links()
    if not links:
        return True # No social links, so this step is not required
    for social_id, _, _ in links:
        cursor.execute("SELECT 1 FROM social_clicks WHERE user_id=? AND social_id=?", (user_id, social_id))
        if cursor.fetchone() is None:
            return False
    return True

# ==== KEYBOARDS ====
def main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💰 Daily Bonus", callback_data='daily_bonus'),
        InlineKeyboardButton("🔗 Refer & Earn", callback_data='refer_earn'),
        InlineKeyboardButton("💵 Withdraw", callback_data='withdraw'),
        InlineKeyboardButton("⚙️ My Account", callback_data='my_account'),
        InlineKeyboardButton("✍️ Chat Support", callback_data='chat_support'),
        InlineKeyboardButton("📊 Bot Status", callback_data='bot_status')
    )
    return markup

def admin_main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast'),
        InlineKeyboardButton("👥 User Management", callback_data='admin_user_management'),
        InlineKeyboardButton("⚙️ Bot Settings", callback_data='admin_settings'),
        InlineKeyboardButton("🔒 Manage Withdrawals", callback_data='admin_withdrawals'),
        InlineKeyboardButton("✅ Set Channels", callback_data='admin_set_channels'),
        InlineKeyboardButton("🔗 Set Social Links", callback_data='admin_set_social')
    )
    return markup

def admin_user_management_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Add Admin", callback_data='admin_add_admin'),
        InlineKeyboardButton("➖ Remove Admin", callback_data='admin_remove_admin'),
        InlineKeyboardButton("⛔ Block User", callback_data='admin_block_user'),
        InlineKeyboardButton("🔓 Unblock User", callback_data='admin_unblock_user'),
        InlineKeyboardButton("🔙 Back to Admin Menu", callback_data='admin_panel')
    )
    return markup

def admin_settings_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💰 Set Bonus Amount", callback_data='set_bonus_amount'),
        InlineKeyboardButton("🔗 Set Referral Amount", callback_data='set_refer_amount'),
        InlineKeyboardButton("💵 Set Withdrawal Min/Max", callback_data='set_withdraw_min_max'),
        InlineKeyboardButton("💵 Set Currency", callback_data='set_currency'),
        InlineKeyboardButton("📊 Start/Stop Bot", callback_data='start_stop_bot'),
        InlineKeyboardButton("🔙 Back to Admin Menu", callback_data='admin_panel')
    )
    return markup

def admin_withdrawal_status_keyboard(withdrawal_id):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("⏳ Set Status: Pending", callback_data=f'set_status_pending_{withdrawal_id}'),
        InlineKeyboardButton("➡️ Set Status: Paying", callback_data=f'set_status_paying_{withdrawal_id}'),
        InlineKeyboardButton("✅ Set Status: Paid", callback_data=f'set_status_paid_{withdrawal_id}')
    )
    return markup

def back_to_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu'))
    return markup

# ==== START HANDLER ====
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    add_user_if_not_exists(user_id, username, first_name)
    
    if not bot_active() and user_id != OWNER_ID:
        bot.send_message(user_id, "The bot is currently stopped for maintenance. Please check back later.")
        return

    # Handle referral links
    referrer_id = None
    if message.text.startswith("/start "):
        referrer_id_str = message.text.split(" ")[1]
        if referrer_id_str.isdigit():
            referrer_id = int(referrer_id_str)
            if referrer_id != user_id:
                cursor.execute("UPDATE users SET referrer=? WHERE user_id=? AND referrer IS NULL", (referrer_id, user_id))
                conn.commit()

    # Check for join channels
    channels = get_join_channels()
    if channels:
        markup = InlineKeyboardMarkup()
        for name, channel_id in channels:
            markup.add(InlineKeyboardButton(f"Join {name}", url=f"https://t.me/{channel_id.replace('@', '')}"))
        markup.add(InlineKeyboardButton("✅ I have joined", callback_data='check_join'))
        bot.send_message(user_id, "Please join the following channels to continue:", reply_markup=markup)
        return

    # Check for social links
    social_links = get_social_links()
    if social_links and not has_clicked_social(user_id):
        markup = InlineKeyboardMarkup()
        for social_id, description, link in social_links:
            markup.add(InlineKeyboardButton(description, url=link))
        markup.add(InlineKeyboardButton("✅ I have clicked", callback_data='check_social'))
        bot.send_message(user_id, "Please follow our social media accounts to continue:", reply_markup=markup)
        return

    # All checks passed, show main menu
    bot.send_message(user_id, "Welcome! Please use the menu below to get started.", reply_markup=main_menu_keyboard())


# ==== CALLBACK HANDLERS ====
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    
    if not bot_active() and user_id != OWNER_ID:
        bot.send_message(user_id, "The bot is currently stopped for maintenance. Please check back later.")
        return
        
    if call.data == 'check_join':
        if is_member_of_channels(user_id):
            if has_clicked_social(user_id):
                bot.edit_message_text("Thank you! Please use the menu below.", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
            else:
                social_links = get_social_links()
                markup = InlineKeyboardMarkup()
                for social_id, description, link in social_links:
                    markup.add(InlineKeyboardButton(description, url=link))
                markup.add(InlineKeyboardButton("✅ I have clicked", callback_data='check_social'))
                bot.edit_message_text("Great! Now, please follow our social media accounts to continue:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "You have not joined all channels yet!")

    elif call.data == 'check_social':
        # This will need to be refined as you can't verify a click, just that they've clicked the button
        social_links = get_social_links()
        if social_links:
            for social_id, _, _ in social_links:
                cursor.execute("INSERT OR IGNORE INTO social_clicks (user_id, social_id, clicked_at) VALUES (?,?,?)", (user_id, social_id, datetime.now().isoformat()))
                conn.commit()
        bot.edit_message_text("Thank you! Please use the menu below.", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())

    elif call.data == 'main_menu':
        bot.edit_message_text("Welcome back! Please use the menu below.", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())

    elif call.data == 'daily_bonus':
        bonus_amount = float(get_setting("bonus_amount"))
        bonus_cooldown = float(get_setting("bonus_cooldown"))
        
        cursor.execute("SELECT last_bonus, refer_activated FROM users WHERE user_id=?", (user_id,))
        user = cursor.fetchone()
        last_bonus_str = user[0]
        refer_activated = user[1]
        
        can_claim = False
        if not last_bonus_str:
            can_claim = True
        else:
            last_bonus_time = datetime.fromisoformat(last_bonus_str)
            if datetime.now() >= last_bonus_time + timedelta(hours=bonus_cooldown):
                can_claim = True

        if can_claim:
            cursor.execute("UPDATE users SET balance = balance + ?, last_bonus=? WHERE user_id=?", (bonus_amount, datetime.now().isoformat(), user_id))
            
            # Activate referral system for the user after first bonus claim
            if not refer_activated:
                cursor.execute("UPDATE users SET refer_activated=1 WHERE user_id=?", (user_id,))
            
            conn.commit()
            currency = get_setting("currency") or "USD"
            bot.edit_message_text(f"✅ You have claimed your daily bonus of {bonus_amount} {currency}!", call.message.chat.id, call.message.message_id, reply_markup=back_to_menu_keyboard())
        else:
            last_bonus_time = datetime.fromisoformat(last_bonus_str)
            next_claim_time = last_bonus_time + timedelta(hours=bonus_cooldown)
            time_left = next_claim_time - datetime.now()
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            bot.answer_callback_query(call.id, f"You can claim your next bonus in {int(hours)}h {int(minutes)}m.")
            
    elif call.data == 'refer_earn':
        refer_amount = float(get_setting("refer_amount"))
        cursor.execute("SELECT refer_activated FROM users WHERE user_id=?", (user_id,))
        refer_activated = cursor.fetchone()[0]
        
        if not refer_activated:
            bot.answer_callback_query(call.id, "You must claim your daily bonus first to unlock your referral link!")
            return
            
        bot_username = bot.get_me().username
        refer_link = f"https://t.me/{bot_username}?start={user_id}"
        message_text = (
            f"🔗 Your unique referral link:\n"
            f"`{refer_link}`\n\n"
            f"Share this link with your friends. For every friend who joins the bot and claims their first daily bonus, you will receive {refer_amount} {get_setting('currency') or 'USD'}!"
        )
        bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

    elif call.data == 'my_account':
        cursor.execute("SELECT balance, wallet_address FROM users WHERE user_id=?", (user_id,))
        balance, wallet_address = cursor.fetchone()
        currency = get_setting("currency") or "USD"
        
        wallet_status = "Not set"
        if wallet_address:
            wallet_status = f"✅ Set: `{wallet_address}`"
            
        message_text = (
            f"📊 **My Account Details**\n\n"
            f"🆔 User ID: `{user_id}`\n"
            f"💰 Balance: `{balance:.2f} {currency}`\n"
            f"👛 Wallet Address: {wallet_status}"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Set/Change Wallet Address", callback_data='set_wallet'))
        markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu'))
        bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        
    elif call.data == 'set_wallet':
        bot.send_message(user_id, "Please reply with your cryptocurrency wallet address:")
        bot.register_next_step_handler(call.message, process_wallet_address)
        
    elif call.data == 'bot_status':
        cursor.execute("SELECT COUNT(*) FROM users")
        total_members = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(amount) FROM withdrawals WHERE status='paid'")
        total_paid_withdrawals = cursor.fetchone()[0] or 0
        
        start_time_str = get_setting("bot_start_time")
        if not start_time_str:
            start_time = datetime.now()
            set_setting("bot_start_time", start_time.isoformat())
        else:
            start_time = datetime.fromisoformat(start_time_str)

        uptime = datetime.now() - start_time
        days, seconds = uptime.days, uptime.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        message_text = (
            f"📊 **Bot Statistics**\n\n"
            f"👥 Total Members: `{total_members}`\n"
            f"💵 Total Paid Withdrawals: `{total_paid_withdrawals:.2f} {get_setting('currency') or 'USD'}`\n"
            f"⏰ Bot Uptime: `{days}d {hours}h {minutes}m`"
        )
        bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

    # ==== ADMIN PANEL CALLS ====
    elif call.data == 'admin_panel':
        if not is_admin(user_id):
            return
        bot.edit_message_text("Welcome to the Admin Panel. Select an option below:", call.message.chat.id, call.message.message_id, reply_markup=admin_main_menu_keyboard())
    
    # User Management
    elif call.data == 'admin_user_management':
        if not is_admin(user_id): return
        bot.edit_message_text("User Management options:", call.message.chat.id, call.message.message_id, reply_markup=admin_user_management_keyboard())
    
    # Admin settings sub-menu
    elif call.data == 'admin_settings':
        if not is_admin(user_id): return
        bot.edit_message_text("Bot Settings:", call.message.chat.id, call.message.message_id, reply_markup=admin_settings_keyboard())
        
    # Set Bonus Amount
    elif call.data == 'set_bonus_amount':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Please send the new bonus amount (e.g., 0.5):")
        bot.register_next_step_handler(msg, process_set_bonus_amount)
        
    # Set Referral Amount
    elif call.data == 'set_refer_amount':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Please send the new referral amount (e.g., 0.2):")
        bot.register_next_step_handler(msg, process_set_refer_amount)

    # Set Currency
    elif call.data == 'set_currency':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Please send the new currency symbol (e.g., USDT, TRX, BNB):")
        bot.register_next_step_handler(msg, process_set_currency)

    # Start/Stop Bot
    elif call.data == 'start_stop_bot':
        if not is_admin(user_id): return
        status = get_setting("bot_status")
        new_status = "stopped" if status == "running" else "running"
        set_setting("bot_status", new_status)
        
        bot.edit_message_text(f"Bot is now {new_status}.", call.message.chat.id, call.message.message_id, reply_markup=admin_settings_keyboard())
        
        # Broadcast the change
        cursor.execute("SELECT user_id FROM users")
        all_users = [row[0] for row in cursor.fetchall()]
        for uid in all_users:
            try:
                if new_status == "stopped":
                    bot.send_message(uid, "📢 The bot has been temporarily stopped for maintenance. Please check back later.")
                else:
                    bot.send_message(uid, "🎉 The bot is now online and fully operational!")
            except Exception as e:
                print(f"Could not send message to {uid}: {e}")
                
    # Handle withdrawal status changes
    elif call.data.startswith('set_status_'):
        if not is_admin(user_id): return
        parts = call.data.split('_')
        new_status = parts[2]
  
