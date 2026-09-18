"""
Dynamic QR Attendance Tracker
=============================
A lightweight Flask application for classroom attendance using rotating QR codes.
"""

import csv
import io
import os
import secrets
import sqlite3
import base64
from datetime import datetime, timedelta, timezone

import qrcode
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = secrets.token_hex(32)

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "attendance.db")
QR_TOKEN_LIFETIME_SECONDS = 10  # configurable: how long each QR token is valid

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Return a database connection with row-factory enabled."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they do not exist."""
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id          TEXT PRIMARY KEY,
            class_section TEXT NOT NULL,
            subject     TEXT NOT NULL,
            topic       TEXT DEFAULT '',
            started_at  TEXT NOT NULL,
            ended_at    TEXT,
            status      TEXT NOT NULL DEFAULT 'ACTIVE'
        );

        CREATE TABLE IF NOT EXISTS qr_tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            token       TEXT NOT NULL UNIQUE,
            created_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES attendance_sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_qr_tokens_token ON qr_tokens(token);
        CREATE INDEX IF NOT EXISTS idx_qr_tokens_session ON qr_tokens(session_id);

        CREATE TABLE IF NOT EXISTS attendance (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            name            TEXT NOT NULL,
            roll_number     TEXT NOT NULL,
            class_section   TEXT NOT NULL,
            student_id      TEXT NOT NULL,
            email           TEXT DEFAULT '',
            marked_at       TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'PRESENT',
            FOREIGN KEY (session_id) REFERENCES attendance_sessions(id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_unique
            ON attendance(session_id, student_id);
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def generate_session_id():
    """Generate a short, human-readable session identifier."""
    return "SES-" + secrets.token_hex(4).upper()


def generate_token():
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(32)


def utcnow():
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def utcnow_dt():
    """Return current UTC datetime object."""
    return datetime.now(timezone.utc)


def create_qr_token(conn, session_id):
    """Create a new QR token for the given session and return the row."""
    token = generate_token()
    now = utcnow_dt()
    expires = now + timedelta(seconds=QR_TOKEN_LIFETIME_SECONDS)
    conn.execute(
        "INSERT INTO qr_tokens (session_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (session_id, token, now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    return {
        "token": token,
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "lifetime": QR_TOKEN_LIFETIME_SECONDS,
    }


def make_qr_data_uri(data_string):
    """Generate a QR code image and return it as a base64 data-URI."""
    img = qrcode.make(data_string, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Redirect to teacher dashboard."""
    return redirect(url_for("admin_page"))


@app.route("/admin")
def admin_page():
    """Render the teacher / admin dashboard."""
    return render_template("admin.html")


@app.route("/attendance/<token>")
def student_page(token):
    """
    Render the student attendance form.

    Validates the token. If the token was valid when the student scanned,
    we issue a short-lived 'form_ticket' so the student can still submit
    even if the QR rotates while they are filling in the form.
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM qr_tokens WHERE token = ?", (token,)).fetchone()

    if row is None:
        conn.close()
        return render_template("error.html", title="Invalid QR Code",
                               message="This QR code is not associated with an active attendance session.")

    # Check if token has expired
    expires_at = datetime.fromisoformat(row["expires_at"])
    now = utcnow_dt()
    if now > expires_at:
        conn.close()
        return render_template("error.html", title="QR Code Expired",
                               message="This QR code has expired. Please scan the currently displayed QR code.")

    # Check if session is active
    session = conn.execute("SELECT * FROM attendance_sessions WHERE id = ?", (row["session_id"],)).fetchone()
    if session is None or session["status"] != "ACTIVE":
        conn.close()
        return render_template("error.html", title="Attendance Closed",
                               message="This attendance session is no longer accepting responses.")

    # Token is valid — issue a form_ticket so the student can submit
    # even after QR rotates. The form_ticket is just the token they used;
    # the backend will accept it during submission validation.
    conn.close()
    return render_template("student.html",
                           session_id=row["session_id"],
                           token=token,
                           class_section=session["class_section"],
                           subject=session["subject"])


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

# ── Session management ────────────────────────────────────────────────────

@app.route("/api/sessions/start", methods=["POST"])
def start_session():
    """Create a new attendance session and return the first QR token."""
    data = request.get_json(force=True)
    class_section = data.get("class_section", "").strip()
    subject = data.get("subject", "").strip()
    topic = data.get("topic", "").strip()

    if not class_section or not subject:
        return jsonify({"error": "class_section and subject are required"}), 400

    session_id = generate_session_id()
    conn = get_db()
    conn.execute(
        "INSERT INTO attendance_sessions (id, class_section, subject, topic, started_at, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
        (session_id, class_section, subject, topic, utcnow()),
    )
    token_info = create_qr_token(conn, session_id)
    conn.close()

    # Build QR URL
    base_url = request.host_url.rstrip("/")
    qr_url = f"{base_url}/attendance/{token_info['token']}"
    qr_data_uri = make_qr_data_uri(qr_url)

    return jsonify({
        "session_id": session_id,
        "class_section": class_section,
        "subject": subject,
        "topic": topic,
        "token": token_info,
        "qr_url": qr_url,
        "qr_image": qr_data_uri,
    })


@app.route("/api/sessions/<session_id>/stop", methods=["POST"])
def stop_session(session_id):
    """Stop an active attendance session."""
    conn = get_db()
    session = conn.execute("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        conn.close()
        return jsonify({"error": "Session not found"}), 404
    if session["status"] != "ACTIVE":
        conn.close()
        return jsonify({"error": "Session is not active"}), 400

    conn.execute(
        "UPDATE attendance_sessions SET status = 'CLOSED', ended_at = ? WHERE id = ?",
        (utcnow(), session_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Session stopped", "session_id": session_id})


# ── QR token rotation ────────────────────────────────────────────────────

@app.route("/api/sessions/<session_id>/current-token", methods=["GET"])
def current_token(session_id):
    """Return a fresh QR token for the active session."""
    conn = get_db()
    session = conn.execute("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        conn.close()
        return jsonify({"error": "Session not found"}), 404
    if session["status"] != "ACTIVE":
        conn.close()
        return jsonify({"error": "Session is no longer active"}), 400

    token_info = create_qr_token(conn, session_id)
    conn.close()

    base_url = request.host_url.rstrip("/")
    qr_url = f"{base_url}/attendance/{token_info['token']}"
    qr_data_uri = make_qr_data_uri(qr_url)

    return jsonify({
        "token": token_info,
        "qr_url": qr_url,
        "qr_image": qr_data_uri,
    })


# ── Attendance marking ───────────────────────────────────────────────────

@app.route("/api/attendance/mark", methods=["POST"])
def mark_attendance():
    """Mark a student's attendance for a given session."""
    data = request.get_json(force=True)

    session_id = data.get("session_id", "").strip()
    token = data.get("token", "").strip()
    name = data.get("name", "").strip()
    roll_number = data.get("roll_number", "").strip()
    class_section = data.get("class_section", "").strip()
    student_id = data.get("student_id", "").strip()
    email = data.get("email", "").strip()

    # --- basic validation ---
    if not all([session_id, token, name, roll_number, class_section, student_id]):
        return jsonify({"error": "All required fields must be filled."}), 400

    conn = get_db()

    # 1. Session exists?
    session = conn.execute("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        conn.close()
        return jsonify({"error": "Attendance session not found."}), 404

    # 2. Session active?
    if session["status"] != "ACTIVE":
        conn.close()
        return jsonify({"error": "This attendance session is no longer accepting responses."}), 400

    # 3. Token belongs to session?
    token_row = conn.execute(
        "SELECT * FROM qr_tokens WHERE token = ? AND session_id = ?", (token, session_id)
    ).fetchone()
    if token_row is None:
        conn.close()
        return jsonify({"error": "Invalid QR token for this session."}), 400

    # 4. We do NOT re-check token expiry here — see spec §3.
    #    The student obtained access while the token was valid; their
    #    form submission should still be accepted.

    # 5. Duplicate check
    existing = conn.execute(
        "SELECT id FROM attendance WHERE session_id = ? AND student_id = ?",
        (session_id, student_id),
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({
            "error": "Attendance Already Marked",
            "detail": "Your attendance has already been recorded for this class session.",
        }), 409

    # Mark attendance
    marked_at = utcnow()
    try:
        conn.execute(
            """INSERT INTO attendance
                (session_id, name, roll_number, class_section, student_id, email, marked_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PRESENT')""",
            (session_id, name, roll_number, class_section, student_id, email, marked_at),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({
            "error": "Attendance Already Marked",
            "detail": "Your attendance has already been recorded for this class session.",
        }), 409

    conn.close()
    return jsonify({
        "message": "Attendance marked successfully!",
        "name": name,
        "roll_number": roll_number,
        "class_section": class_section,
        "student_id": student_id,
        "subject": session["subject"],
        "session_id": session_id,
        "marked_at": marked_at,
        "status": "PRESENT",
    })


# ── Attendance list & export ─────────────────────────────────────────────

@app.route("/api/sessions/<session_id>/attendance", methods=["GET"])
def get_attendance(session_id):
    """Return the list of marked attendances for a session."""
    conn = get_db()
    session = conn.execute("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        conn.close()
        return jsonify({"error": "Session not found"}), 404

    rows = conn.execute(
        "SELECT name, roll_number, class_section, student_id, email, marked_at, status "
        "FROM attendance WHERE session_id = ? ORDER BY marked_at ASC",
        (session_id,),
    ).fetchall()
    conn.close()

    records = [dict(r) for r in rows]
    return jsonify({
        "session_id": session_id,
        "class_section": session["class_section"],
        "subject": session["subject"],
        "status": session["status"],
        "count": len(records),
        "records": records,
    })


@app.route("/api/sessions/<session_id>/export", methods=["GET"])
def export_csv(session_id):
    """Export the attendance list as a downloadable CSV file."""
    conn = get_db()
    session = conn.execute("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        conn.close()
        return jsonify({"error": "Session not found"}), 404

    rows = conn.execute(
        "SELECT name, roll_number, class_section, student_id, email, marked_at, status "
        "FROM attendance WHERE session_id = ? ORDER BY marked_at ASC",
        (session_id,),
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Roll Number", "Class/Section", "Student ID", "Email",
                      "Subject", "Session", "Date", "Time", "Status"])

    for r in rows:
        dt = r["marked_at"]
        date_part = dt[:10] if len(dt) >= 10 else dt
        time_part = dt[11:19] if len(dt) >= 19 else ""
        writer.writerow([
            r["name"], r["roll_number"], r["class_section"], r["student_id"],
            r["email"], session["subject"], session_id, date_part, time_part, r["status"],
        ])

    output.seek(0)
    buf = io.BytesIO(output.getvalue().encode("utf-8"))
    filename = f"attendance_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name=filename)


# ── Past sessions ────────────────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    """List all attendance sessions (newest first)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, class_section, subject, topic, started_at, ended_at, status "
        "FROM attendance_sessions ORDER BY started_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Initialize the database on startup (works for both local and Gunicorn)
init_db()

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1").lower() in ("1", "true", "yes")
    port = int(os.environ.get("PORT", "5000"))
    print("\n  ✦  Dynamic QR Attendance Tracker")
    print(f"  ✦  Running at http://127.0.0.1:{port}\n")
    app.run(debug=debug_mode, host="0.0.0.0", port=port)
