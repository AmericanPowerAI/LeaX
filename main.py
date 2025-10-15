from flask import Flask, request, jsonify, render_template, redirect, url_for, session
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

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this!

# ==================== CONFIGURATION ====================
openai.api_key = os.environ.get('OPENAI_API_KEY')

# PayPal Configuration
paypalrestsdk.configure({
    "mode": "sandbox",  # sandbox or live
    "client_id": os.environ.get('PAYPAL_CLIENT_ID'),
    "client_secret": os.environ.get('PAYPAL_CLIENT_SECRET')
})

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         email TEXT UNIQUE,
         business_name TEXT,
         phone_number TEXT,
         website_url TEXT,
         services TEXT,
         custom_info TEXT,
         status TEXT DEFAULT 'active',
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         twilio_url TEXT)
    ''')
    conn.commit()
    conn.close()

init_db()

# ==================== BUSINESS INTELLIGENCE SYSTEM ====================
class BusinessIntelligence:
    def scan_website(self, url):
        """Scan business website for information"""
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract business name
            title = soup.find('title')
            business_name = 'Your Business'
            if title:
                business_name = title.get_text().split('|')[0].split('-')[0].strip()
            
            # Extract services/products
            services = []
            for element in soup.find_all(['h1', 'h2', 'h3', 'p']):
                text = element.get_text().lower()
                if any(keyword in text for keyword in ['service', 'product', 'offer', 'solution', 'package']):
                    services.append(element.get_text().strip())
            
            return {
                'success': True,
                'business_name': business_name,
                'services': services[:10],
                'website': url
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

# ==================== LANDING PAGE & SIGNUP ====================
@app.route('/')
def index():
    """Main landing page - customers see this first"""
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    """Customer signup process"""
    email = request.form.get('email')
    business_name = request.form.get('business_name')
    
    # Create payment with PayPal
    payment = paypalrestsdk.Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "paypal"
        },
        "redirect_urls": {
            "return_url": url_for('payment_success', _external=True),
            "cancel_url": url_for('payment_cancel', _external=True)
        },
        "transactions": [{
            "amount": {
                "total": "29.99",  # Monthly price
                "currency": "USD"
            },
            "description": f"LeaX AI Agent for {business_name}"
        }]
    })
    
    if payment.create():
        # Store signup info in session
        session['signup_data'] = {
            'email': email,
            'business_name': business_name
        }
        # Redirect to PayPal
        for link in payment.links:
            if link.rel == "approval_url":
                return redirect(link.href)
    else:
        return "Payment creation failed"

@app.route('/payment/success')
def payment_success():
    """Handle successful PayPal payment"""
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')
    
    # Execute payment
    payment = paypalrestsdk.Payment.find(payment_id)
    if payment.execute({"payer_id": payer_id}):
        # Create customer account
        signup_data = session.get('signup_data', {})
        
        conn = sqlite3.connect('customers.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO customers (email, business_name, status)
            VALUES (?, ?, 'active')
        ''', (signup_data.get('email'), signup_data.get('business_name')))
        conn.commit()
        conn.close()
        
        # Redirect to setup wizard
        return redirect(url_for('setup_wizard'))
    else:
        return "Payment execution failed"

@app.route('/payment/cancel')
def payment_cancel():
    """Handle cancelled payment"""
    return "Payment was cancelled"

# ==================== CUSTOMER SETUP WIZARD ====================
@app.route('/setup')
def setup_wizard():
    """Step-by-step setup wizard for customers"""
    return render_template('setup_wizard.html')

@app.route('/api/setup-business', methods=['POST'])
def setup_business():
    """API to setup business info"""
    data = request.json
    email = data.get('email')
    
    # Update customer in database
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute('''
        UPDATE customers 
        SET website_url = ?, services = ?, custom_info = ?
        WHERE email = ?
    ''', (
        data.get('website_url'),
        json.dumps(data.get('services', [])),
        json.dumps(data.get('custom_info', {})),
        email
    ))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/scan-website', methods=['POST'])
def scan_website():
    """API to scan customer website"""
    data = request.json
    url = data.get('website_url')
    
    scanner = BusinessIntelligence()
    result = scanner.scan_website(url)
    
    return jsonify(result)

# ==================== CUSTOMER DASHBOARD ====================
@app.route('/dashboard')
def customer_dashboard():
    """Customer dashboard to manage their AI agent"""
    return render_template('dashboard.html')

# ==================== AI AGENT ENDPOINT ====================
@app.route('/agent/<customer_id>', methods=['POST'])
def ai_agent(customer_id):
    """Dynamic AI agent endpoint for each customer"""
    # Get customer data from database
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
    customer = c.fetchone()
    conn.close()
    
    if not customer:
        return "Customer not found", 404
    
    # Handle SMS
    if "SmsMessageSid" in request.form:
        incoming_msg = request.form.get('Body', '').strip()
        
        # Create AI prompt with customer's business info
        business_context = f"""
BUSINESS: {customer[2]}  # business_name
WEBSITE: {customer[4]}   # website_url
SERVICES: {customer[5]}  # services
CUSTOM INFO: {customer[6]}  # custom_info
"""
        
        prompt = f"""
You are a friendly sales assistant for this business. Sound human and helpful.

{business_context}

Customer Message: {incoming_msg}

Your response (be human, 1-2 sentences):
"""
        
        # Generate AI response
        try:
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
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
        resp.say(f"Thanks for calling {customer[2]}! ", voice='alice')
        resp.say("Please text us at this number and we'll help you right away!")
        return str(resp)

# ==================== ADMIN PANEL ====================
@app.route('/admin')
def admin_panel():
    """Your admin panel to see all customers"""
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute('SELECT * FROM customers')
    customers = c.fetchall()
    conn.close()
    
    return render_template('admin.html', customers=customers)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
