import os
import random
import re
import smtplib
import sqlite3
import time
from email.message import EmailMessage
from flask import Flask, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()
else:
    # Minimal fallback loader when python-dotenv is unavailable.
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

app = Flask(__name__)
app.secret_key = "student-performance-secret-key"

BASE_SEMESTER_MARKS = 50.0
PASS_MARK = 75.0
BACKLOG_PENALTY_PER = 4.0
BACKLOG_PENALTY_CAP = 20.0
LECTURER_REG_PATTERN = re.compile(r"^AAP23CS(00[2-9]|0[1-2][0-9]|03[0-6])$")
STUDENT_ACCOUNT_REG_PATTERN = re.compile(r"^AAP23CS(00[2-9]|0[1-2][0-9]|03[0-6])$")
DB_PATH = "auth_users.db"
OTP_PROVIDER = os.getenv("OTP_PROVIDER", "gmail").strip().lower()
GMAIL_OTP_SENDER = os.getenv("GMAIL_OTP_SENDER", "").strip()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()
SEMESTER_PAPER_COUNTS = {1: 5, 2: 5, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 6}

AUTH_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login / Register</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
        :root {
            --bg1: #070b18;
            --bg2: #0f1f3b;
            --panel: rgba(255, 255, 255, 0.08);
            --text: #e2e8f0;
            --muted: #9fb0c9;
            --accent: #06b6d4;
            --accent2: #0ea5e9;
            --error: #b91c1c;
            --ok: #15803d;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 20px;
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
            color: var(--text);
            background:
                radial-gradient(circle at 12% 15%, rgba(6, 182, 212, 0.30), transparent 35%),
                radial-gradient(circle at 82% 78%, rgba(14, 165, 233, 0.26), transparent 42%),
                linear-gradient(135deg, var(--bg1), var(--bg2));
            animation: bgShift 10s ease-in-out infinite alternate;
        }
        .shell {
            width: min(760px, 100%);
            display: grid;
            grid-template-columns: 1fr;
            gap: 14px;
        }
        .card {
            background: var(--panel);
            border-radius: 14px;
            padding: 18px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            backdrop-filter: blur(16px);
            box-shadow: 0 22px 48px rgba(2, 8, 23, 0.35);
            animation: riseIn 0.5s ease-out both;
        }
        h1 { margin: 0 0 8px; font-size: 1.6rem; }
        h2 { margin: 0 0 12px; font-size: 1.2rem; }
        p { margin: 0 0 14px; color: var(--muted); }
        form { display: grid; gap: 10px; }
        label { font-weight: 600; font-size: 0.92rem; margin-bottom: 4px; display: block; }
        input, select {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 10px;
            font-size: 0.95rem;
            background: rgba(15, 23, 42, 0.45);
            color: #e2e8f0;
            transition: border-color 0.25s ease, transform 0.2s ease, box-shadow 0.25s ease;
        }
        input:focus, select:focus {
            outline: none;
            border-color: rgba(34, 211, 238, 0.85);
            box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.22);
            transform: translateY(-1px);
        }
        button {
            border: 0;
            padding: 10px 12px;
            border-radius: 10px;
            color: #fff;
            font-weight: 700;
            background: linear-gradient(90deg, var(--accent), var(--accent2));
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        button:hover {
            transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(14, 165, 233, 0.35);
        }
        .inline-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 8px;
        }
        .helper-link {
            color: #0369a1;
            text-decoration: none;
            font-size: 0.84rem;
            font-weight: 600;
        }
        .msg {
            margin-bottom: 10px;
            padding: 8px 10px;
            border-radius: 8px;
            font-size: 0.9rem;
        }
        .msg.error { background: #fee2e2; color: var(--error); }
        .msg.ok { background: #dcfce7; color: var(--ok); }
        @media (max-width: 900px) {
            .shell { grid-template-columns: 1fr; }
        }
        @keyframes riseIn {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes bgShift {
            from { background-position: 0% 0%, 100% 100%, 50% 50%; }
            to { background-position: 8% 6%, 92% 86%, 50% 50%; }
        }
    </style>
</head>
<body>
    <div class="shell">
        <div class="card">
            <h1>Student Performance Portal</h1>
            <p>Login or register as Student/Lecturer before accessing prediction.</p>
            {% if message %}
            <div class="msg {{ 'ok' if message_type == 'ok' else 'error' }}">{{ message }}</div>
            {% endif %}
            <h2>Login</h2>
            <form method="post" action="/login">
                <div>
                    <label for="login-role">Role</label>
                    <select id="login-role" name="role" required>
                        <option value="student">Student</option>
                        <option value="lecturer">Lecturer</option>
                    </select>
                </div>
                <div>
                    <label for="login-username">Username</label>
                    <input id="login-username" type="text" name="username" required>
                </div>
                <div>
                    <div class="inline-row">
                        <label for="login-password">Password</label>
                        <div>
                            <a class="helper-link" href="/forgot-password">Forgot Password?</a>
                            <span style="color:#94a3b8;"> | </span>
                            <a class="helper-link" href="/reset-password">Reset Password</a>
                        </div>
                    </div>
                    <input id="login-password" type="password" name="password" required>
                </div>
                <button type="submit">Login</button>
            </form>
        </div>

        <div class="card">
            <h2>Register</h2>
            <form method="post" action="/register">
                <div>
                    <label for="reg-role">Role</label>
                    <select id="reg-role" name="role" required onchange="toggleStudentRegisterField()">
                        <option value="student">Student</option>
                        <option value="lecturer">Lecturer</option>
                    </select>
                </div>
                <div>
                    <label for="reg-username">Username</label>
                    <input id="reg-username" type="text" name="username" required>
                </div>
                <div>
                    <label for="reg-password">Password</label>
                    <input id="reg-password" type="password" name="password" required>
                </div>
                <div>
                    <label for="reg-email">Gmail Address</label>
                    <input id="reg-email" type="email" name="email" required placeholder="e.g. student@gmail.com">
                </div>
                <div id="student-reg-wrap">
                    <label for="reg-student-register-number">Student Register Number</label>
                    <input
                        id="reg-student-register-number"
                        type="text"
                        name="student_register_number"
                        placeholder="AAP23CS002 to AAP23CS036"
                        pattern="AAP23CS(00[2-9]|0[1-2][0-9]|03[0-6])">
                </div>
                <button type="submit">Create Account</button>
            </form>
            <p style="margin-top:10px;">Registration completes only after OTP verification.</p>
        </div>
    </div>
    <script>
        function toggleStudentRegisterField() {
            const role = document.getElementById("reg-role").value;
            const wrap = document.getElementById("student-reg-wrap");
            const input = document.getElementById("reg-student-register-number");
            if (role === "student") {
                wrap.style.display = "block";
                input.required = true;
            } else {
                wrap.style.display = "none";
                input.required = false;
                input.value = "";
            }
        }
        toggleStudentRegisterField();
    </script>
</body>
</html>
"""

OTP_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify OTP</title>
    <style>
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 20px;
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            background: #f1f5f9;
        }
        .card {
            width: min(420px, 100%);
            background: #fff;
            border-radius: 14px;
            padding: 20px;
            box-shadow: 0 10px 24px rgba(2, 8, 23, 0.1);
        }
        h2 { margin: 0 0 10px; }
        p { margin: 0 0 14px; color: #475569; }
        .msg {
            margin-bottom: 10px;
            padding: 8px 10px;
            border-radius: 8px;
            font-size: 0.9rem;
        }
        .msg.error { background: #fee2e2; color: #b91c1c; }
        .msg.ok { background: #dcfce7; color: #15803d; }
        label {
            display: block;
            margin-bottom: 6px;
            font-weight: 600;
        }
        input {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #cbd5e1;
            border-radius: 10px;
            margin-bottom: 12px;
        }
        button {
            width: 100%;
            border: 0;
            padding: 10px 12px;
            border-radius: 10px;
            color: #fff;
            font-weight: 700;
            background: linear-gradient(90deg, #0284c7, #0369a1);
            cursor: pointer;
        }
        a {
            display: inline-block;
            margin-top: 12px;
            color: #0369a1;
            text-decoration: none;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>OTP Verification</h2>
        <p>An OTP was sent to {{ email }}.</p>
        {% if message %}
        <div class="msg {{ 'ok' if message_type == 'ok' else 'error' }}">{{ message }}</div>
        {% endif %}
        <form method="post" action="/verify-otp">
            <label for="otp">Enter 6-digit OTP</label>
            <input id="otp" type="text" name="otp" pattern="\\d{6}" maxlength="6" required>
            <button type="submit">Verify & Complete Registration</button>
        </form>
        <a href="/auth">Back to Login/Register</a>
    </div>
</body>
</html>
"""

FORGOT_PASSWORD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Forgot Password</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 20px;
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
            background:
                radial-gradient(circle at 15% 20%, rgba(6, 182, 212, 0.24), transparent 35%),
                radial-gradient(circle at 85% 85%, rgba(14, 165, 233, 0.20), transparent 40%),
                linear-gradient(135deg, #071122, #0b1830);
        }
        .card {
            width: min(460px, 100%);
            background: rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 20px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            backdrop-filter: blur(14px);
            box-shadow: 0 18px 40px rgba(2, 8, 23, 0.35);
        }
        h2 { margin: 0 0 10px; }
        p { margin: 0 0 14px; color: #9fb0c9; }
        .msg {
            margin-bottom: 10px;
            padding: 8px 10px;
            border-radius: 8px;
            font-size: 0.9rem;
        }
        .msg.error { background: #fee2e2; color: #b91c1c; }
        .msg.ok { background: #dcfce7; color: #15803d; }
        label {
            display: block;
            margin-bottom: 6px;
            font-weight: 600;
        }
        input, select {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 10px;
            margin-bottom: 12px;
            background: rgba(15, 23, 42, 0.45);
            color: #e2e8f0;
        }
        button {
            width: 100%;
            border: 0;
            padding: 10px 12px;
            border-radius: 10px;
            color: #fff;
            font-weight: 700;
            background: linear-gradient(90deg, #0284c7, #0369a1);
            cursor: pointer;
        }
        a {
            display: inline-block;
            margin-top: 12px;
            color: #38bdf8;
            text-decoration: none;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>Forgot Password</h2>
        <p>Enter your registration details. A temporary password will be sent to your Gmail.</p>
        {% if message %}
        <div class="msg {{ 'ok' if message_type == 'ok' else 'error' }}">{{ message }}</div>
        {% endif %}
        <form method="post" action="/forgot-password">
            <label for="fp-role">Role</label>
            <select id="fp-role" name="role" required>
                <option value="student">Student</option>
                <option value="lecturer">Lecturer</option>
            </select>
            <label for="fp-username">Username</label>
            <input id="fp-username" type="text" name="username" required>
            <label for="fp-email">Gmail Address</label>
            <input id="fp-email" type="email" name="email" required placeholder="e.g. student@gmail.com">
            <button type="submit">Send Temporary Password</button>
        </form>
        <a href="/reset-password">Already have temporary password? Reset it here</a>
        <br>
        <a href="/auth">Back to Login</a>
    </div>
</body>
</html>
"""

RESET_PASSWORD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Password</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 20px;
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
            background:
                radial-gradient(circle at 15% 20%, rgba(6, 182, 212, 0.24), transparent 35%),
                radial-gradient(circle at 85% 85%, rgba(14, 165, 233, 0.20), transparent 40%),
                linear-gradient(135deg, #071122, #0b1830);
        }
        .card {
            width: min(480px, 100%);
            background: rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 20px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            backdrop-filter: blur(14px);
            box-shadow: 0 18px 40px rgba(2, 8, 23, 0.35);
        }
        h2 { margin: 0 0 10px; }
        p { margin: 0 0 14px; color: #9fb0c9; }
        .msg {
            margin-bottom: 10px;
            padding: 8px 10px;
            border-radius: 8px;
            font-size: 0.9rem;
        }
        .msg.error { background: #fee2e2; color: #b91c1c; }
        .msg.ok { background: #dcfce7; color: #15803d; }
        label {
            display: block;
            margin-bottom: 6px;
            font-weight: 600;
        }
        input, select {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 10px;
            margin-bottom: 12px;
            background: rgba(15, 23, 42, 0.45);
            color: #e2e8f0;
        }
        button {
            width: 100%;
            border: 0;
            padding: 10px 12px;
            border-radius: 10px;
            color: #fff;
            font-weight: 700;
            background: linear-gradient(90deg, #0284c7, #0369a1);
            cursor: pointer;
        }
        a {
            display: inline-block;
            margin-top: 12px;
            color: #38bdf8;
            text-decoration: none;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>Reset Password</h2>
        <p>Use the temporary password received on Gmail to set your own new password.</p>
        {% if message %}
        <div class="msg {{ 'ok' if message_type == 'ok' else 'error' }}">{{ message }}</div>
        {% endif %}
        <form method="post" action="/reset-password">
            <label for="rp-role">Role</label>
            <select id="rp-role" name="role" required>
                <option value="student">Student</option>
                <option value="lecturer">Lecturer</option>
            </select>
            <label for="rp-username">Username</label>
            <input id="rp-username" type="text" name="username" required>
            <label for="rp-email">Gmail Address</label>
            <input id="rp-email" type="email" name="email" required placeholder="e.g. student@gmail.com">
            <label for="rp-temp-password">Temporary Password</label>
            <input id="rp-temp-password" type="password" name="temp_password" required>
            <label for="rp-new-password">New Password</label>
            <input id="rp-new-password" type="password" name="new_password" required>
            <label for="rp-confirm-password">Confirm New Password</label>
            <input id="rp-confirm-password" type="password" name="confirm_password" required>
            <button type="submit">Update Password</button>
        </form>
        <a href="/auth">Back to Login</a>
    </div>
</body>
</html>
"""

FORM_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Student Performance Predictor</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
        :root {
            --bg1: #070b18;
            --bg2: #10223f;
            --panel: rgba(255, 255, 255, 0.08);
            --text: #e2e8f0;
            --muted: #9fb0c9;
            --accent: #06b6d4;
            --accent-2: #0ea5e9;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
            color: var(--text);
            background:
                radial-gradient(circle at 8% 15%, rgba(6, 182, 212, 0.30), transparent 34%),
                radial-gradient(circle at 86% 84%, rgba(14, 165, 233, 0.22), transparent 42%),
                linear-gradient(135deg, var(--bg1), var(--bg2));
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 20px;
        }
        .card {
            width: min(640px, 100%);
            background: var(--panel);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            backdrop-filter: blur(16px);
            box-shadow: 0 22px 48px rgba(2, 8, 23, 0.35);
            animation: riseIn 0.45s ease-out both;
        }
        .top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }
        h1 { margin: 0 0 8px; font-size: 1.8rem; }
        .subtitle { margin: 0 0 16px; color: var(--muted); }
        .badge {
            background: rgba(34, 211, 238, 0.15);
            color: #67e8f9;
            border: 1px solid rgba(34, 211, 238, 0.35);
            border-radius: 999px;
            padding: 5px 10px;
            font-size: 0.85rem;
            font-weight: 700;
        }
        .link {
            text-decoration: none;
            color: #0369a1;
            font-size: 0.9rem;
            font-weight: 600;
        }
        form { display: grid; gap: 14px; }
        label {
            display: block;
            margin-bottom: 6px;
            font-weight: 600;
            font-size: 0.95rem;
        }
        input {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 10px;
            font-size: 0.95rem;
            background: rgba(15, 23, 42, 0.45);
            color: #e2e8f0;
            transition: border-color 0.25s ease, transform 0.2s ease, box-shadow 0.25s ease;
        }
        input:focus {
            outline: none;
            border-color: rgba(34, 211, 238, 0.85);
            box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.22);
            transform: translateY(-1px);
        }
        button {
            margin-top: 8px;
            border: 0;
            background: linear-gradient(90deg, var(--accent), var(--accent-2));
            color: white;
            padding: 12px 14px;
            font-size: 0.95rem;
            font-weight: 700;
            border-radius: 10px;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        button:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 22px rgba(14, 165, 233, 0.35);
        }
        .msg-error {
            margin-bottom: 10px;
            padding: 8px 10px;
            border-radius: 8px;
            background: rgba(220, 38, 38, 0.18);
            color: #fecaca;
            border: 1px solid rgba(220, 38, 38, 0.5);
            font-size: 0.92rem;
            font-weight: 600;
        }
        @keyframes riseIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="top">
            <div>
                <h1>Student Performance Predictor</h1>
            </div>
            <div>
                <span class="badge">{{ role|capitalize }} Portal</span>
                <a class="link" href="/logout">Logout</a>
            </div>
        </div>
        {% if error_message %}
        <div class="msg-error">{{ error_message }}</div>
        {% endif %}
        <form method="post" action="/result">
            <div>
                <label for="course">Course</label>
                <input type="text" id="course" name="Course" required placeholder="e.g. B.Tech CSE">
            </div>
            {% if role == 'student' %}
            <div>
                <label for="study-hours">Study Hours per Week</label>
                <input type="number" step="0.1" min="0" max="168" id="study-hours" name="Study Hours per Week" required>
            </div>
            {% endif %}
            <div>
                <label for="attendance">Attendance Rate (%)</label>
                <input type="number" step="0.1" min="0" max="100" id="attendance" name="Attendance Rate" required>
            </div>
            <div>
                <label for="internal-marks">Internal Marks (out of 50)</label>
                <input type="number" step="0.1" min="0" max="50" id="internal-marks" name="Internal Marks" required>
            </div>
            <div>
                <label for="current-semester">Current Semester</label>
                <input type="number" min="2" max="8" step="1" id="current-semester" name="Current Semester" value="6" required>
                <small style="color:#64748b;">Total semesters: 8. Sem 1-2 have 5 papers, Sem 3-8 have 6 papers.</small>
            </div>
            <div>
                <label for="backlogs">Number of Backlogs</label>
                <input type="number" min="0" max="40" step="1" id="backlogs" name="Number of Backlogs" required>
            </div>
            {% if role == 'lecturer' %}
            <div>
                <label for="student-register-number">Student Register Number</label>
                <input
                    type="text"
                    id="student-register-number"
                    name="Student Register Number"
                    required
                    maxlength="11"
                    pattern="AAP23CS(00[2-9]|0[1-2][0-9]|03[0-6])"
                    placeholder="AAP23CS002 to AAP23CS036">
            </div>
            {% endif %}
            <button type="submit">Predict Performance</button>
        </form>
    </div>
</body>
</html>
"""

RESULT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prediction Result</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
        :root {
            --bg: #070b18;
            --panel: rgba(255, 255, 255, 0.08);
            --text: #e2e8f0;
            --muted: #9fb0c9;
            --ok: #15803d;
            --bad: #b91c1c;
            --accent: #0891b2;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            background:
                radial-gradient(circle at 8% 16%, rgba(6, 182, 212, 0.30), transparent 35%),
                radial-gradient(circle at 88% 78%, rgba(14, 165, 233, 0.22), transparent 42%),
                var(--bg);
            color: var(--text);
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
            padding: 18px;
        }
        .wrap {
            max-width: 1080px;
            margin: 0 auto;
            display: grid;
            gap: 14px;
        }
        .panel {
            background: var(--panel);
            border-radius: 14px;
            padding: 16px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            backdrop-filter: blur(16px);
            box-shadow: 0 16px 34px rgba(2, 8, 23, 0.3);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .panel:hover {
            transform: translateY(-2px);
            box-shadow: 0 22px 42px rgba(2, 8, 23, 0.35);
        }
        .grid-4 {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 10px;
        }
        .metric {
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 12px;
            padding: 12px;
            background: rgba(15, 23, 42, 0.4);
        }
        .metric .k { font-size: 0.82rem; color: var(--muted); }
        .metric .v { margin-top: 6px; font-size: 1.2rem; font-weight: 700; }
        .status-pass { color: var(--ok); }
        .status-fail { color: var(--bad); }
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        h1, h2, h3 { margin: 0 0 8px; }
        p { margin: 0; color: var(--muted); }
        ul { margin: 8px 0 0 18px; }
        li { margin-bottom: 6px; }
        .actions {
            background: rgba(15, 23, 42, 0.58);
            border: 1px solid rgba(34, 211, 238, 0.32);
        }
        .actions h2, .actions li { color: #e2e8f0; }
        .action-toggle {
            display: inline-flex;
            gap: 6px;
            background: rgba(15, 23, 42, 0.55);
            border: 1px solid rgba(148, 163, 184, 0.35);
            padding: 6px;
            border-radius: 999px;
            margin-bottom: 10px;
        }
        .toggle-btn {
            border: 0;
            padding: 8px 12px;
            border-radius: 999px;
            background: transparent;
            color: #cbd5e1;
            font-weight: 700;
            cursor: pointer;
            font-size: 0.86rem;
        }
        .toggle-btn.active {
            background: linear-gradient(90deg, #06b6d4, #0ea5e9);
            color: #fff;
            box-shadow: 0 8px 16px rgba(14, 165, 233, 0.28);
        }
        .action-list.hidden {
            display: none;
        }
        .topline {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 10px;
            flex-wrap: wrap;
        }
        .back-btn {
            text-decoration: none;
            color: white;
            background: var(--accent);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .back-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 20px rgba(6, 182, 212, 0.35);
        }
        .export-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .export-btn {
            border: 0;
            padding: 10px 14px;
            border-radius: 10px;
            color: #fff;
            font-weight: 700;
            background: linear-gradient(90deg, #0891b2, #0ea5e9);
            cursor: pointer;
        }
        .insight-panel {
            margin-top: 10px;
            padding: 12px;
            border-radius: 10px;
            border: 1px solid rgba(34, 211, 238, 0.28);
            background: rgba(15, 23, 42, 0.45);
            color: #dbeafe;
            min-height: 68px;
        }
        .insight-title {
            font-weight: 700;
            margin-bottom: 6px;
            color: #67e8f9;
        }
        .touch-insight {
            position: fixed;
            z-index: 9999;
            max-width: 280px;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid rgba(34, 211, 238, 0.55);
            background: rgba(2, 6, 23, 0.92);
            color: #e2e8f0;
            box-shadow: 0 18px 34px rgba(2, 8, 23, 0.45);
            backdrop-filter: blur(10px);
            pointer-events: none;
            transform: translate(-50%, -115%);
            opacity: 0;
            transition: opacity 0.18s ease;
        }
        .touch-insight.show {
            opacity: 1;
        }
        .touch-insight .ti-title {
            font-weight: 700;
            color: #67e8f9;
            margin-bottom: 4px;
            font-size: 0.86rem;
        }
        .touch-insight .ti-body {
            font-size: 0.82rem;
            line-height: 1.35;
        }
        @media print {
            .back-btn, .export-actions, .export-panel-title {
                display: none !important;
            }
            @page {
                size: A4;
                margin: 12mm;
            }
            body {
                background: #fff !important;
                color: #000 !important;
            }
            .panel, .metric {
                box-shadow: none !important;
                border: 1px solid #d1d5db !important;
                background: #fff !important;
            }
            canvas {
                max-height: 240px !important;
            }
        }
        @media (max-width: 900px) {
            .grid-4 { grid-template-columns: 1fr 1fr; }
            .grid-2 { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="panel">
            <div class="topline">
                <div>
                    <h1>Prediction Result</h1>
                    <p>
                        {{ course }} | Role: {{ role|capitalize }} | Current Sem: {{ current_semester }} | Backlogs: {{ backlogs }}
                        {% if student_register_number %}| Reg No: {{ student_register_number }}{% endif %}
                    </p>
                </div>
                <a class="back-btn" href="/">Back To Form</a>
            </div>
        </div>

        <div class="panel grid-4">
            <div class="metric">
                <div class="k">Current Status</div>
                <div class="v {{ 'status-pass' if result == 'Pass' else 'status-fail' }}">{{ result }}</div>
            </div>
            <div class="metric">
                <div class="k">Attendance Rate</div>
                <div class="v">{{ attendance_rate }}%</div>
            </div>
            <div class="metric">
                <div class="k">Internal Marks (50)</div>
                <div class="v">{{ internal_marks }}</div>
            </div>
            <div class="metric">
                <div class="k">Current Total (out of 150)</div>
                <div class="v">{{ current_total }}</div>
            </div>
            <div class="metric">
                <div class="k">Effective Score After Backlog Penalty</div>
                <div class="v">{{ current_effective }}</div>
            </div>
            <div class="metric">
                <div class="k">Current Pass Chance</div>
                <div class="v">{{ current_pass_pct }}%</div>
            </div>
        </div>

        <div class="panel actions">
            <h2>Action Center</h2>
            <div class="action-toggle" role="tablist" aria-label="Action mode">
                <button id="btnEssential" class="toggle-btn active" type="button" onclick="switchActionMode('essential')">Essential Actions</button>
                <button id="btnTailored" class="toggle-btn" type="button" onclick="switchActionMode('tailored')">Tailored Suggestions</button>
            </div>
            <ul id="essentialList" class="action-list">
                {% for item in actions %}
                <li>{{ item }}</li>
                {% endfor %}
            </ul>
            <ul id="tailoredList" class="action-list hidden">
                {% for item in tailored_actions %}
                <li>{{ item }}</li>
                {% endfor %}
            </ul>
        </div>

        <div class="grid-2">
            <div class="panel">
                <h3>Pass vs Fail Chance (Current)</h3>
                <canvas id="pieChance"></canvas>
            </div>
            <div class="panel">
                <h3>Score Composition (Current)</h3>
                <canvas id="pieComposition"></canvas>
            </div>
        </div>

        <div class="panel">
            <h3>Projected Improvement If Actions Are Followed</h3>
            <p>Projection assumes attendance recovery, internal improvement, and backlog reduction by one.</p>
            <canvas id="barImprovement"></canvas>
        </div>

        <div class="grid-2">
            <div class="panel">
                <h3>Current vs Projected Performance (Line Chart)</h3>
                <canvas id="lineOverallPerformance"></canvas>
            </div>
            <div class="panel">
                <h3>Current Semester vs Future Semester (Line Chart)</h3>
                <canvas id="lineSemesterPerformance"></canvas>
            </div>
        </div>

        <div class="panel">
            <h3>Chart Insights</h3>
            <div id="chartInsight" class="insight-panel">
                <div class="insight-title">Tip</div>
                <div>Click on any chart segment, bar, or point to view detailed interpretation.</div>
            </div>
        </div>

        <div class="panel">
            <h3 class="export-panel-title">Export Analysis</h3>
            <div class="export-actions">
                <button class="export-btn" type="button" onclick="downloadAnalysisTxt()">Download TXT</button>
                <button class="export-btn" type="button" onclick="downloadAnalysisPdf()">Download PDF</button>
                <button class="export-btn" type="button" onclick="printResult()">Print Result</button>
            </div>
        </div>
    </div>

    <script>
        const chartData = {{ chart_data | tojson }};
        const exportData = {{ export_data | tojson }};
        const btnEssential = document.getElementById("btnEssential");
        const btnTailored = document.getElementById("btnTailored");
        const essentialList = document.getElementById("essentialList");
        const tailoredList = document.getElementById("tailoredList");
        const chartInsight = document.getElementById("chartInsight");
        const touchInsight = document.createElement("div");
        touchInsight.className = "touch-insight";
        document.body.appendChild(touchInsight);
        let hideTouchInsightTimer = null;

        function setInsight(title, text, chartEvent = null) {
            chartInsight.innerHTML = `
                <div class="insight-title">${title}</div>
                <div>${text}</div>
            `;
            if (chartEvent) {
                showTouchInsight(chartEvent, title, text);
            }
        }

        function showTouchInsight(chartEvent, title, text) {
            const evt = chartEvent?.native || chartEvent;
            const x = evt?.clientX ?? (evt?.x || 0);
            const y = evt?.clientY ?? (evt?.y || 0);
            touchInsight.innerHTML = `
                <div class="ti-title">${title}</div>
                <div class="ti-body">${text}</div>
            `;
            touchInsight.style.left = `${x}px`;
            touchInsight.style.top = `${y}px`;
            touchInsight.classList.add("show");
            if (hideTouchInsightTimer) clearTimeout(hideTouchInsightTimer);
            hideTouchInsightTimer = setTimeout(() => {
                touchInsight.classList.remove("show");
            }, 2200);
        }

        const pieChanceChart = new Chart(document.getElementById("pieChance"), {
            type: "pie",
            data: {
                labels: ["Pass Chance", "Fail Chance"],
                datasets: [{
                    data: [chartData.current_pass_pct, chartData.current_fail_pct],
                    backgroundColor: ["#16a34a", "#dc2626"]
                }]
            },
            options: {
                onClick: (event, elements) => {
                    if (!elements.length) return;
                    const idx = elements[0].index;
                    if (idx === 0) {
                        setInsight(
                            "Pass Probability",
                            `Current pass chance is ${chartData.current_pass_pct}%. Increasing attendance and internals will raise this further.`,
                            event
                        );
                    } else {
                        setInsight(
                            "Fail Probability",
                            `Current fail chance is ${chartData.current_fail_pct}%. Backlog pressure and low internals are common contributors.`,
                            event
                        );
                    }
                }
            }
        });

        const pieCompositionChart = new Chart(document.getElementById("pieComposition"), {
            type: "pie",
            data: {
                labels: ["Internal Marks", "Semester Baseline", "Backlog Penalty"],
                datasets: [{
                    data: [chartData.internal_marks, chartData.semester_baseline, chartData.backlog_penalty],
                    backgroundColor: ["#0ea5e9", "#6366f1", "#f59e0b"]
                }]
            },
            options: {
                onClick: (event, elements) => {
                    if (!elements.length) return;
                    const idx = elements[0].index;
                    if (idx === 0) {
                        setInsight(
                            "Internal Marks Component",
                            `Internal contribution is ${chartData.internal_marks}/50. This is one of the highest-impact controllable components.`,
                            event
                        );
                    } else if (idx === 1) {
                        setInsight(
                            "Semester Baseline",
                            `Semester baseline contribution is ${chartData.semester_baseline}. This is the fixed semester-side input in this model.`,
                            event
                        );
                    } else {
                        setInsight(
                            "Backlog Penalty",
                            `Backlog penalty is ${chartData.backlog_penalty}. Reducing backlogs directly improves effective score.`,
                            event
                        );
                    }
                }
            }
        });

        const barImprovementChart = new Chart(document.getElementById("barImprovement"), {
            type: "bar",
            data: {
                labels: ["Effective Score", "Pass Chance %"],
                datasets: [
                    {
                        label: "Current",
                        data: [chartData.current_effective, chartData.current_pass_pct],
                        backgroundColor: "#60a5fa"
                    },
                    {
                        label: "Projected",
                        data: [chartData.projected_effective, chartData.projected_pass_pct],
                        backgroundColor: "#22c55e"
                    }
                ]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        suggestedMax: 120
                    }
                },
                onClick: (event, elements) => {
                    if (!elements.length) return;
                    const ds = elements[0].datasetIndex;
                    const i = elements[0].index;
                    const label = i === 0 ? "Effective Score" : "Pass Chance";
                    const value = ds === 0
                        ? (i === 0 ? chartData.current_effective : chartData.current_pass_pct)
                        : (i === 0 ? chartData.projected_effective : chartData.projected_pass_pct);
                    const phase = ds === 0 ? "Current" : "Projected";
                    setInsight(
                        `${phase} ${label}`,
                        `${phase} ${label} is ${value}. Compare both bars to understand expected improvement after action compliance.`,
                        event
                    );
                }
            }
        });

        const lineOverallPerformanceChart = new Chart(document.getElementById("lineOverallPerformance"), {
            type: "line",
            data: {
                labels: ["Current", "Projected"],
                datasets: [{
                    label: "Effective Performance",
                    data: [chartData.current_effective, chartData.projected_effective],
                    borderColor: "#0ea5e9",
                    backgroundColor: "rgba(14, 165, 233, 0.2)",
                    tension: 0.3,
                    fill: true
                }]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        suggestedMax: 150
                    }
                },
                onClick: (event, elements) => {
                    if (!elements.length) return;
                    const idx = elements[0].index;
                    if (idx === 0) {
                        setInsight(
                            "Current Effective Performance",
                            `Current effective score is ${chartData.current_effective}. This reflects present conditions including backlog effect.`,
                            event
                        );
                    } else {
                        setInsight(
                            "Projected Effective Performance",
                            `Projected effective score is ${chartData.projected_effective}. This assumes recommended actions are followed.`,
                            event
                        );
                    }
                }
            }
        });

        const lineSemesterPerformanceChart = new Chart(document.getElementById("lineSemesterPerformance"), {
            type: "line",
            data: {
                labels: ["Current Semester", "Future Semester"],
                datasets: [{
                    label: "Semester Performance",
                    data: [chartData.current_total, chartData.projected_total],
                    borderColor: "#22c55e",
                    backgroundColor: "rgba(34, 197, 94, 0.2)",
                    tension: 0.3,
                    fill: true
                }]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        suggestedMax: 150
                    }
                },
                onClick: (event, elements) => {
                    if (!elements.length) return;
                    const idx = elements[0].index;
                    if (idx === 0) {
                        setInsight(
                            "Current Semester Performance",
                            `Current semester total is ${chartData.current_total}. This is your present semester-side performance baseline.`,
                            event
                        );
                    } else {
                        setInsight(
                            "Future Semester Projection",
                            `Future semester projection is ${chartData.projected_total}. Improvement mainly depends on internals and reduced backlog pressure.`,
                            event
                        );
                    }
                }
            }
        });

        function buildAnalysisText() {
            return [
                "Student Performance Analysis",
                "============================",
                `Course: ${exportData.course}`,
                `Role: ${exportData.role}`,
                `Current Semester: ${exportData.current_semester}`,
                `Backlogs: ${exportData.backlogs}`,
                exportData.student_register_number ? `Register Number: ${exportData.student_register_number}` : "",
                "",
                `Attendance Rate: ${exportData.attendance_rate}%`,
                `Internal Marks (50): ${exportData.internal_marks}`,
                `Current Status: ${exportData.result}`,
                `Current Total (150): ${exportData.current_total}`,
                `Effective Score: ${exportData.current_effective}`,
                `Pass Chance (%): ${exportData.current_pass_pct}`,
                "",
                "Necessary Actions:",
                ...exportData.actions.map((x, i) => `${i + 1}. ${x}`)
            ].filter(Boolean).join("\\n");
        }

        function downloadAnalysisTxt() {
            const content = buildAnalysisText();
            const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "student_performance_analysis.txt";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        function downloadAnalysisPdf() {
            const { jsPDF } = window.jspdf;
            const doc = new jsPDF({ unit: "pt", format: "a4" });
            const text = buildAnalysisText();
            const lines = doc.splitTextToSize(text, 520);
            doc.setFont("helvetica", "normal");
            doc.setFontSize(12);
            doc.text(lines, 40, 50);
            doc.save("student_performance_analysis.pdf");
        }

        function printResult() {
            const w = window.open("", "_blank", "width=900,height=1000");
            if (!w) {
                alert("Popup blocked. Please allow popups for printing.");
                return;
            }

            const actionsHtml = exportData.actions
                .map((a, i) => `<li>${i + 1}. ${a}</li>`)
                .join("");
            const tailoredHtml = (exportData.tailored_actions || [])
                .map((a, i) => `<li>${i + 1}. ${a}</li>`)
                .join("");

            const html = `
                <!doctype html>
                <html>
                <head>
                    <meta charset="utf-8" />
                    <title>Student Performance Analysis</title>
                    <style>
                        @page { size: A4; margin: 14mm; }
                        body { font-family: Arial, sans-serif; color: #111; }
                        h1 { margin: 0 0 10px; font-size: 22px; }
                        h2 { margin: 14px 0 8px; font-size: 16px; }
                        p { margin: 4px 0; }
                        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 20px; margin-top: 10px; }
                        .box { border: 1px solid #ddd; border-radius: 8px; padding: 10px; }
                        ul { margin: 6px 0 0 18px; }
                        li { margin: 4px 0; }
                        .muted { color: #555; }
                    </style>
                </head>
                <body>
                    <h1>Student Performance Analysis</h1>
                    <p><b>Course:</b> ${exportData.course}</p>
                    <p><b>Role:</b> ${exportData.role}</p>
                    <p><b>Current Semester:</b> ${exportData.current_semester}</p>
                    <p><b>Backlogs:</b> ${exportData.backlogs}</p>
                    ${exportData.student_register_number ? `<p><b>Register Number:</b> ${exportData.student_register_number}</p>` : ""}
                    <div class="grid">
                        <div class="box"><b>Status</b><p>${exportData.result}</p></div>
                        <div class="box"><b>Pass Chance</b><p>${exportData.current_pass_pct}%</p></div>
                        <div class="box"><b>Attendance</b><p>${exportData.attendance_rate}%</p></div>
                        <div class="box"><b>Internal Marks (50)</b><p>${exportData.internal_marks}</p></div>
                        <div class="box"><b>Current Total (150)</b><p>${exportData.current_total}</p></div>
                        <div class="box"><b>Effective Score</b><p>${exportData.current_effective}</p></div>
                    </div>
                    <h2>Essential Actions</h2>
                    <ul>${actionsHtml}</ul>
                    <h2>Tailored Suggestions</h2>
                    <ul>${tailoredHtml || "<li>No additional tailored suggestion.</li>"}</ul>
                    <p class="muted">Generated by Student Performance Predictor</p>
                </body>
                </html>
            `;

            w.document.open();
            w.document.write(html);
            w.document.close();
            w.focus();
            setTimeout(() => {
                w.print();
                w.close();
            }, 250);
        }

        function switchActionMode(mode) {
            const essential = mode === "essential";
            essentialList.classList.toggle("hidden", !essential);
            tailoredList.classList.toggle("hidden", essential);
            btnEssential.classList.toggle("active", essential);
            btnTailored.classList.toggle("active", !essential);
        }
    </script>
</body>
</html>
"""


def _safe_float(raw_value, min_value, max_value):
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = min_value
    return max(min_value, min(value, max_value))


def _safe_int(raw_value, min_value, max_value):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = min_value
    return max(min_value, min(value, max_value))


def _generate_temp_password(length=10):
    charset = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(random.choice(charset) for _ in range(length))


def _max_backlogs_before_semester(current_semester):
    current_semester = max(1, min(8, int(current_semester)))
    # Cumulative papers up to and including current semester.
    return sum(SEMESTER_PAPER_COUNTS[s] for s in range(1, current_semester + 1))


def _backlog_penalty(backlogs, current_semester):
    # Normalize backlog pressure based on papers available before current semester.
    max_backlogs = _max_backlogs_before_semester(current_semester)
    if max_backlogs <= 0:
        return 0.0
    severity = min(max(backlogs, 0) / max_backlogs, 1.0)
    return round(BACKLOG_PENALTY_CAP * severity, 1)


def _backlog_risk_factor(backlogs, current_semester):
    max_backlogs = _max_backlogs_before_semester(current_semester)
    if max_backlogs <= 0:
        return 0.0
    return min(max(backlogs, 0) / max_backlogs, 1.0)


def _get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _get_db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL CHECK(role IN ('student', 'lecturer')),
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                student_register_number TEXT UNIQUE,
                created_at INTEGER NOT NULL,
                UNIQUE(role, username)
            )
            """
        )


def _normalize_email(raw_email):
    email = (raw_email or "").strip().lower()
    # Restrict to Gmail based on current project requirement.
    if re.fullmatch(r"[a-zA-Z0-9._%+-]+@gmail\.com", email):
        return email
    return None


def _is_valid_student_registration_number(reg_no):
    if not reg_no:
        return False
    return bool(STUDENT_ACCOUNT_REG_PATTERN.fullmatch(reg_no.strip().upper()))


def _send_otp(email, otp):
    if OTP_PROVIDER in {"console", "demo"}:
        print(f"[OTP] Sending to {email}: {otp}")
        return True, "OTP generated in demo mode."

    missing = []
    if not GMAIL_OTP_SENDER:
        missing.append("GMAIL_OTP_SENDER")
    if not GMAIL_APP_PASSWORD:
        missing.append("GMAIL_APP_PASSWORD")
    if missing:
        return False, "OTP service not configured. Missing: " + ", ".join(missing)

    if OTP_PROVIDER not in {"gmail", "email"}:
        return False, "Unsupported OTP_PROVIDER. Use 'gmail' or 'console'."

    message = EmailMessage()
    message["Subject"] = "Your OTP for Student Performance Portal"
    message["From"] = GMAIL_OTP_SENDER
    message["To"] = email
    message.set_content(f"Your OTP is {otp}. It is valid for 5 minutes.")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(GMAIL_OTP_SENDER, GMAIL_APP_PASSWORD)
            smtp.send_message(message)
        return True, "OTP sent successfully to your Gmail."
    except Exception as exc:
        print(f"[OTP][GMAIL][Error] {exc}")
        return False, "Failed to send OTP email. Check Gmail/app-password settings."


def _send_email(email, subject, body):
    if OTP_PROVIDER in {"console", "demo"}:
        print(f"[EMAIL] To {email} | Subject: {subject}\n{body}")
        return True, "Email generated in demo mode."

    missing = []
    if not GMAIL_OTP_SENDER:
        missing.append("GMAIL_OTP_SENDER")
    if not GMAIL_APP_PASSWORD:
        missing.append("GMAIL_APP_PASSWORD")
    if missing:
        return False, "Email service not configured. Missing: " + ", ".join(missing)

    if OTP_PROVIDER not in {"gmail", "email"}:
        return False, "Unsupported OTP_PROVIDER. Use 'gmail' or 'console'."

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = GMAIL_OTP_SENDER
    message["To"] = email
    message.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(GMAIL_OTP_SENDER, GMAIL_APP_PASSWORD)
            smtp.send_message(message)
        return True, "Email sent successfully."
    except Exception as exc:
        print(f"[EMAIL][GMAIL][Error] {exc}")
        return False, "Failed to send email. Check Gmail/app-password settings."


def _pass_probability(
    internal_marks, attendance, study_hours, backlogs, current_semester, effective_score
):
    prob = 0.40
    prob += 0.27 * (internal_marks / 50.0)
    prob += 0.16 * (attendance / 100.0)
    prob += 0.04 * (min(study_hours, 20.0) / 20.0)  # Kept intentionally low.
    # Backlogs should matter, but not dominate the outcome.
    prob -= 0.18 * _backlog_risk_factor(backlogs, current_semester)
    prob += 0.13 * ((effective_score - PASS_MARK) / PASS_MARK)
    prob = max(0.01, min(0.99, prob))
    return round(prob * 100.0, 1)


def _actions(role, study_hours, attendance, internal_marks, backlogs, current_semester):
    recommendations = []
    if role == "student":
        if study_hours < 14:
            recommendations.append(
                "Increase weekly study hours to at least 14 with a fixed timetable."
            )
    else:
        recommendations.append(
            "Track student study hours weekly; even small gains can improve consistency."
        )
    if attendance < 85:
        recommendations.append("Raise attendance to 85%+ by prioritizing core and lab classes.")
    if internal_marks < 35:
        recommendations.append("Target internals above 35/50 through weekly unit-test practice.")
    if backlogs > 0:
        recommendations.append("Create a backlog-clearing plan: oldest backlog first, one subject at a time.")
        recommendations.append(
            "Note: Backlogs are typically cleared in semester exams, so treat this as a planning risk for upcoming semesters rather than an immediate current-semester mark change."
        )
        max_b = _max_backlogs_before_semester(current_semester)
        recommendations.append(
            f"Current backlog pressure: {backlogs}/{max_b} based on completed semesters."
        )
    recommendations.append("Take one mock test every week and track weak topics in a revision sheet.")
    return recommendations


def _tailored_actions(
    role,
    study_hours,
    attendance,
    internal_marks,
    backlogs,
    current_semester,
    current_pass_pct,
):
    suggestions = []

    # 1) Attendance weakness
    if attendance < 75:
        gap = round(75 - attendance, 1)
        suggestions.append(
            f"Attendance is {attendance:.1f}%. Recover about {gap:.1f}% to reach safer zone (>=75%). Focus on high-impact classes first."
        )
    elif attendance < 85:
        gap = round(85 - attendance, 1)
        suggestions.append(
            f"Attendance is acceptable but not strong ({attendance:.1f}%). Closing ~{gap:.1f}% gap can noticeably improve stability."
        )

    # 2) Internal marks weakness
    if internal_marks < 25:
        suggestions.append(
            f"Internal marks are low ({internal_marks:.1f}/50). Prioritize weekly tests and assignment quality to cross 30+ quickly."
        )
    elif internal_marks < 35:
        suggestions.append(
            f"Internal marks are moderate ({internal_marks:.1f}/50). A +5 to +8 improvement can significantly raise pass confidence."
        )

    # 3) Study-hours weakness (role-aware)
    if role == "student":
        if study_hours < 8:
            suggestions.append(
                f"Study time is limited ({study_hours:.1f} hrs/week). Move to at least 10-12 hrs/week with 45-minute focused blocks."
            )
        elif study_hours < 14:
            suggestions.append(
                f"Study pattern is okay ({study_hours:.1f} hrs/week) but below ideal. Add 3-4 focused hours for revision and backlog subjects."
            )
    else:
        suggestions.append(
            "As lecturer view: assign topic-level micro targets for each student and monitor weekly completion instead of only monthly tests."
        )

    # 4) Backlog pressure, semester-normalized
    max_b = _max_backlogs_before_semester(current_semester)
    pressure = 0 if max_b == 0 else backlogs / max_b
    if backlogs > 0:
        if pressure >= 0.40:
            suggestions.append(
                f"Backlog pressure is high ({backlogs}/{max_b}). Use a strict clearance sequence: highest carry-forward impact papers first."
            )
        elif pressure >= 0.20:
            suggestions.append(
                f"Backlog pressure is moderate ({backlogs}/{max_b}). Reserve fixed weekly slots only for backlog topics to prevent spillover."
            )
        else:
            suggestions.append(
                f"Backlog pressure is manageable ({backlogs}/{max_b}). Maintain continuity to avoid conversion into critical risk."
            )

    # 5) Overall risk-tailored message
    if current_pass_pct < 55:
        suggestions.append(
            f"Current pass confidence is low ({current_pass_pct:.1f}%). Apply a short 2-week corrective plan with daily check-ins."
        )
    elif current_pass_pct < 75:
        suggestions.append(
            f"Current pass confidence is moderate ({current_pass_pct:.1f}%). Consistency in attendance + internals can move this to high-confidence range."
        )
    else:
        suggestions.append(
            f"Current pass confidence is strong ({current_pass_pct:.1f}%). Focus on sustaining momentum and reducing avoidable backlog risk."
        )

    return suggestions


def _is_logged_in():
    return "username" in session and "role" in session


def _valid_lecturer_register_number(register_number):
    if not register_number:
        return False
    return bool(LECTURER_REG_PATTERN.fullmatch(register_number.strip().upper()))


_init_db()


@app.route("/auth", methods=["GET"])
def auth_page():
    if _is_logged_in():
        return redirect(url_for("index"))
    return render_template_string(AUTH_TEMPLATE, message=None, message_type="error")


@app.route("/register", methods=["POST"])
def register():
    role = request.form.get("role", "").strip().lower()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    email = _normalize_email(request.form.get("email", ""))
    student_register_number = request.form.get("student_register_number", "").strip().upper()

    if role not in {"student", "lecturer"} or not username or not password or not email:
        return render_template_string(
            AUTH_TEMPLATE,
            message="Invalid registration details. Use a valid Gmail address.",
            message_type="error",
        )

    if role == "student":
        if not _is_valid_student_registration_number(student_register_number):
            return render_template_string(
                AUTH_TEMPLATE,
                message="Enter a valid student register number: AAP23CS002 to AAP23CS036.",
                message_type="error",
            )
    else:
        student_register_number = None

    with _get_db_conn() as conn:
        duplicate = conn.execute(
            """
            SELECT 1 FROM users
            WHERE (role = ? AND username = ?)
               OR phone = ?
               OR (? IS NOT NULL AND student_register_number = ?)
            LIMIT 1
            """,
            (role, username, email, student_register_number, student_register_number),
        ).fetchone()
    if duplicate:
        return render_template_string(
            AUTH_TEMPLATE,
            message="Duplicate details found. Username/Gmail/register number must be unique.",
            message_type="error",
        )

    otp = f"{random.randint(0, 999999):06d}"
    sent, send_message = _send_otp(email, otp)
    if not sent:
        return render_template_string(
            AUTH_TEMPLATE,
            message=send_message,
            message_type="error",
        )
    session["pending_registration"] = {
        "role": role,
        "username": username,
        "password_hash": generate_password_hash(password),
        "phone": email,
        "student_register_number": student_register_number,
        "otp": otp,
        "expires_at": int(time.time()) + 300,
    }
    return render_template_string(
        OTP_TEMPLATE,
        email=email,
        message=send_message,
        message_type="ok",
    )


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template_string(
            FORGOT_PASSWORD_TEMPLATE, message=None, message_type="error"
        )

    role = request.form.get("role", "").strip().lower()
    username = request.form.get("username", "").strip()
    email = _normalize_email(request.form.get("email", ""))

    if role not in {"student", "lecturer"} or not username or not email:
        return render_template_string(
            FORGOT_PASSWORD_TEMPLATE,
            message="Invalid details. Please enter role, username, and valid Gmail.",
            message_type="error",
        )

    with _get_db_conn() as conn:
        user = conn.execute(
            """
            SELECT id FROM users
            WHERE role = ? AND username = ? AND phone = ?
            LIMIT 1
            """,
            (role, username, email),
        ).fetchone()

    if not user:
        return render_template_string(
            FORGOT_PASSWORD_TEMPLATE,
            message="No account found with the provided details.",
            message_type="error",
        )

    temp_password = _generate_temp_password()
    sent, msg = _send_email(
        email,
        "Temporary Password - Student Performance Portal",
        (
            "Your temporary password is: "
            f"{temp_password}\n\n"
            "Please login and change it after sign-in."
        ),
    )
    if not sent:
        return render_template_string(
            FORGOT_PASSWORD_TEMPLATE, message=msg, message_type="error"
        )

    with _get_db_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(temp_password), int(user["id"])),
        )

    return render_template_string(
        FORGOT_PASSWORD_TEMPLATE,
        message="Temporary password sent to your Gmail.",
        message_type="ok",
    )


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "GET":
        return render_template_string(
            RESET_PASSWORD_TEMPLATE, message=None, message_type="error"
        )

    role = request.form.get("role", "").strip().lower()
    username = request.form.get("username", "").strip()
    email = _normalize_email(request.form.get("email", ""))
    temp_password = request.form.get("temp_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if role not in {"student", "lecturer"} or not username or not email:
        return render_template_string(
            RESET_PASSWORD_TEMPLATE,
            message="Invalid details. Provide role, username, and valid Gmail.",
            message_type="error",
        )
    if not temp_password or not new_password:
        return render_template_string(
            RESET_PASSWORD_TEMPLATE,
            message="Temporary password and new password are required.",
            message_type="error",
        )
    if len(new_password) < 6:
        return render_template_string(
            RESET_PASSWORD_TEMPLATE,
            message="New password must be at least 6 characters.",
            message_type="error",
        )
    if new_password != confirm_password:
        return render_template_string(
            RESET_PASSWORD_TEMPLATE,
            message="New password and confirm password do not match.",
            message_type="error",
        )

    with _get_db_conn() as conn:
        user = conn.execute(
            """
            SELECT id, password_hash FROM users
            WHERE role = ? AND username = ? AND phone = ?
            LIMIT 1
            """,
            (role, username, email),
        ).fetchone()
    if not user:
        return render_template_string(
            RESET_PASSWORD_TEMPLATE,
            message="No account found with the provided details.",
            message_type="error",
        )
    if not check_password_hash(user["password_hash"], temp_password):
        return render_template_string(
            RESET_PASSWORD_TEMPLATE,
            message="Temporary password is incorrect.",
            message_type="error",
        )

    with _get_db_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), int(user["id"])),
        )

    return render_template_string(
        RESET_PASSWORD_TEMPLATE,
        message="Password updated successfully. You can now login with your new password.",
        message_type="ok",
    )


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    pending = session.get("pending_registration")
    if not pending:
        return redirect(url_for("auth_page"))

    if request.method == "GET":
        return render_template_string(
            OTP_TEMPLATE, email=pending["phone"], message=None, message_type="error"
        )

    user_otp = request.form.get("otp", "").strip()
    if int(time.time()) > int(pending.get("expires_at", 0)):
        session.pop("pending_registration", None)
        return render_template_string(
            AUTH_TEMPLATE,
            message="OTP expired. Please register again.",
            message_type="error",
        )

    if user_otp != pending.get("otp"):
        return render_template_string(
            OTP_TEMPLATE,
            email=pending["phone"],
            message="Invalid OTP. Please try again.",
            message_type="error",
        )

    try:
        with _get_db_conn() as conn:
            conn.execute(
                """
                INSERT INTO users(role, username, password_hash, phone, student_register_number, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    pending["role"],
                    pending["username"],
                    pending["password_hash"],
                    pending["phone"],
                    pending["student_register_number"],
                    int(time.time()),
                ),
            )
    except sqlite3.IntegrityError:
        session.pop("pending_registration", None)
        return render_template_string(
            AUTH_TEMPLATE,
            message="Registration failed due to duplicate data. Try with unique details.",
            message_type="error",
        )

    session.pop("pending_registration", None)
    return render_template_string(
        AUTH_TEMPLATE,
        message="Registration completed. You can login now.",
        message_type="ok",
    )


@app.route("/login", methods=["POST"])
def login():
    role = request.form.get("role", "").strip().lower()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if role not in {"student", "lecturer"} or not username or not password:
        return render_template_string(
            AUTH_TEMPLATE,
            message="Invalid credentials.",
            message_type="error",
        )

    with _get_db_conn() as conn:
        user = conn.execute(
            "SELECT id, role, username, password_hash FROM users WHERE role = ? AND username = ? LIMIT 1",
            (role, username),
        ).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template_string(
            AUTH_TEMPLATE,
            message="Invalid credentials.",
            message_type="error",
        )
    session["role"] = role
    session["username"] = username
    session["user_id"] = int(user["id"])
    return redirect(url_for("index"))


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect(url_for("auth_page"))


@app.route("/", methods=["GET"])
def index():
    if not _is_logged_in():
        return redirect(url_for("auth_page"))
    return render_template_string(FORM_TEMPLATE, role=session["role"], error_message=None)


@app.route("/result", methods=["POST"])
def result():
    if not _is_logged_in():
        return redirect(url_for("auth_page"))

    role = session["role"]
    course = request.form.get("Course", "B.Tech")
    attendance = _safe_float(request.form.get("Attendance Rate"), 0.0, 100.0)
    internal_marks = _safe_float(request.form.get("Internal Marks"), 0.0, 50.0)
    current_semester = _safe_int(request.form.get("Current Semester"), 2, 8)
    backlogs = _safe_int(request.form.get("Number of Backlogs"), 0, 40)
    max_allowed_backlogs = _max_backlogs_before_semester(current_semester)
    if current_semester <= 1:
        return render_template_string(
            FORM_TEMPLATE,
            role=role,
            error_message="Current semester must be between 2 and 8.",
        )
    if backlogs > max_allowed_backlogs:
        return render_template_string(
            FORM_TEMPLATE,
            role=role,
            error_message=(
                f"Backlogs cannot exceed {max_allowed_backlogs} cumulatively up to semester {current_semester}."
            ),
        )

    if role == "student":
        study_hours = _safe_float(request.form.get("Study Hours per Week"), 0.0, 168.0)
        student_register_number = None
    else:
        # Lecturer view has no study-hours input. Use neutral baseline.
        study_hours = 8.0
        student_register_number = request.form.get("Student Register Number", "").strip().upper()
        if not _valid_lecturer_register_number(student_register_number):
            return render_template_string(
                FORM_TEMPLATE,
                role=role,
                error_message="Enter a valid register number: AAP23CS002 to AAP23CS036.",
            )

    current_total = round(internal_marks + BASE_SEMESTER_MARKS, 1)
    backlog_penalty = _backlog_penalty(backlogs, current_semester)
    current_effective = round(current_total - backlog_penalty, 1)
    current_pass_pct = _pass_probability(
        internal_marks, attendance, study_hours, backlogs, current_semester, current_effective
    )
    current_fail_pct = round(100.0 - current_pass_pct, 1)
    current_result = "Pass" if current_effective >= PASS_MARK else "Fail"

    projected_study = max(study_hours, 14.0)
    projected_attendance = max(attendance, 85.0)
    projected_internal = min(50.0, internal_marks + 8.0)
    projected_backlogs = max(0, backlogs - 1)
    projected_total = round(projected_internal + BASE_SEMESTER_MARKS, 1)
    projected_penalty = _backlog_penalty(projected_backlogs, current_semester)
    projected_effective = round(projected_total - projected_penalty, 1)
    projected_pass_pct = _pass_probability(
        projected_internal,
        projected_attendance,
        projected_study,
        projected_backlogs,
        current_semester,
        projected_effective,
    )

    chart_data = {
        "internal_marks": round(internal_marks, 1),
        "semester_baseline": BASE_SEMESTER_MARKS,
        "backlog_penalty": backlog_penalty,
        "current_total": current_total,
        "projected_total": projected_total,
        "current_effective": current_effective,
        "projected_effective": projected_effective,
        "current_pass_pct": current_pass_pct,
        "current_fail_pct": current_fail_pct,
        "projected_pass_pct": projected_pass_pct,
    }
    actions_list = _actions(
        role, study_hours, attendance, internal_marks, backlogs, current_semester
    )
    tailored_actions_list = _tailored_actions(
        role,
        study_hours,
        attendance,
        internal_marks,
        backlogs,
        current_semester,
        current_pass_pct,
    )
    export_data = {
        "course": course,
        "role": role,
        "current_semester": current_semester,
        "backlogs": backlogs,
        "student_register_number": student_register_number,
        "attendance_rate": round(attendance, 1),
        "internal_marks": round(internal_marks, 1),
        "result": current_result,
        "current_total": current_total,
        "current_effective": current_effective,
        "current_pass_pct": current_pass_pct,
        "actions": actions_list,
        "tailored_actions": tailored_actions_list,
    }

    return render_template_string(
        RESULT_TEMPLATE,
        role=role,
        course=course,
        current_semester=current_semester,
        backlogs=backlogs,
        attendance_rate=round(attendance, 1),
        internal_marks=round(internal_marks, 1),
        student_register_number=student_register_number,
        result=current_result,
        current_total=current_total,
        current_effective=current_effective,
        current_pass_pct=current_pass_pct,
        actions=actions_list,
        tailored_actions=tailored_actions_list,
        chart_data=chart_data,
        export_data=export_data,
    )


if __name__ == "__main__":
    app.run(debug=True)
