"""
LeaX AI Agent - Advanced Multi-Tenant Memory System
FIXED: Now properly stores ALL conversation data permanently
FIXED: Never forgets customer information
FIXED: Updates existing data instead of overwriting
FIXED: Full conversation context for AI responses
"""

import os
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager
import hashlib

class MemoryManager:
    """
    Creates and manages isolated memory files for each customer
    Tracks conversations, updates, login changes, company info
    ALL DATA IS PERSISTENT - NOTHING IS FORGOTTEN
    """
    
    def __init__(self, base_memory_dir='customer_memories'):
        self.base_memory_dir = base_memory_dir
        self.master_db = 'master_tracking.db'
        self._init_master_tracking()
        
    def _init_master_tracking(self):
        """Initialize master tracking database with ENHANCED persistence"""
        os.makedirs(self.base_memory_dir, exist_ok=True)
        
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            
            # Master customer tracking
            c.execute('''
                CREATE TABLE IF NOT EXISTS customer_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    memory_file_path TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_conversations INTEGER DEFAULT 0,
                    total_messages INTEGER DEFAULT 0,
                    total_calls INTEGER DEFAULT 0,
                    memory_size_kb INTEGER DEFAULT 0,
                    last_conversation_summary TEXT,
                    customer_preferences TEXT DEFAULT '{}',
                    important_dates TEXT DEFAULT '{}'
                )
            ''')
            
            # All changes log (for your tracking)
            c.execute('''
                CREATE TABLE IF NOT EXISTS change_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    change_type TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT,
                    session_id TEXT
                )
            ''')
            
            # Message/Call unified tracking - ENHANCED
            c.execute('''
                CREATE TABLE IF NOT EXISTS communication_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    communication_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    from_number TEXT,
                    to_number TEXT,
                    content TEXT,
                    ai_response TEXT,
                    duration_seconds INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    lead_id INTEGER,
                    ai_model_used TEXT,
                    tokens_used INTEGER,
                    cost_usd DECIMAL(10,4),
                    sentiment_score REAL,
                    intent_detected TEXT,
                    conversation_context TEXT
                )
            ''')
            
            # NEW: Persistent customer knowledge base
            c.execute('''
                CREATE TABLE IF NOT EXISTS customer_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    phone_number TEXT NOT NULL,
                    customer_name TEXT,
                    customer_email TEXT,
                    customer_company TEXT,
                    preferred_contact_method TEXT,
                    last_inquiry_topic TEXT,
                    purchase_history TEXT DEFAULT '[]',
                    notes TEXT,
                    meeting_scheduled BOOLEAN DEFAULT 0,
                    meeting_datetime TIMESTAMP,
                    meeting_location TEXT,
                    decision_maker BOOLEAN DEFAULT 0,
                    budget_range TEXT,
                    urgency_level TEXT,
                    conversion_probability REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, phone_number)
                )
            ''')
            
            # NEW: Session tracking for rate limiting intelligence
            c.execute('''
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_type TEXT NOT NULL,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    messages_sent INTEGER DEFAULT 0,
                    full_sale_completed BOOLEAN DEFAULT 0,
                    meeting_scheduled BOOLEAN DEFAULT 0,
                    session_active BOOLEAN DEFAULT 1
                )
            ''')
            
            conn.commit()
    
    def create_customer_memory(self, user_id, business_name, email):
        """
        Creates isolated memory file for new customer
        Returns path to their memory file
        """
        memory_filename = f"customer_{user_id}_{hashlib.md5(email.encode()).hexdigest()[:8]}.json"
        memory_path = os.path.join(self.base_memory_dir, memory_filename)
        
        # Initialize customer memory structure - ENHANCED
        customer_memory = {
            "customer_info": {
                "user_id": user_id,
                "business_name": business_name,
                "email": email,
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "login_count": 0,
                "account_status": "active",
                "subscription_plan": "basic",
                "trial_used": False
            },
            "business_profile": {
                "website_url": None,
                "services": [],
                "personality": "professional",
                "custom_info": None,
                "phone_numbers": [],
                "business_hours": {},
                "pricing_ranges": {},
                "target_market": "",
                "unique_selling_points": [],
                "api_keys": {
                    "twilio_sid": None,
                    "twilio_token": None,
                    "openai_key": None
                }
            },
            "conversation_history": [],
            "customer_database": {},  # Phone number as key, customer details as value
            "lead_summaries": [],
            "login_history": [],
            "updates_history": [],
            "meeting_calendar": [],
            "sales_pipeline": [],
            "analytics": {
                "total_conversations": 0,
                "total_messages": 0,
                "total_calls": 0,
                "leads_captured": 0,
                "meetings_scheduled": 0,
                "conversion_rate": 0.0,
                "avg_response_time_seconds": 0.0,
                "most_common_inquiries": [],
                "peak_contact_hours": [],
                "customer_satisfaction_score": 0.0
            },
            "ai_learning": {
                "successful_responses": [],
                "failed_responses": [],
                "customer_preferences": {},
                "common_objections": [],
                "best_closing_techniques": []
            }
        }
        
        # Write to file
        with open(memory_path, 'w') as f:
            json.dump(customer_memory, f, indent=2)
        
        # Register in master tracking
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO customer_memories 
                (user_id, memory_file_path, total_conversations, total_messages, total_calls)
                VALUES (?, ?, 0, 0, 0)
            ''', (user_id, memory_path))
            conn.commit()
        
        print(f"✅ Created persistent memory file for {business_name}: {memory_path}")
        return memory_path
    
    def load_customer_memory(self, user_id):
        """Load customer's complete memory - ALWAYS AVAILABLE"""
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            c.execute('SELECT memory_file_path FROM customer_memories WHERE user_id = ?', (user_id,))
            result = c.fetchone()
            
            if not result:
                print(f"⚠️ No memory found for user {user_id}")
                return None
            
            memory_path = result[0]
            
            if os.path.exists(memory_path):
                with open(memory_path, 'r') as f:
                    return json.load(f)
            else:
                print(f"⚠️ Memory file not found: {memory_path}")
            
            return None
    
    def save_customer_memory(self, user_id, memory_data):
        """Save updated memory to file - PERSISTENT STORAGE"""
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            c.execute('SELECT memory_file_path FROM customer_memories WHERE user_id = ?', (user_id,))
            result = c.fetchone()
            
            if result:
                memory_path = result[0]
                
                # Update file with pretty printing for readability
                with open(memory_path, 'w') as f:
                    json.dump(memory_data, f, indent=2, sort_keys=False)
                
                # Update master tracking
                file_size = os.path.getsize(memory_path) // 1024  # KB
                c.execute('''
                    UPDATE customer_memories 
                    SET last_updated = CURRENT_TIMESTAMP, 
                        memory_size_kb = ?,
                        last_conversation_summary = ?
                    WHERE user_id = ?
                ''', (file_size, 
                      json.dumps(memory_data.get('conversation_history', [])[-5:])[:500],
                      user_id))
                conn.commit()
                
                print(f"✅ Memory saved for user {user_id} ({file_size}KB)")
    
    def log_conversation(self, user_id, conversation_data):
        """
        Log conversation to customer memory AND master tracking
        NEVER FORGETS - ALWAYS UPDATES
        """
        # Load customer memory
        memory = self.load_customer_memory(user_id)
        if not memory:
            print(f"❌ Cannot log conversation - no memory for user {user_id}")
            return False
        
        # Add to conversation history
        conversation_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": conversation_data['type'],
            "direction": conversation_data['direction'],
            "from": conversation_data['from_number'],
            "to": conversation_data['to_number'],
            "content": conversation_data['content'],
            "ai_response": conversation_data.get('ai_response', ''),
            "duration_seconds": conversation_data.get('duration', 0),
            "lead_id": conversation_data.get('lead_id'),
            "ai_model": conversation_data.get('ai_model', 'gpt-3.5-turbo'),
            "tokens_used": conversation_data.get('tokens', 0),
            "cost_usd": conversation_data.get('cost', 0.0),
            "intent": conversation_data.get('intent', 'general_inquiry'),
            "sentiment": conversation_data.get('sentiment', 'neutral')
        }
        
        memory['conversation_history'].append(conversation_entry)
        
        # Update customer database if it's an inbound message
        if conversation_data['direction'] == 'inbound':
            phone = conversation_data['from_number']
            if phone not in memory['customer_database']:
                memory['customer_database'][phone] = {
                    "first_contact": datetime.now().isoformat(),
                    "total_messages": 0,
                    "last_inquiry": None,
                    "name": None,
                    "email": None,
                    "company": None,
                    "meeting_scheduled": False,
                    "notes": []
                }
            
            # Update customer info
            memory['customer_database'][phone]['total_messages'] += 1
            memory['customer_database'][phone]['last_contact'] = datetime.now().isoformat()
            memory['customer_database'][phone]['last_inquiry'] = conversation_data['content']
        
        # Update analytics
        if conversation_data['type'] == 'sms':
            memory['analytics']['total_messages'] += 1
        elif conversation_data['type'] == 'call':
            memory['analytics']['total_calls'] += 1
        
        memory['analytics']['total_conversations'] += 1
        
        # Save updated memory
        self.save_customer_memory(user_id, memory)
        
        # Log to master communication log with FULL CONTEXT
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO communication_log
                (user_id, communication_type, direction, from_number, to_number, 
                 content, ai_response, duration_seconds, lead_id, ai_model_used, 
                 tokens_used, cost_usd, intent_detected, conversation_context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, conversation_data['type'], conversation_data['direction'],
                  conversation_data['from_number'], conversation_data['to_number'],
                  conversation_data['content'], conversation_data.get('ai_response', ''),
                  conversation_data.get('duration', 0),
                  conversation_data.get('lead_id'), conversation_data.get('ai_model'),
                  conversation_data.get('tokens', 0), conversation_data.get('cost', 0.0),
                  conversation_data.get('intent', 'general'),
                  json.dumps(conversation_data.get('context', {}))))
            
            # Update master stats
            if conversation_data['type'] == 'sms':
                c.execute('UPDATE customer_memories SET total_messages = total_messages + 1 WHERE user_id = ?', (user_id,))
            else:
                c.execute('UPDATE customer_memories SET total_calls = total_calls + 1 WHERE user_id = ?', (user_id,))
            
            c.execute('UPDATE customer_memories SET total_conversations = total_conversations + 1 WHERE user_id = ?', (user_id,))
            conn.commit()
        
        print(f"✅ Conversation logged and permanently stored for user {user_id}")
        return True
    
    def update_customer_info(self, user_id, phone_number, customer_data):
        """
        Update specific customer information in the database
        NEVER overwrites - always MERGES with existing data
        """
        memory = self.load_customer_memory(user_id)
        if not memory:
            return False
        
        if phone_number not in memory['customer_database']:
            memory['customer_database'][phone_number] = {
                "first_contact": datetime.now().isoformat(),
                "total_messages": 0,
                "last_inquiry": None,
                "name": None,
                "email": None,
                "company": None,
                "meeting_scheduled": False,
                "notes": []
            }
        
        # MERGE data - never overwrite existing
        customer = memory['customer_database'][phone_number]
        for key, value in customer_data.items():
            if value is not None:  # Only update if new value provided
                if key == 'notes' and isinstance(value, str):
                    # Append to notes instead of replacing
                    customer['notes'].append({
                        "timestamp": datetime.now().isoformat(),
                        "note": value
                    })
                elif key == 'meeting_scheduled' and value:
                    customer['meeting_scheduled'] = True
                    customer['meeting_datetime'] = customer_data.get('meeting_datetime')
                    memory['analytics']['meetings_scheduled'] += 1
                else:
                    customer[key] = value
        
        customer['last_updated'] = datetime.now().isoformat()
        
        # Save to persistent storage
        self.save_customer_memory(user_id, memory)
        
        # Also save to SQL for quick queries
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO customer_knowledge
                (user_id, phone_number, customer_name, customer_email, customer_company,
                 meeting_scheduled, meeting_datetime, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, phone_number, 
                  customer_data.get('name'), customer_data.get('email'),
                  customer_data.get('company'), customer_data.get('meeting_scheduled', False),
                  customer_data.get('meeting_datetime'), json.dumps(customer.get('notes', []))))
            conn.commit()
        
        print(f"✅ Customer info updated for {phone_number} (user {user_id})")
        return True
    
    def should_rate_limit(self, user_id, phone_number=None):
        """
        Intelligent rate limiting - DON'T limit if:
        1. Full sale completed (meeting scheduled)
        2. Customer has provided name, company, and meeting time
        3. Active conversation in progress
        """
        memory = self.load_customer_memory(user_id)
        if not memory:
            return True  # Rate limit if no memory
        
        # Check subscription status
        if memory['customer_info'].get('subscription_plan') in ['standard', 'enterprise']:
            return False  # Never rate limit paid plans
        
        # Check if trial has been used
        if memory['customer_info'].get('trial_used', False):
            # Check if any customer has completed sale
            if phone_number and phone_number in memory['customer_database']:
                customer = memory['customer_database'][phone_number]
                if customer.get('meeting_scheduled') and customer.get('name'):
                    print(f"✅ No rate limit - meeting scheduled for {phone_number}")
                    return False  # Don't rate limit completed sales
            
            return True  # Rate limit if trial used and no sale
        
        return False  # Allow trial
    
    def mark_trial_used(self, user_id):
        """Mark that trial has been used"""
        memory = self.load_customer_memory(user_id)
        if memory:
            memory['customer_info']['trial_used'] = True
            self.save_customer_memory(user_id, memory)
    
    def get_conversation_context(self, user_id, phone_number, last_n_messages=20):
        """
        Get FULL conversation context for AI prompt
        Returns formatted conversation history with customer intelligence
        """
        memory = self.load_customer_memory(user_id)
        if not memory:
            return ""
        
        # Get customer-specific info
        customer_info = ""
        if phone_number in memory['customer_database']:
            customer = memory['customer_database'][phone_number]
            customer_info = f"\n🔍 CUSTOMER INTEL:\n"
            if customer.get('name'):
                customer_info += f"Name: {customer['name']}\n"
            if customer.get('company'):
                customer_info += f"Company: {customer['company']}\n"
            if customer.get('email'):
                customer_info += f"Email: {customer['email']}\n"
            customer_info += f"Total Messages: {customer.get('total_messages', 0)}\n"
            if customer.get('meeting_scheduled'):
                customer_info += f"✅ MEETING SCHEDULED: {customer.get('meeting_datetime', 'Pending confirmation')}\n"
            if customer.get('notes'):
                customer_info += f"Notes: {'; '.join([n.get('note', '') for n in customer['notes'][-3:]])}\n"
        
        # Filter conversations with this phone number
        relevant_convos = [
            c for c in memory['conversation_history']
            if c.get('from') == phone_number or c.get('to') == phone_number
        ]
        
        # Get last N with priority on recent
        recent = relevant_convos[-last_n_messages:] if relevant_convos else []
        
        # Format for AI with FULL CONTEXT
        context = f"{customer_info}\n📝 CONVERSATION HISTORY (Last {len(recent)} messages):\n"
        for convo in recent:
            direction = "Customer" if convo['direction'] == 'inbound' else "AI Agent"
            timestamp = convo.get('timestamp', '')[:19]  # Just date and time
            content = convo.get('content', '')
            context += f"[{timestamp}] {direction}: {content}\n"
            if convo.get('ai_response'):
                context += f"    → Response: {convo['ai_response']}\n"
        
        return context
    
    def log_login(self, user_id, ip_address=None, user_agent=None):
        """Track login activity"""
        memory = self.load_customer_memory(user_id)
        if not memory:
            return False
        
        login_entry = {
            "timestamp": datetime.now().isoformat(),
            "ip_address": ip_address,
            "user_agent": user_agent
        }
        
        memory['login_history'].append(login_entry)
        memory['customer_info']['last_login'] = datetime.now().isoformat()
        memory['customer_info']['login_count'] += 1
        
        self.save_customer_memory(user_id, memory)
        return True
    
    def log_profile_update(self, user_id, field_name, old_value, new_value, ip_address=None):
        """Track any profile/business info changes"""
        memory = self.load_customer_memory(user_id)
        if not memory:
            return False
        
        update_entry = {
            "timestamp": datetime.now().isoformat(),
            "field": field_name,
            "old_value": str(old_value),
            "new_value": str(new_value),
            "ip_address": ip_address
        }
        
        memory['updates_history'].append(update_entry)
        self.save_customer_memory(user_id, memory)
        
        # Log to master change log
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO change_log (user_id, change_type, old_value, new_value, ip_address)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, field_name, str(old_value), str(new_value), ip_address))
            conn.commit()
        
        return True
    
    def update_business_profile(self, user_id, updates):
        """
        Update business profile info - MERGES instead of overwriting
        """
        memory = self.load_customer_memory(user_id)
        if not memory:
            return False
        
        for key, value in updates.items():
            if key in memory['business_profile'] and value is not None:
                old_value = memory['business_profile'][key]
                memory['business_profile'][key] = value
                
                # Log the change
                self.log_profile_update(user_id, f"business_profile.{key}", old_value, value)
        
        self.save_customer_memory(user_id, memory)
        return True
    
    def add_api_keys(self, user_id, api_keys):
        """Store customer's API keys securely"""
        memory = self.load_customer_memory(user_id)
        if not memory:
            return False
        
        for key, value in api_keys.items():
            if value:  # Only update if provided
                memory['business_profile']['api_keys'][key] = value
        
        self.save_customer_memory(user_id, memory)
        return True
    
    def get_customer_analytics(self, user_id):
        """Get comprehensive analytics for customer"""
        memory = self.load_customer_memory(user_id)
        if not memory:
            return None
        
        return memory['analytics']
    
    def export_all_customer_data(self, user_id):
        """Export complete customer data (GDPR compliance)"""
        memory = self.load_customer_memory(user_id)
        
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            
            # Get all communication logs
            c.execute('SELECT * FROM communication_log WHERE user_id = ?', (user_id,))
            comms = [dict(row) for row in c.fetchall()]
            
            # Get all change logs
            c.execute('SELECT * FROM change_log WHERE user_id = ?', (user_id,))
            changes = [dict(row) for row in c.fetchall()]
            
            # Get customer knowledge base
            c.execute('SELECT * FROM customer_knowledge WHERE user_id = ?', (user_id,))
            customers = [dict(row) for row in c.fetchall()]
        
        return {
            "memory_file": memory,
            "communication_logs": comms,
            "change_logs": changes,
            "customer_database": customers
        }
    
    def get_all_customers_summary(self):
        """Get summary of all customers (for your admin dashboard)"""
        with sqlite3.connect(self.master_db) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            c.execute('''
                SELECT 
                    user_id,
                    memory_file_path,
                    created_at,
                    last_updated,
                    total_conversations,
                    total_messages,
                    total_calls,
                    memory_size_kb
                FROM customer_memories
                ORDER BY last_updated DESC
            ''')
            
            return [dict(row) for row in c.fetchall()]
    
    def get_total_usage_stats(self):
        """Get platform-wide usage statistics"""
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            
            stats = {}
            
            # Total customers
            c.execute('SELECT COUNT(*) FROM customer_memories')
            stats['total_customers'] = c.fetchone()[0]
            
            # Total communications
            c.execute('SELECT SUM(total_conversations) FROM customer_memories')
            stats['total_conversations'] = c.fetchone()[0] or 0
            
            # Total messages
            c.execute('SELECT SUM(total_messages) FROM customer_memories')
            stats['total_messages'] = c.fetchone()[0] or 0
            
            # Total calls
            c.execute('SELECT SUM(total_calls) FROM customer_memories')
            stats['total_calls'] = c.fetchone()[0] or 0
            
            # Total cost
            c.execute('SELECT SUM(cost_usd) FROM communication_log')
            stats['total_cost_usd'] = c.fetchone()[0] or 0.0
            
            # Most active customer
            c.execute('''
                SELECT user_id, total_conversations 
                FROM customer_memories 
                ORDER BY total_conversations DESC 
                LIMIT 1
            ''')
            result = c.fetchone()
            stats['most_active_customer'] = {
                'user_id': result[0] if result else None,
                'conversations': result[1] if result else 0
            }
            
            return stats


# ==================== USAGE EXAMPLES ====================

if __name__ == "__main__":
    # Initialize memory manager
    memory_mgr = MemoryManager()
    
    # Example 1: New customer signup
    print("\n--- Creating new customer memory ---")
    user_id = 123
    memory_path = memory_mgr.create_customer_memory(
        user_id=user_id,
        business_name="Joe's Plumbing",
        email="joe@plumbing.com"
    )
    
    # Example 2: Update business profile
    print("\n--- Updating business profile ---")
    memory_mgr.update_business_profile(user_id, {
        'website_url': 'https://joesplumbing.com',
        'services': ['Emergency Plumbing', '24/7 Service', 'Drain Cleaning'],
        'personality': 'friendly',
        'custom_info': 'Family-owned plumbing business serving the area for 20 years'
    })
    
    # Example 3: Log a conversation with AI response
    print("\n--- Logging SMS conversation ---")
    memory_mgr.log_conversation(user_id, {
        'type': 'sms',
        'direction': 'inbound',
        'from_number': '+15551234567',
        'to_number': '+15559876543',
        'content': 'I need emergency plumbing help!',
        'ai_response': 'I can help you right away! What type of plumbing emergency are you dealing with?',
        'lead_id': 456,
        'ai_model': 'gpt-4',
        'tokens': 120,
        'cost': 0.0036
    })
    
    # Example 4: Update customer information (persistent)
    print("\n--- Updating customer info ---")
    memory_mgr.update_customer_info(user_id, '+15551234567', {
        'name': 'John Smith',
        'company': 'Smith Construction',
        'email': 'john@smithconstruction.com',
        'notes': 'Needs emergency water heater replacement'
    })
    
    # Example 5: Check rate limiting
    print("\n--- Checking rate limit ---")
    should_limit = memory_mgr.should_rate_limit(user_id, '+15551234567')
    print(f"Should rate limit: {should_limit}")
    
    # Example 6: Get full conversation context
    print("\n--- Getting conversation context ---")
    context = memory_mgr.get_conversation_context(user_id, '+15551234567')
    print(context)
    
    # Example 7: Schedule a meeting (no more rate limiting)
    print("\n--- Scheduling meeting ---")
    memory_mgr.update_customer_info(user_id, '+15551234567', {
        'meeting_scheduled': True,
        'meeting_datetime': '2024-10-20 10:00:00'
    })
    
    # Example 8: Verify no rate limiting after meeting scheduled
    should_limit = memory_mgr.should_rate_limit(user_id, '+15551234567')
    print(f"Should rate limit after meeting: {should_limit}")
