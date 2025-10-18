"""
Enhanced Admin Settings - Add funding controls to existing dashboard
"""

from flask import render_template, session, redirect, url_for, request, jsonify
from funding_tracker import FundingTracker
from accessibility_layer import AccessibilityEngine

funding = FundingTracker()
accessibility = AccessibilityEngine()

def register_funding_routes(app):
    """Add new routes to existing Flask app"""
    
    @app.route('/funding-dashboard')
    def funding_dashboard():
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        earnings = funding.get_monthly_earnings(session['user_id'])
        
        return render_template('funding_dashboard.html',
            earnings=earnings,
            business_name=session['business_name']
        )
    
    @app.route('/enable-accessibility', methods=['POST'])
    def enable_accessibility():
        if 'user_id' not in session:
            return jsonify({'error': 'Not logged in'})
        
        feature = request.json.get('feature')  # 'captions', 'speech_assist', etc.
        enabled = request.json.get('enabled', True)
        
        # Update in memory_manager
        from memory_manager import MemoryManager
        memory_mgr = MemoryManager()
        memory = memory_mgr.load_customer_memory(session['user_id'])
        
        if 'accessibility_settings' not in memory:
            memory['accessibility_settings'] = {}
        
        memory['accessibility_settings'][f'{feature}_enabled'] = enabled
        memory_mgr.save_customer_memory(session['user_id'], memory)
        
        return jsonify({'success': True, 'message': f'{feature} {"enabled" if enabled else "disabled"}'})
    
    @app.route('/apply-for-funding/<program>')
    def apply_for_funding(program):
        """One-click grant applications"""
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        # Auto-generate application for program (Lifeline, ACP, USDA, etc.)
        # Fill in user's business info automatically
        
        return render_template('grant_application.html',
            program=program,
            business_name=session['business_name']
        )
