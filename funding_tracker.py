"""
Funding Tracker - Automatically tracks billable events
Generates FCC reports, submits reimbursement claims

This module handles ALL government funding programs:
- IP CTS (Internet Protocol Captioned Telephone Service) - $1.40/min
- STS (Speech-to-Speech) - $1.75/min
- VRS (Video Relay Service) - $3.00/min average
- Lifeline - $9.25/month per subscriber
- ACP (Affordable Connectivity Program) - $30/month per subscriber
- Rural subsidies and grants

Automatically:
- Tracks every billable minute
- Calculates earnings in real-time
- Generates FCC Form 1187 reports
- Manages subsidy enrollments
- Prepares reimbursement claims
"""

import sqlite3
from datetime import datetime, timedelta
import json
import os
import csv
from decimal import Decimal

class FundingTracker:
    """
    Main funding tracker that monitors all government-reimbursable activities
    and prepares compliance reports
    """
    
    def __init__(self, db_path='funding_tracker.db'):
        """
        Initialize funding tracker with database
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db = db_path
        self._init_db()
        print("✅ Funding Tracker initialized")
    
    def _init_db(self):
        """Create all necessary database tables for funding tracking"""
        with sqlite3.connect(self.db) as conn:
            c = conn.cursor()
            
            # Track billable minutes for IP CTS, VRS, STS
            c.execute('''
                CREATE TABLE IF NOT EXISTS billable_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    from_number TEXT,
                    to_number TEXT,
                    duration_seconds INTEGER,
                    billable_amount DECIMAL(10,4),
                    program_type TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    claimed BOOLEAN DEFAULT 0,
                    claim_date TIMESTAMP,
                    claim_id TEXT,
                    notes TEXT
                )
            ''')
            
            # Track Lifeline/ACP enrollments and monthly subsidies
            c.execute('''
                CREATE TABLE IF NOT EXISTS subsidy_customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    customer_phone TEXT NOT NULL,
                    customer_name TEXT,
                    customer_email TEXT,
                    program_type TEXT NOT NULL,
                    monthly_subsidy DECIMAL(10,2),
                    enrolled_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    eligibility_verified BOOLEAN DEFAULT 0,
                    verification_date TIMESTAMP,
                    tribal_lands BOOLEAN DEFAULT 0,
                    last_billing_date TIMESTAMP,
                    total_billed DECIMAL(10,2) DEFAULT 0,
                    notes TEXT,
                    UNIQUE(user_id, customer_phone, program_type)
                )
            ''')
            
            # Track reimbursement claims submitted to FCC/USAC
            c.execute('''
                CREATE TABLE IF NOT EXISTS reimbursement_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    claim_period TEXT NOT NULL,
                    program_type TEXT NOT NULL,
                    total_minutes DECIMAL(10,2),
                    total_amount DECIMAL(10,2),
                    submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    approval_date TIMESTAMP,
                    payment_date TIMESTAMP,
                    payment_amount DECIMAL(10,2),
                    claim_reference TEXT,
                    notes TEXT
                )
            ''')
            
            # Track grant applications and awards
            c.execute('''
                CREATE TABLE IF NOT EXISTS grants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    grant_program TEXT NOT NULL,
                    grant_name TEXT,
                    application_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    amount_requested DECIMAL(10,2),
                    status TEXT DEFAULT 'pending',
                    award_date TIMESTAMP,
                    award_amount DECIMAL(10,2),
                    payment_schedule TEXT,
                    reporting_requirements TEXT,
                    notes TEXT
                )
            ''')
            
            # Create indexes for faster queries
            c.execute('CREATE INDEX IF NOT EXISTS idx_billable_user_date ON billable_events(user_id, timestamp)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_subsidy_user ON subsidy_customers(user_id, status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_claims_user ON reimbursement_claims(user_id, claim_period)')
            
            conn.commit()
        
        print("✅ Funding database initialized")
    
    def track_billable_event(self, user_id, event_type, duration_seconds, from_number, to_number=None, notes=None):
        """
        Track any event that generates government funding
        
        Args:
            user_id: User providing the service
            event_type: Type of service ('caption', 'speech_assist', 'video_relay')
            duration_seconds: Duration in seconds
            from_number: Customer's phone number
            to_number: Service number (optional)
            notes: Additional notes (optional)
            
        Returns:
            dict: Event details including billable amount
        """
        try:
            # Calculate billable amount based on program rates
            rates = {
                'caption': 1.40,        # IP CTS: $1.40/minute
                'speech_assist': 1.75,  # STS: $1.75/minute
                'video_relay': 3.00,    # VRS: $3.00/minute (average)
                'ip_relay': 1.28,       # IP Relay: $1.28/minute
                'vri': 2.50            # Video Remote Interpreting: $2.50/minute
            }
            
            rate_per_minute = rates.get(event_type, 0)
            duration_minutes = Decimal(duration_seconds) / Decimal(60)
            billable_amount = duration_minutes * Decimal(rate_per_minute)
            
            # Determine program type
            program_map = {
                'caption': 'IP_CTS',
                'speech_assist': 'STS',
                'video_relay': 'VRS',
                'ip_relay': 'IP_RELAY',
                'vri': 'VRI'
            }
            program_type = program_map.get(event_type, 'OTHER')
            
            # Save to database
            with sqlite3.connect(self.db) as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT INTO billable_events
                    (user_id, event_type, from_number, to_number, duration_seconds, 
                     billable_amount, program_type, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, event_type, from_number, to_number, duration_seconds, 
                      float(billable_amount), program_type, notes))
                
                event_id = c.lastrowid
                conn.commit()
            
            print(f"💰 Billable event tracked: {event_type} - ${billable_amount:.2f} ({duration_seconds}s)")
            
            return {
                'event_id': event_id,
                'event_type': event_type,
                'program_type': program_type,
                'duration_seconds': duration_seconds,
                'duration_minutes': float(duration_minutes),
                'rate_per_minute': rate_per_minute,
                'billable_amount': float(billable_amount),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error tracking billable event: {e}")
            return {'error': str(e)}
    
    def get_monthly_earnings(self, user_id, month=None, year=None):
        """
        Calculate how much money user generated this month from all programs
        
        Args:
            user_id: User ID
            month: Month number (defaults to current month)
            year: Year (defaults to current year)
            
        Returns:
            dict: Earnings breakdown by program
        """
        try:
            if not month:
                month = datetime.now().month
            if not year:
                year = datetime.now().year
            
            with sqlite3.connect(self.db) as conn:
                c = conn.cursor()
                
                # Billable minutes earnings (IP CTS, STS, VRS)
                c.execute('''
                    SELECT SUM(billable_amount), program_type
                    FROM billable_events 
                    WHERE user_id = ? 
                    AND strftime('%Y-%m', timestamp) = ?
                    GROUP BY program_type
                ''', (user_id, f"{year}-{month:02d}"))
                
                minutes_data = c.fetchall()
                minutes_earnings = {}
                total_minutes_earnings = 0
                
                for amount, program in minutes_data:
                    if amount:
                        minutes_earnings[program] = float(amount)
                        total_minutes_earnings += float(amount)
                
                # Subsidy earnings (Lifeline/ACP)
                c.execute('''
                    SELECT COUNT(*) * 9.25 as lifeline,
                           COUNT(*) * 30.00 as acp
                    FROM subsidy_customers
                    WHERE user_id = ?
                    AND status = 'active'
                    AND program_type IN ('lifeline', 'acp')
                ''', (user_id,))
                
                subsidy_result = c.fetchone()
                
                # Count customers by program type
                c.execute('''
                    SELECT program_type, COUNT(*) as count
                    FROM subsidy_customers
                    WHERE user_id = ?
                    AND status = 'active'
                    GROUP BY program_type
                ''', (user_id,))
                
                subsidy_counts = {}
                for program, count in c.fetchall():
                    subsidy_counts[program] = count
                
                # Calculate subsidy earnings
                lifeline_customers = subsidy_counts.get('lifeline', 0)
                acp_customers = subsidy_counts.get('acp', 0)
                
                lifeline_earnings = lifeline_customers * 9.25
                acp_earnings = acp_customers * 30.00
                tribal_earnings = subsidy_counts.get('tribal_lifeline', 0) * 34.25
                
                total_subsidy_earnings = lifeline_earnings + acp_earnings + tribal_earnings
                
                # Total earnings
                total_monthly = total_minutes_earnings + total_subsidy_earnings
                
                earnings = {
                    'user_id': user_id,
                    'period': f"{year}-{month:02d}",
                    'minutes_earnings': total_minutes_earnings,
                    'minutes_breakdown': minutes_earnings,
                    'subsidy_earnings': total_subsidy_earnings,
                    'subsidy_breakdown': {
                        'lifeline': lifeline_earnings,
                        'acp': acp_earnings,
                        'tribal': tribal_earnings
                    },
                    'subsidy_customers': {
                        'lifeline': lifeline_customers,
                        'acp': acp_customers,
                        'tribal': subsidy_counts.get('tribal_lifeline', 0)
                    },
                    'total_monthly': total_monthly
                }
                
                return earnings
                
        except Exception as e:
            print(f"❌ Error calculating earnings: {e}")
            return {
                'error': str(e),
                'minutes_earnings': 0,
                'subsidy_earnings': 0,
                'total_monthly': 0
            }
    
    def generate_fcc_report(self, user_id, month, year, report_type='form_1187'):
        """
        Auto-generate FCC compliance report (Form 1187 for IP CTS/STS)
        
        Args:
            user_id: User/provider ID
            month: Report month
            year: Report year
            report_type: Type of report ('form_1187', 'form_431', etc.)
            
        Returns:
            dict: Formatted FCC report data
        """
        try:
            with sqlite3.connect(self.db) as conn:
                c = conn.cursor()
                
                # Get all billable events for the period
                c.execute('''
                    SELECT event_type, program_type, 
                           SUM(duration_seconds) as total_seconds, 
                           SUM(billable_amount) as total_amount,
                           COUNT(*) as event_count
                    FROM billable_events
                    WHERE user_id = ?
                    AND strftime('%Y-%m', timestamp) = ?
                    GROUP BY event_type, program_type
                ''', (user_id, f"{year}-{month:02d}"))
                
                report_data = c.fetchall()
                
                # Format for FCC Form 1187 submission
                fcc_report = {
                    'form_type': report_type,
                    'provider_id': user_id,
                    'reporting_period': f"{year}-{month:02d}",
                    'submission_date': datetime.now().isoformat(),
                    'programs': {}
                }
                
                total_reimbursement = 0
                
                for event_type, program_type, total_seconds, total_amount, event_count in report_data:
                    if not program_type in fcc_report['programs']:
                        fcc_report['programs'][program_type] = {
                            'total_minutes': 0,
                            'total_amount': 0,
                            'event_count': 0
                        }
                    
                    minutes = total_seconds / 60
                    fcc_report['programs'][program_type]['total_minutes'] += minutes
                    fcc_report['programs'][program_type]['total_amount'] += total_amount
                    fcc_report['programs'][program_type]['event_count'] += event_count
                    total_reimbursement += total_amount
                
                fcc_report['total_reimbursement'] = float(total_reimbursement)
                fcc_report['certification'] = {
                    'certified_by': 'System Administrator',
                    'certification_date': datetime.now().isoformat(),
                    'accuracy_statement': 'I certify that the information contained in this report is true and accurate to the best of my knowledge.'
                }
                
                print(f"📊 FCC Report {report_type} generated for {year}-{month:02d}: ${total_reimbursement:.2f}")
                
                return fcc_report
                
        except Exception as e:
            print(f"❌ Error generating FCC report: {e}")
            return {'error': str(e)}
    
    def export_fcc_report_csv(self, user_id, month, year, output_file=None):
        """
        Export FCC report as CSV file for submission
        
        Args:
            user_id: User ID
            month: Report month
            year: Report year
            output_file: Output filename (optional)
            
        Returns:
            str: Path to generated CSV file
        """
        try:
            if not output_file:
                output_file = f"fcc_report_{user_id}_{year}_{month:02d}.csv"
            
            report = self.generate_fcc_report(user_id, month, year)
            
            with open(output_file, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                # Header
                writer.writerow(['FCC Compliance Report'])
                writer.writerow(['Provider ID', report['provider_id']])
                writer.writerow(['Reporting Period', report['reporting_period']])
                writer.writerow(['Submission Date', report['submission_date']])
                writer.writerow([])
                
                # Programs
                writer.writerow(['Program Type', 'Total Minutes', 'Total Amount', 'Event Count'])
                
                for program, data in report['programs'].items():
                    writer.writerow([
                        program,
                        f"{data['total_minutes']:.2f}",
                        f"${data['total_amount']:.2f}",
                        data['event_count']
                    ])
                
                writer.writerow([])
                writer.writerow(['Total Reimbursement', f"${report['total_reimbursement']:.2f}"])
            
            print(f"✅ FCC report exported to {output_file}")
            return output_file
            
        except Exception as e:
            print(f"❌ Error exporting FCC report: {e}")
            return None
    
    def enroll_subsidy_customer(self, user_id, customer_phone, program_type, customer_name=None, 
                                customer_email=None, tribal_lands=False):
        """
        Enroll a customer in Lifeline or ACP subsidy program
        
        Args:
            user_id: Provider user ID
            customer_phone: Customer's phone number
            program_type: 'lifeline', 'acp', or 'tribal_lifeline'
            customer_name: Customer name (optional)
            customer_email: Customer email (optional)
            tribal_lands: Whether customer is on tribal lands
            
        Returns:
            dict: Enrollment details
        """
        try:
            # Determine monthly subsidy amount
            subsidy_amounts = {
                'lifeline': 9.25,
                'acp': 30.00,
                'tribal_lifeline': 34.25  # Enhanced Lifeline for tribal lands
            }
            
            monthly_subsidy = subsidy_amounts.get(program_type, 0)
            
            with sqlite3.connect(self.db) as conn:
                c = conn.cursor()
                
                # Check if already enrolled
                c.execute('''
                    SELECT id FROM subsidy_customers
                    WHERE user_id = ? AND customer_phone = ? AND program_type = ?
                ''', (user_id, customer_phone, program_type))
                
                existing = c.fetchone()
                
                if existing:
                    print(f"⚠️ Customer {customer_phone} already enrolled in {program_type}")
                    return {'error': 'Customer already enrolled', 'enrollment_id': existing[0]}
                
                # Enroll customer
                c.execute('''
                    INSERT INTO subsidy_customers
                    (user_id, customer_phone, customer_name, customer_email, program_type, 
                     monthly_subsidy, tribal_lands, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_verification')
                ''', (user_id, customer_phone, customer_name, customer_email, 
                      program_type, monthly_subsidy, tribal_lands))
                
                enrollment_id = c.lastrowid
                conn.commit()
            
            print(f"✅ Customer enrolled in {program_type}: {customer_phone} (${monthly_subsidy}/month)")
            
            return {
                'enrollment_id': enrollment_id,
                'user_id': user_id,
                'customer_phone': customer_phone,
                'program_type': program_type,
                'monthly_subsidy': monthly_subsidy,
                'status': 'pending_verification',
                'enrolled_date': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error enrolling subsidy customer: {e}")
            return {'error': str(e)}
    
    def verify_subsidy_eligibility(self, enrollment_id, verified=True, notes=None):
        """
        Mark subsidy enrollment as verified/approved
        
        Args:
            enrollment_id: Enrollment ID
            verified: Whether eligibility is verified
            notes: Verification notes
            
        Returns:
            bool: Success status
        """
        try:
            with sqlite3.connect(self.db) as conn:
                c = conn.cursor()
                
                status = 'active' if verified else 'rejected'
                
                c.execute('''
                    UPDATE subsidy_customers
                    SET eligibility_verified = ?,
                        verification_date = CURRENT_TIMESTAMP,
                        status = ?,
                        notes = ?
                    WHERE id = ?
                ''', (verified, status, notes, enrollment_id))
                
                conn.commit()
            
            print(f"✅ Enrollment {enrollment_id} verified: {status}")
            return True
            
        except Exception as e:
            print(f"❌ Error verifying eligibility: {e}")
            return False
    
    def submit_reimbursement_claim(self, user_id, month, year, program_type):
        """
        Submit reimbursement claim to FCC/USAC
        
        Args:
            user_id: Provider user ID
            month: Claim month
            year: Claim year
            program_type: Type of program ('IP_CTS', 'STS', 'VRS', etc.)
            
        Returns:
            dict: Claim details
        """
        try:
            # Generate report for the period
            report = self.generate_fcc_report(user_id, month, year)
            
            if program_type not in report['programs']:
                print(f"⚠️ No billable events for {program_type} in {year}-{month:02d}")
                return {'error': f'No events for {program_type}'}
            
            program_data = report['programs'][program_type]
            
            claim_period = f"{year}-{month:02d}"
            claim_reference = f"CLAIM-{user_id}-{program_type}-{claim_period}"
            
            with sqlite3.connect(self.db) as conn:
                c = conn.cursor()
                
                c.execute('''
                    INSERT INTO reimbursement_claims
                    (user_id, claim_period, program_type, total_minutes, total_amount, 
                     status, claim_reference)
                    VALUES (?, ?, ?, ?, ?, 'submitted', ?)
                ''', (user_id, claim_period, program_type, 
                      program_data['total_minutes'], program_data['total_amount'],
                      claim_reference))
                
                claim_id = c.lastrowid
                
                # Mark events as claimed
                c.execute('''
                    UPDATE billable_events
                    SET claimed = 1, claim_date = CURRENT_TIMESTAMP, claim_id = ?
                    WHERE user_id = ? 
                    AND program_type = ?
                    AND strftime('%Y-%m', timestamp) = ?
                    AND claimed = 0
                ''', (claim_reference, user_id, program_type, claim_period))
                
                conn.commit()
            
            print(f"💵 Reimbursement claim submitted: {claim_reference} (${program_data['total_amount']:.2f})")
            
            return {
                'claim_id': claim_id,
                'claim_reference': claim_reference,
                'user_id': user_id,
                'program_type': program_type,
                'claim_period': claim_period,
                'total_minutes': program_data['total_minutes'],
                'total_amount': program_data['total_amount'],
                'status': 'submitted',
                'submission_date': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error submitting reimbursement claim: {e}")
            return {'error': str(e)}
    
    def get_pending_claims(self, user_id):
        """
        Get all pending reimbursement claims
        
        Args:
            user_id: User ID
            
        Returns:
            list: List of pending claims
        """
        try:
            with sqlite3.connect(self.db) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                
                c.execute('''
                    SELECT * FROM reimbursement_claims
                    WHERE user_id = ?
                    AND status IN ('pending', 'submitted')
                    ORDER BY submission_date DESC
                ''', (user_id,))
                
                claims = [dict(row) for row in c.fetchall()]
                
                return claims
                
        except Exception as e:
            print(f"❌ Error getting pending claims: {e}")
            return []
    
    def get_total_earnings_ytd(self, user_id, year=None):
        """
        Get year-to-date total earnings from all programs
        
        Args:
            user_id: User ID
            year: Year (defaults to current year)
            
        Returns:
            dict: YTD earnings summary
        """
        try:
            if not year:
                year = datetime.now().year
            
            total_ytd = 0
            monthly_breakdown = []
            
            for month in range(1, 13):
                if year == datetime.now().year and month > datetime.now().month:
                    break
                
                earnings = self.get_monthly_earnings(user_id, month, year)
                monthly_breakdown.append({
                    'month': f"{year}-{month:02d}",
                    'earnings': earnings['total_monthly']
                })
                total_ytd += earnings['total_monthly']
            
            return {
                'user_id': user_id,
                'year': year,
                'total_ytd': total_ytd,
                'monthly_breakdown': monthly_breakdown,
                'average_monthly': total_ytd / len(monthly_breakdown) if monthly_breakdown else 0
            }
            
        except Exception as e:
            print(f"❌ Error calculating YTD earnings: {e}")
            return {'error': str(e), 'total_ytd': 0}


# ==================== USAGE EXAMPLES ====================

if __name__ == "__main__":
    print("🔧 Testing Funding Tracker...\n")
    
    # Initialize tracker
    tracker = FundingTracker()
    
    # Example 1: Track billable event
    print("=" * 50)
    print("Example 1: Track Billable Event")
    print("=" * 50)
    event = tracker.track_billable_event(
        user_id=1,
        event_type='caption',
        duration_seconds=300,
        from_number='+12605551234',
        notes='Emergency plumbing call'
    )
    print(f"Event tracked: {json.dumps(event, indent=2)}\n")
    
    # Example 2: Get monthly earnings
    print("=" * 50)
    print("Example 2: Monthly Earnings")
    print("=" * 50)
    earnings = tracker.get_monthly_earnings(user_id=1)
    print(f"Earnings: {json.dumps(earnings, indent=2)}\n")
    
    # Example 3: Enroll subsidy customer
    print("=" * 50)
    print("Example 3: Enroll Subsidy Customer")
    print("=" * 50)
    enrollment = tracker.enroll_subsidy_customer(
        user_id=1,
        customer_phone='+12605551234',
        program_type='lifeline',
        customer_name='John Smith'
    )
    print(f"Enrollment: {json.dumps(enrollment, indent=2)}\n")
    
    # Example 4: Generate FCC report
    print("=" * 50)
    print("Example 4: Generate FCC Report")
    print("=" * 50)
    report = tracker.generate_fcc_report(user_id=1, month=10, year=2025)
    print(f"FCC Report: {json.dumps(report, indent=2)}\n")
    
    print("✅ All tests complete!")
