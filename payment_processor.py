"""
Enhanced Payment Processor - All payments go to YOUR Stripe account
No PayPal - All payments processed through Stripe
Users can test AI agent before creating account or paying
"""

from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template_string
import stripe
import os
import sqlite3
from datetime import datetime
import json

payment_bp = Blueprint('payments', __name__)

# Stripe Configuration - YOUR Stripe account
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')  # YOUR Stripe key
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')  # YOUR publishable key

# Plan pricing
PLANS = {
    'basic': {'price': 29.99, 'name': 'Basic Plan', 'features': ['1,000 messages/month', '1 phone number', 'Email support']},
    'standard': {'price': 59.99, 'name': 'Standard Plan', 'features': ['5,000 messages/month', '3 phone numbers', 'Priority support', 'Auto-bidding']},
    'enterprise': {'price': 149.99, 'name': 'Enterprise Plan', 'features': ['Unlimited messages', 'Unlimited numbers', 'Dedicated support', 'Full auto-bidding']}
}

def get_db():
    """Get database connection"""
    conn = sqlite3.connect('leax_users.db')
    conn.row_factory = sqlite3.Row
    return conn

@payment_bp.route('/checkout/<plan>')
def checkout(plan):
    """Universal checkout page - all payments go to YOUR Stripe"""
    if plan not in PLANS:
        return redirect(url_for('index'))
    
    plan_info = PLANS[plan]
    
    # Render checkout template
    return render_template_string(CHECKOUT_TEMPLATE, 
                                 plan=plan,
                                 plan_name=plan_info['name'],
                                 amount=plan_info['price'],
                                 features=plan_info['features'],
                                 stripe_key=STRIPE_PUBLISHABLE_KEY)

@payment_bp.route('/create-stripe-payment-intent', methods=['POST'])
def create_stripe_payment_intent():
    """Create Stripe payment intent for all payment methods"""
    try:
        data = request.json
        plan = data.get('plan')
        payment_method = data.get('payment_method', 'card')  # card, apple_pay, google_pay, cashapp
        
        if plan not in PLANS:
            return jsonify({'error': 'Invalid plan'}), 400
        
        amount = int(PLANS[plan]['price'] * 100)  # Convert to cents
        
        # Determine payment method types
        if payment_method == 'apple_pay':
            payment_method_types = ['card', 'apple_pay']
        elif payment_method == 'google_pay':
            payment_method_types = ['card', 'google_pay']
        elif payment_method == 'cashapp':
            payment_method_types = ['cashapp']
        else:  # card or default
            payment_method_types = ['card']
        
        # Create payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency='usd',
            automatic_payment_methods={
                'enabled': True,
                'allow_redirects': 'never'
            },
            payment_method_types=payment_method_types,
            metadata={
                'plan': plan,
                'email': data.get('email'),
                'business_name': data.get('business_name'),
                'payment_method': payment_method
            }
        )
        
        # Store pending user data
        session['pending_user'] = {
            'email': data.get('email'),
            'business_name': data.get('business_name'),
            'password': data.get('password'),
            'plan': plan,
            'payment_intent': intent.id,
            'payment_method': payment_method
        }
        
        return jsonify({
            'client_secret': intent.client_secret,
            'payment_intent_id': intent.id
        })
        
    except stripe.error.StripeError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/create-stripe-checkout-session', methods=['POST'])
def create_stripe_checkout_session():
    """Create Stripe Checkout Session (simpler for users)"""
    try:
        data = request.json
        plan = data.get('plan')
        
        if plan not in PLANS:
            return jsonify({'error': 'Invalid plan'}), 400
        
        amount = int(PLANS[plan]['price'] * 100)
        
        # Create Stripe Checkout Session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card', 'apple_pay', 'google_pay', 'cashapp'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': PLANS[plan]['name'],
                        'description': 'LeaX AI - ' + ', '.join(PLANS[plan]['features'][:2])
                    },
                    'unit_amount': amount,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('payments.payment_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('payments.payment_cancelled', _external=True),
            customer_email=data.get('email'),
            metadata={
                'email': data.get('email'),
                'business_name': data.get('business_name'),
                'plan': plan
            }
        )
        
        # Store pending user data
        session['pending_user'] = {
            'email': data.get('email'),
            'business_name': data.get('business_name'),
            'password': data.get('password'),
            'plan': plan,
            'checkout_session': checkout_session.id
        }
        
        return jsonify({'redirect_url': checkout_session.url})
        
    except stripe.error.StripeError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/payment-success')
def payment_success():
    """Handle successful Stripe payment"""
    session_id = request.args.get('session_id')
    payment_intent_id = request.args.get('payment_intent_id')
    pending = session.get('pending_user')
    
    if not pending:
        return redirect(url_for('index'))
    
    try:
        # Verify payment
        if pending.get('checkout_session'):
            # Checkout session payment
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            if checkout_session.payment_status != 'paid':
                return render_template_string(PAYMENT_FAILED_TEMPLATE)
        elif pending.get('payment_intent'):
            # Payment intent payment
            intent = stripe.PaymentIntent.retrieve(payment_intent_id or pending['payment_intent'])
            if intent.status != 'succeeded':
                return render_template_string(PAYMENT_FAILED_TEMPLATE)
        
        # Create user account
        success = create_user_account(pending)
        
        if success:
            session.pop('pending_user', None)
            return redirect(url_for('customize_agent'))
        else:
            return render_template_string(PAYMENT_FAILED_TEMPLATE)
            
    except Exception as e:
        print(f"Payment verification error: {e}")
        return render_template_string(PAYMENT_FAILED_TEMPLATE)

@payment_bp.route('/payment-cancelled')
def payment_cancelled():
    """Handle cancelled payment"""
    session.pop('pending_user', None)
    return render_template_string(PAYMENT_CANCELLED_TEMPLATE)

def create_user_account(user_data):
    """Create user account after successful payment"""
    try:
        from main import hash_password
        from memory_manager import MemoryManager
        
        with get_db() as conn:
            c = conn.cursor()
            
            # Check if email already exists
            c.execute('SELECT id FROM users WHERE email = ?', (user_data['email'],))
            if c.fetchone():
                print(f"User {user_data['email']} already exists")
                return False
            
            # Create user
            c.execute('''
                INSERT INTO users (email, password_hash, business_name, status, plan_type)
                VALUES (?, ?, ?, 'active', ?)
            ''', (user_data['email'], hash_password(user_data['password']), 
                  user_data['business_name'], user_data['plan']))
            
            user_id = c.lastrowid
            
            # Create business info
            c.execute('''
                INSERT INTO business_info (user_id, agent_personality)
                VALUES (?, 'Sarah')
            ''', (user_id,))
            
            conn.commit()
        
        # Create memory file
        memory_mgr = MemoryManager()
        memory_mgr.create_customer_memory(
            user_id=user_id,
            business_name=user_data['business_name'],
            email=user_data['email']
        )
        
        # Log in user
        session['user_id'] = user_id
        session['email'] = user_data['email']
        session['business_name'] = user_data['business_name']
        session['user_plan'] = user_data['plan']
        
        # Send notification email
        try:
            from main import email_notifier
            email_notifier.notify_new_signup({
                'user_id': user_id,
                'business_name': user_data['business_name'],
                'email': user_data['email'],
                'plan_type': user_data['plan']
            })
        except:
            pass
        
        print(f"✅ User account created: {user_data['email']} ({user_data['plan']} plan)")
        return True
        
    except Exception as e:
        print(f"Error creating account: {e}")
        return False

# ==================== FREE TRIAL & TESTING ====================

@payment_bp.route('/start-free-trial', methods=['POST'])
def start_free_trial():
    """Start free trial WITHOUT payment"""
    try:
        data = request.json
        email = data.get('email')
        business_name = data.get('business_name')
        password = data.get('password')
        
        if not all([email, business_name, password]):
            return jsonify({'error': 'All fields required'}), 400
        
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        
        # Check if email exists
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT id FROM users WHERE email = ?', (email,))
            if c.fetchone():
                return jsonify({'error': 'Email already exists'}), 400
            
            # Create trial user
            from main import hash_password
            c.execute('''
                INSERT INTO users (email, password_hash, business_name, status, plan_type, trial_session_used)
                VALUES (?, ?, ?, 'active', 'trial', 0)
            ''', (email, hash_password(password), business_name))
            
            user_id = c.lastrowid
            
            # Create business info
            c.execute('''
                INSERT INTO business_info (user_id, agent_personality)
                VALUES (?, 'Sarah')
            ''', (user_id,))
            
            # Start trial
            c.execute('''
                INSERT INTO plan_trials (user_id, plan_type, trial_active, messages_sent)
                VALUES (?, 'trial', 1, 0)
            ''', (user_id,))
            
            conn.commit()
        
        # Create memory file
        from memory_manager import MemoryManager
        memory_mgr = MemoryManager()
        memory_mgr.create_customer_memory(
            user_id=user_id,
            business_name=business_name,
            email=email
        )
        
        # Log in user
        session['user_id'] = user_id
        session['email'] = email
        session['business_name'] = business_name
        session['user_plan'] = 'trial'
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'redirect_url': url_for('customize_agent')
        })
        
    except Exception as e:
        print(f"Trial creation error: {e}")
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/try-for-free')
def try_for_free():
    """Landing page for free trial"""
    return render_template_string(FREE_TRIAL_TEMPLATE)

def register_payment_routes(app):
    """Register payment blueprint with main app"""
    app.register_blueprint(payment_bp, url_prefix='/payments')
    print("✅ Payment routes registered (All payments go to YOUR Stripe)")

# ==================== TEMPLATES ====================

FREE_TRIAL_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Try LeaX AI Free - No Payment Required</title>
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
        .trial-container {
            background: white;
            padding: 50px 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.2);
            max-width: 600px;
            width: 100%;
        }
        .logo {
            font-size: 36px;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            margin-bottom: 20px;
        }
        .trial-badge {
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            padding: 15px;
            border-radius: 15px;
            text-align: center;
            margin: 30px 0;
            font-size: 20px;
            font-weight: 700;
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
        .btn {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 15px;
            border: none;
            cursor: pointer;
            width: 100%;
            border-radius: 10px;
            font-size: 18px;
            font-weight: 600;
            margin-top: 10px;
            transition: transform 0.3s;
        }
        .btn:hover:not(:disabled) {
            transform: scale(1.02);
        }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .btn-free {
            background: linear-gradient(135deg, #10b981, #059669);
            font-size: 20px;
            padding: 20px;
        }
        .features {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
        .features li {
            padding: 8px 0;
            list-style: none;
        }
        .features li:before {
            content: "✓ ";
            color: #10b981;
            font-weight: bold;
            margin-right: 10px;
        }
        .error {
            color: #dc3545;
            margin: 10px 0;
            display: none;
        }
    </style>
</head>
<body>
    <div class="trial-container">
        <div class="logo">🤖 LeaX AI</div>
        <h2 style="text-align: center; margin-bottom: 10px; color: #333;">Try Our AI Agent - No Payment Required!</h2>
        <p style="text-align: center; color: #666; margin-bottom: 20px;">
            Test the full AI agent, customize it to your business, and see how it works before paying anything.
        </p>
        
        <div class="trial-badge">
            🎁 FREE TRIAL - No Credit Card Required
        </div>
        
        <form id="trialForm">
            <input type="email" id="email" placeholder="Your Email" required>
            <input type="text" id="business_name" placeholder="Your Business Name" required>
            <input type="password" id="password" placeholder="Password (min 8 characters)" required minlength="8">
            
            <div class="features">
                <p><strong>What you get in the free trial:</strong></p>
                <li>Full AI agent customization</li>
                <li>Test conversations with the AI</li>
                <li>Configure phone number settings</li>
                <li>Set up auto-bidding rules</li>
                <li>Access to dashboard</li>
                <li>50 test messages to try everything</li>
            </div>
            
            <button type="button" class="btn btn-free" onclick="startFreeTrial()">
                🚀 Start Free Trial Now
            </button>
            
            <p style="text-align: center; margin-top: 15px; color: #666;">
                <a href="/" style="color: #667eea;">View pricing plans</a>
            </p>
        </form>
        
        <div class="error" id="error"></div>
    </div>
    
    <script>
        async function startFreeTrial() {
            const email = document.getElementById('email').value;
            const business_name = document.getElementById('business_name').value;
            const password = document.getElementById('password').value;
            
            if (!email || !business_name || !password) {
                showError('Please fill in all fields');
                return;
            }
            
            if (password.length < 8) {
                showError('Password must be at least 8 characters');
                return;
            }
            
            const button = document.querySelector('.btn-free');
            button.disabled = true;
            button.textContent = 'Creating your trial account...';
            
            try {
                const response = await fetch('/payments/start-free-trial', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ email, business_name, password })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    throw new Error(data.error);
                }
                
                // Success - redirect to customization
                window.location.href = '/customize';
                
            } catch (error) {
                showError(error.message);
                button.disabled = false;
                button.textContent = '🚀 Start Free Trial Now';
            }
        }
        
        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = '❌ ' + message;
            errorDiv.style.display = 'block';
            setTimeout(() => errorDiv.style.display = 'none', 5000);
        }
    </script>
</body>
</html>
'''

CHECKOUT_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Upgrade to {{ plan_name }} - LeaX AI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://js.stripe.com/v3/"></script>
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
        .checkout-container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.2);
            max-width: 550px;
            width: 100%;
        }
        .logo {
            font-size: 36px;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            margin-bottom: 10px;
        }
        .plan-summary {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 30px;
            border-radius: 15px;
            text-align: center;
            margin: 30px 0;
        }
        .plan-name {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 10px;
        }
        .plan-price {
            font-size: 48px;
            font-weight: 800;
        }
        .plan-price span {
            font-size: 20px;
        }
        .features {
            list-style: none;
            margin-top: 15px;
            text-align: left;
        }
        .features li {
            padding: 5px 0;
            opacity: 0.9;
        }
        .features li:before {
            content: "✓ ";
            font-weight: bold;
            margin-right: 5px;
        }
        .payment-methods {
            margin: 30px 0;
        }
        .payment-method {
            border: 2px solid #e2e8f0;
            padding: 20px;
            border-radius: 10px;
            margin: 15px 0;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .payment-method:hover {
            border-color: #667eea;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102,126,234,0.2);
        }
        .payment-method.selected {
            border-color: #667eea;
            background: #f8f9ff;
        }
        .payment-icon {
            font-size: 32px;
        }
        .btn {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 15px;
            border: none;
            cursor: pointer;
            width: 100%;
            border-radius: 10px;
            font-size: 18px;
            font-weight: 600;
            margin-top: 10px;
            transition: transform 0.3s;
        }
        .btn:hover:not(:disabled) {
            transform: scale(1.02);
        }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        #card-element {
            padding: 15px;
            border: 2px solid #e2e8f0;
            border-radius: 10px;
            margin: 10px 0;
        }
        .error {
            color: #dc3545;
            margin: 10px 0;
            display: none;
        }
        .hidden {
            display: none;
        }
        .info {
            text-align: center;
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
            font-size: 14px;
            color: #666;
        }
        .secure-badge {
            text-align: center;
            margin: 20px 0;
            color: #10b981;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="checkout-container">
        <div class="logo">🤖 LeaX AI</div>
        <h2 style="text-align: center; margin-bottom: 20px; color: #333;">Upgrade to {{ plan_name }}</h2>

        <div class="plan-summary">
            <div class="plan-name">{{ plan_name }}</div>
            <div class="plan-price">${{ amount }}<span>/month</span></div>
            <ul class="features">
                {% for feature in features %}
                <li>{{ feature }}</li>
                {% endfor %}
            </ul>
        </div>

        <div class="secure-badge">
            🔒 All payments securely processed through Stripe
        </div>

        <div class="payment-methods">
            <h3 style="margin-bottom: 15px;">Choose Payment Method:</h3>
            
            <div class="payment-method" onclick="selectPayment('card')">
                <div class="payment-icon">💳</div>
                <div>
                    <strong>Credit/Debit Card</strong>
                    <p style="font-size: 14px; color: #666;">Visa, Mastercard, Amex, Discover</p>
                </div>
            </div>

            <div class="payment-method" onclick="selectPayment('apple_pay')">
                <div class="payment-icon">🍎</div>
                <div>
                    <strong>Apple Pay</strong>
                    <p style="font-size: 14px; color: #666;">Pay with Apple Pay</p>
                </div>
            </div>

            <div class="payment-method" onclick="selectPayment('google_pay')">
                <div class="payment-icon">📱</div>
                <div>
                    <strong>Google Pay</strong>
                    <p style="font-size: 14px; color: #666;">Pay with Google Pay</p>
                </div>
            </div>

            <div class="payment-method" onclick="selectPayment('cashapp')">
                <div class="payment-icon">💵</div>
                <div>
                    <strong>Cash App Pay</strong>
                    <p style="font-size: 14px; color: #666;">Pay with Cash App</p>
                </div>
            </div>

            <div class="payment-method" onclick="selectPayment('checkout_session')">
                <div class="payment-icon">🔗</div>
                <div>
                    <strong>Simple Checkout</strong>
                    <p style="font-size: 14px; color: #666;">Redirect to secure payment page</p>
                </div>
            </div>
        </div>

        <!-- Card Payment Form -->
        <div id="cardPaymentForm" class="hidden">
            <div id="card-element"></div>
            <button class="btn" onclick="processCardPayment(event)">Pay ${{ amount }}</button>
        </div>

        <!-- Simple Checkout -->
        <div id="checkoutSessionForm" class="hidden">
            <div class="info">You'll be redirected to a secure payment page to complete your purchase</div>
            <button class="btn" onclick="processCheckoutSession(event)">Continue to Secure Checkout</button>
        </div>

        <div class="error" id="error"></div>

        <p style="text-align: center; color: #999; font-size: 14px; margin-top: 20px;">
            <a href="/dashboard" style="color: #667eea;">← Back to Dashboard</a>
        </p>
    </div>

    <script>
        const stripe = Stripe('{{ stripe_key }}');
        const elements = stripe.elements();
        const cardElement = elements.create('card');
        let currentPayment = null;

        function selectPayment(method) {
            currentPayment = method;
            
            // Hide all forms
            document.querySelectorAll('.payment-method').forEach(el => el.classList.remove('selected'));
            document.querySelectorAll('#cardPaymentForm, #checkoutSessionForm').forEach(el => el.classList.add('hidden'));
            
            // Show selected
            event.target.closest('.payment-method').classList.add('selected');
            
            if (method === 'card' || method === 'apple_pay' || method === 'google_pay' || method === 'cashapp') {
                document.getElementById('cardPaymentForm').classList.remove('hidden');
                cardElement.mount('#card-element');
            } else if (method === 'checkout_session') {
                document.getElementById('checkoutSessionForm').classList.remove('hidden');
            }
        }

        async function processCardPayment(e) {
            e.preventDefault();
            
            const button = e.target;
            button.disabled = true;
            button.textContent = 'Processing...';

            try {
                const response = await fetch('/payments/create-stripe-payment-intent', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        plan: '{{ plan }}',
                        payment_method: currentPayment
                    })
                });

                const data = await response.json();

                if (data.error) {
                    throw new Error(data.error);
                }

                // Confirm payment
                let result;
                
                if (currentPayment === 'apple_pay') {
                    result = await stripe.confirmApplePayPayment(data.client_secret);
                } else if (currentPayment === 'google_pay') {
                    result = await stripe.confirmGooglePayPayment(data.client_secret);
                } else if (currentPayment === 'cashapp') {
                    result = await stripe.confirmCashappPayment(data.client_secret);
                } else {
                    result = await stripe.confirmCardPayment(data.client_secret, {
                        payment_method: {
                            card: cardElement
                        }
                    });
                }

                if (result.error) {
                    throw new Error(result.error.message);
                }

                window.location.href = '/payments/payment-success?payment_intent_id=' + data.payment_intent_id;

            } catch (error) {
                showError(error.message);
                button.disabled = false;
                button.textContent = 'Pay ${{ amount }}';
            }
        }

        async function processCheckoutSession(e) {
            e.preventDefault();
            
            const button = e.target;
            button.disabled = true;
            button.textContent = 'Redirecting...';

            try {
                const response = await fetch('/payments/create-stripe-checkout-session', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        plan: '{{ plan }}'
                    })
                });

                const data = await response.json();

                if (data.error) {
                    throw new Error(data.error);
                }

                window.location.href = data.redirect_url;

            } catch (error) {
                showError(error.message);
                button.disabled = false;
                button.textContent = 'Continue to Secure Checkout';
            }
        }

        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = '❌ ' + message;
            errorDiv.style.display = 'block';
            setTimeout(() => errorDiv.style.display = 'none', 5000);
        }
    </script>
</body>
</html>
'''

PAYMENT_CANCELLED_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Payment Cancelled</title>
    <style>
        body { font-family: Arial; text-align: center; padding: 100px; }
        .message { background: #fff3cd; padding: 30px; border-radius: 10px; display: inline-block; }
        .btn { background: #667eea; color: white; padding: 15px 30px; text-decoration: none; 
               border-radius: 25px; display: inline-block; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="message">
        <h1>⚠️ Payment Cancelled</h1>
        <p>Your payment was cancelled. No charges were made.</p>
        <a href="/dashboard" class="btn">Return to Dashboard</a>
    </div>
</body>
</html>
'''

PAYMENT_FAILED_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Payment Failed</title>
    <style>
        body { font-family: Arial; text-align: center; padding: 100px; }
        .message { background: #f8d7da; padding: 30px; border-radius: 10px; display: inline-block; }
        .btn { background: #667eea; color: white; padding: 15px 30px; text-decoration: none; 
               border-radius: 25px; display: inline-block; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="message">
        <h1>❌ Payment Failed</h1>
        <p>There was an error processing your payment. Please try again.</p>
        <a href="/dashboard" class="btn">Return to Dashboard</a>
    </div>
</body>
</html>
'''
