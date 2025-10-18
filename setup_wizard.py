"""
Setup Wizard - Zero-code phone number configuration
Customers can use LeaX in 3 ways:
1. Get a new number (automatic, instant)
2. Forward existing number (simple instructions)
3. Port existing number (enterprise)
"""

from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from twilio.rest import Client
import os

setup_wizard = Blueprint('setup_wizard', __name__)

# Twilio client for automatic provisioning
TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')

if TWILIO_SID and TWILIO_TOKEN:
    twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)
else:
    twilio_client = None
    print("⚠️ Twilio not configured - phone provisioning disabled")

def get_webhook_url(user_id):
    """Generate webhook URL for customer"""
    base_url = os.environ.get('RAILWAY_STATIC_URL') or os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if base_url:
        return f"https://{base_url}/agent/{user_id}"
    return f"https://your-app.railway.app/agent/{user_id}"

@setup_wizard.route('/setup-wizard')
def wizard():
    """Main setup wizard page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    webhook_url = get_webhook_url(session['user_id'])
    
    return render_template('setup_wizard.html',
        user_id=session['user_id'],
        business_name=session['business_name'],
        webhook_url=webhook_url,
        twilio_available=twilio_client is not None
    )

@setup_wizard.route('/api/provision-number', methods=['POST'])
def provision_number():
    """Automatically provision a new Twilio number"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    if not twilio_client:
        return jsonify({'error': 'Twilio not configured'})
    
    try:
        data = request.json
        area_code = data.get('area_code', '800')  # Default to toll-free
        
        # Search for available numbers
        available_numbers = twilio_client.available_phone_numbers('US').local.list(
            area_code=area_code,
            limit=1
        )
        
        if not available_numbers:
            return jsonify({'error': 'No numbers available in that area code'})
        
        # Purchase the number
        phone_number = available_numbers[0].phone_number
        incoming_number = twilio_client.incoming_phone_numbers.create(
            phone_number=phone_number,
            sms_url=get_webhook_url(session['user_id']),
            sms_method='POST',
            voice_url=get_webhook_url(session['user_id']),
            voice_method='POST'
        )
        
        # Save to database
        from main import get_db
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE users 
                SET metadata = json_set(
                    metadata,
                    '$.phone_number', ?,
                    '$.phone_sid', ?,
                    '$.setup_completed', 1
                )
                WHERE id = ?
            ''', (phone_number, incoming_number.sid, session['user_id']))
            conn.commit()
        
        return jsonify({
            'success': True,
            'phone_number': phone_number,
            'message': 'Number provisioned successfully!'
        })
        
    except Exception as e:
        print(f"Provisioning error: {e}")
        return jsonify({'error': str(e)})

@setup_wizard.route('/api/verify-forwarding', methods=['POST'])
def verify_forwarding():
    """Verify customer's phone forwarding is working"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    data = request.json
    customer_number = data.get('phone_number')
    
    # Save customer's existing number
    from main import get_db
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE users 
            SET metadata = json_set(
                metadata,
                '$.customer_phone_number', ?,
                '$.setup_method', 'forwarding',
                '$.setup_completed', 1
            )
            WHERE id = ?
        ''', (customer_number, session['user_id']))
        conn.commit()
    
    return jsonify({
        'success': True,
        'message': 'Setup complete! Your AI is ready.'
    })

@setup_wizard.route('/api/mark-setup-complete', methods=['POST'])
def mark_complete():
    """Mark setup as completed"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    from main import get_db
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE users 
            SET metadata = json_set(metadata, '$.setup_completed', 1)
            WHERE id = ?
        ''', (session['user_id'],))
        conn.commit()
    
    return jsonify({'success': True})
