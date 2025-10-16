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
EMAIL_TO = os.environ.get('EMAIL_TO', 'hr@americanpower.us')  # UPDATED
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
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Initialize database with scalable structure"""
    with get_db() as conn:
        c = conn.cursor()
        
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
        
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_business_info_user_id ON business_info(user_id)')
        
        conn.commit()

init_database()

# ==================== UTILITY FUNCTIONS ====================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_email(subject, message):
    """Send email notification - UPDATED FIXED VERSION"""
    try:
        if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD]):
            print("EMAIL CONFIG MISSING - Check Railway Variables")
            return False
            
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ EMAIL SENT: {subject}")
        return True
    except Exception as e:
        print(f"❌ EMAIL FAILED: {e}")
        return False

# ==================== LANDING PAGE ====================
@app.route('/')
def index():
    """Main landing page"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>LeaX - AI Phone Agent</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 100px auto; padding: 20px; text-align: center; }
            .hero { background: #f8f9fa; padding: 60px 20px; border-radius: 10px; }
            .btn { background: #007cba; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px; }
            .pricing { display: flex; justify-content: center; gap: 20px; margin: 40px 0; }
            .plan { border: 1px solid #ddd; padding: 30px; border-radius: 10px; }
        </style>
    </head>
    <body>
        <div class="hero">
            <h1>🤖 LeaX AI Phone Agent</h1>
            <p>Your business gets an AI assistant that answers calls, texts customers, and makes sales - 24/7!</p>
            
            <div class="pricing">
                <div class="plan">
                    <h3>Starter Plan</h3>
                    <h2>$29.99/month</h2>
                    <ul style="text-align: left;">
                        <li>AI Phone & SMS Agent</li>
                        <li>Website Scanning</li>
                        <li>Lead Capture</li>
                        <li>3 Free Tests</li>
                    </ul>
                    <a href="/register" class="btn">Get Started</a>
                </div>
            </div>
        </div>
        
        <div style="margin: 40px 0;">
            <h2>How It Works</h2>
            <div style="display: flex; justify-content: center; gap: 30px; margin: 30px 0;">
                <div>1. Sign up & customize</div>
                <div>2. Test your AI agent</div>
                <div>3. Connect phone number</div>
                <div>4. Go live!</div>
            </div>
        </div>
    </body>
    </html>
    '''

# ==================== AUTHENTICATION ====================
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
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Register - LeaX</title>
            <style>
                body { font-family: Arial; max-width: 400px; margin: 100px auto; padding: 20px; }
                input { width: 100%; padding: 10px; margin: 10px 0; }
                button { background: #007cba; color: white; padding: 12px 30px; border: none; cursor: pointer; width: 100%; }
            </style>
        </head>
        <body>
            <h2>Create LeaX Account</h2>
            <form method="POST">
                <input type="email" name="email" placeholder="Email" required>
                <input type="text" name="business_name" placeholder="Business Name" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Create Account</button>
            </form>
            <p><a href="/login">Already have an account? Login</a></p>
        </body>
        </html>
        '''
    
    elif request.method == 'POST':
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
                
                c.execute('''
                    INSERT INTO business_info (user_id, agent_personality)
                    VALUES (?, 'friendly')
                ''', (user_id,))
                
                conn.commit()
            
            session['user_id'] = user_id
            session['email'] = email
            session['business_name'] = business_name
            session['user_plan'] = 'starter'
            
            send_email(
                "New LeaX Registration",
                f"New user registered:\nEmail: {email}\nBusiness: {business_name}\nUser ID: {user_id}"
            )
            
            return redirect(url_for('customize_agent'))
            
        except sqlite3.IntegrityError:
            flash('Email already exists')
            return redirect(url_for('register'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ==================== DASHBOARD ====================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        c.execute('SELECT * FROM business_info WHERE user_id = ?', (session['user_id'],))
        business = c.fetchone()
    
    user_dict = dict(user) if user else {}
    business_dict = dict(business) if business else {}
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - LeaX</title>
        <style>
            body {{ font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }}
            .card {{ background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 8px; }}
            .btn {{ background: #007cba; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>Welcome to LeaX, {session['business_name']}!</h1>
        
        <div class="card">
            <h3>Your Account</h3>
            <p><strong>Plan:</strong> {user_dict.get('plan_type', 'Starter')}</p>
            <p><strong>Status:</strong> {user_dict.get('status', 'Active')}</p>
            <p><strong>Trial Uses:</strong> {user_dict.get('trial_uses', 0)}/3</p>
        </div>
        
        <div class="card">
            <h3>Quick Actions</h3>
            <p><a href="/customize" class="btn">Customize Agent</a></p>
            <p><a href="/test-agent" class="btn">Test Your Agent</a></p>
            <p><a href="/pricing" class="btn">Upgrade Plan</a></p>
        </div>
        
        <p><a href="/logout">Logout</a></p>
    </body>
    </html>
    '''

# ==================== AGENT CUSTOMIZATION ====================
@app.route('/customize')
def customize_agent():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Customize Agent - LeaX</title>
        <style>
            body { font-family: Arial; max-width: 600px; margin: 40px auto; padding: 20px; }
            input, textarea { width: 100%; padding: 10px; margin: 10px 0; }
            button { background: #007cba; color: white; padding: 12px 30px; border: none; cursor: pointer; }
        </style>
    </head>
    <body>
        <h2>Customize Your AI Agent</h2>
        
        <div id="message" style="display: none; background: #d4edda; padding: 10px; margin: 10px 0;"></div>
        
        <form id="customizeForm">
            <h3>Business Information</h3>
            <input type="url" id="website_url" placeholder="Your website URL (optional)">
            <textarea id="custom_info" placeholder="Custom business info..." rows="4"></textarea>
            
            <h3>Agent Personality</h3>
            <select id="personality">
                <option value="friendly">Friendly & Helpful</option>
                <option value="professional">Professional</option>
                <option value="enthusiastic">Enthusiastic</option>
            </select>
            
            <button type="submit">Save Customization</button>
        </form>
        
        <script>
            document.getElementById('customizeForm').addEventListener('submit', function(e) {
                e.preventDefault();
                
                const data = {
                    website_url: document.getElementById('website_url').value,
                    custom_info: document.getElementById('custom_info').value,
                    personality: document.getElementById('personality').value
                };
                
                fetch('/api/save-customization', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                })
                .then(response => response.json())
                .then(result => {
                    const message = document.getElementById('message');
                    message.style.display = 'block';
                    message.textContent = 'Customization saved successfully!';
                    message.style.background = '#d4edda';
                })
                .catch(error => {
                    const message = document.getElementById('message');
                    message.style.display = 'block';
                    message.textContent = 'Error saving customization';
                    message.style.background = '#f8d7da';
                });
            });
        </script>
        
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    '''

@app.route('/api/save-customization', methods=['POST'])
def save_customization():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    data = request.json
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO business_info 
            (user_id, website_url, custom_info, agent_personality) 
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], data.get('website_url'), data.get('custom_info'), data.get('personality', 'friendly')))
        conn.commit()
    
    return jsonify({'success': True})

# ==================== TESTING ====================
@app.route('/test-agent')
def test_agent():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT trial_uses, max_trial_uses FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        
        if user['trial_uses'] >= user['max_trial_uses']:
            return redirect(url_for('pricing'))
        
        c.execute('UPDATE users SET trial_uses = trial_uses + 1 WHERE id = ?', (session['user_id'],))
        conn.commit()
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Agent - LeaX</title>
        <style>
            body { font-family: Arial; max-width: 600px; margin: 40px auto; padding: 20px; }
            #chat { border: 1px solid #ddd; height: 300px; overflow-y: scroll; padding: 10px; margin: 20px 0; }
            .message { margin: 10px 0; padding: 10px; border-radius: 5px; }
            .user { background: #007cba; color: white; margin-left: 20%; }
            .agent { background: #f0f0f0; margin-right: 20%; }
            input { width: 70%; padding: 10px; }
            button { padding: 10px 20px; }
        </style>
    </head>
    <body>
        <h2>Test Your AI Agent</h2>
        <p>Try chatting with your AI agent to see how it responds!</p>
        
        <div id="chat"></div>
        
        <div>
            <input type="text" id="messageInput" placeholder="Type a message...">
            <button onclick="sendMessage()">Send</button>
        </div>
        
        <script>
            function addMessage(text, isUser) {
                const chat = document.getElementById('chat');
                const message = document.createElement('div');
                message.className = 'message ' + (isUser ? 'user' : 'agent');
                message.textContent = text;
                chat.appendChild(message);
                chat.scrollTop = chat.scrollTop + chat.scrollHeight;
            }
            
            function sendMessage() {
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                
                if (message) {
                    addMessage(message, true);
                    input.value = '';
                    
                    fetch('/api/test-chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({message: message})
                    })
                    .then(response => response.json())
                    .then(data => {
                        addMessage(data.reply, false);
                    });
                }
            }
            
            // Enter key to send
            document.getElementById('messageInput').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') sendMessage();
            });
        </script>
        
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    '''

@app.route('/api/test-chat', methods=['POST'])
def test_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    data = request.json
    user_message = data.get('message')
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM business_info WHERE user_id = ?', (session['user_id'],))
        business = c.fetchone()
    
    # SCAN WEBSITE FOR BUSINESS INFO - UPDATED
    business_services = []
    if business and business['website_url']:
        try:
            response = requests.get(business['website_url'])
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract services from website
            for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'li']):
                text = element.get_text().lower()
                service_keywords = ['service', 'solution', 'offer', 'provide', 'specializ', 'expert', 'install', 'build', 'repair', 'maintain']
                if any(keyword in text for keyword in service_keywords):
                    business_services.append(element.get_text().strip())
        except:
            pass
    
    business_context = f"""
BUSINESS: {session.get('business_name', 'American Power')}
WEBSITE: {business['website_url'] if business else ''}
SERVICES: {', '.join(business_services[:5]) if business_services else 'Electrical services, fiber optic installation, data center builds, networking solutions'}
CUSTOM INFO: {business['custom_info'] if business else 'We provide skilled workers for electrical, networking, and data center projects. Available 24/7 for emergency calls.'}
PERSONALITY: {business['agent_personality'] if business else 'professional'}
"""

    # ULTIMATE SALES CLOSING PROMPT - UPDATED
    prompt = f"""
You are a SALES CLOSER for {session.get('business_name', 'American Power')}. Your ONLY goal is to CLOSE THE SALE.

**BUSINESS CONTEXT:**
{business_context}

**YOUR MISSION:**
- Sound like a REAL HUMAN employee
- IDENTIFY the customer's specific need
- OFFER the exact service they need
- GET THEIR CONTACT INFO
- CLOSE THE SALE or SCHEDULE A CALL
- Be DIRECT and PROFESSIONAL

**CLOSING TECHNIQUES:**
- "Perfect! I have 2 available technicians for that Amazon locker build. What's the best number to confirm details?"
- "We specialize in fiber optic and data center work. Let me get your contact info to schedule our team."
- "We can definitely have those 10 end caps built by Tuesday 3pm. What's the project address?"
- "I'll have our project manager call you within 30 minutes to finalize. Keep your phone handy!"

**CURRENT CUSTOMER MESSAGE: {user_message}**

**YOUR RESPONSE (CLOSE THE SALE - 2-3 sentences max):**
"""
    
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=150
        )
        ai_reply = completion.choices[0].message.content
        
        # SEND EMAIL NOTIFICATION FOR LEADS - UPDATED
        send_email(
            "🚨 NEW LEAD - Action Required", 
            f"URGENT: New lead conversation\n\n"
            f"Business: {session.get('business_name')}\n"
            f"Customer Message: {user_message}\n"
            f"AI Response: {ai_reply}\n"
            f"Time: {datetime.now()}\n\n"
            f"ACTION: Follow up immediately to close this lead!"
        )
        
    except Exception as e:
        ai_reply = "Thanks for your inquiry! Our team will call you within 30 minutes to discuss your project. Please keep your phone handy."
    
    return jsonify({'reply': ai_reply})

# ==================== PRICING & PAYMENTS ====================
@app.route('/pricing')
def pricing():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pricing - LeaX</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }
            .pricing-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin: 40px 0; }
            .plan { border: 1px solid #ddd; padding: 30px; border-radius: 10px; text-align: center; }
            .btn { background: #007cba; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; }
            .pro { border-color: #007cba; background: #f0f8ff; }
        </style>
    </head>
    <body>
        <h2>Choose Your Plan</h2>
        
        <div class="pricing-grid">
            <div class="plan">
                <h3>Starter</h3>
                <h2>$29.99/month</h2>
                <ul style="text-align: left;">
                    <li>GPT-3.5 Turbo AI</li>
                    <li>Unlimited messages</li>
                    <li>Basic customization</li>
                    <li>Email support</li>
                </ul>
                <button onclick="selectPlan('starter')" class="btn">Select Starter</button>
            </div>
            
            <div class="plan pro">
                <h3>Professional</h3>
                <h2>$59.99/month</h2>
                <ul style="text-align: left;">
                    <li>GPT-4 AI</li>
                    <li>Unlimited messages</li>
                    <li>Advanced customization</li>
                    <li>Priority support</li>
                </ul>
                <button onclick="selectPlan('pro')" class="btn">Select Pro</button>
            </div>
        </div>
        
        <div id="paymentMessage" style="display: none; background: #d4edda; padding: 10px; margin: 20px 0;"></div>
        
        <script>
            function selectPlan(plan) {
                fetch('/create-payment', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({plan: plan})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.approval_url) {
                        window.location.href = data.approval_url;
                    } else {
                        document.getElementById('paymentMessage').style.display = 'block';
                        document.getElementById('paymentMessage').textContent = 'Payment setup failed';
                        document.getElementById('paymentMessage').style.background = '#f8d7da';
                    }
                });
            }
        </script>
        
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    '''

@app.route('/create-payment', methods=['POST'])
def create_payment():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    plan = request.json.get('plan', 'starter')
    
    payment = paypalrestsdk.Payment({
        "intent": "sale",
        "payer": {"payment_method": "paypal"},
        "redirect_urls": {
            "return_url": url_for('payment_success', _external=True),
            "cancel_url": url_for('payment_cancel', _external=True)
        },
        "transactions": [{
            "amount": {
                "total": "29.99" if plan == 'starter' else "59.99",
                "currency": "USD"
            },
            "description": f"LeaX {plan.title()} Plan"
        }]
    })
    
    if payment.create():
        session['payment_plan'] = plan
        for link in payment.links:
            if link.rel == "approval_url":
                return jsonify({'approval_url': link.href})
    
    return jsonify({'error': 'Payment creation failed'})

@app.route('/payment/success')
def payment_success():
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')
    
    payment = paypalrestsdk.Payment.find(payment_id)
    if payment.execute({"payer_id": payer_id}):
        with get_db() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET status = ?, plan_type = ? WHERE id = ?', 
                     ('active', session.get('payment_plan', 'starter'), session['user_id']))
            conn.commit()
        
        send_email(
            "LeaX Payment Received",
            f"Payment received from: {session.get('email')}\nPlan: {session.get('payment_plan')}\nAmount: ${'29.99' if session.get('payment_plan') == 'starter' else '59.99'}"
        )
        
        flash('Payment successful! Your AI agent is now active.')
        return redirect(url_for('dashboard'))
    
    flash('Payment failed')
    return redirect(url_for('pricing'))

@app.route('/payment/cancel')
def payment_cancel():
    flash('Payment was cancelled')
    return redirect(url_for('pricing'))

# ==================== ADMIN ====================
@app.route('/admin')
def admin():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) as total_users FROM users')
        total_users = c.fetchone()['total_users']
        
        c.execute('SELECT COUNT(*) as paid_users FROM users WHERE status != "trial"')
        paid_users = c.fetchone()['paid_users']
        
        c.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 10')
        recent_users = [dict(row) for row in c.fetchall()]
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>LeaX Admin</title>
        <style>
            body {{ font-family: Arial; margin: 20px; }}
            .stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin: 20px 0; }}
            .stat-card {{ background: #f5f5f5; padding: 20px; border-radius: 8px; text-align: center; }}
            .stat-number {{ font-size: 2em; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background: #f0f0f0; }}
        </style>
    </head>
    <body>
        <h1>LeaX Platform Admin</h1>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{total_users}</div>
                <div>Total Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{paid_users}</div>
                <div>Paid Users</div>
            </div>
        </div>

        <h2>Recent Users</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Email</th>
                <th>Business</th>
                <th>Plan</th>
                <th>Joined</th>
            </tr>
            {"".join(f'''
            <tr>
                <td>{user['id']}</td>
                <td>{user['email']}</td>
                <td>{user['business_name']}</td>
                <td>{user['plan_type']}</td>
                <td>{user['created_at']}</td>
            </tr>
            ''' for user in recent_users)}
        </table>

        <p><a href="/">Back to Site</a></p>
    </body>
    </html>
    '''

# ==================== AI AGENT ENDPOINT ====================
@app.route('/agent/<user_id>', methods=['POST'])
def ai_agent(user_id):
    """Live AI agent endpoint for paying customers"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = ? AND status != "trial"', (user_id,))
        user = c.fetchone()
        
        if not user:
            return "Agent not active", 404
        
        c.execute('SELECT * FROM business_info WHERE user_id = ?', (user_id,))
        business = c.fetchone()
    
    # Handle SMS
    if "SmsMessageSid" in request.form:
        incoming_msg = request.form.get('Body', '').strip()
        
        # SCAN WEBSITE FOR BUSINESS INFO - UPDATED FOR LIVE AGENT
        business_services = []
        if business and business['website_url']:
            try:
                response = requests.get(business['website_url'])
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract services from website
                for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'li']):
                    text = element.get_text().lower()
                    service_keywords = ['service', 'solution', 'offer', 'provide', 'specializ', 'expert', 'install', 'build', 'repair', 'maintain']
                    if any(keyword in text for keyword in service_keywords):
                        business_services.append(element.get_text().strip())
            except:
                pass
        
        business_context = f"""
BUSINESS: {user['business_name']}
WEBSITE: {business['website_url'] if business else ''}
SERVICES: {', '.join(business_services[:5]) if business_services else 'Electrical services, fiber optic installation, data center builds, networking solutions'}
CUSTOM INFO: {business['custom_info'] if business else 'We provide skilled workers for electrical, networking, and data center projects. Available 24/7 for emergency calls.'}
PERSONALITY: {business['agent_personality'] if business else 'professional'}
"""
        
        # ULTIMATE SALES CLOSING PROMPT - UPDATED FOR LIVE AGENT
        prompt = f"""
You are a SALES CLOSER for {user['business_name']}. Your ONLY goal is to CLOSE THE SALE.

**BUSINESS CONTEXT:**
{business_context}

**YOUR MISSION:**
- Sound like a REAL HUMAN employee
- IDENTIFY the customer's specific need
- OFFER the exact service they need
- GET THEIR CONTACT INFO
- CLOSE THE SALE or SCHEDULE A CALL
- Be DIRECT and PROFESSIONAL

**CLOSING TECHNIQUES:**
- "Perfect! I have 2 available technicians for that Amazon locker build. What's the best number to confirm details?"
- "We specialize in fiber optic and data center work. Let me get your contact info to schedule our team."
- "We can definitely have those 10 end caps built by Tuesday 3pm. What's the project address?"
- "I'll have our project manager call you within 30 minutes to finalize. Keep your phone handy!"

**CURRENT CUSTOMER MESSAGE: {incoming_msg}**

**YOUR RESPONSE (CLOSE THE SALE - 2-3 sentences max):**
"""
        
        try:
            completion = openai.ChatCompletion.create(
                model="gpt-4" if user['plan_type'] == 'pro' else "gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=150
            )
            ai_reply = completion.choices[0].message.content
            
            # Log conversation
            c.execute('''
                INSERT INTO conversations (user_id, phone_number, message_text, response_text, message_direction)
                VALUES (?, ?, ?, ?, 'incoming')
            ''', (user_id, request.form.get('From'), incoming_msg, ai_reply))
            conn.commit()
            
            # SEND EMAIL NOTIFICATION FOR LEADS - UPDATED FOR LIVE AGENT
            send_email(
                "🚨 NEW LEAD - Action Required", 
                f"URGENT: New lead conversation\n\n"
                f"Business: {user['business_name']}\n"
                f"Customer Phone: {request.form.get('From')}\n"
                f"Customer Message: {incoming_msg}\n"
                f"AI Response: {ai_reply}\n"
                f"Time: {datetime.now()}\n\n"
                f"ACTION: Follow up immediately to close this lead!"
            )
            
        except Exception as e:
            ai_reply = "Thanks for your message! We'll get back to you soon."
        
        resp = MessagingResponse()
        resp.message(ai_reply)
        return str(resp)
    
    # Handle Voice
    else:
        resp = VoiceResponse()
        resp.say(f"Thanks for calling {user['business_name']}! Text us at this number and we'll help you right away!")
        return str(resp)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info(f"LeaX Platform Starting - Database: {DATABASE_FILE}")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
