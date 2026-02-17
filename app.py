import socket
import json
import os
import secrets
import time
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Required for session

DATA_FILE = 'data.json'

# --- Data Management ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "password": "admin",
            "current_question": "Kā tev šķiet...?",
            "expires_at": None,  # Timestamp when question expires
            "next_questions": [],
            "answers": [],
            "settings": {"interval": "1d", "max_answers": 40, "theme": "light"}
        }
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # Ensure new fields exist if loading old data
        if "expires_at" not in data:
            data["expires_at"] = None
        return data

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Initialize data
app_data = load_data()

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

# --- decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper: Rotate Question ---
def rotate_question():
    global app_data
    if app_data['next_questions']:
        app_data['current_question'] = app_data['next_questions'].pop(0)
    else:
        app_data['current_question'] = "Gaidām jautājumu..."
    
    app_data['expires_at'] = None
    app_data['answers'] = []
    save_data(app_data)

# --- Public Routes ---
@app.route('/')
def board():
    return render_template('board.html', 
                           question=app_data['current_question'],
                           theme=app_data['settings'].get('theme', 'light'))

@app.route('/student')
def student():
    return render_template('student.html')

@app.route('/api/submit', methods=['POST'])
def submit_answer():
    data = request.json
    answer_text = data.get('answer', '').strip()
    
    if answer_text:
        # Check limit
        max_answers = int(app_data['settings'].get('max_answers', 40))
        if max_answers > 0 and len(app_data['answers']) >= max_answers:
            # Remove oldest (first index)
            app_data['answers'].pop(0)

        new_answer = {
            'text': answer_text,
            'id': len(app_data['answers']) + 1
        }
        
        app_data['answers'].append(new_answer)
        save_data(app_data)
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@app.route('/api/answers', methods=['GET'])
def get_answers():
    global app_data
    # Check expiration
    if app_data.get('expires_at') and time.time() > app_data['expires_at']:
        rotate_question()
    
    remaining_time = None
    if app_data.get('expires_at'):
        remaining_time = max(0, int(app_data['expires_at'] - time.time()))

    return jsonify({
        'answers': app_data['answers'],
        'question': app_data['current_question'],
        'remaining_time': remaining_time,
        'theme': app_data['settings'].get('theme', 'light')
    })

# --- Admin Routes ---
@app.route('/admin')
def admin_login():
    if 'logged_in' in session:
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.json
    password = data.get('password')
    if password == app_data['password']:
        session['logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Incorrect password'}), 401

@app.route('/api/admin/logout', methods=['POST'])
def api_admin_logout():
    session.pop('logged_in', None)
    return jsonify({'success': True})

@app.route('/api/admin/data', methods=['GET'])
@login_required
def api_admin_get_data():
    return jsonify(app_data)

@app.route('/api/admin/update', methods=['POST'])
@login_required
def api_admin_update():
    global app_data
    new_data = request.json
    
    # Selective update to prevent overwriting everything blindly
    if 'current_question' in new_data:
        app_data['current_question'] = new_data['current_question']
        # If explicitly setting question, clear expiration unless duration is provided
        app_data['expires_at'] = None

    if 'duration' in new_data and new_data['duration']:
        try:
            seconds = int(new_data['duration'])
            app_data['expires_at'] = time.time() + seconds
        except ValueError:
            pass

    if 'next_questions' in new_data:
        app_data['next_questions'] = new_data['next_questions']
    if 'settings' in new_data:
        app_data['settings'].update(new_data['settings'])
    if 'clear_answers' in new_data and new_data['clear_answers']:
        app_data['answers'] = []
    if 'password' in new_data:
         app_data['password'] = new_data['password']

    save_data(app_data)
    return jsonify({'success': True, 'data': app_data})

if __name__ == '__main__':
    ip = get_ip_address()
    print(f"\n\n==================================================")
    print(f" QUESTION BOARD RUNNING")
    print(f"==================================================")
    print(f" [BOARD VIEW]   http://{ip}:5000")
    print(f" [STUDENT VIEW] http://{ip}:5000/student")
    print(f" [ADMIN PANEL]  http://{ip}:5000/admin")
    print(f"==================================================\n\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
