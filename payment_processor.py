"""
Enhanced Payment Processor - Multiple Payment Options
Supports: Credit Cards, Debit Cards, CashApp, PayPal (no account needed)
Uses Stripe for card processing - customers never need PayPal account
"""

from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template_string
import stripe
import os
import sqlite3
from datetime import datetime
import json

payment_bp = Blueprint('payments', __name__)

# Stripe Configuration (handles cards, Apple Pay, Google Pay, CashApp)
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')

# PayPal for those who prefer it
import paypalrestsdk
paypalrestsdk.configure({
    "mode": os.environ.get('PAYPAL_MODE', 'sandbox'),
    "client_id": os.environ.get('PAYPAL_CLIENT_ID'),
    "client_secret": os.environ.get('PAYPAL_CLIENT_SECRET')
})

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
    """Universal checkout page - choose payment method"""
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

@payment_bp.route('/create-stripe-payment', methods=['POST'])
def create_stripe_payment():
    """Create Stripe payment intent for cards"""
    try:
        data = request.json
        plan = data.get('plan')
        
        if plan not in PLANS:
            return jsonify({'error': 'Invalid plan'}), 400
        
        amount = int(PLANS[plan]['price'] * 100)  # Convert to cents
        
        # Create payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency='usd',
            automatic_payment_methods={'enabled': True},
            metadata={
                'plan': plan,
                'email': data.get('email'),
                'business_name': data.get('business_name')
            }
        )
        
        # Store pending user data
        session['pending_user'] = {
            'email': data.get('email'),
            'business_name': data.get('business_name'),
            'password': data.get('password'),
            'plan': plan,
            'payment_intent': intent.id
        }
        
        return jsonify({
            'client_secret': intent.client_secret,
            'session_id': intent.id
        })
        
    except stripe.error.StripeError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/create-cashapp-payment', methods=['POST'])
def create_cashapp_payment():
    """Create Cash App payment session via Stripe"""
    try:
        data = request.json
        plan = data.get('plan')
        
        if plan not in PLANS:
            return jsonify({'error': 'Invalid plan'}), 400
        
        amount = int(PLANS[plan]['price'] * 100)
        
        # Create Stripe Checkout Session with Cash App
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['cashapp'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': PLANS[plan]['name'],
                        'description': 'LeaX AI - ' + ', '.join(PLANS[plan]['features'][:2])
                    },
                    'unit_amount': amount,
                    'recurring': {'interval': 'month'}
                },
                'quantity': 1,
            }],
            mode='subscription',
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

@payment_bp.route('/create-paypal-payment', methods=['POST'])
def create_paypal_payment():
    """Create PayPal payment (no account required - guest checkout)"""
    try:
        data = request.json
        plan = data.get('plan')
        
        if plan not in PLANS:
            return jsonify({'error': 'Invalid plan'}), 400
        
        amount = str(PLANS[plan]['price'])
        
        # Create PayPal payment
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "redirect_urls": {
                "return_url": url_for('payments.paypal_success', _external=True),
                "cancel_url": url_for('payments.payment_cancelled', _external=True)
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": PLANS[plan]['name'],
                        "sku": plan,
                        "price": amount,
                        "currency": "USD",
                        "quantity": 1
                    }]
                },
                "amount": {
                    "total": amount,
                    "currency": "USD"
                },
                "description": f"LeaX AI {PLANS[plan]['name']} - Monthly Subscription"
            }]
        })
        
        if payment.create():
            # Store pending user data
            session['pending_user'] = {
                'email': data.get('email'),
                'business_name': data.get('business_name'),
                'password': data.get('password'),
                'plan': plan,
                'payment_id': payment.id
            }
            
            # Get approval URL
            for link in payment.links:
                if link.rel == "approval_url":
                    return jsonify({'approval_url': link.href})
            
            return jsonify({'error': 'No approval URL found'}), 500
        else:
            print(f"PayPal Error: {payment.error}")
            return jsonify({'error': 'Payment creation failed'}), 500
            
    except Exception as e:
        print(f"Payment Error: {e}")
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/payment-success')
def payment_success():
    """Handle successful Stripe payment"""
    session_id = request.args.get('session_id')
    pending = session.get('pending_user')
    
    if not pending:
        return redirect(url_for('index'))
    
    try:
        # Verify payment with Stripe
        if pending.get('checkout_session'):
            # Cash App payment
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            if checkout_session.payment_status != 'paid':
                return "Payment not completed", 400
        elif pending.get('payment_intent'):
            # Card payment
            intent = stripe.PaymentIntent.retrieve(session_id)
            if intent.status != 'succeeded':
                return "Payment not completed", 400
        
        # Create user account
        success = create_user_account(pending)
        
        if success:
            session.pop('pending_user', None)
            return redirect(url_for('customize_agent'))
        else:
            return "Account creation failed", 500
            
    except Exception as e:
        print(f"Payment verification error: {e}")
        return f"Error: {e}", 500

@payment_bp.route('/paypal-success')
def paypal_success():
    """Handle successful PayPal payment"""
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')
    pending = session.get('pending_user')
    
    if not payment_id or not payer_id or not pending:
        return redirect(url_for('index'))
    
    try:
        # Execute PayPal payment
        payment = paypalrestsdk.Payment.find(payment_id)
        
        if payment.execute({"payer_id": payer_id}):
            # Create user account
            success = create_user_account(pending)
            
            if success:
                session.pop('pending_user', None)
                return redirect(url_for('customize_agent'))
            else:
                return "Account creation failed", 500
        else:
            return "Payment execution failed", 400
            
    except Exception as e:
        print(f"PayPal success error: {e}")
        return f"Error: {e}", 500

@payment_bp.route('/payment-cancelled')
def payment_cancelled():
    """Handle cancelled payment"""
    session.pop('pending_user', None)
    return render_template_string("""
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
            <a href="/" class="btn">Try Again</a>
        </div>
    </body>
    </html>
    """)

def create_user_account(user_data):
    """Create user account after successful payment"""
    try:
        from main import hash_password
        from memory_manager import MemoryManager
        from trial_manager import TrialManager
        
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

def register_payment_routes(app):
    """Register payment blueprint with main app"""
    app.register_blueprint(payment_bp, url_prefix='/payments')
    print("✅ Payment routes registered")

# Checkout page template
CHECKOUT_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Checkout - LeaX AI</title>
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
    </style>
</head>
<body>
    <div class="checkout-container">
        <div class="logo">🤖 LeaX AI</div>
        <h2 style="text-align: center; margin-bottom: 20px; color: #333;">Complete Your Order</h2>

        <div class="plan-summary">
            <div class="plan-name">{{ plan_name }}</div>
            <div class="plan-price">${{ amount }}<span>/month</span></div>
            <ul class="features">
                {% for feature in features %}
                <li>{{ feature }}</li>
                {% endfor %}
            </ul>
        </div>

        <form id="accountForm">
            <input type="email" id="email" placeholder="Business Email" required>
            <input type="text" id="business_name" placeholder="Business Name" required>
            <input type="password" id="password" placeholder="Password (min 8 characters)" required minlength="8">
        </form>

        <div class="payment-methods">
            <h3 style="margin-bottom: 15px;">Choose Payment Method:</h3>
            
            <div class="payment-method" onclick="selectPayment('card')">
                <div class="payment-icon">💳</div>
                <div>
                    <strong>Credit/Debit Card</strong>
                    <p style="font-size: 14px; color: #666;">Visa, Mastercard, Amex, Discover</p>
                </div>
            </div>

            <div class="payment-method" onclick="selectPayment('cashapp')">
                <div class="payment-icon">💵</div>
                <div>
                    <strong>Cash App Pay</strong>
                    <p style="font-size: 14px; color: #666;">Pay with Cash App</p>
                </div>
            </div>

            <div class="payment-method" onclick="selectPayment('paypal')">
                <div class="payment-icon">🅿️</div>
                <div>
                    <strong>PayPal</strong>
                    <p style="font-size: 14px; color: #666;">No account needed - guest checkout</p>
                </div>
            </div>
        </div>

        <!-- Card Payment Form (Stripe) -->
        <div id="cardPaymentForm" class="hidden">
            <div id="card-element"></div>
            <button class="btn" onclick="processCardPayment(event)">Pay ${{ amount }}</button>
        </div>

        <!-- CashApp Payment -->
        <div id="cashappPaymentForm" class="hidden">
            <div class="info">You'll be redirected to Cash App to complete payment</div>
            <button class="btn" onclick="processCashAppPayment(event)">Continue to Cash App</button>
        </div>

        <!-- PayPal Payment -->
        <div id="paypalPaymentForm" class="hidden">
            <div class="info">You'll be redirected to PayPal (no account required - guest checkout available)</div>
            <button class="btn" onclick="processPayPalPayment(event)">Continue to PayPal</button>
        </div>

        <div class="error" id="error"></div>

        <p style="text-align: center; color: #999; font-size: 14px; margin-top: 20px;">
            Already have an account? <a href="/login" style="color: #667eea;">Login</a>
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
            document.querySelectorAll('#cardPaymentForm, #cashappPaymentForm, #paypalPaymentForm').forEach(el => el.classList.add('hidden'));
            
            // Show selected
            event.target.closest('.payment-method').classList.add('selected');
            
            if (method === 'card') {
                document.getElementById('cardPaymentForm').classList.remove('hidden');
                cardElement.mount('#card-element');
            } else if (method === 'cashapp') {
                document.getElementById('cashappPaymentForm').classList.remove('hidden');
            } else if (method === 'paypal') {
                document.getElementById('paypalPaymentForm').classList.remove('hidden');
            }
        }

        async function processCardPayment(e) {
            e.preventDefault();
            
            const accountData = getAccountData();
            if (!accountData) return;

            const button = e.target;
            button.disabled = true;
            button.textContent = 'Processing...';

            try {
                const response = await fetch('/payments/create-stripe-payment', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        plan: '{{ plan }}',
                        ...accountData
                    })
                });

                const data = await response.json();

                if (data.error) {
                    throw new Error(data.error);
                }

                const result = await stripe.confirmCardPayment(data.client_secret, {
                    payment_method: {
                        card: cardElement,
                        billing_details: {
                            email: accountData.email,
                            name: accountData.business_name
                        }
                    }
                });

                if (result.error) {
                    throw new Error(result.error.message);
                }

                window.location.href = '/payments/payment-success?session_id=' + data.session_id;

            } catch (error) {
                showError(error.message);
                button.disabled = false;
                button.textContent = 'Pay ${{ amount }}';
            }
        }

        async function processCashAppPayment(e) {
            e.preventDefault();
            
            const accountData = getAccountData();
            if (!accountData) return;

            const button = e.target;
            button.disabled = true;
            button.textContent = 'Redirecting...';

            try {
                const response = await fetch('/payments/create-cashapp-payment', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        plan: '{{ plan }}',
                        ...accountData
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
                button.textContent = 'Continue to Cash App';
            }
        }

        async function processPayPalPayment(e) {
            e.preventDefault();
            
            const accountData = getAccountData();
            if (!accountData) return;

            const button = e.target;
            button.disabled = true;
            button.textContent = 'Redirecting...';

            try {
                const response = await fetch('/payments/create-paypal-payment', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        plan: '{{ plan }}',
                        ...accountData
                    })
                });

                const data = await response.json();

                if (data.error) {
                    throw new Error(data.error);
                }

                window.location.href = data.approval_url;

            } catch (error) {
                showError(error.message);
                button.disabled = false;
                button.textContent = 'Continue to PayPal';
            }
        }

        function getAccountData() {
            const email = document.getElementById('email').value;
            const business_name = document.getElementById('business_name').value;
            const password = document.getElementById('password').value;

            if (!email || !business_name || !password) {
                showError('Please fill in all fields');
                return null;
            }

            if (password.length < 8) {
                showError('Password must be at least 8 characters');
                return null;
            }

            return { email, business_name, password };
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
