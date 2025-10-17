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
import re

# IMPORT MEMORY MANAGER
from memory_manager import MemoryManager

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'leax-super-secure-2024-8f7d2a9c1e6b4a0d5c8e2f1b7a9d4c3')

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
SMTP_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# Database Configuration
DATABASE_FILE = os.environ.get('DATABASE_FILE', 'leax_users.db')

# INITIALIZE MEMORY MANAGER
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
                <p><strong>Plan:</strong> {user_data.get('plan_type', 'basic')}</p>
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
    """Initialize database with PERSISTENT STORAGE"""
    with get_db() as conn:
        c = conn.cursor()
        
        # USERS TABLE - Enhanced with persistent credentials
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                business_name TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                plan_type TEXT DEFAULT 'basic',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trial_session_used BOOLEAN DEFAULT 0,
                total_sessions INTEGER DEFAULT 0,
                total_messages INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                last_login TIMESTAMP,
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # BUSINESS INFO - Enhanced
        c.execute('''
            CREATE TABLE IF NOT EXISTS business_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                website_url TEXT,
                services TEXT,
                custom_info TEXT,
                agent_personality TEXT DEFAULT 'Sarah',
                business_hours TEXT DEFAULT '{}',
                pricing_info TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # CONVERSATIONS - Full persistent storage
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
                session_id TEXT,
                tokens_used INTEGER DEFAULT 0,
                cost_usd DECIMAL(10,4) DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # LEADS - Enhanced with full details
        c.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL,
                business_name TEXT,
                contact_name TEXT,
                contact_email TEXT,
                project_type TEXT,
                urgency TEXT,
                budget TEXT,
                location TEXT,
                status TEXT DEFAULT 'new',
                lead_score INTEGER DEFAULT 0,
                meeting_scheduled BOOLEAN DEFAULT 0,
                meeting_datetime TIMESTAMP,
                last_contact TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                conversation_summary TEXT,
                needs_analysis TEXT,
                next_steps TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # LEAD CONVERSATIONS - Enhanced with sales tracking
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
                sale_closed BOOLEAN DEFAULT 0,
                FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # PLAN TRIALS - Track which plans users have tested
        c.execute('''
            CREATE TABLE IF NOT EXISTS plan_trials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_type TEXT NOT NULL,
                trial_started TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trial_ended TIMESTAMP,
                messages_sent INTEGER DEFAULT 0,
                trial_active BOOLEAN DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone_number)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id)')
        
        conn.commit()

init_database()

# ==================== UTILITY FUNCTIONS ====================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def normalize_url(url):
    """Add https:// if missing - AUTOMATIC"""
    if not url:
        return url
    url = url.strip()
    # Remove any existing protocol
    url = url.replace('http://', '').replace('https://', '')
    # Add https://
    url = 'https://' + url
    return url

def scrape_website_info(url):
    """Scrape website to get business info - ENHANCED"""
    try:
        url = normalize_url(url)
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get text content
        text_content = soup.get_text(separator=' ', strip=True)
        
        # Extract services keywords
        services_keywords = []
        service_patterns = [
            r'services?[:=]?\s*([^.]+)',
            r'we offer\s+([^.]+)',
            r'specializ(?:e|ing) in\s+([^.]+)'
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE)
            services_keywords.extend(matches)
        
        # Extract pricing if available
        pricing_matches = re.findall(r'\$\d+(?:,\d{3})*(?:\.\d{2})?', text_content)
        
        # Extract key info
        info = {
            'title': soup.title.string if soup.title else '',
            'description': '',
            'content_summary': text_content[:2000] if text_content else '',
            'services_found': ', '.join(services_keywords[:5]),
            'pricing_indicators': ', '.join(pricing_matches[:10]) if pricing_matches else 'No pricing found'
        }
        
        # Get meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            info['description'] = meta_desc.get('content', '')
        
        return info
    except Exception as e:
        print(f"Website scrape error: {e}")
        return None

def generate_example_prompts(business_name, custom_info):
    """Generate personalized example prompts based on business"""
    try:
        prompt = f"""Based on this business info, generate 3 SHORT (5-8 words) example customer questions:

Business: {business_name}
Info: {custom_info or 'General service provider'}

Return ONLY a JSON array of 3 strings, like:
["Question 1", "Question 2", "Question 3"]

Keep questions natural and relevant to their business."""

        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=100
        )
        
        examples = json.loads(completion.choices[0].message.content)
        return examples[:3]
    except:
        # Fallback examples
        return [
            "What are your hours?",
            "How much do you charge?",
            "Are you available today?"
        ]

def analyze_customer_intent(message):
    """Analyze customer message to extract key information - ENHANCED"""
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
    - decision_maker: Do they seem like a decision maker? (yes, no, maybe)
    
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
            "contact_willingness": "maybe",
            "decision_maker": "maybe"
        }

def calculate_lead_score(intent_analysis, message_length, has_contact_info, meeting_scheduled=False):
    """Calculate lead quality score - ENHANCED"""
    score = 0
    
    # Meeting scheduled = automatic hot lead
    if meeting_scheduled:
        return 95
    
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
    
    if intent_analysis.get('decision_maker') == 'yes':
        score += 15
    
    return min(score, 100)

def send_comprehensive_lead_email(lead_data, conversation_history, business_info):
    """Send detailed lead information - ENHANCED"""
    try:
        if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD]):
            print("EMAIL CONFIG MISSING")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🚨 HOT LEAD: {lead_data.get('project_type', 'New Lead')} - {business_info.get('business_name', 'N/A')}"
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        
        meeting_info = ""
        if lead_data.get('meeting_scheduled'):
            meeting_info = f"""
            <div style="background: #28a745; color: white; padding: 15px; margin: 10px 0; border-radius: 5px;">
                <h3>✅ MEETING SCHEDULED!</h3>
                <p><strong>Time:</strong> {lead_data.get('meeting_datetime', 'TBD')}</p>
            </div>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; margin: 20px;">
            <div style="background: #dc3545; color: white; padding: 20px; border-radius: 10px;">
                <h1>🚨 HOT LEAD - CALL NOW!</h1>
                <h2>Score: {lead_data.get('lead_score', 0)}/100</h2>
            </div>
            {meeting_info}
            <div style="background: #fff3cd; padding: 15px; margin: 10px 0;">
                <h3>📋 LEAD DETAILS</h3>
                <p><strong>Business:</strong> {business_info.get('business_name', 'N/A')}</p>
                <p><strong>Phone:</strong> {lead_data.get('phone_number', 'N/A')}</p>
                <p><strong>Contact Name:</strong> {lead_data.get('contact_name', 'Not provided')}</p>
                <p><strong>Email:</strong> {lead_data.get('contact_email', 'Not provided')}</p>
                <p><strong>Project:</strong> {lead_data.get('project_type', 'N/A')}</p>
                <p><strong>Urgency:</strong> {lead_data.get('urgency', 'N/A')}</p>
                <p><strong>Budget:</strong> {lead_data.get('budget', 'Not specified')}</p>
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
Contact: {lead_data.get('contact_name', 'Not provided')}
Email: {lead_data.get('contact_email', 'Not provided')}
Project: {lead_data.get('project_type', 'N/A')}
Urgency: {lead_data.get('urgency', 'N/A')}
Meeting: {'SCHEDULED - ' + str(lead_data.get('meeting_datetime', 'TBD')) if lead_data.get('meeting_scheduled') else 'Not scheduled'}
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
    """Update lead conversation - PERSISTENT"""
    with get_db() as conn:
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO lead_conversations 
            (lead_id, user_id, message_text, response_text, intent_detected, needs_identified)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (lead_id, user_id, message_text, response_text, 
              json.dumps(intent_analysis), intent_analysis.get('key_requirements', '')))
        
        # Update lead last contact
        c.execute('UPDATE leads SET last_contact = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (lead_id,))
        
        conn.commit()
        
        return {'lead_id': lead_id}

def check_for_meeting_info(message, ai_response):
    """Check if meeting was scheduled in conversation"""
    meeting_indicators = ['meeting', 'appointment', 'schedule', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'visit', 'come over', 'send someone', 'technician']
    time_indicators = ['am', 'pm', 'oclock', "o'clock", ':00', ':30', 'morning', 'afternoon', 'evening']
    
    combined_text = (message + ' ' + ai_response).lower()
    
    has_meeting_word = any(word in combined_text for word in meeting_indicators)
    has_time = any(word in combined_text for word in time_indicators)
    
    return has_meeting_word and has_time

def check_for_sale_closed(message, ai_response):
    """Check if customer committed to purchase/service"""
    commitment_indicators = [
        'yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'let\'s do it', 'go ahead', 
        'schedule', 'book it', 'sign me up', 'i\'ll take it', 'sounds good',
        'that works', 'perfect', 'great', 'deal'
    ]
    
    rejection_indicators = [
        'no', 'nope', 'nevermind', 'never mind', 'not interested', 'no thanks',
        'find someone else', 'too expensive', 'too much', 'can\'t afford'
    ]
    
    message_lower = message.lower()
    
    # Check for rejection first
    has_rejection = any(word in message_lower for word in rejection_indicators)
    if has_rejection:
        return False
    
    # Check for commitment
    has_commitment = any(word in message_lower for word in commitment_indicators)
    
    # Also check if AI asked to schedule and customer didn't reject
    ai_lower = ai_response.lower()
    ai_asked_to_schedule = any(phrase in ai_lower for phrase in ['shall we schedule', 'can we schedule', 'would you like to', 'arrange'])
    
    return has_commitment or (ai_asked_to_schedule and len(message_lower) > 5 and not has_rejection)

# ==================== 🔥 AI PROMPT WITH WEBSITE CONTEXT ====================
def generate_human_response(business_name, business_context, customer_message, conversation_history=""):
    """Generate HUMAN-SOUNDING responses with website context - ENHANCED"""
    
    prompt = f"""You are Sarah, a friendly team member at {business_name}. You answer texts/calls like a real person would.

CRITICAL RULES:
1. NEVER say "I'll have someone call you" - YOU are that person! 
2. NEVER give generic responses
3. ASK SPECIFIC QUESTIONS to understand their exact needs
4. Give REAL answers with pricing, timing, availability based on the business info
5. Sound conversational and natural
6. Use their exact words when responding
7. Get to the bottom of what they need FAST
8. CLOSE THE SALE by asking for commitment or scheduling a meeting
9. If they ask about prices, give them from the business info or ask what their budget is
10. If scheduling a meeting, confirm time and ask for their name/email

BUSINESS INFO:
{business_context}

CONVERSATION SO FAR:
{conversation_history}

CURRENT CUSTOMER MESSAGE:
"{customer_message}"

NOW RESPOND LIKE A REAL HUMAN WHO WANTS TO CLOSE THIS DEAL (2-3 sentences max):"""
    
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=150
        )
        return completion.choices[0].message.content, completion['usage']['total_tokens']
    except Exception as e:
        print(f"AI Error: {e}")
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
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container { max-width: 1200px; width: 100%; }
            .hero { 
                background: rgba(255,255,255,0.98); 
                padding: 60px 40px; 
                border-radius: 20px; 
                box-shadow: 0 20px 60px rgba(0,0,0,0.2);
                text-align: center;
            }
            .logo { 
                font-size: 48px; 
                font-weight: 800; 
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 10px;
            }
            .tagline { font-size: 20px; color: #666; margin-bottom: 40px; }
            .pricing { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); 
                gap: 30px; 
                margin: 40px 0; 
            }
            .plan { 
                background: white;
                border: 2px solid #e2e8f0; 
                padding: 40px 30px; 
                border-radius: 15px; 
                text-align: center;
                transition: all 0.3s;
                position: relative;
            }
            .plan:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 40px rgba(0,0,0,0.1);
                border-color: #667eea;
            }
            .plan.featured {
                border-color: #667eea;
                border-width: 3px;
            }
            .plan.featured::before {
                content: "⭐ MOST POPULAR";
                position: absolute;
                top: -15px;
                left: 50%;
                transform: translateX(-50%);
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                padding: 5px 20px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 700;
            }
            .plan h3 { 
                font-size: 24px; 
                margin-bottom: 15px; 
                color: #333;
            }
            .plan .price { 
                font-size: 42px; 
                font-weight: 800; 
                color: #667eea; 
                margin: 20px 0;
            }
            .plan .price span { font-size: 18px; color: #666; font-weight: 400; }
            .plan ul { 
                list-style: none; 
                text-align: left; 
                margin: 30px 0;
            }
            .plan ul li { 
                padding: 12px 0; 
                border-bottom: 1px solid #f0f0f0;
                color: #555;
            }
            .plan ul li::before { 
                content: "✓ "; 
                color: #10b981; 
                font-weight: bold; 
                margin-right: 10px;
            }
            .btn { 
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white; 
                padding: 15px 40px; 
                text-decoration: none; 
                border-radius: 30px; 
                display: inline-block; 
                margin: 10px;
                font-weight: 600;
                border: none;
                cursor: pointer;
                font-size: 16px;
                transition: all 0.3s;
            }
            .btn:hover {
                transform: scale(1.05);
                box-shadow: 0 10px 30px rgba(102,126,234,0.3);
            }
            .trial-badge {
                background: #ffc107;
                color: #000;
                padding: 8px 20px;
                border-radius: 20px;
                font-size: 14px;
                font-weight: 700;
                display: inline-block;
                margin: 20px 0;
            }
            @media (max-width: 768px) {
                .hero { padding: 40px 20px; }
                .logo { font-size: 36px; }
                .tagline { font-size: 16px; }
                .plan .price { font-size: 32px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="hero">
                <div class="logo">🤖 LeaX AI</div>
                <p class="tagline">Your 24/7 AI Assistant That Closes Sales While You Sleep</p>
                
                <div class="trial-badge">🎁 Try Any Plan FREE During Sign-Up!</div>
                
                <div class="pricing">
                    <div class="plan">
                        <h3>Basic</h3>
                        <div class="price">$29<span>/mo</span></div>
                        <ul>
                            <li>AI Phone & SMS Agent</li>
                            <li>Natural Conversations</li>
                            <li>Basic Lead Tracking</li>
                            <li>Email Notifications</li>
                            <li>Website Integration</li>
                        </ul>
                        <a href="/register?plan=basic" class="btn">Start Basic</a>
                    </div>
                    
                    <div class="plan featured">
                        <h3>Standard</h3>
                        <div class="price">$59<span>/mo</span></div>
                        <ul>
                            <li>Everything in Basic</li>
                            <li>Advanced Lead Scoring</li>
                            <li>Meeting Scheduler</li>
                            <li>Conversation Analytics</li>
                            <li>Priority Support</li>
                            <li>Custom Training</li>
                        </ul>
                        <a href="/register?plan=standard" class="btn">Start Standard</a>
                    </div>
                    
                    <div class="plan">
                        <h3>Enterprise</h3>
                        <div class="price">$149<span>/mo</span></div>
                        <ul>
                            <li>Everything in Standard</li>
                            <li>Multi-Agent Support</li>
                            <li>CRM Integration</li>
                            <li>Advanced Analytics</li>
                            <li>White-Label Option</li>
                            <li>Dedicated Account Manager</li>
                        </ul>
                        <a href="/register?plan=enterprise" class="btn">Start Enterprise</a>
                    </div>
                </div>
                
                <p style="color: #999; font-size: 14px; margin-top: 30px;">
                    Already have an account? <a href="/login" style="color: #667eea; text-decoration: none; font-weight: 600;">Login here</a>
                </p>
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
            
            # Update last login
            with get_db() as conn:
                c = conn.cursor()
                c.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
                conn.commit()
            
            # Log to memory manager
            memory_mgr.log_login(
                user_id=user['id'],
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            flash('Welcome back!')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password')
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - LeaX</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .login-container {
                background: white;
                padding: 50px 40px;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.2);
                max-width: 450px;
                width: 100%;
            }
            .logo {
                font-size: 36px;
                font-weight: 800;
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                text-align: center;
                margin-bottom: 30px;
            }
            input {
                width: 100%;
                padding: 15px;
                margin: 10px 0;
                border: 2px solid #e2e8f0;
                border-radius: 10px;
                font-size: 16px;
                transition: border-color 0.3s;
            }
            input:focus {
                outline: none;
                border-color: #667eea;
            }
            button {
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                padding: 15px;
                border: none;
                cursor: pointer;
                width: 100%;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 600;
                margin-top: 10px;
                transition: transform 0.3s;
            }
            button:hover {
                transform: scale(1.02);
            }
            .flash {
                background: #fee;
                color: #c33;
                padding: 12px;
                margin: 15px 0;
                border-radius: 8px;
                text-align: center;
            }
            .password-wrapper {
                position: relative;
            }
            .toggle-password {
                position: absolute;
                right: 15px;
                top: 50%;
                transform: translateY(-50%);
                cursor: pointer;
                font-size: 20px;
                color: #999;
            }
            .links {
                text-align: center;
                margin-top: 20px;
                color: #666;
            }
            .links a {
                color: #667eea;
                text-decoration: none;
                font-weight: 600;
            }
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="logo">🤖 LeaX AI</div>
            <h2 style="text-align: center; margin-bottom: 30px; color: #333;">Welcome Back</h2>
            
            <form method="POST">
                <input type="email" name="email" placeholder="Email Address" required autofocus>
                <div class="password-wrapper">
                    <input type="password" id="password" name="password" placeholder="Password" required>
                    <span class="toggle-password" onclick="togglePassword()">👁️</span>
                </div>
                <button type="submit">Login</button>
            </form>
            
            <div class="links">
                <p>Don't have an account? <a href="/">Sign up here</a></p>
            </div>
        </div>
        
        <script>
            function togglePassword() {
                const pw = document.getElementById('password');
                pw.type = pw.type === 'password' ? 'text' : 'password';
            }
        </script>
    </body>
    </html>
    '''

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        selected_plan = request.args.get('plan', 'basic')
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Register - LeaX</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }}
                .register-container {{
                    background: white;
                    padding: 50px 40px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.2);
                    max-width: 500px;
                    width: 100%;
                }}
                .logo {{
                    font-size: 36px;
                    font-weight: 800;
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    text-align: center;
                    margin-bottom: 10px;
                }}
                .plan-badge {{
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white;
                    padding: 10px 20px;
                    border-radius: 20px;
                    text-align: center;
                    margin-bottom: 30px;
                    font-weight: 600;
                }}
                input {{
                    width: 100%;
                    padding: 15px;
                    margin: 10px 0;
                    border: 2px solid #e2e8f0;
                    border-radius: 10px;
                    font-size: 16px;
                    transition: border-color 0.3s;
                }}
                input:focus {{
                    outline: none;
                    border-color: #667eea;
                }}
                button {{
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white;
                    padding: 15px;
                    border: none;
                    cursor: pointer;
                    width: 100%;
                    border-radius: 10px;
                    font-size: 16px;
                    font-weight: 600;
                    margin-top: 10px;
                    transition: transform 0.3s;
                }}
                button:hover {{
                    transform: scale(1.02);
                }}
                button:disabled {{
                    background: #ccc;
                    cursor: not-allowed;
                    transform: none;
                }}
                .password-strength {{
                    height: 5px;
                    margin: 5px 0;
                    border-radius: 3px;
                    background: #ddd;
                    transition: all 0.3s;
                }}
                .password-strength.weak {{ background: #dc3545; }}
                .password-strength.medium {{ background: #ffc107; }}
                .password-strength.strong {{ background: #28a745; }}
                .password-wrapper {{
                    position: relative;
                }}
                .toggle-password {{
                    position: absolute;
                    right: 15px;
                    top: 50%;
                    transform: translateY(-50%);
                    cursor: pointer;
                    font-size: 20px;
                    color: #999;
                }}
                .hint {{
                    font-size: 12px;
                    color: #666;
                    margin: 5px 0;
                }}
                .links {{
                    text-align: center;
                    margin-top: 20px;
                    color: #666;
                }}
                .links a {{
                    color: #667eea;
                    text-decoration: none;
                    font-weight: 600;
                }}
            </style>
        </head>
        <body>
            <div class="register-container">
                <div class="logo">🤖 LeaX AI</div>
                <h2 style="text-align: center; margin-bottom: 20px; color: #333;">Create Your Account</h2>
                
                <div class="plan-badge">
                    🎁 Starting with {selected_plan.upper()} plan - Try FREE!
                </div>
                
                <form method="POST" onsubmit="return validateForm()">
                    <input type="hidden" name="plan_type" value="{selected_plan}">
                    
                    <input type="email" id="email" name="email" placeholder="Business Email" required autofocus>
                    
                    <input type="text" name="business_name" placeholder="Business Name" required>
                    
                    <div class="password-wrapper">
                        <input type="password" id="password" name="password" placeholder="Password (min 8 characters)" required minlength="8" oninput="checkPasswordStrength()">
                        <span class="toggle-password" onclick="togglePassword()">👁️</span>
                    </div>
                    <div class="password-strength" id="strengthBar"></div>
                    <div class="hint" id="strengthText"></div>
                    
                    <button type="submit" id="submitBtn">Create Account & Start Testing</button>
                </form>
                
                <div class="links">
                    <p>Already have an account? <a href="/login">Login here</a></p>
                </div>
            </div>
            
            <script>
                function togglePassword() {{
                    const pw = document.getElementById('password');
                    pw.type = pw.type === 'password' ? 'text' : 'password';
                }}
                
                function checkPasswordStrength() {{
                    const pw = document.getElementById('password').value;
                    const bar = document.getElementById('strengthBar');
                    const text = document.getElementById('strengthText');
                    
                    if (pw.length < 8) {{
                        bar.className = 'password-strength weak';
                        text.textContent = 'Weak - add more characters';
                        text.style.color = '#dc3545';
                    }} else if (pw.length < 12) {{
                        bar.className = 'password-strength medium';
                        text.textContent = 'Medium - consider adding numbers/symbols';
                        text.style.color = '#ffc107';
                    }} else {{
                        bar.className = 'password-strength strong';
                        text.textContent = 'Strong password!';
                        text.style.color = '#28a745';
                    }}
                }}
                
                function validateForm() {{
                    const password = document.getElementById('password').value;
                    
                    if (password.length < 8) {{
                        alert('Password must be at least 8 characters');
                        return false;
                    }}
                    
                    return true;
                }}
            </script>
        </body>
        </html>
        '''
    
    elif request.method == 'POST':
        email = request.form.get('email')
        business_name = request.form.get('business_name')
        password = request.form.get('password')
        plan_type = request.form.get('plan_type', 'basic')
        
        if len(password) < 8:
            flash('Password must be at least 8 characters')
            return redirect(url_for('register'))
        
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT INTO users (email, password_hash, business_name, status, plan_type, trial_session_used)
                    VALUES (?, ?, ?, 'active', ?, 0)
                ''', (email, hash_password(password), business_name, plan_type))
                user_id = c.lastrowid
                
                c.execute('''
                    INSERT INTO business_info (user_id, agent_personality)
                    VALUES (?, 'Sarah')
                ''', (user_id,))
                
                # Create initial plan trial record
                c.execute('''
                    INSERT INTO plan_trials (user_id, plan_type, trial_active)
                    VALUES (?, ?, 1)
                ''', (user_id, plan_type))
                
                conn.commit()
            
            # Create memory file for persistent storage
            memory_path = memory_mgr.create_customer_memory(
                user_id=user_id,
                business_name=business_name,
                email=email
            )
            
            # Set session - AUTO LOGIN after registration
            session['user_id'] = user_id
            session['email'] = email
            session['business_name'] = business_name
            session['user_plan'] = plan_type
            
            # Send notification email
            email_notifier.notify_new_signup({
                'user_id': user_id,
                'business_name': business_name,
                'email': email,
                'plan_type': plan_type
            })
            
            flash(f'Account created! You\'re now testing the {plan_type.upper()} plan for free.')
            
            # AUTOMATIC REDIRECT to customize agent
            return redirect(url_for('customize_agent'))
            
        except sqlite3.IntegrityError:
            flash('Email already exists')
            return redirect(url_for('register'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out')
    return redirect(url_for('login'))

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
                   COUNT(CASE WHEN lead_score >= 70 THEN 1 END) as hot_leads,
                   COUNT(CASE WHEN meeting_scheduled = 1 THEN 1 END) as meetings_scheduled
            FROM leads WHERE user_id = ?
        ''', (session['user_id'],))
        lead_stats = c.fetchone()
    
    analytics = memory_mgr.get_customer_analytics(session['user_id'])
    
    user_dict = dict(user) if user else {}
    lead_stats_dict = dict(lead_stats) if lead_stats else {}
    
    # Check if this is first time user (no activity yet)
    total_activity = analytics['total_conversations'] if analytics else 0
    show_onboarding = total_activity == 0
    
    if show_onboarding:
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Welcome - LeaX</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }}
                .container {{ max-width: 900px; margin: 0 auto; }}
                .welcome-card {{ 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    color: white; 
                    padding: 50px 40px; 
                    border-radius: 20px; 
                    text-align: center; 
                    margin: 20px 0;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.2);
                }}
                .welcome-card h1 {{ font-size: 36px; margin-bottom: 15px; }}
                .welcome-card p {{ font-size: 18px; opacity: 0.95; }}
                .step-card {{ 
                    background: white; 
                    padding: 30px; 
                    margin: 20px 0; 
                    border-radius: 15px; 
                    border-left: 5px solid #667eea;
                    box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                    display: flex;
                    align-items: center;
                    gap: 20px;
                    transition: transform 0.3s;
                }}
                .step-card:hover {{
                    transform: translateX(10px);
                }}
                .btn {{ 
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white; 
                    padding: 12px 30px; 
                    text-decoration: none; 
                    border-radius: 25px; 
                    display: inline-block; 
                    font-weight: 600;
                    transition: all 0.3s;
                }}
                .btn:hover {{
                    transform: scale(1.05);
                    box-shadow: 0 5px 20px rgba(102,126,234,0.3);
                }}
                .step-number {{ 
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white; 
                    width: 60px; 
                    height: 60px; 
                    border-radius: 50%; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center; 
                    font-weight: bold; 
                    font-size: 24px;
                    flex-shrink: 0;
                }}
                .step-content {{ flex: 1; }}
                .step-content h3 {{ margin-bottom: 10px; color: #333; }}
                .step-content p {{ color: #666; margin-bottom: 15px; }}
                .logout-link {{
                    text-align: center;
                    margin-top: 30px;
                }}
                .logout-link a {{
                    color: white;
                    text-decoration: none;
                    opacity: 0.9;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="welcome-card">
                    <h1>🎉 Welcome to LeaX, {session['business_name']}!</h1>
                    <p>Let's get your AI agent set up in 3 easy steps</p>
                    <p style="margin-top: 20px; font-size: 16px;">You're testing the <strong>{user_dict.get('plan_type', 'Basic').upper()}</strong> plan</p>
                </div>
                
                <div class="step-card">
                    <div class="step-number">1</div>
                    <div class="step-content">
                        <h3>📝 Tell us about your business</h3>
                        <p>Add your website URL and we'll automatically learn about your services, pricing, and more</p>
                        <a href="/customize" class="btn">Customize Your Agent →</a>
                    </div>
                </div>
                
                <div class="step-card">
                    <div class="step-number">2</div>
                    <div class="step-content">
                        <h3>💬 Test how it sounds</h3>
                        <p>Chat with your AI to see exactly how it responds to real customer questions</p>
                        <a href="/test-agent" class="btn">Test Your Agent →</a>
                    </div>
                </div>
                
                <div class="step-card">
                    <div class="step-number">3</div>
                    <div class="step-content">
                        <h3>🚀 Watch the leads come in</h3>
                        <p>Once you're happy, connect your phone number and start capturing leads 24/7</p>
                        <a href="/pricing" class="btn">View Setup Guide →</a>
                    </div>
                </div>
                
                <div class="logout-link">
                    <a href="/logout">Logout</a>
                </div>
            </div>
        </body>
        </html>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - LeaX</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: #f5f7fa;
                min-height: 100vh;
            }}
            .nav {{
                background: white;
                padding: 20px 40px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .logo {{
                font-size: 24px;
                font-weight: 800;
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .nav-links a {{
                margin: 0 15px;
                color: #333;
                text-decoration: none;
                font-weight: 500;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 40px 20px; }}
            .header {{
                margin-bottom: 30px;
            }}
            .header h1 {{ font-size: 32px; color: #333; margin-bottom: 10px; }}
            .plan-badge {{
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                padding: 8px 20px;
                border-radius: 20px;
                display: inline-block;
                font-size: 14px;
                font-weight: 600;
            }}
            .stats-grid {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
                gap: 20px; 
                margin: 30px 0; 
            }}
            .stat-card {{ 
                background: white; 
                padding: 30px; 
                border-radius: 15px; 
                text-align: center;
                box-shadow: 0 5px 20px rgba(0,0,0,0.05);
                transition: transform 0.3s;
            }}
            .stat-card:hover {{
                transform: translateY(-5px);
            }}
            .stat-number {{ 
                font-size: 42px; 
                font-weight: 800; 
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 10px;
            }}
            .stat-label {{ color: #666; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }}
            .card {{ 
                background: white; 
                padding: 30px; 
                margin: 20px 0; 
                border-radius: 15px;
                box-shadow: 0 5px 20px rgba(0,0,0,0.05);
            }}
            .btn {{ 
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white; 
                padding: 12px 25px; 
                text-decoration: none; 
                border-radius: 25px; 
                display: inline-block; 
                margin: 5px;
                font-weight: 600;
                transition: all 0.3s;
            }}
            .btn:hover {{
                transform: scale(1.05);
                box-shadow: 0 5px 20px rgba(102,126,234,0.3);
            }}
        </style>
    </head>
    <body>
        <div class="nav">
            <div class="logo">🤖 LeaX AI</div>
            <div class="nav-links">
                <a href="/dashboard">Dashboard</a>
                <a href="/customize">Customize</a>
                <a href="/test-agent">Test Agent</a>
                <a href="/leads">Leads</a>
                <a href="/analytics">Analytics</a>
                <a href="/pricing">Upgrade</a>
                <a href="/logout">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="header">
                <h1>Welcome back, {session['business_name']}!</h1>
                <span class="plan-badge">🎯 {user_dict.get('plan_type', 'Basic').upper()} PLAN</span>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{lead_stats_dict.get('total_leads', 0)}</div>
                    <div class="stat-label">Total Leads</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{analytics['total_messages'] if analytics else 0}</div>
                    <div class="stat-label">Messages</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{analytics['total_calls'] if analytics else 0}</div>
                    <div class="stat-label">Calls</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{lead_stats_dict.get('meetings_scheduled', 0)}</div>
                    <div class="stat-label">Meetings Scheduled</div>
                </div>
            </div>
            
            <div class="card">
                <h3 style="margin-bottom: 20px;">Quick Actions</h3>
                <a href="/customize" class="btn">⚙️ Customize Agent</a>
                <a href="/test-agent" class="btn">💬 Test Agent</a>
                <a href="/leads" class="btn">📋 View Leads</a>
                <a href="/analytics" class="btn">📊 Analytics</a>
                <a href="/pricing" class="btn">⭐ Upgrade Plan</a>
            </div>
        </div>
    </body>
    </html>
    '''

# ==================== CUSTOMIZE AGENT ====================
@app.route('/customize')
def customize_agent():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM business_info WHERE user_id = ?', (session['user_id'],))
        business = c.fetchone()
    
    existing_url = business['website_url'] if business else ''
    existing_info = business['custom_info'] if business else ''
    existing_personality = business['agent_personality'] if business else 'Sarah'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Customize Agent - LeaX</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: #f5f7fa;
                min-height: 100vh;
            }}
            .nav {{
                background: white;
                padding: 20px 40px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .logo {{
                font-size: 24px;
                font-weight: 800;
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 40px 20px; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }}
            .form-section {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 5px 20px rgba(0,0,0,0.05); }}
            .preview-section {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 5px 20px rgba(0,0,0,0.05); }}
            input, textarea, select {{ 
                width: 100%; 
                padding: 12px 15px; 
                margin: 10px 0; 
                border: 2px solid #e2e8f0; 
                border-radius: 10px; 
                font-size: 15px;
                font-family: inherit;
                transition: border-color 0.3s;
            }}
            input:focus, textarea:focus, select:focus {{
                outline: none;
                border-color: #667eea;
            }}
            button {{ 
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white; 
                padding: 15px 30px; 
                border: none; 
                cursor: pointer; 
                width: 100%; 
                border-radius: 10px; 
                font-size: 16px;
                font-weight: 600;
                margin-top: 20px;
                transition: all 0.3s;
            }}
            button:hover:not(:disabled) {{
                transform: scale(1.02);
            }}
            button:disabled {{ 
                background: #ccc; 
                cursor: not-allowed;
            }}
            .message {{ 
                padding: 15px; 
                margin: 15px 0; 
                border-radius: 10px; 
                display: none;
            }}
            .success {{ 
                background: #d4edda; 
                color: #155724; 
                display: block; 
            }}
            .info-banner {{ 
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                padding: 20px; 
                border-radius: 10px; 
                margin: 20px 0;
            }}
            .preview-message {{ 
                background: #f8f9fa; 
                padding: 20px; 
                margin: 15px 0; 
                border-radius: 10px; 
                border-left: 4px solid #667eea; 
            }}
            h2 {{ color: #333; margin-bottom: 10px; }}
            h3 {{ color: #333; margin: 20px 0 10px 0; }}
            label {{ 
                display: block; 
                color: #666; 
                font-weight: 600; 
                margin-top: 15px; 
            }}
            small {{ color: #999; font-size: 13px; }}
            .back-link {{
                display: inline-block;
                color: #667eea;
                text-decoration: none;
                margin-top: 20px;
                font-weight: 600;
            }}
            @media (max-width: 968px) {{
                .grid {{ grid-template-columns: 1fr; }}
            }}
        </style>
    </head>
    <body>
        <div class="nav">
            <div class="logo">🤖 LeaX AI</div>
            <div><a href="/dashboard" style="color: #667eea; text-decoration: none; font-weight: 600;">← Back to Dashboard</a></div>
        </div>
        
        <div class="container">
            <h2>Customize Your AI Agent</h2>
            
            <div class="info-banner">
                <strong>💡 Pro Tip:</strong> Just paste your website URL and we'll automatically learn about your business - services, pricing, hours, and more!
            </div>
            
            <div id="message" class="message"></div>
            
            <div class="grid">
                <div class="form-section">
                    <h3>Business Information</h3>
                    <form id="customizeForm">
                        <label>Website URL</label>
                        <input type="text" id="website_url" placeholder="example.com" value="{existing_url}">
                        <small>No need to type https:// - we'll add it automatically!</small>
                        
                        <label>About Your Business</label>
                        <textarea id="custom_info" placeholder="Tell us about your services, pricing, hours, specialties..." rows="6">{existing_info}</textarea>
                        <small>The more details you provide, the better your AI will respond</small>
                        
                        <label>Agent Name</label>
                        <input type="text" id="agent_name" placeholder="e.g., Sarah, Mike, Jessica" value="{existing_personality}">
                        <small>Give your AI a friendly name customers will love</small>
                        
                        <button type="submit" id="saveBtn">💾 Save & Preview Response</button>
                    </form>
                </div>
                
                <div class="preview-section">
                    <h3>🎯 Preview: How Your AI Will Respond</h3>
                    <div id="previewArea">
                        <p style="color: #999; text-align: center; padding: 60px 20px;">Fill out the form and click "Save & Preview" to see how your AI will sound with real customer questions!</p>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            document.getElementById('customizeForm').addEventListener('submit', function(e) {{
                e.preventDefault();
                
                const saveBtn = document.getElementById('saveBtn');
                const message = document.getElementById('message');
                
                saveBtn.disabled = true;
                saveBtn.textContent = '⏳ Saving & Learning From Your Website...';
                
                const data = {{
                    website_url: document.getElementById('website_url').value,
                    custom_info: document.getElementById('custom_info').value,
                    agent_name: document.getElementById('agent_name').value
                }};
                
                fetch('/api/save-customization', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(data)
                }})
                .then(response => response.json())
                .then(result => {{
                    message.className = 'message success';
                    message.textContent = '✅ Saved! Your AI is now trained. Check the preview →';
                    
                    const preview = document.getElementById('previewArea');
                    preview.innerHTML = `
                        <div class="preview-message">
                            <p style="margin-bottom: 15px;"><strong>Customer:</strong> "Do you offer emergency services?"</p>
                            <p style="margin-bottom: 20px;"><strong>${{data.agent_name}}:</strong> "${{result.preview}}"</p>
                        </div>
                        <p style="text-align: center; margin-top: 30px;">
                            <a href="/test-agent" style="background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 15px 30px; text-decoration: none; border-radius: 25px; display: inline-block; font-weight: 600;">
                                💬 Test Live Chat Now →
                            </a>
                        </p>
                    `;
                    
                    saveBtn.disabled = false;
                    saveBtn.textContent = '💾 Save & Preview Response';
                    
                    // Scroll to preview
                    preview.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }})
                .catch(error => {{
                    message.className = 'message';
                    message.style.background = '#fee';
                    message.style.color = '#c33';
                    message.style.display = 'block';
                    message.textContent = '❌ Error saving. Please try again.';
                    saveBtn.disabled = false;
                    saveBtn.textContent = '💾 Save & Preview Response';
                }});
            }});
        </script>
    </body>
    </html>
    '''

@app.route('/api/save-customization', methods=['POST'])
def save_customization():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    data = request.json
    website_url = data.get('website_url', '')
    custom_info = data.get('custom_info', '')
    agent_name = data.get('agent_name', 'Sarah')
    
    # AUTOMATIC URL NORMALIZATION
    if website_url:
        website_url = normalize_url(website_url)
    
    # Scrape website if URL provided - ENHANCED
    website_context = ""
    if website_url:
        print(f"🔍 Scraping website: {website_url}")
        scraped = scrape_website_info(website_url)
        if scraped:
            website_context = f"""
Website: {scraped['title']}
Description: {scraped['description']}
Services Found: {scraped['services_found']}
Pricing Info: {scraped['pricing_indicators']}
Content Summary: {scraped['content_summary']}
"""
            print(f"✅ Website scraped successfully")
        else:
            print(f"⚠️ Could not scrape website")
    
    # Combine custom info with website context
    full_context = custom_info + "\n\n" + website_context if website_context else custom_info
    
    # Save to database
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO business_info 
            (user_id, website_url, custom_info, agent_personality, updated_at) 
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (session['user_id'], website_url, full_context, agent_name))
        conn.commit()
    
    # Save to memory manager for PERSISTENT STORAGE
    memory_mgr.update_business_profile(session['user_id'], {
        'website_url': website_url,
        'custom_info': full_context,
        'personality': agent_name
    })
    
    print(f"✅ Customization saved for user {session['user_id']}")
    
    # Generate preview response
    business_context = f"""
Business: {session.get('business_name')}
Services: {full_context or 'Full service provider'}
Website: {website_url or 'Not provided'}
"""
    
    preview_response, _ = generate_human_response(
        session.get('business_name'),
        business_context,
        "Do you offer emergency services?",
        ""
    )
    
    return jsonify({'success': True, 'preview': preview_response})

# ==================== TEST AGENT ====================
@app.route('/test-agent')
def test_agent():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        
        # Get business info for examples
        c.execute('SELECT * FROM business_info WHERE user_id = ?', (session['user_id'],))
        business = c.fetchone()
    
    # Generate personalized examples
    examples = generate_example_prompts(
        session.get('business_name'),
        business['custom_info'] if business else None
    )
    
    # NO MORE TRIAL LIMITS - users can test freely
    return render_template('test_agent_modern.html', 
                         examples=examples,
                         trials_remaining=None)

@app.route('/api/test-chat', methods=['POST'])
def test_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    data = request.json
    user_message = data.get('message')
    
    # SIMULATE HUMAN TYPING DELAY (1-3 seconds based on message length)
    import time
    typing_delay = min(3, max(1, len(user_message) * 0.05))  # More realistic
    time.sleep(typing_delay)
    
    # Get conversation history from PERSISTENT MEMORY
    conversation_context = memory_mgr.get_conversation_context(
        session['user_id'], 
        'TEST-USER',
        last_n_messages=10
    )
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM business_info WHERE user_id = ?', (session['user_id'],))
        business = c.fetchone()
    
    business_context = f"""
Business: {session.get('business_name')}
Services: {business['custom_info'] if business and business['custom_info'] else 'Full service provider - professional services'}
Website: {business['website_url'] if business and business['website_url'] else 'Not provided'}
"""
    
    # Generate HUMAN response
    ai_reply, tokens = generate_human_response(
        session.get('business_name'),
        business_context,
        user_message,
        conversation_context
    )
    
    # PERSISTENT STORAGE - Log to memory
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
        'ai_response': ai_reply,
        'ai_model': 'gpt-4',
        'tokens': 0,
        'cost': 0
    })
    
    # CREATE/UPDATE LEAD FROM TEST CONVERSATIONS TOO
    with get_db() as conn:
        c = conn.cursor()
        
        # Save conversation
        c.execute('''
            INSERT INTO conversations (user_id, phone_number, message_text, response_text, message_direction, tokens_used, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], 'TEST-USER', user_message, ai_reply, 'incoming', tokens, tokens * 0.00003))
        
        c.execute('''
            INSERT INTO conversations (user_id, phone_number, message_text, response_text, message_direction)
            VALUES (?, ?, ?, ?, ?)
        ''', (session['user_id'], 'TEST-USER', ai_reply, '', 'outgoing'))
        
        # CREATE OR UPDATE LEAD
        c.execute('SELECT * FROM leads WHERE phone_number = ? AND user_id = ?', ('TEST-USER', session['user_id']))
        existing_lead = c.fetchone()
        
        intent_analysis = analyze_customer_intent(user_message)
        
        # Detect if sale was closed
        sale_closed = check_for_sale_closed(user_message, ai_reply)
        meeting_scheduled = check_for_meeting_info(user_message, ai_reply)
        
        if existing_lead:
            lead_id = existing_lead['id']
            
            # Calculate new score
            has_contact_info = bool(existing_lead['contact_name'] or existing_lead['contact_email'])
            new_score = calculate_lead_score(intent_analysis, len(user_message), has_contact_info, meeting_scheduled or sale_closed or existing_lead['meeting_scheduled'])
            
            updates = []
            params = []
            
            if intent_analysis.get('project_type') != 'general_inquiry':
                updates.append('project_type = ?')
                params.append(intent_analysis['project_type'])
            
            if intent_analysis.get('urgency') != 'flexible':
                updates.append('urgency = ?')
                params.append(intent_analysis['urgency'])
            
            if meeting_scheduled or sale_closed:
                updates.append('meeting_scheduled = 1')
                if not existing_lead['meeting_scheduled']:
                    updates.append('meeting_datetime = CURRENT_TIMESTAMP')
            
            updates.append('lead_score = ?')
            params.append(new_score)
            updates.append('last_contact = CURRENT_TIMESTAMP')
            updates.append('updated_at = CURRENT_TIMESTAMP')
            
            params.append(lead_id)
            
            c.execute(f'''
                UPDATE leads 
                SET {', '.join(updates)}
                WHERE id = ?
            ''', params)
            
        else:
            # CREATE new lead
            lead_score = calculate_lead_score(intent_analysis, len(user_message), False, meeting_scheduled or sale_closed)
            
            c.execute('''
                INSERT INTO leads 
                (user_id, phone_number, project_type, urgency, budget, status, lead_score, meeting_scheduled)
                VALUES (?, ?, ?, ?, ?, 'new', ?, ?)
            ''', (session['user_id'], 'TEST-USER', 
                  intent_analysis.get('project_type', 'inquiry'),
                  intent_analysis.get('urgency', 'flexible'),
                  intent_analysis.get('potential_budget', 'unknown'),
                  lead_score,
                  1 if (meeting_scheduled or sale_closed) else 0))
            
            lead_id = c.lastrowid
        
        # Log lead conversation
        c.execute('''
            INSERT INTO lead_conversations 
            (lead_id, user_id, message_text, response_text, intent_detected, needs_identified)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (lead_id, session['user_id'], user_message, ai_reply, 
              json.dumps(intent_analysis), intent_analysis.get('key_requirements', '')))
        
        conn.commit()
    
    # Update memory manager
    memory_mgr.update_customer_info(session['user_id'], 'TEST-USER', {
        'last_inquiry': user_message,
        'meeting_scheduled': meeting_scheduled or sale_closed,
        'notes': f"Sale closed: {sale_closed}, Meeting: {meeting_scheduled}" if (sale_closed or meeting_scheduled) else None
    })
    
    print(f"✅ Test conversation + LEAD logged for user {session['user_id']}")
    
    return jsonify({'reply': ai_reply, 'typing_time': typing_delay})

# ==================== LIVE AGENT ENDPOINT ====================
@app.route('/agent/<user_id>', methods=['POST'])
def ai_agent(user_id):
    """Live AI agent - handles SMS and VOICE CALLS - FULL PERSISTENCE"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = ? AND is_active = 1', (user_id,))
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
        
        # Get FULL conversation history from PERSISTENT MEMORY
        conversation_context = memory_mgr.get_conversation_context(
            user_id, 
            from_number,
            last_n_messages=15
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
        
        # PERSISTENT STORAGE - Log to memory manager
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
            'ai_response': ai_reply,
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
        
        # Create/Update Lead with FULL PERSISTENCE
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM leads WHERE phone_number = ? AND user_id = ?', (from_number, user_id))
            existing_lead = c.fetchone()
            
            intent_analysis = analyze_customer_intent(incoming_msg)
            
            # Check if meeting was scheduled
            meeting_scheduled = check_for_meeting_info(incoming_msg, ai_reply)
            
            if existing_lead:
                lead_id = existing_lead['id']
                
                # UPDATE existing lead
                has_contact_info = bool(existing_lead['contact_name'] or existing_lead['contact_email'])
                new_score = calculate_lead_score(intent_analysis, len(incoming_msg), has_contact_info, meeting_scheduled or existing_lead['meeting_scheduled'])
                
                updates = []
                params = []
                
                if intent_analysis.get('project_type') != 'general_inquiry':
                    updates.append('project_type = ?')
                    params.append(intent_analysis['project_type'])
                
                if intent_analysis.get('urgency') != 'flexible':
                    updates.append('urgency = ?')
                    params.append(intent_analysis['urgency'])
                
                if intent_analysis.get('potential_budget') != 'unknown':
                    updates.append('budget = ?')
                    params.append(intent_analysis['potential_budget'])
                
                if meeting_scheduled and not existing_lead['meeting_scheduled']:
                    updates.append('meeting_scheduled = 1')
                    updates.append('meeting_datetime = CURRENT_TIMESTAMP')
                
                updates.append('lead_score = ?')
                params.append(new_score)
                updates.append('last_contact = CURRENT_TIMESTAMP')
                updates.append('updated_at = CURRENT_TIMESTAMP')
                
                params.append(lead_id)
                
                c.execute(f'''
                    UPDATE leads 
                    SET {', '.join(updates)}
                    WHERE id = ?
                ''', params)
                
                # Update memory manager
                memory_mgr.update_customer_info(user_id, from_number, {
                    'last_inquiry': incoming_msg,
                    'meeting_scheduled': meeting_scheduled
                })
                
            else:
                # CREATE new lead
                lead_score = calculate_lead_score(intent_analysis, len(incoming_msg), False, meeting_scheduled)
                
                c.execute('''
                    INSERT INTO leads 
                    (user_id, phone_number, project_type, urgency, budget, status, lead_score, meeting_scheduled)
                    VALUES (?, ?, ?, ?, ?, 'new', ?, ?)
                ''', (user_id, from_number, 
                      intent_analysis.get('project_type', 'inquiry'),
                      intent_analysis.get('urgency', 'flexible'),
                      intent_analysis.get('potential_budget', 'unknown'),
                      lead_score,
                      1 if meeting_scheduled else 0))
                
                lead_id = c.lastrowid
                
                # Add to memory manager
                memory_mgr.update_customer_info(user_id, from_number, {
                    'first_contact': datetime.now().isoformat(),
                    'last_inquiry': incoming_msg,
                    'meeting_scheduled': meeting_scheduled
                })
            
            conn.commit()
            
            # Update lead conversation
            update_lead_conversation(lead_id, user_id, incoming_msg, ai_reply, intent_analysis)
            
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
        
        # Log call to PERSISTENT memory
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
        resp.say(
            f"Hi! You've reached {user['business_name']}. For fastest service, please text us at this number and we'll get right back to you with pricing and availability.",
            voice='alice',
            language='en-US'
        )
        
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
        resp.say(f'Great! Text this number and we will respond right away. Thanks!', voice='alice')
    else:
        resp.say('Sorry, I did not get that. Please call back or text us. Goodbye!', voice='alice')
    
    resp.hangup()
    return str(resp)

@app.route('/agent/<user_id>/voicemail', methods=['POST'])
def handle_voicemail(user_id):
    """Handle voicemail recording"""
    recording_url = request.form.get('RecordingUrl', '')
    from_number = request.form.get('From', '')
    
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
            SELECT l.*, 
                   (SELECT COUNT(*) FROM lead_conversations lc WHERE lc.lead_id = l.id) as message_count
            FROM leads l
            WHERE l.user_id = ? 
            ORDER BY l.lead_score DESC, l.last_contact DESC
            LIMIT 100
        ''', (session['user_id'],))
        leads = [dict(row) for row in c.fetchall()]
    
    if not leads:
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Leads - LeaX</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }}
                .empty-state {{ 
                    background: white; 
                    padding: 60px 40px; 
                    border-radius: 20px; 
                    text-align: center;
                    max-width: 600px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.2);
                }}
                .empty-state h1 {{ color: #333; margin-bottom: 15px; }}
                .empty-state p {{ color: #666; margin-bottom: 30px; }}
                .btn {{ 
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white; 
                    padding: 15px 30px; 
                    text-decoration: none; 
                    border-radius: 25px; 
                    display: inline-block; 
                    margin: 10px;
                    font-weight: 600;
                }}
            </style>
        </head>
        <body>
            <div class="empty-state">
                <h1>📋 No Leads Yet</h1>
                <p>Test your agent to see how it captures and tracks leads automatically!</p>
                <a href="/test-agent" class="btn">💬 Test Agent</a>
                <a href="/dashboard" class="btn">🏠 Dashboard</a>
            </div>
        </body>
        </html>
        '''
    
    leads_html = ""
    for lead in leads:
        score_color = "#dc3545" if lead['lead_score'] >= 70 else "#fd7e14" if lead['lead_score'] >= 50 else "#666"
        meeting_badge = '✅ MEETING SET' if lead.get('meeting_scheduled') else ''
        
        leads_html += f'''
        <div class="lead-card" style="border-left-color: {score_color};">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 15px;">
                <div>
                    <h3 style="margin: 0; color: #333;">📞 {lead['phone_number']}</h3>
                    <p style="color: {score_color}; font-weight: bold; margin: 5px 0;">Score: {lead['lead_score']}/100</p>
                </div>
                <div style="text-align: right;">
                    <span class="status-badge" style="background: {score_color};">
                        {lead['status'].upper()}
                    </span>
                    {f'<br><span class="meeting-badge">{meeting_badge}</span>' if meeting_badge else ''}
                </div>
            </div>
            <div class="lead-details">
                <p><strong>Name:</strong> {lead.get('contact_name') or 'Not provided'}</p>
                <p><strong>Email:</strong> {lead.get('contact_email') or 'Not provided'}</p>
                <p><strong>Project:</strong> {lead.get('project_type') or 'Not specified'}</p>
                <p><strong>Urgency:</strong> {lead.get('urgency') or 'Not specified'}</p>
                <p><strong>Budget:</strong> {lead.get('budget') or 'Not specified'}</p>
                <p><strong>Messages:</strong> {lead['message_count']}</p>
                <p><strong>Last Contact:</strong> {lead['last_contact']}</p>
                {f"<p><strong>Meeting:</strong> {lead.get('meeting_datetime', 'Time TBD')}</p>" if lead.get('meeting_scheduled') else ''}
            </div>
        </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Leads - LeaX</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: #f5f7fa;
                min-height: 100vh;
            }}
            .nav {{
                background: white;
                padding: 20px 40px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .logo {{
                font-size: 24px;
                font-weight: 800;
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 40px 20px; }}
            .header {{ 
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
                margin-bottom: 30px;
            }}
            .header h1 {{ color: #333; }}
            .lead-card {{ 
                background: white; 
                padding: 25px; 
                margin: 20px 0; 
                border-radius: 15px; 
                border-left: 5px solid #ddd;
                box-shadow: 0 5px 20px rgba(0,0,0,0.05);
                transition: transform 0.3s;
            }}
            .lead-card:hover {{
                transform: translateX(10px);
            }}
            .lead-details p {{ 
                margin: 8px 0; 
                color: #666;
            }}
            .status-badge {{
                color: white;
                padding: 6px 15px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 700;
                display: inline-block;
            }}
            .meeting-badge {{
                background: #10b981;
                color: white;
                padding: 6px 15px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 700;
                display: inline-block;
                margin-top: 10px;
            }}
            .btn {{ 
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white; 
                padding: 12px 25px; 
                text-decoration: none; 
                border-radius: 25px; 
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="nav">
            <div class="logo">🤖 LeaX AI</div>
            <div><a href="/dashboard" class="btn">← Dashboard</a></div>
        </div>
        
        <div class="container">
            <div class="header">
                <h1>Your Leads - {session['business_name']}</h1>
            </div>
            <p style="color: #666; margin-bottom: 20px;"><strong>Total:</strong> {len(leads)} leads</p>
            
            {leads_html}
        </div>
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
    
    # Only show if they have data
    if not analytics_data or analytics_data['total_conversations'] == 0:
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Analytics - LeaX</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }}
                .empty-state {{ 
                    background: white; 
                    padding: 60px 40px; 
                    border-radius: 20px; 
                    text-align: center;
                    max-width: 600px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.2);
                }}
                .btn {{ 
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white; 
                    padding: 15px 30px; 
                    text-decoration: none; 
                    border-radius: 25px; 
                    display: inline-block; 
                    margin: 10px;
                    font-weight: 600;
                }}
            </style>
        </head>
        <body>
            <div class="empty-state">
                <h1>📊 No Analytics Yet</h1>
                <p>Start chatting with your agent to see detailed analytics!</p>
                <a href="/test-agent" class="btn">💬 Test Agent</a>
                <a href="/dashboard" class="btn">🏠 Dashboard</a>
            </div>
        </body>
        </html>
        '''
    
    recent_convos = memory['conversation_history'][-30:] if memory else []
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Analytics - LeaX</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: #f5f7fa;
                min-height: 100vh;
            }}
            .nav {{
                background: white;
                padding: 20px 40px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .logo {{
                font-size: 24px;
                font-weight: 800;
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 40px 20px; }}
            .stats-grid {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 20px; 
                margin: 30px 0; 
            }}
            .stat-card {{ 
                background: white; 
                padding: 30px; 
                border-radius: 15px; 
                text-align: center;
                box-shadow: 0 5px 20px rgba(0,0,0,0.05);
            }}
            .stat-number {{ 
                font-size: 42px; 
                font-weight: 800; 
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .activity-log {{ 
                background: white; 
                padding: 20px; 
                margin: 15px 0; 
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            }}
            .btn {{ 
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white; 
                padding: 12px 25px; 
                text-decoration: none; 
                border-radius: 25px; 
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="nav">
            <div class="logo">🤖 LeaX AI</div>
            <div><a href="/dashboard" class="btn">← Dashboard</a></div>
        </div>
        
        <div class="container">
            <h1 style="color: #333; margin-bottom: 30px;">Analytics - {session['business_name']}</h1>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{analytics_data['total_conversations']}</div>
                    <div style="color: #666; margin-top: 10px;">Conversations</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{analytics_data['total_messages']}</div>
                    <div style="color: #666; margin-top: 10px;">Messages</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{analytics_data['total_calls']}</div>
                    <div style="color: #666; margin-top: 10px;">Calls</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{analytics_data['leads_captured']}</div>
                    <div style="color: #666; margin-top: 10px;">Leads</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{analytics_data['meetings_scheduled']}</div>
                    <div style="color: #666; margin-top: 10px;">Meetings</div>
                </div>
            </div>
            
            <h2 style="color: #333; margin: 40px 0 20px 0;">Recent Activity</h2>
            {"".join([f'''
            <div class="activity-log">
                <strong style="color: #667eea;">{convo.get('timestamp', 'N/A')[:19]}</strong> - 
                {convo.get('type', 'N/A').upper()} from {convo.get('from', 'N/A')}
                <br>
                <span style="color: #666; margin-top: 10px; display: block;">{convo.get('content', 'N/A')[:150]}...</span>
            </div>
            ''' for convo in recent_convos])}
        </div>
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
        <title>Pricing - LeaX</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: #f5f7fa;
                min-height: 100vh;
            }
            .nav {
                background: white;
                padding: 20px 40px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .logo {
                font-size: 24px;
                font-weight: 800;
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; }
            .pricing-grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
                gap: 30px; 
                margin: 40px 0; 
            }
            .plan { 
                background: white;
                border: 2px solid #e2e8f0; 
                padding: 40px 30px; 
                border-radius: 15px; 
                text-align: center;
                transition: all 0.3s;
            }
            .plan:hover {
                transform: translateY(-10px);
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }
            .plan.featured {
                border-color: #667eea;
                border-width: 3px;
                position: relative;
            }
            .plan.featured::before {
                content: "⭐ RECOMMENDED";
                position: absolute;
                top: -15px;
                left: 50%;
                transform: translateX(-50%);
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                padding: 5px 20px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 700;
            }
            .plan h3 { font-size: 24px; margin-bottom: 15px; color: #333; }
            .plan .price { 
                font-size: 48px; 
                font-weight: 800; 
                color: #667eea; 
                margin: 20px 0;
            }
            .plan .price span { font-size: 18px; color: #666; font-weight: 400; }
            .plan ul { 
                list-style: none; 
                text-align: left; 
                margin: 30px 0;
            }
            .plan ul li { 
                padding: 12px 0; 
                border-bottom: 1px solid #f0f0f0;
                color: #555;
            }
            .plan ul li::before { 
                content: "✓ "; 
                color: #10b981; 
                font-weight: bold; 
                margin-right: 10px;
            }
            .btn { 
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white; 
                padding: 15px 40px; 
                border-radius: 30px; 
                border: none;
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                transition: all 0.3s;
            }
            .btn:hover {
                transform: scale(1.05);
            }
        </style>
    </head>
    <body>
        <div class="nav">
            <div class="logo">🤖 LeaX AI</div>
            <div><a href="/dashboard" style="color: #667eea; text-decoration: none; font-weight: 600;">← Dashboard</a></div>
        </div>
        
        <div class="container">
            <h1 style="text-align: center; color: #333; margin-bottom: 15px;">Choose Your Plan</h1>
            <p style="text-align: center; color: #666; margin-bottom: 40px;">All plans include 24/7 AI agent, unlimited conversations, and lead tracking</p>
            
            <div class="pricing-grid">
                <div class="plan">
                    <h3>Basic</h3>
                    <div class="price">$29<span>/mo</span></div>
                    <ul>
                        <li>AI Phone & SMS Agent</li>
                        <li>Natural Conversations</li>
                        <li>Basic Lead Tracking</li>
                        <li>Email Notifications</li>
                        <li>Website Integration</li>
                        <li>Conversation History</li>
                    </ul>
                    <button onclick="alert('Contact us to activate: hr@americanpower.us')" class="btn">Select Basic</button>
                </div>
                
                <div class="plan featured">
                    <h3>Standard</h3>
                    <div class="price">$59<span>/mo</span></div>
                    <ul>
                        <li>Everything in Basic</li>
                        <li>Advanced Lead Scoring</li>
                        <li>Meeting Scheduler</li>
                        <li>Conversation Analytics</li>
                        <li>Priority Support</li>
                        <li>Custom AI Training</li>
                        <li>No Rate Limits</li>
                    </ul>
                    <button onclick="alert('Contact us to activate: hr@americanpower.us')" class="btn">Select Standard</button>
                </div>
                
                <div class="plan">
                    <h3>Enterprise</h3>
                    <div class="price">$149<span>/mo</span></div>
                    <ul>
                        <li>Everything in Standard</li>
                        <li>Multi-Agent Support</li>
                        <li>CRM Integration</li>
                        <li>Advanced Analytics</li>
                        <li>White-Label Option</li>
                        <li>Dedicated Account Manager</li>
                        <li>Custom Features</li>
                    </ul>
                    <button onclick="alert('Contact us to activate: hr@americanpower.us')" class="btn">Select Enterprise</button>
                </div>
            </div>
            
            <div style="background: white; padding: 40px; border-radius: 15px; margin-top: 40px; box-shadow: 0 5px 20px rgba(0,0,0,0.05);">
                <h3 style="color: #333; margin-bottom: 20px;">🚀 Complete Setup Instructions</h3>
                
                <div style="background: #f0f9ff; padding: 20px; border-radius: 10px; margin-bottom: 20px; border-left: 4px solid #667eea;">
                    <h4 style="color: #333; margin-bottom: 10px;">Step 1: Get Your Twilio Phone Number</h4>
                    <ol style="color: #666; line-height: 2; margin-left: 20px;">
                        <li>Sign up at <a href="https://www.twilio.com/try-twilio" target="_blank" style="color: #667eea; font-weight: 600;">twilio.com/try-twilio</a> (Free trial available!)</li>
                        <li>Verify your email and phone number</li>
                        <li>In Twilio Console, go to <strong>Phone Numbers → Buy a Number</strong></li>
                        <li>Choose a number that supports <strong>SMS</strong> and <strong>Voice</strong></li>
                        <li>Recommended: Get an 888 or 800 toll-free number for better customer trust</li>
                    </ol>
                </div>
                
                <div style="background: #f0fdf4; padding: 20px; border-radius: 10px; margin-bottom: 20px; border-left: 4px solid #10b981;">
                    <h4 style="color: #333; margin-bottom: 10px;">Step 2: Connect Your AI Agent</h4>
                    <ol style="color: #666; line-height: 2; margin-left: 20px;">
                        <li>In Twilio Console, click on your phone number</li>
                        <li>Scroll to <strong>Messaging Configuration</strong></li>
                        <li>Under "A MESSAGE COMES IN", select <strong>Webhook</strong></li>
                        <li>Enter this URL: <code style="background: #e2e8f0; padding: 4px 10px; border-radius: 5px; color: #333; font-family: monospace;">https://your-domain.com/agent/{session.get('user_id', 'YOUR_USER_ID')}</code></li>
                        <li>Method: <strong>HTTP POST</strong></li>
                        <li>Click <strong>Save</strong></li>
                    </ol>
                </div>
                
                <div style="background: #fef3c7; padding: 20px; border-radius: 10px; margin-bottom: 20px; border-left: 4px solid #f59e0b;">
                    <h4 style="color: #333; margin-bottom: 10px;">Step 3: Enable Voice Calls</h4>
                    <ol style="color: #666; line-height: 2; margin-left: 20px;">
                        <li>Still in your phone number settings</li>
                        <li>Scroll to <strong>Voice Configuration</strong></li>
                        <li>Under "A CALL COMES IN", select <strong>Webhook</strong></li>
                        <li>Enter the SAME URL: <code style="background: #e2e8f0; padding: 4px 10px; border-radius: 5px; color: #333; font-family: monospace;">https://your-domain.com/agent/{session.get('user_id', 'YOUR_USER_ID')}</code></li>
                        <li>Method: <strong>HTTP POST</strong></li>
                        <li>Click <strong>Save</strong></li>
                    </ol>
                </div>
                
                <div style="background: #fce7f3; padding: 20px; border-radius: 10px; margin-bottom: 20px; border-left: 4px solid #ec4899;">
                    <h4 style="color: #333; margin-bottom: 10px;">Step 4: Deploy Your LeaX Server</h4>
                    <ol style="color: #666; line-height: 2; margin-left: 20px;">
                        <li><strong>Option A - Quick Deploy (Recommended for Testing):</strong>
                            <ul style="margin-top: 10px;">
                                <li>Use <a href="https://replit.com" target="_blank" style="color: #667eea;">Replit.com</a> or <a href="https://glitch.com" target="_blank" style="color: #667eea;">Glitch.com</a></li>
                                <li>Upload your LeaX files</li>
                                <li>Set environment variable: <code style="background: #e2e8f0; padding: 2px 8px; border-radius: 3px;">OPENAI_API_KEY=your_key</code></li>
                                <li>Run the app - you'll get a public URL automatically</li>
                            </ul>
                        </li>
                        <li style="margin-top: 15px;"><strong>Option B - Production Deploy:</strong>
                            <ul style="margin-top: 10px;">
                                <li>Deploy to Railway, Heroku, or AWS</li>
                                <li>Get SSL certificate (required by Twilio)</li>
                                <li>Set your domain in Twilio webhook</li>
                            </ul>
                        </li>
                    </ol>
                </div>
                
                <div style="background: #e0e7ff; padding: 20px; border-radius: 10px; border-left: 4px solid #667eea;">
                    <h4 style="color: #333; margin-bottom: 10px;">🎯 Your Webhook URL</h4>
                    <p style="color: #666; margin-bottom: 15px;">Once deployed, your webhook URL will be:</p>
                    <div style="background: #1e293b; color: #10b981; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 14px; overflow-x: auto;">
                        https://YOUR-DOMAIN.com/agent/{session.get('user_id', 'YOUR_USER_ID')}
                    </div>
                    <p style="color: #666; margin-top: 15px; font-size: 14px;">
                        <strong>Note:</strong> Replace <code style="background: #e2e8f0; padding: 2px 6px; border-radius: 3px;">YOUR-DOMAIN.com</code> with your actual domain.
                        Your User ID is: <strong style="color: #667eea;">{session.get('user_id', 'YOUR_USER_ID')}</strong>
                    </p>
                </div>
                
                <div style="background: #dcfce7; padding: 20px; border-radius: 10px; margin-top: 20px; text-align: center;">
                    <h4 style="color: #333; margin-bottom: 10px;">✅ That's It!</h4>
                    <p style="color: #666; margin-bottom: 15px;">Once connected, your AI will automatically:</p>
                    <ul style="color: #666; text-align: left; max-width: 500px; margin: 0 auto; line-height: 2;">
                        <li>✓ Answer all SMS messages instantly</li>
                        <li>✓ Handle voice calls 24/7</li>
                        <li>✓ Capture and score leads</li>
                        <li>✓ Schedule meetings automatically</li>
                        <li>✓ Email you every new lead</li>
                    </ul>
                </div>
                
                <p style="color: #666; text-align: center; margin-top: 30px; line-height: 1.8;">
                    <strong>Need help?</strong> Email us at <a href="mailto:hr@americanpower.us" style="color: #667eea; font-weight: 600;">hr@americanpower.us</a><br>
                    <strong>Watch Video Tutorial:</strong> <a href="#" style="color: #667eea; font-weight: 600;">Coming Soon</a>
                </p>
            </div>
        </div>
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
        
        c.execute('SELECT COUNT(*) as active FROM users WHERE is_active = 1')
        active_users = c.fetchone()['active']
        
        c.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 20')
        recent_users = [dict(row) for row in c.fetchall()]
    
    platform_stats = memory_mgr.get_total_usage_stats()
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin - LeaX</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: Arial; background: #f5f7fa; padding: 20px; }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            h1 {{ color: #333; margin-bottom: 30px; }}
            .stats {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 20px; 
                margin: 30px 0; 
            }}
            .stat-card {{ 
                background: white; 
                padding: 25px; 
                border-radius: 10px; 
                text-align: center;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            }}
            .stat-number {{ font-size: 36px; font-weight: bold; color: #667eea; }}
            table {{ 
                width: 100%; 
                border-collapse: collapse; 
                margin: 30px 0;
                background: white;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            }}
            th, td {{ 
                border: 1px solid #e2e8f0; 
                padding: 12px; 
                text-align: left; 
            }}
            th {{ 
                background: #667eea; 
                color: white;
                font-weight: 600;
            }}
            tr:hover {{ background: #f8f9fa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎛️ LeaX Admin Dashboard</h1>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number">{total_users}</div>
                    <div>Total Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{active_users}</div>
                    <div>Active Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{platform_stats['total_conversations']}</div>
                    <div>Conversations</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{platform_stats['total_messages']}</div>
                    <div>Messages</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${platform_stats['total_cost_usd']:.2f}</div>
                    <div>API Costs</div>
                </div>
            </div>

            <h2 style="color: #333; margin-top: 40px;">Recent Users</h2>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Email</th>
                    <th>Business</th>
                    <th>Plan</th>
                    <th>Status</th>
                    <th>Joined</th>
                    <th>Last Login</th>
                </tr>
                {"".join(f'''
                <tr>
                    <td>{user['id']}</td>
                    <td>{user['email']}</td>
                    <td>{user['business_name']}</td>
                    <td>{user['plan_type']}</td>
                    <td>{user['status']}</td>
                    <td>{user['created_at']}</td>
                    <td>{user['last_login'] or 'Never'}</td>
                </tr>
                ''' for user in recent_users)}
            </table>

            <p style="margin-top: 30px;"><a href="/" style="color: #667eea; text-decoration: none; font-weight: 600;">← Back to Site</a></p>
        </div>
    </body>
    </html>
    '''

# ==================== RUN ====================
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info(f"🚀 LeaX Starting - Database: {DATABASE_FILE}")
    logging.info(f"🔐 Secret Key: leax-super-secure-2024-...")
    logging.info(f"✅ Memory Manager Initialized - PERSISTENT STORAGE ACTIVE")
    logging.info(f"✅ HUMAN AI Responses Active - GPT-4")
    logging.info(f"✅ Website Scanning Enabled - AUTOMATIC https://")
    logging.info(f"✅ No Rate Limits - Unlimited Testing")
    logging.info(f"✅ Full Lead Tracking - Meeting Detection Active")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
