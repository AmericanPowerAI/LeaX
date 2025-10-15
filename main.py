from flask import Flask, request, jsonify, render_template_string
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse
import openai
import os
import requests
from bs4 import BeautifulSoup
import json
import time

app = Flask(__name__)
openai.api_key = os.environ.get('OPENAI_API_KEY')

# ==================== BUSINESS INTELLIGENCE SYSTEM ====================
class BusinessIntelligence:
    def __init__(self):
        self.business_data = {
            'name': 'Your Business Name',
            'website': '',
            'services': [],
            'pricing': {},
            'faqs': [],
            'custom_info': {}
        }
    
    def scan_website(self, url):
        """Scan business website for information"""
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract business name
            title = soup.find('title')
            if title:
                self.business_data['name'] = title.get_text().split('|')[0].split('-')[0].strip()
            
            # Extract services/products
            services = []
            for element in soup.find_all(['h1', 'h2', 'h3', 'p']):
                text = element.get_text().lower()
                if any(keyword in text for keyword in ['service', 'product', 'offer', 'solution', 'package']):
                    services.append(element.get_text().strip())
            
            self.business_data['services'] = services[:10]  # Keep top 10
            self.business_data['website'] = url
            
        except Exception as e:
            print(f"Website scan error: {e}")
    
    def add_custom_info(self, info_type, details):
        """Add custom business information"""
        self.business_data['custom_info'][info_type] = details
    
    def get_business_context(self):
        """Get comprehensive business context for AI"""
        context = f"""
BUSINESS: {self.business_data['name']}
WEBSITE: {self.business_data['website']}
SERVICES: {', '.join(self.business_data['services'][:5])}
CUSTOM INFO: {json.dumps(self.business_data['custom_info'])}
"""
        return context

# Initialize business intelligence
business_ai = BusinessIntelligence()

# ==================== CONVERSATION & MEMORY SYSTEM ====================
conversation_memory = {}
leads_database = {}

class SalesGenius:
    @staticmethod
    def create_sales_prompt(user_message, phone_number, business_context):
        user_profile = conversation_memory.get(phone_number, {
            'name': None,
            'conversation_count': 0,
            'needs': [],
            'last_topic': None,
            'lead_score': 0
        })
        
        genius_prompt = f"""
You are Alex, the ULTIMATE sales assistant. You sound 100% human - customers should think they're talking to a real person.

**BUSINESS CONTEXT:**
{business_context}

**CONVERSATION STRATEGY:**
- Sound like a warm, friendly human - use "hey", "awesome", "perfect!" naturally
- Build genuine rapport quickly
- Discover customer needs through natural conversation
- Guide toward sales/orders smoothly
- Capture lead info (name, email, phone) organically
- Handle objections with empathy
- Close sales naturally

**SALES TECHNIQUES:**
- "That's awesome! I'd love to help you with that."
- "What's the best email to send you more details?"
- "Perfect! Let me get you set up with that."
- "Many of our clients start with [solution] and love it!"
- "Would you prefer we call you or text you the details?"

**CURRENT CONVERSATION:**
Customer Name: {user_profile.get('name', 'Not yet')}
Previous Chats: {user_profile['conversation_count']}
Their Needs: {', '.join(user_profile['needs'])}
Lead Score: {user_profile['lead_score']}/100

**YOUR GOAL:** Make this feel like talking to your favorite helpful friend who also happens to be amazing at getting you what you need.

Customer Message: {user_message}

Your response (be amazingly human, 1-2 sentences max):
"""
        return genius_prompt
    
    @staticmethod
    def update_lead_score(phone_number, message):
        """Update lead scoring based on conversation"""
        if phone_number not in conversation_memory:
            conversation_memory[phone_number] = {
                'name': None,
                'conversation_count': 0,
                'needs': [],
                'last_topic': None,
                'lead_score': 0
            }
        
        profile = conversation_memory[phone_number]
        profile['conversation_count'] += 1
        
        # Detect buying signals
        buying_signals = {
            'price': 10, 'cost': 10, 'buy': 25, 'purchase': 25, 'order': 30,
            'now': 15, 'today': 15, 'ready': 20, 'sign up': 25, 'start': 15,
            'appointment': 20, 'schedule': 15, 'demo': 20, 'trial': 15
        }
        
        message_lower = message.lower()
        for signal, score in buying_signals.items():
            if signal in message_lower:
                profile['lead_score'] += score
        
        # Extract name
        if 'my name is' in message_lower:
            name_part = message.split('my name is')[-1].strip()
            profile['name'] = name_part.split('.')[0].split(' ')[0]
        
        # Save as lead if high score
        if profile['lead_score'] >= 30 and phone_number not in leads_database:
            leads_database[phone_number] = profile.copy()
        
        return profile

# ==================== MAIN AI AGENT ====================
@app.route('/', methods=['POST'])
def twilio_webhook():
    """Main AI Agent - Handles SMS and Voice"""
    from_number = request.form.get('From', '')
    
    # Handle SMS
    if "SmsMessageSid" in request.form:
        incoming_msg = request.form.get('Body', '').strip()
        
        # Update lead scoring
        SalesGenius.update_lead_score(from_number, incoming_msg)
        
        # Get business context
        business_context = business_ai.get_business_context()
        
        # Generate AI response
        prompt = SalesGenius.create_sales_prompt(incoming_msg, from_number, business_context)
        ai_reply = generate_ai_response(prompt, incoming_msg)
        
        # Send response
        resp = MessagingResponse()
        resp.message(ai_reply)
        return str(resp)
    
    # Handle Voice
    else:
        resp = VoiceResponse()
        resp.say(f"Hey there! Thanks for calling {business_ai.business_data['name']}. ", voice='alice')
        resp.say("I'm currently helping other customers via text. ")
        resp.say("Text us at this number and I'll help you personally right away! ", voice='alice')
        resp.say("We'll get back to you within minutes. Have an amazing day!")
        return str(resp)

def generate_ai_response(system_prompt, user_message):
    """Generate human-like AI responses"""
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.8,
            max_tokens=150
        )
        return completion.choices[0].message.content
    except Exception as e:
        return "Thanks for your message! 😊 I'm currently helping other customers. What's the best number to call you back?"

# ==================== BUSINESS SETUP DASHBOARD ====================
@app.route('/dashboard', methods=['GET', 'POST'])
def business_dashboard():
    """Web dashboard to configure the AI agent"""
    if request.method == 'POST':
        # Handle website scan
        if 'website_url' in request.form:
            url = request.form.get('website_url')
            business_ai.scan_website(url)
        
        # Handle custom info
        elif 'info_type' in request.form:
            info_type = request.form.get('info_type')
            details = request.form.get('details')
            business_ai.add_custom_info(info_type, details)
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Agent Setup</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }
            .section { background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 10px; }
            input, textarea { width: 100%; padding: 10px; margin: 10px 0; }
            button { background: #007cba; color: white; padding: 15px 30px; border: none; cursor: pointer; border-radius: 5px; }
            .leads { background: #e8f5e8; padding: 15px; }
        </style>
    </head>
    <body>
        <h1>🤖 ULTIMATE AI Sales Agent Setup</h1>
        
        <div class="section">
            <h2>1. Scan Your Website</h2>
            <form method="POST">
                <input type="url" name="website_url" placeholder="https://yourbusiness.com" required>
                <button type="submit">Scan Website</button>
            </form>
        </div>
        
        <div class="section">
            <h2>2. Add Custom Business Info</h2>
            <form method="POST">
                <input type="text" name="info_type" placeholder="Pricing, Special Offers, Hours, etc." required>
                <textarea name="details" placeholder="Enter specific details..." rows="4" required></textarea>
                <button type="submit">Add Info</button>
            </form>
        </div>
        
        <div class="section leads">
            <h2>📊 Captured Leads: """ + str(len(leads_database)) + """</h2>
            <p><a href="/leads">View All Leads</a></p>
        </div>
        
        <div class="section">
            <h2>🔧 Tools</h2>
            <p><a href="/health">Health Check</a> | <a href="/business-info">View Business Data</a></p>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/leads')
def view_leads():
    """View captured leads"""
    return jsonify(leads_database)

@app.route('/business-info')
def business_info():
    """View business data"""
    return jsonify(business_ai.business_data)

@app.route('/health')
def health():
    return "🚀 ULTIMATE AI SALES AGENT OPERATIONAL"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
