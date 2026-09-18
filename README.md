# Dynamic QR Attendance Tracker

A lightweight web application for classroom attendance using rotating QR codes.

The teacher displays a single QR code that rotates every 10 seconds. Students scan the current QR, fill in a short form, and mark their attendance. Expired QR screenshots are rejected — making it difficult for absent students to cheat.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the application
python app.py
```

The server starts at **http://127.0.0.1:5000**

---

## How It Works

### Teacher Flow

1. Open **http://127.0.0.1:5000/admin**
2. Enter class/section, subject, and optional topic
3. Click **Start Attendance**
4. A QR code appears and refreshes every 10 seconds
5. The dashboard shows a live student count and attendance list
6. Click **Stop Attendance** when done
7. Click **Export CSV** to download the attendance sheet

### Student Flow

1. Scan the QR code displayed on the teacher's screen
2. A mobile-friendly form opens
3. Fill in name, roll number, class, and student ID
4. Tap **Mark Attendance**
5. See a confirmation with session details

---

## Key Features

- **Rotating QR**: Changes every 10 seconds (configurable in `app.py`)
- **Anti-sharing**: Expired QR screenshots are rejected
- **Concurrent scanning**: Multiple students scan the same QR simultaneously
- **Form persistence**: If a student opens the form before QR rotates, they can still submit
- **Duplicate prevention**: Each student can only mark attendance once per session
- **Live dashboard**: Teacher sees attendance count update in real time
- **CSV export**: Download attendance list with one click
- **Mobile-first**: Student form is optimized for phones

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions/start` | Create new session |
| POST | `/api/sessions/<id>/stop` | Stop session |
| GET | `/api/sessions/<id>/current-token` | Get fresh QR token |
| GET | `/attendance/<token>` | Student form page |
| POST | `/api/attendance/mark` | Submit attendance |
| GET | `/api/sessions/<id>/attendance` | List attendees |
| GET | `/api/sessions/<id>/export` | Download CSV |
| GET | `/api/sessions` | List all sessions |

---

## Configuration

In `app.py`, change `QR_TOKEN_LIFETIME_SECONDS` to adjust QR rotation speed (default: 10 seconds).

---

## Tech Stack

- **Backend**: Python + Flask
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **QR**: `qrcode` library (Python)

---

## License

MIT
