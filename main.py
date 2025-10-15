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
from email.mime.text import MimeText
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = 'leax-secret-key-2024'  # Change in production!

# ==================== CONFIGURATION ====================
openai.api_key = os.environ.get('OPENAI_API_KEY')

# PayPal Configuration
paypalrestsdk.configure({
    "mode": "sandbox",
    "client_id": os.environ.get('PAYPAL_CLIENT_ID'),
    "client_secret": os.environ.get('PAYPAL_CLIENT_SECRET')
})

# Email Configuration
EMAIL_FROM = "admin@americanpower.us"
EMAIL_TO = "systems@americanpower.us"
SMTP_SERVER = "smtp.office365.com"  # For Outlook/Office365
SMTP_PORT = 587
SMTP_USERNAME = "admin@americanpower.us"
SMTP_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         email TEXT UNIQUE,
         password_hash TEXT,
         business_name TEXT,
         status TEXT DEFAULT 'trial',
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         trial_uses INTEGER DEFAULT 0,
         max_trial_uses INTEGER DEFAULT 3)
    ''')
    
    # Business info table
    c.execute('''
        CREATE TABLE IF NOT EXISTS business_info
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         user_id INTEGER,
         website_url TEXT,
         services TEXT,
         custom_info TEXT,
         agent_personality TEXT DEFAULT 'friendly',
         FOREIGN KEY(user_id) REFERENCES users(id))
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ==================== UTILITY FUNCTIONS ====================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_email(subject, message):
    """Send email notification to systems@americanpower.us"""
    try:
        msg = MimeText(message)
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# ==================== AUTHENTICATION ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        conn.close()
        
        if user and user[2] == hash_password(password):  # password_hash
            session['user_id'] = user[0]
            session['email'] = user[1]
            session['business_name'] = user[3]
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password')
    
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    email = request.form.get('email')
    business_name = request.form.get('business_name')
    password = request.form.get('password')
    
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO users (email, password_hash, business_name, status)
            VALUES (?, ?, ?, 'trial')
        ''', (email, hash_password(password), business_name))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        
        # Send notification email
        send_email(
            "New LeaX Registration",
            f"New user registered:\nEmail: {email}\nBusiness: {business_name}\nTime: {datetime.now()}"
        )
        
        session['user_id'] = user_id
        session['email'] = email
        session['business_name'] = business_name
        return redirect(url_for('customize_agent'))
        
    except sqlite3.IntegrityError:
        flash('Email already exists')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ==================== LANDING PAGE ====================
@app.route('/')
def index():
    return render_template('index.html')

# ==================== AGENT CUSTOMIZATION ====================
@app.route('/customize')
def customize_agent():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('customize.html')

@app.route('/api/scan-website', methods=['POST'])
def scan_website():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    data = request.json
    url = data.get('website_url')
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        business_name = session.get('business_name', 'Your Business')
        title = soup.find('title')
        if title:
            business_name = title.get_text().split('|')[0].split('-')[0].strip()
        
        services = []
        for element in soup.find_all(['h1', 'h2', 'h3']):
            text = element.get_text().lower()
            if any(keyword in text for keyword in ['service', 'product', 'offer', 'solution']):
                services.append(element.get_text().strip())
        
        # Save to database
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO business_info 
            (user_id, website_url, services) 
            VALUES (?, ?, ?)
        ''', (session['user_id'], url, json.dumps(services)))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'business_name': business_name,
            'services': services[:10]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/save-customization', methods=['POST'])
def save_customization():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    data = request.json
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO business_info 
        (user_id, website_url, services, custom_info, agent_personality) 
        VALUES (?, ?, ?, ?, ?)
    ''', (
        session['user_id'],
        data.get('website_url'),
        json.dumps(data.get('services', [])),
        json.dumps(data.get('custom_info', {})),
        data.get('personality', 'friendly')
    ))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ==================== LIVE TESTING ====================
@app.route('/test-agent')
def test_agent():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check trial uses
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT trial_uses, max_trial_uses FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    
    if user[0] >= user[1]:
        return redirect(url_for('pricing'))
    
    # Increment trial uses
    c.execute('UPDATE users SET trial_uses = trial_uses + 1 WHERE id = ?', (session['user_id'],))
    conn.commit()
    conn.close()
    
    return render_template('test_agent.html')

@app.route('/api/test-chat', methods=['POST'])
def test_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    data = request.json
    user_message = data.get('message')
    
    # Get user's business info
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM business_info WHERE user_id = ?', (session['user_id'],))
    business = c.fetchone()
    conn.close()
    
    # Create AI prompt
    business_context = f"""
BUSINESS: {session.get('business_name', 'Business')}
WEBSITE: {business[2] if business else ''}
SERVICES: {business[3] if business else ''}
"""
    
    prompt = f"""
You are a friendly sales assistant. Sound human and helpful.

{business_context}

Customer Message: {user_message}

Your response (be human, 1-2 sentences):
"""
    
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Use cheaper model for testing
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=100
        )
        ai_reply = completion.choices[0].message.content
    except Exception as e:
        ai_reply = "Thanks for your message! We'll get back to you soon."
    
    return jsonify({'reply': ai_reply})

# ==================== PAYMENT & PRICING ====================
@app.route('/pricing')
def pricing():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('pricing.html')

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
        # Update user status
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET status = ? WHERE id = ?', 
                 (session.get('payment_plan', 'starter'), session['user_id']))
        conn.commit()
        conn.close()
        
        # Send payment notification
        send_email(
            "LeaX Payment Received",
            f"Payment received from: {session.get('email')}\n"
            f"Plan: {session.get('payment_plan')}\n"
            f"Amount: $29.99\n"
            f"Time: {datetime.now()}"
        )
        
        flash('Payment successful! Your AI agent is now active.')
        return redirect(url_for('dashboard'))
    
    flash('Payment failed')
    return redirect(url_for('pricing'))

@app.route('/payment/cancel')
def payment_cancel():
    flash('Payment was cancelled')
    return redirect(url_for('pricing'))

# ==================== DASHBOARD ====================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    c.execute('SELECT * FROM business_info WHERE user_id = ?', (session['user_id'],))
    business = c.fetchone()
    conn.close()
    
    return render_template('dashboard.html', user=user, business=business)

# ==================== LIVE AI AGENT ====================
@app.route('/agent/<user_id>', methods=['POST'])
def ai_agent(user_id):
    """Live AI agent endpoint for paying customers"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ? AND status != "trial"', (user_id,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return "Agent not active", 404
    
    c.execute('SELECT * FROM business_info WHERE user_id = ?', (user_id,))
    business = c.fetchone()
    conn.close()
    
    # Handle SMS
    if "SmsMessageSid" in request.form:
        incoming_msg = request.form.get('Body', '').strip()
        
        business_context = f"""
BUSINESS: {user[3]}
WEBSITE: {business[2] if business else ''}
SERVICES: {business[3] if business else ''}
CUSTOM INFO: {business[4] if business else ''}
"""
        
        prompt = f"""
You are a friendly sales assistant for this business. Sound human and helpful.

{business_context}

Customer Message: {incoming_msg}

Your response (be human, 1-2 sentences):
"""
        
        try:
            completion = openai.ChatCompletion.create(
                model="gpt-4" if user[4] == 'pro' else "gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=150
            )
            ai_reply = completion.choices[0].message.content
        except:
            ai_reply = "Thanks for your message! We'll get back to you soon."
        
        resp = MessagingResponse()
        resp.message(ai_reply)
        return str(resp)
    
    # Handle Voice
    else:
        resp = VoiceResponse()
        resp.say(f"Thanks for calling {user[3]}! Text us at this number and we'll help you right away!")
        return str(resp)

# ==================== ADMIN ====================
@app.route('/admin')
def admin():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users')
    users = c.fetchall()
    conn.close()
    
    return render_template('admin.html', users=users)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
