# api_endpoints.py
"""
API Endpoints for Desktop App + Web Dashboard
"""

from flask import Blueprint, request, jsonify, session
from functools import wraps
import jwt
import os
from datetime import datetime, timedelta

api_bp = Blueprint('api', __name__)
SECRET_KEY = os.environ.get('FLASK_SECRET')

OPENAI_KEY = os.environ.get('OPENAI_API_KEY')
TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')


def require_auth(f):
    """Accept either JWT token (desktop) or Flask session (web dashboard)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Web dashboard: session-based auth
        if 'user_id' in session:
            request.user_id = session['user_id']
            request.user_email = session.get('email', '')
            return f(*args, **kwargs)

        # Desktop app: JWT auth
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Not authenticated'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.user_id = data['user_id']
            request.user_email = data['email']
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401

        return f(*args, **kwargs)
    return decorated


# ============= AUTHENTICATION =============

@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    data = request.json or {}
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')

    from main import get_db, hash_password

    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ? AND is_active = 1', (email,))
        user = c.fetchone()

    if not user or user['password_hash'] != hash_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401

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


@api_bp.route('/auth/web-token', methods=['POST'])
def web_token():
    """Exchange active Flask session for a JWT used by dashboard JS"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    token = jwt.encode({
        'user_id': session['user_id'],
        'email': session.get('email', ''),
        'business_name': session.get('business_name', ''),
        'exp': datetime.utcnow() + timedelta(days=1)
    }, SECRET_KEY, algorithm='HS256')

    return jsonify({'token': token})


@api_bp.route('/auth/validate', methods=['POST'])
@require_auth
def validate_token():
    return jsonify({'valid': True, 'user_id': request.user_id})


# ============= BUSINESS INFO =============

@api_bp.route('/business/info', methods=['GET'])
@require_auth
def api_get_business():
    """Return current business info to pre-fill the knowledge base form"""
    from main import get_db
    import json

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM business_info WHERE user_id = ?', (request.user_id,))
            biz = c.fetchone()
            c.execute('SELECT business_name, plan_type, metadata FROM users WHERE id = ?', (request.user_id,))
            user = c.fetchone()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    phone_number = None
    if user:
        try:
            meta = json.loads(user['metadata'] or '{}')
            phone_number = meta.get('phone_number')
        except Exception:
            pass

    # plan_type from session as fallback
    plan = (user['plan_type'] if user else None) or session.get('user_plan', 'basic')

    return jsonify({
        'business_name': session.get('business_name', '') or (user['business_name'] if user else ''),
        'plan_type': plan,
        'agent_name': (biz['agent_personality'] if biz else '') or '',
        'website_url': (biz['website_url'] if biz else '') or '',
        'custom_info': (biz['custom_info'] if biz else '') or '',
        'phone_number': phone_number
    })


@api_bp.route('/business/update', methods=['POST'])
@require_auth
def api_update_business():
    """Update business / knowledge base info"""
    data = request.json or {}
    from main import get_db
    from memory_manager import MemoryManager

    website_url = data.get('website_url') or None
    custom_info = data.get('custom_info') or None
    agent_name  = data.get('agent_name') or None

    try:
        with get_db() as conn:
            c = conn.cursor()
            fields, params = [], []
            if website_url is not None:
                fields.append('website_url = ?'); params.append(website_url)
            if custom_info is not None:
                fields.append('custom_info = ?'); params.append(custom_info)
            if agent_name is not None:
                fields.append('agent_personality = ?'); params.append(agent_name)
            fields.append('updated_at = CURRENT_TIMESTAMP')

            if fields:
                params.append(request.user_id)
                c.execute(f'UPDATE business_info SET {", ".join(fields)} WHERE user_id = ?', params)
                if c.rowcount == 0:
                    c.execute('''
                        INSERT INTO business_info (user_id, website_url, custom_info, agent_personality)
                        VALUES (?, ?, ?, ?)
                    ''', (request.user_id, website_url, custom_info, agent_name or 'Customer Service'))
                conn.commit()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    try:
        MemoryManager().update_business_profile(request.user_id, {
            k: v for k, v in {
                'website_url': website_url,
                'custom_info': custom_info,
                'personality': agent_name
            }.items() if v is not None
        })
    except Exception:
        pass  # memory manager failure shouldn't break the save

    return jsonify({'success': True})


# ============= WEBSITE SCANNING =============

@api_bp.route('/scan-website', methods=['POST'])
@require_auth
def api_scan_website():
    """Scan a website and update business_info with scraped context"""
    data = request.json or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    from main import scrape_website_info, normalize_url, get_db
    from memory_manager import MemoryManager

    url = normalize_url(url)

    try:
        scraped = scrape_website_info(url)
    except Exception as e:
        return jsonify({'error': f'Could not reach website: {str(e)}'}), 422

    if not scraped:
        return jsonify({'error': 'Could not read website content. Check the URL and try again.'}), 422

    website_context = (
        f"Website: {scraped.get('title', '')}\n"
        f"Description: {scraped.get('description', '')}\n"
        f"Services Found: {scraped.get('services_found', '')}\n"
        f"Pricing Info: {scraped.get('pricing_indicators', '')}\n"
        f"Content Summary: {scraped.get('content_summary', '')}"
    )

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT custom_info FROM business_info WHERE user_id = ?', (request.user_id,))
            existing = c.fetchone()
            existing_info = (existing['custom_info'] or '') if existing else ''
            if '--- Website Scan ---' in existing_info:
                existing_info = existing_info[:existing_info.index('--- Website Scan ---')].strip()
            full_context = (existing_info + '\n\n--- Website Scan ---\n' + website_context).strip()

            if existing:
                c.execute('''
                    UPDATE business_info
                    SET website_url = ?, custom_info = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (url, full_context, request.user_id))
            else:
                c.execute('''
                    INSERT INTO business_info (user_id, website_url, custom_info)
                    VALUES (?, ?, ?)
                ''', (request.user_id, url, full_context))
            conn.commit()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    try:
        MemoryManager().update_business_profile(request.user_id, {
            'website_url': url,
            'custom_info': full_context
        })
    except Exception:
        pass

    return jsonify({
        'success': True,
        'title': scraped.get('title', ''),
        'services_found': scraped.get('services_found', ''),
        'summary': scraped.get('content_summary', '')[:200]
    })


# ============= AI CHAT =============

@api_bp.route('/chat/send', methods=['POST'])
@require_auth
def api_chat():
    data = request.json or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    import openai
    openai.api_key = OPENAI_KEY

    from main import generate_human_response, get_db
    from memory_manager import MemoryManager

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM business_info WHERE user_id = ?', (request.user_id,))
            biz = c.fetchone()
            c.execute('SELECT business_name FROM users WHERE id = ?', (request.user_id,))
            user = c.fetchone()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    biz_name = (user['business_name'] if user else None) or session.get('business_name', 'Business')
    business_context = (
        f"Business: {biz_name}\n"
        f"Services: {biz['custom_info'] if biz and biz['custom_info'] else 'General services'}\n"
        f"Agent Name: {biz['agent_personality'] if biz else 'Customer Service'}"
    )

    memory_mgr = MemoryManager()
    conversation_context = memory_mgr.get_conversation_context(
        request.user_id, 'DESKTOP-TEST', last_n_messages=10
    )

    reply, tokens = generate_human_response(
        biz_name, business_context, message, conversation_context
    )

    memory_mgr.log_conversation(request.user_id, {
        'type': 'sms', 'direction': 'inbound',
        'from_number': 'DESKTOP-TEST', 'to_number': 'AI-AGENT',
        'content': message, 'ai_response': reply,
        'ai_model': 'gpt-4', 'tokens': tokens, 'cost': tokens * 0.00003
    })

    return jsonify({'reply': reply, 'tokens_used': tokens})


# ============= CONVERSATIONS =============

@api_bp.route('/conversations', methods=['GET'])
@require_auth
def api_conversations():
    limit  = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))
    rows = []

    # Try master_tracking.db first
    try:
        import sqlite3 as _sqlite3
        master_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'master_tracking.db')
        if not os.path.exists(master_db):
            master_db = 'master_tracking.db'
        conn = _sqlite3.connect(master_db)
        conn.row_factory = _sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT id, communication_type, direction, from_number, to_number,
                   content, ai_response, duration_seconds, timestamp, intent_detected
            FROM communication_log
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        ''', (request.user_id, limit, offset))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
    except Exception:
        pass

    # Fallback to main conversations table
    if not rows:
        try:
            from main import get_db
            with get_db() as conn:
                c = conn.cursor()
                c.execute('''
                    SELECT id, phone_number, message_text, response_text, created_at
                    FROM conversations
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                ''', (request.user_id, limit, offset))
                for r in c.fetchall():
                    rows.append({
                        'id': r['id'],
                        'communication_type': 'sms',
                        'direction': 'inbound',
                        'from_number': r['phone_number'],
                        'to_number': None,
                        'content': r['message_text'],
                        'ai_response': r['response_text'],
                        'timestamp': r['created_at'],
                        'intent_detected': None
                    })
        except Exception:
            pass

    return jsonify({'conversations': rows, 'total': len(rows)})


# ============= LEADS =============

@api_bp.route('/leads', methods=['GET'])
@require_auth
def api_leads():
    limit  = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))

    try:
        from main import get_db
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT l.id, l.phone_number, l.contact_name, l.business_name,
                       l.project_type, l.urgency, l.budget, l.status,
                       l.lead_score, l.meeting_scheduled,
                       l.last_contact, l.created_at
                FROM leads l
                WHERE l.user_id = ?
                ORDER BY l.lead_score DESC, l.last_contact DESC
                LIMIT ? OFFSET ?
            ''', (request.user_id, limit, offset))
            leads = [dict(r) for r in c.fetchall()]

            c.execute('''
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN status = "new" THEN 1 END) as new_count,
                       COUNT(CASE WHEN lead_score >= 70 THEN 1 END) as hot_count,
                       COUNT(CASE WHEN meeting_scheduled = 1 THEN 1 END) as booked_count
                FROM leads WHERE user_id = ?
            ''', (request.user_id,))
            stats = dict(c.fetchone())
    except Exception as e:
        return jsonify({'leads': [], 'stats': {}, 'error': str(e)})

    return jsonify({'leads': leads, 'stats': stats})


# ============= ANALYTICS =============

@api_bp.route('/analytics/summary', methods=['GET'])
@require_auth
def api_analytics():
    try:
        from memory_manager import MemoryManager
        analytics = MemoryManager().get_customer_analytics(request.user_id) or {}
    except Exception:
        analytics = {}

    try:
        from main import get_db
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT COUNT(*) as total_leads,
                       COUNT(CASE WHEN meeting_scheduled = 1 THEN 1 END) as meetings
                FROM leads WHERE user_id = ?
            ''', (request.user_id,))
            lead_stats = c.fetchone()
    except Exception:
        lead_stats = None

    return jsonify({
        'total_messages':     analytics.get('total_messages', 0),
        'total_calls':        analytics.get('total_calls', 0),
        'total_leads':        lead_stats['total_leads'] if lead_stats else 0,
        'meetings_scheduled': lead_stats['meetings'] if lead_stats else 0
    })


@api_bp.route('/analytics/detailed', methods=['GET'])
@require_auth
def api_analytics_detailed():
    period = request.args.get('period', 'today')

    now = datetime.utcnow()
    if period == 'today':
        since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    elif period == 'week':
        since = (now - timedelta(days=7)).isoformat()
    else:
        since = (now - timedelta(days=30)).isoformat()

    conversations, calls, messages = 0, 0, 0

    try:
        import sqlite3 as _sqlite3
        master_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'master_tracking.db')
        if not os.path.exists(master_db):
            master_db = 'master_tracking.db'
        if os.path.exists(master_db):
            conn = _sqlite3.connect(master_db)
            conn.row_factory = _sqlite3.Row
            c = conn.cursor()
            c.execute('''
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN communication_type = "call" THEN 1 END) as calls,
                       COUNT(CASE WHEN communication_type = "sms"  THEN 1 END) as messages
                FROM communication_log
                WHERE user_id = ? AND timestamp >= ?
            ''', (request.user_id, since))
            row = c.fetchone()
            if row:
                conversations = row['total']
                calls         = row['calls']
                messages      = row['messages']
            conn.close()
    except Exception:
        pass

    leads, booked = 0, 0
    try:
        from main import get_db
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT COUNT(*) as leads,
                       COUNT(CASE WHEN meeting_scheduled = 1 THEN 1 END) as booked
                FROM leads
                WHERE user_id = ? AND created_at >= ?
            ''', (request.user_id, since))
            r = c.fetchone()
            if r:
                leads  = r['leads']
                booked = r['booked']
    except Exception:
        pass

    return jsonify({
        'period': period, 'conversations': conversations,
        'calls': calls, 'messages': messages,
        'leads': leads, 'appointments': booked
    })


# ============= PHONE PROVISIONING =============

@api_bp.route('/phone/provision', methods=['POST'])
@require_auth
def api_provision_phone():
    data = request.json or {}
    area_code = data.get('area_code', '800')

    from twilio.rest import Client
    from main import get_db
    import json

    if not TWILIO_SID or not TWILIO_TOKEN:
        return jsonify({'error': 'Twilio is not configured. Add TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN to your environment variables.'}), 503

    client = Client(TWILIO_SID, TWILIO_TOKEN)

    try:
        available = client.available_phone_numbers('US').local.list(area_code=area_code, limit=1)
        if not available:
            return jsonify({'error': f'No numbers available in area code {area_code}.'}), 404

        webhook_url = f"{request.host_url}agent/{request.user_id}"

        number = client.incoming_phone_numbers.create(
            phone_number=available[0].phone_number,
            sms_url=webhook_url, sms_method='POST',
            voice_url=webhook_url, voice_method='POST'
        )

        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT metadata FROM users WHERE id = ?', (request.user_id,))
            row = c.fetchone()
            meta = {}
            if row and row['metadata']:
                try:
                    meta = json.loads(row['metadata'])
                except Exception:
                    pass
            meta['phone_number'] = number.phone_number
            meta['phone_sid']    = number.sid
            c.execute('UPDATE users SET metadata = ? WHERE id = ?',
                      (json.dumps(meta), request.user_id))
            conn.commit()

        return jsonify({
            'success': True,
            'phone_number': number.phone_number,
            'webhook_url': webhook_url
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============= FUNDING =============

@api_bp.route('/funding/earnings', methods=['GET'])
@require_auth
def api_funding_earnings():
    try:
        from funding_tracker import FundingTracker
        tracker = FundingTracker()
        earnings = tracker.get_monthly_earnings(request.user_id)
        try:
            ytd = tracker.get_total_earnings_ytd(request.user_id)
            ytd_val = ytd.get('total_ytd', 0) if ytd else 0
        except Exception:
            ytd_val = 0
        return jsonify({'monthly': earnings, 'ytd': ytd_val})
    except Exception as e:
        return jsonify({'monthly': {'total_monthly': 0}, 'ytd': 0})


# ============= REGISTRATION =============

def register_api_routes(app):
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    print("API routes registered at /api/v1")
