import os
import sqlite3
import requests
import json
import threading
import time
import hmac
import hashlib
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# ==========================================
# FLASHTOPUP API CONFIG
# ==========================================
FLASHTOPUP_API_ID = os.getenv("FLASHTOPUP_API_ID")
FLASHTOPUP_API_KEY = os.getenv("FLASHTOPUP_API_KEY")
FLASHTOPUP_BASE_URL = os.getenv("FLASHTOPUP_BASE_URL")
FLASHTOPUP_SIGNATURE_METHOD = os.getenv("FLASHTOPUP_SIGNATURE_METHOD")

# ==========================================
# SMILE ONE API CONFIG
# ==========================================
SMILE_ONE_API_URL = os.getenv("SMILE_ONE_API_URL")
SMILE_ONE_UID = os.getenv("SMILE_ONE_UID")
SMILE_ONE_API_KEY = os.getenv("SMILE_ONE_API_KEY")

def get_db():
    conn = sqlite3.connect("shop.db")
    conn.row_factory = sqlite3.Row
    return conn

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def create_flashtopup_signature(method, path, body):
    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4())
    body_str = json.dumps(body, separators=(',', ':')) if body else ""
    body_hash = hashlib.sha256(body_str.encode()).hexdigest()
    message = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_hash}\n"
    signature = hmac.new(FLASHTOPUP_API_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()
    return timestamp, nonce, signature

def get_smile_one_code(amount, currency, email=None):
    try:
        url = f"{SMILE_ONE_API_URL}/generate"
        payload = {"amount": amount, "currency": currency}
        if email:
            payload["email"] = email
        headers = {"Authorization": f"Bearer {SMILE_ONE_API_KEY}", "X-UID": SMILE_ONE_UID, "Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        data = response.json()
        if data.get("success"):
            return {"success": True, "code": data.get("code")}
        return {"success": False, "error": data.get("error", "Unknown Error")}
    except Exception as e:
        return {"success": False, "error": str(e)}

def flash_topup_enabled():
    return bool(FLASHTOPUP_API_ID and FLASHTOPUP_API_KEY and FLASHTOPUP_BASE_URL)

def flash_place_order(game, package, game_id, server_id, order_id):
    product_code = ""
    
    if game == "ML":
        if "86 💎" in package: product_code = "ML_DIAMONDS_86"
        elif "172 💎" in package: product_code = "ML_DIAMONDS_172"
        elif "257 💎" in package: product_code = "ML_DIAMONDS_257"
        elif "343 💎" in package: product_code = "ML_DIAMONDS_343"
        elif "429 💎" in package: product_code = "ML_DIAMONDS_429"
        elif "Weekly Pass" in package: product_code = "ML_WEEKLY_PASS"
    
    elif game == "PUBG":
        if "60 UC" in package: product_code = "PUBG_UC_60"
        elif "325 UC" in package: product_code = "PUBG_UC_325"
        elif "660 UC" in package: product_code = "PUBG_UC_660"
        elif "1800 UC" in package: product_code = "PUBG_UC_1800"
        elif "3850 UC" in package: product_code = "PUBG_UC_3850"
    
    elif game == "HOK":
        if "3 Months" in package: product_code = "HOK_3_MONTHS"
        elif "6 Months" in package: product_code = "HOK_6_MONTHS"
        elif "12 Months" in package: product_code = "HOK_12_MONTHS"
    
    if not product_code:
        return {"success": False, "error": f"Package '{package}' အတွက် Product Code မတွေ့ပါ။"}
    
    path = "/api/reseller/v2/order"
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

       def check_flashtopup_order_status(order_id):
    path = "/api/reseller/v2/order/status"
    url = f"{FLASHTOPUP_BASE_URL}{path}"
    payload = {"reference_id": str(order_id)}
    timestamp, nonce, signature = create_flashtopup_signature("POST", path, payload)
    headers = {"Accept": "application/json", "Content-Type": "application/json", "X-FT-API-ID": FLASHTOPUP_API_ID, "X-FT-Timestamp": timestamp, "X-FT-Nonce": nonce, "X-FT-Signature": signature}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

STYLE = """
<style>
    body { font-family: Arial, sans-serif; background: #0f172a; color: #fff; padding-bottom: 80px; }
    .box { max-width: 500px; margin: 0 auto; padding: 15px; }
    .success { background: #22c55e; color: white; padding: 10px; border-radius: 8px; margin-bottom: 10px; }
    .error { background: #ef4444; color: white; padding: 10px; border-radius: 8px; margin-bottom: 10px; }
    .green { background: #14b8a6; color: white; border: none; border-radius: 8px; padding: 10px; }
    .auto-badge { background: #fbbf24; color: #0d1117; padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: bold; margin-left: 6px; text-transform: uppercase; }
</style>
"""

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
        return "Invalid credentials"
    return """
    <h1>Login</h1>
    <form method='POST'>
        <input name='username' placeholder='Username'>
        <input type='password' name='password' placeholder='Password'>
        <button type='submit'>Login</button>
    </form>
    """

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("order"))

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
        body {{ font-family: Arial, sans-serif; background: #000; color: #fff; padding-bottom: 80px; }}
        .grid-2 {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; padding: 15px; max-width: 500px; margin: auto; }}
        .card {{ background: #14b8a6; border-radius: 12px; padding: 15px 10px; text-align: center; text-decoration: none; color: #fff; }}
        .card img {{ width: 100%; height: 100px; object-fit: contain; border-radius: 6px; margin-bottom: 8px; }}
        .card .name {{ font-weight: bold; font-size: 14px; }}
        .bottom-nav {{ position: fixed; bottom: 0; left: 0; right: 0; background: #14b8a6; display: flex; justify-content: space-around; padding: 8px 0 12px 0; z-index: 999; }}
        .bottom-nav a {{ display: flex; flex-direction: column; align-items: center; text-decoration: none; color: #fff; font-size: 11px; }}
        .bottom-nav a .icon {{ font-size: 22px; margin-bottom: 2px; }}
        .bottom-nav a.active {{ color: #0d1117; font-weight: bold; }}
        .auto-badge {{ background: #fbbf24; color: #0d1117; padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: bold; margin-left: 6px; text-transform: uppercase; }}
    </style>
</head>
<body>
    <div class="grid-2">
        <a href="/packages/ML" class="card">
            <img src="/static/ml.png">
            <div class="name">Mobile Legends <span class="auto-badge">Auto</span></div>
        </a>
        <a href="/packages/PUBG" class="card">
            <img src="/static/pubg.png">
            <div class="name">PUBG Mobile <span class="auto-badge">Auto</span></div>
        </a>
        <a href="/packages/HOK" class="card">
            <img src="/static/hok.png">
            <div class="name">Honor Of Kings <span class="auto-badge">Auto</span></div>
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

            <img src="/static/smileone.png">
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
    return f"<h1>Packages for {game}</h1><p><a href='/place_order?game={game}&package=test'>Test Order</a></p>"

@app.route("/wallet")
def wallet():
    if "username" not in session:
        return redirect(url_for("login"))
    return f"<h1>Wallet</h1>"

@app.route("/orders")
def orders():
    if "username" not in session:
        return redirect(url_for("login"))
    return f"<h1>Order History</h1>"

@app.route("/profile")
def profile():
    if "username" not in session:
        return redirect(url_for("login"))
    return f"<h1>Profile</h1>"

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
                        # AUTO TOP UP LOGIC
                        # ==========================================
                        if game in {"ML", "PUBG", "HOK"} and flash_topup_enabled():
                            cursor.execute("INSERT INTO orders (username, game, package, game_id, server_id, telegram_username, acc_mail, payment, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                if conn: conn.close()

    # ... (HTML ပြန်ပေးတဲ့ အပိုင်း ဆက်သွားပါ)
    return ""

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
            background: #0f172a;
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
            <div style="margin-top: 12px;">
                <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Game ID</label>
                <input type="text" name="game_id" placeholder="Enter Game ID" required>
            </div>
            <div style="margin-top: 12px;">
                <label style="color: #94a3b8; font-size: 13px; display: block; margin-bottom: 4px;">Server ID</label>
                <input type="text" name="server_id" placeholder="Enter Server ID">
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

if __name__ == "__main__":
    init_db()
    app.run(debug=True)

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

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
