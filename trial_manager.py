"""
Trial Manager - Give users limited free trials to test full UX
Users get X free messages to test everything before subscribing
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
            try:
                c.execute('''
                    ALTER TABLE users ADD COLUMN trial_messages_remaining INTEGER DEFAULT 50
                ''')
            except:
                pass  # Column already exists
            
            try:
                c.execute('''
                    ALTER TABLE users ADD COLUMN trial_started_at TIMESTAMP
                ''')
            except:
                pass
            
            try:
                c.execute('''
                    ALTER TABLE users ADD COLUMN trial_expires_at TIMESTAMP
                ''')
            except:
                pass
            
            conn.commit()
    
    def start_trial(self, user_id, trial_messages=50, trial_days=7):
        """
        Start free trial for user
        
        Args:
            user_id: User ID
            trial_messages: Number of free messages (default 50)
            trial_days: Trial duration in days (default 7)
        """
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
        
        print(f"✅ Trial started for user {user_id}: {trial_messages} messages, {trial_days} days")
        return True
    
    def use_trial_message(self, user_id):
        """
        Use one trial message
        
        Returns:
            dict: Trial status with remaining messages
        """
        with self.get_db() as conn:
            c = conn.cursor()
            
            # Get current trial status
            c.execute('''
                SELECT trial_messages_remaining, trial_expires_at, plan_type
                FROM users 
                WHERE id = ?
            ''', (user_id,))
            
            user = c.fetchone()
            
            if not user:
                return {'allowed': False, 'error': 'User not found'}
            
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
                expiry = datetime.fromisoformat(user['trial_expires_at'])
                if datetime.now() > expiry:
                    return {
                        'allowed': False,
                        'trial': True,
                        'expired': True,
                        'messages_remaining': 0,
                        'message': 'Trial expired. Please upgrade to continue.'
                    }
            
            # Check remaining messages
            remaining = user['trial_messages_remaining'] or 0
            
            if remaining <= 0:
                return {
                    'allowed': False,
                    'trial': True,
                    'messages_remaining': 0,
                    'message': 'Trial messages used up. Please upgrade to continue.'
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
        
        Returns:
            dict: Trial information
        """
        with self.get_db() as conn:
            c = conn.cursor()
            
            c.execute('''
                SELECT trial_messages_remaining, trial_started_at, 
                       trial_expires_at, plan_type
                FROM users 
                WHERE id = ?
            ''', (user_id,))
            
            user = c.fetchone()
            
            if not user:
                return {'error': 'User not found'}
            
            # Paid plan
            if user['plan_type'] in ['basic', 'standard', 'enterprise']:
                return {
                    'is_trial': False,
                    'plan': user['plan_type'],
                    'unlimited': True
                }
            
            # Trial status
            remaining = user['trial_messages_remaining'] or 0
            expires_at = user['trial_expires_at']
            
            if expires_at:
                expiry = datetime.fromisoformat(expires_at)
                expired = datetime.now() > expiry
                days_left = (expiry - datetime.now()).days if not expired else 0
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
                'needs_upgrade': remaining <= 0 or expired
            }
    
    def upgrade_to_paid(self, user_id, plan_type):
        """
        Upgrade user from trial to paid plan
        
        Args:
            user_id: User ID
            plan_type: 'basic', 'standard', or 'enterprise'
        """
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
        
        print(f"✅ User {user_id} upgraded to {plan_type} plan")
        return True
    
    def extend_trial(self, user_id, extra_messages=25, extra_days=3):
        """
        Extend trial for user (customer support feature)
        
        Args:
            user_id: User ID
            extra_messages: Additional messages to add
            extra_days: Additional days to add
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
                return False
            
            new_messages = (user['trial_messages_remaining'] or 0) + extra_messages
            
            if user['trial_expires_at']:
                current_expiry = datetime.fromisoformat(user['trial_expires_at'])
                new_expiry = current_expiry + timedelta(days=extra_days)
            else:
                new_expiry = datetime.now() + timedelta(days=extra_days)
            
            c.execute('''
                UPDATE users 
                SET trial_messages_remaining = ?,
                    trial_expires_at = ?
                WHERE id = ?
            ''', (new_messages, new_expiry, user_id))
            
            conn.commit()
        
        print(f"✅ Trial extended for user {user_id}: +{extra_messages} messages, +{extra_days} days")
        return True


# Flask integration decorator
def require_trial_or_paid(f):
    """
    Decorator to check if user has trial messages or paid plan
    Use this on routes that consume a message/credit
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
                'upgrade_url': '/checkout/basic'
            }), 402  # Payment Required
        
        # Add trial info to request context
        kwargs['trial_info'] = status
        
        return f(*args, **kwargs)
    
    return decorated_function


# Example usage in main.py routes:
"""
from trial_manager import TrialManager, require_trial_or_paid

trial_mgr = TrialManager()

@app.route('/api/test-chat', methods=['POST'])
@require_trial_or_paid  # Add this decorator
def test_chat(trial_info=None):
    # ... your existing code ...
    
    # Optionally show trial info in response
    return jsonify({
        'reply': ai_reply,
        'trial_info': trial_info  # Shows remaining messages
    })
"""
