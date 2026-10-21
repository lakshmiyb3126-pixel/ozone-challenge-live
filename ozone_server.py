"""Ozone Challenge: publicly deployable, standard-library-only quiz server.
Run locally with `python ozone_server.py`, or deploy as a public web service.
Students: /   Teacher dashboard: /teacher
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import json
import sqlite3
import secrets
import socket
import os
import time
import threading
from http.cookies import SimpleCookie

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("OZONE_DATABASE_PATH", os.path.join(BASE, "ozone_scores.sqlite3"))
PORT = int(os.environ.get("PORT", os.environ.get("OZONE_PORT", "8765")))
TEACHER_PASSWORD = os.environ.get("OZONE_TEACHER_PASSWORD", "")
TEACHER_SESSIONS = {}  # randomized session IDs; cleared on server restart
SESSION_SECONDS = 6 * 60 * 60
LOCK = threading.RLock()
SECONDS = 10

QUESTIONS = [
    {"q": "What is the chemical formula of ozone?", "choices": ["O₂", "O₃", "CO₂", "H₂O"], "right": 1, "answer": "O₃"},
    {"q": "In which atmospheric layer is ozone mainly present?", "choices": ["Troposphere", "Mesosphere", "Stratosphere", "Thermosphere"], "right": 2, "answer": "Stratosphere"},
    {"q": "What does CFC stand for?", "choices": ["Carbon Fluorine Complex", "Chlorofluorocarbon", "Chemical Fuel Compound", "Chlorine Free Carbon"], "right": 1, "answer": "Chlorofluorocarbon"},
    {"q": "Which type of radiation is absorbed by the ozone layer?", "choices": ["Microwave", "Infrared", "Ultraviolet (UV)", "Radio waves"], "right": 2, "answer": "Ultraviolet (UV)"},
    {"q": "Which international treaty protects the ozone layer?", "choices": ["Montreal Protocol", "Kyoto Protocol", "Basel Convention", "Paris Agreement"], "right": 0, "answer": "Montreal Protocol"},
    {"q": "In which year was the Montreal Protocol adopted?", "choices": ["1972", "1997", "1987", "2005"], "right": 2, "answer": "1987"},
    {"q": "Which region experiences the largest seasonal ozone hole?", "choices": ["Arctic", "Antarctica", "Equator", "Sahara"], "right": 1, "answer": "Antarctica"},
    {"q": "What is the unit used to measure total column ozone?", "choices": ["Pascal", "Decibel", "Dobson Unit (DU)", "Joule"], "right": 2, "answer": "Dobson Unit (DU)"},
    {"q": "Name one element responsible for catalytic ozone destruction.", "choices": ["Sodium", "Neon", "Argon", "Chlorine or Bromine"], "right": 3, "answer": "Chlorine or Bromine"},
    {"q": "What is the full form of ODP?", "choices": ["Ozone Depletion Potential", "Oxygen Density Parameter", "Ozone Distribution Process", "Oxygen Depletion Percentage"], "right": 0, "answer": "Ozone Depletion Potential"},
    {"q": "Which skin disease is linked to increased UV exposure?", "choices": ["Skin cancer", "Malaria", "Diabetes", "Asthma"], "right": 0, "answer": "Skin cancer"},
    {"q": "Does CO₂ refrigerant (R-744) have an ozone depletion potential of zero?", "choices": ["No", "Only above 100°C", "Yes", "Only at low pressure"], "right": 2, "answer": "Yes"},
]


def connect():
    conn = sqlite3.connect(DB, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS players (
            token TEXT PRIMARY KEY, name TEXT NOT NULL, score INTEGER NOT NULL DEFAULT 0,
            correct INTEGER NOT NULL DEFAULT 0, idx INTEGER NOT NULL DEFAULT 0,
            qstarted REAL NOT NULL, answered INTEGER NOT NULL DEFAULT 0,
            chosen INTEGER NOT NULL DEFAULT -1, earned INTEGER NOT NULL DEFAULT 0,
            started REAL NOT NULL, finished REAL, updated REAL NOT NULL)""")


def get_question(row):
    i = row['idx']
    if i >= len(QUESTIONS):
        return None
    q = QUESTIONS[i]
    return {"index": i, "total": len(QUESTIONS), "text": q["q"],
            "choices": q["choices"], "duration": SECONDS,
            "expires": round(row['qstarted'] + SECONDS, 3),
            "score": row['score'], "name": row['name'],
            "answered": bool(row['answered'])}


def save_answer(db, row, choice):
    if row['answered']:
        return db.execute("SELECT * FROM players WHERE token=?", (row['token'],)).fetchone()
    i = row['idx']
    if i >= len(QUESTIONS):
        return row
    now = time.time()
    is_correct = (isinstance(choice, int) and not isinstance(choice, bool)
                  and choice == QUESTIONS[i]['right'] and now <= row['qstarted'] + SECONDS + 0.35)
    earned = 10 if is_correct else 0
    db.execute("""UPDATE players SET answered=1, chosen=?, earned=?, score=score+?,
               correct=correct+?, updated=? WHERE token=?""",
               (choice, earned, earned, int(is_correct), now, row['token']))
    return db.execute("SELECT * FROM players WHERE token=?", (row['token'],)).fetchone()


def feedback(row):
    i = row['idx']
    q = QUESTIONS[i]
    return {"index": i, "right": q['right'], "answer": q['answer'],
            "chosen": row['chosen'], "earned": row['earned'], "score": row['score']}


def summary(row):
    return {"name": row['name'], "score": row['score'], "correct": row['correct'],
            "total": len(QUESTIONS), "elapsed": round((row['finished'] or time.time()) - row['started'], 1)}


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        try: return socket.gethostbyname(socket.gethostname())
        except OSError: return "YOUR-LAPTOP-IP"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Classroom-friendly console

    def _send_headers(self, extra=None):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        for k, v in (extra or {}).items():
            self.send_header(k, v)

    def _cookie(self, value='', max_age=SESSION_SECONDS):
        secure = self.headers.get('X-Forwarded-Proto','').split(',')[0].strip().lower() == 'https'
        # On Render the incoming browser request is HTTPS, forwarded to this HTTP server.
        return f'ozone_teacher={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}' + ('; Secure' if secure else '')

    def _session_key(self):
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
            return jar['ozone_teacher'].value if 'ozone_teacher' in jar else ''
        except Exception:
            return ''

    def is_teacher(self):
        key = self._session_key()
        with LOCK:
            until = TEACHER_SESSIONS.get(key, 0) if key else 0
            if until > time.time():
                return True
            if key:
                TEACHER_SESSIONS.pop(key, None)
        return False

    def guard_teacher(self):
        if not self.is_teacher():
            self.send_data({'error': 'Teacher login required.'}, 401)
            return False
        return True

    def send_data(self, data, status=200, extra=None):
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self._send_headers(extra)
        self.end_headers()
        self.wfile.write(payload)

    def page(self, filename):
        path = os.path.join(BASE, filename)
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self._send_headers()
        self.end_headers()
        self.wfile.write(data)

    def incoming(self):
        if int(self.headers.get('Content-Length', '0')) > 4096:
            raise ValueError('Request too large.')
        return json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or b'{}')

    def do_GET(self):
        route = urlparse(self.path).path
        if route == '/':
            return self.page('index.html')
        if route in ('/teacher', '/teacher/'):
            return self.page('teacher.html' if self.is_teacher() else 'teacher_login.html')
        if route == '/api/board':
            if not self.guard_teacher(): return
            with LOCK, connect() as db:
                rows = db.execute('SELECT name, score, correct, idx, answered, started, finished FROM players').fetchall()
            leaders = [dict(r) for r in rows]
            leaders.sort(key=lambda p: (-p['score'], p['finished'] is None, (p['finished'] or time.time()) - p['started'], p['name'].casefold()))
            for i, p in enumerate(leaders):
                p['rank'] = i + 1
                p['progress'] = min(12, p['idx'] + int(bool(p['answered']))) if p['finished'] is None else 12
                p['elapsed'] = round((p['finished'] or time.time()) - p['started'], 1)
                p['finished'] = p['finished'] is not None
                del p['started']
                del p['idx']
                del p['answered']
            return self.send_data({'players': leaders, 'joined': len(rows),
                'completed': sum(1 for x in leaders if x['finished'])})
        if route == '/api/info':
            return self.send_data({'student_url': '/', 'total_questions': len(QUESTIONS)})
        if route == '/api/health':
            return self.send_data({'ok': True})
        self.send_error(404)

    def do_POST(self):
        route = urlparse(self.path).path
        try:
            data = self.incoming()
            if not isinstance(data, dict): raise ValueError('Invalid request.')
            if route == '/api/teacher/login':
                password = data.get('password', '')
                if not TEACHER_PASSWORD:
                    return self.send_data({'error': 'Teacher password is not configured on Render. Set OZONE_TEACHER_PASSWORD in Environment.'}, 503)
                if not isinstance(password, str) or not secrets.compare_digest(password, TEACHER_PASSWORD):
                    time.sleep(0.4)  # reduce automated password guessing
                    return self.send_data({'error': 'Incorrect teacher password.'}, 403)
                key = secrets.token_urlsafe(32)
                with LOCK:
                    TEACHER_SESSIONS[key] = time.time() + SESSION_SECONDS
                return self.send_data({'ok': True}, extra={'Set-Cookie': self._cookie(key)})
            if route == '/api/teacher/logout':
                with LOCK:
                    TEACHER_SESSIONS.pop(self._session_key(), None)
                return self.send_data({'ok': True}, extra={'Set-Cookie': self._cookie('', 0)})
            if route == '/api/start':
                name = data.get('name', '')
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 32:
                    return self.send_data({'error': 'Enter a name (1–32 characters).'}, 400)
                name = ' '.join(name.strip().split())
                token = secrets.token_urlsafe(24)
                now = time.time()
                with LOCK, connect() as db:
                    db.execute('INSERT INTO players (token,name,qstarted,started,updated) VALUES (?,?,?,?,?)',
                               (token, name, now, now, now))
                    row = db.execute('SELECT * FROM players WHERE token=?', (token,)).fetchone()
                return self.send_data({'token': token, 'question': get_question(row)})
            if route == '/api/reset':
                if not self.guard_teacher(): return
                if not TEACHER_PASSWORD or not isinstance(data.get('password'), str) or not secrets.compare_digest(data['password'], TEACHER_PASSWORD):
                    return self.send_data({'error': 'Incorrect teacher password.'}, 403)
                with LOCK, connect() as db:
                    db.execute('DELETE FROM players')
                return self.send_data({'ok': True})
            if route in ('/api/answer', '/api/next'):
                token = data.get('token', '')
                if not isinstance(token, str) or len(token) > 100:
                    return self.send_data({'error': 'Invalid player session.'}, 400)
                with LOCK, connect() as db:
                    row = db.execute('SELECT * FROM players WHERE token=?', (token,)).fetchone()
                    if row is None: return self.send_data({'error': 'Game session not found. Start a new game.'}, 404)
                    if row['finished'] is not None: return self.send_data({'finished': True, 'result': summary(row)})
                    if route == '/api/answer':
                        if data.get('index') != row['idx']:
                            return self.send_data({'error': 'Question changed. Refresh and start again.'}, 409)
                        choice = data.get('choice', -1)
                        if not isinstance(choice, int) or isinstance(choice, bool) or choice < -1 or choice > 3:
                            return self.send_data({'error': 'Invalid answer.'}, 400)
                        row = save_answer(db, row, choice)
                        return self.send_data({'feedback': feedback(row)})
                    if not row['answered']:
                        if time.time() > row['qstarted'] + SECONDS:
                            row = save_answer(db, row, -1)
                        else:
                            return self.send_data({'error': 'Answer this question before continuing.'}, 400)
                    if row['idx'] == len(QUESTIONS) - 1:
                        now = time.time()
                        db.execute('UPDATE players SET finished=?, idx=?, updated=? WHERE token=?',
                                   (now, len(QUESTIONS), now, token))
                        row = db.execute('SELECT * FROM players WHERE token=?', (token,)).fetchone()
                        return self.send_data({'finished': True, 'result': summary(row)})
                    now = time.time()
                    db.execute('UPDATE players SET idx=idx+1, answered=0, chosen=-1, earned=0, qstarted=?, updated=? WHERE token=?',
                               (now, now, token))
                    row = db.execute('SELECT * FROM players WHERE token=?', (token,)).fetchone()
                    return self.send_data({'question': get_question(row)})
            self.send_error(404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_data({'error': str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            print('Unexpected server error:', repr(exc), flush=True)
            try: self.send_data({'error': 'Server error. Please retry.'}, 500)
            except (BrokenPipeError, ConnectionResetError): pass


if __name__ == '__main__':
    init_db()
    try:
        server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    except OSError as exc:
        print(f'Cannot start server on port {PORT}: {exc}')
        raise SystemExit(1)
    ip = local_ip()
    print('\n' + '=' * 60)
    print('           OZONE CHALLENGE — LIVE CLASSROOM GAME')
    print('=' * 60)
    print(f' LOCAL TEST: http://localhost:{PORT}')
    print(f' LOCAL TEACHER BOARD: http://localhost:{PORT}/teacher')
    print(' TEACHER DASHBOARD: password-protected (OZONE_TEACHER_PASSWORD)')
    print('\n PUBLIC DEPLOYMENT: share the HTTPS domain given by your hosting platform.')
    print(' Students can use mobile data or any internet connection.')
    print(' NOTE: free hosting with temporary disks can erase scores on restart or idle.')
    print('=' * 60 + '\n', flush=True)
    if os.name == 'nt':
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(f'http://localhost:{PORT}/teacher')).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nQuiz server stopped.')
    finally: server.server_close()
