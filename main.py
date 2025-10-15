from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse
import openai
import os
import requests
from bs4 import BeautifulSoup
import json
import time
import sqlite3
from datetime import datetime
import paypalrestsdk
import smtplib
from email.mime.text import MIMEText
import hashlib
import secrets
import logging
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'leax-secret-key-2024')

# ==================== CONFIGURATION ====================
openai.api_key = os.environ.get('OPENAI_API_KEY')

# PayPal Configuration
paypalrestsdk.configure({
    "mode": os.environ.get('PAYPAL_MODE', 'sandbox'),
    "client_id": os.environ.get('PAYPAL_CLIENT_ID'),
    "client_secret": os.environ.get('PAYPAL_CLIENT_SECRET')
})

# Email Configuration
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'admin@americanpower.us')
EMAIL_TO = os.environ.get('EMAIL_TO', 'systems@americanpower.us')
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.office365.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')

# Database Configuration
DATABASE_FILE = os.environ.get('DATABASE_FILE', 'leax_users.db')

# ==================== SCALABLE DATABASE SYSTEM ====================
@contextmanager
def get_db():
    """Database connection context manager"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Initialize database with scalable structure"""
    with get_db() as conn:
        c = conn.cursor()
        
        # Users table with indexing for performance
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                business_name TEXT NOT NULL,
                status TEXT DEFAULT 'trial',
                plan_type TEXT DEFAULT 'starter',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trial_uses INTEGER DEFAULT 0,
                max_trial_uses INTEGER DEFAULT 3,
                total_messages INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # Business info table
        c.execute('''
            CREATE TABLE IF NOT EXISTS business_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                website_url TEXT,
                services TEXT,
                custom_info TEXT,
                agent_personality TEXT DEFAULT 'friendly',
                business_hours TEXT DEFAULT '{}',
                pricing_info TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # Conversations table for message history
        c.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone_number TEXT,
                message_text TEXT,
                response_text TEXT,
                message_type TEXT DEFAULT 'sms',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_direction TEXT DEFAULT 'incoming',
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # Payments table
        c.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                payment_id TEXT UNIQUE,
                amount REAL,
                currency TEXT DEFAULT 'USD',
                plan_type TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # System logs table
        c.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                user_id INTEGER,
                description TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for performance
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_business_info_user_id ON business_info(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)')
        
        conn.commit()

# Initialize database on startup
init_database()

# ==================== DATABASE UTILITIES ====================
def log_system_event(event_type, user_id=None, description="", ip_address=""):
    """Log system events for monitoring"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO system_logs (event_type, user_id, description, ip_address)
            VALUES (?, ?, ?, ?)
        ''', (event_type, user_id, description, ip_address or request.remote_addr))
        conn.commit()

def get_user_stats():
    """Get system statistics"""
    with get_db() as conn:
        c = conn.cursor()
        
        c.execute('SELECT COUNT(*) as total_users FROM users')
        total_users = c.fetchone()['total_users']
        
        c.execute('SELECT COUNT(*) as active_users FROM users WHERE is_active = 1')
        active_users = c.fetchone()['active_users']
        
        c.execute('SELECT COUNT(*) as paid_users FROM users WHERE status != "trial"')
        paid_users = c.fetchone()['paid_users']
        
        c.execute('SELECT SUM(total_messages) as total_messages FROM users')
        total_messages = c.fetchone()['total_messages'] or 0
        
        return {
            'total_users': total_users,
            'active_users': active_users,
            'paid_users': paid_users,
            'total_messages': total_messages
        }

def export_user_data(user_id):
    """Export all user data for portability"""
    with get_db() as conn:
        c = conn.cursor()
        
        # Get user data
        c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = dict(c.fetchone())
        
        # Get business info
        c.execute('SELECT * FROM business_info WHERE user_id = ?', (user_id,))
        business = dict(c.fetchone()) if c.fetchone() else {}
        
        # Get conversations (last 1000 for export)
        c.execute('SELECT * FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1000', (user_id,))
        conversations = [dict(row) for row in c.fetchall()]
        
        # Get payments
        c.execute('SELECT * FROM payments WHERE user_id = ?', (user_id,))
        payments = [dict(row) for row in c.fetchall()]
        
        return {
            'user': user,
            'business': business,
            'conversations': conversations,
            'payments': payments,
            'exported_at': datetime.now().isoformat()
        }

# ==================== UTILITY FUNCTIONS ====================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_email(subject, message):
    """Send email notification"""
    try:
        if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD]):
            logging.warning("Email configuration missing")
            return False
            
        msg = MimeText(message)
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        log_system_event('email_sent', description=f"Subject: {subject}")
        return True
    except Exception as e:
        logging.error(f"Email error: {e}")
        return False

# ==================== AUTHENTICATION ROUTES ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE email = ? AND is_active = 1', (email,))
            user = c.fetchone()
        
        if user and user['password_hash'] == hash_password(password):
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['business_name'] = user['business_name']
            session['user_plan'] = user['plan_type']
            
            log_system_event('user_login', user['id'], "Successful login")
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password')
            log_system_event('failed_login', description=f"Failed login attempt for: {email}")
    
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    email = request.form.get('email')
    business_name = request.form.get('business_name')
    password = request.form.get('password')
    
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO users (email, password_hash, business_name, status, plan_type)
                VALUES (?, ?, ?, 'trial', 'starter')
            ''', (email, hash_password(password), business_name))
            user_id = c.lastrowid
            
            # Create initial business info record
            c.execute('''
                INSERT INTO business_info (user_id, agent_personality)
                VALUES (?, 'friendly')
            ''', (user_id,))
            
            conn.commit()
        
        session['user_id'] = user_id
        session['email'] = email
        session['business_name'] = business_name
        session['user_plan'] = 'starter'
        
        # Send notification
        send_email(
            "New LeaX Platform Registration",
            f"New platform user registered:\n"
            f"Email: {email}\n"
            f"Business: {business_name}\n"
            f"User ID: {user_id}\n"
            f"Platform: {request.host}\n"
            f"Time: {datetime.now()}\n"
            f"Total users on platform: {get_user_stats()['total_users']}"
        )
        
        log_system_event('user_registered', user_id, f"New user: {business_name}")
        return redirect(url_for('customize_agent'))
        
    except sqlite3.IntegrityError:
        flash('Email already exists')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_system_event('user_logout', session['user_id'], "User logged out")
    session.clear()
    return redirect(url_for('index'))

# ==================== ADMIN & SYSTEM ROUTES ====================
@app.route('/admin')
def admin_dashboard():
    """Admin dashboard with system statistics"""
    stats = get_user_stats()
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT * FROM users 
            ORDER BY created_at DESC 
            LIMIT 10
        ''')
        recent_users = [dict(row) for row in c.fetchall()]
        
        c.execute('''
            SELECT * FROM system_logs 
            ORDER BY created_at DESC 
            LIMIT 50
        ''')
        recent_logs = [dict(row) for row in c.fetchall()]
    
    return render_template('admin.html', 
                         stats=stats, 
                         recent_users=recent_users, 
                         recent_logs=recent_logs)

@app.route('/admin/export-data')
def admin_export_data():
    """Export all system data"""
    with get_db() as conn:
        c = conn.cursor()
        
        # Get all data
        c.execute('SELECT * FROM users')
        users = [dict(row) for row in c.fetchall()]
        
        c.execute('SELECT * FROM business_info')
        business_info = [dict(row) for row in c.fetchall()]
        
        c.execute('SELECT COUNT(*) as count FROM conversations')
        conversation_count = c.fetchone()['count']
        
        data = {
            'export_info': {
                'exported_at': datetime.now().isoformat(),
                'total_users': len(users),
                'total_conversations': conversation_count,
                'platform_url': request.host
            },
            'users': users,
            'business_info': business_info,
            'statistics': get_user_stats()
        }
    
    return jsonify(data)

# ==================== USER MANAGEMENT ROUTES ====================
@app.route('/user/profile')
def user_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT u.*, b.* 
            FROM users u 
            LEFT JOIN business_info b ON u.id = b.user_id 
            WHERE u.id = ?
        ''', (session['user_id'],))
        user_data = c.fetchone()
    
    return render_template('profile.html', user=dict(user_data))

@app.route('/user/export-my-data')
def export_my_data():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_data = export_user_data(session['user_id'])
    return jsonify(user_data)

# [Include all the other routes from previous version: customize, test, payment, etc.]
# ... (Include all the routes from the previous version)

if __name__ == '__main__':
    # Log startup information
    logging.basicConfig(level=logging.INFO)
    logging.info(f"LeaX Platform Starting - Database: {DATABASE_FILE}")
    
    stats = get_user_stats()
    logging.info(f"System Stats: {stats}")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
