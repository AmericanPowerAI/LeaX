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
    """Initialize database with comprehensive lead tracking"""
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
        
        # NEW: Comprehensive leads table
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
        
        # NEW: Lead conversations history
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
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_business_info_user_id ON business_info(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone_number)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)')
        
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
    
    # Project type scoring
    project_scores = {
        "emergency": 90,
        "immediate": 80,
        "urgent": 70,
        "specific_project": 60,
        "quote_request": 50,
        "general_inquiry": 30
    }
    
    score += project_scores.get(intent_analysis.get('project_type', 'general_inquiry'), 30)
    
    # Urgency scoring
    urgency_scores = {
        "immediate": 40,
        "this_week": 30,
        "next_week": 20,
        "flexible": 10
    }
    
    score += urgency_scores.get(intent_analysis.get('urgency', 'flexible'), 10)
    
    # Budget scoring
    if intent_analysis.get('potential_budget') in ['high', 'enterprise']:
        score += 20
    elif intent_analysis.get('potential_budget') == 'medium':
        score += 10
    
    # Contact willingness
    if has_contact_info:
        score += 30
    elif intent_analysis.get('contact_willingness') == 'yes':
        score += 20
    
    return min(score, 100)

def send_comprehensive_lead_email(lead_data, conversation_history, business_info):
    """Send detailed lead information with conversation context"""
    try:
        if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD]):
            print("EMAIL CONFIG MISSING - Check Railway Variables")
            return False
        
        # Create HTML email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🚨 HOT LEAD: {lead_data['project_type']} - {lead_data['business_name']}"
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        
        # HTML content
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #dc3545; color: white; padding: 20px; border-radius: 10px; }}
                .section {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                .urgent {{ background: #fff3cd; border-left: 4px solid #ffc107; }}
                .conversation {{ background: white; border: 1px solid #ddd; }}
                .customer {{ background: #e7f3ff; padding: 8px; margin: 5px; }}
                .agent {{ background: #f0f0f0; padding: 8px; margin: 5px; }}
                .score-high {{ color: #dc3545; font-weight: bold; }}
                .score-medium {{ color: #fd7e14; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🚨 NEW HOT LEAD - ACTION REQUIRED</h1>
                <h2>Lead Score: <span class="score-high">{lead_data['lead_score']}/100</span></h2>
            </div>
            
            <div class="section urgent">
                <h3>📋 LEAD SUMMARY</h3>
                <p><strong>Business:</strong> {business_info['business_name']}</p>
                <p><strong>Client Phone:</strong> {lead_data['phone_number']}</p>
                <p><strong>Project Type:</strong> {lead_data['project_type'].title()}</p>
                <p><strong>Urgency:</strong> {lead_data['urgency'].title()}</p>
                <p><strong>Location:</strong> {lead_data.get('location', 'Not specified')}</p>
                <p><strong>Budget Level:</strong> {lead_data.get('budget', 'Not specified')}</p>
                <p><strong>Status:</strong> {lead_data['status'].title()}</p>
            </div>
            
            <div class="section">
                <h3>🎯 NEEDS ANALYSIS</h3>
                <p>{lead_data['needs_analysis']}</p>
            </div>
            
            <div class="section">
                <h3>✅ NEXT STEPS</h3>
                <p>{lead_data['next_steps']}</p>
            </div>
            
            <div class="section">
                <h3>💬 COMPLETE CONVERSATION</h3>
                <div class="conversation">
        """
        
        for conv in conversation_history:
            if conv['message_direction'] == 'incoming':
                html += f'<div class="customer"><strong>Customer:</strong> {conv["message_text"]}</div>'
            else:
                html += f'<div class="agent"><strong>Agent:</strong> {conv["response_text"]}</div>'
        
        html += f"""
                </div>
            </div>
            
            <div class="section">
                <h3>📞 IMMEDIATE ACTION REQUIRED</h3>
                <p><strong>Call this lead NOW:</strong> {lead_data['phone_number']}</p>
                <p><strong>Reference:</strong> {lead_data['project_type']} project for {business_info['business_name']}</p>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text = f"""
URGENT LEAD - ACTION REQUIRED
=============================

Lead Score: {lead_data['lead_score']}/100

BUSINESS: {business_info['business_name']}
CLIENT PHONE: {lead_data['phone_number']}
PROJECT TYPE: {lead_data['project_type']}
URGENCY: {lead_data['urgency']}
LOCATION: {lead_data.get('location', 'Not specified')}

NEEDS ANALYSIS:
{lead_data['needs_analysis']}

NEXT STEPS:
{lead_data['next_steps']}

CONVERSATION HISTORY:
{"-" * 50}
"""
        
        for conv in conversation_history:
            if conv['message_direction'] == 'incoming':
                text += f"CUSTOMER: {conv['message_text']}\n"
            else:
                text += f"AGENT: {conv['response_text']}\n"
        
        text += f"""
{"-" * 50}

IMMEDIATE ACTION:
• Call {lead_data['phone_number']} NOW
• Reference: {lead_data['project_type']} project
• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # Attach both versions
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ COMPREHENSIVE LEAD EMAIL SENT: {lead_data['phone_number']}")
        return True
        
    except Exception as e:
        print(f"❌ LEAD EMAIL FAILED: {e}")
        return False

def update_lead_conversation(lead_id, user_id, message_text, response_text, intent_analysis):
    """Update lead with new conversation and analysis"""
    with get_db() as conn:
        c = conn.cursor()
        
        # Insert conversation
        c.execute('''
            INSERT INTO lead_conversations 
            (lead_id, user_id, message_text, response_text, intent_detected, needs_identified)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (lead_id, user_id, message_text, response_text, 
              json.dumps(intent_analysis), intent_analysis.get('key_requirements', '')))
        
        # Update lead summary and score
        c.execute('''
            SELECT message_text, response_text 
            FROM lead_conversations 
            WHERE lead_id = ? 
            ORDER BY timestamp
        ''', (lead_id,))
        
        conversations = c.fetchall()
        full_conversation = "\n".join([
            f"Customer: {conv['message_text']}\nAgent: {conv['response_text']}" 
            for conv in conversations
        ])
        
        # Generate updated analysis
        analysis_prompt = f"""
        Based on this entire conversation, provide a comprehensive analysis:
        
        CONVERSATION:
        {full_conversation}
        
        Provide:
        1. Clear project requirements summary
        2. Customer's main pain points
        3. Urgency level assessment
        4. Recommended next steps for sales team
        
        Keep it concise but comprehensive.
        """
        
        try:
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=0.3,
                max_tokens=300
            )
            needs_analysis = completion.choices[0].message.content
        except:
            needs_analysis = "Analysis pending - review conversation history"
        
        # Calculate updated lead score
        has_contact = any(word in full_conversation.lower() for word in ['call', 'phone', 'contact', 'number', 'reach'])
        lead_score = calculate_lead_score(intent_analysis, len(message_text), has_contact)
        
        # Update lead record
        c.execute('''
            UPDATE leads 
            SET conversation_summary = ?, needs_analysis = ?, lead_score = ?,
                next_steps = ?, last_contact = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (full_conversation, needs_analysis, lead_score, 
              f"Call customer to discuss {intent_analysis.get('project_type', 'project')}", lead_id))
        
        conn.commit()
        
        return {
            'lead_id': lead_id,
            'needs_analysis': needs_analysis,
            'lead_score': lead_score
        }

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
            
            send_comprehensive_lead_email(
                {
                    'phone_number': 'New Registration',
                    'project_type': 'Account Setup',
                    'urgency': 'low',
                    'business_name': business_name,
                    'lead_score': 10,
                    'status': 'new',
                    'needs_analysis': f'New user registration: {email}',
                    'next_steps': 'Welcome new user and assist with setup'
                },
                [],
                {'business_name': business_name}
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
        
        # Get lead stats
        c.execute('''
            SELECT COUNT(*) as total_leads, 
                   COUNT(CASE WHEN status = 'new' THEN 1 END) as new_leads,
                   COUNT(CASE WHEN lead_score >= 70 THEN 1 END) as hot_leads
            FROM leads WHERE user_id = ?
        ''', (session['user_id'],))
        lead_stats = c.fetchone()
    
    user_dict = dict(user) if user else {}
    business_dict = dict(business) if business else {}
    lead_stats_dict = dict(lead_stats) if lead_stats else {}
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - LeaX</title>
        <style>
            body {{ font-family: Arial; max-width: 1000px; margin: 40px auto; padding: 20px; }}
            .card {{ background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 8px; }}
            .btn {{ background: #007cba; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #007cba; }}
            .stat-number {{ font-size: 2em; font-weight: bold; color: #007cba; }}
        </style>
    </head>
    <body>
        <h1>Welcome to LeaX, {session['business_name']}!</h1>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{lead_stats_dict.get('total_leads', 0)}</div>
                <div>Total Leads</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{lead_stats_dict.get('new_leads', 0)}</div>
                <div>New Leads</div>
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
            <p><a href="/customize" class="btn">Customize Agent</a></p>
            <p><a href="/test-agent" class="btn">Test Your Agent</a></p>
            <p><a href="/leads" class="btn">View Leads</a></p>
            <p><a href="/pricing" class="btn">Upgrade Plan</a></p>
        </div>
        
        <p><a href="/logout">Logout</a></p>
    </body>
    </html>
    '''

# ==================== LEADS MANAGEMENT ====================
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
        ''', (session['user_id'],))
        leads = [dict(row) for row in c.fetchall()]
    
    leads_html = ""
    for lead in leads:
        score_color = "score-high" if lead['lead_score'] >= 70 else "score-medium" if lead['lead_score'] >= 50 else ""
        leads_html += f'''
        <div class="lead-card">
            <h3>📞 {lead['phone_number']} <span class="{score_color}">({lead['lead_score']}/100)</span></h3>
            <p><strong>Project:</strong> {lead['project_type']}</p>
            <p><strong>Urgency:</strong> {lead['urgency']}</p>
            <p><strong>Status:</strong> {lead['status']}</p>
            <p><strong>Last Contact:</strong> {lead['last_contact']}</p>
            <button onclick="viewLeadDetails({lead['id']})">View Details</button>
        </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Leads - LeaX</title>
        <style>
            body {{ font-family: Arial; max-width: 1000px; margin: 40px auto; padding: 20px; }}
            .lead-card {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #007cba; }}
            .score-high {{ color: #dc3545; font-weight: bold; }}
            .score-medium {{ color: #fd7e14; font-weight: bold; }}
            .btn {{ background: #007cba; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; border: none; cursor: pointer; }}
        </style>
    </head>
    <body>
        <h1>Your Leads - {session['business_name']}</h1>
        <p>Total Leads: {len(leads)}</p>
        
        <div id="leadsList">
            {leads_html if leads else '<p>No leads yet. Start testing your agent or go live to capture leads!</p>'}
        </div>
        
        <div id="leadDetails" style="display: none; margin-top: 20px; padding: 20px; background: white; border: 1px solid #ddd;"></div>
        
        <script>
            function viewLeadDetails(leadId) {{
                fetch(`/api/lead-details/${{leadId}}`)
                    .then(response => response.json())
                    .then(lead => {{
                        const detailsDiv = document.getElementById('leadDetails');
                        detailsDiv.style.display = 'block';
                        detailsDiv.innerHTML = `
                            <h2>Lead Details</h2>
                            <p><strong>Phone:</strong> ${{lead.phone_number}}</p>
                            <p><strong>Project:</strong> ${{lead.project_type}}</p>
                            <p><strong>Urgency:</strong> ${{lead.urgency}}</p>
                            <p><strong>Location:</strong> ${{lead.location || 'Not specified'}}</p>
                            <p><strong>Lead Score:</strong> ${{lead.lead_score}}/100</p>
                            <p><strong>Needs Analysis:</strong></p>
                            <div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">${{lead.needs_analysis}}</div>
                            <p><strong>Next Steps:</strong> ${{lead.next_steps}}</p>
                            <button class="btn" onclick="document.getElementById('leadDetails').style.display='none'">Close</button>
                        `;
                    }});
            }}
        </script>
        
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    '''

@app.route('/api/lead-details/<int:lead_id>')
def get_lead_details(lead_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM leads WHERE id = ? AND user_id = ?', (lead_id, session['user_id']))
        lead = c.fetchone()
        
        if lead:
            return jsonify(dict(lead))
        else:
            return jsonify({'error': 'Lead not found'})

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
                chat.scrollTop = chat.scrollHeight;
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
    
    # SCAN WEBSITE FOR BUSINESS INFO
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

    # Analyze customer intent for lead tracking
    intent_analysis = analyze_customer_intent(user_message)
    
    # ULTIMATE SALES CLOSING PROMPT
    prompt = f"""
You are a SALES CLOSER for {session.get('business_name', 'American Power')}. Your ONLY goal is to CLOSE THE SALE.

**BUSINESS CONTEXT:**
{business_context}

**CUSTOMER ANALYSIS:**
Project Type: {intent_analysis.get('project_type', 'general inquiry')}
Urgency: {intent_analysis.get('urgency', 'flexible')}
Key Requirements: {intent_analysis.get('key_requirements', 'Not specified')}

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
        
        # CREATE OR UPDATE LEAD
        test_phone = "TEST-" + str(int(time.time()))[-6:]
        with get_db() as conn:
            c = conn.cursor()
            
            # Check if test lead exists
            c.execute('SELECT id FROM leads WHERE phone_number = ? AND user_id = ?', (test_phone, session['user_id']))
            existing_lead = c.fetchone()
            
            if existing_lead:
                lead_id = existing_lead['id']
                # Update existing test lead
                update_result = update_lead_conversation(lead_id, session['user_id'], user_message, ai_reply, intent_analysis)
            else:
                # Create new test lead
                lead_score = calculate_lead_score(intent_analysis, len(user_message), False)
                
                c.execute('''
                    INSERT INTO leads 
                    (user_id, phone_number, project_type, urgency, budget, location, status, lead_score, conversation_summary)
                    VALUES (?, ?, ?, ?, ?, ?, 'test', ?, ?)
                ''', (session['user_id'], test_phone, 
                      intent_analysis.get('project_type', 'general_inquiry'),
                      intent_analysis.get('urgency', 'flexible'),
                      intent_analysis.get('potential_budget', 'unknown'),
                      intent_analysis.get('location', 'unknown'),
                      lead_score,
                      f"Test conversation: {user_message}"))
                
                lead_id = c.lastrowid
                
                # Add to conversation history
                c.execute('''
                    INSERT INTO lead_conversations 
                    (lead_id, user_id, message_text, response_text, intent_detected, needs_identified)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (lead_id, session['user_id'], user_message, ai_reply, 
                      json.dumps(intent_analysis), intent_analysis.get('key_requirements', '')))
                
                conn.commit()
            
            # Get conversation history for email
            c.execute('''
                SELECT message_text, response_text, message_direction 
                FROM lead_conversations 
                WHERE lead_id = ? 
                ORDER BY timestamp
            ''', (lead_id,))
            conversation_history = [dict(row) for row in c.fetchall()]
            
            # Get lead data for email
            c.execute('SELECT * FROM leads WHERE id = ?', (lead_id,))
            lead_data = dict(c.fetchone())
        
        # SEND COMPREHENSIVE LEAD EMAIL
        business_info = {
            'business_name': session.get('business_name', 'Test Business')
        }
        send_comprehensive_lead_email(lead_data, conversation_history, business_info)
        
    except Exception as e:
        print(f"Error in test chat: {e}")
        ai_reply = "Thanks for your inquiry! Our team will call you within 30 minutes to discuss your project. Please keep your phone handy."
    
    return jsonify({'reply': ai_reply})

# ==================== LIVE AGENT ENDPOINT ====================
@app.route('/agent/<user_id>', methods=['POST'])
def ai_agent(user_id):
    """Live AI agent endpoint for paying customers with comprehensive lead tracking"""
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
        
        # SCAN WEBSITE FOR BUSINESS INFO
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
        
        # Analyze customer intent for lead tracking
        intent_analysis = analyze_customer_intent(incoming_msg)
        
        # ULTIMATE SALES CLOSING PROMPT
        prompt = f"""
You are a SALES CLOSER for {user['business_name']}. Your ONLY goal is to CLOSE THE SALE.

**BUSINESS CONTEXT:**
{business_context}

**CUSTOMER ANALYSIS:**
Project Type: {intent_analysis.get('project_type', 'general inquiry')}
Urgency: {intent_analysis.get('urgency', 'flexible')}
Key Requirements: {intent_analysis.get('key_requirements', 'Not specified')}

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
            
            # CREATE OR UPDATE LEAD
            c.execute('SELECT id FROM leads WHERE phone_number = ? AND user_id = ?', (from_number, user_id))
            existing_lead = c.fetchone()
            
            if existing_lead:
                lead_id = existing_lead['id']
                # Update existing lead
                update_result = update_lead_conversation(lead_id, user_id, incoming_msg, ai_reply, intent_analysis)
                lead_data = update_result
            else:
                # Create new lead
                has_contact_info = any(word in incoming_msg.lower() for word in ['call', 'phone', 'contact', 'number', 'reach'])
                lead_score = calculate_lead_score(intent_analysis, len(incoming_msg), has_contact_info)
                
                c.execute('''
                    INSERT INTO leads 
                    (user_id, phone_number, project_type, urgency, budget, location, status, lead_score)
                    VALUES (?, ?, ?, ?, ?, ?, 'new', ?)
                ''', (user_id, from_number, 
                      intent_analysis.get('project_type', 'general_inquiry'),
                      intent_analysis.get('urgency', 'flexible'),
                      intent_analysis.get('potential_budget', 'unknown'),
                      intent_analysis.get('location', 'unknown'),
                      lead_score))
                
                lead_id = c.lastrowid
                
                # Add to conversation history
                c.execute('''
                    INSERT INTO lead_conversations 
                    (lead_id, user_id, message_text, response_text, intent_detected, needs_identified)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (lead_id, user_id, incoming_msg, ai_reply, 
                      json.dumps(intent_analysis), intent_analysis.get('key_requirements', '')))
                
                # Generate initial analysis
                analysis_prompt = f"""
                New lead inquiry: {incoming_msg}
                
                Project Type: {intent_analysis.get('project_type')}
                Urgency: {intent_analysis.get('urgency')}
                Requirements: {intent_analysis.get('key_requirements')}
                
                Provide a quick analysis of this lead's needs and recommended next steps.
                """
                
                try:
                    completion = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": analysis_prompt}],
                        temperature=0.3,
                        max_tokens=200
                    )
                    needs_analysis = completion.choices[0].message.content
                except:
                    needs_analysis = "New lead - review conversation"
                
                c.execute('''
                    UPDATE leads 
                    SET needs_analysis = ?, next_steps = ?
                    WHERE id = ?
                ''', (needs_analysis, f"Call to discuss {intent_analysis.get('project_type', 'project')}", lead_id))
                
                conn.commit()
                
                lead_data = {
                    'lead_id': lead_id,
                    'needs_analysis': needs_analysis,
                    'lead_score': lead_score
                }
            
            # Get conversation history for email
            c.execute('''
                SELECT message_text, response_text, message_direction 
                FROM lead_conversations 
                WHERE lead_id = ? 
                ORDER BY timestamp
            ''', (lead_id,))
            conversation_history = [dict(row) for row in c.fetchall()]
            
            # Get complete lead data for email
            c.execute('SELECT * FROM leads WHERE id = ?', (lead_id,))
            complete_lead_data = dict(c.fetchone())
            
            # SEND COMPREHENSIVE LEAD EMAIL
            business_info = {
                'business_name': user['business_name']
            }
            send_comprehensive_lead_email(complete_lead_data, conversation_history, business_info)
            
        except Exception as e:
            print(f"Error in live agent: {e}")
            ai_reply = "Thanks for your message! We'll get back to you soon."
        
        resp = MessagingResponse()
        resp.message(ai_reply)
        return str(resp)
    
    # Handle Voice
    else:
        resp = VoiceResponse()
        resp.say(f"Thanks for calling {user['business_name']}! Text us at this number and we'll help you right away!")
        return str(resp)

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
        
        send_comprehensive_lead_email(
            {
                'phone_number': 'Payment System',
                'project_type': 'Plan Upgrade',
                'urgency': 'low',
                'business_name': session.get('business_name'),
                'lead_score': 5,
                'status': 'upgrade',
                'needs_analysis': f'User upgraded to {session.get("payment_plan")} plan',
                'next_steps': 'Activate premium features'
            },
            [],
            {'business_name': session.get('business_name')}
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
        
        c.execute('SELECT COUNT(*) as total_leads FROM leads')
        total_leads = c.fetchone()['total_leads']
        
        c.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 10')
        recent_users = [dict(row) for row in c.fetchall()]
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>LeaX Admin</title>
        <style>
            body {{ font-family: Arial; margin: 20px; }}
            .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; }}
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
            <div class="stat-card">
                <div class="stat-number">{total_leads}</div>
                <div>Total Leads</div>
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

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info(f"LeaX Platform Starting - Database: {DATABASE_FILE}")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
