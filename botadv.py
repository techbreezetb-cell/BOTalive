# bot.py - Generic Telegram Bot Framework
import telebot
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==== BOT CONFIG ====
BOT_TOKEN = os.getenv("8136580879:AAG_LCUUQhctxfnUspJoFNU-KHmmzIQNamE")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")

try:
    OWNER_ID = int(os.getenv("8126299341"))
except (TypeError, ValueError):
    raise ValueError("OWNER_ID not found or invalid in environment variables")

bot = telebot.TeleBot(BOT_TOKEN)

# ==== DATABASE SETUP ====
conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

# Generic tables for any bot type
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance REAL DEFAULT 0,
    referrer INTEGER,
    last_claim TEXT,
    is_blocked INTEGER DEFAULT 0,
    wallet_address TEXT,
    refer_activated INTEGER DEFAULT 0,
    custom_field1 TEXT,
    custom_field2 TEXT
)
""")

cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
cursor.execute("""
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_name TEXT,
    channel_id TEXT,
    type TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS social_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link TEXT,
    description TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS social_clicks (
    user_id INTEGER,
    social_id INTEGER,
    clicked_at TEXT,
    PRIMARY KEY (user_id, social_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    type TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    custom_field1 TEXT,
    custom_field2 TEXT
)
""")

cursor.execute("CREATE TABLE IF NOT EXISTS bot_stats (key TEXT PRIMARY KEY, value TEXT)")
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

def add_user_if_not_exists(user_id, username, first_name):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?,?,?)", (user_id, username, first_name))
    conn.commit()

def get_join_channels():
    cursor.execute("SELECT channel_name, channel_id FROM channels WHERE type='join'")
    return cursor.fetchall()

def get_social_links():
    cursor.execute("SELECT id, description, link FROM social_links")
    return cursor.fetchall()

def is_member_of_channels(user_id):
    channels = get_join_channels()
    for channel_name, channel_id in channels:
        try:
            member = bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except:
            return False
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

# ==== MESSAGE PROCESSORS ====
def process_wallet_address(message):
    user_id = message.from_user.id
    wallet_address = message.text.strip()
    
    cursor.execute("UPDATE users SET wallet_address=? WHERE user_id=?", (wallet_address, user_id))
    conn.commit()
    
    bot.send_message(user_id, f"✅ Wallet address updated successfully!", reply_markup=back_to_menu_keyboard())

def process_support_message(message):
    user_id = message.from_user.id
    support_message = message.text
    
    cursor.execute("INSERT INTO support (user_id, message, time) VALUES (?,?,?)", 
                  (user_id, support_message, datetime.now().isoformat()))
    conn.commit()
    
    # Notify owner/admin
    try:
        bot.send_message(OWNER_ID, f"New support message from {user_id}:\n\n{support_message}")
    except:
        pass  # Owner might have blocked the bot
    
    bot.send_message(user_id, "✅ Your message has been sent to support. We'll get back to you soon!", reply_markup=back_to_menu_keyboard())

def process_withdrawal(message, wallet_address, balance):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
    except ValueError:
        bot.send_message(user_id, "❌ Invalid amount. Please try again.", reply_markup=back_to_menu_keyboard())
        return
    
    min_withdraw = float(get_setting("min_withdraw") or 1.0)
    max_withdraw = float(get_setting("max_withdraw") or 1000.0)
    currency = get_setting("currency") or "coins"
    
    if amount < min_withdraw:
        bot.send_message(user_id, f"❌ Minimum withdrawal is {min_withdraw} {currency}", reply_markup=back_to_menu_keyboard())
        return
    
    if amount > max_withdraw:
        bot.send_message(user_id, f"❌ Maximum withdrawal is {max_withdraw} {currency}", reply_markup=back_to_menu_keyboard())
        return
    
    if amount > balance:
        bot.send_message(user_id, "❌ Insufficient balance", reply_markup=back_to_menu_keyboard())
        return
    
    # Create withdrawal transaction
    cursor.execute("INSERT INTO transactions (user_id, amount, type, created_at, custom_field1) VALUES (?,?,?,?,?)",
                  (user_id, amount, "withdrawal", datetime.now().isoformat(), wallet_address))
    transaction_id = cursor.lastrowid
    
    # Deduct from user balance
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    
    # Notify admin for approval
    try:
        admin_msg = f"New withdrawal request:\nUser: {user_id}\nAmount: {amount} {currency}\nWallet: {wallet_address}"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Approve", callback_data=f"approve_withdrawal_{transaction_id}"))
        bot.send_message(OWNER_ID, admin_msg, reply_markup=markup)
    except:
        pass  # Owner might have blocked the bot
    
    bot.send_message(user_id, f"✅ Withdrawal request for {amount} {currency} submitted successfully!", reply_markup=back_to_menu_keyboard())

# ==== KEYBOARD GENERATORS ====
def main_menu_keyboard(user_id):
    # This should be customized based on bot type
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎁 Daily Reward", callback_data='daily_reward'),
        InlineKeyboardButton("👥 Refer Friends", callback_data='refer_friends'),
        InlineKeyboardButton("💳 Withdraw", callback_data='withdraw'),
        InlineKeyboardButton("👤 My Account", callback_data='my_account'),
        InlineKeyboardButton("💬 Support", callback_data='support'),
        InlineKeyboardButton("📊 Statistics", callback_data='statistics')
    )
    return markup

def admin_main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast'),
        InlineKeyboardButton("👥 User Management", callback_data='admin_user_management'),
        InlineKeyboardButton("⚙️ Bot Settings", callback_data='admin_settings'),
        InlineKeyboardButton("💳 Manage Transactions", callback_data='admin_transactions'),
        InlineKeyboardButton("✅ Set Channels", callback_data='admin_set_channels'),
        InlineKeyboardButton("🔗 Set Social Links", callback_data='admin_set_social')
    )
    return markup

def back_to_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu'))
    return markup

# ==== COMMAND HANDLERS ====
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    add_user_if_not_exists(user_id, username, first_name)
    
    # Check bot status
    if get_setting("bot_status") == "stopped" and user_id != OWNER_ID:
        bot.send_message(user_id, "The bot is currently stopped for maintenance.")
        return

    # Check if user is blocked
    cursor.execute("SELECT is_blocked FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    if result and result[0]:
        bot.send_message(user_id, "You are blocked from using this bot.")
        return

    # Handle referral
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id != user_id:
                cursor.execute("UPDATE users SET referrer=? WHERE user_id=? AND referrer IS NULL", (referrer_id, user_id))
                conn.commit()
        except ValueError:
            pass

    # Force channel join
    channels = get_join_channels()
    if channels and not is_member_of_channels(user_id):
        markup = InlineKeyboardMarkup()
        for name, channel_id in channels:
            markup.add(InlineKeyboardButton(f"Join {name}", url=f"https://t.me/{channel_id.replace('@', '')}"))
        markup.add(InlineKeyboardButton("✅ I have joined", callback_data='check_join'))
        bot.send_message(user_id, "Please join our channels:", reply_markup=markup)
        return

    # Force social media follow
    social_links = get_social_links()
    if social_links and not has_clicked_social(user_id):
        markup = InlineKeyboardMarkup()
        for social_id, description, link in social_links:
            markup.add(InlineKeyboardButton(description, url=link))
        markup.add(InlineKeyboardButton("✅ I have clicked", callback_data='check_social'))
        bot.send_message(user_id, "Please follow our social media:", reply_markup=markup)
        return

    # Send main menu
    bot.send_message(user_id, "Welcome! Use the menu below:", reply_markup=main_menu_keyboard(user_id))

# ==== CALLBACK HANDLERS ====
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    try:
        user_id = call.from_user.id
        
        # Check bot status
        if get_setting("bot_status") == "stopped" and user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "Bot is under maintenance.")
            return

        # Check if user is blocked
        cursor.execute("SELECT is_blocked FROM users WHERE user_id=?", (user_id,))
        result = cursor.fetchone()
        if result and result[0]:
            bot.answer_callback_query(call.id, "You are blocked.")
            return

        # Handle different callbacks
        if call.data == 'check_join':
            if is_member_of_channels(user_id):
                if has_clicked_social(user_id):
                    bot.edit_message_text("Thank you! Menu below:", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard(user_id))
                else:
                    social_links = get_social_links()
                    markup = InlineKeyboardMarkup()
                    for social_id, description, link in social_links:
                        markup.add(InlineKeyboardButton(description, url=link))
                    markup.add(InlineKeyboardButton("✅ I have clicked", callback_data='check_social'))
                    bot.edit_message_text("Now follow our social media:", call.message.chat.id, call.message.message_id, reply_markup=markup)
            else:
                bot.answer_callback_query(call.id, "Join all channels first!")

        elif call.data == 'check_social':
            social_links = get_social_links()
            if social_links:
                for social_id, _, _ in social_links:
                    cursor.execute("INSERT OR IGNORE INTO social_clicks (user_id, social_id, clicked_at) VALUES (?,?,?)", 
                                  (user_id, social_id, datetime.now().isoformat()))
                    conn.commit()
            bot.edit_message_text("Thank you! Menu below:", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard(user_id))

        elif call.data == 'main_menu':
            bot.edit_message_text("Welcome back! Menu below:", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard(user_id))

        elif call.data == 'daily_reward':
            # This should be customized based on bot type
            reward_amount = float(get_setting("reward_amount") or 1.0)
            reward_cooldown = float(get_setting("reward_cooldown") or 24)
            
            cursor.execute("SELECT last_claim, refer_activated, referrer FROM users WHERE user_id=?", (user_id,))
            result = cursor.fetchone()
            if not result:
                bot.answer_callback_query(call.id, "User not found.")
                return
                
            last_claim_str, refer_activated, referrer_id = result
            
            can_claim = False
            if not last_claim_str:
                can_claim = True
            else:
                last_claim_time = datetime.fromisoformat(last_claim_str)
                if datetime.now() >= last_claim_time + timedelta(hours=reward_cooldown):
                    can_claim = True

            if can_claim:
                cursor.execute("UPDATE users SET balance = balance + ?, last_claim=? WHERE user_id=?", 
                              (reward_amount, datetime.now().isoformat(), user_id))
                
                # Handle referral reward
                if not refer_activated:
                    cursor.execute("UPDATE users SET refer_activated=1 WHERE user_id=?", (user_id,))
                    if referrer_id:
                        refer_amount = float(get_setting("refer_amount") or 0.5)
                        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (refer_amount, referrer_id))
                
                conn.commit()
                currency = get_setting("currency") or "coins"
                bot.edit_message_text(f"✅ Claimed {reward_amount} {currency}!", call.message.chat.id, call.message.message_id, reply_markup=back_to_menu_keyboard())
            else:
                last_claim_time = datetime.fromisoformat(last_claim_str)
                next_claim = last_claim_time + timedelta(hours=reward_cooldown)
                time_left = next_claim - datetime.now()
                hours, remainder = divmod(time_left.seconds, 3600)
                minutes = remainder // 60
                bot.answer_callback_query(call.id, f"Next reward in {hours}h {minutes}m")

        elif call.data == 'refer_friends':
            cursor.execute("SELECT refer_activated FROM users WHERE user_id=?", (user_id,))
            result = cursor.fetchone()
            if not result:
                bot.answer_callback_query(call.id, "User not found.")
                return
                
            if not result[0]:
                bot.answer_callback_query(call.id, "Claim your first reward first!")
                return
                
            refer_amount = float(get_setting("refer_amount") or 0.5)
            bot_username = bot.get_me().username
            refer_link = f"https://t.me/{bot_username}?start={user_id}"
            message_text = (
                f"👥 Your referral link:\n"
                f"`{refer_link}`\n\n"
                f"Get {refer_amount} {get_setting('currency') or 'coins'} per referral!"
            )
            bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

        elif call.data == 'my_account':
            cursor.execute("SELECT balance, wallet_address FROM users WHERE user_id=?", (user_id,))
            result = cursor.fetchone()
            if not result:
                bot.answer_callback_query(call.id, "User not found.")
                return
                
            balance, wallet_address = result
            currency = get_setting("currency") or "coins"
            
            wallet_status = "Not set" if not wallet_address else f"✅ `{wallet_address}`"
            
            message_text = (
                f"👤 **Account Details**\n\n"
                f"🆔 User ID: `{user_id}`\n"
                f"💰 Balance: `{balance:.2f} {currency}`\n"
                f"👛 Wallet: {wallet_status}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Set/Change Wallet", callback_data='set_wallet'))
            markup.add(InlineKeyboardButton("🔙 Back", callback_data='main_menu'))
            bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

        elif call.data == 'set_wallet':
            msg = bot.send_message(user_id, "Send your wallet address:")
            bot.register_next_step_handler(msg, process_wallet_address)

        elif call.data == 'support':
            msg = bot.send_message(user_id, "Send your support message:")
            bot.register_next_step_handler(msg, process_support_message)
            
        elif call.data == 'statistics':
            cursor.execute("SELECT COUNT(*) FROM users")
            total_members = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(amount) FROM transactions WHERE status='completed'")
            total_distributed = cursor.fetchone()[0] or 0
            
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
                f"💰 Total Distributed: `{total_distributed:.2f} {get_setting('currency') or 'coins'}`\n"
                f"⏰ Uptime: `{days}d {hours}h {minutes}m`"
            )
            bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=back_to_menu_keyboard(), parse_mode='Markdown')

        elif call.data == 'withdraw':
            cursor.execute("SELECT balance, wallet_address FROM users WHERE user_id=?", (user_id,))
            result = cursor.fetchone()
            if not result:
                bot.answer_callback_query(call.id, "User not found.")
                return
                
            balance, wallet_address = result
            
            if not wallet_address:
                bot.send_message(user_id, "Please set your wallet address first!", reply_markup=back_to_menu_keyboard())
                return
                
            min_withdraw = float(get_setting("min_withdraw") or 1.0)
            currency = get_setting("currency") or "coins"
            
            message_text = (
                f"💳 **Withdraw Funds**\n\n"
                f"💰 Balance: `{balance:.2f} {currency}`\n"
                f"👛 Wallet: `{wallet_address}`\n\n"
                f"Minimum withdrawal: `{min_withdraw} {currency}`\n"
                f"Send the amount you want to withdraw:"
            )
            
            msg = bot.send_message(user_id, message_text, parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_withdrawal, wallet_address, balance)

        # ==== ADMIN PANEL CALLS ====
        elif call.data == 'admin_panel':
            if not is_admin(user_id): 
                bot.answer_callback_query(call.id, "Access denied.")
                return
            bot.edit_message_text("Admin Panel:", call.message.chat.id, call.message.message_id, reply_markup=admin_main_menu_keyboard())
        
        # Add more admin handlers here as needed

    except Exception as e:
        print(f"Error in callback handler: {e}")
        bot.answer_callback_query(call.id, "An error occurred. Please try again.")

# ==== MESSAGE HANDLERS ====
@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "Access denied.")
        return
    bot.send_message(user_id, "Admin Panel:", reply_markup=admin_main_menu_keyboard())

# ==== START BOT ====
if __name__ == "__main__":
    print("Bot is running...")
    bot.polling(none_stop=True)
