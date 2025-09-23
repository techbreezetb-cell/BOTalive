# bot.py - Final, Fixed, and Fully Functional Version
import telebot
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, timedelta
import re
import os
import requests

# ==== BOT CONFIG ====
BOT_TOKEN = "8136580879:AAHgjjLOGc3LqAaVoU-MiSo0wf0JNOoxjIs"
OWNER_ID = 8126299341

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
    refer_activated INTEGER DEFAULT 0,
    ip_address TEXT,
    device_id TEXT
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
    cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
    is_new = cursor.fetchone() is None
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?,?,?)", (user_id, username, first_name))
    conn.commit()
    return is_new

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
    if not channels:
        return True # No channels to join, so user can proceed
    for channel_name, channel_id in channels:
        try:
            member = bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except telebot.apihelper.ApiException as e:
            if "not an administrator" in str(e):
                bot.send_message(OWNER_ID, f"⚠️ **Warning:** Bot is not an administrator in channel `{channel_id}`. Please add the bot as an admin to check membership.\n\n_Note: This check is being treated as 'failed' for User {user_id}._", parse_mode='Markdown')
                return False
            else:
                print(f"Could not check membership for channel {channel_id}: {e}")
                return False # Failsafe
    return True

def has_clicked_social(user_id):
    links = get_social_links()
    if not links:
        return True
    for social_id, _, _ in links:
        cursor.execute("SELECT 1 FROM social_clicks WHERE user_id=? AND social_id=?", (user_id, social_id))
        if cursor.fetchone() is None:
            return False
    return True

def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

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
        InlineKeyboardButton("💰 Add Balance", callback_data='admin_add_balance'),
        InlineKeyboardButton("💵 Remove Balance", callback_data='admin_remove_balance'),
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

    is_new_user = add_user_if_not_exists(user_id, username, first_name)
    
    if is_new_user:
        bot.send_message(OWNER_ID, f"🎉 New user joined!\n\nUser: {get_user_link(user_id)}\nID: `{user_id}`", parse_mode='Markdown')

    if not bot_active() and user_id != OWNER_ID:
        bot.send_message(user_id, "The bot is currently stopped for maintenance. Please check back later.")
        return

    cursor.execute("SELECT is_blocked FROM users WHERE user_id=?", (user_id,))
    is_blocked = cursor.fetchone()[0]
    if is_blocked:
        bot.send_message(user_id, "You are currently blocked from using this bot.")
        return

    referrer_id = None
    if message.text.startswith("/start "):
        referrer_id_str = message.text.split(" ")[1]
        if referrer_id_str.isdigit():
            referrer_id = int(referrer_id_str)
            if referrer_id != user_id:
                cursor.execute("UPDATE users SET referrer=? WHERE user_id=? AND referrer IS NULL", (referrer_id, user_id))
                conn.commit()

    channels = get_join_channels()
    if channels and not is_member_of_channels(user_id):
        markup = InlineKeyboardMarkup()
        for name, channel_id in channels:
            markup.add(InlineKeyboardButton(f"Join {name}", url=f"https://t.me/{channel_id.replace('@', '')}"))
        markup.add(InlineKeyboardButton("✅ I have joined", callback_data='check_join'))
        bot.send_message(user_id, "Please join the following channels to continue:", reply_markup=markup)
        return

    social_links = get_social_links()
    if social_links and not has_clicked_social(user_id):
        markup = InlineKeyboardMarkup()
        for social_id, description, link in social_links:
            markup.add(InlineKeyboardButton(description, url=link))
        markup.add(InlineKeyboardButton("✅ I have clicked", callback_data='check_social'))
        bot.send_message(user_id, "Please follow our social media accounts to continue:", reply_markup=markup)
        return
    
    bot.send_message(user_id, "Welcome! Please use the menu below to get started.", reply_markup=main_menu_keyboard())


# ==== CALLBACK HANDLERS ====
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    
    # Persistent Channel Check at the start of every button press
    channels = get_join_channels()
    if channels and not is_member_of_channels(user_id):
        markup = InlineKeyboardMarkup()
        for name, channel_id in channels:
            markup.add(InlineKeyboardButton(f"Join {name}", url=f"https://t.me/{channel_id.replace('@', '')}"))
        markup.add(InlineKeyboardButton("✅ I have joined", callback_data='check_join'))
        bot.send_message(user_id, "Please join the following channels to continue:", reply_markup=markup)
        bot.answer_callback_query(call.id) # Answer the callback to prevent a frozen button
        return

    if not bot_active() and user_id != OWNER_ID:
        bot.send_message(user_id, "The bot is currently stopped for maintenance. Please check back later.")
        return

    cursor.execute("SELECT is_blocked FROM users WHERE user_id=?", (user_id,))
    is_blocked = cursor.fetchone()[0]
    if is_blocked:
        bot.answer_callback_query(call.id, "You are currently blocked from using this bot.")
        return
        
    if call.data == 'check_join':
        if is_member_of_channels(user_id):
            social_links = get_social_links()
            if social_links and not has_clicked_social(user_id):
                markup = InlineKeyboardMarkup()
                for social_id, description, link in social_links:
                    markup.add(InlineKeyboardButton(description, url=link))
                markup.add(InlineKeyboardButton("✅ I have clicked", callback_data='check_social'))
                bot.edit_message_text("Great! Now, please follow our social media accounts to continue:", call.message.chat.id, call.message.message_id, reply_markup=markup)
            else:
                bot.edit_message_text("Thank you! Please use the menu below.", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
        else:
            bot.answer_callback_query(call.id, "You have not joined all channels yet!")
            bot.send_message(user_id, "Join the channels and click 'I have joined' again to continue.")

    elif call.data == 'check_social':
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
        
        cursor.execute("SELECT last_bonus, refer_activated, referrer FROM users WHERE user_id=?", (user_id,))
        user = cursor.fetchone()
        last_bonus_str = user[0]
        refer_activated = user[1]
        referrer_id = user[2]
        
        can_claim = False
        if not last_bonus_str:
            can_claim = True
        else:
            last_bonus_time = datetime.fromisoformat(last_bonus_str)
            if datetime.now() >= last_bonus_time + timedelta(hours=bonus_cooldown):
                can_claim = True

        if can_claim:
            cursor.execute("UPDATE users SET balance = balance + ?, last_bonus=? WHERE user_id=?", (bonus_amount, datetime.now().isoformat(), user_id))
            
            if not refer_activated:
                cursor.execute("UPDATE users SET refer_activated=1 WHERE user_id=?", (user_id,))
                if referrer_id:
                    refer_amount = float(get_setting("refer_amount"))
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (refer_amount, referrer_id))
            
            conn.commit()
            currency = get_setting("currency")
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
            f"Share this link with your friends. For every friend who joins the bot and claims their first daily bonus, you will receive {refer_amount} {get_setting('currency')}!"
        )
        bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

    elif call.data == 'my_account':
        cursor.execute("SELECT balance, wallet_address FROM users WHERE user_id=?", (user_id,))
        balance, wallet_address = cursor.fetchone()
        currency = get_setting("currency")
        
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

    elif call.data == 'chat_support':
        bot.send_message(user_id, "Please send your support message. An admin will get back to you soon.")
        bot.register_next_step_handler(call.message, process_support_message)
        
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
            f"💵 Total Paid Withdrawals: `{total_paid_withdrawals:.2f} {get_setting('currency')}`\n"
            f"⏰ Bot Uptime: `{days}d {hours}h {minutes}m`"
        )
        bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

    # ==== ADMIN PANEL CALLS ====
    elif call.data == 'admin_panel':
        if not is_admin(user_id): return
        bot.edit_message_text("Welcome to the Admin Panel. Select an option below:", call.message.chat.id, call.message.message_id, reply_markup=admin_main_menu_keyboard())
    
    elif call.data == 'admin_user_management':
        if not is_admin(user_id): return
        bot.edit_message_text("User Management options:", call.message.chat.id, call.message.message_id, reply_markup=admin_user_management_keyboard())

    elif call.data == 'admin_add_balance':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Enter user ID and amount to add (e.g., 123456789 50.5):")
        bot.register_next_step_handler(msg, process_add_balance_by_admin)

    elif call.data == 'admin_remove_balance':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Enter user ID and amount to remove (e.g., 123456789 10):")
        bot.register_next_step_handler(msg, process_remove_balance_by_admin)

    elif call.data == 'admin_settings':
        if not is_admin(user_id): return
        bot.edit_message_text("Bot Settings:", call.message.chat.id, call.message.message_id, reply_markup=admin_settings_keyboard())
        
    elif call.data == 'admin_broadcast':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Please send the message you want to broadcast to all users:")
        bot.register_next_step_handler(msg, process_broadcast)

    elif call.data == 'admin_withdrawals':
        if not is_admin(user_id): return
        cursor.execute("SELECT id, user_id, amount, status FROM withdrawals WHERE status != 'paid' ORDER BY requested_at DESC")
        withdrawals = cursor.fetchall()
        
        if not withdrawals:
            bot.edit_message_text("No pending or paying withdrawals found.", call.message.chat.id, call.message.message_id, reply_markup=admin_main_menu_keyboard())
            return
            
        message_text = "Pending and Paying Withdrawals:\n\n"
        markup = InlineKeyboardMarkup()
        for wid, uid, amount, status in withdrawals:
            user_link = get_user_link(uid)
            message_text += f"ID: {wid} | User: {user_link} | Amount: {amount} {get_setting('currency')} | Status: {status.capitalize()}\n"
            markup.add(InlineKeyboardButton(f"Manage Withdrawal #{wid}", callback_data=f'manage_withdrawal_{wid}'))
            
        markup.add(InlineKeyboardButton("🔙 Back to Admin Menu", callback_data='admin_panel'))
        bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        
    elif call.data.startswith('manage_withdrawal_'):
        if not is_admin(user_id): return
        withdrawal_id = int(call.data.split('_')[2])
        
        cursor.execute("SELECT amount, status, user_id, wallet_address FROM withdrawals WHERE id=?", (withdrawal_id,))
        withdrawal = cursor.fetchone()
        
        if not withdrawal:
            bot.answer_callback_query(call.id, "Withdrawal not found!")
            return
            
        amount, status, uid, wallet = withdrawal
        user_link = get_user_link(uid)
        currency = get_setting("currency")
        
        message_text = (
            f"**Managing Withdrawal #{withdrawal_id}**\n\n"
            f"User: {user_link}\n"
            f"Amount: `{amount} {currency}`\n"
            f"Wallet: `{wallet}`\n"
            f"Current Status: `{status.capitalize()}`"
        )
        
        bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=admin_withdrawal_status_keyboard(withdrawal_id), parse_mode='Markdown')
    
    elif call.data.startswith('set_status_'):
        if not is_admin(user_id): return
        parts = call.data.split('_')
        new_status = parts[2]
        withdrawal_id = int(parts[3])
        
        cursor.execute("SELECT user_id, amount, wallet_address, channel_chat_id, channel_message_id FROM withdrawals WHERE id=?", (withdrawal_id,))
        withdrawal = cursor.fetchone()
        
        if withdrawal:
            user_id_to_notify, amount, wallet, channel_chat_id, channel_message_id = withdrawal
            
            cursor.execute("UPDATE withdrawals SET status=? WHERE id=?", (new_status, withdrawal_id))
            conn.commit()
            
            currency = get_setting("currency")
            message_to_user = f"✅ Your withdrawal request of {amount} {currency} has been updated to status: **{new_status.capitalize()}**."
            if new_status == 'paid':
                message_to_user += "\n\nThe amount has been sent to your wallet."
            try:
                bot.send_message(user_id_to_notify, message_to_user, parse_mode='Markdown')
            except telebot.apihelper.ApiException:
                pass
            
            if channel_chat_id and channel_message_id:
                user_link = get_user_link(user_id_to_notify)
                
                status_text = f"Status: `{new_status.capitalize()}`"
                
                message_for_channel = (
                    f"**💰 New Withdrawal Request**\n\n"
                    f"User: {user_link}\n"
                    f"Amount: `{amount} {currency}`\n"
                    f"Wallet: `{wallet}`\n"
                    f"{status_text}\n"
                    f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                )
                try:
                    bot.edit_message_text(message_for_channel, channel_chat_id, channel_message_id, parse_mode='Markdown', disable_web_page_preview=True)
                except Exception as e:
                    print(f"Could not edit message in channel: {e}")
                    
            bot.edit_message_text(f"Withdrawal #{withdrawal_id} status updated to {new_status}.", call.message.chat.id, call.message.message_id, reply_markup=admin_main_menu_keyboard())

    elif call.data == 'set_bonus_amount':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Please send the new bonus amount:")
        bot.register_next_step_handler(msg, process_set_bonus_amount)

    elif call.data == 'set_refer_amount':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Please send the new referral amount:")
        bot.register_next_step_handler(msg, process_set_refer_amount)

    elif call.data == 'set_withdraw_min_max':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Please send the minimum and maximum withdrawal amounts separated by a space (e.g., 10 1000):")
        bot.register_next_step_handler(msg, process_set_withdraw_min_max)
        
    elif call.data == 'set_currency':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "Please send the new currency (e.g., USDT):")
        bot.register_next_step_handler(msg, process_set_currency)

    elif call.data == 'start_stop_bot':
        if not is_admin(user_id): return
        current_status = get_setting("bot_status")
        new_status = 'stopped' if current_status == 'running' else 'running'
        set_setting('bot_status', new_status)
        bot.answer_callback_query(call.id, f"Bot status changed to {new_status}.")
        bot.edit_message_text(f"Bot status is now **{new_status.capitalize()}**.", call.message.chat.id, call.message.message_id, reply_markup=admin_settings_keyboard(), parse_mode='Markdown')

    elif call.data == 'admin_set_channels':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "To add a channel, use `/addchannel <name> <channel_id> join`.\nTo add a withdrawal channel, use `/addchannel <name> <channel_id> withdrawal`.\nTo remove a channel, use `/removechannel <name>`.")

    elif call.data == 'admin_set_social':
        if not is_admin(user_id): return
        msg = bot.send_message(user_id, "To add a social link, use `/addsocial <description> <link>`.\nTo remove a link, use `/removesocial <description>`.")
        
# ==== WITHDRAWAL LOGIC ====
@bot.callback_query_handler(func=lambda call: call.data == 'withdraw')
def handle_withdrawal_request(call):
    user_id = call.from_user.id
    cursor.execute("SELECT balance, wallet_address FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        bot.answer_callback_query(call.id, "Please start the bot first!")
        return

    balance, wallet_address = user
    min_amount = float(get_setting("withdraw_min"))
    currency = get_setting("currency")
    
    if not wallet_address:
        bot.answer_callback_query(call.id, "Please set your wallet address first via the My Account menu.")
        return
        
    if balance < min_amount:
        bot.answer_callback_query(call.id, f"You need a minimum of {min_amount} {currency} to withdraw. Your current balance is {balance} {currency}.")
        return

    msg = bot.send_message(user_id, f"Your balance is {balance} {currency}. How much would you like to withdraw? (Min: {min_amount} {currency})")
    bot.register_next_step_handler(msg, process_withdrawal_amount)
    
def process_withdrawal_amount(message):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        if amount <= 0:
            bot.send_message(user_id, "Please enter a positive number.")
            return
            
        min_amount = float(get_setting("withdraw_min"))
        max_amount = float(get_setting("withdraw_max"))
        
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        balance = cursor.fetchone()[0]
        
        if amount < min_amount or amount > max_amount:
            bot.send_message(user_id, f"The amount must be between {min_amount} and {max_amount}.")
            return
            
        if amount > balance:
            bot.send_message(user_id, "You do not have enough balance for this withdrawal.")
            return

        cursor.execute("SELECT wallet_address FROM users WHERE user_id=?", (user_id,))
        wallet_address = cursor.fetchone()[0]
        
        if not wallet_address:
             bot.send_message(user_id, "Please set your wallet address first via the My Account menu.")
             return
        
        cursor.execute("INSERT INTO withdrawals (user_id, amount, requested_at, wallet_address, status) VALUES (?,?,?,?,?)", (user_id, amount, datetime.now().isoformat(), wallet_address, 'pending'))
        withdrawal_id = cursor.lastrowid
        conn.commit()
        
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
        conn.commit()
        
        new_balance = get_balance(user_id)

        owner_message = (
            f"**💰 New Withdrawal Request**\n\n"
            f"ID: `{withdrawal_id}`\n"
            f"User: {get_user_link(user_id)}\n"
            f"Amount: `{amount} {get_setting('currency')}`\n"
            f"Wallet: `{wallet_address}`\n"
            f"User Left Balance: `{new_balance:.2f} {get_setting('currency')}`\n"
            f"Status: `Pending`\n"
            f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        markup = admin_withdrawal_status_keyboard(withdrawal_id)
        
        withdrawal_channel_id = get_withdrawal_channel_id()
        if withdrawal_channel_id:
            try:
                channel_msg = bot.send_message(withdrawal_channel_id, owner_message, parse_mode='Markdown', reply_markup=markup, disable_web_page_preview=True)
                cursor.execute("UPDATE withdrawals SET channel_chat_id=?, channel_message_id=? WHERE id=?", (channel_msg.chat.id, channel_msg.message_id, withdrawal_id))
                conn.commit()
            except telebot.apihelper.ApiException as e:
                bot.send_message(user_id, "Error posting to withdrawal channel. Please check bot permissions or channel ID.")
                print(f"Error posting to withdrawal channel: {e}")
        
        bot.send_message(user_id, f"✅ Your withdrawal request of {amount} {get_setting('currency')} has been submitted and is awaiting admin approval.")

    except ValueError:
        bot.send_message(user_id, "Invalid amount. Please send a valid number.")

def process_wallet_address(message):
    user_id = message.from_user.id
    wallet_address = message.text.strip()
    
    if not wallet_address:
        bot.send_message(user_id, "Wallet address cannot be empty. Please try again.")
        return
        
    cursor.execute("UPDATE users SET wallet_address=? WHERE user_id=?", (wallet_address, user_id))
    conn.commit()
    bot.send_message(user_id, "✅ Your wallet address has been saved successfully!", reply_markup=main_menu_keyboard())

def process_support_message(message):
    user_id = message.from_user.id
    support_message = message.text
    
    cursor.execute("INSERT INTO support (user_id, message, time) VALUES (?,?,?)", (user_id, support_message, datetime.now().isoformat()))
    conn.commit()
    
    bot.send_message(user_id, "✅ Your message has been sent to the support team. We will get back to you as soon as possible.", reply_markup=main_menu_keyboard())
    bot.send_message(OWNER_ID, f"**New Support Message from {get_user_link(user_id)}**:\n\n`{support_message}`", parse_mode='Markdown')
    bot.send_message(OWNER_ID, "Reply to this message with /reply <user_id> <your_message>")

def process_broadcast(message):
    user_id = message.from_user.id
    broadcast_text = message.text
    
    cursor.execute("SELECT user_id FROM users WHERE is_blocked=0")
    all_users = [row[0] for row in cursor.fetchall()]
    
    sent_count = 0
    for uid in all_users:
        try:
            bot.send_message(uid, broadcast_text)
            sent_count += 1
        except Exception:
            pass
            
    bot.send_message(user_id, f"✅ Broadcast sent to {sent_count} users.")

def process_set_bonus_amount(message):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        set_setting('bonus_amount', amount)
        bot.send_message(user_id, f"✅ Bonus amount set to {amount}.", reply_markup=admin_settings_keyboard())
    except ValueError:
        bot.send_message(user_id, "Invalid amount. Please send a valid number.")

def process_set_refer_amount(message):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        set_setting('refer_amount', amount)
        bot.send_message(user_id, f"✅ Referral amount set to {amount}.", reply_markup=admin_settings_keyboard())
    except ValueError:
        bot.send_message(user_id, "Invalid amount. Please send a valid number.")

def process_set_withdraw_min_max(message):
    user_id = message.from_user.id
    try:
        min_amount, max_amount = map(float, message.text.split())
        set_setting('withdraw_min', min_amount)
        set_setting('withdraw_max', max_amount)
        bot.send_message(user_id, f"✅ Withdrawal limits set to Min: {min_amount}, Max: {max_amount}.", reply_markup=admin_settings_keyboard())
    except ValueError:
        bot.send_message(user_id, "Invalid format. Please send two numbers separated by a space.")

def process_set_currency(message):
    user_id = message.from_user.id
    currency = message.text.upper()
    set_setting('currency', currency)
    bot.send_message(user_id, f"✅ Currency set to {currency}.", reply_markup=admin_settings_keyboard())

def process_add_balance_by_admin(message):
    user_id = message.from_user.id
    try:
        parts = message.text.split(" ")
        user_id_to_add = int(parts[0])
        amount = float(parts[1])
        
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id_to_add))
        conn.commit()
        bot.send_message(user_id_to_add, f"✅ An admin has added {amount} {get_setting('currency')} to your balance.")
        bot.send_message(user_id, f"✅ Added {amount} to user {user_id_to_add}'s balance.", reply_markup=admin_user_management_keyboard())
    except (ValueError, IndexError):
        bot.send_message(user_id, "Invalid format. Please send user ID and amount like: 123456789 50.5")

def process_remove_balance_by_admin(message):
    user_id = message.from_user.id
    try:
        parts = message.text.split(" ")
        user_id_to_remove = int(parts[0])
        amount = float(parts[1])
        
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id_to_remove))
        conn.commit()
        bot.send_message(user_id_to_remove, f"❌ An admin has removed {amount} {get_setting('currency')} from your balance.")
        bot.send_message(user_id, f"✅ Removed {amount} from user {user_id_to_remove}'s balance.", reply_markup=admin_user_management_keyboard())
    except (ValueError, IndexError):
        bot.send_message(user_id, "Invalid format. Please send user ID and amount like: 123456789 10")


# ==== ADMIN COMMANDS ====
@bot.message_handler(commands=['admin'])
def open_admin_panel(message):
    if not is_admin(message.from_user.id): return
    bot.send_message(message.chat.id, "Welcome to the Admin Panel. Select an option below:", reply_markup=admin_main_menu_keyboard())

@bot.message_handler(commands=['reply'])
def handle_reply(message):
    if not is_admin(message.from_user.id): return
    
    try:
        parts = message.text.split(" ", 2)
        if len(parts) < 3:
            bot.reply_to(message, "Usage: /reply <user_id> <your_message>")
            return
            
        user_id_to_reply = int(parts[1])
        reply_text = parts[2]
        
        bot.send_message(user_id_to_reply, f"**📢 Admin Reply:**\n\n{reply_text}", parse_mode='Markdown')
        bot.reply_to(message, "✅ Reply sent successfully.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Invalid command format. Usage: /reply <user_id> <your_message>")

@bot.message_handler(commands=['addadmin'])
def handle_add_admin(message):
    if not is_admin(message.from_user.id): return
    try:
        user_id_to_add = int(message.text.split(" ")[1])
        add_admin(user_id_to_add)
        bot.reply_to(message, f"✅ User {user_id_to_add} added as admin.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Usage: /addadmin <user_id>")

@bot.message_handler(commands=['removeadmin'])
def handle_remove_admin(message):
    if not is_admin(message.from_user.id): return
    try:
        user_id_to_remove = int(message.text.split(" ")[1])
        remove_admin(user_id_to_remove)
        bot.reply_to(message, f"✅ User {user_id_to_remove} removed from admins.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Usage: /removeadmin <user_id>")

@bot.message_handler(commands=['block'])
def handle_block(message):
    if not is_admin(message.from_user.id): return
    
    try:
        user_id_to_block = int(message.text.split(" ")[1])
        cursor.execute("UPDATE users SET is_blocked=1 WHERE user_id=?", (user_id_to_block,))
        conn.commit()
        bot.send_message(user_id_to_block, "❌ You have been blocked by an admin.")
        bot.reply_to(message, f"✅ User {user_id_to_block} has been blocked.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Usage: /block <user_id>")

@bot.message_handler(commands=['unblock'])
def handle_unblock(message):
    if not is_admin(message.from_user.id): return
    
    try:
        user_id_to_unblock = int(message.text.split(" ")[1])
        cursor.execute("UPDATE users SET is_blocked=0 WHERE user_id=?", (user_id_to_unblock,))
        conn.commit()
        bot.send_message(user_id_to_unblock, "✅ You have been unblocked by an admin. You can now use the bot again.")
        bot.reply_to(message, f"✅ User {user_id_to_unblock} has been unblocked.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Usage: /unblock <user_id>")

@bot.message_handler(commands=['addbal'])
def handle_add_balance(message):
    if not is_admin(message.from_user.id): return
    
    try:
        parts = message.text.split(" ")
        user_id_to_add = int(parts[1])
        amount = float(parts[2])
        
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id_to_add))
        conn.commit()
        bot.send_message(user_id_to_add, f"✅ An admin has added {amount} {get_setting('currency')} to your balance.")
        bot.reply_to(message, f"✅ Added {amount} to user {user_id_to_add}'s balance.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Usage: /addbal <user_id> <amount>")

@bot.message_handler(commands=['removebal'])
def handle_remove_balance(message):
    if not is_admin(message.from_user.id): return
    
    try:
        parts = message.text.split(" ")
        user_id_to_remove = int(parts[1])
        amount = float(parts[2])
        
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id_to_remove))
        conn.commit()
        bot.send_message(user_id_to_remove, f"❌ An admin has removed {amount} {get_setting('currency')} from your balance.")
        bot.reply_to(message, f"✅ Removed {amount} from user {user_id_to_remove}'s balance.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Usage: /removebal <user_id> <amount>")

@bot.message_handler(commands=['addchannel'])
def handle_add_channel(message):
    if not is_admin(message.from_user.id): return
    try:
        parts = message.text.split(" ", 3)
        if len(parts) < 4:
            bot.reply_to(message, "Usage: /addchannel <name> <channel_id> <type>")
            return
        name, channel_id, channel_type = parts[1], parts[2], parts[3]
        cursor.execute("INSERT INTO channels (channel_name, channel_id, type) VALUES (?,?,?)", (name, channel_id, channel_type))
        conn.commit()
        bot.reply_to(message, f"✅ Channel '{name}' of type '{channel_type}' added successfully.")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")

@bot.message_handler(commands=['removechannel'])
def handle_remove_channel(message):
    if not is_admin(message.from_user.id): return
    try:
        name = message.text.split(" ", 1)[1]
        cursor.execute("DELETE FROM channels WHERE channel_name=?", (name,))
        conn.commit()
        bot.reply_to(message, f"✅ Channel '{name}' removed successfully.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Usage: /removechannel <name>")

@bot.message_handler(commands=['addsocial'])
def handle_add_social(message):
    if not is_admin(message.from_user.id): return
    try:
        parts = message.text.split(" ", 2)
        if len(parts) < 3:
            bot.reply_to(message, "Usage: /addsocial <description> <link>")
            return
        description, link = parts[1], parts[2]
        cursor.execute("INSERT INTO social_links (description, link) VALUES (?,?)", (description, link))
        conn.commit()
        bot.reply_to(message, f"✅ Social link '{description}' added successfully.")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")

@bot.message_handler(commands=['removesocial'])
def handle_remove_social(message):
    if not is_admin(message.from_user.id): return
    try:
        description = message.text.split(" ", 1)[1]
        cursor.execute("DELETE FROM social_links WHERE description=?", (description,))
        conn.commit()
        bot.reply_to(message, f"✅ Social link '{description}' removed successfully.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Usage: /removesocial <description>")

# ==== INITIAL DEFAULT SETTINGS ====
if get_setting('bot_status') is None:
    set_setting('bot_status', 'running')
if get_setting('bonus_amount') is None:
    set_setting('bonus_amount', '1.0')
if get_setting('bonus_cooldown') is None:
    set_setting('bonus_cooldown', '24')
if get_setting('refer_amount') is None:
    set_setting('refer_amount', '0.5')
if get_setting('withdraw_min') is None:
    set_setting('withdraw_min', '10.0')
if get_setting('withdraw_max') is None:
    set_setting('withdraw_max', '1000.0')
if get_setting('currency') is None:
    set_setting('currency', 'USDT')
if get_setting('bot_start_time') is None:
    set_setting('bot_start_time', datetime.now().isoformat())


print("Fully Advanced Dynamic Bot is Running...")
bot.polling(none_stop=True)