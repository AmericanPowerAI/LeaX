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
from email.mime.multipart import MIMEMultipart
import hashlib
import secrets
import logging
from contextlib import contextmanager

# 🆕 IMPORT MEMORY MANAGER
from memory_manager import MemoryManager

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
EMAIL_TO = os.environ.get('EMAIL_TO', 'hr@americanpower.us')
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.office365.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('EMAIL_PASSWORD')  # Updated to match your variable

# Database Configuration
DATABASE_FILE = os.environ.get('DATABASE_FILE', 'leax_users.db')

# 🆕 INITIALIZE MEMORY MANAGER
memory_mgr = MemoryManager()

# ==================== EMAIL NOTIFICATION SYSTEM ====================
class EmailNotifier:
    """Send comprehensive email notifications"""
    
    @staticmethod
    def send_notification(subject, html_content, text_content):
        """Send email notification"""
        try:
            if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD]):
                print("⚠️ Email config missing")
                return False
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = EMAIL_FROM
            msg['To'] = EMAIL_TO
            
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            
            msg.attach(part1)
            msg.attach(part2)
            
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            print(f"✅ Email sent: {subject}")
            return True
        except Exception as e:
            print(f"❌ Email failed: {e}")
            return False
    
    @staticmethod
    def notify_new_signup(user_data):
        """Notify about new customer signup"""
        subject = f"🎉 NEW SIGNUP: {user_data['business_name']}"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; margin: 20px;">
            <div style="background: #28a745; color: white; padding: 20px; border-radius: 10px;">
                <h1>🎉 NEW CUSTOMER SIGNUP!</h1>
            </div>
            <div style="background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px;">
                <h3>Customer Details</h3>
                <p><strong>Business Name:</strong> {user_data['business_name']}</p>
                <p><strong>Email:</strong> {user_data['email']}</p>
                <p><strong>User ID:</strong> {user_data['user_id']}</p>
                <p><strong>Plan:</strong> {user_data.get('plan_type', 'trial')}</p>
                <p><strong>Signup Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </body>
        </html>
        """
        
        text = f"""
NEW CUSTOMER SIGNUP
==================
Business: {user_data['business_name']}
Email: {user_data['email']}
User ID: {user_data['user_id']}
        """
        
        return EmailNotifier.send_notification(subject, html, text)
    
    @staticmethod
    def notify_conversation(user_data, conversation_data):
        """Notify about every message/call"""
        comm_type = conversation_data['type'].upper()
        subject = f"💬 {comm_type}: {user_data['business_name']}"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; margin: 20px;">
            <div style="background: #007cba; color: white; padding: 20px; border-radius: 10px;">
                <h1>💬 NEW {comm_type}</h1>
            </div>
            <div style="background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px;">
                <h3>Customer: {user_data['business_name']}</h3>
                <p><strong>From:</strong> {conversation_data['from_number']}</p>
                <p><strong>Content:</strong> {conversation_data['content']}</p>
            </div>
        </body>
        </html>
        """
        
        text = f"""
NEW {comm_type}: {user_data['business_name']}
From: {conversation_data['from_number']}
Content: {conversation_data['content']}
        """
        
        return EmailNotifier.send_notification(subject, html, text)

email_notifier = EmailNotifier()

# ==================== DATABASE ====================
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
    """Initialize database"""
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
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL,
                business_name TEXT,
                contact_name TEXT,
                project_type TEXT,
                urgency TEXT,
                budget TEXT,
                location TEXT,
                status TEXT DEFAULT 'new',
                lead_score INTEGER DEFAULT 0,
                last_contact TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                conversation_summary TEXT,
                needs_analysis TEXT,
                next_steps TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS lead_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message_text TEXT,
                response_text TEXT,
                message_type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                intent_detected TEXT,
                needs_identified TEXT,
                FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone_number)')
        
        conn.commit()

init_database()

# ==================== UTILITY FUNCTIONS ====================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def analyze_customer_intent(message):
    """Analyze customer message to extract key information"""
    prompt = f"""
    Analyze this customer message and extract structured information:
    
    MESSAGE: "{message}"
    
    Extract and return as JSON:
    - project_type: What type of project/work do they need?
    - urgency: How soon do they need it? (immediate, this_week, next_week, flexible)
    - potential_budget: Any budget indicators? (low, medium, high, enterprise)
    - location: Any location mentioned?
    - key_requirements: Specific requirements or specifications
    - contact_willingness: Are they willing to share contact info? (yes, no, maybe)
    
    Return ONLY valid JSON, no other text.
    """
    
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200
        )
        analysis = completion.choices[0].message.content
        return json.loads(analysis)
    except:
        return {
            "project_type": "general_inquiry",
            "urgency": "flexible",
            "potential_budget": "unknown",
            "location": "unknown",
            "key_requirements": "",
            "contact_willingness": "maybe"
        }

def calculate_lead_score(intent_analysis, message_length, has_contact_info):
    """Calculate lead quality score"""
    score = 0
    
    project_scores = {
        "emergency": 90,
        "immediate": 80,
        "urgent": 70,
        "specific_project": 60,
        "quote_request": 50,
        "general_inquiry": 30
    }
    
    score += project_scores.get(intent_analysis.get('project_type', 'general_inquiry'), 30)
    
    urgency_scores = {
        "immediate": 40,
        "this_week": 30,
        "next_week": 20,
        "flexible": 10
    }
    
    score += urgency_scores.get(intent_analysis.get('urgency', 'flexible'), 10)
    
    if intent_analysis.get('potential_budget') in ['high', 'enterprise']:
        score += 20
    elif intent_analysis.get('potential_budget') == 'medium':
        score += 10
    
    if has_contact_info:
        score += 30
    elif intent_analysis.get('contact_willingness') == 'yes':
        score += 20
    
    return min(score, 100)

def send_comprehensive_lead_email(lead_data, conversation_history, business_info):
    """Send detailed lead information"""
    try:
        if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD]):
            print("EMAIL CONFIG MISSING")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🚨 HOT LEAD: {lead_data.get('project_type', 'New Lead')} - {business_info.get('business_name', 'N/A')}"
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; margin: 20px;">
            <div style="background: #dc3545; color: white; padding: 20px; border-radius: 10px;">
                <h1>🚨 HOT LEAD - CALL NOW!</h1>
                <h2>Score: {lead_data.get('lead_score', 0)}/100</h2>
            </div>
            <div style="background: #fff3cd; padding: 15px; margin: 10px 0;">
                <h3>📋 LEAD DETAILS</h3>
                <p><strong>Business:</strong> {business_info.get('business_name', 'N/A')}</p>
                <p><strong>Phone:</strong> {lead_data.get('phone_number', 'N/A')}</p>
                <p><strong>Project:</strong> {lead_data.get('project_type', 'N/A')}</p>
                <p><strong>Urgency:</strong> {lead_data.get('urgency', 'N/A')}</p>
            </div>
            <div style="background: #f8f9fa; padding: 15px; margin: 10px 0;">
                <h3>📞 CALL THIS NUMBER NOW!</h3>
                <h2>{lead_data.get('phone_number', 'N/A')}</h2>
            </div>
        </body>
        </html>
        """
        
        text = f"""
HOT LEAD - CALL NOW!
===================
Business: {business_info.get('business_name', 'N/A')}
Phone: {lead_data.get('phone_number', 'N/A')}
Project: {lead_data.get('project_type', 'N/A')}
Urgency: {lead_data.get('urgency', 'N/A')}
        """
        
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ LEAD EMAIL SENT")
        return True
        
    except Exception as e:
        print(f"❌ EMAIL FAILED: {e}")
        return False

def update_lead_conversation(lead_id, user_id, message_text, response_text, intent_analysis):
    """Update lead conversation"""
    with get_db() as conn:
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO lead_conversations 
            (lead_id, user_id, message_text, response_text, intent_detected, needs_identified)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (lead_id, user_id, message_text, response_text, 
              json.dumps(intent_analysis), intent_analysis.get('key_requirements', '')))
        
        conn.commit()
        
        return {'lead_id': lead_id}

# ==================== 🔥 FIXED AI PROMPT - SOUNDS HUMAN ====================
def generate_human_response(business_name, business_context, customer_message, conversation_history=""):
    """
    Generate HUMAN-SOUNDING responses that CLOSE SALES
    This is the KEY to making money - AI sounds like a real person!
    """
    
    prompt = f"""You are Sarah, a friendly team member at {business_name}. You answer texts/calls like a real person would.

CRITICAL RULES:
1. NEVER say "I'll have someone call you" - YOU are that person! 
2. NEVER give generic responses
3. ASK SPECIFIC QUESTIONS to understand their exact needs
4. Give REAL answers with pricing, timing, availability
5. Sound conversational and natural
6. Use their exact words when responding
7. Get to the bottom of what they need FAST
8. CLOSE THE SALE by asking for commitment

BUSINESS INFO:
{business_context}

CONVERSATION SO FAR:
{conversation_history}

CURRENT CUSTOMER MESSAGE:
"{customer_message}"

NOW RESPOND LIKE A REAL HUMAN WHO WANTS TO CLOSE THIS DEAL:

EXAMPLES OF GOOD RESPONSES:
Customer: "I need 10 fixtures and end caps built how fast can you get it done?"
YOU: "Hey! I can get 10 fixtures with end caps done for you. When do you need them by? We usually do custom builds like this in 3-5 days. What's your project timeline and location?"

Customer: "Do you do electrical work?"
YOU: "Yes we do! What kind of electrical work are you looking for? New installation, repairs, or upgrades? And where's the job located?"

Customer: "How much for a service call?"
YOU: "Service calls are $125 which covers the first hour. What's going on that you need looked at? I can give you a better quote once I know what we're dealing with."

NOW RESPOND TO THE CUSTOMER ABOVE (2-3 sentences max, sound HUMAN):"""
    
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,  # Higher for more human-like variation
            max_tokens=150
        )
        return completion.choices[0].message.content, completion['usage']['total_tokens']
    except Exception as e:
        print(f"AI Error: {e}")
        # Fallback response that still sounds human
        return f"Hey! Thanks for reaching out to {business_name}. Can you tell me more about what you need? That way I can give you accurate pricing and timing.", 0

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
                        <li>Sounds Like Real Human</li>
                        <li>Closes Sales 24/7</li>
                        <li>Lead Tracking</li>
                        <li>3 Free Tests</li>
                    </ul>
                    <a href="/register" class="btn">Get Started</a>
                </div>
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
            
            memory_mgr.log_login(
                user_id=user['id'],
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password')
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - LeaX</title>
        <style>
            body { font-family: Arial; max-width: 400px; margin: 100px auto; padding: 20px; }
            input { width: 100%; padding: 10px; margin: 10px 0; }
            button { background: #007cba; color: white; padding: 12px 30px; border: none; cursor: pointer; width: 100%; }
        </style>
    </head>
    <body>
        <h2>Login to LeaX</h2>
        <form method="POST">
            <input type="email" name="email" placeholder="Email" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        <p><a href="/register">Sign up</a></p>
    </body>
    </html>
    '''

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
            <p><a href="/login">Login</a></p>
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
            
            memory_path = memory_mgr.create_customer_memory(
                user_id=user_id,
                business_name=business_name,
                email=email
            )
            
            session['user_id'] = user_id
            session['email'] = email
            session['business_name'] = business_name
            session['user_plan'] = 'starter'
            
            email_notifier.notify_new_signup({
                'user_id': user_id,
                'business_name': business_name,
                'email': email,
                'plan_type': 'trial'
            })
            
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
        
        c.execute('''
            SELECT COUNT(*) as total_leads, 
                   COUNT(CASE WHEN status = 'new' THEN 1 END) as new_leads,
                   COUNT(CASE WHEN lead_score >= 70 THEN 1 END) as hot_leads
            FROM leads WHERE user_id = ?
        ''', (session['user_id'],))
        lead_stats = c.fetchone()
    
    analytics = memory_mgr.get_customer_analytics(session['user_id'])
    
    user_dict = dict(user) if user else {}
    lead_stats_dict = dict(lead_stats) if lead_stats else {}
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - LeaX</title>
        <style>
            body {{ font-family: Arial; max-width: 1000px; margin: 40px auto; padding: 20px; }}
            .card {{ background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 8px; }}
            .btn {{ background: #007cba; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #007cba; }}
            .stat-number {{ font-size: 2em; font-weight: bold; color: #007cba; }}
        </style>
    </head>
    <body>
        <h1>Welcome, {session['business_name']}!</h1>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{lead_stats_dict.get('total_leads', 0)}</div>
                <div>Total Leads</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{analytics['total_messages'] if analytics else 0}</div>
                <div>Messages</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{analytics['total_calls'] if analytics else 0}</div>
                <div>Calls</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{lead_stats_dict.get('hot_leads', 0)}</div>
                <div>Hot Leads</div>
            </div>
        </div>
        
        <div class="card">
            <h3>Your Account</h3>
            <p><strong>Plan:</strong> {user_dict.get('plan_type', 'Starter')}</p>
            <p><strong>Status:</strong> {user_dict.get('status', 'Active')}</p>
            <p><strong>Trial Uses:</strong> {user_dict.get('trial_uses', 0)}/3</p>
        </div>
        
        <div class="card">
            <h3>Quick Actions</h3>
            <a href="/customize" class="btn">Customize Agent</a>
            <a href="/test-agent" class="btn">Test Agent</a>
            <a href="/leads" class="btn">View Leads</a>
            <a href="/analytics" class="btn">Analytics</a>
            <a href="/pricing" class="btn">Upgrade</a>
        </div>
        
        <p><a href="/logout">Logout</a></p>
    </body>
    </html>
    '''

# ==================== CUSTOMIZE AGENT ====================
@app.route('/customize')
def customize_agent():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Customize Agent</title>
        <style>
            body { font-family: Arial; max-width: 600px; margin: 40px auto; padding: 20px; }
            input, textarea, select { width: 100%; padding: 10px; margin: 10px 0; }
            button { background: #007cba; color: white; padding: 12px 30px; border: none; cursor: pointer; width: 100%; }
            .message { display: none; padding: 10px; margin: 10px 0; border-radius: 5px; }
            .success { background: #d4edda; color: #155724; }
        </style>
    </head>
    <body>
        <h2>Customize Your AI Agent</h2>
        
        <div id="message" class="message"></div>
        
        <form id="customizeForm">
            <h3>Business Information</h3>
            <input type="url" id="website_url" placeholder="Your website URL (optional)">
            <textarea id="custom_info" placeholder="Tell us about your business, services, pricing..." rows="6"></textarea>
            
            <h3>Agent Name (sounds more human)</h3>
            <input type="text" id="agent_name" placeholder="e.g., Sarah, Mike, etc." value="Sarah">
            
            <button type="submit">Save</button>
        </form>
        
        <script>
            document.getElementById('customizeForm').addEventListener('submit', function(e) {
                e.preventDefault();
                
                const data = {
                    website_url: document.getElementById('website_url').value,
                    custom_info: document.getElementById('custom_info').value,
                    agent_name: document.getElementById('agent_name').value
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
                    message.className = 'message success';
                    message.textContent = 'Saved!';
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
        ''', (session['user_id'], data.get('website_url'), 
              data.get('custom_info'), data.get('agent_name', 'Sarah')))
        conn.commit()
    
    memory_mgr.update_business_profile(session['user_id'], {
        'website_url': data.get('website_url'),
        'custom_info': data.get('custom_info'),
        'personality': data.get('agent_name', 'Sarah')
    })
    
    return jsonify({'success': True})

# ==================== TEST AGENT ====================
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
    
    return render_template('test_agent_modern.html')

@app.route('/api/test-chat', methods=['POST'])
def test_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    data = request.json
    user_message = data.get('message')
    
    # Get conversation history from memory
    conversation_context = memory_mgr.get_conversation_context(
        session['user_id'], 
        'TEST-USER',
        last_n_messages=5
    )
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM business_info WHERE user_id = ?', (session['user_id'],))
        business = c.fetchone()
    
    business_context = f"""
Business: {session.get('business_name')}
Services: {business['custom_info'] if business and business['custom_info'] else 'Full service provider - electrical, construction, installations'}
Website: {business['website_url'] if business and business['website_url'] else 'Not provided'}
"""
    
    # Generate HUMAN response
    ai_reply, tokens = generate_human_response(
        session.get('business_name'),
        business_context,
        user_message,
        conversation_context
    )
    
    # Log to memory
    memory_mgr.log_conversation(session['user_id'], {
        'type': 'sms',
        'direction': 'inbound',
        'from_number': 'TEST-USER',
        'to_number': 'AI-AGENT',
        'content': user_message,
        'ai_model': 'gpt-4',
        'tokens': tokens,
        'cost': tokens * 0.00003
    })
    
    memory_mgr.log_conversation(session['user_id'], {
        'type': 'sms',
        'direction': 'outbound',
        'from_number': 'AI-AGENT',
        'to_number': 'TEST-USER',
        'content': ai_reply,
        'ai_model': 'gpt-4',
        'tokens': 0,
        'cost': 0
    })
    
    return jsonify({'reply': ai_reply})

# ==================== LIVE AGENT ENDPOINT ====================
@app.route('/agent/<user_id>', methods=['POST'])
def ai_agent(user_id):
    """Live AI agent - handles SMS and VOICE CALLS"""
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
        from_number = request.form.get('From', '')
        to_number = request.form.get('To', '')
        
        # Get conversation history
        conversation_context = memory_mgr.get_conversation_context(
            user_id, 
            from_number,
            last_n_messages=10
        )
        
        business_context = f"""
Business: {user['business_name']}
Services: {business['custom_info'] if business and business['custom_info'] else 'Full service provider'}
Website: {business['website_url'] if business and business['website_url'] else ''}
"""
        
        # Generate HUMAN response
        ai_reply, tokens = generate_human_response(
            user['business_name'],
            business_context,
            incoming_msg,
            conversation_context
        )
        
        # Log to memory
        memory_mgr.log_conversation(user_id, {
            'type': 'sms',
            'direction': 'inbound',
            'from_number': from_number,
            'to_number': to_number,
            'content': incoming_msg,
            'ai_model': 'gpt-4',
            'tokens': tokens,
            'cost': tokens * 0.00003
        })
        
        memory_mgr.log_conversation(user_id, {
            'type': 'sms',
            'direction': 'outbound',
            'from_number': to_number,
            'to_number': from_number,
            'content': ai_reply,
            'ai_model': 'gpt-4',
            'tokens': 0,
            'cost': 0
        })
        
        # Send email notification
        email_notifier.notify_conversation({
            'business_name': user['business_name'],
            'email': user['email'],
            'user_id': user_id
        }, {
            'type': 'sms',
            'from_number': from_number,
            'to_number': to_number,
            'direction': 'inbound',
            'content': incoming_msg
        })
        
        # Create/Update Lead
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT id FROM leads WHERE phone_number = ? AND user_id = ?', (from_number, user_id))
            existing_lead = c.fetchone()
            
            intent_analysis = analyze_customer_intent(incoming_msg)
            
            if not existing_lead:
                lead_score = calculate_lead_score(intent_analysis, len(incoming_msg), False)
                
                c.execute('''
                    INSERT INTO leads 
                    (user_id, phone_number, project_type, urgency, status, lead_score)
                    VALUES (?, ?, ?, ?, 'new', ?)
                ''', (user_id, from_number, 
                      intent_analysis.get('project_type', 'inquiry'),
                      intent_analysis.get('urgency', 'flexible'),
                      lead_score))
                
                lead_id = c.lastrowid
                conn.commit()
                
                # Send lead email
                c.execute('SELECT * FROM leads WHERE id = ?', (lead_id,))
                lead_data = dict(c.fetchone())
                
                send_comprehensive_lead_email(lead_data, [], {'business_name': user['business_name']})
        
        resp = MessagingResponse()
        resp.message(ai_reply)
        return str(resp)
    
    # Handle VOICE CALLS
    else:
        from_number = request.form.get('From', '')
        to_number = request.form.get('To', '')
        
        # Get conversation history for context
        conversation_context = memory_mgr.get_conversation_context(
            user_id, 
            from_number,
            last_n_messages=5
        )
        
        business_context = f"""
Business: {user['business_name']}
Services: {business['custom_info'] if business and business['custom_info'] else 'Full service provider'}
"""
        
        # Generate greeting for voice call
        greeting, tokens = generate_human_response(
            user['business_name'],
            business_context,
            "Incoming phone call - greet them professionally",
            conversation_context
        )
        
        # Log call to memory
        memory_mgr.log_conversation(user_id, {
            'type': 'call',
            'direction': 'inbound',
            'from_number': from_number,
            'to_number': to_number,
            'content': f"Voice call from {from_number}",
            'duration': 0,
            'ai_model': 'voice',
            'tokens': 0,
            'cost': 0.01
        })
        
        resp = VoiceResponse()
        
        # Answer with human-like greeting
        resp.say(
            f"Hi! You've reached {user['business_name']}. For fastest service, please text us at this number and we'll get right back to you with pricing and availability. Or stay on the line and we'll connect you shortly.",
            voice='alice',
            language='en-US'
        )
        
        # Gather input if they want to leave a message
        gather = Gather(num_digits=1, action=f'/agent/{user_id}/voice-menu', method='POST')
        gather.say('Press 1 to leave a message, or press 2 to text us instead.', voice='alice')
        resp.append(gather)
        
        return str(resp)

@app.route('/agent/<user_id>/voice-menu', methods=['POST'])
def voice_menu(user_id):
    """Handle voice call menu"""
    digit = request.form.get('Digits', '')
    
    resp = VoiceResponse()
    
    if digit == '1':
        resp.say('Please leave your message after the beep, and we will call you back shortly.', voice='alice')
        resp.record(max_length=60, action=f'/agent/{user_id}/voicemail', method='POST')
    elif digit == '2':
        from_number = request.form.get('From', '')
        resp.say(f'Great! Text this number and we will respond right away. The number again is {to_number}. Thanks!', voice='alice')
    else:
        resp.say('Sorry, I did not get that. Please call back or text us. Goodbye!', voice='alice')
    
    resp.hangup()
    return str(resp)

@app.route('/agent/<user_id>/voicemail', methods=['POST'])
def handle_voicemail(user_id):
    """Handle voicemail recording"""
    recording_url = request.form.get('RecordingUrl', '')
    from_number = request.form.get('From', '')
    
    # Send email notification about voicemail
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = c.fetchone()
        
        if user:
            email_notifier.send_notification(
                f"📞 VOICEMAIL: {user['business_name']}",
                f"<p>New voicemail from {from_number}</p><p><a href='{recording_url}'>Listen to recording</a></p>",
                f"Voicemail from {from_number}\nRecording: {recording_url}"
            )
    
    resp = VoiceResponse()
    resp.say('Thank you! We received your message and will call you back soon.', voice='alice')
    resp.hangup()
    return str(resp)

# ==================== LEADS ====================
@app.route('/leads')
def view_leads():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT * FROM leads 
            WHERE user_id = ? 
            ORDER BY lead_score DESC, last_contact DESC
            LIMIT 50
        ''', (session['user_id'],))
        leads = [dict(row) for row in c.fetchall()]
    
    leads_html = ""
    for lead in leads:
        score_color = "#dc3545" if lead['lead_score'] >= 70 else "#fd7e14" if lead['lead_score'] >= 50 else "#666"
        leads_html += f'''
        <div style="background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid {score_color};">
            <h3>📞 {lead['phone_number']} <span style="color: {score_color};">({lead['lead_score']}/100)</span></h3>
            <p><strong>Project:</strong> {lead['project_type']}</p>
            <p><strong>Urgency:</strong> {lead['urgency']}</p>
            <p><strong>Status:</strong> {lead['status']}</p>
            <p><strong>Last Contact:</strong> {lead['last_contact']}</p>
        </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Leads</title>
        <style>
            body {{ font-family: Arial; max-width: 1000px; margin: 40px auto; padding: 20px; }}
        </style>
    </head>
    <body>
        <h1>Your Leads - {session['business_name']}</h1>
        <p>Total: {len(leads)}</p>
        
        {leads_html if leads else '<p>No leads yet. Test your agent to see it in action!</p>'}
        
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    '''

# ==================== ANALYTICS ====================
@app.route('/analytics')
def analytics():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    analytics_data = memory_mgr.get_customer_analytics(session['user_id'])
    memory = memory_mgr.load_customer_memory(session['user_id'])
    recent_convos = memory['conversation_history'][-20:] if memory else []
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Analytics</title>
        <style>
            body {{ font-family: Arial; max-width: 1200px; margin: 40px auto; padding: 20px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
            .stat-number {{ font-size: 2.5em; font-weight: bold; color: #007cba; }}
            .activity-log {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>Analytics - {session['business_name']}</h1>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{analytics_data['total_conversations']}</div>
                <div>Conversations</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{analytics_data['total_messages']}</div>
                <div>Messages</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{analytics_data['total_calls']}</div>
                <div>Calls</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{analytics_data['leads_captured']}</div>
                <div>Leads</div>
            </div>
        </div>
        
        <h2>Recent Activity</h2>
        {"".join([f'''
        <div class="activity-log">
            <strong>{convo.get('timestamp', 'N/A')[:19]}</strong> - 
            {convo.get('type', 'N/A').upper()} from {convo.get('from', 'N/A')}
            <br>
            <em>{convo.get('content', 'N/A')[:100]}...</em>
        </div>
        ''' for convo in recent_convos])}
        
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    '''

# ==================== PRICING ====================
@app.route('/pricing')
def pricing():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pricing</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }
            .pricing-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin: 40px 0; }
            .plan { border: 1px solid #ddd; padding: 30px; border-radius: 10px; text-align: center; }
            .btn { background: #007cba; color: white; padding: 15px 30px; border-radius: 5px; border: none; cursor: pointer; }
        </style>
    </head>
    <body>
        <h2>Choose Your Plan</h2>
        
        <div class="pricing-grid">
            <div class="plan">
                <h3>Starter</h3>
                <h2>$29.99/month</h2>
                <ul style="text-align: left;">
                    <li>GPT-4 AI Agent</li>
                    <li>Sounds Human</li>
                    <li>Unlimited messages/calls</li>
                    <li>Lead tracking</li>
                </ul>
                <button onclick="alert('Contact us to activate')" class="btn">Select</button>
            </div>
            
            <div class="plan" style="border-color: #007cba; background: #f0f8ff;">
                <h3>Professional</h3>
                <h2>$59.99/month</h2>
                <ul style="text-align: left;">
                    <li>Everything in Starter</li>
                    <li>Priority support</li>
                    <li>Custom training</li>
                    <li>Advanced analytics</li>
                </ul>
                <button onclick="alert('Contact us to activate')" class="btn">Select</button>
            </div>
        </div>
        
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    '''

# ==================== ADMIN ====================
@app.route('/admin')
def admin():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) as total FROM users')
        total_users = c.fetchone()['total']
        
        c.execute('SELECT COUNT(*) as paid FROM users WHERE status != "trial"')
        paid_users = c.fetchone()['paid']
        
        c.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 10')
        recent_users = [dict(row) for row in c.fetchall()]
    
    platform_stats = memory_mgr.get_total_usage_stats()
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin</title>
        <style>
            body {{ font-family: Arial; margin: 20px; }}
            .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
            .stat-card {{ background: #f5f5f5; padding: 20px; border-radius: 8px; text-align: center; }}
            .stat-number {{ font-size: 2em; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background: #f0f0f0; }}
        </style>
    </head>
    <body>
        <h1>LeaX Admin</h1>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{total_users}</div>
                <div>Total Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{paid_users}</div>
                <div>Paid Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{platform_stats['total_conversations']}</div>
                <div>Conversations</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">${platform_stats['total_cost_usd']:.2f}</div>
                <div>API Costs</div>
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

        <p><a href="/">Back</a></p>
    </body>
    </html>
    '''

# ==================== RUN ====================
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info(f"🚀 LeaX Starting - Database: {DATABASE_FILE}")
    logging.info(f"✅ Memory Manager Initialized")
    logging.info(f"✅ HUMAN AI Responses Active")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
