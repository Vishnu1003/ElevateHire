import os
import sqlite3
import random
import pdfplumber
import docx
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_mail import Mail, Message
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI

# =====================================================
# APP CONFIG
# =====================================================
app = Flask(__name__, static_folder="public")
CORS(app)

app.config["SECRET_KEY"] = "elevatehire_secret"

# ---------- MAIL CONFIG ----------
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = "vish78622@gmail.com"
app.config["MAIL_PASSWORD"] = "ftoa cyyr dmes jerm"

mail = Mail(app)

# ---------- GROQ API ----------
client = OpenAI(

    api_key="YOUR_GROQ_API_KEY",  # Replace with your actual Groq API key
    base_url="https://api.groq.com/openai/v1"
)

# ---------- FOLDERS ----------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- OTP STORE ----------
otp_store = {}

# =====================================================
# DATABASE
# =====================================================
def init_db():
    conn = sqlite3.connect("auth.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# =====================================================
# RESUME TEXT EXTRACTION
# =====================================================
def extract_text(file_path):
    text = ""

    if file_path.endswith(".pdf"):
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""

    elif file_path.endswith(".docx"):
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"

    return text


# =====================================================
# ATS SCORE
# =====================================================
def calculate_ats_score(text):
    score = 0
    text_lower = text.lower()
    
    # 1. Section Completeness (Max 30)
    sections = {
        "education": r"\b(education|academic background|coursework)\b",
        "experience": r"\b(experience|work history|employment|history)\b",
        "projects": r"\b(projects|personal projects|portfolio)\b",
        "skills": r"\b(skills|technical skills|technologies)\b"
    }
    
    section_score = 0
    for sec, pattern in sections.items():
        if re.search(pattern, text_lower):
            section_score += 7.5
    score += section_score

    # 2. Quantifiable Impact & Metrics (Max 25)
    metrics_score = 0
    # Search for percentages (20%), money ($100), or isolated numbers (5)
    metric_matches = re.findall(r'(\d+%|\$\d+|\b\d+\b)', text)
    metrics_count = len(metric_matches)
    metrics_score = min(25, metrics_count * 5)  # 5 points per metric, up to 5 metrics
    score += metrics_score

    # 3. Action Verbs (Max 25)
    action_verbs = [
        "spearheaded", "optimized", "implemented", "developed", 
        "managed", "architected", "orchestrated", "engineered", 
        "designed", "streamlined", "increased", "decreased", "led", "created"
    ]
    found_verbs = 0
    for verb in action_verbs:
        if re.search(r'\b' + verb + r'\b', text_lower):
            found_verbs += 1
    verb_score = min(25, found_verbs * 5)  # 5 points per unique verb, up to 5
    score += verb_score

    # 4. Length Constraints (Max 20)
    # Optimal length roughly 200 - 800 words
    word_count = len(text.split())
    length_score = 0
    if 200 <= word_count <= 800:
        length_score = 20
    elif 100 <= word_count < 200 or 800 < word_count <= 1200:
        length_score = 10
    elif word_count < 100:
        length_score = 5 # Too short
    else:
        length_score = 5 # Too long
    score += length_score

    return min(int(score), 100)

# =====================================================
# FRONTEND
# =====================================================
@app.route("/")
def home():
    return send_from_directory("public", "index.html")

# =====================================================
# AUTH SYSTEM
# =====================================================

# -------- REGISTER OTP --------
@app.route("/send-register-otp", methods=["POST"])
def send_register_otp():
    data = request.json
    email = data["email"]

    otp = str(random.randint(100000, 999999))
    otp_store[email] = otp

    print(f"--- DEVELOPMENT OTP for {email}: {otp} ---")

    try:
        msg = Message(
            "ElevateHire Registration OTP",
            sender=app.config["MAIL_USERNAME"],
            recipients=[email]
        )
        msg.body = f"Your OTP is: {otp}"
        mail.send(msg)
        return jsonify({"message": "OTP Sent"})
    except Exception as e:
        print(f"Mail sending failed (is your email configured?): {e}")
        return jsonify({"message": "OTP Sent (Check Terminal)"})


# -------- REGISTER --------
def is_valid_password(pw):
    if len(pw) < 8:
        return False
    if not re.search(r'[A-Z]', pw):
        return False
    if not re.search(r'\d', pw):
        return False
    if not re.search(r'[!@#$%^&*()_+{}\[\]:;<>,.?~\\/-]', pw):
        return False
    return True

@app.route("/register", methods=["POST"])
def register():
    data = request.json

    if not is_valid_password(data.get("password", "")):
        return jsonify({"message": "Weak Password"})

    if otp_store.get(data["email"]) != data["otp"]:
        return jsonify({"message": "Invalid OTP"})

    conn = sqlite3.connect("auth.db")
    c = conn.cursor()

    hashed = generate_password_hash(data["password"])

    try:
        c.execute(
            "INSERT INTO users(name,email,password) VALUES(?,?,?)",
            (data["name"], data["email"], hashed)
        )
        conn.commit()
    except:
        return jsonify({"message": "Email already exists"})
    finally:
        conn.close()

    return jsonify({"message": "Registered Successfully"})


# -------- LOGIN --------
@app.route("/login", methods=["POST"])
def login():
    data = request.json

    conn = sqlite3.connect("auth.db")
    c = conn.cursor()

    c.execute(
        "SELECT password FROM users WHERE email=?",
        (data["email"],)
    )

    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[0], data["password"]):
        return jsonify({"message": "Login Success"})
    else:
        return jsonify({"message": "Invalid Credentials"})


# -------- FORGOT PASSWORD OTP --------
@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.json
    email = data["email"]

    otp = str(random.randint(100000, 999999))
    otp_store[email] = otp

    print(f"--- DEVELOPMENT OTP for {email}: {otp} ---")

    try:
        msg = Message(
            "ElevateHire Password Reset OTP",
            sender=app.config["MAIL_USERNAME"],
            recipients=[email]
        )
        msg.body = f"Your Reset OTP is: {otp}"
        mail.send(msg)
        return jsonify({"message": "OTP Sent"})
    except Exception as e:
        print(f"Mail sending failed (is your email configured?): {e}")
        return jsonify({"message": "OTP Sent (Check Terminal)"})


# -------- RESET PASSWORD --------
@app.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.json

    if not is_valid_password(data.get("password", "")):
        return jsonify({"message": "Weak Password"})

    if otp_store.get(data["email"]) != data["otp"]:
        return jsonify({"message": "Invalid OTP"})

    hashed = generate_password_hash(data["password"])

    conn = sqlite3.connect("auth.db")
    c = conn.cursor()

    c.execute(
        "UPDATE users SET password=? WHERE email=?",
        (hashed, data["email"])
    )

    conn.commit()
    conn.close()

    return jsonify({"message": "Password Updated"})


# =====================================================
# CHATBOT
# =====================================================
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message", "")
    history = data.get("history", "")

    current_time = datetime.now().strftime("%I:%M %p")
    hour = datetime.now().hour
    if hour < 12:
        time_of_day = "morning"
    elif hour < 17:
        time_of_day = "afternoon"
    else:
        time_of_day = "evening"

    if not history:
        greeting_instruction = f"The current local time is {current_time} ({time_of_day}). Please greet the user appropriately based on this time. If you do not know the user's name, ask for it immediately."
    else:
        greeting_instruction = "Do NOT greet the user again. Continue the conversation naturally."

    prompt = f"""
You are RON, an expert Career Advisor and Interview Prep Coach. 
{greeting_instruction}

Your goal is to help the user prepare for conversations with HR, give them interview tips, and suggest job roles they are qualified for based on their skillset, education, experience, and their resume analysis verdict.

- Start the conversation by asking ONE question at a time to gather their background, education, and skills.
- Ask about any resume feedback they've received.
- Provide actionable advice on how to talk to HR and answer interview questions.
- Suggest specific job roles that fit their profile.
- Do NOT write recruitment letters or offer them a job.
- Keep the conversation highly interactive, engaging, and professional.

Conversation:
{history}

User: {user_input}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are RON, an expert Career Advisor and Interview Prep Coach."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=500
    )

    return jsonify({
        "reply": response.choices[0].message.content.strip()
    })


# =====================================================
# RESUME UPLOAD
# =====================================================
@app.route("/upload", methods=["POST"])
def upload_resume():
    file = request.files["resume"]

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    resume_text = extract_text(file_path)
    ats_score = calculate_ats_score(resume_text)

    ai_prompt = f"""
Analyze this resume and suggest:

1. Best job roles
2. Suitable companies
3. Improvements

Resume:
{resume_text}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": ai_prompt}],
        temperature=0.7,
        max_tokens=700
    )

    return jsonify({
        "ats_score": ats_score,
        "analysis": response.choices[0].message.content.strip()
    })


# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)