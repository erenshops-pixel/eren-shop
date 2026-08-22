from flask import render_template
from flask import (
    Flask,
    request,
    session,
    redirect,
    url_for
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from datetime import datetime

import os
import sqlite3
import requests
import json
import threading
import time
import hmac
import hashlib
import uuid


# ==================================================
# APP
# ==================================================

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "CHANGE_THIS_TO_RANDOM_SECRET_KEY")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# ==================================================
# SMILE ONE API Config
# ==================================================

# IMPORTANT: keep credentials in Railway Variables, never in GitHub.
SMILE_ONE_API_URL = "https://jcplays.com/smilecoin/api"
SMILE_ONE_UID = "70275119-162c-435b-8836-5971e82fc0fd"
SMILE_ONE_API_KEY = "9099bf7aa361fd26295ba42a30402be778922f76bdc3ad31a0cc8333118104d2"


def get_smile_one_code(amount, product_type, email=None):
    """
    Smile One API ကို ခေါ်ပြီး Code ထုတ်ယူတဲ့ Function
    product_type က "PHP" သို့မဟုတ် "BRL" ဖြစ်ရပါမယ်။
    """
    try:
        url = f"{SMILE_ONE_API_URL}/generate"   # API Endpoint
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": SMILE_ONE_API_KEY,
            "X-UID": SMILE_ONE_UID
        }
        payload = {
            "uid": SMILE_ONE_UID,
            "amount": amount,        # ဥပမာ - 280 (PHP), 30 (BRL)
            "type": product_type     # "PHP" သို့ "BRL"
        }

        # ✅ Email ရှိရင် payload ထဲ ထည့်ပါ
        if email:
            payload["email"] = email

        response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return {
                    "success": True,
                    "code": data.get("code"),      # API က ပြန်ပေးတဲ့ Code
                    "message": data.get("message")
                }
            else:
                return {"success": False, "error": data.get("message", "Unknown error")}
        else:
            return {"success": False, "error": f"API Error: {response.status_code}"}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "API request timed out (အချိန်ကုန်သွားပါတယ်)"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==================================================
# FLASH TOPUP RESELLER API Config
# ==================================================

FT_API_ID = "RSL5YP4YFXLEGL8X"
FT_API_KEY = "4aadba4402eceffa0e6f777a8b09c7709c74c5c7556c9cc7e72e8740639e2f6e"
FT_BASE_URL = "https://api.flashtopup.com/api/reseller/v2"
FT_TIMEOUT = 20
FT_AUTO_RECHARGE = True


def flash_topup_enabled():
    return bool(FT_API_ID and FT_API_KEY and FT_BASE_URL and FT_AUTO_RECHARGE)


def _flash_signature(path, timestamp, nonce, body_bytes):
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    signing_string = f"{path}{timestamp}{nonce}{body_hash}"
    return hmac.new(
        FT_API_KEY.encode("utf-8"),
        signing_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _flash_headers(path, body_bytes):
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-FT-API-ID": FT_API_ID,
        "X-FT-TIMESTAMP": timestamp,
        "X-FT-NONCE": nonce,
        "X-FT-SIGNATURE": _flash_signature(path, timestamp, nonce, body_bytes),
                                     }

# ==================================================
# FLASH TOPUP ORDER FUNCTIONS
# ==================================================

def flash_place_order(game, package, game_id, server_id, local_order_id):
    if not flash_topup_enabled():
        return {"success": False, "enabled": False, "error": "FlashTopup API is not configured/enabled."}

    service_code = f"TOPUP_{game}_{package.split(' - ', 1)[0].strip().replace('💎', '').replace('UC', '')}"

    payload = {
        "service_code": service_code,
        "reference_id": f"EREN-{local_order_id}-{uuid.uuid4().hex[:8]}",
        "quantity": 1,
        "user_id": str(game_id),
    }
    if game == "ML" and server_id:
        payload["server_id"] = str(server_id)

    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = _flash_headers("/order", body)
    url = f"{FT_BASE_URL}/order"

    try:
        response = requests.post(url, data=body, headers=headers, timeout=FT_TIMEOUT)
        data = response.json()
        if response.status_code == 200 and data.get("success"):
            return {"success": True, "provider_order_id": str(data.get("data", {}).get("order_id", ""))}
        return {"success": False, "error": data.get("message", str(data))}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==================================================
# SETTINGS
# ==================================================

# SQLite Database File
DB_FILE = os.environ.get("DB_FILE", "/home/erenyeager250/mysite/website.db")
os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)

# Telegram Bot Settings
BOT_TOKEN = "8996593086:AAGll9JC9IJlTvPcgadRvj9URInBY8USlqw"
GROUP_ID = -1003987776013
OWNER_CHAT_ID = 5698123475
ADMIN_USERNAME = "Eren"

# Email Settings
EMAIL_ADDRESS = "erenshops7@gmail.com"
EMAIL_PASSWORD = "umuezngvtzvbrmch"


# ==================================================
# DATABASE
# ==================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
""")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password TEXT NOT NULL,
            balance INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            device_name TEXT DEFAULT 'Unknown'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            game TEXT,
            package TEXT,
            game_id TEXT,
            server_id TEXT,
            telegram_username TEXT,
            acc_mail TEXT,
            payment TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT NOT NULL
        )
    """)

    # Safe migrations for FlashTopup auto-recharge fields.
    for column_sql in [
        "ALTER TABLE orders ADD COLUMN provider_order_id TEXT",
        "ALTER TABLE orders ADD COLUMN provider_status TEXT",
        "ALTER TABLE orders ADD COLUMN wallet_charged INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(column_sql)
        except sqlite3.OperationalError:
            pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            amount INTEGER NOT NULL,
            transaction_id TEXT NOT NULL,
            payment TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            created_at TEXT NOT NULL,
            telegram_username TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS telegram_forward_map (
            owner_message_id INTEGER PRIMARY KEY,
            customer_chat_id INTEGER NOT NULL,
            customer_message_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    # Migrations
    migrations = {
        "users": {"device_name": "TEXT DEFAULT 'Unknown'"},
        "orders": {"telegram_username": "TEXT", "acc_mail": "TEXT"},
        "deposit_requests": {"telegram_username": "TEXT"},
    }

    for table, columns in migrations.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    conn.commit()
    conn.close()
    print("✅ Database tables created successfully!")

init_db()

# ==================================================
# TIME
# ==================================================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==================================================
# STYLE (Updated to support new CSS)
# ==================================================

STYLE = """
<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 20px;
    background: #0f172a;
    background-image: url('/static/wallpaper.png');
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    color: white;
    font-family: Arial, sans-serif;
    padding-bottom: 75px;
}

.box {
    width: 100%;
    max-width: 430px;
    margin: auto;
    background: #1e293b;
    padding: 20px;
    border-radius: 20px;
    box-shadow: 0 10px 30px rgba(0,0,0,.3);
}

h1 {
    text-align: center;
    color: #00e5ff;
    margin-bottom: 25px;
}
h2 { color: #00e5ff; }
.card {
    background: #0f172a;
    padding: 16px;
    margin-top: 12px;
    border-radius: 14px;
}
input, select, button {
    width: 100%;
    min-height: 48px;
    margin-top: 10px;
    padding: 12px;
    border-radius: 10px;
    font-size: 16px;
}
input, select {
    background: #0f172a;
    color: white;
    border: 1px solid #475569;
}
button {
    border: 0;
    background: #00e5ff;
    color: #000;
    font-weight: bold;
    cursor: pointer;
}
.green { background: #22c55e; color: white; }
.red { background: #ef4444; color: white; }
.balance {
    text-align: center;
    font-size: 30px;
    font-weight: bold;
    color: #22c55e;
    padding: 15px;
}
.success { color: #4ade80; margin-top: 15px; }
.error { color: #f87171; margin-top: 15px; }
a { color: #00e5ff; text-decoration: none; }
.small { color: #94a3b8; font-size: 13px; }
.hidden { display: none; }
.order-card {
    background: #0f172a;
    padding: 16px;
    margin-top: 12px;
    border-radius: 14px;
    border-left: 4px solid #00e5ff;
}
.status {
    display: inline-block;
    padding: 6px 10px;
    border-radius: 8px;
    background: #f59e0b;
    color: #000;
    font-weight: bold;
}
</style>
"""


# ==================================================
# TELEGRAM MESSAGE
# ==================================================

def send_telegram_message(text):
    if not BOT_TOKEN: return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        response = requests.post(url, data={"chat_id": GROUP_ID, "text": text}, timeout=20)
        return response.status_code == 200
    except Exception as e:
        print("Telegram Error:", e)
        return False

def send_telegram_message_with_buttons(text, reply_markup=None):
    """Send an order/deposit message to the configured Telegram group."""
    if not BOT_TOKEN or not GROUP_ID:
        print("Telegram config missing: BOT_TOKEN/GROUP_ID")
        return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": GROUP_ID, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            data["reply_markup"] = reply_markup
        response = requests.post(url, data=data, timeout=20)
        if response.status_code != 200:
            print("Telegram sendMessage failed:", response.status_code, response.text[:1000])
            return False
        return bool(response.json().get("ok"))
    except Exception as e:
        print("Telegram Error:", e)
        return False

def send_telegram_photo(photo, caption, reply_markup=None):
    if not BOT_TOKEN: return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        files = {"photo": (photo.filename, photo.stream, photo.mimetype)}
        data = {"chat_id": GROUP_ID, "caption": caption}
        if reply_markup: data["reply_markup"] = reply_markup
        response = requests.post(url, data=data, files=files, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print("Telegram Photo Error:", e)
        return False

def send_message_to_user(username, text):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_username FROM orders WHERE username=? AND telegram_username IS NOT NULL AND telegram_username != '' ORDER BY id DESC LIMIT 1", (username,))
        user = cursor.fetchone()
        if not user:
            cursor.execute("SELECT telegram_username FROM deposit_requests WHERE username=? AND telegram_username IS NOT NULL AND telegram_username != '' ORDER BY id DESC LIMIT 1", (username,))
            user = cursor.fetchone()
        conn.close()
        if not user or not user[0]: return False
        telegram_username = str(user[0]).strip().lstrip("@")
        if not telegram_username: return False
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": f"@{telegram_username}", "text": text, "parse_mode": "HTML"}
        response = requests.post(url, data=data, timeout=20)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message to {username}: {e}")
        return False

# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():
    if "username" in session: return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# ==================================================
# REGISTER
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not username or not email or not password: error = "⚠️ အကုန်ဖြည့်ပါ"
        elif len(username) < 3: error = "⚠️ Username အနည်းဆုံး 3 လုံး"
        elif len(password) < 6: error = "⚠️ Password အနည်းဆုံး 6 လုံး"
        elif password != confirm: error = "⚠️ Password မတူပါ"
        else:
            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO users (username, email, password, balance, created_at) VALUES (?, ?, ?, ?, ?)", (username, email, generate_password_hash(password), 0, now()))
                conn.commit()
                conn.close()
                session["username"] = username
                send_telegram_message(f"🆕 NEW USER REGISTERED\n━━━━━━━━━━━━━━━━━━\n👤 Username: {username}\n📧 Email: {email}\n🕒 Time: {now()}")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                conn.close()
                error = "⚠️ ဒီ Username ရှိပြီးသားပါ"
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Register</title>{STYLE}</head><body><div class="box"><h1>👤 Create Account</h1><form method="POST"><input name="username" placeholder="👤 Username" required><input type="email" name="email" placeholder="📧 Gmail" required><input type="password" name="password" placeholder="🔒 Password" required><input type="password" name="confirm" placeholder="🔒 Confirm Password" required><button class="green" type="submit">✅ Register</button></form><p class="error">{error}</p><p>Account ရှိပြီးသားလား? <a href="/login">Login</a></p></div></body></html>"""

# ==================================================
# LOGIN
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            session["username"] = username
            user_agent = request.headers.get('User-Agent', 'Unknown')
            device_name = user_agent.split('(')[1].split(')')[0] if '(' in user_agent and ')' in user_agent else user_agent[:30]
            cursor.execute("UPDATE users SET device_name = ? WHERE username = ?", (device_name, username))
            conn.commit()
            conn.close()
            return redirect(url_for("dashboard"))
        conn.close()
        error = "❌ Username သို့မဟုတ် Password မှားနေပါတယ်"
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Login</title>{STYLE}</head><body><div class="box"><h1>🔐 Login</h1><form method="POST"><input name="username" placeholder="👤 Username" required><input type="password" name="password" placeholder="🔒 Password" required><button type="submit">🔐 Login</button></form><p class="error">{error}</p><p>Account မရှိသေးပါသလား? <a href="/register">Register</a></p><p><a href="/forgot-password">🔑 Forgot Password?</a></p></div></body></html>"""


# ==================================================
# FORGOT PASSWORD
# ==================================================

import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

def send_reset_email(email, token):
    try:
        reset_link = f"https://erenyeager250.pythonanywhere.com/reset-password/{token}"
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = email
        msg['Subject'] = "Password Reset Request - Eren's Shop"
        body = f"<h2>🔑 Password Reset</h2><p>Click the link below to reset your password:</p><a href='{reset_link}'>{reset_link}</a><p>This link will expire in 1 hour.</p>"
        msg.attach(MIMEText(body, 'html'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    message = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email: message = "⚠️ Email ထည့်ပါ"
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email=?", (email,))
            user = cursor.fetchone()
            conn.close()
            if not user: message = "❌ ဒီ Email နဲ့ User မရှိပါ"
            else:
                token = secrets.token_urlsafe(32)
                expires_at = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM password_resets WHERE email=?", (email,))
                cursor.execute("INSERT INTO password_resets (email, token, created_at, expires_at) VALUES (?, ?, ?, ?)", (email, token, now(), expires_at))
                conn.commit()
                conn.close()
                if send_reset_email(email, token): message = "✅ Password reset link ကို သင့် Email ဆီ ပို့ထားပါတယ်။"
                else: message = "❌ Email ပို့လို့မရပါ။ နောက်မှပြန်စမ်းပါ။"
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Forgot Password</title>{STYLE}</head><body><div class="box"><h1>🔑 Forgot Password</h1><p>သင့် Email ထည့်ပါ။ Reset link ကို ပို့ပေးပါမယ်။</p><form method="POST"><input type="email" name="email" placeholder="📧 Email" required><button type="submit">📤 Send Reset Link</button></form><p class="success">{message}</p><a href="/login"><button>⬅️ Back to Login</button></a></div></body></html>"""

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    message = ""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM password_resets WHERE token=? AND expires_at > datetime('now')", (token,))
    reset = cursor.fetchone()
    conn.close()
    if not reset: return """<div class="box"><h1>❌ Invalid or Expired Link</h1><p>ဒီ Link က သက်တမ်းကုန်သွားပါပြီ။</p><a href="/forgot-password"><button>🔄 Try Again</button></a></div>"""
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not password or len(password) < 6: message = "⚠️ Password အနည်းဆုံး 6 လုံးထည့်ပါ"
        elif password != confirm: message = "⚠️ Password မတူပါ"
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET password=? WHERE email=?", (generate_password_hash(password), reset[1]))
            cursor.execute("DELETE FROM password_resets WHERE token=?", (token,))
            conn.commit()
            conn.close()
            return """<div class="box"><h1>✅ Password Changed!</h1><p>သင့် Password ကို အောင်မြင်စွာ ပြောင်းလိုက်ပါပြီ။</p><a href="/login"><button>🔐 Login</button></a></div>"""
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reset Password</title>{STYLE}</head><body><div class="box"><h1>🔑 Reset Password</h1><form method="POST"><input type="password" name="password" placeholder="🔒 New Password" required><input type="password" name="confirm" placeholder="🔒 Confirm Password" required><button type="submit">✅ Reset Password</button></form><p class="error">{message}</p></div></body></html>"""

# ==================================================
# SHOP (Dashboard - Auto System Separated)
# ==================================================

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, email, balance FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        session.clear()
        return redirect(url_for("login"))

    wallet_balance = int(user[2] or 0)

    # Sold counts
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT game, COUNT(*) FROM orders WHERE status IN ('Confirmed', 'Completed') GROUP BY game")
    sold_counts = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    ml_sold = sold_counts.get("ML", 0)
    pubg_sold = sold_counts.get("PUBG", 0)
    hok_sold = sold_counts.get("HOK", 0)
    tg_sold = sold_counts.get("TG Pre", 0)
    smile_brl_sold = sold_counts.get("Smile One Code BRL", 0)
    smile_php_sold = sold_counts.get("Smile One Coin PHP", 0)

    # ==================== ✅ Notifications System ====================
    conn = get_db()
    cursor = conn.cursor()

    # 1. Unread count (Red Dot အတွက်)
    cursor.execute("SELECT COUNT(*) FROM notifications WHERE username=? AND is_read=0", (username,))
    unread_count = cursor.fetchone()[0]

    # 2. Get latest 10 notifications (စာသားအသစ်နဲ့)
    cursor.execute("SELECT id, type, title, message, created_at, is_read FROM notifications WHERE username=? ORDER BY created_at DESC LIMIT 10", (username,))
    notifications = cursor.fetchall()
    conn.close()

    # 3. Mark all as read (ခေါင်းလောင်းဖွင့်လိုက်ရင် အကုန်ဖတ်ပြီးသား ဖြစ်သွားမယ်)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read=1 WHERE username=?", (username,))
    conn.commit()
    conn.close()

    notice_html = ""
    for note in notifications:
        note_id = note[0]
        title = note[2]
        message = note[3]
        date_str = note[4]

        # အရောင်အလိုက် Icon ပြောင်းမယ်
        if "Deposit" in title:
            icon = "💰"
            color = "#4ade80"
        else:
            icon = "🛒"
            color = "#4ade80"

        notice_html += f"""
        <div class="notice-item" style="border-left: 4px solid {color};">
            <div style="display:flex; justify-content:space-between; align-items:start;">
                <div>
                    <div style="font-weight:bold; font-size:16px; color:#fff; margin-bottom:4px;">{icon} {title}</div>
                    <div style="font-size:14px; color:#b0c4de; line-height:1.5;">{message}</div>
                    <div style="font-size:11px; color:#6b7280; margin-top:6px;">{date_str}</div>
                </div>
            </div>
        </div>
        """

    if not notice_html:
        notice_html = "<div class='notice-item' style='color:#94a3b8; text-align:center; padding:20px;'>အကြောင်းကြားစာ မရှိသေးပါ။</div>"

    # Red Dot ပြမယ့် Logic
    bell_dot_html = f'<span class="bell-dot"></span>' if unread_count > 0 else ''

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Eren's Shop</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Arial, sans-serif;
            background: #000;
            color: #fff;
            padding-bottom: 80px;
        }}

        .header {{
            background: #0d1117;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header .title {{
            font-size: 20px;
            color: #14b8a6;
            font-weight: bold;
        }}
        .header .right {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .header .balance {{
            background: #1e293b;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 14px;
            color: #4ade80;
            font-weight: bold;
        }}
        .bell-btn {{
            position: relative;
            background: transparent;
            border: none;
            color: #fff;
            font-size: 24px;
            cursor: pointer;
            padding: 0;
        }}
        .bell-dot {{
            position: absolute;
            top: -2px;
            right: -2px;
            width: 10px;
            height: 10px;
            background: #ef4444;
            border-radius: 50%;
            border: 2px solid #0d1117;
        }}

        .modal-overlay {{
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.85);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 9999;
        }}
        .modal-box {{
            background: #0d1117;
            width: 92%;
            max-width: 420px;
            border-radius: 20px;
            padding: 20px;
            border: 1px solid #222;
            max-height: 80vh;
            overflow-y: auto;
            color: #fff;
            position: relative;
        }}
        .modal-box .close-btn {{
            position: absolute;
            top: 10px;
            right: 15px;
            font-size: 28px;
            color: #94a3b8;
            cursor: pointer;
            background: none;
            border: none;
        }}
        .modal-box h3 {{
            color: #14b8a6;
            font-size: 20px;
            margin-bottom: 15px;
            padding-right: 30px;
        }}
        .notice-item {{
            background: #1e293b;
            padding: 14px;
            border-radius: 12px;
            margin-bottom: 10px;
        }}

        .product-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            padding: 15px 15px 20px 15px;
            max-width: 500px;
            margin: auto;
        }}
        .product-card {{
            background: #14b8a6;
            border-radius: 12px;
            padding: 15px 10px;
            text-align: center;
            text-decoration: none;
            color: #fff;
        }}
        .product-card img {{
            width: 100%;
            height: 100px;
            object-fit: contain;
            border-radius: 6px;
            margin-bottom: 8px;
        }}
        .product-card .name {{
            font-weight: bold;
            font-size: 14px;
        }}
        .product-card .sold {{
            font-size: 12px;
            color: rgba(255,255,255,0.9);
            margin-top: 4px;
            display: block;
        }}

        .bottom-nav {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px 0;
            z-index: 999;
        }}
        .bottom-nav a {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }}
        .bottom-nav a .icon {{
            font-size: 22px;
            margin-bottom: 2px;
        }}
        .bottom-nav a.active {{
            color: #0d1117;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">Eren's Shop</div>
        <div class="right">
            <div class="balance">💳 {wallet_balance:,} Ks</div>
            <button class="bell-btn" onclick="openNotice()">🔔{bell_dot_html}</button>
        </div>
    </div>

    <div id="noticeModal" class="modal-overlay" onclick="closeNoticeOutside(event)">
        <div class="modal-box">
            <button class="close-btn" onclick="closeNotice()">×</button>
            <h3>📢 အကြောင်းကြားစာများ</h3>
            {notice_html}
        </div>
    </div>

    <div class="product-grid">
        <!-- ✅ ပုံမှန် Game တွေ (Manual) -->
        <a href="/packages/ML" class="product-card">
            <img src="/static/ml.png">
            <div class="name">Mobile Legends</div>
            <span class="sold">{ml_sold:,} Sold</span>
        </a>
        <a href="/packages/PUBG" class="product-card">
            <img src="/static/pubg.png">
            <div class="name">PUBG Mobile</div>
            <span class="sold">{pubg_sold:,} Sold</span>
        </a>
        <a href="/packages/HOK" class="product-card">
            <img src="/static/hok.png">
            <div class="name">Honor Of Kings</div>
            <span class="sold">{hok_sold:,} Sold</span>
        </a>
        <a href="/packages/TG Pre" class="product-card">
            <img src="/static/telegram.png">
            <div class="name">Telegram Premium</div>
            <span class="sold">{tg_sold:,} Sold</span>
        </a>

        <!-- ✅ Auto System (Smile One) ကို သီးသန့်ခွဲမယ် -->
        <div style="margin-top: 15px; border-top: 1px solid #333; padding-top: 15px; width: 100%;"></div>
        <div style="grid-column: 1 / -1; text-align: center; color: #14b8a6; font-weight: bold; margin-bottom: 5px;">⚡ Auto System</div>

        <a href="/packages/Smile One Code BRL" class="product-card" style="background: #f59e0b;">
            <img src="/static/smileone.png">
            <div class="name">Smile One BRL (Auto)</div>
            <span class="sold">{smile_brl_sold:,} Sold</span>
        </a>
        <a href="/packages/Smile One Coin PHP" class="product-card" style="background: #f59e0b;">
            <img src="/static/smileone.png">
            <div class="name">Smile One PHP (Auto)</div>
            <span class="sold">{smile_php_sold:,} Sold</span>
        </a>
    </div>

    <div class="bottom-nav">
        <a href="/dashboard" class="active"><span class="icon">🏠</span> Shop</a>
        <a href="/wallet"><span class="icon">💰</span> Recharge</a>
        <a href="/orders"><span class="icon">📦</span> Order History</a>
        <a href="/profile"><span class="icon">👤</span> Profile</a>
    </div>

    <script>
        function openNotice() {{
            document.getElementById('noticeModal').style.display = 'flex';
            // ခေါင်းလောင်းဖွင့်ပြီးရင် Red Dot ပျောက်ဖို့ Refresh လုပ်မယ်
            setTimeout(() => {{
                location.reload();
            }}, 3000); // 3 seconds ကြာရင် ပြန်သွားမယ်
        }}
        function closeNotice() {{ document.getElementById('noticeModal').style.display = 'none'; }}
        function closeNoticeOutside(e) {{ if (e.target === document.getElementById('noticeModal')) {{ closeNotice(); }} }}
    </script>
</body>
</html>
"""

# ==================================================
# RECHARGE (Wallet - Menu Bar 4 Items)
# ==================================================

@app.route("/wallet", methods=["GET", "POST"])
def wallet():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    message = ""
    message_type = "success"
    active_tab = request.args.get("tab", "deposit")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, email, balance FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    raw_balance = user[2]
    try:
        if raw_balance is None:
            wallet_balance = 0
        else:
            wallet_balance = int(float(str(raw_balance).strip()))
    except:
        wallet_balance = 0

    # Handle Deposit POST
    if request.method == "POST" and request.form.get("action") == "deposit":
        amount = request.form.get("amount", "").strip()
        transaction = request.form.get("transaction", "").strip()
        telegram_username = request.form.get("telegram_username", "").strip().lstrip("@")
        screenshot = request.files.get("screenshot")
        payment = "Manual"

        if not amount or not amount.isdigit() or int(amount) < 1000:
            message = "⚠️ အနည်းဆုံး 1,000 Ks မှ စတင်ပါ။"
            message_type = "error"
        elif not transaction.isdigit() or len(transaction) != 5:
            message = "⚠️ Transaction နောက်ဆုံး 5 လုံးပဲ ထည့်ပါ"
            message_type = "error"
        elif not telegram_username:
            message = "⚠️ Telegram Username ထည့်ပါ"
            message_type = "error"
        elif not screenshot or not screenshot.filename:
            message = "⚠️ Screenshot ထည့်ပါ"
            message_type = "error"
        else:
            amount = int(amount)
            cursor.execute("INSERT INTO deposit_requests (username, amount, transaction_id, payment, status, created_at, telegram_username) VALUES (?, ?, ?, ?, ?, ?, ?)", (username, amount, transaction, payment, "Pending", now(), telegram_username))
            deposit_id = cursor.lastrowid
            conn.commit()
            deposit_text = f"💰 NEW DEPOSIT REQUEST\n━━━━━━━━━━━━━━━━━━\n🆔 ID: #{deposit_id}\n👤 User: {username}\n💵 Amount: {amount:,} Ks\n🔢 Transaction: {transaction}\n📱 Telegram: @{telegram_username}"
            import json
            reply_markup = {"inline_keyboard": [[{"text": "✅ Confirm", "callback_data": f"confirm_deposit_{deposit_id}"}, {"text": "❌ Reject", "callback_data": f"reject_deposit_{deposit_id}"}]]}
            sent = send_telegram_photo(screenshot, deposit_text, json.dumps(reply_markup))
            if sent:
                message = f"✅ Deposit Request #{deposit_id} ပို့ပြီးပါပြီ။"
            else:
                message = f"⚠️ Deposit Request #{deposit_id} သိမ်းပြီးပါပြီ။ Telegram သို့ ပို့မရပါ။"
                message_type = "error"

    # Get History
    cursor.execute("""
        SELECT 'confirmed' as type, id, username, amount, description as detail, created_at FROM wallet_transactions WHERE username = ?
        UNION ALL
        SELECT 'pending' as type, id, username, amount, status as detail, created_at FROM deposit_requests WHERE username = ? AND status = 'Pending'
        ORDER BY created_at DESC LIMIT 30
    """, (username, username))
    combined_history = cursor.fetchall()
    conn.close()

    history_html = ""
    for item in combined_history:
        if item[0] == 'confirmed':
            is_deposit = "DEPOSIT" in item[4] or "Deposit" in item[4]
            sign = "+" if is_deposit else "-"
            color = '#4ade80' if is_deposit else '#f87171'
            history_html += f"""<div class="pay-card" style="flex-direction:column; align-items:flex-start;"><b style="color:{color};">{sign}{item[3]:,} Ks</b><small style="color:#94a3b8;">{item[4]}</small><small>{item[5]}</small></div>"""
        else:
            history_html += f"""<div class="pay-card" style="flex-direction:column; align-items:flex-start; border-left:4px solid #f59e0b;"><b style="color:#f59e0b;">🟡 Pending {item[3]:,} Ks</b><small>Deposit Request</small><small>{item[5]}</small></div>"""
    if not history_html:
        history_html = "<div class='pay-card' style='text-align:center; color:#94a3b8;'>မှတ်တမ်း မရှိသေးပါ။</div>"

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Recharge</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Arial, sans-serif;
            background: #000;
            color: #fff;
            padding-bottom: 80px;
        }}

        .header {{
            background: #0d1117;
            padding: 15px;
            border-bottom: 1px solid #222;
            text-align: center;
        }}
        .header h1 {{
            font-size: 20px;
            color: #14b8a6;
            margin: 0;
        }}

        .container {{
            max-width: 500px;
            margin: auto;
            padding: 15px;
        }}

        .notice-box {{
            background: #bae6fd;
            color: #0c4a6e;
            padding: 15px;
            border-radius: 10px;
            font-size: 14px;
            margin-bottom: 15px;
            text-align: center;
            line-height: 1.6;
        }}

        .tabs {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }}
        .tab-btn {{
            flex: 1;
            padding: 12px;
            border-radius: 10px;
            text-align: center;
            font-weight: bold;
            border: none;
            font-size: 15px;
            cursor: pointer;
            text-decoration: none;
            display: block;
        }}
        .tab-btn.active {{
            background: #1d4ed8;
            color: #fff;
        }}
        .tab-btn.inactive {{
            background: #fff;
            color: #000;
        }}

        .pay-card {{
            background: #0d1117;
            border: 1px solid #222;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .pay-card .info strong {{
            display: block;
            font-size: 15px;
        }}
        .pay-card .info small {{
            color: #94a3b8;
        }}
        .btn-copy {{
            background: #1e293b;
            color: #fff;
            border: none;
            padding: 6px 15px;
            border-radius: 6px;
            cursor: pointer;
        }}

        input, select {{
            width: 100%;
            padding: 12px;
            margin-top: 8px;
            border-radius: 8px;
            border: 1px solid #222;
            background: #0d1117;
            color: #fff;
        }}
        .btn-green {{
            width: 100%;
            padding: 14px;
            background: #22c55e;
            border: none;
            border-radius: 10px;
            font-weight: bold;
            color: #000;
            font-size: 16px;
            margin-top: 15px;
            cursor: pointer;
        }}

        .bottom-nav {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px 0;
            z-index: 999;
        }}
        .bottom-nav a {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }}
        .bottom-nav a .icon {{
            font-size: 22px;
            margin-bottom: 2px;
        }}
        .bottom-nav a.active {{
            color: #0d1117;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>💰 Recharge</h1>
    </div>

    <div class="container">
        <div class="notice-box">
            Deposit Order တင်ပြီးလျှင် Bot ကတစ်ဆင့် owner စီစာပို့ပေးပါ
        </div>

        <div class="tabs">
            <a href="/wallet?tab=deposit" class="tab-btn {'active' if active_tab == 'deposit' else 'inactive'}">ငွေဖြည့်မည်</a>
            <a href="/wallet?tab=history" class="tab-btn {'active' if active_tab == 'history' else 'inactive'}">မှတ်တမ်း</a>
        </div>

        <div id="deposit" style="display: {'block' if active_tab == 'deposit' else 'none'}">
            <form method="POST" enctype="multipart/form-data">
                <input type="hidden" name="action" value="deposit">

                <div class="pay-card">
                    <div class="info">
                        <strong>K Pay</strong>
                        <small>09766605879<br>Thet Naing Swan</small>
                    </div>
                    <button type="button" class="btn-copy" onclick="copyText('09766605879')">Copy</button>
                </div>

                <div class="pay-card">
                    <div class="info">
                        <strong>UAB Pay</strong>
                        <small>09425160424<br>Thet Naing Swan</small>
                    </div>
                    <button type="button" class="btn-copy" onclick="copyText('09425160424')">Copy</button>
                </div>

                <input type="number" name="amount" min="1000" placeholder="💵 ပမာဏ (1000 Ks)" required>
                <input type="text" name="transaction" maxlength="5" placeholder="🔢 Transaction နောက်ဆုံး 5 လုံး" required>
                <input type="text" name="telegram_username" placeholder="📱 Telegram Username" required>
                <input type="file" name="screenshot" accept="image/*" required>

                <button class="btn-green" type="submit">📤 Deposit Request ပို့မည်</button>
            </form>
        </div>

        <div id="history" style="display: {'block' if active_tab == 'history' else 'none'}">
            {history_html}
        </div>
    </div>

    <div class="bottom-nav">
        <a href="/dashboard"><span class="icon">🏠</span> Shop</a>
        <a href="/wallet" class="active"><span class="icon">💰</span> Recharge</a>
        <a href="/orders"><span class="icon">📦</span> Order History</a>
        <a href="/profile"><span class="icon">👤</span> Profile</a>
    </div>

    <script>
        function copyText(t) {{ navigator.clipboard.writeText(t).then(()=>alert('Copied: '+t)); }}
    </script>
</body>
</html>
"""

# ==================================================
# ORDER (Choose Game - No Header Title)
# ==================================================

@app.route("/order", methods=["GET"])
def order():
    if "username" not in session:
        return redirect(url_for("login"))
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Order</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Arial, sans-serif;
            background: #000;
            color: #fff;
            padding-bottom: 80px;
        }}

        /* ✅ Header ကို ဖယ်ပြီး Game Grid ကို အပေါ်ဆုံးရောက်အောင် လုပ်ထားပါတယ် */
        .grid-2 {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            padding: 15px;
            max-width: 500px;
            margin: auto;
        }}
        .card {{
            background: #14b8a6;
            border-radius: 12px;
            padding: 15px 10px;
            text-align: center;
            text-decoration: none;
            color: #fff;
        }}
        .card img {{
            width: 100%;
            height: 100px;
            object-fit: contain;
            border-radius: 6px;
            margin-bottom: 8px;
        }}
        .card .name {{
            font-weight: bold;
            font-size: 14px;
        }}

        /* Bottom Nav (5 Tabs) */
        .bottom-nav {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px 0;
            z-index: 999;
        }}
        .bottom-nav a {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }}
        .bottom-nav a .icon {{
            font-size: 22px;
            margin-bottom: 2px;
        }}
        .bottom-nav a.active {{
            color: #0d1117;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <!-- ✅ Game Grid ချည်း သက်သက် -->
    <div class="grid-2">
        <a href="/packages/ML" class="card">
            <img src="/static/ml.png">
            <div class="name">Mobile Legends</div>
        </a>
        <a href="/packages/PUBG" class="card">
            <img src="/static/pubg.png">
            <div class="name">PUBG Mobile</div>
        </a>
        <a href="/packages/HOK" class="card">
            <img src="/static/hok.png">
            <div class="name">Honor Of Kings</div>
        </a>
        <a href="/packages/TG Pre" class="card">
            <img src="/static/telegram.png">
            <div class="name">Telegram Premium</div>
        </a>
        <a href="/packages/Smile One Code BRL" class="card">
            <img src="/static/smileone.png">
            <div class="name">Smile One BRL</div>
        </a>
        <a href="/packages/Smile One Coin PHP" class="card">
            <img src="/static/smileone.png">
            <div class="name">Smile One PHP</div>
        </a>
    </div>

    <!-- Bottom Nav (5 Tabs) -->
    <div class="bottom-nav">
        <a href="/dashboard"><span class="icon">🏠</span> Shop</a>
        <a href="/wallet"><span class="icon">💰</span> Recharge</a>
        <a href="/order" class="active"><span class="icon">📄</span> Order</a>
        <a href="/orders"><span class="icon">📦</span> Order History</a>
        <a href="/profile"><span class="icon">👤</span> Profile</a>
    </div>
</body>
</html>
"""


# ==================================================
# PACKAGES (Turbo Style - With Back Button)
# ==================================================

@app.route("/packages/<game>", methods=["GET"])
def packages(game):
    if "username" not in session:
        return redirect(url_for("login"))

    package_lists = {
        "ML": ["10 💎 - 1,000 Ks", "12 💎 - 1,200 Ks", "20 💎 - 1,900 Ks", "22 💎 - 2,100 Ks", "33 💎 - 3,000 Ks", "44 💎 - 3,600 Ks", "55 💎 - 4,000 Ks", "56 💎 - 4,400 Ks", "86 💎 - 5,600 Ks", "172 💎 - 10,800 Ks", "257 💎 - 15,800 Ks", "279 💎 - 17,100 Ks", "343 💎 - 20,600 Ks", "429 💎 - 25,900 Ks", "Weekly Pass - 6,400 Ks"],
        "PUBG": ["60 UC - 600 Ks", "325 UC - 3,250 Ks", "660 UC - 6,600 Ks", "1800 UC - 18,000 Ks", "3850 UC - 38,500 Ks"],
        "HOK": ["60 Tokens - 1,000 Ks", "120 Tokens - 2,000 Ks", "250 Tokens - 4,000 Ks", "500 Tokens - 8,000 Ks", "1000 Tokens - 15,000 Ks"],
        "TG Pre": ["3 Months - 3,000 Ks", "6 Months - 6,000 Ks", "12 Months - 12,000 Ks"],
        "Smile One Code BRL": ["30 BRL - 24,500 Ks", "100 BRL - 85,500 Ks", "500 BRL - 424,000 Ks"],
        "Smile One Coin PHP": ["280 PHP - 22,000 Ks", "560 PHP - 42,000 Ks", "1120 PHP - 83,000 Ks"]
    }

    game_names = {"ML": "Mobile Legends", "PUBG": "PUBG Mobile", "HOK": "Honor Of Kings", "TG Pre": "Telegram Premium", "Smile One Code BRL": "Smile One BRL", "Smile One Coin PHP": "Smile One PHP"}
    display_name = game_names.get(game, game)
    packages = package_lists.get(game, [])

    packages_html = ""
    for pkg in packages:
        packages_html += f'<a href="/place_order?game={game}&package={pkg}" class="card"><div class="name">{pkg}</div></a>'

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{display_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Arial, sans-serif;
            background: #000;
            color: #fff;
            padding-bottom: 80px;
        }}

        /* Header with Back Button */
        .header {{
            background: #0d1117;
            padding: 15px;
            border-bottom: 1px solid #222;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }}
        .header .back-btn {{
            position: absolute;
            left: 15px;
            color: #fff;
            text-decoration: none;
            font-size: 18px;
        }}
        .header h1 {{
            font-size: 20px;
            color: #14b8a6;
            margin: 0;
        }}

        .container {{
            max-width: 500px;
            margin: auto;
            padding: 15px;
        }}
        .grid-2 {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }}
        .card {{
            background: #14b8a6;
            border-radius: 12px;
            padding: 15px 10px;
            text-align: center;
            text-decoration: none;
            color: #fff;
        }}
        .card .name {{
            font-weight: bold;
            font-size: 14px;
        }}

        /* Bottom Nav (4 Tabs - No Order) */
        .bottom-nav {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px 0;
            z-index: 999;
        }}
        .bottom-nav a {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }}
        .bottom-nav a .icon {{
            font-size: 22px;
            margin-bottom: 2px;
        }}
        .bottom-nav a.active {{
            color: #0d1117;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <!-- Header with Back Button -->
    <div class="header">
        <a href="/order" class="back-btn">← Back</a>
        <h1>📦 {display_name}</h1>
    </div>

    <div class="container">
        <div class="grid-2">{packages_html}</div>
    </div>

    <div class="bottom-nav">
        <a href="/dashboard"><span class="icon">🏠</span> Shop</a>
        <a href="/wallet"><span class="icon">💰</span> Recharge</a>
        <a href="/orders"><span class="icon">📦</span> Order History</a>
        <a href="/profile"><span class="icon">👤</span> Profile</a>
    </div>
</body>
</html>
"""

# ==================================================
# PLACE ORDER (Auto API + Manual Support)
# ==================================================

@app.route("/place_order", methods=["GET", "POST"])
def place_order():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    message = ""
    message_type = "success"

    package_price_map = {
        "10 💎 - 1,000 Ks": 1000, "12 💎 - 1,200 Ks": 1200, "20 💎 - 1,900 Ks": 1900,
        "22 💎 - 2,100 Ks": 2100, "33 💎 - 3,000 Ks": 3000, "44 💎 - 3,600 Ks": 3600,
        "55 💎 - 4,000 Ks": 4000, "56 💎 - 4,400 Ks": 4400, "86 💎 - 5,600 Ks": 5600,
        "172 💎 - 10,800 Ks": 10800, "257 💎 - 15,800 Ks": 15800, "279 💎 - 17,100 Ks": 17100,
        "343 💎 - 20,600 Ks": 20600, "429 💎 - 25,900 Ks": 25900, "Weekly Pass - 6,400 Ks": 6400,
        "60 UC - 600 Ks": 600, "325 UC - 3,250 Ks": 3250, "660 UC - 6,600 Ks": 6600,
        "1800 UC - 18,000 Ks": 18000, "3850 UC - 38,500 Ks": 38500,
        "3 Months - 3,000 Ks": 3000, "6 Months - 6,000 Ks": 6000, "12 Months - 12,000 Ks": 12000,
        "30 BRL - 24,500 Ks": 24500, "100 BRL - 85,500 Ks": 85500, "500 BRL - 424,000 Ks": 424000,
        "280 PHP - 22,000 Ks": 22000, "560 PHP - 42,000 Ks": 42000, "1120 PHP - 83,000 Ks": 83000,
        "60 Tokens - 1,000 Ks": 1000, "120 Tokens - 2,000 Ks": 2000, "250 Tokens - 4,000 Ks": 4000,
        "500 Tokens - 8,000 Ks": 8000, "1000 Tokens - 15,000 Ks": 15000,
    }

    game = request.args.get("game", "").strip()
    package = request.args.get("package", "").strip()

    if request.method == "POST":
        game = request.form.get("game", "").strip()
        package = request.form.get("package", "").strip()
        game_id = request.form.get("game_id", "").strip()
        server_id = request.form.get("server_id", "").strip()
        telegram_username = request.form.get("telegram_username", "").strip().lstrip("@")
        acc_mail = request.form.get("acc_mail", "").strip()
        payment = request.form.get("payment", "").strip()

        if not game or not package or package not in package_price_map:
            message = "⚠️ Product သို့မဟုတ် Package မှားနေပါတယ်။"
            message_type = "error"
        elif game == "ML" and not game_id:
            message = "⚠️ Game ID ထည့်ပါ။"
            message_type = "error"
        elif game == "ML" and not server_id:
            message = "⚠️ Server ID ထည့်ပါ။"
            message_type = "error"
        elif game == "PUBG" and not game_id:
            message = "⚠️ PUBG ID ထည့်ပါ။"
            message_type = "error"
        elif game == "HOK" and not game_id:
            message = "⚠️ Account UID ထည့်ပါ။"
            message_type = "error"
        elif game == "TG Pre" and not telegram_username:
            message = "⚠️ Telegram Username ထည့်ပါ။"
            message_type = "error"
        # ✅ Smile One Code BRL အတွက် Validation ဖြုတ်ပြီးသား
        elif game == "Smile One Coin PHP" and not acc_mail:
            message = "⚠️ Account Mail ထည့်ပါ။"
            message_type = "error"
        elif not payment:
            message = "⚠️ Payment ရွေးပါ။"
            message_type = "error"
        else:
            package_price = package_price_map.get(package, 0)
            conn = None
            try:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT balance FROM users WHERE username=?", (username,))
                user_balance_row = cursor.fetchone()
                if not user_balance_row:
                    message = "❌ User Account မတွေ့ပါ။"
                    message_type = "error"
                else:
                    current_balance = float(user_balance_row[0] or 0)
                    if current_balance < package_price:
                        message = f"⚠️ သင့် Wallet Balance မလုံလောက်ပါ။ လိုအပ်ငွေ: {package_price - current_balance:,.0f} Ks"
                        message_type = "error"
                    else:
                        # ==========================================
                        # ✅ SMILE ONE AUTO API SUPPORT
                        # ==========================================
                        if game == "Smile One Coin PHP":
                            result = get_smile_one_code(package_price, "PHP", email=acc_mail)
                            if result["success"]:
                                cursor.execute("INSERT INTO orders (username, game, package, status, created_at) VALUES (?, ?, ?, ?, ?)",
                                               (username, game, package, "Completed", now()))
                                order_id = cursor.lastrowid
                                conn.commit()
                                message = f"✅ သင်၏ Smile One PHP Coin {package_price} Ks ကို Account ထဲသို့ အောင်မြင်စွာ ဖြည့်သွင်းပြီးပါပြီ။"
                                message_type = "success"
                            else:
                                message = f"❌ Coin ဖြည့်သွင်းရာတွင် အမှားဖြစ်နေပါတယ်။\nError: {result['error']}"
                                message_type = "error"

                        elif game == "Smile One Code BRL":
                            result = get_smile_one_code(package_price, "BRL")
                            if result["success"]:
                                cursor.execute("INSERT INTO orders (username, game, package, status, created_at) VALUES (?, ?, ?, ?, ?)",
                                               (username, game, package, "Completed", now()))
                                order_id = cursor.lastrowid
                                conn.commit()
                                message = f"✅ သင်၏ Smile One BRL Code ကို ရရှိပါပြီ။\n\n🔑 Code: {result['code']}"
                                message_type = "success"
                            else:
                                message = f"❌ Code ထုတ်ယူရာတွင် အမှားဖြစ်နေပါတယ်။\nError: {result['error']}"
                                message_type = "error"

                        # ==========================================
                        # ML / PUBG AUTO RECHARGE
                        # ==========================================
                        elif game in {"ML", "PUBG"} and flash_topup_enabled():
                            cursor.execute("INSERT INTO orders (username, game, package, game_id, server_id, telegram_username, acc_mail, payment, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                           (username, game, package, game_id, server_id, telegram_username, acc_mail, payment, "Pending", now()))
                            order_id = cursor.lastrowid
                            conn.commit()
                            conn.close()
                            conn = None

                            result = flash_place_order(game, package, game_id, server_id, order_id)
                            if result.get("success"):
                                cursor = conn.cursor()
                                cursor.execute("UPDATE orders SET status='Completed' WHERE id=?", (order_id,))
                                conn.commit()
                                message = f"✅ Order #{order_id} အောင်မြင်ပြီး Auto Recharge ပြီးပါပြီ။"
                            else:
                                message = f"❌ Auto Recharge မအောင်မြင်ပါ။\n{result.get('error', 'Unknown error')}"
                                message_type = "error"

                        # ==========================================
                        # OTHER GAMES / MANUAL ORDERS
                        # ==========================================
                        else:
                            cursor.execute("INSERT INTO orders (username, game, package, game_id, server_id, telegram_username, acc_mail, payment, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                           (username, game, package, game_id, server_id, telegram_username, acc_mail, payment, "Pending", now()))
                            order_id = cursor.lastrowid
                            conn.commit()
                            conn.close()
                            conn = None

                            order_text = f"🛒 NEW ORDER\n━━━━━━━━━━━━━━━━━━\n🆔 ID: #{order_id}\n👤 User: {username}\n🎮 Game: {game}\n📦 Package: {package}\n💵 Price: {package_price:,} Ks\n🆔 ID: {game_id or '-'}\n🌎 Server: {server_id or '-'}\n📱 Telegram: @{telegram_username if telegram_username else '-'}"
                            import json
                            reply_markup = {"inline_keyboard": [[{"text": "✅ Confirm", "callback_data": f"confirm_order_{order_id}"}, {"text": "❌ Reject", "callback_data": f"reject_order_{order_id}"}]]}
                            sent = send_telegram_message_with_buttons(order_text, json.dumps(reply_markup))
                            if sent:
                                message = f"✅ Order #{order_id} တင်ပြီးပါပြီ။"
                            else:
                                message = f"⚠️ Order #{order_id} သိမ်းပြီးပါပြီ။ Telegram ပို့မရပါ။"
                                message_type = "error"

            except Exception as e:
                message = f"❌ Error: {str(e)}"
                message_type = "error"
                if conn: conn.close()

    # ✅ Smile One Code BRL ကို Field Map ထဲကနေ ဖယ်ပြီးသား
    field_map = {
        "ML": ["gameIdBox", "serverIdBox"],
        "PUBG": ["gameIdBox"],
        "TG Pre": ["telegramBox"],
        "Smile One Coin PHP": ["mailBox"],
        "HOK": ["gameIdBox"]
    }
    required_fields = field_map.get(game, [])
    game_id_hidden = "hidden" if "gameIdBox" not in required_fields else ""
    server_id_hidden = "hidden" if "serverIdBox" not in required_fields else ""
    telegram_hidden = "hidden" if "telegramBox" not in required_fields else ""
    mail_hidden = "hidden" if "mailBox" not in required_fields else ""

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Place Order</title>
    {STYLE}
    <style>
        body {{
            background: #0f172a; /* Solid Dark Background */
            background-image: none !important;
            padding-bottom: 80px;
        }}

        .header {{
            background: #0d1117;
            padding: 15px;
            border-bottom: 1px solid #222;
            display: flex;
            align-items: center;
            position: relative;
            justify-content: center;
        }}
        .header .back-btn {{
            position: absolute;
            left: 15px;
            color: #fff;
            text-decoration: none;
            font-size: 18px;
        }}
        .header h1 {{
            font-size: 20px;
            color: #14b8a6;
            margin: 0;
        }}

        .bottom-nav {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px 0;
            z-index: 999;
        }}
        .bottom-nav a {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }}
        .bottom-nav a .icon {{
            font-size: 22px;
            margin-bottom: 2px;
        }}
        .bottom-nav a.active {{
            color: #0d1117;
            font-weight: bold;
        }}
        .hidden {{ display: none; }}
    </style>
</head>
<body>
    <div class="header">
        <a href="javascript:history.back()" class="back-btn">← Back</a>
        <h1>🛒 Place Order</h1>
    </div>

    <div class="box">
        <div class="{message_type}" style="margin-top:12px;">{message}</div>
        <form method="POST">
            <input type="hidden" name="game" value="{game}">
            <input type="hidden" name="package" value="{package}">
            <div id="gameIdBox" class="{game_id_hidden}" style="margin-top: 12px;">
                <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">{'Account UID' if game == 'HOK' else 'Game ID'}</label>
                <input type="text" name="game_id" placeholder="{'Enter Account UID' if game == 'HOK' else 'Enter Game ID'}" {"required" if "gameIdBox" in required_fields else ""}>
            </div>
            <div id="serverIdBox" class="{server_id_hidden}" style="margin-top: 12px;">
                <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Server ID</label>
                <input type="text" name="server_id" placeholder="Enter Server ID" {"required" if "serverIdBox" in required_fields else ""}>
            </div>
            <div id="telegramBox" class="{telegram_hidden}" style="margin-top: 12px;">
                <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Telegram Username</label>
                <input type="text" name="telegram_username" placeholder="@username" {"required" if "telegramBox" in required_fields else ""}>
            </div>
            <div id="mailBox" class="{mail_hidden}" style="margin-top: 12px;">
                <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Account Mail</label>
                <input type="email" name="acc_mail" placeholder="email@example.com" {"required" if "mailBox" in required_fields else ""}>
                <p style="color: #fbbf24; font-size: 12px; margin-top: 4px;">⚠️ သင့် Smile One Account Mail ကို သေချာထည့်ပါ။ မှားပါက Coin များ အခြား Account သို့ ရောက်သွားနိုင်ပါသည်။</p>
            </div>
            <div style="margin-top: 12px;">
                <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Payment</label>
                <select name="payment" required><option value="">💳 Payment ရွေးပါ</option><option value="Wallet">💰 Wallet</option></select>
            </div>
            <button type="submit" class="green" style="margin-top: 20px; width: 100%; padding: 14px; font-size: 16px;" onclick="this.disabled = true; this.innerHTML = '⏳ Order တင်နေပါတယ်...'; this.form.submit();">🛒 Order တင်မည်</button>
        </form>
    </div>

    <div class="bottom-nav">
        <a href="/dashboard"><span class="icon">🏠</span> Shop</a>
        <a href="/wallet"><span class="icon">💰</span> Recharge</a>
        <a href="/orders"><span class="icon">📦</span> Order History</a>
        <a href="/profile"><span class="icon">👤</span> Profile</a>
    </div>
</body>
</html>
"""

    # ==================================================
# ORDER HISTORY (With Game ID & Server ID)
# ==================================================

@app.route("/orders")
def orders():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    search_query = request.args.get("search", "").strip()

    conn = get_db()
    cursor = conn.cursor()

    if search_query:
        cursor.execute("""
            SELECT id, game, package, game_id, server_id, status, created_at
            FROM orders
            WHERE username=? AND (game_id LIKE ? OR package LIKE ?)
            ORDER BY id DESC
        """, (username, f"%{search_query}%", f"%{search_query}%"))
    else:
        cursor.execute("""
            SELECT id, game, package, game_id, server_id, status, created_at
            FROM orders
            WHERE username=?
            ORDER BY id DESC
        """, (username,))

    order_list = cursor.fetchall()
    conn.close()

    html = ""
    for item in order_list:
        order_id = item[0]
        package = item[2]
        game_id = item[3] or "-"
        server_id = item[4] or "-"  # ✅ Server ID ကို ယူမယ်
        status = item[5]
        date_str = item[6]

        if status == "Confirmed" or status == "Completed":
            badge_color = "#22c55e"
            badge_text = "success"
        elif status == "Pending":
            badge_color = "#f59e0b"
            badge_text = "pending"
        else:
            badge_color = "#ef4444"
            badge_text = "အောင်မြင်မှု မရှိ"

        html += f"""
        <div class="row-item">
            <div class="col-id">
                <div>{order_id}</div>
                <div style="font-size:10px; color:#94a3b8; font-weight:normal;">ID: {game_id}</div>
                <div style="font-size:10px; color:#94a3b8; font-weight:normal;">Server: {server_id}</div>
            </div>
            <div class="col-pkg">{package}</div>
            <div class="col-status">
                <span class="status-pill" style="background:{badge_color};">{badge_text}</span>
            </div>
        </div>
        """

    if not html:
        html = "<div class='row-item' style='justify-content:center; color:#94a3b8;'>Order မရှိသေးပါ။</div>"

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Order History</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Arial, sans-serif;
            background: #000;
            color: #fff;
            padding-bottom: 80px;
        }}

        .header {{
            background: #0d1117;
            padding: 15px;
            border-bottom: 1px solid #222;
            display: flex;
            align-items: center;
        }}
        .header .back-btn {{
            color: #fff;
            text-decoration: none;
            font-size: 18px;
            margin-right: 15px;
        }}
        .header h1 {{
            font-size: 20px;
            color: #14b8a6;
        }}

        .container {{
            max-width: 500px;
            margin: auto;
            padding: 20px 15px;
        }}
        .white-card {{
            background: #ffffff;
            border-radius: 16px;
            padding: 20px;
            color: #000;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }}

        .white-card .page-title {{
            text-align: center;
            font-weight: bold;
            font-size: 18px;
            margin-bottom: 20px;
            color: #000;
        }}

        .search-box {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }}
        .search-box input {{
            flex: 1;
            padding: 10px 15px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            outline: none;
        }}
        .search-box button {{
            background: #1d4ed8;
            color: #fff;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: bold;
            cursor: pointer;
        }}

        .table-header {{
            display: flex;
            font-weight: bold;
            color: #ef4444;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
            margin-bottom: 10px;
        }}
        .table-header .col-id {{ width: 30%; }}
        .table-header .col-pkg {{ width: 40%; }}
        .table-header .col-status {{ width: 30%; text-align: right; color: #000; }}

        .row-item {{
            display: flex;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid #f0f0f0;
        }}
        .row-item .col-id {{
            width: 30%;
            color: #1d4ed8;
            font-weight: bold;
            font-size: 15px;
        }}
        .row-item .col-pkg {{
            width: 40%;
            font-size: 14px;
            font-weight: 500;
        }}
        .row-item .col-status {{
            width: 30%;
            text-align: right;
        }}

        .status-pill {{
            display: inline-block;
            padding: 4px 14px;
            border-radius: 20px;
            color: #fff;
            font-size: 12px;
            font-weight: bold;
            text-transform: lowercase;
        }}

        .pagination {{
            display: flex;
            justify-content: center;
            gap: 5px;
            margin-top: 20px;
        }}
        .pagination .page {{
            display: flex;
            justify-content: center;
            align-items: center;
            width: 35px;
            height: 35px;
            border: 1px solid #ddd;
            border-radius: 6px;
            color: #555;
            text-decoration: none;
            font-weight: bold;
        }}
        .pagination .page.active {{
            background: #1d4ed8;
            color: #fff;
            border-color: #1d4ed8;
        }}

        .bottom-nav {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px 0;
            z-index: 999;
        }}
        .bottom-nav a {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }}
        .bottom-nav a .icon {{
            font-size: 22px;
            margin-bottom: 2px;
        }}
        .bottom-nav a.active {{
            color: #0d1117;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="header">
        <a href="/dashboard" class="back-btn">← Back</a>
        <h1>ဝယ်ယူမှုမှတ်တမ်းများ</h1>
    </div>

    <div class="container">
        <div class="white-card">
            <div class="page-title">ဝယ်ယူမှုမှတ်တမ်းများ</div>
            <form method="GET" action="/orders" class="search-box">
                <input type="text" name="search" placeholder="Search by Game ID" value="{search_query}">
                <button type="submit">Search</button>
            </form>
            <div class="table-header">
                <div class="col-id">ID</div>
                <div class="col-pkg">ပမာဏ</div>
                <div class="col-status">Status</div>
            </div>
            {html}
            <div class="pagination">
                <a href="#" class="page">&lt;</a>
                <a href="#" class="page active">1</a>
                <a href="#" class="page">2</a>
                <a href="#" class="page">&gt;</a>
            </div>
        </div>
    </div>

    <div class="bottom-nav">
        <a href="/dashboard"><span class="icon">🏠</span> Shop</a>
        <a href="/wallet"><span class="icon">💰</span> Recharge</a>
        <a href="/orders" class="active"><span class="icon">📦</span> Order History</a>
        <a href="/profile"><span class="icon">👤</span> Profile</a>
    </div>
</body>
</html>
"""


# ==================================================
# PROFILE - Menu Bar 4 Items
# ==================================================

@app.route("/profile")
def profile():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, email, balance, created_at, device_name FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    conn.close()

    device_name = user[4] if user[4] and user[4] != "Unknown" else "Unknown Device / Browser"

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Profile</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Arial, sans-serif;
            background: #000;
            color: #fff;
            padding-bottom: 80px;
        }}

        .header {{
            background: #0d1117;
            padding: 15px;
            border-bottom: 1px solid #222;
            text-align: center;
        }}
        .header h1 {{
            font-size: 20px;
            color: #14b8a6;
            margin: 0;
        }}

        .container {{
            max-width: 500px;
            margin: auto;
            padding: 20px;
        }}

        .profile-card {{
            background: #0d1117;
            border: 1px solid #222;
            border-radius: 16px;
            padding: 30px 20px;
            text-align: center;
            margin-bottom: 20px;
            color: #fff;
        }}

        .avatar {{
            width: 100px;
            height: 100px;
            border-radius: 50%;
            object-fit: cover;
            margin: 0 auto 15px;
            display: block;
            border: 3px solid #14b8a6;
        }}

        .username {{
            font-size: 24px;
            font-weight: bold;
            color: #14b8a6;
        }}
        .email {{
            color: #94a3b8;
            font-size: 14px;
            margin-top: 5px;
        }}
        .balance-info {{
            color: #4ade80;
            font-size: 18px;
            margin-top: 10px;
            font-weight: bold;
        }}

        .options-card {{
            background: #0d1117;
            border: 1px solid #222;
            border-radius: 16px;
            padding: 15px 20px;
            margin-bottom: 15px;
        }}
        .options-card .row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid #222;
        }}
        .options-card .row:last-child {{
            border-bottom: none;
        }}
        .options-card .label {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 15px;
            color: #fff;
        }}
        .options-card .value {{
            color: #94a3b8;
            font-size: 14px;
        }}
        .options-card .arrow {{
            color: #94a3b8;
            font-size: 18px;
            margin-left: 5px;
        }}
        .options-card a {{
            text-decoration: none;
            color: inherit;
        }}

        .btn-logout {{
            width: 100%;
            padding: 14px;
            background: #ef4444;
            border: none;
            border-radius: 12px;
            font-weight: bold;
            color: #fff;
            font-size: 16px;
            cursor: pointer;
        }}

        .bottom-nav {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #14b8a6;
            display: flex;
            justify-content: space-around;
            padding: 8px 0 12px 0;
            z-index: 999;
        }}
        .bottom-nav a {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: #fff;
            font-size: 11px;
        }}
        .bottom-nav a .icon {{
            font-size: 22px;
            margin-bottom: 2px;
        }}
        .bottom-nav a.active {{
            color: #0d1117;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="header"><h1>👤 Profile</h1></div>

    <div class="container">
        <div class="profile-card">
            <img src="/static/logo.png" class="avatar" alt="Logo">
            <div class="username">{user[0]}</div>
            <div class="email">{user[1] or 'Not set'}</div>
            <div class="balance-info">💰 {int(user[2] or 0):,} Ks</div>
        </div>

        <div class="options-card">
            <div class="row">
                <div class="label">📱 Device Log in</div>
                <div class="value">{device_name}</div>
            </div>
            <a href="/forgot-password">
                <div class="row">
                    <div class="label">🔑 Change Password</div>
                    <div class="value" style="color:#14b8a6;">Edit <span class="arrow">›</span></div>
                </div>
            </a>
        </div>

        <a href="/logout" style="text-decoration:none;">
            <button class="btn-logout">🚪 Logout</button>
        </a>
    </div>

    <div class="bottom-nav">
        <a href="/dashboard"><span class="icon">🏠</span> Shop</a>
        <a href="/wallet"><span class="icon">💰</span> Recharge</a>
        <a href="/orders"><span class="icon">📦</span> Order History</a>
        <a href="/profile" class="active"><span class="icon">👤</span> Profile</a>
    </div>
</body>
</html>
"""

    # ==================================================
# SET LANGUAGE & THEME
# ==================================================

@app.route("/set-language/<lang>")
def set_language(lang):
    if lang in ["mm", "en"]:
        session["lang"] = lang
    return redirect(url_for("dashboard"))

@app.route("/set-theme", methods=["POST"])
def set_theme():
    data = request.get_json()
    if data and "theme" in data:
        session["theme"] = data["theme"]
    return "OK", 200


# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

    # ==================================================
# ADMIN DEPOSITS
# ==================================================

@app.route("/admin/deposits")
def admin_deposits():
    if "username" not in session: return redirect(url_for("login"))
    if session.get("username") != ADMIN_USERNAME: return "❌ Access Denied", 403
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deposit_requests ORDER BY id DESC")
    deposits = cursor.fetchall()
    conn.close()
    deposit_html = ""
    for deposit in deposits:
        status = deposit[5]
        status_html = '<span class="status green">✅ Confirmed</span>' if status == "Confirmed" else '<span class="status red">❌ Rejected</span>' if status == "Rejected" else '<span class="status">🟡 Pending</span>'
        buttons = f'<a href="/admin/deposit/{deposit[0]}/confirm"><button class="green">✅ CONFIRM</button></a><a href="/admin/deposit/{deposit[0]}/reject"><button class="red">❌ REJECT</button></a>' if status == "Pending" else ""
        deposit_html += f'<div class="order-card"><h2>💰 Deposit #{deposit[0]}</h2><p>👤 User: <b>{deposit[1]}</b></p><p>💵 Amount: <b>{deposit[2]:,} Ks</b></p><p>💳 Payment: {deposit[4]}</p><p>🔢 Transaction: {deposit[3]}</p><p>📌 Status: {status_html}</p><p class="small">🕒 {deposit[6]}</p>{buttons}</div>'
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin Deposits</title>{STYLE}</head><body><div class="box"><h1>👑 Deposit Requests</h1>{deposit_html}<a href="/dashboard"><button>⬅️ Dashboard</button></a></div></body></html>"""

@app.route("/admin/deposit/<int:deposit_id>/confirm")
def confirm_deposit(deposit_id):
    if "username" not in session: return redirect(url_for("login"))
    if session.get("username") != ADMIN_USERNAME: return "❌ Access Denied", 403
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deposit_requests WHERE id=?", (deposit_id,))
    deposit = cursor.fetchone()
    if not deposit or deposit[5] != "Pending": conn.close(); return "⚠️ ဒီ Deposit ကို စစ်ပြီးသားပါ။", 400
    cursor.execute("UPDATE users SET balance = balance + ? WHERE username = ?", (deposit[2], deposit[1]))
    cursor.execute("UPDATE deposit_requests SET status = 'Confirmed' WHERE id = ?", (deposit_id,))
    cursor.execute("INSERT INTO wallet_transactions (username, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)", (deposit[1], "DEPOSIT", deposit[2], f"Deposit #{deposit_id} Confirmed", now()))

    # 🔔 Website Bell Notification
    add_user_notification(
        deposit[1],
        "deposit",
        "💰 Deposit အောင်မြင်ပါပြီ",
        f"သင်ဖြည့်ထားသော Deposit {deposit[2]:,} Ks ကို Wallet ထဲထည့်ပြီးပါပြီ။"
    )

    conn.commit()
    conn.close()
    send_message_to_user(deposit[1], f"✅ <b>Deposit Confirmed</b>\nDeposit #{deposit_id}\nAmount: {deposit[2]:,} Ks")
    return redirect("/admin/deposits")

@app.route("/admin/deposit/<int:deposit_id>/reject")
def reject_deposit(deposit_id):
    if "username" not in session: return redirect(url_for("login"))
    if session.get("username") != ADMIN_USERNAME: return "❌ Access Denied", 403
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deposit_requests WHERE id=?", (deposit_id,))
    deposit = cursor.fetchone()
    if not deposit or deposit[5] != "Pending": conn.close(); return "⚠️ ဒီ Deposit ကို စစ်ပြီးသားပါ။", 400
    cursor.execute("UPDATE deposit_requests SET status = 'Rejected' WHERE id = ?", (deposit_id,))
    conn.commit()
    conn.close()
    return redirect("/admin/deposits")

@app.route("/admin/orders")
def admin_orders():
    if "username" not in session: return redirect(url_for("login"))
    if session.get("username") != ADMIN_USERNAME: return "❌ Access Denied", 403
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY id DESC")
    orders = cursor.fetchall()
    conn.close()
    order_html = ""
    for order in orders:
        status = order[9]
        status_html = '<span class="status green">✅ Confirmed</span>' if status == "Confirmed" else '<span class="status red">❌ Rejected</span>' if status == "Rejected" else '<span class="status">🟡 Pending</span>'
        buttons = f'<a href="/admin/order/{order[0]}/confirm"><button class="green">✅ CONFIRM</button></a><a href="/admin/order/{order[0]}/reject"><button class="red">❌ REJECT</button></a>' if status == "Pending" else ""
        order_html += f'<div class="order-card"><h2>🛒 Order #{order[0]}</h2><p>👤 User: <b>{order[1]}</b></p><p>🎮 Product: {order[2]}</p><p>📦 Package: {order[3]}</p><p>🆔 Game ID: {order[4] or "-"}</p><p>🌎 Server ID: {order[5] or "-"}</p><p>📱 Telegram: {order[6] or "-"}</p><p>📧 Mail: {order[7] or "-"}</p><p>💳 Payment: {order[8] or "-"}</p><p>📌 Status: {status_html}</p><p class="small">🕒 {order[10]}</p>{buttons}</div>'
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin Orders</title>{STYLE}</head><body><div class="box"><h1>👑 Admin Orders</h1>{order_html}<a href="/dashboard"><button>⬅️ Dashboard</button></a></div></body></html>"""

@app.route("/admin/order/<int:order_id>/confirm")
def confirm_order(order_id):
    if "username" not in session:
        return redirect(url_for("login"))
    if session.get("username") != ADMIN_USERNAME:
        return "❌ Access Denied", 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    order = cursor.fetchone()

    if not order or order[9] != "Pending":
        conn.close()
        return "⚠️ ဒီ Order ကို စစ်ပြီးသားပါ။", 400

    package = order[3]
    package_price_map = {
        "10 💎 - 1,000 Ks": 1000, "12 💎 - 1,200 Ks": 1200, "20 💎 - 1,900 Ks": 1900,
        "22 💎 - 2,100 Ks": 2100, "33 💎 - 3,000 Ks": 3000, "44 💎 - 3,600 Ks": 3600,
        "55 💎 - 4,000 Ks": 4000, "56 💎 - 4,400 Ks": 4400, "86 💎 - 5,600 Ks": 5600,
        "172 💎 - 10,800 Ks": 10800, "257 💎 - 15,800 Ks": 15800, "279 💎 - 17,100 Ks": 17100,
        "343 💎 - 20,600 Ks": 20600, "429 💎 - 25,900 Ks": 25900, "Weekly Pass - 6,400 Ks": 6400,
        "60 UC - 600 Ks": 600, "325 UC - 3,250 Ks": 3250, "660 UC - 6,600 Ks": 6600,
        "1800 UC - 18,000 Ks": 18000, "3850 UC - 38,500 Ks": 38500,
        "3 Months - 3,000 Ks": 3000, "6 Months - 6,000 Ks": 6000, "12 Months - 12,000 Ks": 12000,
        "30 BRL - 24,500 Ks": 24500, "100 BRL - 85,500 Ks": 85500, "500 BRL - 424,000 Ks": 424000,
        "280 PHP - 22,000 Ks": 22000, "560 PHP - 42,000 Ks": 42000, "1120 PHP - 83,000 Ks": 83000,
        "60 Tokens - 1,000 Ks": 1000, "120 Tokens - 2,000 Ks": 2000, "250 Tokens - 4,000 Ks": 4000,
        "500 Tokens - 8,000 Ks": 8000, "1000 Tokens - 15,000 Ks": 15000,
    }

    price = package_price_map.get(package, 0)
    cursor.execute("UPDATE orders SET status='Confirmed' WHERE id=?", (order_id,))
    cursor.execute("UPDATE users SET balance = balance - ? WHERE username = ?", (price, order[1]))
    cursor.execute("INSERT INTO wallet_transactions (username, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)", (order[1], "PURCHASE", price, f"Order #{order_id} Confirmed: {order[2]} - {package}", now()))

    # 🔔 Website Bell Notification
    order_amount_text = get_order_amount_text(package)
    add_user_notification(
        order[1],
        "order",
        "🎮 Order အောင်မြင်ပါပြီ",
        f"သင်ဖြည့်ထားသော {order_amount_text or package} ကို In Game ထဲဖြည့်ပြီးပါပြီ။"
    )

    conn.commit()
    conn.close()

    send_message_to_user(order[1], f"✅ <b>Order Confirmed</b>\nOrder #{order_id}\nProduct: {order[2]}\nPackage: {package}")
    return redirect("/admin/orders")

@app.route("/admin/order/<int:order_id>/reject")
def reject_order(order_id):
    if "username" not in session: return redirect(url_for("login"))
    if session.get("username") != ADMIN_USERNAME: return "❌ Access Denied", 403
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    order = cursor.fetchone()
    if not order or order[9] != "Pending": conn.close(); return "⚠️ ဒီ Order ကို စစ်ပြီးသားပါ။", 400
    cursor.execute("UPDATE orders SET status='Rejected' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    send_message_to_user(order[1], f"❌ <b>Order Rejected</b>\nOrder #{order_id}\nProduct: {order[2]}\nPackage: {order[3]}")
    return redirect("/admin/orders")

    # ==================================================
# PRIVACY PAGE
# ==================================================

@app.route("/privacy")
def privacy_page():
    try:
        with open("privacy.html", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Privacy Policy page not found.", 404


def add_user_notification(username, notification_type, title, message):
    """Create a bell notification for a website user."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notifications (username, type, title, message, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, notification_type, title, message, 0, now()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Notification Error for {username}: {e}")
        try:
            conn.close()
        except:
            pass
        return False


def get_order_amount_text(package):
    """Return only the item amount, e.g. '86 💎' from '86 💎 - 5,600 Ks'."""
    if not package:
        return ""
    return str(package).split(" - ")[0].strip()


# ==================================================
# TELEGRAM CALLBACK HELPERS
# ==================================================

def edit_telegram_button_message(chat_id, message_id, text):
    if chat_id is None or message_id is None: return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": json.dumps({"inline_keyboard": []})}
    try:
        response = requests.post(url, data=data, timeout=20)
        return response.status_code == 200
    except Exception as e:
        print("Telegram edit error:", e)
        return False


def confirm_deposit_from_telegram(deposit_id, chat_id, message_id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM deposit_requests WHERE id=?", (deposit_id,))
    deposit = cursor.fetchone()
    if not deposit or deposit[5] != "Pending": conn.close(); return
    cursor.execute("UPDATE users SET balance = balance + ? WHERE username = ?", (deposit[2], deposit[1]))
    cursor.execute("UPDATE deposit_requests SET status='Confirmed' WHERE id=?", (deposit_id,))
    cursor.execute("INSERT INTO wallet_transactions (username, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)", (deposit[1], "DEPOSIT", deposit[2], f"Deposit #{deposit_id} Confirmed via Telegram", now()))

    # 🔔 Website Bell Notification
    add_user_notification(
        deposit[1],
        "deposit",
        "💰 Deposit အောင်မြင်ပါပြီ",
        f"သင်ဖြည့်ထားသော Deposit {deposit[2]:,} Ks ကို Wallet ထဲထည့်ပြီးပါပြီ။"
    )

    conn.commit(); conn.close()
    edit_telegram_button_message(chat_id, message_id, f"✅ Deposit #{deposit_id} Confirmed!\n👤 User: {deposit[1]}\n💵 Amount: {deposit[2]:,} Ks")
    send_message_to_user(deposit[1], f"✅ <b>Deposit Confirmed</b>\nDeposit #{deposit_id}\nAmount: {deposit[2]:,} Ks")

def reject_deposit_from_telegram(deposit_id, chat_id, message_id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM deposit_requests WHERE id=?", (deposit_id,))
    deposit = cursor.fetchone()
    if not deposit or deposit[5] != "Pending": conn.close(); return
    cursor.execute("UPDATE deposit_requests SET status='Rejected' WHERE id=?", (deposit_id,))
    conn.commit(); conn.close()
    edit_telegram_button_message(chat_id, message_id, f"❌ Deposit #{deposit_id} Rejected!\n👤 User: {deposit[1]}")
    send_message_to_user(deposit[1], f"❌ <b>Deposit Rejected</b>\nDeposit #{deposit_id}")

def confirm_order_from_telegram(order_id, chat_id, message_id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    order = cursor.fetchone()
    if not order or order[9] != "Pending": conn.close(); return
    package_price_map = {
        "10 💎 - 1,000 Ks": 1000, "12 💎 - 1,200 Ks": 1200, "20 💎 - 1,900 Ks": 1900,
        "22 💎 - 2,100 Ks": 2100, "33 💎 - 3,000 Ks": 3000, "44 💎 - 3,600 Ks": 3600,
        "55 💎 - 4,000 Ks": 4000, "56 💎 - 4,400 Ks": 4400, "86 💎 - 5,600 Ks": 5600,
        "172 💎 - 10,800 Ks": 10800, "257 💎 - 15,800 Ks": 15800, "279 💎 - 17,100 Ks": 17100,
        "343 💎 - 20,600 Ks": 20600, "429 💎 - 25,900 Ks": 25900, "Weekly Pass - 6,400 Ks": 6400,
        "60 UC - 600 Ks": 600, "325 UC - 3,250 Ks": 3250, "660 UC - 6,600 Ks": 6600,
        "1800 UC - 18,000 Ks": 18000, "3850 UC - 38,500 Ks": 38500,
        "3 Months - 3,000 Ks": 3000, "6 Months - 6,000 Ks": 6000, "12 Months - 12,000 Ks": 12000,
        "30 BRL - 24,500 Ks": 24500, "100 BRL - 85,500 Ks": 85500, "500 BRL - 424,000 Ks": 424000,
        "280 PHP - 22,000 Ks": 22000, "560 PHP - 42,000 Ks": 42000, "1120 PHP - 83,000 Ks": 83000,
        "60 Tokens - 1,000 Ks": 1000, "120 Tokens - 2,000 Ks": 2000, "250 Tokens - 4,000 Ks": 4000,
        "500 Tokens - 8,000 Ks": 8000, "1000 Tokens - 15,000 Ks": 15000,
    }
    price = package_price_map.get(order[3], 0)

    if order[2] in {"ML", "PUBG"} and flash_topup_enabled():
        conn.close()
        result = flash_place_order(order[2], order[3], order[4], order[5], order_id)
        if result.get("success"):
            conn = get_db(); cursor = conn.cursor()
            cursor.execute("UPDATE orders SET status='Completed' WHERE id=?", (order_id,))
            conn.commit(); conn.close()
            edit_telegram_button_message(chat_id, message_id, f"🟢 Order #{order_id} Auto Recharge {result.get('status','Completed')}\n👤 User: {order[1]}\n🎮 Product: {order[2]}\n📦 {order[3]}")
        else:
            edit_telegram_button_message(chat_id, message_id, f"❌ Order #{order_id} Auto Recharge Failed\n{result.get('error','Unknown error')}")
        return

    cursor.execute("UPDATE orders SET status='Confirmed' WHERE id=?", (order_id,))
    cursor.execute("UPDATE users SET balance = balance - ? WHERE username = ?", (price, order[1]))
    cursor.execute("INSERT INTO wallet_transactions (username, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)", (order[1], "PURCHASE", price, f"Order #{order_id} Confirmed via Telegram: {order[2]} - {order[3]}", now()))

    order_amount_text = get_order_amount_text(order[3])
    add_user_notification(
        order[1],
        "order",
        "🎮 Order အောင်မြင်ပါပြီ",
        f"သင်ဖြည့်ထားသော {order_amount_text or order[3]} ကို In Game ထဲဖြည့်ပြီးပါပြီ။"
    )

    conn.commit(); conn.close()
    edit_telegram_button_message(chat_id, message_id, f"✅ Order #{order_id} Confirmed!\n👤 User: {order[1]}\n🎮 Product: {order[2]}\n💵 Deducted: {price:,} Ks")
    send_message_to_user(order[1], f"✅ <b>Order Confirmed</b>\nOrder #{order_id}\nProduct: {order[2]}\nPackage: {order[3]}\n💵 Deducted: {price:,} Ks")

def reject_order_from_telegram(order_id, chat_id, message_id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    order = cursor.fetchone()
    if not order or order[9] != "Pending": conn.close(); return
    cursor.execute("UPDATE orders SET status='Rejected' WHERE id=?", (order_id,))
    conn.commit(); conn.close()
    edit_telegram_button_message(chat_id, message_id, f"❌ Order #{order_id} Rejected!\n👤 User: {order[1]}")
    send_message_to_user(order[1], f"❌ <b>Order Rejected</b>\nOrder #{order_id}\nProduct: {order[2]}")


# ==================================================
# MAIN TELEGRAM CALLBACK
# ==================================================

@app.route("/telegram_callback", methods=["POST"])
def telegram_callback():
    try:
        data = request.get_json(silent=True) or {}
        callback = data.get("callback_query") or {}
        callback_data = callback.get("data", "")
        callback_message = callback.get("message") or {}
        callback_message_id = callback_message.get("message_id")
        callback_chat = callback_message.get("chat") or {}
        callback_chat_id = callback_chat.get("id")
        callback_id = callback.get("id")

        if callback_id:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", data={"callback_query_id": callback_id}, timeout=10)

        if callback_data.startswith("confirm_deposit_"):
            confirm_deposit_from_telegram(int(callback_data.rsplit("_", 1)[1]), callback_chat_id, callback_message_id)
        elif callback_data.startswith("reject_deposit_"):
            reject_deposit_from_telegram(int(callback_data.rsplit("_", 1)[1]), callback_chat_id, callback_message_id)
        elif callback_data.startswith("confirm_order_"):
            confirm_order_from_telegram(int(callback_data.rsplit("_", 1)[1]), callback_chat_id, callback_message_id)
        elif callback_data.startswith("reject_order_"):
            reject_order_from_telegram(int(callback_data.rsplit("_", 1)[1]), callback_chat_id, callback_message_id)

        incoming_msg = data.get("message")
        if incoming_msg:
            user_chat = incoming_msg.get("chat") or {}
            user_chat_id = user_chat.get("id")
            message_id_in = incoming_msg.get("message_id")
            text = (incoming_msg.get("text") or incoming_msg.get("caption") or "").strip()
            reply_to = incoming_msg.get("reply_to_message") or {}

            if user_chat_id == OWNER_CHAT_ID and message_id_in and reply_to.get("message_id"):
                owner_reply_to_message_id = reply_to.get("message_id")
                conn = get_db(); cursor = conn.cursor()
                cursor.execute("SELECT customer_chat_id FROM telegram_forward_map WHERE owner_message_id=?", (owner_reply_to_message_id,))
                mapped = cursor.fetchone()
                conn.close()
                if mapped and mapped[0]:
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/copyMessage", data={"chat_id": mapped[0], "from_chat_id": OWNER_CHAT_ID, "message_id": message_id_in}, timeout=20)
                    return "OK", 200

            if text == "/start":
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": user_chat_id, "text": "Hello, Eren's shop 🛒 ကနေကြိုဆိုပါတယ်ဗျာ\nML Dia/PUBG UC/Tg Pre/ Smile One Code တွေကိုလည်း Bot Website ကနေတစ်ဆင့် Order တင်နိုင်ပါတယ်ဗျာ။\n#Bot_Owner - t.me/erenIsNot4U"}, timeout=20)

            elif user_chat_id and message_id_in:
                forward_response = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/forwardMessage", data={"chat_id": OWNER_CHAT_ID, "from_chat_id": user_chat_id, "message_id": message_id_in}, timeout=20)
                if forward_response.status_code == 200:
                    forward_data_json = forward_response.json().get("result", {})
                    owner_forwarded_message_id = forward_data_json.get("message_id")
                    if owner_forwarded_message_id:
                        conn = get_db(); cursor = conn.cursor()
                        cursor.execute("INSERT OR REPLACE INTO telegram_forward_map (owner_message_id, customer_chat_id, customer_message_id, created_at) VALUES (?, ?, ?, ?)", (int(owner_forwarded_message_id), int(user_chat_id), int(message_id_in), now()))
                        conn.commit(); conn.close()
                    sent = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": user_chat_id, "text": "Message Sent To Owner ✅"}, timeout=20)
                    if sent.status_code == 200:
                        confirmation_message_id = sent.json().get("result", {}).get("message_id")
                        def delete_confirmation():
                            time.sleep(3)
                            if confirmation_message_id:
                                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage", data={"chat_id": user_chat_id, "message_id": confirmation_message_id}, timeout=10)
                                except: pass
                        threading.Thread(target=delete_confirmation, daemon=True).start()
        return "OK", 200
    except Exception as e:
        print(f"Callback error: {e}")
        return "OK", 200


# ==================================================
# WSGI APPLICATION (PythonAnywhere)
# ==================================================

application = app
