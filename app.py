import os
from dotenv import load_dotenv
load_dotenv()

from functools import wraps
import pymysql
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

def get_db():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"), user=os.environ.get("DB_USER", "root"), password=os.environ.get("DB_PASSWORD", ""),
        database="nexora", cursorclass=pymysql.cursors.DictCursor
    )

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

HR_CARDS = [
    ("Recruiting & Hiring", "recruiting"),
    ("Onboarding & Training", "onboarding"),
    ("Attendance & Leave", "attendance"),
]
EMP_CARDS = [
    ("My Onboarding", "onboarding"),
    ("My Training", "training"),
    ("Attendance", "attendance"),
    ("Apply Leave", "leave"),
    ("AI Assistant", "assistant"),
]

@app.route("/")
def home():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT u.user_id, u.email, u.password_hash, r.role_name "
                "FROM users u JOIN roles r ON u.role_id = r.role_id "
                "WHERE u.email = %s", (email,))
            user = cur.fetchone()
        db.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["user_id"]
            session["email"] = user["email"]
            session["role"] = user["role_name"]
            return redirect(url_for("dashboard"))
        error = "Wrong email or password"
    return render_template("login.html", error=error)

@app.route("/dashboard")
@login_required
def dashboard():
    cards = HR_CARDS if session["role"] == "HR" else EMP_CARDS
    return render_template("dashboard.html", cards=cards)

@app.route("/page/<slug>")
@login_required
def page(slug):
    return render_template("placeholder.html", title=slug.capitalize())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

from recruiting import register as register_recruiting
register_recruiting(app, get_db, login_required)

if __name__ == "__main__":
    app.run(debug=True)
