"""
Trial Manager - Give users limited free trials to test full UX
Users get X free messages to test everything before subscribing
Admins get unlimited everything for free
"""

import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

class TrialManager:
    """Manage free trials with message limits"""
    
    def __init__(self, db_path='leax_users.db'):
        self.db_path = db_path
        self._init_trial_tracking()
    
    @contextmanager
    def get_db(self):
        """Database connection context manager"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_trial_tracking(self):
        """Initialize trial tracking tables"""
        with self.get_db() as conn:
            c = conn.cursor()
            
            # Add trial columns to users table if not exists
            columns_to_add = [
                ('trial_messages_remaining', 'INTEGER DEFAULT 50'),
                ('trial_started_at', 'TIMESTAMP'),
                ('trial_expires_at', 'TIMESTAMP'),
                ('is_admin', 'BOOLEAN DEFAULT 0')
            ]
            
            for column_name, column_type in columns_to_add:
                try:
                    c.execute(f'ALTER TABLE users ADD COLUMN {column_name} {column_type}')
                except sqlite3.OperationalError:
                    pass  # Column already exists
            
            conn.commit()
    
    def start_trial(self, user_id, trial_messages=50, trial_days=7):
        """
        Start free trial for user
        
        Args:
            user_id: User ID
            trial_messages: Number of free messages (default 50)
            trial_days: Trial duration in days (default 7)
        
        Returns:
            bool: True if trial started successfully
        """
        # Check if admin
        try:
            from admin_override import is_admin
            if is_admin(user_id):
                print(f"âœ… Admin user {user_id} - Unlimited access granted")
                with self.get_db() as conn:
                    c = conn.cursor()
                    c.execute('UPDATE users SET is_admin = 1 WHERE id = ?', (user_id,))
                    conn.commit()
                return True
        except ImportError:
            pass  # admin_override not set up yet
        
        with self.get_db() as conn:
            c = conn.cursor()
            
            trial_expires = datetime.now() + timedelta(days=trial_days)
            
            c.execute('''
                UPDATE users 
                SET trial_messages_remaining = ?,
                    trial_started_at = CURRENT_TIMESTAMP,
                    trial_expires_at = ?,
                    plan_type = 'trial'
                WHERE id = ?
            ''', (trial_messages, trial_expires, user_id))
            
            conn.commit()
        
        print(f"âœ… Trial started for user {user_id}: {trial_messages} messages, {trial_days} days")
        return True
    
    def use_trial_message(self, user_id):
        """
        Use one trial message
        
        Args:
            user_id: User ID
        
        Returns:
            dict: Trial status with remaining messages
        """
        # ADMIN BYPASS - Unlimited for you
        try:
            from admin_override import is_admin
            if is_admin(user_id):
                return {
                    'allowed': True,
                    'trial': False,
                    'admin': True,
                    'messages_remaining': 'unlimited',
                    'message': 'ðŸ'' Admin - Unlimited Access'
                }
        except ImportError:
            pass
        
        with self.get_db() as conn:
            c = conn.cursor()
            
            # Get current trial status
            c.execute('''
                SELECT trial_messages_remaining, trial_expires_at, plan_type, is_admin
                FROM users 
                WHERE id = ?
            ''', (user_id,))
            
            user = c.fetchone()
            
            if not user:
                return {'allowed': False, 'error': 'User not found'}
            
            # Double-check admin status
            if user['is_admin']:
                return {
                    'allowed': True,
                    'trial': False,
                    'admin': True,
                    'messages_remaining': 'unlimited',
                    'message': 'ðŸ'' Admin - Unlimited Access'
                }
            
            # If paid plan, always allow
            if user['plan_type'] in ['basic', 'standard', 'enterprise']:
                return {
                    'allowed': True,
                    'trial': False,
                    'messages_remaining': 'unlimited',
                    'plan': user['plan_type']
                }
            
            # Check trial expiration
            if user['trial_expires_at']:
                try:
                    expiry = datetime.fromisoformat(user['trial_expires_at'])
                    if datetime.now() > expiry:
                        return {
                            'allowed': False,
                            'trial': True,
                            'expired': True,
                            'messages_remaining': 0,
                            'message': 'Trial expired. Please upgrade to continue.',
                            'upgrade_url': '/checkout/basic'
                        }
                except (ValueError, TypeError):
                    pass
            
            # Check remaining messages
            remaining = user['trial_messages_remaining'] or 0
            
            if remaining <= 0:
                return {
                    'allowed': False,
                    'trial': True,
                    'messages_remaining': 0,
                    'message': 'Trial messages used up. Please upgrade to continue.',
                    'upgrade_url': '/checkout/basic'
                }
            
            # Decrement trial messages
            c.execute('''
                UPDATE users 
                SET trial_messages_remaining = trial_messages_remaining - 1
                WHERE id = ?
            ''', (user_id,))
            
            conn.commit()
            
            new_remaining = remaining - 1
            
            return {
                'allowed': True,
                'trial': True,
                'messages_remaining': new_remaining,
                'warning': new_remaining <= 10,  # Warn when low
                'message': f'{new_remaining} trial messages remaining'
            }
    
    def get_trial_status(self, user_id):
        """
        Get current trial status for user
        
        Args:
            user_id: User ID
        
        Returns:
            dict: Trial information including remaining messages and days
        """
        # Admin check
        try:
            from admin_override import is_admin
            if is_admin(user_id):
                return {
                    'is_trial': False,
                    'is_admin': True,
                    'unlimited': True,
                    'messages_remaining': 'unlimited',
                    'plan': 'admin'
                }
        except ImportError:
            pass
        
        with self.get_db() as conn:
            c = conn.cursor()
            
            c.execute('''
                SELECT trial_messages_remaining, trial_started_at, 
                       trial_expires_at, plan_type, is_admin
                FROM users 
                WHERE id = ?
            ''', (user_id,))
            
            user = c.fetchone()
            
            if not user:
                return {'error': 'User not found'}
            
            # Check admin flag
            if user['is_admin']:
                return {
                    'is_trial': False,
                    'is_admin': True,
                    'unlimited': True,
                    'messages_remaining': 'unlimited',
                    'plan': 'admin'
                }
            
            # Paid plan
            if user['plan_type'] in ['basic', 'standard', 'enterprise']:
                return {
                    'is_trial': False,
                    'plan': user['plan_type'],
                    'unlimited': True,
                    'messages_remaining': 'unlimited'
                }
            
            # Trial status
            remaining = user['trial_messages_remaining'] or 0
            expires_at = user['trial_expires_at']
            
            if expires_at:
                try:
                    expiry = datetime.fromisoformat(expires_at)
                    expired = datetime.now() > expiry
                    days_left = (expiry - datetime.now()).days if not expired else 0
                except (ValueError, TypeError):
                    expired = False
                    days_left = None
            else:
                expired = False
                days_left = None
            
            return {
                'is_trial': True,
                'messages_remaining': remaining,
                'days_left': days_left,
                'expired': expired,
                'started_at': user['trial_started_at'],
                'expires_at': expires_at,
                'needs_upgrade': remaining <= 0 or expired,
                'upgrade_url': '/checkout/basic' if (remaining <= 0 or expired) else None
            }
    
    def upgrade_to_paid(self, user_id, plan_type):
        """
        Upgrade user from trial to paid plan
        
        Args:
            user_id: User ID
            plan_type: 'basic', 'standard', or 'enterprise'
        
        Returns:
            bool: True if upgrade successful
        """
        valid_plans = ['basic', 'standard', 'enterprise']
        if plan_type not in valid_plans:
            print(f"âŒ Invalid plan type: {plan_type}")
            return False
        
        with self.get_db() as conn:
            c = conn.cursor()
            
            c.execute('''
                UPDATE users 
                SET plan_type = ?,
                    trial_messages_remaining = NULL,
                    trial_expires_at = NULL
                WHERE id = ?
            ''', (plan_type, user_id))
            
            conn.commit()
        
        print(f"âœ… User {user_id} upgraded to {plan_type} plan")
        return True
    
    def extend_trial(self, user_id, extra_messages=25, extra_days=3):
        """
        Extend trial for user (customer support feature)
        
        Args:
            user_id: User ID
            extra_messages: Additional messages to add
            extra_days: Additional days to add
        
        Returns:
            bool: True if extension successful
        """
        with self.get_db() as conn:
            c = conn.cursor()
            
            c.execute('''
                SELECT trial_messages_remaining, trial_expires_at
                FROM users 
                WHERE id = ?
            ''', (user_id,))
            
            user = c.fetchone()
            
            if not user:
                print(f"âŒ User {user_id} not found")
                return False
            
            # Calculate new values
            new_messages = (user['trial_messages_remaining'] or 0) + extra_messages
            
            if user['trial_expires_at']:
                try:
                    current_expiry = datetime.fromisoformat(user['trial_expires_at'])
                    new_expiry = current_expiry + timedelta(days=extra_days)
                except (ValueError, TypeError):
                    new_expiry = datetime.now() + timedelta(days=extra_days)
            else:
                new_expiry = datetime.now() + timedelta(days=extra_days)
            
            # Update database
            c.execute('''
                UPDATE users 
                SET trial_messages_remaining = ?,
                    trial_expires_at = ?
                WHERE id = ?
            ''', (new_messages, new_expiry, user_id))
            
            conn.commit()
        
        print(f"âœ… Trial extended for user {user_id}: +{extra_messages} messages, +{extra_days} days")
        return True
    
    def reset_trial(self, user_id):
        """
        Reset trial to initial state (admin function)
        
        Args:
            user_id: User ID
        
        Returns:
            bool: True if reset successful
        """
        return self.start_trial(user_id, trial_messages=50, trial_days=7)
    
    def get_all_trial_stats(self):
        """
        Get platform-wide trial statistics (admin function)
        
        Returns:
            dict: Trial statistics across all users
        """
        with self.get_db() as conn:
            c = conn.cursor()
            
            # Total trials
            c.execute('''
                SELECT COUNT(*) FROM users 
                WHERE plan_type = 'trial' OR trial_messages_remaining IS NOT NULL
            ''')
            total_trials = c.fetchone()[0]
            
            # Active trials (not expired)
            c.execute('''
                SELECT COUNT(*) FROM users 
                WHERE plan_type = 'trial' 
                AND (trial_expires_at IS NULL OR trial_expires_at > CURRENT_TIMESTAMP)
                AND trial_messages_remaining > 0
            ''')
            active_trials = c.fetchone()[0]
            
            # Expired trials
            c.execute('''
                SELECT COUNT(*) FROM users 
                WHERE plan_type = 'trial' 
                AND (trial_expires_at < CURRENT_TIMESTAMP OR trial_messages_remaining <= 0)
            ''')
            expired_trials = c.fetchone()[0]
            
            # Converted to paid
            c.execute('''
                SELECT COUNT(*) FROM users 
                WHERE plan_type IN ('basic', 'standard', 'enterprise')
                AND trial_started_at IS NOT NULL
            ''')
            converted_users = c.fetchone()[0]
            
            # Conversion rate
            conversion_rate = (converted_users / total_trials * 100) if total_trials > 0 else 0
            
            return {
                'total_trials': total_trials,
                'active_trials': active_trials,
                'expired_trials': expired_trials,
                'converted_users': converted_users,
                'conversion_rate': round(conversion_rate, 2)
            }


# Flask integration decorator
def require_trial_or_paid(f):
    """
    Decorator to check if user has trial messages or paid plan
    Use this on routes that consume a message/credit
    
    Usage:
        @app.route('/api/test-chat', methods=['POST'])
        @require_trial_or_paid
        def test_chat(trial_info=None):
            # trial_info contains status
            return jsonify({'reply': 'Hello', 'trial_info': trial_info})
    """
    from functools import wraps
    from flask import session, jsonify
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not logged in'}), 401
        
        trial_mgr = TrialManager()
        status = trial_mgr.use_trial_message(session['user_id'])
        
        if not status['allowed']:
            return jsonify({
                'error': 'Trial limit reached',
                'message': status.get('message'),
                'needs_upgrade': True,
                'upgrade_url': status.get('upgrade_url', '/checkout/basic'),
                'trial_expired': status.get('expired', False)
            }), 402  # Payment Required
        
        # Add trial info to request context
        kwargs['trial_info'] = status
        
        return f(*args, **kwargs)
    
    return decorated_function


# Example usage in main.py routes:
"""
INTEGRATION EXAMPLE:
===================

1. Import at top of main.py:
   from trial_manager import TrialManager, require_trial_or_paid

2. Initialize after app creation:
   trial_mgr = TrialManager()

3. Add decorator to any route that uses credits:
   @app.route('/api/test-chat', methods=['POST'])
   @require_trial_or_paid  # ⬅️ Add this line
   def test_chat(trial_info=None):  # ⬅️ Add trial_info parameter
       # ... your existing code ...
       
       # Optionally show trial info in response
       return jsonify({
           'reply': ai_reply,
           'trial_info': trial_info  # Shows remaining messages
       })

4. Start trial for new users:
   # In your register() function, after creating user:
   trial_mgr.start_trial(user_id, trial_messages=50, trial_days=7)

5. Check trial status anytime:
   status = trial_mgr.get_trial_status(session['user_id'])
   print(f"User has {status['messages_remaining']} messages left")
"""


# ==================== TESTING & DEBUGGING ====================

if __name__ == "__main__":
    print("ðŸ§ª Testing Trial Manager...\n")
    
    # Initialize
    trial_mgr = TrialManager()
    
    # Test 1: Start trial
    print("=" * 50)
    print("Test 1: Starting Trial")
    print("=" * 50)
    test_user_id = 999
    trial_mgr.start_trial(test_user_id, trial_messages=10, trial_days=7)
    
    # Test 2: Check status
    print("\n" + "=" * 50)
    print("Test 2: Checking Status")
    print("=" * 50)
    status = trial_mgr.get_trial_status(test_user_id)
    print(f"Trial Status: {status}")
    
    # Test 3: Use messages
    print("\n" + "=" * 50)
    print("Test 3: Using Messages")
    print("=" * 50)
    for i in range(3):
        result = trial_mgr.use_trial_message(test_user_id)
        print(f"Message {i+1}: {result['messages_remaining']} remaining")
    
    # Test 4: Extend trial
    print("\n" + "=" * 50)
    print("Test 4: Extending Trial")
    print("=" * 50)
    trial_mgr.extend_trial(test_user_id, extra_messages=5, extra_days=3)
    status = trial_mgr.get_trial_status(test_user_id)
    print(f"After extension: {status['messages_remaining']} messages")
    
    # Test 5: Platform stats
    print("\n" + "=" * 50)
    print("Test 5: Platform Statistics")
    print("=" * 50)
    stats = trial_mgr.get_all_trial_stats()
    print(f"Platform Stats: {stats}")
    
    print("\n✅ All tests complete!")
