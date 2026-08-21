# ============================================================
# EREN'S SHOP - FLASK WEBSITE
# PART 1 / 16
# ============================================================

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

import sqlite3
import os
import json
import time
import threading
import uuid
import hashlib
import hmac
import requests


# ============================================================
# APP CONFIG
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "eren-shop-change-this-secret-key"
)

DATABASE = os.environ.get(
    "DATABASE_PATH",
    "eren_shop.db"
)


# ============================================================
# FLASH TOPUP API CONFIG
# ============================================================
#
# API Key ကို GitHub code ထဲ မရေးပါဘူး။
# Railway Variables ထဲမှာ ထည့်ပြီး os.getenv() နဲ့ယူမယ်။
#
# FT_API_ID
# FT_API_KEY
# FT_BASE_URL
#
# Screenshot ထဲက Base URL:
# https://api.flashtopup.com/api/reseller/v2
#
# ============================================================

FT_API_ID = os.environ.get(
    "FT_API_ID",
    ""
).strip()

FT_API_KEY = os.environ.get(
    "FT_API_KEY",
    ""
).strip()

FT_BASE_URL = os.environ.get(
    "FT_BASE_URL",
    "https://api.flashtopup.com/api/reseller/v2"
).rstrip("/")

FT_TIMEOUT = int(
    os.environ.get(
        "FT_TIMEOUT",
        "20"
    )
)


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

    cursor = conn.cursor()


    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            balance REAL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)


    # --------------------------------------------------------
    # ORDERS
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL,

            game TEXT NOT NULL,

            package TEXT NOT NULL,

            amount REAL DEFAULT 0,

            game_id TEXT,

            server_id TEXT,

            provider_order_id TEXT,

            status TEXT DEFAULT 'Pending',

            provider_status TEXT,

            wallet_charged INTEGER DEFAULT 0,

            refunded INTEGER DEFAULT 0,

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL
        )
    """)


    # --------------------------------------------------------
    # DEPOSITS
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL,

            amount REAL NOT NULL,

            payment_method TEXT,

            transaction_id TEXT,

            screenshot TEXT,

            status TEXT DEFAULT 'Pending',

            created_at TEXT NOT NULL
        )
    """)


    # --------------------------------------------------------
    # NOTIFICATIONS
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL,

            title TEXT,

            message TEXT,

            is_read INTEGER DEFAULT 0,

            created_at TEXT NOT NULL
        )
    """)


    # --------------------------------------------------------
    # DATABASE MIGRATION
    # --------------------------------------------------------
    #
    # အရင် database ရှိနေပြီး column တချို့မရှိရင်
    # website crash မဖြစ်အောင် column ထည့်ပေးမယ်။
    #

    def add_column_if_missing(
        table,
        column,
        definition
    ):

        cursor.execute(
            f"PRAGMA table_info({table})"
        )

        existing = {
            row["name"]
            for row in cursor.fetchall()
        }

        if column not in existing:

            cursor.execute(
                f"""
                ALTER TABLE {table}
                ADD COLUMN {column}
                {definition}
                """
            )


    add_column_if_missing(
        "users",
        "balance",
        "REAL DEFAULT 0"
    )

    add_column_if_missing(
        "orders",
        "provider_order_id",
        "TEXT"
    )

    add_column_if_missing(
        "orders",
        "provider_status",
        "TEXT"
    )

    add_column_if_missing(
        "orders",
        "wallet_charged",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        "orders",
        "refunded",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        "orders",
        "updated_at",
        "TEXT"
    )


    conn.commit()

    conn.close()


# ============================================================
# TIME
# ============================================================

def now():

    return time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# ============================================================
# NOTIFICATION
# ============================================================

def create_notification(
    username,
    title,
    message
):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO notifications (
            username,
            title,
            message,
            is_read,
            created_at
        )
        VALUES (?, ?, ?, 0, ?)
        """,
        (
            username,
            title,
            message,
            now()
        )
    )

    conn.commit()

    conn.close()


# ============================================================
# FLASH TOPUP - ENABLE CHECK
# ============================================================

def flash_topup_configured():

    return bool(
        FT_API_ID
        and FT_API_KEY
        and FT_BASE_URL
    )


# ============================================================
# FLASH TOPUP - BODY HASH
# ============================================================

def make_body_hash(
    body
):

    return hashlib.sha256(
        body
    ).hexdigest()


# ============================================================
# FLASH TOPUP - HMAC SIGNATURE
# ============================================================

def make_flash_signature(
    path,
    timestamp,
    nonce,
    body
):

    body_hash = make_body_hash(
        body
    )

    signing_string = (
        path
        + timestamp
        + nonce
        + body_hash
    )

    return hmac.new(
        FT_API_KEY.encode("utf-8"),
        signing_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


# ============================================================
# FLASH TOPUP - REQUEST
# ============================================================

def flash_request(
    method,
    path,
    payload=None
):

    if not flash_topup_configured():

        return {
            "success": False,
            "error": "FlashTopup API is not configured."
        }


    if payload is None:

        payload = {}


    body = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False
    ).encode("utf-8")


    timestamp = str(
        int(time.time())
    )

    nonce = uuid.uuid4().hex


    signature = make_flash_signature(
        path,
        timestamp,
        nonce,
        body
    )


    headers = {

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",

        "X-FT-API-ID":
            FT_API_ID,

        "X-FT-TIMESTAMP":
            timestamp,

        "X-FT-NONCE":
            nonce,

        "X-FT-SIGNATURE":
            signature
    }


    url = (
        FT_BASE_URL
        + path
    )


    try:

        response = requests.request(
            method=method,
            url=url,
            data=body,
            headers=headers,
            timeout=FT_TIMEOUT
        )


        try:

            data = response.json()

        except Exception:

            data = {
                "raw": response.text
            }


        print(
            "[FlashTopup]",
            method,
            path,
            response.status_code,
            data
        )


        return {

            "success":
                200
                <= response.status_code
                < 300,

            "status_code":
                response.status_code,

            "data":
                data
        }


    except Exception as e:

        print(
            "[FlashTopup ERROR]",
            str(e)
        )

        return {

            "success":
                False,

            "status_code":
                0,

            "error":
                str(e)
        }


# ============================================================
# START DATABASE
# ============================================================

init_db()


# ============================================================
# PART 1 END
# =========================================================END

# ============================================================
# EREN'S SHOP - PART 2 / 16
# AUTHENTICATION + DASHBOARD
# ============================================================


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = (
            request.form.get("username")
            or ""
        ).strip()

        password = (
            request.form.get("password")
            or ""
        )


        if not username or not password:

            flash(
                "Username နဲ့ Password ဖြည့်ပေးပါ။",
                "error"
            )

            return redirect(
                url_for("register")
            )


        if len(username) < 3:

            flash(
                "Username အနည်းဆုံး 3 လုံးရှိရပါမယ်။",
                "error"
            )

            return redirect(
                url_for("register")
            )


        if len(password) < 6:

            flash(
                "Password အနည်းဆုံး 6 လုံးရှိရပါမယ်။",
                "error"
            )

            return redirect(
                url_for("register")
            )


        conn = get_db()


        existing = conn.execute(
            """
            SELECT id
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()


        if existing:

            conn.close()

            flash(
                "ဒီ Username ရှိပြီးသားပါ။",
                "error"
            )

            return redirect(
                url_for("register")
            )


        password_hash = generate_password_hash(
            password
        )


        conn.execute(
            """
            INSERT INTO users (
                username,
                password,
                balance,
                created_at
            )
            VALUES (?, ?, 0, ?)
            """,
            (
                username,
                password_hash,
                now()
            )
        )


        conn.commit()

        conn.close()


        flash(
            "Account ဖွင့်ပြီးပါပြီ။ Login ဝင်ပါ။",
            "success"
        )


        return redirect(
            url_for("login")
        )


    return render_template(
        "register.html"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = (
            request.form.get("username")
            or ""
        ).strip()

        password = (
            request.form.get("password")
            or ""
        )


        conn = get_db()


        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()


        conn.close()


        if not user:

            flash(
                "Username သို့မဟုတ် Password မှားနေပါတယ်။",
                "error"
            )

            return redirect(
                url_for("login")
            )


        if not check_password_hash(
            user["password"],
            password
        ):

            flash(
                "Username သို့မဟုတ် Password မှားနေပါတယ်။",
                "error"
            )

            return redirect(
                url_for("login")
            )


        session.clear()

        session["username"] = user["username"]

        session["user_id"] = user["id"]


        return redirect(
            url_for("dashboard")
        )


    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# LOGIN REQUIRED HELPER
# ============================================================

def login_required():

    return (
        "username" in session
        and "user_id" in session
    )


# ============================================================
# CURRENT USER
# ============================================================

def get_current_user():

    if not login_required():

        return None


    conn = get_db()


    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (
            session["user_id"],
        )
    ).fetchone()


    conn.close()


    return user


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def index():

    if login_required():

        return redirect(
            url_for("dashboard")
        )


    return redirect(
        url_for("login")
    )


@app.route("/dashboard")
def dashboard():

    if not login_required():

        return redirect(
            url_for("login")
        )


    user = get_current_user()


    if not user:

        session.clear()

        return redirect(
            url_for("login")
        )


    conn = get_db()


    orders = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (
            user["username"],
        )
    ).fetchall()


    notifications = conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (
            user["username"],
        )
    ).fetchall()


    unread_count = conn.execute(
        """
        SELECT COUNT(*)
        AS total
        FROM notifications
        WHERE username = ?
        AND is_read = 0
        """,
        (
            user["username"],
        )
    ).fetchone()["total"]


    conn.close()


    return render_template(
        "dashboard.html",
        user=user,
        orders=orders,
        notifications=notifications,
        unread_count=unread_count
    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
def profile():

    if not login_required():

        return redirect(
            url_for("login")
        )


    user = get_current_user()


    if not user:

        session.clear()

        return redirect(
            url_for("login")
        )


    return render_template(
        "profile.html",
        user=user
    )


# ============================================================
# WALLET
# ============================================================

@app.route("/wallet")
def wallet():

    if not login_required():

        return redirect(
            url_for("login")
        )


    user = get_current_user()


    if not user:

        session.clear()

        return redirect(
            url_for("login")
        )


    conn = get_db()


    deposits = conn.execute(
        """
        SELECT *
        FROM deposits
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (
            user["username"],
        )
    ).fetchall()


    conn.close()


    return render_template(
        "wallet.html",
        user=user,
        deposits=deposits
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
def notifications():

    if not login_required():

        return redirect(
            url_for("login")
        )


    username = session["username"]


    conn = get_db()


    rows = conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE username = ?
        ORDER BY id DESC
        """,
        (
            username,
        )
    ).fetchall()


    conn.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE username = ?
        """,
        (
            username,
        )
    )


    conn.commit()

    conn.close()


    return render_template(
        "notifications.html",
        notifications=rows
    )


# ============================================================
# NOTIFICATION COUNT API
# ============================================================

@app.route(
    "/api/notifications/count"
)
def notification_count():

    if not login_required():

        return jsonify({
            "success": False,
            "count": 0
        }), 401


    conn = get_db()


    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM notifications
        WHERE username = ?
        AND is_read = 0
        """,
        (
            session["username"],
        )
    ).fetchone()


    conn.close()


    return jsonify({
        "success": True,
        "count": row["total"]
    })


# ============================================================
# PART 2 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 3 / 16
# GAME PACKAGES + ORDER PAGE
# ============================================================


# ============================================================
# PACKAGE DATA
# ============================================================

ML_PACKAGES = [
    {
        "name": "10 💎",
        "price": 1000
    },
    {
        "name": "12 💎",
        "price": 1200
    },
    {
        "name": "20 💎",
        "price": 1900
    },
    {
        "name": "22 💎",
        "price": 2200
    },
    {
        "name": "28 💎",
        "price": 2800
    },
    {
        "name": "36 💎",
        "price": 3500
    },
    {
        "name": "44 💎",
        "price": 4200
    },
    {
        "name": "56 💎",
        "price": 5000
    },
    {
        "name": "86 💎",
        "price": 4500
    },
    {
        "name": "172 💎",
        "price": 9000
    },
    {
        "name": "257 💎",
        "price": 19000
    },
    {
        "name": "706 💎",
        "price": 40000
    },
    {
        "name": "2195 💎",
        "price": 107000
    },
    {
        "name": "3688 💎",
        "price": 180000
    },
    {
        "name": "5532 💎",
        "price": 270000
    },
    {
        "name": "9288 💎",
        "price": 450000
    },
    {
        "name": "Weekly Pass",
        "price": 6000
    },
    {
        "name": "Twilight Pass",
        "price": 35000
    }
]


PUBG_PACKAGES = [
    {
        "name": "60 UC",
        "price": 3000
    },
    {
        "name": "325 UC",
        "price": 14000
    },
    {
        "name": "660 UC",
        "price": 27000
    },
    {
        "name": "1800 UC",
        "price": 70000
    },
    {
        "name": "3850 UC",
        "price": 135000
    },
    {
        "name": "8100 UC",
        "price": 270000
    }
]


# ============================================================
# GAME SELECT
# ============================================================

@app.route("/games")
def games():

    if not login_required():

        return redirect(
            url_for("login")
        )


    return render_template(
        "games.html"
    )


# ============================================================
# PACKAGES
# ============================================================

@app.route(
    "/packages/<game>"
)
def packages(game):

    if not login_required():

        return redirect(
            url_for("login")
        )


    game = (
        game
        or ""
    ).upper()


    if game == "ML":

        package_list = ML_PACKAGES

        game_name = "Mobile Legends"


    elif game == "PUBG":

        package_list = PUBG_PACKAGES

        game_name = "PUBG Mobile"


    else:

        flash(
            "Game မတွေ့ပါ။",
            "error"
        )

        return redirect(
            url_for("games")
        )


    return render_template(
        "packages.html",
        game=game,
        game_name=game_name,
        packages=package_list
    )


# ============================================================
# GET PACKAGE
# ============================================================

def get_package(
    game,
    package_name
):

    game = (
        game
        or ""
    ).upper()


    package_name = (
        package_name
        or ""
    ).strip()


    if game == "ML":

        package_list = ML_PACKAGES

    elif game == "PUBG":

        package_list = PUBG_PACKAGES

    else:

        return None


    for package in package_list:

        if package["name"] == package_name:

            return package


    return None


# ============================================================
# ORDER PAGE
# ============================================================

@app.route(
    "/order/<game>",
    methods=["GET"]
)
def order_page(game):

    if not login_required():

        return redirect(
            url_for("login")
        )


    game = (
        game
        or ""
    ).upper()


    if game not in {
        "ML",
        "PUBG"
    }:

        flash(
            "Game မမှန်ပါ။",
            "error"
        )

        return redirect(
            url_for("games")
        )


    package_name = (
        request.args.get(
            "package"
        )
        or ""
    ).strip()


    package = get_package(
        game,
        package_name
    )


    if not package:

        flash(
            "Package မတွေ့ပါ။",
            "error"
        )

        return redirect(
            url_for(
                "packages",
                game=game
            )
        )


    user = get_current_user()


    return render_template(
        "order.html",
        game=game,
        package=package,
        user=user
    )


# ============================================================
# PLACE ORDER - BASIC VALIDATION
# ============================================================

@app.route(
    "/place_order",
    methods=["POST"]
)
def place_order():

    if not login_required():

        return jsonify({
            "success": False,
            "message":
                "Login ဝင်ထားဖို့လိုပါတယ်။"
        }), 401


    username = session["username"]


    game = (
        request.form.get("game")
        or ""
    ).upper().strip()


    package_name = (
        request.form.get("package")
        or ""
    ).strip()


    game_id = (
        request.form.get("game_id")
        or ""
    ).strip()


    server_id = (
        request.form.get("server_id")
        or ""
    ).strip()


    package = get_package(
        game,
        package_name
    )


    if not package:

        return jsonify({
            "success": False,
            "message":
                "Package မတွေ့ပါ။"
        }), 400


    if not game_id:

        return jsonify({
            "success": False,
            "message":
                "Game ID ဖြည့်ပေးပါ။"
        }), 400


    if game == "ML" and not server_id:

        return jsonify({
            "success": False,
            "message":
                "Server ID ဖြည့်ပေးပါ။"
        }), 400


    amount = float(
        package["price"]
    )


    conn = get_db()


    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (
            username,
        )
    ).fetchone()


    if not user:

        conn.close()

        return jsonify({
            "success": False,
            "message":
                "User မတွေ့ပါ။"
        }), 404


    balance = float(
        user["balance"] or 0
    )


    if balance < amount:

        conn.close()

        return jsonify({
            "success": False,
            "message":
                "Wallet ထဲမှာ ငွေမလောက်ပါ။"
        }), 400


    # --------------------------------------------------------
    # CREATE LOCAL ORDER
    # --------------------------------------------------------

    created = now()


    cursor = conn.execute(
        """
        INSERT INTO orders (
            username,
            game,
            package,
            amount,
            game_id,
            server_id,
            status,
            provider_status,
            wallet_charged,
            refunded,
            created_at,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?,
            'Pending',
            'Pending',
            0,
            0,
            ?,
            ?
        )
        """,
        (
            username,
            game,
            package_name,
            amount,
            game_id,
            server_id,
            created,
            created
        )
    )


    local_order_id = cursor.lastrowid


    conn.commit()

    conn.close()


    # --------------------------------------------------------
    # API RECHARGE
    # --------------------------------------------------------
    #
    # Part 4 မှာ ဒီ function ကို complete လုပ်မယ်။
    #
    # အခု order ကို Pending အနေနဲ့ထားတယ်။
    #

    return jsonify({

        "success": True,

        "message":
            "Order လက်ခံပြီးပါပြီ။",

        "order_id":
            local_order_id,

        "status":
            "Pending"
    })


# ============================================================
# ORDER HISTORY
# ============================================================

@app.route("/orders")
def orders():

    if not login_required():

        return redirect(
            url_for("login")
        )


    username = session["username"]


    conn = get_db()


    order_list = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE username = ?
        ORDER BY id DESC
        """,
        (
            username,
        )
    ).fetchall()


    conn.close()


    return render_template(
        "orders.html",
        orders=order_list
    )


# ============================================================
# ORDER DETAILS
# ============================================================

@app.route(
    "/order/<int:order_id>"
)
def order_details(
    order_id
):

    if not login_required():

        return redirect(
            url_for("login")
        )


    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        AND username = ?
        """,
        (
            order_id,
            session["username"]
        )
    ).fetchone()


    conn.close()


    if not order:

        flash(
            "Order မတွေ့ပါ။",
            "error"
        )

        return redirect(
            url_for("orders")
        )


    return render_template(
        "order_details.html",
        order=order
    )


# ============================================================
# PART 3 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 4 / 16
# FLASH TOPUP AUTO RECHARGE
# ============================================================


# ============================================================
# FLASH TOPUP SERVICE CODE
# ============================================================

def get_service_code(
    game,
    package_name
):

    game = (
        game
        or ""
    ).upper().strip()

    package_name = (
        package_name
        or ""
    ).strip()


    # --------------------------------------------------------
    # CUSTOM SERVICE MAP
    # --------------------------------------------------------
    #
    # Railway Variables ထဲမှာ
    # FT_SERVICE_MAP_JSON
    # ထည့်ထားရင် အဲဒါကို အရင်သုံးမယ်။
    #
    # Example:
    #
    # {
    #   "ML|86 💎": "YOUR_SERVICE_CODE",
    #   "PUBG|60 UC": "YOUR_SERVICE_CODE"
    # }
    #
    # --------------------------------------------------------

    raw_map = os.environ.get(
        "FT_SERVICE_MAP_JSON",
        ""
    ).strip()


    if raw_map:

        try:

            service_map = json.loads(
                raw_map
            )


            custom_code = service_map.get(
                f"{game}|{package_name}"
            )


            if custom_code:

                return str(
                    custom_code
                )


        except Exception:

            print(
                "[FlashTopup] "
                "Invalid FT_SERVICE_MAP_JSON"
            )


    # --------------------------------------------------------
    # DEFAULT ML SERVICE CODE
    # --------------------------------------------------------

    if game == "ML":

        if "💎" in package_name:

            amount = (
                package_name
                .replace("💎", "")
                .strip()
            )


            if amount.isdigit():

                return (
                    "TOPUP_MOBILE_LEGENDS_"
                    f"{amount}_DIAMONDS"
                )


        if (
            "Weekly" in package_name
            or "weekly" in package_name
        ):

            return (
                "TOPUP_MOBILE_LEGENDS_"
                "WEEKLY_PASS"
            )


        if (
            "Twilight" in package_name
            or "twilight" in package_name
        ):

            return (
                "TOPUP_MOBILE_LEGENDS_"
                "TWILIGHT_PASS"
            )


    # --------------------------------------------------------
    # DEFAULT PUBG SERVICE CODE
    # --------------------------------------------------------

    if game == "PUBG":

        amount = (
            package_name
            .replace("UC", "")
            .strip()
        )


        if amount.isdigit():

            return (
                "TOPUP_PUBG_MOBILE_"
                f"{amount}_UC"
            )


    return None


# ============================================================
# FLASH TOPUP CREATE ORDER
# ============================================================

def create_flash_order(
    local_order_id,
    game,
    package_name,
    game_id,
    server_id
):

    if not flash_topup_configured():

        return {

            "success":
                False,

            "message":
                "FlashTopup API "
                "မသတ်မှတ်ရသေးပါ။"
        }


    service_code = get_service_code(
        game,
        package_name
    )


    if not service_code:

        return {

            "success":
                False,

            "message":
                (
                    "ဒီ Package အတွက် "
                    "FlashTopup service code "
                    "မတွေ့ပါ။"
                )
        }


    # --------------------------------------------------------
    # REFERENCE ID
    # --------------------------------------------------------

    reference_id = (
        "EREN-"
        f"{local_order_id}-"
        f"{uuid.uuid4().hex[:8]}"
    )


    # --------------------------------------------------------
    # REQUEST BODY
    # --------------------------------------------------------

    payload = {

        "service_code":
            service_code,

        "reference_id":
            reference_id,

        "quantity":
            1,

        "user_id":
            str(game_id)
    }


    # --------------------------------------------------------
    # ML SERVER ID
    # --------------------------------------------------------

    if game == "ML":

        payload["server_id"] = str(
            server_id
        )


    # --------------------------------------------------------
    # SEND TO FLASHTOPUP
    # --------------------------------------------------------

    result = flash_request(
        "POST",
        "/order",
        payload
    )


    if not result.get(
        "success"
    ):

        return {

            "success":
                False,

            "message":
                (
                    "FlashTopup API "
                    "request failed."
                ),

            "response":
                result
        }


    data = result.get(
        "data"
    )


    if not isinstance(
        data,
        dict
    ):

        return {

            "success":
                False,

            "message":
                "API response မမှန်ပါ။",

            "response":
                result
        }


    # --------------------------------------------------------
    # FIND RESPONSE DATA
    # --------------------------------------------------------

    response_data = data


    if isinstance(
        data.get("data"),
        dict
    ):

        response_data = data["data"]


    provider_order_id = (

        response_data.get(
            "order_id"
        )

        or response_data.get(
            "orderId"
        )

        or response_data.get(
            "id"
        )

        or data.get(
            "order_id"
        )

        or data.get(
            "orderId"
        )

        or data.get(
            "id"
        )
    )


    provider_status = (

        response_data.get(
            "status"
        )

        or response_data.get(
            "order_status"
        )

        or data.get(
            "status"
        )

        or data.get(
            "order_status"
        )

        or "Processing"
    )


    # --------------------------------------------------------
    # NO PROVIDER ORDER ID
    # --------------------------------------------------------

    if not provider_order_id:

        error_message = (

            data.get(
                "message"
            )

            or data.get(
                "error"
            )

            or "Provider Order ID မရပါ။"
        )


        return {

            "success":
                False,

            "message":
                str(
                    error_message
                ),

            "response":
                data
        }


    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    return {

        "success":
            True,

        "provider_order_id":
            str(
                provider_order_id
            ),

        "provider_status":
            str(
                provider_status
            ),

        "reference_id":
            reference_id,

        "service_code":
            service_code,

        "response":
            data
    }


# ============================================================
# SEND ORDER TO PROVIDER
# ============================================================

def send_order_to_provider(
    local_order_id
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            local_order_id,
        )
    ).fetchone()


    if not order:

        conn.close()

        return {

            "success":
                False,

            "message":
                "Order မတွေ့ပါ။"
        }


    # --------------------------------------------------------
    # ALREADY SENT
    # --------------------------------------------------------

    if order["provider_order_id"]:

        conn.close()

        return {

            "success":
                True,

            "already_sent":
                True,

            "provider_order_id":
                order[
                    "provider_order_id"
                ]
        }


    # --------------------------------------------------------
    # CREATE PROVIDER ORDER
    # --------------------------------------------------------

    result = create_flash_order(

        local_order_id,

        order["game"],

        order["package"],

        order["game_id"],

        order["server_id"]
    )


    # --------------------------------------------------------
    # PROVIDER FAILED
    # --------------------------------------------------------

    if not result.get(
        "success"
    ):

        conn.execute(
            """
            UPDATE orders
            SET
                status = 'Failed',
                provider_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                result.get(
                    "message",
                    "API Failed"
                ),

                now(),

                local_order_id
            )
        )


        conn.commit()

        conn.close()


        create_notification(

            order["username"],

            "❌ Order Failed",

            (
                f"{order['package']} "
                f"Order #{local_order_id} "
                "ကို Auto Recharge မလုပ်နိုင်ပါ။ "
                "Wallet ငွေမဖြတ်ထားပါ။"
            )
        )


        return result


    # --------------------------------------------------------
    # SAVE PROVIDER ORDER
    # --------------------------------------------------------

    provider_order_id = result[
        "provider_order_id"
    ]


    provider_status = result.get(
        "provider_status",
        "Processing"
    )


    conn.execute(
        """
        UPDATE orders
        SET
            provider_order_id = ?,
            provider_status = ?,
            status = 'Processing',
            updated_at = ?
        WHERE id = ?
        """,
        (
            provider_order_id,

            provider_status,

            now(),

            local_order_id
        )
    )


    conn.commit()

    conn.close()


    create_notification(

        order["username"],

        "🔄 Auto Recharge",

        (
            f"{order['package']} "
            f"Order #{local_order_id} ကို "
            "Auto Recharge လုပ်နေပါပြီ။"
        )
    )


    return {

        "success":
            True,

        "provider_order_id":
            provider_order_id,

        "provider_status":
            provider_status
    }


# ============================================================
# AUTO SEND AFTER LOCAL ORDER
# ============================================================

def auto_send_order(
    local_order_id
):

    try:

        result = send_order_to_provider(
            local_order_id
        )


        print(
            "[AUTO RECHARGE]",
            local_order_id,
            result
        )


    except Exception as e:

        print(
            "[AUTO RECHARGE ERROR]",
            local_order_id,
            str(e)
        )


# ============================================================
# PART 4 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 5 / 16
# WALLET CHARGE + AUTO RECHARGE ORDER FLOW
# ============================================================


# ============================================================
# CHARGE WALLET
# ============================================================

def charge_wallet(
    username,
    amount
):

    conn = get_db()


    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (
            username,
        )
    ).fetchone()


    if not user:

        conn.close()

        return {
            "success": False,
            "message": "User မတွေ့ပါ။"
        }


    balance = float(
        user["balance"] or 0
    )


    amount = float(amount)


    if amount <= 0:

        conn.close()

        return {
            "success": False,
            "message": "Amount မမှန်ပါ။"
        }


    if balance < amount:

        conn.close()

        return {
            "success": False,
            "message":
                "Wallet balance မလောက်ပါ။"
        }


    new_balance = (
        balance - amount
    )


    conn.execute(
        """
        UPDATE users
        SET balance = ?
        WHERE username = ?
        """,
        (
            new_balance,
            username
        )
    )


    conn.commit()

    conn.close()


    return {
        "success": True,
        "balance": new_balance
    }


# ============================================================
# REFUND WALLET
# ============================================================

def refund_wallet(
    username,
    amount
):

    conn = get_db()


    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (
            username,
        )
    ).fetchone()


    if not user:

        conn.close()

        return {
            "success": False,
            "message": "User မတွေ့ပါ။"
        }


    balance = float(
        user["balance"] or 0
    )


    amount = float(amount)


    if amount <= 0:

        conn.close()

        return {
            "success": False,
            "message": "Refund amount မမှန်ပါ။"
        }


    new_balance = (
        balance + amount
    )


    conn.execute(
        """
        UPDATE users
        SET balance = ?
        WHERE username = ?
        """,
        (
            new_balance,
            username
        )
    )


    conn.commit()

    conn.close()


    return {
        "success": True,
        "balance": new_balance
    }


# ============================================================
# MARK ORDER AS CHARGED
# ============================================================

def mark_order_charged(
    order_id
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    if not order:

        conn.close()

        return False


    if int(
        order["wallet_charged"] or 0
    ) == 1:

        conn.close()

        return True


    conn.execute(
        """
        UPDATE orders
        SET
            wallet_charged = 1,
            updated_at = ?
        WHERE id = ?
        """,
        (
            now(),
            order_id
        )
    )


    conn.commit()

    conn.close()

    return True


# ============================================================
# MARK ORDER REFUNDED
# ============================================================

def mark_order_refunded(
    order_id
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    if not order:

        conn.close()

        return False


    if int(
        order["refunded"] or 0
    ) == 1:

        conn.close()

        return True


    conn.execute(
        """
        UPDATE orders
        SET
            refunded = 1,
            updated_at = ?
        WHERE id = ?
        """,
        (
            now(),
            order_id
        )
    )


    conn.commit()

    conn.close()

    return True


# ============================================================
# COMPLETE ORDER PAYMENT FLOW
# ============================================================

def process_order_payment(
    order_id
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    conn.close()


    if not order:

        return {
            "success": False,
            "message":
                "Order မတွေ့ပါ။"
        }


    # --------------------------------------------------------
    # ALREADY CHARGED
    # --------------------------------------------------------

    if int(
        order["wallet_charged"] or 0
    ) == 1:

        return {
            "success": True,
            "already_charged": True
        }


    # --------------------------------------------------------
    # SEND ORDER TO PROVIDER FIRST
    # --------------------------------------------------------
    #
    # Provider API က order လက်ခံပြီးမှ
    # customer wallet ကို charge လုပ်မယ်။
    #
    # ဒါကြောင့် API မအောင်မြင်ရင်
    # customer ပိုက်ဆံ မဖြတ်ပါဘူး။
    #

    provider_result = (
        send_order_to_provider(
            order_id
        )
    )


    if not provider_result.get(
        "success"
    ):

        return {
            "success": False,

            "message":
                provider_result.get(
                    "message",
                    "Auto Recharge မအောင်မြင်ပါ။"
                )
        }


    # --------------------------------------------------------
    # CHARGE WALLET
    # --------------------------------------------------------

    charge_result = charge_wallet(
        order["username"],
        float(order["amount"])
    )


    if not charge_result.get(
        "success"
    ):

        # ----------------------------------------------------
        # CUSTOMER BALANCE မလောက်ရင်
        # PROVIDER ORDER ကို cancel လုပ်နိုင်မလား
        # provider API အပေါ်မူတည်ပါတယ်။
        #
        # ဒီနေရာမှာ local order ကို Failed ထားမယ်။
        # ----------------------------------------------------

        conn = get_db()


        conn.execute(
            """
            UPDATE orders
            SET
                status = 'Failed',
                provider_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                "Wallet balance insufficient",

                now(),

                order_id
            )
        )


        conn.commit()

        conn.close()


        create_notification(

            order["username"],

            "❌ Order Failed",

            (
                f"Order #{order_id} အတွက် "
                "Wallet balance မလောက်ပါ။"
            )
        )


        return {

            "success":
                False,

            "message":
                "Wallet balance မလောက်ပါ။"
        }


    # --------------------------------------------------------
    # MARK WALLET CHARGED
    # --------------------------------------------------------

    mark_order_charged(
        order_id
    )


    # --------------------------------------------------------
    # UPDATE ORDER
    # --------------------------------------------------------

    conn = get_db()


    conn.execute(
        """
        UPDATE orders
        SET
            status = 'Processing',
            updated_at = ?
        WHERE id = ?
        """,
        (
            now(),
            order_id
        )
    )


    conn.commit()

    conn.close()


    create_notification(

        order["username"],

        "💎 Order Processing",

        (
            f"သင်တင်ထားသော "
            f"{order['package']} Order "
            f"#{order_id} ကို "
            "လက်ခံပြီး Auto Recharge "
            "လုပ်နေပါပြီ။"
        )
    )


    return {

        "success":
            True,

        "message":
            "Order Processing",

        "provider_order_id":
            provider_result.get(
                "provider_order_id"
            ),

        "balance":
            charge_result.get(
                "balance"
            )
    }


# ============================================================
# REPLACE / FINALIZE PLACE ORDER
# ============================================================

@app.route(
    "/api/place-order",
    methods=["POST"]
)
def api_place_order():

    if not login_required():

        return jsonify({

            "success":
                False,

            "message":
                "Login ဝင်ထားဖို့လိုပါတယ်။"

        }), 401


    username = session[
        "username"
    ]


    data = request.get_json(
        silent=True
    )


    if not data:

        data = request.form


    game = (
        data.get("game")
        or ""
    ).upper().strip()


    package_name = (
        data.get("package")
        or ""
    ).strip()


    game_id = (
        data.get("game_id")
        or ""
    ).strip()


    server_id = (
        data.get("server_id")
        or ""
    ).strip()


    package = get_package(
        game,
        package_name
    )


    if not package:

        return jsonify({

            "success":
                False,

            "message":
                "Package မတွေ့ပါ။"

        }), 400


    if not game_id:

        return jsonify({

            "success":
                False,

            "message":
                "Game ID ဖြည့်ပေးပါ။"

        }), 400


    if (
        game == "ML"
        and not server_id
    ):

        return jsonify({

            "success":
                False,

            "message":
                "Server ID ဖြည့်ပေးပါ။"

        }), 400


    amount = float(
        package["price"]
    )


    conn = get_db()


    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (
            username,
        )
    ).fetchone()


    if not user:

        conn.close()

        return jsonify({

            "success":
                False,

            "message":
                "User မတွေ့ပါ။"

        }), 404


    balance = float(
        user["balance"] or 0
    )


    if balance < amount:

        conn.close()

        return jsonify({

            "success":
                False,

            "message":
                "Wallet ထဲမှာ ငွေမလောက်ပါ။",

            "balance":
                balance,

            "required":
                amount

        }), 400


    created_at = now()


    cursor = conn.execute(
        """
        INSERT INTO orders (
            username,
            game,
            package,
            amount,
            game_id,
            server_id,
            status,
            provider_status,
            wallet_charged,
            refunded,
            created_at,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?,
            'Pending',
            'Pending',
            0,
            0,
            ?,
            ?
        )
        """,
        (
            username,
            game,
            package_name,
            amount,
            game_id,
            server_id,
            created_at,
            created_at
        )
    )


    order_id = cursor.lastrowid


    conn.commit()

    conn.close()


    # --------------------------------------------------------
    # PROCESS PAYMENT + API
    # --------------------------------------------------------

    result = process_order_payment(
        order_id
    )


    if not result.get(
        "success"
    ):

        return jsonify({

            "success":
                False,

            "order_id":
                order_id,

            "message":
                result.get(
                    "message",
                    "Order မအောင်မြင်ပါ။"
                )

        }), 400


    return jsonify({

        "success":
            True,

        "order_id":
            order_id,

        "provider_order_id":
            result.get(
                "provider_order_id"
            ),

        "status":
            "Processing",

        "balance":
            result.get(
                "balance"
            ),

        "message":
            (
                "Order တင်ပြီးပါပြီ။ "
                "Auto Recharge လုပ်နေပါပြီ။"
            )

    })


# ============================================================
# WALLET BALANCE API
# ============================================================

@app.route(
    "/api/wallet"
)
def api_wallet():

    if not login_required():

        return jsonify({

            "success":
                False,

            "message":
                "Unauthorized"

        }), 401


    user = get_current_user()


    if not user:

        return jsonify({

            "success":
                False,

            "message":
                "User မတွေ့ပါ။"

        }), 404


    return jsonify({

        "success":
            True,

        "username":
            user["username"],

        "balance":
            float(
                user["balance"] or 0
            )

    })


# ============================================================
# PART 5 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 6 / 16
# DEPOSIT SYSTEM
# ============================================================


# ============================================================
# DEPOSIT PAGE
# ============================================================

@app.route("/deposit")
def deposit():

    if not login_required():
        return redirect(url_for("login"))

    user = get_current_user()

    if not user:
        session.clear()
        return redirect(url_for("login"))

    conn = get_db()

    deposits = conn.execute(
        """
        SELECT *
        FROM deposits
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 30
        """,
        (user["username"],)
    ).fetchall()

    conn.close()

    return render_template(
        "deposit.html",
        user=user,
        deposits=deposits
    )


# ============================================================
# CREATE DEPOSIT
# ============================================================

@app.route(
    "/deposit",
    methods=["POST"]
)
def create_deposit():

    if not login_required():

        return redirect(
            url_for("login")
        )


    username = session["username"]


    amount_raw = (
        request.form.get("amount")
        or ""
    ).strip()


    payment_method = (
        request.form.get(
            "payment_method"
        )
        or ""
    ).strip()


    transaction_id = (
        request.form.get(
            "transaction_id"
        )
        or ""
    ).strip()


    try:

        amount = float(
            amount_raw
        )

    except ValueError:

        flash(
            "Deposit amount မမှန်ပါ။",
            "error"
        )

        return redirect(
            url_for("deposit")
        )


    if amount <= 0:

        flash(
            "Deposit amount မှန်ကန်စွာ ဖြည့်ပါ။",
            "error"
        )

        return redirect(
            url_for("deposit")
        )


    if not payment_method:

        flash(
            "Payment method ရွေးပေးပါ။",
            "error"
        )

        return redirect(
            url_for("deposit")
        )


    if not transaction_id:

        flash(
            "Transaction ID ဖြည့်ပေးပါ။",
            "error"
        )

        return redirect(
            url_for("deposit")
        )


    # --------------------------------------------------------
    # SCREENSHOT
    # --------------------------------------------------------

    screenshot_file = request.files.get(
        "screenshot"
    )


    screenshot_name = ""


    if screenshot_file:

        screenshot_name = (
            screenshot_file.filename
            or ""
        ).strip()


    # --------------------------------------------------------
    # SAVE DEPOSIT
    # --------------------------------------------------------

    conn = get_db()


    cursor = conn.execute(
        """
        INSERT INTO deposits (
            username,
            amount,
            payment_method,
            transaction_id,
            screenshot,
            status,
            created_at
        )
        VALUES (
            ?, ?, ?, ?, ?,
            'Pending',
            ?
        )
        """,
        (
            username,
            amount,
            payment_method,
            transaction_id,
            screenshot_name,
            now()
        )
    )


    deposit_id = cursor.lastrowid


    conn.commit()

    conn.close()


    # --------------------------------------------------------
    # CUSTOMER NOTIFICATION
    # --------------------------------------------------------

    create_notification(

        username,

        "💰 Deposit Submitted",

        (
            f"သင်ဖြည့်ထားသော Deposit "
            f"{amount:,.0f} Ks ကို "
            f"လက်ခံရရှိပါပြီ။ "
            f"Admin စစ်ဆေးပြီး Wallet ထဲ "
            f"ထည့်ပေးပါမယ်။"
        )
    )


    flash(
        (
            f"Deposit #{deposit_id} "
            "တင်ပြီးပါပြီ။"
        ),
        "success"
    )


    return redirect(
        url_for("deposit")
    )


# ============================================================
# DEPOSIT DETAILS
# ============================================================

@app.route(
    "/deposit/<int:deposit_id>"
)
def deposit_details(
    deposit_id
):

    if not login_required():

        return redirect(
            url_for("login")
        )


    conn = get_db()


    deposit_row = conn.execute(
        """
        SELECT *
        FROM deposits
        WHERE id = ?
        AND username = ?
        """,
        (
            deposit_id,
            session["username"]
        )
    ).fetchone()


    conn.close()


    if not deposit_row:

        flash(
            "Deposit မတွေ့ပါ။",
            "error"
        )

        return redirect(
            url_for("deposit")
        )


    return render_template(
        "deposit_details.html",
        deposit=deposit_row
    )


# ============================================================
# APPROVE DEPOSIT
# ============================================================
#
# Admin system ကို Part 11 မှာ ထည့်မယ်။
#
# ဒီ function ကို admin ကပဲ သုံးနိုင်အောင်
# အောက်ပိုင်းမှာ protection ထည့်မယ်။
#
# ============================================================

def approve_deposit(
    deposit_id
):

    conn = get_db()


    deposit_row = conn.execute(
        """
        SELECT *
        FROM deposits
        WHERE id = ?
        """,
        (
            deposit_id,
        )
    ).fetchone()


    if not deposit_row:

        conn.close()

        return {
            "success":
                False,

            "message":
                "Deposit မတွေ့ပါ။"
        }


    # --------------------------------------------------------
    # ALREADY APPROVED
    # --------------------------------------------------------

    if (
        deposit_row["status"]
        == "Approved"
    ):

        conn.close()

        return {
            "success":
                False,

            "message":
                "ဒီ Deposit ကို အရင် approve လုပ်ပြီးပါပြီ။"
        }


    # --------------------------------------------------------
    # ONLY PENDING
    # --------------------------------------------------------

    if (
        deposit_row["status"]
        != "Pending"
    ):

        conn.close()

        return {
            "success":
                False,

            "message":
                (
                    "ဒီ Deposit ရဲ့ status က "
                    f"{deposit_row['status']} ဖြစ်နေပါတယ်။"
                )
        }


    username = deposit_row[
        "username"
    ]


    amount = float(
        deposit_row["amount"]
        or 0
    )


    # --------------------------------------------------------
    # UPDATE WALLET
    # --------------------------------------------------------

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (
            username,
        )
    ).fetchone()


    if not user:

        conn.close()

        return {
            "success":
                False,

            "message":
                "User မတွေ့ပါ။"
        }


    old_balance = float(
        user["balance"] or 0
    )


    new_balance = (
        old_balance
        + amount
    )


    conn.execute(
        """
        UPDATE users
        SET balance = ?
        WHERE username = ?
        """,
        (
            new_balance,
            username
        )
    )


    # --------------------------------------------------------
    # APPROVE DEPOSIT
    # --------------------------------------------------------

    conn.execute(
        """
        UPDATE deposits
        SET status = 'Approved'
        WHERE id = ?
        """,
        (
            deposit_id,
        )
    )


    conn.commit()

    conn.close()


    # --------------------------------------------------------
    # NOTIFICATION
    # --------------------------------------------------------

    create_notification(

        username,

        "💰 Deposit Approved",

        (
            f"သင်ဖြည့်ထားသော Deposit "
            f"{amount:,.0f} Ks ကို "
            "Wallet ထဲ ထည့်ပြီးပါပြီ။ "
            f"လက်ကျန်ငွေ {new_balance:,.0f} Ks ဖြစ်ပါတယ်။"
        )
    )


    return {

        "success":
            True,

        "deposit_id":
            deposit_id,

        "amount":
            amount,

        "balance":
            new_balance
    }


# ============================================================
# REJECT DEPOSIT
# ============================================================

def reject_deposit(
    deposit_id,
    reason=""
):

    conn = get_db()


    deposit_row = conn.execute(
        """
        SELECT *
        FROM deposits
        WHERE id = ?
        """,
        (
            deposit_id,
        )
    ).fetchone()


    if not deposit_row:

        conn.close()

        return {
            "success":
                False,

            "message":
                "Deposit မတွေ့ပါ။"
        }


    if (
        deposit_row["status"]
        != "Pending"
    ):

        conn.close()

        return {
            "success":
                False,

            "message":
                (
                    "Deposit status က "
                    f"{deposit_row['status']} ဖြစ်နေပါတယ်။"
                )
        }


    conn.execute(
        """
        UPDATE deposits
        SET status = 'Rejected'
        WHERE id = ?
        """,
        (
            deposit_id,
        )
    )


    conn.commit()

    conn.close()


    username = deposit_row[
        "username"
    ]


    amount = float(
        deposit_row["amount"]
        or 0
    )


    message = (
        f"သင်ဖြည့်ထားသော Deposit "
        f"{amount:,.0f} Ks ကို "
        "Reject လုပ်လိုက်ပါတယ်။"
    )


    if reason:

        message += (
            f"\nအကြောင်းပြချက်: {reason}"
        )


    create_notification(

        username,

        "❌ Deposit Rejected",

        message
    )


    return {

        "success":
            True,

        "deposit_id":
            deposit_id
    }


# ============================================================
# DEPOSIT API STATUS
# ============================================================

@app.route(
    "/api/deposit/<int:deposit_id>"
)
def deposit_status_api(
    deposit_id
):

    if not login_required():

        return jsonify({

            "success":
                False,

            "message":
                "Unauthorized"

        }), 401


    conn = get_db()


    row = conn.execute(
        """
        SELECT
            id,
            amount,
            payment_method,
            transaction_id,
            status,
            created_at
        FROM deposits
        WHERE id = ?
        AND username = ?
        """,
        (
            deposit_id,
            session["username"]
        )
    ).fetchone()


    conn.close()


    if not row:

        return jsonify({

            "success":
                False,

            "message":
                "Deposit မတွေ့ပါ။"

        }), 404


    return jsonify({

        "success":
            True,

        "deposit": {

            "id":
                row["id"],

            "amount":
                float(
                    row["amount"]
                ),

            "payment_method":
                row["payment_method"],

            "transaction_id":
                row["transaction_id"],

            "status":
                row["status"],

            "created_at":
                row["created_at"]
        }

    })


# ============================================================
# PART 6 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 7 / 16
# AUTO ORDER STATUS + REFUND
# ============================================================


# ============================================================
# GET PROVIDER ORDER STATUS
# ============================================================

def get_provider_order_status(
    provider_order_id
):

    if not provider_order_id:

        return {
            "success": False,
            "status": "Unknown",
            "message": "Provider Order ID မရှိပါ။"
        }


    result = flash_request(
        "GET",
        f"/order/{provider_order_id}",
        {}
    )


    if not result.get("success"):

        return {
            "success": False,
            "status": "Unknown",
            "message":
                "Provider status စစ်လို့မရပါ။",
            "response": result
        }


    data = result.get(
        "data"
    ) or {}


    if not isinstance(
        data,
        dict
    ):

        return {
            "success": False,
            "status": "Unknown",
            "message":
                "Provider response မမှန်ပါ။"
        }


    response_data = data


    if isinstance(
        data.get("data"),
        dict
    ):

        response_data = data["data"]


    provider_status = (

        response_data.get(
            "status"
        )

        or response_data.get(
            "order_status"
        )

        or response_data.get(
            "orderStatus"
        )

        or data.get(
            "status"
        )

        or data.get(
            "order_status"
        )

        or "Unknown"
    )


    return {
        "success": True,
        "status":
            str(provider_status),
        "response": data
    }


# ============================================================
# NORMALIZE ORDER STATUS
# ============================================================

def normalize_order_status(
    status
):

    value = str(
        status or ""
    ).strip().lower()


    if value in {
        "completed",
        "complete",
        "success",
        "successful",
        "delivered",
        "delivery_success",
        "done"
    }:

        return "Completed"


    if value in {
        "failed",
        "failure",
        "cancelled",
        "canceled",
        "rejected",
        "error",
        "refunded"
    }:

        return "Failed"


    if value in {
        "processing",
        "pending",
        "in_progress",
        "in-progress",
        "queued",
        "waiting"
    }:

        return "Processing"


    return "Processing"


# ============================================================
# REFUND FAILED ORDER
# ============================================================

def refund_failed_order(
    order_id
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    conn.close()


    if not order:

        return {
            "success": False,
            "message": "Order မတွေ့ပါ။"
        }


    # --------------------------------------------------------
    # WALLET WAS NEVER CHARGED
    # --------------------------------------------------------

    if int(
        order["wallet_charged"] or 0
    ) != 1:

        return {
            "success": True,
            "refunded": False,
            "message":
                "Wallet မဖြတ်ထားပါ။ Refund မလိုပါ။"
        }


    # --------------------------------------------------------
    # ALREADY REFUNDED
    # --------------------------------------------------------

    if int(
        order["refunded"] or 0
    ) == 1:

        return {
            "success": True,
            "refunded": False,
            "message":
                "ဒီ Order ကို Refund လုပ်ပြီးပါပြီ။"
        }


    # --------------------------------------------------------
    # REFUND
    # --------------------------------------------------------

    refund_result = refund_wallet(
        order["username"],
        float(order["amount"])
    )


    if not refund_result.get(
        "success"
    ):

        return {
            "success": False,
            "refunded": False,
            "message":
                refund_result.get(
                    "message",
                    "Refund မလုပ်နိုင်ပါ။"
                )
        }


    mark_order_refunded(
        order_id
    )


    # --------------------------------------------------------
    # UPDATE ORDER
    # --------------------------------------------------------

    conn = get_db()


    conn.execute(
        """
        UPDATE orders
        SET
            status = 'Failed',
            updated_at = ?
        WHERE id = ?
        """,
        (
            now(),
            order_id
        )
    )


    conn.commit()

    conn.close()


    # --------------------------------------------------------
    # CUSTOMER NOTIFICATION
    # --------------------------------------------------------

    create_notification(

        order["username"],

        "💰 Order Refund",

        (
            f"သင်တင်ထားသော "
            f"{order['package']} "
            f"Order #{order_id} "
            "မအောင်မြင်သဖြင့် "
            f"{float(order['amount']):,.0f} Ks ကို "
            "Wallet ထဲ ပြန်ထည့်ပေးပြီးပါပြီ။"
        )
    )


    return {

        "success": True,

        "refunded": True,

        "amount":
            float(
                order["amount"]
            ),

        "balance":
            refund_result.get(
                "balance"
            )
    }


# ============================================================
# UPDATE SINGLE ORDER STATUS
# ============================================================

def update_single_order_status(
    order_id
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    conn.close()


    if not order:

        return {
            "success": False,
            "message": "Order မတွေ့ပါ။"
        }


    # --------------------------------------------------------
    # NO PROVIDER ORDER
    # --------------------------------------------------------

    if not order[
        "provider_order_id"
    ]:

        return {
            "success": False,
            "message":
                "Provider Order ID မရှိပါ။"
        }


    # --------------------------------------------------------
    # ALREADY FINAL
    # --------------------------------------------------------

    if order["status"] in {
        "Completed",
        "Failed"
    }:

        return {
            "success": True,
            "status":
                order["status"],
            "message":
                "Order already finalized."
        }


    # --------------------------------------------------------
    # GET PROVIDER STATUS
    # --------------------------------------------------------

    result = get_provider_order_status(
        order[
            "provider_order_id"
        ]
    )


    if not result.get(
        "success"
    ):

        return result


    provider_status = result.get(
        "status",
        "Unknown"
    )


    normalized = normalize_order_status(
        provider_status
    )


    # --------------------------------------------------------
    # PROCESSING
    # --------------------------------------------------------

    if normalized == "Processing":

        conn = get_db()


        conn.execute(
            """
            UPDATE orders
            SET
                status = 'Processing',
                provider_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                provider_status,
                now(),
                order_id
            )
        )


        conn.commit()

        conn.close()


        return {

            "success": True,

            "status":
                "Processing",

            "provider_status":
                provider_status
        }


    # --------------------------------------------------------
    # COMPLETED
    # --------------------------------------------------------

    if normalized == "Completed":

        conn = get_db()


        conn.execute(
            """
            UPDATE orders
            SET
                status = 'Completed',
                provider_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                provider_status,
                now(),
                order_id
            )
        )


        conn.commit()

        conn.close()


        create_notification(

            order["username"],

            "✅ Recharge Completed",

            (
                f"သင်တင်ထားသော "
                f"{order['package']} "
                f"Order #{order_id} ကို "
                "In Game ထဲ ဖြည့်ပြီးပါပြီ။"
            )
        )


        return {

            "success": True,

            "status":
                "Completed",

            "provider_status":
                provider_status
        }


    # --------------------------------------------------------
    # FAILED
    # --------------------------------------------------------

    if normalized == "Failed":

        conn = get_db()


        conn.execute(
            """
            UPDATE orders
            SET
                status = 'Failed',
                provider_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                provider_status,
                now(),
                order_id
            )
        )


        conn.commit()

        conn.close()


        refund_result = refund_failed_order(
            order_id
        )


        return {

            "success":
                refund_result.get(
                    "success",
                    True
                ),

            "status":
                "Failed",

            "provider_status":
                provider_status,

            "refunded":
                refund_result.get(
                    "refunded",
                    False
                )
        }


    return {

        "success": True,

        "status":
            normalized,

        "provider_status":
            provider_status
    }


# ============================================================
# CHECK ALL PROCESSING ORDERS
# ============================================================

def check_processing_orders():

    conn = get_db()


    orders = conn.execute(
        """
        SELECT id
        FROM orders
        WHERE status = 'Processing'
        AND provider_order_id IS NOT NULL
        AND provider_order_id != ''
        ORDER BY id ASC
        LIMIT 50
        """
    ).fetchall()


    conn.close()


    results = []


    for row in orders:

        try:

            result = (
                update_single_order_status(
                    row["id"]
                )
            )


            results.append({
                "order_id":
                    row["id"],

                "result":
                    result
            })


        except Exception as e:

            print(
                "[STATUS CHECK ERROR]",
                row["id"],
                str(e)
            )


    return results


# ============================================================
# MANUAL ORDER STATUS API
# ============================================================

@app.route(
    "/api/order/<int:order_id>/status"
)
def order_status_api(
    order_id
):

    if not login_required():

        return jsonify({

            "success":
                False,

            "message":
                "Unauthorized"

        }), 401


    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        AND username = ?
        """,
        (
            order_id,
            session["username"]
        )
    ).fetchone()


    conn.close()


    if not order:

        return jsonify({

            "success":
                False,

            "message":
                "Order မတွေ့ပါ။"

        }), 404


    result = (
        update_single_order_status(
            order_id
        )
    )


    conn = get_db()


    updated = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    conn.close()


    return jsonify({

        "success":
            result.get(
                "success",
                False
            ),

        "order": {

            "id":
                updated["id"],

            "game":
                updated["game"],

            "package":
                updated["package"],

            "amount":
                float(
                    updated["amount"]
                ),

            "status":
                updated["status"],

            "provider_status":
                updated["provider_status"],

            "provider_order_id":
                updated["provider_order_id"],

            "created_at":
                updated["created_at"],

            "updated_at":
                updated["updated_at"]
        },

        "message":
            result.get(
                "message",
                ""
            )
    })


# ============================================================
# BACKGROUND STATUS CHECKER
# ============================================================

_status_checker_started = False


def status_checker_loop():

    while True:

        try:

            if flash_topup_configured():

                check_processing_orders()


        except Exception as e:

            print(
                "[STATUS CHECKER ERROR]",
                str(e)
            )


        # ----------------------------------------------------
        # Check every 30 seconds
        # ----------------------------------------------------

        time.sleep(30)


def start_status_checker():

    global _status_checker_started


    if _status_checker_started:

        return


    _status_checker_started = True


    thread = threading.Thread(
        target=status_checker_loop,
        daemon=True
    )


    thread.start()


# ============================================================
# START BACKGROUND CHECKER
# ============================================================

start_status_checker()


# ============================================================
# PART 7 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 8 / 16
# NOTIFICATION SYSTEM
# ============================================================


# ============================================================
# CREATE NOTIFICATION
# ============================================================

def create_notification(
    username,
    title,
    message
):

    try:

        conn = get_db()

        conn.execute(
            """
            INSERT INTO notifications (
                username,
                title,
                message,
                is_read,
                created_at
            )
            VALUES (
                ?, ?, ?, 0, ?
            )
            """,
            (
                username,
                title,
                message,
                now()
            )
        )

        conn.commit()

        conn.close()

        return True

    except Exception as e:

        print(
            "[NOTIFICATION ERROR]",
            str(e)
        )

        return False


# ============================================================
# GET NOTIFICATIONS
# ============================================================

@app.route(
    "/api/notifications"
)
def api_notifications():

    if not login_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401


    username = session[
        "username"
    ]


    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (
            username,
        )
    ).fetchall()

    conn.close()


    notifications = []


    for row in rows:

        notifications.append({

            "id":
                row["id"],

            "title":
                row["title"],

            "message":
                row["message"],

            "is_read":
                int(
                    row["is_read"] or 0
                ),

            "created_at":
                row["created_at"]
        })


    return jsonify({

        "success":
            True,

        "notifications":
            notifications
    })


# ============================================================
# UNREAD NOTIFICATION COUNT
# ============================================================

@app.route(
    "/api/notifications/unread"
)
def api_unread_notifications():

    if not login_required():

        return jsonify({
            "success": False,
            "count": 0
        }), 401


    conn = get_db()


    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM notifications
        WHERE username = ?
        AND is_read = 0
        """,
        (
            session["username"],
        )
    ).fetchone()


    conn.close()


    return jsonify({

        "success":
            True,

        "count":
            int(
                row["total"] or 0
            )
    })


# ============================================================
# MARK ONE NOTIFICATION AS READ
# ============================================================

@app.route(
    "/api/notifications/<int:notification_id>/read",
    methods=["POST"]
)
def mark_notification_read(
    notification_id
):

    if not login_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401


    conn = get_db()


    notification = conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE id = ?
        AND username = ?
        """,
        (
            notification_id,
            session["username"]
        )
    ).fetchone()


    if not notification:

        conn.close()

        return jsonify({
            "success": False,
            "message":
                "Notification မတွေ့ပါ။"
        }), 404


    conn.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
        AND username = ?
        """,
        (
            notification_id,
            session["username"]
        )
    )


    conn.commit()

    conn.close()


    return jsonify({

        "success":
            True,

        "message":
            "Notification ဖတ်ပြီးပါပြီ။"
    })


# ============================================================
# MARK ALL NOTIFICATIONS AS READ
# ============================================================

@app.route(
    "/api/notifications/read-all",
    methods=["POST"]
)
def mark_all_notifications_read():

    if not login_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401


    conn = get_db()


    conn.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE username = ?
        AND is_read = 0
        """,
        (
            session["username"],
        )
    )


    conn.commit()

    conn.close()


    return jsonify({

        "success":
            True,

        "message":
            "Notification အားလုံး ဖတ်ပြီးပါပြီ။"
    })


# ============================================================
# DELETE ONE NOTIFICATION
# ============================================================

@app.route(
    "/api/notifications/<int:notification_id>",
    methods=["DELETE"]
)
def delete_notification(
    notification_id
):

    if not login_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401


    conn = get_db()


    cursor = conn.execute(
        """
        DELETE FROM notifications
        WHERE id = ?
        AND username = ?
        """,
        (
            notification_id,
            session["username"]
        )
    )


    conn.commit()

    deleted = (
        cursor.rowcount > 0
    )


    conn.close()


    if not deleted:

        return jsonify({

            "success":
                False,

            "message":
                "Notification မတွေ့ပါ။"

        }), 404


    return jsonify({

        "success":
            True,

        "message":
            "Notification ဖျက်ပြီးပါပြီ။"
    })


# ============================================================
# DELETE ALL READ NOTIFICATIONS
# ============================================================

@app.route(
    "/api/notifications/delete-read",
    methods=["DELETE"]
)
def delete_read_notifications():

    if not login_required():

        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401


    conn = get_db()


    conn.execute(
        """
        DELETE FROM notifications
        WHERE username = ?
        AND is_read = 1
        """,
        (
            session["username"],
        )
    )


    conn.commit()

    conn.close()


    return jsonify({

        "success":
            True,

        "message":
            "ဖတ်ပြီးသား Notification တွေ ဖျက်ပြီးပါပြီ။"
    })


# ============================================================
# NOTIFICATION PAGE - NEW VERSION
# ============================================================

@app.route(
    "/my-notifications"
)
def my_notifications():

    if not login_required():

        return redirect(
            url_for("login")
        )


    username = session[
        "username"
    ]


    conn = get_db()


    rows = conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (
            username,
        )
    ).fetchall()


    unread = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM notifications
        WHERE username = ?
        AND is_read = 0
        """,
        (
            username,
        )
    ).fetchone()


    conn.close()


    return render_template(
        "notifications.html",
        notifications=rows,
        unread_count=int(
            unread["total"] or 0
        )
    )


# ============================================================
# ORDER NOTIFICATION HELPER
# ============================================================

def notify_order_processing(
    order
):

    try:

        create_notification(

            order["username"],

            "🔄 Order Processing",

            (
                f"သင်တင်ထားသော "
                f"{order['package']} "
                f"Order #{order['id']} ကို "
                "Auto Recharge လုပ်နေပါပြီ။"
            )
        )

    except Exception as e:

        print(
            "[ORDER NOTIFICATION ERROR]",
            str(e)
        )


# ============================================================
# ORDER COMPLETED NOTIFICATION
# ============================================================

def notify_order_completed(
    order
):

    try:

        create_notification(

            order["username"],

            "✅ Recharge Completed",

            (
                f"သင်ဖြည့်ထားသော "
                f"{order['package']} "
                f"Order #{order['id']} ကို "
                "In Game ထဲ ဖြည့်ပြီးပါပြီ။"
            )
        )

    except Exception as e:

        print(
            "[COMPLETED NOTIFICATION ERROR]",
            str(e)
        )


# ============================================================
# ORDER FAILED NOTIFICATION
# ============================================================

def notify_order_failed(
    order
):

    try:

        create_notification(

            order["username"],

            "❌ Recharge Failed",

            (
                f"သင်တင်ထားသော "
                f"{order['package']} "
                f"Order #{order['id']} "
                "မအောင်မြင်ပါ။"
            )
        )

    except Exception as e:

        print(
            "[FAILED NOTIFICATION ERROR]",
            str(e)
        )


# ============================================================
# WALLET DEPOSIT NOTIFICATION
# ============================================================

def notify_deposit_approved(
    username,
    amount,
    balance
):

    return create_notification(

        username,

        "💰 Deposit Approved",

        (
            f"သင်ဖြည့်ထားသော Deposit "
            f"{float(amount):,.0f} Ks ကို "
            "Wallet ထဲထည့်ပြီးပါပြီ။\n\n"
            f"လက်ကျန်ငွေ - "
            f"{float(balance):,.0f} Ks"
        )
    )


# ============================================================
# WALLET CHARGE NOTIFICATION
# ============================================================

def notify_wallet_charged(
    username,
    amount,
    package,
    order_id
):

    return create_notification(

        username,

        "💎 Wallet Charged",

        (
            f"Order #{order_id} အတွက် "
            f"{package} ကို ဝယ်ယူပြီး "
            f"{float(amount):,.0f} Ks "
            "Wallet ထဲမှ ဖြတ်ထားပါပြီ။"
        )
    )


# ============================================================
# REFUND NOTIFICATION
# ============================================================

def notify_refund(
    username,
    amount,
    order_id
):

    return create_notification(

        username,

        "💰 Refund Completed",

        (
            f"Order #{order_id} မအောင်မြင်သဖြင့် "
            f"{float(amount):,.0f} Ks ကို "
            "Wallet ထဲ ပြန်ထည့်ပေးပြီးပါပြီ။"
        )
    )


# ============================================================
# PART 8 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 9 / 16
# TELEGRAM OWNER NOTIFICATION
# ============================================================


# ============================================================
# TELEGRAM SETTINGS
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get(
    "8996593086:AAGll9JC9IJlTvPcgadRvj9URInBY8USlqw",
    ""
).strip()


TELEGRAM_OWNER_ID = os.environ.get(
    "5698123END",
    ""
).strip()


# ============================================================
# TELEGRAM CONFIG CHECK
# ============================================================

def telegram_configured():

    return bool(
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_OWNER_ID
    )


# ============================================================
# SEND TELEGRAM MESSAGE
# ============================================================

def send_telegram_message(
    message
):

    if not telegram_configured():

        print(
            "[TELEGRAM] "
            "Bot Token / Owner ID မရှိပါ။"
        )

        return {
            "success": False,
            "message":
                "Telegram configuration မရှိပါ။"
        }


    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )


    payload = {

        "chat_id":
            TELEGRAM_OWNER_ID,

        "text":
            str(message),

        "parse_mode":
            "HTML",

        "disable_web_page_preview":
            True
    }


    try:

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )


        try:

            data = response.json()

        except Exception:

            data = {}


        if (
            response.ok
            and data.get("ok")
        ):

            return {
                "success": True,
                "data": data
            }


        return {

            "success": False,

            "message":
                data.get(
                    "description",
                    response.text
                ),

            "data":
                data
        }


    except Exception as e:

        print(
            "[TELEGRAM ERROR]",
            str(e)
        )


        return {

            "success": False,

            "message":
                str(e)
        }


# ============================================================
# FORMAT ORDER FOR TELEGRAM
# ============================================================

def format_order_telegram(
    order
):

    return (
        "🛒 <b>NEW ORDER</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Order ID: "
        f"<code>#{order['id']}</code>\n"
        f"👤 Username: "
        f"<code>{order['username']}</code>\n"
        f"🎮 Game: "
        f"<b>{order['game']}</b>\n"
        f"📦 Package: "
        f"<b>{order['package']}</b>\n"
        f"💰 Amount: "
        f"<b>{float(order['amount']):,.0f} Ks</b>\n"
        f"🎯 Game ID: "
        f"<code>{order['game_id']}</code>\n"
        f"🌐 Server ID: "
        f"<code>{order['server_id'] or '-'}</code>\n"
        f"📌 Status: "
        f"<b>{order['status']}</b>\n"
        f"🔗 Provider ID: "
        f"<code>{order['provider_order_id'] or '-'}</code>\n"
        f"🕐 Created: "
        f"{order['created_at']}\n"
        "━━━━━━━━━━━━━━━━━━"
    )


# ============================================================
# SEND NEW ORDER TO OWNER
# ============================================================

def notify_owner_new_order(
    order_id
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    conn.close()


    if not order:

        return {
            "success": False,
            "message":
                "Order မတွေ့ပါ။"
        }


    message = format_order_telegram(
        order
    )


    return send_telegram_message(
        message
    )


# ============================================================
# FORMAT DEPOSIT FOR TELEGRAM
# ============================================================

def format_deposit_telegram(
    deposit
):

    return (
        "💰 <b>NEW DEPOSIT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Deposit ID: "
        f"<code>#{deposit['id']}</code>\n"
        f"👤 Username: "
        f"<code>{deposit['username']}</code>\n"
        f"💵 Amount: "
        f"<b>{float(deposit['amount']):,.0f} Ks</b>\n"
        f"💳 Payment: "
        f"<b>{deposit['payment_method']}</b>\n"
        f"🧾 Transaction: "
        f"<code>{deposit['transaction_id']}</code>\n"
        f"📌 Status: "
        f"<b>{deposit['status']}</b>\n"
        f"🕐 Created: "
        f"{deposit['created_at']}\n"
        "━━━━━━━━━━━━━━━━━━"
    )


# ============================================================
# SEND DEPOSIT TO OWNER
# ============================================================

def notify_owner_new_deposit(
    deposit_id
):

    conn = get_db()


    deposit_row = conn.execute(
        """
        SELECT *
        FROM deposits
        WHERE id = ?
        """,
        (
            deposit_id,
        )
    ).fetchone()


    conn.close()


    if not deposit_row:

        return {
            "success": False,
            "message":
                "Deposit မတွေ့ပါ။"
        }


    message = format_deposit_telegram(
        deposit_row
    )


    return send_telegram_message(
        message
    )


# ============================================================
# SEND ORDER COMPLETED TO OWNER
# ============================================================

def notify_owner_order_completed(
    order_id
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    conn.close()


    if not order:

        return {
            "success": False,
            "message":
                "Order မတွေ့ပါ။"
        }


    message = (
        "✅ <b>ORDER COMPLETED</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Order: "
        f"<code>#{order['id']}</code>\n"
        f"👤 User: "
        f"<code>{order['username']}</code>\n"
        f"🎮 Game: "
        f"<b>{order['game']}</b>\n"
        f"📦 Package: "
        f"<b>{order['package']}</b>\n"
        f"💰 Amount: "
        f"<b>{float(order['amount']):,.0f} Ks</b>\n"
        f"🎯 ID: "
        f"<code>{order['game_id']}</code>\n"
        f"🌐 Server: "
        f"<code>{order['server_id'] or '-'}</code>\n"
        f"🔗 Provider: "
        f"<code>{order['provider_order_id'] or '-'}</code>\n"
        "━━━━━━━━━━━━━━━━━━"
    )


    return send_telegram_message(
        message
    )


# ============================================================
# SEND ORDER FAILED TO OWNER
# ============================================================

def notify_owner_order_failed(
    order_id,
    reason=""
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    conn.close()


    if not order:

        return {
            "success": False,
            "message":
                "Order မတွေ့ပါ။"
        }


    message = (
        "❌ <b>ORDER FAILED</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Order: "
        f"<code>#{order['id']}</code>\n"
        f"👤 User: "
        f"<code>{order['username']}</code>\n"
        f"🎮 Game: "
        f"<b>{order['game']}</b>\n"
        f"📦 Package: "
        f"<b>{order['package']}</b>\n"
        f"💰 Amount: "
        f"<b>{float(order['amount']):,.0f} Ks</b>\n"
        f"📌 Status: "
        f"<b>{order['status']}</b>\n"
        f"🔗 Provider: "
        f"<code>{order['provider_order_id'] or '-'}</code>\n"
    )


    if reason:

        message += (
            f"⚠️ Reason: "
            f"<code>{reason}</code>\n"
        )


    message += (
        "━━━━━━━━━━━━━━━━━━"
    )


    return send_telegram_message(
        message
    )


# ============================================================
# SEND DEPOSIT APPROVED TO OWNER
# ============================================================

def notify_owner_deposit_approved(
    deposit_id
):

    conn = get_db()


    deposit_row = conn.execute(
        """
        SELECT *
        FROM deposits
        WHERE id = ?
        """,
        (
            deposit_id,
        )
    ).fetchone()


    conn.close()


    if not deposit_row:

        return {
            "success": False,
            "message":
                "Deposit မတွေ့ပါ။"
        }


    message = (
        "✅ <b>DEPOSIT APPROVED</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Deposit: "
        f"<code>#{deposit_row['id']}</code>\n"
        f"👤 User: "
        f"<code>{deposit_row['username']}</code>\n"
        f"💰 Amount: "
        f"<b>{float(deposit_row['amount']):,.0f} Ks</b>\n"
        f"💳 Payment: "
        f"<b>{deposit_row['payment_method']}</b>\n"
        f"🧾 Transaction: "
        f"<code>{deposit_row['transaction_id']}</code>\n"
        "📌 Status: <b>Approved</b>\n"
        "━━━━━━━━━━━━━━━━━━"
    )


    return send_telegram_message(
        message
    )


# ============================================================
# TELEGRAM TEST ROUTE
# ============================================================

@app.route(
    "/api/telegram/test",
    methods=["POST"]
)
def telegram_test():

    if not login_required():

        return jsonify({

            "success":
                False,

            "message":
                "Unauthorized"

        }), 401


    # --------------------------------------------------------
    # IMPORTANT
    # ဒီ route ကို နောက်ပိုင်း Admin Only
    # ပြောင်းပေးမယ်။
    # --------------------------------------------------------

    result = send_telegram_message(

        "🤖 <b>Eren's Shop</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Telegram API Test OK\n"
        "🌐 Website is connected.\n"
        "━━━━━━━━━━━━━━━━━━"
    )


    if not result.get(
        "success"
    ):

        return jsonify({

            "success":
                False,

            "message":
                result.get(
                    "message",
                    "Telegram ပို့မရပါ။"
                )

        }), 500


    return jsonify({

        "success":
            True,

        "message":
            "Telegram message ပို့ပြီးပါပြီ။"
    })


# ============================================================
# PART 9 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 10 / 16
# TELEGRAM OWNER + GROUP NOTIFICATION
# ============================================================


# ============================================================
# TELEGRAM GROUP ID
# ============================================================

TELEGRAM_GROUP_ID = os.environ.get(
    "1003987776013",
    ""
).strip()


# ============================================================
# TELEGRAM DESTINATIONS
# ============================================================

def telegram_destinations():

    destinations = []


    if TELEGRAM_OWNER_ID:

        destinations.append(
            TELEGRAM_OWNER_ID
        )


    if TELEGRAM_GROUP_ID:

        if (
            TELEGRAM_GROUP_ID
            not in destinations
        ):

            destinations.append(
                TELEGRAM_GROUP_ID
            )


    return destinations


# ============================================================
# SEND MESSAGE TO OWNER + GROUP
# ============================================================

def send_telegram_all(
    message
):

    destinations = (
        telegram_destinations()
    )


    if not TELEGRAM_BOT_TOKEN:

        return {
            "success": False,
            "message":
                "TELEGRAM_BOT_TOKEN မရှိပါ။"
        }


    if not destinations:

        return {
            "success": False,
            "message":
                (
                    "TELEGRAM_OWNER_ID "
                    "သို့မဟုတ် "
                    "TELEGRAM_GROUP_ID "
                    "မရှိပါ။"
                )
        }


    results = []


    for chat_id in destinations:

        result = send_telegram_to_chat(
            chat_id,
            message
        )


        results.append({

            "chat_id":
                chat_id,

            "success":
                result.get(
                    "success",
                    False
                ),

            "message":
                result.get(
                    "message",
                    ""
                )
        })


    success_count = sum(
        1
        for item in results
        if item["success"]
    )


    return {

        "success":
            success_count > 0,

        "success_count":
            success_count,

        "total":
            len(destinations),

        "results":
            results
    }


# ============================================================
# SEND TELEGRAM TO SPECIFIC CHAT
# ============================================================

def send_telegram_to_chat(
    chat_id,
    message
):

    if not TELEGRAM_BOT_TOKEN:

        return {
            "success": False,
            "message":
                "Bot Token မရှိပါ။"
        }


    if not chat_id:

        return {
            "success": False,
            "message":
                "Chat ID မရှိပါ။"
        }


    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )


    payload = {

        "chat_id":
            str(chat_id),

        "text":
            str(message),

        "parse_mode":
            "HTML",

        "disable_web_page_preview":
            True
    }


    try:

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )


        try:

            data = response.json()

        except Exception:

            data = {}


        if (
            response.ok
            and data.get("ok")
        ):

            return {

                "success":
                    True,

                "data":
                    data
            }


        return {

            "success":
                False,

            "message":
                data.get(
                    "description",
                    response.text
                ),

            "data":
                data
        }


    except Exception as e:

        print(
            "[TELEGRAM SEND ERROR]",
            str(e)
        )


        return {

            "success":
                False,

            "message":
                str(e)
        }


# ============================================================
# ORDER -> OWNER + GROUP
# ============================================================

def notify_order_all(
    order_id
):

    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (
            order_id,
        )
    ).fetchone()


    conn.close()


    if not order:

        return {

            "success":
                False,

            "message":
                "Order မတွေ့ပါ။"
        }


    message = (
        "🛒 <b>NEW ORDER</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Order ID: "
        f"<code>#{order['id']}</code>\n"
        f"👤 Username: "
        f"<code>{order['username']}</code>\n"
        f"🎮 Game: "
        f"<b>{order['game']}</b>\n"
        f"📦 Package: "
        f"<b>{order['package']}</b>\n"
        f"💰 Amount: "
        f"<b>{float(order['amount']):,.0f} Ks</b>\n"
        f"🎯 Game ID: "
        f"<code>{order['game_id']}</code>\n"
        f"🌐 Server ID: "
        f"<code>{order['server_id'] or '-'}</code>\n"
        f"📌 Status: "
        f"<b>{order['status']}</b>\n"
        f"🔗 Provider ID: "
        f"<code>{order['provider_order_id'] or '-'}</code>\n"
        f"🕐 Created: "
        f"{order['created_at']}\n"
        "━━━━━━━━━━━━━━━━━━"
    )


    return send_telegram_all(
        message
    )


# ============================================================
# DEPOSIT -> OWNER + GROUP
# ============================================================

def notify_deposit_all(
    deposit_id
):

    conn = get_db()


    deposit_row = conn.execute(
        """
        SELECT *
        FROM deposits
        WHERE id = ?
        """,
        (
            deposit_id,
        )
    ).fetchone()


    conn.close()


    if not deposit_row:

        return {

            "success":
                False,

            "message":
                "Deposit မတွေ့ပါ။"
        }


    message = (
        "💰 <b>NEW DEPOSIT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Deposit ID: "
        f"<code>#{deposit_row['id']}</code>\n"
        f"👤 Username: "
        f"<code>{deposit_row['username']}</code>\n"
        f"💵 Amount: "
        f"<b>{float(deposit_row['amount']):,.0f} Ks</b>\n"
        f"💳 Payment: "
        f"<b>{deposit_row['payment_method']}</b>\n"
        f"🧾 Transaction: "
        f"<code>{deposit_row['transaction_id']}</code>\n"
        f"📌 Status: "
        f"<b>{deposit_row['status']}</b>\n"
        f"🕐 Created: "
        f"{deposit_row['created_at']}\n"
        "━━━━━━━━━━━━━━━━━━"
    )


    return send_telegram_all(
        message
    )


# ============================================================
# TEST OWNER + GROUP
# ============================================================

@app.route(
    "/api/telegram/test-all",
    methods=["POST"]
)
def telegram_test_all():

    if not login_required():

        return jsonify({

            "success":
                False,

            "message":
                "Unauthorized"

        }), 401


    message = (
        "🤖 <b>Eren's Shop</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Telegram connection test\n"
        "👤 Owner + GP\n"
        "🌐 Website connected successfully.\n"
        "━━━━━━━━━━━━━━━━━━"
    )


    result = send_telegram_all(
        message
    )


    if not result.get(
        "success"
    ):

        return jsonify({

            "success":
                False,

            "message":
                result.get(
                    "message",
                    "Telegram ပို့မရပါ။"
                ),

            "results":
                result.get(
                    "results",
                    []
                )

        }), 500


    return jsonify({

        "success":
            True,

        "message":
            "Owner + GP နှစ်နေရာလုံးကို ပို့ပြီးပါပြီ။",

        "results":
            result.get(
                "results",
                []
            )
    })


# ============================================================
# PART 10 END
# ============================================================


# ============================================================
# EREN'S SHOP - PART 11 / 16
# ADMIN SYSTEM
# ============================================================


# ============================================================
# ADMIN SETTINGS
# ============================================================

ADMIN_USERNAME = os.environ.get(
    "Eren",
    "admin"
).strip()

ADMIN_PASSWORD = os.environ.get(
    "1852001",
    ""
).strip()


# ============================================================
# ADMIN LOGIN CHECK
# ============================================================

def admin_logged_in():

    return (
        session.get("is_admin")
        is True
    )


# ============================================================
# ADMIN REQUIRED
# ============================================================

def require_admin():

    if not admin_logged_in():

        return redirect(
            url_for("admin_login")
        )

    return None


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if admin_logged_in():

        return redirect(
            url_for("admin_dashboard")
        )


    if request.method == "POST":

        username = (
            request.form.get(
                "username"
            )
            or ""
        ).strip()


        password = (
            request.form.get(
                "password"
            )
            or ""
        )


        if (
            username == ADMIN_USERNAME
            and ADMIN_PASSWORD
            and password == ADMIN_PASSWORD
        ):

            session["is_admin"] = True

            session["admin_username"] = (
                username
            )


            return redirect(
                url_for("admin_dashboard")
            )


        flash(
            "Admin Username သို့မဟုတ် Password မှားနေပါတယ်။",
            "error"
        )


    return render_template(
        "admin_login.html"
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route(
    "/admin/logout"
)
def admin_logout():

    session.pop(
        "is_admin",
        None
    )

    session.pop(
        "admin_username",
        None
    )


    return redirect(
        url_for("admin_login")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route(
    "/admin"
)
def admin_dashboard():

    check = require_admin()

    if check:

        return check


    conn = get_db()


    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    total_users = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM users
        """
    ).fetchone()["total"]


    # --------------------------------------------------------
    # ORDERS
    # --------------------------------------------------------

    total_orders = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM orders
        """
    ).fetchone()["total"]


    pending_orders = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM orders
        WHERE status IN (
            'Pending',
            'Processing'
        )
        """
    ).fetchone()["total"]


    completed_orders = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM orders
        WHERE status = 'Completed'
        """
    ).fetchone()["total"]


    failed_orders = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM orders
        WHERE status = 'Failed'
        """
    ).fetchone()["total"]


    # --------------------------------------------------------
    # DEPOSITS
    # --------------------------------------------------------

    pending_deposits = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM deposits
        WHERE status = 'Pending'
        """
    ).fetchone()["total"]


    total_deposits = conn.execute(
        """
        SELECT COALESCE(
            SUM(amount), 0
        ) AS total
        FROM deposits
        WHERE status = 'Approved'
        """
    ).fetchone()["total"]


    # --------------------------------------------------------
    # RECENT ORDERS
    # --------------------------------------------------------

    recent_orders = conn.execute(
        """
        SELECT *
        FROM orders
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()


    # --------------------------------------------------------
    # RECENT DEPOSITS
    # --------------------------------------------------------

    recent_deposits = conn.execute(
        """
        SELECT *
        FROM deposits
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()


    conn.close()


    return render_template(

        "admin_dashboard.html",

        total_users=
            total_users,

        total_orders=
            total_orders,

        pending_orders=
            pending_orders,

        completed_orders=
            completed_orders,

        failed_orders=
            failed_orders,

        pending_deposits=
            pending_deposits,

        total_deposits=
            float(
                total_deposits or 0
            ),

        recent_orders=
            recent_orders,

        recent_deposits=
            recent_deposits
    )


# ============================================================
# ADMIN DEPOSITS
# ============================================================

@app.route(
    "/admin/deposits"
)
def admin_deposits():

    check = require_admin()

    if check:

        return check


    status = (
        request.args.get(
            "status"
        )
        or "all"
    ).strip()


    conn = get_db()


    if status == "all":

        deposits = conn.execute(
            """
            SELECT *
            FROM deposits
            ORDER BY id DESC
            """
        ).fetchall()

    else:

        deposits = conn.execute(
            """
            SELECT *
            FROM deposits
            WHERE status = ?
            ORDER BY id DESC
            """,
            (
                status,
            )
        ).fetchall()


    conn.close()


    return render_template(

        "admin_deposits.html",

        deposits=
            deposits,

        selected_status=
            status
    )


# ============================================================
# ADMIN APPROVE DEPOSIT
# ============================================================

@app.route(
    "/admin/deposit/<int:deposit_id>/approve",
    methods=["POST"]
)
def admin_approve_deposit(
    deposit_id
):

    check = require_admin()

    if check:

        return check


    result = approve_deposit(
        deposit_id
    )


    if not result.get(
        "success"
    ):

        flash(
            result.get(
                "message",
                "Deposit approve မလုပ်နိုင်ပါ။"
            ),
            "error"
        )

        return redirect(
            url_for(
                "admin_deposits"
            )
        )


    # --------------------------------------------------------
    # TELEGRAM OWNER + GP
    # --------------------------------------------------------

    try:

        notify_owner_deposit_approved(
            deposit_id
        )

    except Exception as e:

        print(
            "[DEPOSIT TELEGRAM ERROR]",
            str(e)
        )


    flash(
        (
            f"Deposit #{deposit_id} "
            "Approve လုပ်ပြီးပါပြီ။"
        ),
        "success"
    )


    return redirect(
        url_for(
            "admin_deposits"
        )
    )


# ============================================================
# ADMIN REJECT DEPOSIT
# ============================================================

@app.route(
    "/admin/deposit/<int:deposit_id>/reject",
    methods=["POST"]
)
def admin_reject_deposit(
    deposit_id
):

    check = require_admin()

    if check:

        return check


    reason = (
        request.form.get(
            "reason"
        )
        or ""
    ).strip()


    result = reject_deposit(
        deposit_id,
        reason
    )


    if not result.get(
        "success"
    ):

        flash(
            result.get(
                "message",
                "Deposit reject မလုပ်နိုင်ပါ။"
            ),
            "error"
        )

        return redirect(
            url_for(
                "admin_deposits"
            )
        )


    flash(
        (
            f"Deposit #{deposit_id} "
            "Reject လုပ်ပြီးပါပြီ။"
        ),
        "success"
    )


    return redirect(
        url_for(
            "admin_deposits"
        )
    )


# ============================================================
# ADMIN ORDERS
# ============================================================

@app.route(
    "/admin/orders"
)
def admin_orders():

    check = require_admin()

    if check:

        return check


    status = (
        request.args.get(
            "status"
        )
        or "all"
    ).strip()


    conn = get_db()


    if status == "all":

        orders = conn.execute(
            """
            SELECT *
            FROM orders
            ORDER BY id DESC
            """
        ).fetchall()

    else:

        orders = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE status = ?
            ORDER BY id DESC
            """,
            (
                status,
            )
        ).fetchall()


    conn.close()


    return render_template(

        "admin_orders.html",

        orders=
            orders,

        selected_status=
            status
    )


# ============================================================
# ADMIN ORDER STATUS CHECK
# ============================================================

@app.route(
    "/admin/order/<int:order_id>/check",
    methods=["POST"]
)
def admin_check_order(
    order_id
):

    check = require_admin()

    if check:

        return check


    result = (
        update_single_order_status(
            order_id
        )
    )


    if result.get(
        "success"
    ):

        flash(
            (
                f"Order #{order_id} "
                f"Status: "
                f"{result.get('status', 'Unknown')}"
            ),
            "success"
        )

    else:

        flash(
            result.get(
                "message",
                "Status စစ်မရပါ။"
            ),
            "error"
        )


    return redirect(
        url_for(
            "admin_orders"
        )
    )


# ============================================================
# ADMIN USERS
# ============================================================

@app.route(
    "/admin/users"
)
def admin_users():

    check = require_admin()

    if check:

        return check


    conn = get_db()


    users = conn.execute(
        """
        SELECT
            id,
            username,
            balance,
            created_at
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()


    conn.close()


    return render_template(

        "admin_users.html",

        users=
            users
    )


# ============================================================
# ADMIN USER BALANCE
# ============================================================

@app.route(
    "/admin/user/<int:user_id>/balance",
    methods=["POST"]
)
def admin_update_balance(
    user_id
):

    check = require_admin()

    if check:

        return check


    action = (
        request.form.get(
            "action"
        )
        or ""
    ).strip().lower()


    amount_raw = (
        request.form.get(
            "amount"
        )
        or ""
    ).strip()


    try:

        amount = float(
            amount_raw
        )

    except ValueError:

        flash(
            "Amount မမှန်ပါ။",
            "error"
        )

        return redirect(
            url_for(
                "admin_users"
            )
        )


    if amount <= 0:

        flash(
            "Amount 0 ထက်ကြီးရပါမယ်။",
            "error"
        )

        return redirect(
            url_for(
                "admin_users"
            )
        )


    conn = get_db()


    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (
            user_id,
        )
    ).fetchone()


    if not user:

        conn.close()

        flash(
            "User မတွေ့ပါ။",
            "error"
        )

        return redirect(
            url_for(
                "admin_users"
            )
        )


    old_balance = float(
        user["balance"] or 0
    )


    if action == "add":

        new_balance = (
            old_balance
            + amount
        )


    elif action == "remove":

        new_balance = (
            old_balance
            - amount
        )


        if new_balance < 0:

            new_balance = 0


    else:

        conn.close()

        flash(
            "Action မမှန်ပါ။",
            "error"
        )

        return redirect(
            url_for(
                "admin_users"
            )
        )


    conn.execute(
        """
        UPDATE users
        SET balance = ?
        WHERE id = ?
        """,
        (
            new_balance,
            user_id
        )
    )


    conn.commit()

    conn.close()


    create_notification(

        user["username"],

        "💰 Wallet Updated",

        (
            f"Admin မှ Wallet Balance ကို "
            f"{new_balance:,.0f} Ks သို့ "
            "ပြောင်းလဲပေးထားပါတယ်။"
        )
    )


    flash(
        (
            f"{user['username']} Wallet "
            "ပြောင်းပြီးပါပြီ။"
        ),
        "success"
    )


    return redirect(
        url_for(
            "admin_users"
        )
    )


# ============================================================
# PART 11 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 12 / 16
# ML / PUBG AUTO RECHARGE API
# FLASH TOPUP
# ============================================================

import os
import json
import time
import uuid
import hmac
import hashlib
import requests


# ============================================================
# FLASH TOPUP API CONFIG
# ============================================================

FT_API_ID = os.environ.get(
    "RSL5YP4YFXLEGL8X",
    ""
).strip()

FT_API_KEY = os.environ.get(
    "4aadba4402eceffa0e6f777a8b09c7709c74c5c7556c9cc7e72e8740639e2f6e",
    ""
).strip()

FT_BASE_URL = os.environ.get(
    "FT_BASE_URL",
    "https://api.flashtopup.com/api/reseller/v2"
).rstrip("/")

FT_TIMEOUT = int(
    os.environ.get(
        "FT_TIMEOUT",
        "20"
    )
)

FT_AUTO_RECHARGE = (
    os.environ.get(
        "FT_AUTO_RECHARGE",
        "1"
    )
    .strip()
    .lower()
    in {
        "1",
        "true",
        "yes",
        "on"
    }
)


# ============================================================
# SIGNATURE SETTINGS
# ============================================================

FT_SIGN_TEMPLATE = os.environ.get(
    "FT_SIGN_TEMPLATE",
    "{path}{timestamp}{nonce}{body_hash}"
)

FT_ORDER_PATH = os.environ.get(
    "FT_ORDER_PATH",
    "/order"
)

FT_STATUS_PATH_TEMPLATE = os.environ.get(
    "FT_STATUS_PATH_TEMPLATE",
    "/order/{order_id}"
)

FT_WEBHOOK_SECRET = os.environ.get(
    "FT_WEBHOOK_SECRET",
    ""
).strip()


# ============================================================
# ENABLE CHECK
# ============================================================

def flash_topup_enabled():

    return bool(
        FT_API_ID
        and FT_API_KEY
        and FT_BASE_URL
        and FT_AUTO_RECHARGE
    )


# ============================================================
# CREATE HMAC SIGNATURE
# ============================================================

def _flash_signature(
    path,
    timestamp,
    nonce,
    body_bytes
):

    body_hash = hashlib.sha256(
        body_bytes
    ).hexdigest()


    signing_string = (
        FT_SIGN_TEMPLATE.format(
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body_hash=body_hash
        )
    )


    return hmac.new(
        FT_API_KEY.encode(
            "utf-8"
        ),

        signing_string.encode(
            "utf-8"
        ),

        hashlib.sha256
    ).hexdigest()


# ============================================================
# API HEADERS
# ============================================================

def _flash_headers(
    path,
    body_bytes
):

    timestamp = str(
        int(time.time())
    )

    nonce = uuid.uuid4().hex


    signature = _flash_signature(
        path,
        timestamp,
        nonce,
        body_bytes
    )


    return {

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",

        "X-FT-API-ID":
            FT_API_ID,

        "X-FT-TIMESTAMP":
            timestamp,

        "X-FT-NONCE":
            nonce,

        "X-FT-SIGNATURE":
            signature
    }


# ============================================================
# FLASH TOPUP REQUEST
# ============================================================

def _flash_json_request(
    method,
    path,
    payload=None
):

    body = json.dumps(
        payload or {},
        separators=(
            ",",
            ":"
        ),
        ensure_ascii=False
    ).encode("utf-8")


    headers = _flash_headers(
        path,
        body
    )


    url = (
        f"{FT_BASE_URL}"
        f"{path}"
    )


    try:

        response = requests.request(

            method,

            url,

            data=body,

            headers=headers,

            timeout=FT_TIMEOUT
        )


        try:

            data = response.json()

        except Exception:

            data = {
                "raw":
                    response.text[:2000]
            }


        print(
            "[FlashTopup]",
            method,
            path,
            "->",
            response.status_code,
            data
        )


        return {

            "ok":
                200
                <= response.status_code
                < 300,

            "status_code":
                response.status_code,

            "data":
                data
        }


    except requests.RequestException as e:

        print(
            "[FlashTopup ERROR]",
            str(e)
        )


        return {

            "ok":
                False,

            "status_code":
                0,

            "data": {

                "error":
                    str(e)
            }
        }


# ============================================================
# SERVICE CODE MAP
# ============================================================

def load_flash_service_map():

    raw = os.environ.get(
        "FT_SERVICE_MAP_JSON",
        ""
    ).strip()


    if not raw:

        return {}


    try:

        data = json.loads(
            raw
        )


        if isinstance(
            data,
            dict
        ):

            return data


    except Exception as e:

        print(
            "⚠️ FT_SERVICE_MAP_JSON Error:",
            e
        )


    return {}


FT_SERVICE_MAP = (
    load_flash_service_map()
)


# ============================================================
# GET SERVICE CODE
# ============================================================

def flash_service_code(
    game,
    package
):

    key = (
        f"{game}|{package}"
    )


    # Exact service-code override
    if key in FT_SERVICE_MAP:

        return str(
            FT_SERVICE_MAP[key]
        )


    # --------------------------------------------------------
    # MOBILE LEGENDS
    # --------------------------------------------------------

    if game == "ML":

        amount = (
            package
            .split(
                " - ",
                1
            )[0]
            .replace(
                "💎",
                ""
            )
            .strip()
        )


        if amount.isdigit():

            return (
                "TOPUP_MOBILE_LEGENDS_"
                f"{amount}_DIAMONDS"
            )


        if "Weekly" in package:

            return (
                "TOPUP_MOBILE_LEGENDS_"
                "WEEKLY_PASS"
            )


    # --------------------------------------------------------
    # PUBG MOBILE
    # --------------------------------------------------------

    if game == "PUBG":

        amount = (
            package
            .split(
                " - ",
                1
            )[0]
            .replace(
                "UC",
                ""
            )
            .strip()
        )


        if amount.isdigit():

            return (
                "TOPUP_PUBG_MOBILE_"
                f"{amount}_UC"
            )


    return ""


# ============================================================
# PLACE FLASH TOPUP ORDER
# ============================================================

def flash_place_order(
    game,
    package,
    game_id,
    server_id,
    local_order_id
):

    if not flash_topup_enabled():

        return {

            "success":
                False,

            "enabled":
                False,

            "error":
                "FlashTopup API မသတ်မှတ်ရသေးပါ။"
        }


    service_code = (
        flash_service_code(
            game,
            package
        )
    )


    if not service_code:

        return {

            "success":
                False,

            "enabled":
                True,

            "error":
                (
                    f"{game} / {package} "
                    "အတွက် Service Code မရှိပါ။ "
                    "FT_SERVICE_MAP_JSON ထည့်ပါ။"
                )
        }


    # --------------------------------------------------------
    # CREATE UNIQUE REFERENCE
    # --------------------------------------------------------

    reference_id = (
        f"EREN-"
        f"{local_order_id}-"
        f"{uuid.uuid4().hex[:8]}"
    )


    # --------------------------------------------------------
    # API PAYLOAD
    # --------------------------------------------------------

    payload = {

        "service_code":
            service_code,

        "reference_id":
            reference_id,

        "quantity":
            1,

        "user_id":
            str(game_id)
    }


    # ML Server ID
    if (
        game == "ML"
        and server_id
    ):

        payload[
            "server_id"
        ] = str(
            server_id
        )


    # --------------------------------------------------------
    # SEND API ORDER
    # --------------------------------------------------------

    result = _flash_json_request(

        "POST",

        FT_ORDER_PATH,

        payload
    )


    data = (
        result.get(
            "data"
        )
        or {}
    )


    if (
        not result.get("ok")
        or data.get("success")
        is False
    ):

        error = (

            data.get(
                "message"
            )

            or data.get(
                "error"
            )

            or data.get(
                "raw"
            )

            or (
                f"HTTP "
                f"{result.get('status_code')}"
            )
        )


        return {

            "success":
                False,

            "enabled":
                True,

            "error":
                str(error),

            "raw":
                data
        }


    # --------------------------------------------------------
    # RESPONSE DATA
    # --------------------------------------------------------

    inner = (

        data.get("data")

        if isinstance(
            data.get("data"),
            dict
        )

        else data
    )


    provider_order_id = (

        inner.get(
            "order_id"
        )

        or inner.get(
            "id"
        )

        or inner.get(
            "orderId"
        )
    )


    provider_status = (

        inner.get(
            "order_status"
        )

        or inner.get(
            "status"
        )

        or "Processing"
    )


    if not provider_order_id:

        return {

            "success":
                False,

            "enabled":
                True,

            "error":
                (
                    "API Response ထဲမှာ "
                    "Provider Order ID မပါပါ။"
                ),

            "raw":
                data
        }


    return {

        "success":
            True,

        "enabled":
            True,

        "provider_order_id":
            str(
                provider_order_id
            ),

        "provider_status":
            str(
                provider_status
            ),

        "service_code":
            service_code,

        "raw":
            data
    }


# ============================================================
# GET FLASH TOPUP ORDER STATUS
# ============================================================

def flash_get_order_status(
    provider_order_id
):

    if (
        not flash_topup_enabled()
        or not provider_order_id
    ):

        return {

            "success":
                False,

            "error":
                "FlashTopup API မသတ်မှတ်ရသေးပါ။"
        }


    path = (
        FT_STATUS_PATH_TEMPLATE.format(
            order_id=
                provider_order_id
        )
    )


    result = _flash_json_request(

        "GET",

        path,

        {}
    )


    data = (
        result.get(
            "data"
        )
        or {}
    )


    inner = (

        data.get("data")

        if isinstance(
            data.get("data"),
            dict
        )

        else data
    )


    status = (

        inner.get(
            "order_status"
        )

        or inner.get(
            "status"
        )
    )


    return {

        "success":
            bool(
                result.get("ok")
            )
            and bool(status),

        "status":
            str(status)
            if status
            else "Unknown",

        "raw":
            data,

        "error":
            (
                data.get(
                    "message"
                )
                or data.get(
                    "error"
                )
                if isinstance(
                    data,
                    dict
                )
                else ""
            )
    }


# ============================================================
# NORMALIZE PROVIDER STATUS
# ============================================================

def normalize_provider_status(
    status
):

    value = str(
        status or ""
    ).strip().lower()


    if value in {

        "completed",
        "complete",
        "success",
        "successful",
        "delivered",
        "done"

    }:

        return "Completed"


    if value in {

        "failed",
        "failure",
        "cancelled",
        "canceled",
        "rejected",
        "error"

    }:

        return "Failed"


    return "Processing"


# ============================================================
# CHECK API CONFIG
# ============================================================

@app.route(
    "/api/auto-recharge/config",
    methods=["GET"]
)
def auto_recharge_config():

    if not login_required():

        return jsonify({

            "success":
                False,

            "message":
                "Unauthorized"

        }), 401


    return jsonify({

        "success":
            True,

        "enabled":
            flash_topup_enabled(),

        "ml":
            bool(
                flash_service_code(
                    "ML",
                    "86 💎 - 5,600 Ks"
                )
            ),

        "pubg":
            bool(
                flash_service_code(
                    "PUBG",
                    "60 UC - 600 Ks"
                )
            )
    })


# ============================================================
# TEST FLASH TOPUP CONNECTION
# ============================================================

@app.route(
    "/api/auto-recharge/test",
    methods=["POST"]
)
def test_auto_recharge():

    if not admin_logged_in():

        return jsonify({

            "success":
                False,

            "message":
                "Admin Only"

        }), 403


    if not flash_topup_enabled():

        return jsonify({

            "success":
                False,

            "message":
                (
                    "FlashTopup API Variables "
                    "မပြည့်စုံသေးပါ။"
                )
        })


    return jsonify({

        "success":
            True,

        "message":
            "FlashTopup API configuration OK.",

        "base_url":
            FT_BASE_URL,

        "auto_recharge":
            FT_AUTO_RECHARGE
    })


# ============================================================
# PART 12 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 13 / 16
# ML / PUBG ORDER -> AUTO RECHARGE API
# ============================================================


# ============================================================
# PACKAGE PRICE MAP
# ============================================================

PACKAGE_PRICE_MAP = {

    # ---------------- ML ----------------

    "10 💎 - 1,000 Ks": 1000,
    "12 💎 - 1,200 Ks": 1200,
    "20 💎 - 1,900 Ks": 1900,
    "22 💎 - 2,100 Ks": 2100,
    "33 💎 - 3,000 Ks": 3000,
    "44 💎 - 3,600 Ks": 3600,
    "55 💎 - 4,000 Ks": 4000,
    "56 💎 - 4,400 Ks": 4400,
    "86 💎 - 5,600 Ks": 5600,
    "172 💎 - 10,800 Ks": 10800,
    "257 💎 - 15,800 Ks": 15800,
    "279 💎 - 17,100 Ks": 17100,
    "343 💎 - 20,600 Ks": 20600,
    "429 💎 - 25,900 Ks": 25900,
    "Weekly Pass - 6,400 Ks": 6400,


    # ---------------- PUBG ----------------

    "60 UC - 600 Ks": 600,
    "325 UC - 3,250 Ks": 3250,
    "660 UC - 6,600 Ks": 6600,
    "1800 UC - 18,000 Ks": 18000,
    "3850 UC - 38,500 Ks": 38500,
}


# ============================================================
# CREATE AUTO ORDER
# ============================================================

def create_auto_order(
    username,
    game,
    package,
    game_id,
    server_id,
    telegram_username,
    payment
):

    if game not in {
        "ML",
        "PUBG"
    }:

        return {
            "success": False,
            "message":
                "Auto Recharge က ML/PUBG အတွက်ပဲ ဖြစ်ပါတယ်။"
        }


    if not flash_topup_enabled():

        return {
            "success": False,
            "message":
                "Auto Recharge API မချိတ်ထားသေးပါ။"
        }


    if package not in PACKAGE_PRICE_MAP:

        return {
            "success": False,
            "message":
                "Package မမှန်ပါ။"
        }


    price = float(
        PACKAGE_PRICE_MAP[
            package
        ]
    )


    # --------------------------------------------------------
    # CHECK USER
    # --------------------------------------------------------

    conn = get_db()


    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (
            username,
        )
    ).fetchone()


    if not user:

        conn.close()

        return {
            "success": False,
            "message":
                "User account မတွေ့ပါ။"
        }


    balance = float(
        user["balance"] or 0
    )


    if balance < price:

        conn.close()

        return {
            "success": False,
            "message":
                (
                    "Wallet Balance မလုံလောက်ပါ။ "
                    f"လိုအပ်ငွေ - "
                    f"{price - balance:,.0f} Ks"
                )
        }


    # --------------------------------------------------------
    # CREATE LOCAL ORDER FIRST
    # --------------------------------------------------------

    cursor = conn.cursor()


    cursor.execute(
        """
        INSERT INTO orders (
            username,
            game,
            package,
            game_id,
            server_id,
            telegram_username,
            payment,
            status,
            created_at,
            wallet_charged
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, 0
        )
        """,
        (
            username,
            game,
            package,
            game_id,
            server_id,
            telegram_username,
            payment,
            "Pending",
            now()
        )
    )


    order_id = cursor.lastrowid


    conn.commit()

    conn.close()


    # --------------------------------------------------------
    # CUSTOMER NOTIFICATION
    # --------------------------------------------------------

    create_notification(

        username,

        "🟡 Order တင်ပြီးပါပြီ",

        (
            f"သင်ရွေးထားသော "
            f"{package} ကို "
            f"Order #{order_id} အဖြစ် "
            "Auto Recharge စတင်လုပ်နေပါပြီ။"
        )
    )


    # --------------------------------------------------------
    # SEND TO FLASH TOPUP API
    # --------------------------------------------------------

    result = process_auto_recharge(
        order_id,
        notify=True
    )


    # --------------------------------------------------------
    # API FAILED
    # --------------------------------------------------------

    if not result.get(
        "success"
    ):

        error = result.get(
            "error",
            "Unknown API error"
        )


        create_notification(

            username,

            "❌ Auto Recharge Failed",

            (
                f"Order #{order_id} "
                "Auto Recharge မအောင်မြင်ပါ။\n\n"
                f"အကြောင်းရင်း - {error}"
            )
        )


        # ----------------------------------------------------
        # OWNER + GP
        # ----------------------------------------------------

        try:

            send_telegram_all(

                (
                    "❌ <b>AUTO RECHARGE FAILED</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 Order: <code>#{order_id}</code>\n"
                    f"👤 User: <code>{username}</code>\n"
                    f"🎮 Game: <b>{game}</b>\n"
                    f"📦 Package: <b>{package}</b>\n"
                    f"💰 Price: <b>{price:,.0f} Ks</b>\n"
                    f"🎯 ID: <code>{game_id}</code>\n"
                    f"🌐 Server: <code>{server_id or '-'}</code>\n"
                    f"⚠️ Error: <code>{str(error)[:500]}</code>\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
            )

        except Exception as e:

            print(
                "[TELEGRAM FAILED ORDER ERROR]",
                e
            )


        return {

            "success":
                False,

            "order_id":
                order_id,

            "status":
                "Failed",

            "message":
                (
                    f"Order #{order_id} "
                    "Auto Recharge မအောင်မြင်ပါ။"
                ),

            "error":
                str(error)
        }


    # --------------------------------------------------------
    # API ACCEPTED
    # --------------------------------------------------------

    provider_order_id = (
        result.get(
            "provider_order_id"
        )
    )


    provider_status = (
        result.get(
            "status",
            "Processing"
        )
    )


    # --------------------------------------------------------
    # CUSTOMER MESSAGE
    # --------------------------------------------------------

    if provider_status == "Completed":

        customer_message = (

            f"✅ Order #{order_id} "
            "အောင်မြင်ပြီးပါပြီ။\n\n"

            f"💎 {package}\n"

            "🎮 In Game ထဲသို့ "
            "ဖြည့်ပြီးပါပြီ။"
        )


    else:

        customer_message = (

            f"🟢 Order #{order_id} "
            "တင်ပြီးပါပြီ။\n\n"

            f"💎 {package}\n"

            "🔄 Auto Recharge "
            "လုပ်နေပါပြီ။"
        )


    create_notification(

        username,

        (
            "🎮 Order အောင်မြင်ပါပြီ"
            if provider_status == "Completed"
            else
            "🟢 Auto Recharge လုပ်နေပါပြီ"
        ),

        customer_message
    )


    # --------------------------------------------------------
    # OWNER + GP NOTIFICATION
    # --------------------------------------------------------

    try:

        send_telegram_all(

            (
                "🤖 <b>AUTO ORDER</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"🆔 Order: <code>#{order_id}</code>\n"
                f"👤 User: <code>{username}</code>\n"
                f"🎮 Game: <b>{game}</b>\n"
                f"📦 Package: <b>{package}</b>\n"
                f"💰 Price: <b>{price:,.0f} Ks</b>\n"
                f"🎯 Game ID: <code>{game_id}</code>\n"
                f"🌐 Server ID: <code>{server_id or '-'}</code>\n"
                f"🔗 Provider ID: <code>{provider_order_id}</code>\n"
                f"📌 Status: <b>{provider_status}</b>\n"
                "━━━━━━━━━━━━━━━━━━"
            )
        )

    except Exception as e:

        print(
            "[TELEGRAM AUTO ORDER ERROR]",
            e
        )


    return {

        "success":
            True,

        "order_id":
            order_id,

        "provider_order_id":
            provider_order_id,

        "status":
            provider_status,

        "message":
            customer_message
    }


# ============================================================
# PLACE AUTO ORDER API
# ============================================================

@app.route(
    "/api/place-order",
    methods=["POST"]
)
def api_place_auto_order():

    if "username" not in session:

        return jsonify({

            "success":
                False,

            "message":
                "Login လုပ်ပါ။"

        }), 401


    data = (
        request.get_json(
            silent=True
        )
        or {}
    )


    game = str(
        data.get(
            "game",
            ""
        )
    ).strip()


    package = str(
        data.get(
            "package",
            ""
        )
    ).strip()


    game_id = str(
        data.get(
            "game_id",
            ""
        )
    ).strip()


    server_id = str(
        data.get(
            "server_id",
            ""
        )
    ).strip()


    telegram_username = str(
        data.get(
            "telegram_username",
            ""
        )
    ).strip().lstrip("@")


    payment = str(
        data.get(
            "payment",
            "Wallet"
        )
    ).strip()


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if game not in {
        "ML",
        "PUBG"
    }:

        return jsonify({

            "success":
                False,

            "message":
                "ML သို့မဟုတ် PUBG ရွေးပါ။"

        }), 400


    if not package:

        return jsonify({

            "success":
                False,

            "message":
                "Package ရွေးပါ။"

        }), 400


    if not game_id:

        return jsonify({

            "success":
                False,

            "message":
                "Game ID ထည့်ပါ။"

        }), 400


    if (
        game == "ML"
        and not server_id
    ):

        return jsonify({

            "success":
                False,

            "message":
                "ML အတွက် Server ID ထည့်ပါ။"

        }), 400


    # --------------------------------------------------------
    # CREATE ORDER
    # --------------------------------------------------------

    result = create_auto_order(

        session["username"],

        game,

        package,

        game_id,

        server_id,

        telegram_username,

        payment
    )


    if not result.get(
        "success"
    ):

        return jsonify(
            result
        ), 400


    return jsonify(
        result
    )


# ============================================================
# GET ORDER STATUS
# ============================================================

@app.route(
    "/api/my-order/<int:order_id>"
)
def api_my_order(
    order_id
):

    if "username" not in session:

        return jsonify({

            "success":
                False,

            "message":
                "Login လုပ်ပါ။"

        }), 401


    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        AND username = ?
        """,
        (
            order_id,
            session["username"]
        )
    ).fetchone()


    conn.close()


    if not order:

        return jsonify({

            "success":
                False,

            "message":
                "Order မတွေ့ပါ။"

        }), 404


    return jsonify({

        "success":
            True,

        "order": {

            "id":
                order["id"],

            "game":
                order["game"],

            "package":
                order["package"],

            "game_id":
                order["game_id"],

            "server_id":
                order["server_id"],

            "status":
                order["status"],

            "provider_order_id":
                order["provider_order_id"],

            "provider_status":
                order["provider_status"],

            "created_at":
                order["created_at"]
        }
    })


# ============================================================
# PART 13 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 14 / 16
# AUTO API STATUS CHECKER
# COMPLETED / FAILED / REFUND
# ============================================================


# ============================================================
# STATUS CHECK ONE ORDER
# ============================================================

def check_auto_order_status(order_id):

    conn = get_db()

    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (order_id,)
    ).fetchone()

    if not order:
        conn.close()

        return {
            "success": False,
            "message": "Order မတွေ့ပါ။"
        }

    provider_order_id = (
        order["provider_order_id"]
    )

    if not provider_order_id:
        conn.close()

        return {
            "success": False,
            "message":
                "Provider Order ID မရှိသေးပါ။"
        }

    result = flash_get_order_status(
        provider_order_id
    )

    if not result.get("success"):

        conn.close()

        return {
            "success": False,
            "status":
                order["status"],
            "message":
                result.get(
                    "error",
                    "API Status စစ်မရပါ။"
                )
        }

    provider_status = result.get(
        "status",
        "Processing"
    )

    normalized = normalize_provider_status(
        provider_status
    )


    # --------------------------------------------------------
    # CURRENT STATUS
    # --------------------------------------------------------

    old_status = (
        order["status"]
        or "Pending"
    )


    # --------------------------------------------------------
    # COMPLETED
    # --------------------------------------------------------

    if normalized == "Completed":

        conn.execute(
            """
            UPDATE orders
            SET
                provider_status = ?,
                status = 'Completed'
            WHERE id = ?
            """,
            (
                str(provider_status),
                order_id
            )
        )

        conn.commit()

        conn.close()


        # Customer notification
        create_notification(

            order["username"],

            "🎮 Order အောင်မြင်ပါပြီ",

            (
                f"သင်ဖြည့်ထားသော "
                f"{order['package']} ကို "
                "In Game ထဲသို့ "
                "ဖြည့်ပြီးပါပြီ။"
            )
        )


        # Owner + GP
        try:

            send_telegram_all(

                (
                    "✅ <b>AUTO RECHARGE COMPLETED</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 Order: "
                    f"<code>#{order_id}</code>\n"
                    f"👤 User: "
                    f"<code>{order['username']}</code>\n"
                    f"🎮 Game: "
                    f"<b>{order['game']}</b>\n"
                    f"📦 Package: "
                    f"<b>{order['package']}</b>\n"
                    f"🎯 ID: "
                    f"<code>{order['game_id']}</code>\n"
                    f"🌐 Server: "
                    f"<code>{order['server_id'] or '-'}</code>\n"
                    f"🔗 Provider: "
                    f"<code>{provider_order_id}</code>\n"
                    f"📌 Status: "
                    f"<b>{provider_status}</b>\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
            )

        except Exception as e:

            print(
                "[COMPLETED TELEGRAM ERROR]",
                e
            )


        return {

            "success": True,

            "status":
                "Completed",

            "provider_status":
                provider_status,

            "changed":
                old_status != "Completed"
        }


    # --------------------------------------------------------
    # FAILED
    # --------------------------------------------------------

    if normalized == "Failed":

        # Re-open connection because
        # refund helper needs a live connection.
        conn = get_db()

        order = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE id = ?
            """,
            (order_id,)
        ).fetchone()


        if not order:

            conn.close()

            return {
                "success": False,
                "message":
                    "Order မတွေ့ပါ။"
            }


        # Update provider status first
        conn.execute(
            """
            UPDATE orders
            SET
                provider_status = ?,
                status = 'Failed'
            WHERE id = ?
            """,
            (
                str(provider_status),
                order_id
            )
        )


        # ----------------------------------------------------
        # REFUND ONLY IF WALLET WAS CHARGED
        # ----------------------------------------------------

        refunded = (
            _refund_wallet_for_order(
                conn,
                order
            )
        )


        conn.commit()

        conn.close()


        # Customer notification
        refund_amount = (
            PACKAGE_PRICE_MAP.get(
                order["package"],
                0
            )
        )


        create_notification(

            order["username"],

            "❌ Auto Recharge Failed",

            (
                f"Order #{order_id} "
                "မအောင်မြင်ပါ။\n\n"
                f"💰 {refund_amount:,.0f} Ks "
                "ကို Wallet ထဲ "
                "ပြန်ထည့်ပေးထားပါတယ်။"
                if refunded
                else
                (
                    f"Order #{order_id} "
                    "မအောင်မြင်ပါ။"
                )
            )
        )


        # Owner + GP
        try:

            refund_text = (
                f"💰 Refund: "
                f"{refund_amount:,.0f} Ks"
                if refunded
                else
                "💰 Refund: မဖြတ်ထားပါ"
            )


            send_telegram_all(

                (
                    "❌ <b>AUTO RECHARGE FAILED</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 Order: "
                    f"<code>#{order_id}</code>\n"
                    f"👤 User: "
                    f"<code>{order['username']}</code>\n"
                    f"🎮 Game: "
                    f"<b>{order['game']}</b>\n"
                    f"📦 Package: "
                    f"<b>{order['package']}</b>\n"
                    f"🎯 ID: "
                    f"<code>{order['game_id']}</code>\n"
                    f"🔗 Provider: "
                    f"<code>{provider_order_id}</code>\n"
                    f"📌 Status: "
                    f"<b>{provider_status}</b>\n"
                    f"{refund_text}\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
            )

        except Exception as e:

            print(
                "[FAILED TELEGRAM ERROR]",
                e
            )


        return {

            "success": True,

            "status":
                "Failed",

            "provider_status":
                provider_status,

            "refunded":
                refunded,

            "changed":
                old_status != "Failed"
        }


    # --------------------------------------------------------
    # PROCESSING / PENDING
    # --------------------------------------------------------

    conn = get_db()

    conn.execute(
        """
        UPDATE orders
        SET
            provider_status = ?,
            status = 'Processing'
        WHERE id = ?
        """,
        (
            str(provider_status),
            order_id
        )
    )

    conn.commit()

    conn.close()


    return {

        "success":
            True,

        "status":
            "Processing",

        "provider_status":
            provider_status,

        "changed":
            old_status != "Processing"
    }


# ============================================================
# CHECK ALL PROCESSING ORDERS
# ============================================================

def check_all_auto_orders():

    if not flash_topup_enabled():

        return {

            "success":
                False,

            "message":
                "Auto Recharge API disabled.",

            "checked":
                0
        }


    conn = get_db()


    orders = conn.execute(
        """
        SELECT id
        FROM orders
        WHERE game IN ('ML', 'PUBG')
        AND provider_order_id IS NOT NULL
        AND provider_order_id != ''
        AND status IN (
            'Pending',
            'Processing'
        )
        ORDER BY id ASC
        LIMIT 50
        """
    ).fetchall()


    conn.close()


    checked = 0
    completed = 0
    failed = 0


    for row in orders:

        order_id = row["id"]


        try:

            result = (
                check_auto_order_status(
                    order_id
                )
            )


            if result.get(
                "success"
            ):

                checked += 1


                if (
                    result.get(
                        "status"
                    )
                    == "Completed"
                ):

                    completed += 1


                elif (
                    result.get(
                        "status"
                    )
                    == "Failed"
                ):

                    failed += 1


        except Exception as e:

            print(
                f"[STATUS CHECK ERROR] "
                f"Order #{order_id}:",
                e
            )


    return {

        "success":
            True,

        "checked":
            checked,

        "completed":
            completed,

        "failed":
            failed
    }


# ============================================================
# MANUAL ADMIN STATUS CHECK
# ============================================================

@app.route(
    "/admin/order/<int:order_id>/api-status",
    methods=["POST"]
)
def admin_api_status(
    order_id
):

    if not admin_logged_in():

        return jsonify({

            "success":
                False,

            "message":
                "Admin Only"

        }), 403


    result = check_auto_order_status(
        order_id
    )


    return jsonify(
        result
    )


# ============================================================
# CHECK ALL API ORDERS
# ============================================================

@app.route(
    "/admin/api/check-orders",
    methods=["POST"]
)
def admin_check_all_api_orders():

    if not admin_logged_in():

        return jsonify({

            "success":
                False,

            "message":
                "Admin Only"

        }), 403


    result = check_all_auto_orders()


    return jsonify(
        result
    )


# ============================================================
# API STATUS FOR CUSTOMER
# ============================================================

@app.route(
    "/api/order/<int:order_id>/status"
)
def customer_order_status(
    order_id
):

    if "username" not in session:

        return jsonify({

            "success":
                False,

            "message":
                "Login လုပ်ပါ။"

        }), 401


    conn = get_db()


    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        AND username = ?
        """,
        (
            order_id,
            session["username"]
        )
    ).fetchone()


    conn.close()


    if not order:

        return jsonify({

            "success":
                False,

            "message":
                "Order မတွေ့ပါ။"

        }), 404


    return jsonify({

        "success":
            True,

        "order_id":
            order["id"],

        "game":
            order["game"],

        "package":
            order["package"],

        "status":
            order["status"],

        "provider_status":
            order["provider_status"],

        "provider_order_id":
            order["provider_order_id"]
    })


# ============================================================
# PART 14 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 15 / 16
# AUTO STATUS BACKGROUND WORKER
# ============================================================


# ============================================================
# AUTO STATUS CHECK SETTINGS
# ============================================================

AUTO_STATUS_CHECK_INTERVAL = 30

_auto_status_worker_started = False

_auto_status_worker_lock = threading.Lock()


# ============================================================
# AUTO STATUS CHECK WORKER
# ============================================================

def auto_status_check_worker():

    print(
        "🤖 AUTO STATUS CHECKER STARTED"
    )

    while True:

        try:

            # ------------------------------------------------
            # Check API enabled
            # ------------------------------------------------

            if not flash_topup_enabled():

                time.sleep(
                    AUTO_STATUS_CHECK_INTERVAL
                )

                continue


            # ------------------------------------------------
            # Check all processing orders
            # ------------------------------------------------

            result = (
                check_all_auto_orders()
            )


            if result.get("success"):

                checked = result.get(
                    "checked",
                    0
                )

                completed = result.get(
                    "completed",
                    0
                )

                failed = result.get(
                    "failed",
                    0
                )


                if checked > 0:

                    print(
                        "🤖 AUTO STATUS CHECK:",
                        f"Checked={checked},",
                        f"Completed={completed},",
                        f"Failed={failed}"
                    )


        except Exception as e:

            print(
                "[AUTO STATUS WORKER ERROR]",
                e
            )


        # ----------------------------------------------------
        # Wait before next check
        # ----------------------------------------------------

        time.sleep(
            AUTO_STATUS_CHECK_INTERVAL
        )


# ============================================================
# START AUTO STATUS WORKER
# ============================================================

def start_auto_status_worker():

    global _auto_status_worker_started


    with _auto_status_worker_lock:

        if _auto_status_worker_started:

            return


        _auto_status_worker_started = True


        worker = threading.Thread(

            target=
                auto_status_check_worker,

            daemon=True

        )


        worker.start()


        print(
            "✅ Auto Status Worker "
            "Background Thread Started"
        )


# ============================================================
# MANUAL AUTO STATUS TEST
# ============================================================

@app.route(
    "/admin/api/status-worker",
    methods=["GET"]
)
def admin_status_worker():

    if not admin_logged_in():

        return jsonify({

            "success":
                False,

            "message":
                "Admin Only"

        }), 403


    return jsonify({

        "success":
            True,

        "worker_running":
            _auto_status_worker_started,

        "interval":
            AUTO_STATUS_CHECK_INTERVAL,

        "message":
            (
                "Auto Status Checker "
                "is running."
                if _auto_status_worker_started
                else
                "Auto Status Checker "
                "is not running."
            )

    })


# ============================================================
# ADMIN FORCE CHECK ONE ORDER
# ============================================================

@app.route(
    "/admin/order/<int:order_id>/force-status",
    methods=["POST"]
)
def admin_force_order_status(
    order_id
):

    if not admin_logged_in():

        return jsonify({

            "success":
                False,

            "message":
                "Admin Only"

        }), 403


    try:

        result = (
            check_auto_order_status(
                order_id
            )
        )


        return jsonify(
            result
        )


    except Exception as e:

        print(
            "[FORCE STATUS ERROR]",
            e
        )


        return jsonify({

            "success":
                False,

            "message":
                str(e)

        }), 500


# ============================================================
# ADMIN AUTO CHECK SUMMARY
# ============================================================

@app.route(
    "/admin/api/status-summary",
    methods=["GET"]
)
def admin_status_summary():

    if not admin_logged_in():

        return jsonify({

            "success":
                False,

            "message":
                "Admin Only"

        }), 403


    conn = get_db()


    total_processing = conn.execute(
        """
        SELECT COUNT(*)
        FROM orders
        WHERE game IN ('ML', 'PUBG')
        AND provider_order_id IS NOT NULL
        AND provider_order_id != ''
        AND status IN (
            'Pending',
            'Processing'
        )
        """
    ).fetchone()[0]


    total_completed = conn.execute(
        """
        SELECT COUNT(*)
        FROM orders
        WHERE game IN ('ML', 'PUBG')
        AND status = 'Completed'
        """
    ).fetchone()[0]


    total_failed = conn.execute(
        """
        SELECT COUNT(*)
        FROM orders
        WHERE game IN ('ML', 'PUBG')
        AND status = 'Failed'
        """
    ).fetchone()[0]


    conn.close()


    return jsonify({

        "success":
            True,

        "processing":
            total_processing,

        "completed":
            total_completed,

        "failed":
            total_failed,

        "worker_running":
            _auto_status_worker_started,

        "interval":
            AUTO_STATUS_CHECK_INTERVAL

    })


# ============================================================
# START WORKER
# ============================================================

# Flask app စတင်တဲ့အချိန်
# Background Worker တစ်ခါပဲ Start လုပ်မယ်။

try:

    start_auto_status_worker()

except Exception as e:

    print(
        "[AUTO STATUS START ERROR]",
        e
    )


# ============================================================
# PART 15 END
# ============================================================

# ============================================================
# EREN'S SHOP - PART 16 / 16
# FINAL AUTO API INTEGRATION + STARTUP
# ============================================================


# ============================================================
# API HEALTH CHECK
# ============================================================

@app.route(
    "/admin/api/health",
    methods=["GET"]
)
def admin_api_health():

    if not admin_logged_in():

        return jsonify({

            "success": False,
            "message": "Admin Only"

        }), 403


    try:

        enabled = flash_topup_enabled()


        return jsonify({

            "success": True,

            "api_enabled":
                enabled,

            "worker_running":
                _auto_status_worker_started,

            "check_interval":
                AUTO_STATUS_CHECK_INTERVAL,

            "message":
                (
                    "API is ready."
                    if enabled
                    else
                    "API is disabled."
                )

        })


    except Exception as e:

        print(
            "[API HEALTH ERROR]",
            e
        )


        return jsonify({

            "success": False,
            "message": str(e)

        }), 500


# ============================================================
# AUTO CHECK NOW
# ============================================================

@app.route(
    "/admin/api/check-now",
    methods=["POST"]
)
def admin_api_check_now():

    if not admin_logged_in():

        return jsonify({

            "success": False,
            "message": "Admin Only"

        }), 403


    try:

        result = (
            check_all_auto_orders()
        )


        return jsonify(
            result
        )


    except Exception as e:

        print(
            "[CHECK NOW ERROR]",
            e
        )


        return jsonify({

            "success": False,
            "message": str(e)

        }), 500


# ============================================================
# GET ORDER STATUS
# ============================================================

@app.route(
    "/admin/api/order/<int:order_id>",
    methods=["GET"]
)
def admin_get_api_order(
    order_id
):

    if not admin_logged_in():

        return jsonify({

            "success": False,
            "message": "Admin Only"

        }), 403


    conn = get_db()


    order = conn.execute(
        """
        SELECT
            id,
            username,
            game,
            package,
            game_id,
            server_id,
            provider_order_id,
            provider_status,
            status
        FROM orders
        WHERE id = ?
        """,
        (order_id,)
    ).fetchone()


    conn.close()


    if not order:

        return jsonify({

            "success": False,
            "message": "Order မတွေ့ပါ။"

        }), 404


    return jsonify({

        "success": True,

        "order": {

            "id":
                order["id"],

            "username":
                order["username"],

            "game":
                order["game"],

            "package":
                order["package"],

            "game_id":
                order["game_id"],

            "server_id":
                order["server_id"],

            "provider_order_id":
                order["provider_order_id"],

            "provider_status":
                order["provider_status"],

            "status":
                order["status"]

        }

    })


# ============================================================
# STARTUP SAFETY
# ============================================================

def initialize_auto_api_system():

    try:

        print(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        print(
            "🚀 EREN'S SHOP AUTO API"
        )

        print(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


        # ----------------------------------------
        # Check API configuration
        # ----------------------------------------

        try:

            api_enabled = (
                flash_topup_enabled()
            )

        except Exception as e:

            api_enabled = False

            print(
                "[API CONFIG ERROR]",
                e
            )


        print(
            "🔌 API Enabled:",
            api_enabled
        )


        # ----------------------------------------
        # Start background worker
        # ----------------------------------------

        try:

            start_auto_status_worker()

        except Exception as e:

            print(
                "[WORKER START ERROR]",
                e
            )


        print(
            "🤖 Status Worker:",
            _auto_status_worker_started
        )


        print(
            "⏱️ Check Interval:",
            AUTO_STATUS_CHECK_INTERVAL,
            "seconds"
        )


        print(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


    except Exception as e:

        print(
            "[AUTO API INITIALIZATION ERROR]",
            e
        )


# ============================================================
# INITIALIZE
# ============================================================

try:

    initialize_auto_api_system()

except Exception as e:

    print(
        "[FINAL INIT ERROR]",
        e
    )


# ============================================================
# FINAL API MESSAGE
# ============================================================

print(
    "✅ EREN'S SHOP AUTO API SYSTEM READY"
)


# ============================================================
# PART 16 END
# ============================================================
