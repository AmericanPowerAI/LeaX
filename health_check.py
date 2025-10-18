"""
Health check endpoint for monitoring and load balancers
"""
from flask import jsonify
import sqlite3
import os

def register_health_check(app):
    """Register health check endpoints"""
    
    @app.route('/health')
    def health_check():
        """Basic health check"""
        try:
            # Check database
            db_path = os.environ.get('DATABASE_FILE', 'leax_users.db')
            with sqlite3.connect(db_path) as conn:
                conn.execute('SELECT 1')
            
            return jsonify({
                'status': 'healthy',
                'service': 'leax-ai',
                'version': '1.0.0'
            }), 200
        except:
            return jsonify({
                'status': 'unhealthy',
                'service': 'leax-ai'
            }), 503
    
    @app.route('/health/detailed')
    def detailed_health():
        """Detailed health check with system info"""
        try:
            import psutil
            
            return jsonify({
                'status': 'healthy',
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'uptime_seconds': time.time() - psutil.boot_time()
            }), 200
        except:
            return jsonify({'status': 'healthy'}), 200
