# api_endpoints.py
"""
API Endpoints for Desktop App
Desktop app calls these endpoints instead of having API keys locally
"""

from flask import Blueprint, request, jsonify
from functools import wraps
import jwt
import os
from datetime import datetime, timedelta

api_bp = Blueprint('api', __name__)
SECRET_KEY = os.environ.get('FLASK_SECRET')

# Your API keys (stored on server only)
OPENAI_KEY = os.environ.get('OPENAI_API_KEY')
TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')

def require_auth(f):
    """Verify JWT token from desktop app"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.user_id = data['user_id']
            request.user_email = data['email']
        except:
            return jsonify({'error': 'Invalid token'}), 401
            
        return f(*args, **kwargs)
    return decorated

# ============= AUTHENTICATION =============

@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    """Desktop app login"""
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    from main import get_db, hash_password
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ? AND is_active = 1', (email,))
        user = c.fetchone()
    
    if user and user['password_hash'] == hash_password(password):
        # Generate JWT token
        token = jwt.encode({
            'user_id': user['id'],
            'email': user['email'],
            'business_name': user['business_name'],
            'exp': datetime.utcnow() + timedelta(days=30)
        }, SECRET_KEY, algorithm='HS256')
        
        return jsonify({
            'success': True,
            'token': token,
            'user_id': user['id'],
            'business_name': user['business_name'],
            'email': user['email'],
            'plan': user['plan_type']
        })
    
    return jsonify({'error': 'Invalid credentials'}), 401

@api_bp.route('/auth/validate', methods=['POST'])
@require_auth
def validate_token():
    """Check if token is still valid"""
    return jsonify({
        'valid': True,
        'user_id': request.user_id
    })

# ============= AI CHAT =============

@api_bp.route('/chat/send', methods=['POST'])
@require_auth
def api_chat():
    """Send message to AI (uses YOUR OpenAI key)"""
    data = request.json
    message = data.get('message')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    import openai
    openai.api_key = OPENAI_KEY
    
    from main import generate_human_response, get_db
    from memory_manager import MemoryManager
    
    memory_mgr = MemoryManager()
    
    # Get business context
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM business_info WHERE user_id = ?', (request.user_id,))
        business = c.fetchone()
        
        c.execute('SELECT business_name FROM users WHERE id = ?', (request.user_id,))
        user = c.fetchone()
    
    business_context = f"""
Business: {user['business_name'] if user else 'N/A'}
Services: {business['custom_info'] if business else 'General services'}
"""
    
    conversation_context = memory_mgr.get_conversation_context(
        request.user_id,
        'DESKTOP-TEST',
        last_n_messages=10
    )
    
    # Generate response
    reply, tokens = generate_human_response(
        user['business_name'] if user else 'Business',
        business_context,
        message,
        conversation_context
    )
    
    # Log conversation
    memory_mgr.log_conversation(request.user_id, {
        'type': 'sms',
        'direction': 'inbound',
        'from_number': 'DESKTOP-TEST',
        'to_number': 'AI-AGENT',
        'content': message,
        'ai_response': reply,
        'ai_model': 'gpt-4',
        'tokens': tokens,
        'cost': tokens * 0.00003
    })
    
    return jsonify({
        'reply': reply,
        'tokens_used': tokens,
        'cost': tokens * 0.00003
    })

# ============= PHONE PROVISIONING =============

@api_bp.route('/phone/provision', methods=['POST'])
@require_auth
def api_provision_phone():
    """Provision phone number (uses YOUR Twilio account)"""
    data = request.json
    area_code = data.get('area_code', '800')
    
    from twilio.rest import Client
    from main import get_db
    
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    
    try:
        # Search for available numbers
        available = client.available_phone_numbers('US').local.list(
            area_code=area_code,
            limit=1
        )
        
        if not available:
            return jsonify({'error': 'No numbers available'}), 400
        
        # Get webhook URL
        webhook_url = f"{request.host_url}agent/{request.user_id}"
        
        # Purchase number
        number = client.incoming_phone_numbers.create(
            phone_number=available[0].phone_number,
            sms_url=webhook_url,
            sms_method='POST',
            voice_url=webhook_url,
            voice_method='POST'
        )
        
        # Save to database
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE users 
                SET metadata = json_set(
                    COALESCE(metadata, '{}'),
                    '$.phone_number', ?,
                    '$.phone_sid', ?
                )
                WHERE id = ?
            ''', (number.phone_number, number.sid, request.user_id))
            conn.commit()
        
        return jsonify({
            'success': True,
            'phone_number': number.phone_number,
            'webhook_url': webhook_url
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= ANALYTICS =============

@api_bp.route('/analytics/summary', methods=['GET'])
@require_auth
def api_analytics():
    """Get analytics summary"""
    from memory_manager import MemoryManager
    from main import get_db
    
    memory_mgr = MemoryManager()
    analytics = memory_mgr.get_customer_analytics(request.user_id)
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) as total_leads,
                   COUNT(CASE WHEN meeting_scheduled = 1 THEN 1 END) as meetings
            FROM leads WHERE user_id = ?
        ''', (request.user_id,))
        lead_stats = c.fetchone()
    
    return jsonify({
        'total_messages': analytics.get('total_messages', 0) if analytics else 0,
        'total_calls': analytics.get('total_calls', 0) if analytics else 0,
        'total_leads': lead_stats['total_leads'] if lead_stats else 0,
        'meetings_scheduled': lead_stats['meetings'] if lead_stats else 0
    })

# ============= FUNDING TRACKER =============

@api_bp.route('/funding/earnings', methods=['GET'])
@require_auth
def api_funding_earnings():
    """Get monthly funding earnings"""
    from funding_tracker import FundingTracker
    
    tracker = FundingTracker()
    earnings = tracker.get_monthly_earnings(request.user_id)
    
    return jsonify(earnings)

# ============= BUSINESS CUSTOMIZATION =============

@api_bp.route('/business/update', methods=['POST'])
@require_auth
def api_update_business():
    """Update business information"""
    data = request.json
    
    from main import get_db
    from memory_manager import MemoryManager
    
    website_url = data.get('website_url')
    custom_info = data.get('custom_info')
    agent_name = data.get('agent_name')
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE business_info 
            SET website_url = ?,
                custom_info = ?,
                agent_personality = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (website_url, custom_info, agent_name, request.user_id))
        conn.commit()
    
    memory_mgr = MemoryManager()
    memory_mgr.update_business_profile(request.user_id, {
        'website_url': website_url,
        'custom_info': custom_info,
        'personality': agent_name
    })
    
    return jsonify({'success': True})

def register_api_routes(app):
    """Register API blueprint"""
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    print("✅ Desktop API routes registered")
