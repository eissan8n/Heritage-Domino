"""
Heritage Domino - Flask Application
الدومينو التراثي - تطبيق تعليمي لحساب القدماء
"""

import os
import json
import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ============================================
# إعدادات التطبيق
# ============================================
app = Flask(__name__)
app.secret_key = 'heritage-domino-secret-key-2024-change-this-in-production'
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max upload

# إنشاء مجلد uploads إذا لم يكن موجوداً
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ============================================
# قاعدة البيانات
# ============================================
DATABASE = 'heritage_domino.db'

def get_db():
    """الحصول على اتصال بقاعدة البيانات"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول"""
    conn = get_db()
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            avatar_url TEXT DEFAULT '/static/default-avatar.png',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_games_played INTEGER DEFAULT 0,
            total_games_won INTEGER DEFAULT 0,
            total_calculations INTEGER DEFAULT 0,
            total_points INTEGER DEFAULT 0,
            current_level INTEGER DEFAULT 1,
            experience_points INTEGER DEFAULT 0,
            settings TEXT DEFAULT '{}'
        )
    ''')
    
    # جدول الإنجازات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            achievement_id TEXT NOT NULL,
            progress INTEGER DEFAULT 0,
            unlocked_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, achievement_id)
        )
    ''')
    
    # جدول تاريخ اللعب
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            player_score INTEGER NOT NULL,
            ai_score INTEGER NOT NULL,
            winner TEXT NOT NULL,
            tiles_remaining INTEGER DEFAULT 0,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # جدول تاريخ الحسابات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calculation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            first_tile TEXT NOT NULL,
            second_tile TEXT NOT NULL,
            operation TEXT NOT NULL,
            result INTEGER NOT NULL,
            remainder INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

# ============================================
# الأرقام الفارسية (0-1000)
# ============================================
PERSIAN_NUMBERS = {
    # الأساسية 0-10
    0: "صفر", 1: "يك", 2: "دو", 3: "ثه", 4: "جهار",
    5: "بنج", 6: "شيش", 7: "هفت", 8: "هشت", 9: "نوه", 10: "ده",
    
    # 11-19
    11: "يازده", 12: "دوازده", 13: "سيزده", 14: "چهاردَه", 15: "بانزده",
    16: "شانزده", 17: "هفده", 18: "هجده", 19: "نوزده",
    
    # العشرات
    20: "بيست", 30: "سي", 40: "تشهل", 50: "بنجاه",
    60: "شاست", 70: "هفتاد", 80: "هشتاد", 90: "نافاد",
    
    # المئات
    100: "صد", 200: "دویست", 300: "سیصد", 400: "چهارصد",
    500: "پانصد", 600: "ششصد", 700: "هفتصد", 800: "هشتصد",
    900: "نهصد", 1000: "هزار"
}

PERSIAN_OPERATIONS = {
    "+": "جمع",
    "-": "طرح",
    "×": "ضرب",
    "÷": "قسمة"
}

def number_to_persian(num):
    """تحويل رقم عادي إلى فارسي"""
    if num in PERSIAN_NUMBERS:
        return PERSIAN_NUMBERS[num]
    
    # معالجة الأرقام المركبة
    if num < 100:
        tens = (num // 10) * 10
        ones = num % 10
        if tens in PERSIAN_NUMBERS and ones in PERSIAN_NUMBERS:
            return f"{PERSIAN_NUMBERS[tens]} و {PERSIAN_NUMBERS[ones]}"
    elif num < 1000:
        hundreds = (num // 100) * 100
        remainder = num % 100
        if remainder == 0:
            return PERSIAN_NUMBERS[hundreds]
        return f"{PERSIAN_NUMBERS[hundreds]} و {number_to_persian(remainder)}"
    
    return str(num)

# ============================================
# نظام الإنجازات والمستويات
# ============================================
ACHIEVEMENTS = {
    "first_calc": {
        "id": "first_calc",
        "name": "المبتدئ",
        "name_en": "First Steps",
        "description": "إكمال أول عملية حسابية",
        "icon": "🥉",
        "xp_reward": 50
    },
    "calc_25": {
        "id": "calc_25",
        "name": "الحاسب",
        "name_en": "Calculator",
        "description": "إكمال 25 عملية حسابية",
        "icon": "🥈",
        "xp_reward": 150,
        "target": 25
    },
    "calc_100": {
        "id": "calc_100",
        "name": "المهندس",
        "name_en": "Engineer",
        "description": "إكمال 100 عملية حسابية",
        "icon": "🥇",
        "xp_reward": 500,
        "target": 100
    },
    "first_win": {
        "id": "first_win",
        "name": "اللاعب",
        "name_en": "Player",
        "description": "الفوز بأول مباراة ضد الذكاء الاصطناعي",
        "icon": "🎲",
        "xp_reward": 100
    },
    "win_10": {
        "id": "win_10",
        "name": "البطل",
        "name_en": "Champion",
        "description": "الفوز بـ 10 مباريات",
        "icon": "🏆",
        "xp_reward": 750,
        "target": 10
    },
    "win_100": {
        "id": "win_100",
        "name": "الأسطورة",
        "name_en": "Legend",
        "description": "الفوز بـ 100 مباراة",
        "icon": "👑",
        "xp_reward": 5000,
        "target": 100
    }
}

LEVEL_XP_REQUIREMENTS = {
    1: 0, 2: 100, 3: 300, 4: 600, 5: 1000,
    6: 1500, 7: 2100, 8: 2800, 9: 3600, 10: 4500,
    11: 5500, 12: 6600, 13: 7800, 14: 9100, 15: 10500,
    20: 20000, 25: 35000, 30: 50000, 40: 100000, 50: 250000
}

def calculate_level(xp):
    """حساب المستوى بناءً على نقاط الخبرة"""
    current_level = 1
    for level, required_xp in sorted(LEVEL_XP_REQUIREMENTS.items()):
        if xp >= required_xp:
            current_level = level
    return current_level

def get_next_level_xp(current_xp):
    """الحصول على نقاط الخبرة المطلوبة للمستوى التالي"""
    current_level = calculate_level(current_xp)
    next_level = current_level + 1
    if next_level in LEVEL_XP_REQUIREMENTS:
        return LEVEL_XP_REQUIREMENTS[next_level]
    return None

# ============================================
# دوال المساعدة للمصادقة
# ============================================
def login_required(f):
    """ديكوريتور للتأكد من تسجيل الدخول"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """الحصول على بيانات المستخدم الحالي"""
    if 'user_id' not in session:
        return None
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

# ============================================
# المسارات الرئيسية
# ============================================
@app.route('/')
def index():
    """الصفحة الرئيسية"""
    user = get_current_user()
    return render_template('index.html', user=user)

@app.route('/play')
@login_required
def play():
    """وضع اللعب"""
    user = get_current_user()
    return render_template('play.html', user=user)

@app.route('/calculator')
@login_required
def calculator():
    """وضع الحاسبة"""
    user = get_current_user()
    return render_template('calculator.html', user=user, persian_numbers=PERSIAN_NUMBERS)

@app.route('/achievements')
@login_required
def achievements():
    """صفحة الإنجازات"""
    user = get_current_user()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM user_achievements WHERE user_id = ?
    ''', (user['id'],))
    user_achievements = {ach['achievement_id']: dict(ach) for ach in cursor.fetchall()}
    conn.close()
    
    current_level = calculate_level(user['experience_points'])
    next_level_xp = get_next_level_xp(user['experience_points'])
    
    return render_template('achievements.html', 
                         user=user, 
                         achievements=ACHIEVEMENTS,
                         user_achievements=user_achievements,
                         current_level=current_level,
                         next_level_xp=next_level_xp)

@app.route('/profile')
@login_required
def profile():
    """الملف الشخصي"""
    user = get_current_user()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # إحصائيات اللعب
    cursor.execute('''
        SELECT COUNT(*) as total_games, 
               SUM(CASE WHEN winner = 'player' THEN 1 ELSE 0 END) as wins,
               SUM(player_score) as total_points
        FROM game_history WHERE user_id = ?
    ''', (user['id'],))
    game_stats = dict(cursor.fetchone())
    
    # إحصائيات الحساب
    cursor.execute('''
        SELECT COUNT(*) as total_calcs,
               operation,
               COUNT(operation) as op_count
        FROM calculation_history 
        WHERE user_id = ?
        GROUP BY operation
        ORDER BY op_count DESC
        LIMIT 1
    ''', (user['id'],))
    calc_stats = cursor.fetchone()
    
    conn.close()
    
    current_level = calculate_level(user['experience_points'])
    next_level_xp = get_next_level_xp(user['experience_points'])
    
    return render_template('profile.html',
                         user=user,
                         game_stats=game_stats,
                         calc_stats=calc_stats,
                         current_level=current_level,
                         next_level_xp=next_level_xp)

# ============================================
# المصادقة
# ============================================
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """تسجيل حساب جديد"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        
        # التحقق من البيانات
        if not username or not email or not password:
            flash('جميع الحقول مطلوبة', 'danger')
            return redirect(url_for('signup'))
        
        if len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
            return redirect(url_for('signup'))
        
        conn = get_db()
        cursor = conn.cursor()
        
        # التحقق من عدم وجود المستخدم
        cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', 
                      (username, email))
        if cursor.fetchone():
            flash('اسم المستخدم أو البريد الإلكتروني مستخدم بالفعل', 'danger')
            conn.close()
            return redirect(url_for('signup'))
        
        # إنشاء المستخدم
        password_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name)
            VALUES (?, ?, ?, ?)
        ''', (username, email, password_hash, full_name))
        
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        # تسجيل الدخول تلقائياً
        session['user_id'] = user_id
        session['username'] = username
        
        flash(f'مرحباً {full_name or username}! تم إنشاء حسابك بنجاح', 'success')
        return redirect(url_for('index'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """تسجيل الدخول"""
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        
        conn = get_db()
        cursor = conn.cursor()
        
        # البحث عن المستخدم بالبريد أو اسم المستخدم
        cursor.execute('''
            SELECT * FROM users 
            WHERE username = ? OR email = ?
        ''', (login_id, login_id.lower()))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            
            if remember:
                session.permanent = True
            
            flash(f'مرحباً بعودتك {user["full_name"] or user["username"]}!', 'success')
            
            # التوجيه للصفحة المطلوبة
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        
        flash('بيانات الدخول غير صحيحة', 'danger')
        return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """تسجيل الخروج"""
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('index'))

@app.route('/guest')
def guest_mode():
    """الدخول كزائر"""
    session['guest'] = True
    session['username'] = f'زائر_{random.randint(1000, 9999)}'
    flash('أنت الآن في وضع الزائر - البيانات لن تحفظ', 'info')
    return redirect(url_for('index'))

# ============================================
# API Routes للعبة
# ============================================
@app.route('/api/game/save', methods=['POST'])
@login_required
def save_game_result():
    """حفظ نتيجة مباراة"""
    data = request.json
    user = get_current_user()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # حفظ نتيجة المباراة
    cursor.execute('''
        INSERT INTO game_history (user_id, player_score, ai_score, winner, tiles_remaining)
        VALUES (?, ?, ?, ?, ?)
    ''', (user['id'], data['player_score'], data['ai_score'], 
          data['winner'], data.get('tiles_remaining', 0)))
    
    # تحديث إحصائيات المستخدم
    xp_gained = 50 if data['winner'] == 'player' else 15
    new_xp = user['experience_points'] + xp_gained
    new_level = calculate_level(new_xp)
    
    cursor.execute('''
        UPDATE users 
        SET total_games_played = total_games_played + 1,
            total_games_won = total_games_won + ?,
            total_points = total_points + ?,
            experience_points = experience_points + ?,
            current_level = ?
        WHERE id = ?
    ''', (1 if data['winner'] == 'player' else 0,
          data['player_score'],
          xp_gained,
          new_level,
          user['id']))
    
    # التحقق من الإنجازات
    if data['winner'] == 'player':
        # التحقق من أول فوز
        cursor.execute('SELECT COUNT(*) as wins FROM game_history WHERE user_id = ? AND winner = "player"', 
                      (user['id'],))
        wins = cursor.fetchone()[0]
        
        if wins == 1:
            # إنجاز أول فوز
            cursor.execute('''
                INSERT OR IGNORE INTO user_achievements (user_id, achievement_id, unlocked_at)
                VALUES (?, ?, datetime('now'))
            ''', (user['id'], 'first_win'))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'xp_gained': xp_gained,
        'new_level': new_level,
        'level_up': new_level > user['current_level']
    })

@app.route('/api/calculation/save', methods=['POST'])
@login_required
def save_calculation():
    """حفظ عملية حسابية"""
    data = request.json
    user = get_current_user()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # حفظ العملية
    cursor.execute('''
        INSERT INTO calculation_history 
        (user_id, first_tile, second_tile, operation, result, remainder)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user['id'], data['first_tile'], data['second_tile'], 
          data['operation'], data['result'], data.get('remainder')))
    
    # تحديث عدد العمليات
    cursor.execute('SELECT COUNT(*) FROM calculation_history WHERE user_id = ?', (user['id'],))
    calc_count = cursor.fetchone()[0]
    
    # XP للعملية
    xp_gained = 10
    new_xp = user['experience_points'] + xp_gained
    new_level = calculate_level(new_xp)
    
    cursor.execute('''
        UPDATE users 
        SET total_calculations = total_calculations + 1,
            experience_points = experience_points + ?,
            current_level = ?
        WHERE id = ?
    ''', (xp_gained, new_level, user['id']))
    
    # التحقق من إنجازات العمليات الحسابية
    achievement_checks = [
        ('first_calc', 1),
        ('calc_25', 25),
        ('calc_100', 100)
    ]
    
    for ach_id, target in achievement_checks:
        if calc_count >= target:
            cursor.execute('''
                INSERT OR IGNORE INTO user_achievements (user_id, achievement_id, unlocked_at)
                VALUES (?, ?, datetime('now'))
            ''', (user['id'], ach_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'xp_gained': xp_gained,
        'calc_count': calc_count,
        'new_level': new_level
    })

# ============================================
# Persian API
# ============================================
@app.route('/api/persian/<int:number>')
def get_persian_number(number):
    """الحصول على المقابل الفارسي لرقم"""
    return jsonify({
        'number': number,
        'persian': number_to_persian(number)
    })

# ============================================
# تشغيل التطبيق
# ============================================
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
