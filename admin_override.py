"""
Admin Override - Free unlimited access for YOU
Set your email here and you'll have unlimited everything
"""

# YOUR EMAIL - Change this to your actual email
ADMIN_EMAIL = "admin@americanpower.us"

def is_admin(user_id=None, email=None):
    """Check if user is admin (you)"""
    if email and email.lower() == ADMIN_EMAIL.lower():
        return True
    
    # Check by user_id if provided
    if user_id:
        import sqlite3
        try:
            with sqlite3.connect('leax_users.db') as conn:
                c = conn.cursor()
                c.execute('SELECT email FROM users WHERE id = ?', (user_id,))
                result = c.fetchone()
                if result and result[0].lower() == ADMIN_EMAIL.lower():
                    return True
        except:
            pass
    
    return False

def get_admin_privileges(user_id):
    """Get admin privileges"""
    if is_admin(user_id):
        return {
            'unlimited_messages': True,
            'unlimited_trials': True,
            'no_payment_required': True,
            'all_features_unlocked': True,
            'can_bypass_limits': True
        }
    return None
