import os
import sqlite3
import requests
import json
import time
import hmac
import hashlib
import uuid
from datetime import datetime
from flask import Flask, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")

# ==========================================
# FLASHTOPUP API CONFIG
# ==========================================
FLASHTOPUP_API_ID = "RSL5YP4YFXLEGL8X"
FLASHTOPUP_API_KEY = "4aadba4402eceffa0e6f777a8b09c7709c74c5c7556c9cc7e72e8740639e2f6e"
FLASHTOPUP_BASE_URL = "https://api.flashtopup.com/api/reseller/v2"

# ==========================================
# SMILE ONE API CONFIG
# ==========================================
SMILE_ONE_API_URL = os.getenv("SMILE_ONE_API_URL")
SMILE_ONE_UID = os.getenv("SMILE_ONE_UID")
SMILE_ONE_API_KEY = os.getenv("SMILE_ONE_API_KEY")

# ==========================================
# DATABASE
# ==========================================
def get_db():
    conn = sqlite3.connect("shop.db")
    conn.row_factory = sqlite3.Row
    return conn

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            balance REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            game TEXT NOT NULL,
            package TEXT NOT NULL,
            game_id TEXT,
            server_id TEXT,
            telegram_username TEXT,
            acc_mail TEXT,
            payment TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# ==========================================
# FLASHTOPUP FUNCTIONS
# ==========================================
def create_flashtopup_signature(method, path, body):
    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4())
    body_str = json.dumps(body, separators=(',', ':')) if body else ""
    body_hash = hashlib.sha256(body_str.encode()).hexdigest()
    message = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_hash}\n"
    signature = hmac.new(FLASHTOPUP_API_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()
    return timestamp, nonce, signature

def flash_topup_enabled():
    return bool(FLASHTOPUP_API_ID and FLASHTOPUP_API_KEY and FLASHTOPUP_BASE_URL)

def flash_place_order(game, package, game_id, server_id, order_id):
    product_code = ""
    
    # ML Product Codes
    if game == "ML":
        if "10 💎" in package:
            product_code = "ML_DIAMONDS_10"
        elif "12 💎" in package:
            product_code = "ML_DIAMONDS_12"
        elif "20 💎" in package:
            product_code = "ML_DIAMONDS_20"
        elif "22 💎" in package:
            product_code = "ML_DIAMONDS_22"
        elif "33 💎" in package:
            product_code = "ML_DIAMONDS_33"
        elif "44 💎" in package:
            product_code = "ML_DIAMONDS_44"
        elif "55 💎" in package:
            product_code = "ML_DIAMONDS_55"
        elif "56 💎" in package:
            product_code = "ML_DIAMONDS_56"
        elif "86 💎" in package:
            product_code = "ML_DIAMONDS_86"
        elif "172 💎" in package:
            product_code = "ML_DIAMONDS_172"
        elif "257 💎" in package:
            product_code = "ML_DIAMONDS_257"
        elif "279 💎" in package:
            product_code = "ML_DIAMONDS_279"
        elif "343 💎" in package:
            product_code = "ML_DIAMONDS_343"
        elif "429 💎" in package:
            product_code = "ML_DIAMONDS_429"
        elif "Weekly Pass" in package:
            product_code = "ML_WEEKLY_PASS"

# PUBG Product Codes
elif game == "PUBG":
    if "60 UC" in package:
        product_code = "PUBG_UC_60"
    elif "325 UC" in package:
        product_code = "PUBG_UC_325"
    elif "660 UC" in package:
        product_code = "PUBG_UC_660"
    elif "1800 UC" in package:
        product_code = "PUBG_UC_1800"
    elif "3850 UC" in package:
        product_code = "PUBG_UC_3850"

# HOK Product Codes
elif game == "HOK":
    if "3 Months" in package:
        product_code = "HOK_3_MONTHS"
    elif "6 Months" in package:
        product_code = "HOK_6_MONTHS"
    elif "12 Months" in package:
        product_code = "HOK_12_MONTHS"

if not product_code:
    return {"success": False, "error": f"Package '{package}' အတွက် Product Code မတွေ့ပါ။"}

path = "/order"
url = f"{FLASHTOPUP_BASE_URL}/order"

payload = {
    "product_code": product_code,
    "user_id": game_id,
    "server_id": server_id if server_id else "",
    "amount": 1,
    "reference_id": str(order_id)
}

timestamp, nonce, signature = create_flashtopup_signature("POST", path, payload)

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-FT-API-ID": FLASHTOPUP_API_ID,
    "X-FT-Timestamp": timestamp,
    "X-FT-Nonce": nonce,
    "X-FT-Signature": signature
}

try:
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response_data = response.json()
    if response.status_code == 200 and response_data.get("status") == "success":
        return {"success": True, "data": response_data}
    else:
        return {"success": False, "error": response.text}
except Exception as e:
    return {"success": False, "error": str(e)}

# ==========================================
# SMILE ONE FUNCTIONS
# ==========================================
def get_smile_one_code(amount, currency, email=None):
    try:
        url = f"{SMILE_ONE_API_URL}/generate"
        payload = {"amount": amount, "currency": currency}
        if email:
            payload["email"] = email
        headers = {
            "Authorization": f"Bearer {SMILE_ONE_API_KEY}",
            "X-UID": SMILE_ONE_UID,
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        data = response.json()
        if data.get("success"):
            return {"success": True, "code": data.get("code")}
        return {"success": False, "error": data.get("error", "Unknown Error")}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==========================================
# HTML STYLES
# ==========================================
STYLE = """
<style>
    body { font-family: Arial, sans-serif; background: #0f172a; color: #fff; padding-bottom: 80px; margin: 0; }
    .box { max-width: 500px; margin: 0 auto; padding: 15px; }
    .success { background: #22c55e; color: white; padding: 10px; border-radius: 8px; margin-bottom: 10px; }
    .error { background: #ef4444; color: white; padding: 10px; border-radius: 8px; margin-bottom: 10px; }
    .green { background: #14b8a6; color: white; border: none; border-radius: 8px; padding: 10px; cursor: pointer; }
    .auto-badge { background: #fbbf24; color: #0d1117; padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: bold; margin-left: 6px; text-transform: uppercase; }
    input, select { width: 100%; padding: 10px; border-radius: 8px; border: none; background: #1e293b; color: #fff; }
    label { color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px; }
</style>
"""

# ==========================================
# ROUTES
# ==========================================
@app.route("/")
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("order"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session["username"] = username
            return redirect(url_for("dashboard"))
        flash("Invalid credentials")
        return redirect(url_for("login"))

return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login</title>
    <style>
        body { background: #0f172a; color: #fff; font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #1e293b; padding: 40px; border-radius: 12px; width: 100%; max-width: 350px; }
        h1 { color: #14b8a6; text-align: center; }
        input { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: none; background: #0f172a; color: #fff; }
        button { width: 100%; padding: 12px; background: #14b8a6; border: none; border-radius: 8px; color: #fff; font-size: 16px; cursor: pointer; }
        a { color: #14b8a6; text-decoration: none; display: block; text-align: center; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>🔐 Login</h1>
        <form method="POST">
            <input name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        <a href="/register">Account မရှိသေးဘူး? Register</a>
    </div>
</body>
</html>
"""

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            flash("Username and password required")
            return redirect(url_for("register"))
        
        conn = get_db()
        existing = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            flash("Username already exists")
            conn.close()
            return redirect(url_for("register"))
        
        hashed = generate_password_hash(password)
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
        conn.commit()
        conn.close()
        flash("Account created! Please login.")
        return redirect(url_for("login"))

return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register</title>
    <style>
        body { background: #0f172a; color: #fff; font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .register-box { background: #1e293b; padding: 40px; border-radius: 12px; width: 100%; max-width: 350px; }
        h1 { color: #14b8a6; text-align: center; }
        input { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: none; background: #0f172a; color: #fff; }
        button { width: 100%; padding: 12px; background: #14b8a6; border: none; border-radius: 8px; color: #fff; font-size: 16px; cursor: pointer; }
        a { color: #14b8a6; text-decoration: none; display: block; text-align: center; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="register-box">
        <h1>📝 Register</h1>
        <form method="POST">
            <input name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Register</button>
        </form>
        <a href="/login">Already have account? Login</a>
    </div>
</body>
</html>
"""

@app.route("/order", methods=["GET"])
def order():
    if "username" not in session:
        return redirect(url_for("login"))
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Order</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #000; color: #fff; padding-bottom: 80px; }
        .grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; padding: 15px; max-width: 500px; margin: auto; }
        .card { background: #14b8a6; border-radius: 12px; padding: 15px 10px; text-align: center; text-decoration: none; color: #fff; display: block; }
        .card .name { font-weight: bold; font-size: 14px; }
        .bottom-nav { position: fixed; bottom: 0; left: 0; right: 0; background: #14b8a6; display: flex; justify-content: space-around; padding: 8px 0 12px 0; z-index: 999; }
        .bottom-nav a { display: flex; flex-direction: column; align-items: center; text-decoration: none; color: #fff; font-size: 11px; }
        .bottom-nav a .icon { font-size: 22px; margin-bottom: 2px; }
        .bottom-nav a.active { color: #0d1117; font-weight: bold; }
        .auto-badge { background: #fbbf24; color: #0d1117; padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: bold; margin-left: 6px; text-transform: uppercase; }
    </style>
</head>
<body>
    <div class="grid-2">
        <a href="/packages/ML" class="card">
            <div class="name">Mobile Legends <span class="auto-badge">Auto</span></div>
        </a>
        <a href="/packages/PUBG" class="card">
            <div class="name">PUBG Mobile <span class="auto-badge">Auto</span></div>
        </a>
        <a href="/packages/HOK" class="card">
            <div class="name">Honor Of Kings <span class="auto-badge">Auto</span></div>
        </a>
        <a href="/packages/TG Pre" class="card">
            <div class="name">Telegram Premium</div>
        </a>
        <a href="/packages/Smile One Code BRL" class="card">
            <div class="name">Smile One BRL</div>
        </a>
        <a href="/packages/Smile One Coin PHP" class="card">
            <div class="name">Smile One PHP</div>
        </a>
    </div>
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

@app.route("/packages/<game>", methods=["GET"])
def packages(game):
    if "username" not in session:
        return redirect(url_for("login"))
    
    package_lists = {
        "ML": ["10 💎 - 1,000 Ks", "12 💎 - 1,200 Ks", "20 💎 - 1,900 Ks", "22 💎 - 2,100 Ks", 
               "33 💎 - 3,000 Ks", "44 💎 - 3,600 Ks", "55 💎 - 4,000 Ks", "56 💎 - 4,400 Ks",
               "86 💎 - 5,600 Ks", "172 💎 - 10,800 Ks", "257 💎 - 15,800 Ks", "279 💎 - 17,100 Ks",
               "343 💎 - 20,600 Ks", "429 💎 - 25,900 Ks", "Weekly Pass - 6,400 Ks"],
        "PUBG": ["60 UC - 600 Ks", "325 UC - 3,250 Ks", "660 UC - 6,600 Ks", "1800 UC - 18,000 Ks", "3850 UC - 38,500 Ks"],
        "HOK": ["3 Months - 3,000 Ks", "6 Months - 6,000 Ks", "12 Months - 12,000 Ks"],
        "TG Pre": ["60 Tokens - 1,000 Ks", "120 Tokens - 2,000 Ks", "250 Tokens - 4,000 Ks", "500 Tokens - 8,000 Ks", "1000 Tokens - 15,000 Ks"],
        "Smile One Code BRL": ["30 BRL - 24,500 Ks", "100 BRL - 85,500 Ks", "500 BRL - 424,000 Ks"],
        "Smile One Coin PHP": ["280 PHP - 22,000 Ks", "560 PHP - 42,000 Ks", "1120 PHP - 83,000 Ks"]
    }
    
    packages = package_lists.get(game, [])
    if not packages:
        return f"<h1>{game}</h1><p>ပစ္စည်းမရှိသေးပါ</p><a href='/order'>← Back</a>"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{game} Packages</title>
        <style>
            body {{ background: #0f172a; color: #fff; font-family: Arial, sans-serif; padding: 20px; }}
            h1 {{ color: #14b8a6; }}
            .package {{ background: #1e293b; padding: 12px 16px; margin: 8px 0; border-radius: 8px; display: block; color: #fff; text-decoration: none; }}
            .package:hover {{ background: #334155; }}
            .back {{ color: #14b8a6; text-decoration: none; display: block; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <h1>📦 {game} Packages</h1>
    """
    for pkg in packages:
        html += f'<a href="/place_order?game={game}&package={pkg}" class="package">{pkg}</a>'
    html += f'<a href="/order" class="back">← Back to Shop</a>'
    html += "</body></html>"
    return html

@app.route("/wallet")
def wallet():
    if "username" not in session:
        return redirect(url_for("login"))
    return "<h1>💰 Wallet</h1><p>Balance: 0 Ks</p>"

@app.route("/orders")
def orders():
    if "username" not in session:
        return redirect(url_for("login"))
    return "<h1>📦 Order History</h1><p>Order list will appear here</p>"

@app.route("/profile")
def profile():
    if "username" not in session:
        return redirect(url_for("login"))
    return "<h1>👤 Profile</h1><p>Username: " + session["username"] + "</p>"

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
    
    # GET request အတွက် ပြရုံပါ
    if request.method == "GET":
        return render_place_order_form(game, package, message, message_type)

    # POST request (အော်ဒါတင်ခြင်း)
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
                    # ========== AUTO TOP UP LOGIC ==========
                    if game in {"ML", "PUBG", "HOK"} and flash_topup_enabled():
                        cursor.execute("""INSERT INTO orders (username, game, package, game_id, server_id, telegram_username, acc_mail, payment, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                       (username, game, package, game_id, server_id, telegram_username, acc_mail, payment, "Pending", now()))
                        order_id = cursor.lastrowid
                        conn.commit()
                        
                        result = flash_place_order(game, package, game_id, server_id, order_id)
                        if result.get("success"):
                            cursor = conn.cursor()
                            cursor.execute("UPDATE orders SET status='Completed' WHERE id=?", (order_id,))
                            conn.commit()
                            message = f"✅ Order #{order_id} Auto Recharge အောင်မြင်ပါပြီ။"
                        else:
                            message = f"❌ Auto Recharge မအောင်မြင်ပါ။\n{result.get('error', 'Unknown error')}"
                            message_type = "error"
                        conn.close()
                    
                    elif game == "Smile One Coin PHP":
                        result = get_smile_one_code(package_price, "PHP", email=acc_mail)
                        if result.get("success"):
                            cursor.execute("INSERT INTO orders (username, game, package, status, created_at) VALUES (?, ?, ?, ?, ?)",
                                           (username, game, package, "Completed", now()))
                            order_id = cursor.lastrowid
                            conn.commit()
                            message = f"✅ {package_price} Ks တန်ဖိုးရှိ Smile One PHP Coin အောင်မြင်ပါပြီ။"
                        else:
                            message = f"❌ Error: {result.get('error')}"
                            message_type = "error"
                        conn.close()
                    
                    elif game == "Smile One Code BRL":
                        result = get_smile_one_code(package_price, "BRL")
                        if result.get("success"):
                            cursor.execute("INSERT INTO orders (username, game, package, status, created_at) VALUES (?, ?, ?, ?, ?)",
                                           (username, game, package, "Completed", now()))
                            order_id = cursor.lastrowid
                            conn.commit()
                            message = f"✅ Code: {result.get('code')}"
                        else:
                            message = f"❌ Error: {result.get('error')}"
                            message_type = "error"
                        conn.close()
                    
                    else:
                        cursor.execute("INSERT INTO orders (username, game, package, game_id, server_id, telegram_username, acc_mail, payment, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                       (username, game, package, game_id, server_id, telegram_username, acc_mail, payment, "Pending", now()))
                        order_id = cursor.lastrowid
                        conn.commit()
                        message = f"✅ Order #{order_id} တင်ပြီးပါပြီ။"
                        conn.close()

        except Exception as e:
            message = f"❌ Error: {str(e)}"
            message_type = "error"
            if conn:
                conn.close()

    return render_place_order_form(game, package, message, message_type)

def render_place_order_form(game, package, message="", message_type="success"):
    # Game နဲ့ Package အတွက် သီးသန့်နောက်ထပ် field တွေပြဖို့
    extra_fields = ""
    if game == "TG Pre":
        extra_fields = """
        <div style="margin-top: 12px;">
            <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Telegram Username</label>
            <input type="text" name="telegram_username" placeholder="@username" required style="width: 100%; padding: 10px; border-radius: 8px; border: none; background: #1e293b; color: #fff;">
        </div>
        """
    elif game == "Smile One Coin PHP":
        extra_fields = """
        <div style="margin-top: 12px;">
            <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Account Email</label>
            <input type="email" name="acc_mail" placeholder="email@example.com" required style="width: 100%; padding: 10px; border-radius: 8px; border: none; background: #1e293b; color: #fff;">
        </div>
        """
    elif game in ["ML", "PUBG", "HOK"]:
        extra_fields = """
        <div style="margin-top: 12px;">
            <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Game ID / UID</label>
            <input type="text" name="game_id" placeholder="Enter Game ID" required style="width: 100%; padding: 10px; border-radius: 8px; border: none; background: #1e293b; color: #fff;">
        </div>
        <div style="margin-top: 12px;">
            <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Server ID</label>
            <input type="text" name="server_id" placeholder="Enter Server ID" style="width: 100%; padding: 10px; border-radius: 8px; border: none; background: #1e293b; color: #fff;">
        </div>
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Place Order</title>
    {STYLE}
    <style>
        body {{ background: #0f172a; padding-bottom: 80px; }}
        .header {{ background: #0d1117; padding: 15px; border-bottom: 1px solid #222; display: flex; align-items: center; position: relative; justify-content: center; }}
        .header .back-btn {{ position: absolute; left: 15px; color: #fff; text-decoration: none; font-size: 18px; }}
        .header h1 {{ font-size: 20px; color: #14b8a6; margin: 0; }}
        .bottom-nav {{ position: fixed; bottom: 0; left: 0; right: 0; background: #14b8a6; display: flex; justify-content: space-around; padding: 8px 0 12px 0; z-index: 999; }}
        .bottom-nav a {{ display: flex; flex-direction: column; align-items: center; text-decoration: none; color: #fff; font-size: 11px; }}
        .bottom-nav a .icon {{ font-size: 22px; margin-bottom: 2px; }}
        .bottom-nav a.active {{ color: #0d1117; font-weight: bold; }}
        input, select {{ width: 100%; padding: 10px; border-radius: 8px; border: none; background: #1e293b; color: #fff; }}
        label {{ color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px; }}
    </style>
</head>
<body>
    <div class="header">
        <a href="javascript:history.back()" class="back-btn">← Back</a>
        <h1>🛒 Place Order</h1>
    </div>

    <div class="box">
        <div class="{message_type}" style="margin-top:12px;">{message if message else 'ကျေးဇူးပြု၍ အောက်ပါအချက်များ ဖြည့်ပါ။'}</div>
        <form method="POST">
            <input type="hidden" name="game" value="{game}">
            <input type="hidden" name="package" value="{package}">
            <div style="margin-top: 12px;">
                <label>Package</label>
                <input type="text" value="{package}" disabled style="opacity: 0.7; background: #0f172a;">
            </div>
            {extra_fields}
            <div style="margin-top: 12px;">
                <label>Payment</label>
                <select name="payment" required>
                    <option value="">💳 Payment ရွေးပါ</option>
                    <option value="Wallet">💰 Wallet</option>
                </select>
            </div>
            <button type="submit" class="green" style="margin-top: 20px; width: 100%; padding: 14px; font-size: 16px; border: none; border-radius: 8px; cursor: pointer;" onclick="this.disabled = true; this.innerHTML = '⏳ Order တင်နေပါတယ်...'; this.form.submit();">🛒 Order တင်မည်</button>
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

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
