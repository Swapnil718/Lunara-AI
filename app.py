# app.py
import os
from flask import Flask, render_template, request, jsonify
from flask_login import LoginManager, login_required, current_user
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from models import db, ChatHistory, User
from auth import auth

# Load environment variables
load_dotenv()

# ---------------- APP & CONFIG ---------------- #
app = Flask(__name__)

# Allow cross-origin only if you plan to embed from your portfolio domain later.
# For now, keep it simple & open. You can restrict origins in production:
# CORS(app, resources={r"/chat": {"origins": ["https://your-portfolio.com"]}})
CORS(app)

# Use Postgres in production (Render provides DATABASE_URL), or SQLite locally
db_url = os.getenv("DATABASE_URL", "sqlite:///lunara.db")
if db_url.startswith("postgres://"):  # Render/Heroku old scheme
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")

# ---------------- EXTENSIONS ---------------- #
db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.init_app(app)

# Auth blueprint
app.register_blueprint(auth)

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- ROUTES ---------------- #

@app.route("/health")
def health():
    """Simple health check for UptimeRobot / Render."""
    return "ok", 200

@app.route("/")
def home():
    return render_template("landing.html")

@app.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    if request.method == "POST":
        user_message = (request.form.get("message") or "").strip()
        if not user_message:
            return jsonify({"reply": "Please type something."})

        # --- Send message to OpenAI
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are Lunara AI, a friendly and concise assistant."},
                    {"role": "user", "content": user_message},
                ],
            )
            bot_reply = resp.choices[0].message.content.strip()
        except Exception as e:
            bot_reply = f"Sorry, I ran into an error: {e}"

        # --- Save to database
        chat_entry = ChatHistory(
            user_id=current_user.id,
            user_message=user_message,
            bot_response=bot_reply,
        )
        db.session.add(chat_entry)
        db.session.commit()

        # --- JSON for the frontend JS
        return jsonify({"reply": bot_reply})

    # GET -> load full conversation and pass as `messages` to the template
    chats = (
        ChatHistory.query
        .filter_by(user_id=current_user.id)
        .order_by(ChatHistory.timestamp.asc())
        .all()
    )
    messages = []
    for c in chats:
        messages.append({"role": "user", "content": c.user_message, "created_at": c.timestamp})
        messages.append({"role": "assistant", "content": c.bot_response, "created_at": c.timestamp})

    return render_template("chat.html", messages=messages)

@app.route("/history")
@login_required
def history():
    chats = (
        ChatHistory.query
        .filter_by(user_id=current_user.id)
        .order_by(ChatHistory.timestamp.desc())
        .all()
    )
    return render_template("history.html", chats=chats)

# ---------------- BOOTSTRAP DB ---------------- #
with app.app_context():
    db.create_all()

# ---------------- LOCAL DEV ENTRYPOINT ---------------- #
if __name__ == "__main__":
    # For local dev. In Render, Gunicorn runs this app via Procfile.
    app.run(debug=True)

@app.route("/health")
def health():
    return "ok", 200
