"""
Funding Tracker - Automatically tracks billable events
Generates FCC reports, submits reimbursement claims
"""

import sqlite3
from datetime import datetime
import json

class FundingTracker:
    def __init__(self):
        self.db = 'funding_tracker.db'
        self._init_db()
    
    def _init_db(self):
        """Create funding tracking tables"""
        with sqlite3.connect(self.db) as conn:
            c = conn.cursor()
            
            # Track billable minutes for IP CTS, VRS, STS
            c.execute('''
                CREATE TABLE IF NOT EXISTS billable_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    from_number TEXT,
                    duration_seconds INTEGER,
                    billable_amount DECIMAL(10,4),
                    program_type TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    claimed BOOLEAN DEFAULT 0,
                    claim_date TIMESTAMP
                )
            ''')
            
            # Track Lifeline/ACP enrollments
            c.execute('''
                CREATE TABLE IF NOT EXISTS subsidy_customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    customer_phone TEXT NOT NULL,
                    program_type TEXT,
                    monthly_subsidy DECIMAL(10,2),
                    enrolled_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active'
                )
            ''')
            
            conn.commit()
    
    def track_billable_event(self, user_id, event_type, duration_seconds, from_number):
        """
        Track any event that generates government funding
        
        event_type: 'caption', 'speech_assist', 'video_relay', etc.
        """
        # Calculate billable amount based on program
        rates = {
            'caption': 1.40,  # IP CTS: $1.40/minute
            'speech_assist': 1.75,  # STS: $1.75/minute
            'video_relay': 3.00  # VRS: $3.00/minute (avg)
        }
        
        rate_per_minute = rates.get(event_type, 0)
        duration_minutes = duration_seconds / 60
        billable_amount = duration_minutes * rate_per_minute
        
        with sqlite3.connect(self.db) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO billable_events
                (user_id, event_type, from_number, duration_seconds, billable_amount, program_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, event_type, from_number, duration_seconds, billable_amount, 
                  'IP_CTS' if event_type == 'caption' else 'STS'))
            conn.commit()
    
    def get_monthly_earnings(self, user_id):
        """Calculate how much money user generated this month"""
        with sqlite3.connect(self.db) as conn:
            c = conn.cursor()
            
            # Billable minutes earnings
            c.execute('''
                SELECT SUM(billable_amount) 
                FROM billable_events 
                WHERE user_id = ? 
                AND strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')
            ''', (user_id,))
            
            minutes_earnings = c.fetchone()[0] or 0
            
            # Subsidy earnings (Lifeline/ACP)
            c.execute('''
                SELECT COUNT(*) * 39.25
                FROM subsidy_customers
                WHERE user_id = ?
                AND status = 'active'
            ''', (user_id,))
            
            subsidy_earnings = c.fetchone()[0] or 0
            
            return {
                'minutes_earnings': float(minutes_earnings),
                'subsidy_earnings': float(subsidy_earnings),
                'total_monthly': float(minutes_earnings + subsidy_earnings)
            }
    
    def generate_fcc_report(self, user_id, month, year):
        """Auto-generate FCC compliance report (Form 1187)"""
        with sqlite3.connect(self.db) as conn:
            c = conn.cursor()
            
            # Get all billable events for the month
            c.execute('''
                SELECT event_type, SUM(duration_seconds), SUM(billable_amount)
                FROM billable_events
                WHERE user_id = ?
                AND strftime('%Y-%m', timestamp) = ?
                GROUP BY event_type
            ''', (user_id, f"{year}-{month:02d}"))
            
            report_data = c.fetchall()
            
            # Format for FCC submission
            fcc_report = {
                'provider_id': user_id,
                'reporting_period': f"{year}-{month:02d}",
                'caption_minutes': 0,
                'speech_minutes': 0,
                'total_reimbursement': 0
            }
            
            for event_type, total_seconds, total_amount in report_data:
                if event_type == 'caption':
                    fcc_report['caption_minutes'] = total_seconds / 60
                elif event_type == 'speech_assist':
                    fcc_report['speech_minutes'] = total_seconds / 60
                fcc_report['total_reimbursement'] += total_amount
            
            return fcc_report
