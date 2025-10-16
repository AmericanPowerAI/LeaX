"""
LeaX AI Agent - Advanced Multi-Tenant Memory System
Automatically creates isolated memory per customer with full conversation tracking
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
    """
    
    def __init__(self, base_memory_dir='customer_memories'):
        self.base_memory_dir = base_memory_dir
        self.master_db = 'master_tracking.db'
        self._init_master_tracking()
        
    def _init_master_tracking(self):
        """Initialize master tracking database"""
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
                    memory_size_kb INTEGER DEFAULT 0
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
                    user_agent TEXT
                )
            ''')
            
            # Message/Call unified tracking
            c.execute('''
                CREATE TABLE IF NOT EXISTS communication_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    communication_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    from_number TEXT,
                    to_number TEXT,
                    content TEXT,
                    duration_seconds INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    lead_id INTEGER,
                    ai_model_used TEXT,
                    tokens_used INTEGER,
                    cost_usd DECIMAL(10,4)
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
        
        # Initialize customer memory structure
        customer_memory = {
            "customer_info": {
                "user_id": user_id,
                "business_name": business_name,
                "email": email,
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "login_count": 0
            },
            "business_profile": {
                "website_url": None,
                "services": [],
                "personality": "professional",
                "custom_info": None,
                "phone_numbers": [],
                "api_keys": {
                    "twilio_sid": None,
                    "twilio_token": None,
                    "openai_key": None
                }
            },
            "conversation_history": [],
            "lead_summaries": [],
            "login_history": [],
            "updates_history": [],
            "analytics": {
                "total_conversations": 0,
                "total_messages": 0,
                "total_calls": 0,
                "leads_captured": 0,
                "conversion_rate": 0.0,
                "avg_response_time_seconds": 0.0,
                "most_common_inquiries": []
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
        
        print(f"✅ Created memory file for {business_name}: {memory_path}")
        return memory_path
    
    def load_customer_memory(self, user_id):
        """Load customer's complete memory"""
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            c.execute('SELECT memory_file_path FROM customer_memories WHERE user_id = ?', (user_id,))
            result = c.fetchone()
            
            if not result:
                return None
            
            memory_path = result[0]
            
            if os.path.exists(memory_path):
                with open(memory_path, 'r') as f:
                    return json.load(f)
            
            return None
    
    def save_customer_memory(self, user_id, memory_data):
        """Save updated memory to file"""
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            c.execute('SELECT memory_file_path FROM customer_memories WHERE user_id = ?', (user_id,))
            result = c.fetchone()
            
            if result:
                memory_path = result[0]
                
                # Update file
                with open(memory_path, 'w') as f:
                    json.dump(memory_data, f, indent=2)
                
                # Update master tracking
                file_size = os.path.getsize(memory_path) // 1024  # KB
                c.execute('''
                    UPDATE customer_memories 
                    SET last_updated = CURRENT_TIMESTAMP, memory_size_kb = ?
                    WHERE user_id = ?
                ''', (file_size, user_id))
                conn.commit()
    
    def log_conversation(self, user_id, conversation_data):
        """
        Log conversation to customer memory AND master tracking
        conversation_data = {
            'type': 'sms' or 'call',
            'direction': 'inbound' or 'outbound',
            'from_number': '+1234567890',
            'to_number': '+0987654321',
            'content': 'message text' or 'call summary',
            'duration': seconds (for calls),
            'lead_id': optional,
            'ai_model': 'gpt-4',
            'tokens': 150,
            'cost': 0.0045
        }
        """
        # Load customer memory
        memory = self.load_customer_memory(user_id)
        if not memory:
            return False
        
        # Add to conversation history
        conversation_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": conversation_data['type'],
            "direction": conversation_data['direction'],
            "from": conversation_data['from_number'],
            "to": conversation_data['to_number'],
            "content": conversation_data['content'],
            "duration_seconds": conversation_data.get('duration', 0),
            "lead_id": conversation_data.get('lead_id'),
            "ai_model": conversation_data.get('ai_model', 'gpt-3.5-turbo'),
            "tokens_used": conversation_data.get('tokens', 0),
            "cost_usd": conversation_data.get('cost', 0.0)
        }
        
        memory['conversation_history'].append(conversation_entry)
        
        # Update analytics
        if conversation_data['type'] == 'sms':
            memory['analytics']['total_messages'] += 1
        elif conversation_data['type'] == 'call':
            memory['analytics']['total_calls'] += 1
        
        memory['analytics']['total_conversations'] += 1
        
        # Save updated memory
        self.save_customer_memory(user_id, memory)
        
        # Log to master communication log
        with sqlite3.connect(self.master_db) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO communication_log
                (user_id, communication_type, direction, from_number, to_number, 
                 content, duration_seconds, lead_id, ai_model_used, tokens_used, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, conversation_data['type'], conversation_data['direction'],
                  conversation_data['from_number'], conversation_data['to_number'],
                  conversation_data['content'], conversation_data.get('duration', 0),
                  conversation_data.get('lead_id'), conversation_data.get('ai_model'),
                  conversation_data.get('tokens', 0), conversation_data.get('cost', 0.0)))
            
            # Update master stats
            if conversation_data['type'] == 'sms':
                c.execute('UPDATE customer_memories SET total_messages = total_messages + 1 WHERE user_id = ?', (user_id,))
            else:
                c.execute('UPDATE customer_memories SET total_calls = total_calls + 1 WHERE user_id = ?', (user_id,))
            
            c.execute('UPDATE customer_memories SET total_conversations = total_conversations + 1 WHERE user_id = ?', (user_id,))
            conn.commit()
        
        return True
    
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
        Update business profile info
        updates = {
            'website_url': 'https://example.com',
            'services': ['service1', 'service2'],
            'personality': 'friendly',
            'custom_info': 'We are...',
            'phone_numbers': ['+1234567890']
        }
        """
        memory = self.load_customer_memory(user_id)
        if not memory:
            return False
        
        for key, value in updates.items():
            if key in memory['business_profile']:
                old_value = memory['business_profile'][key]
                memory['business_profile'][key] = value
                
                # Log the change
                self.log_profile_update(user_id, f"business_profile.{key}", old_value, value)
        
        self.save_customer_memory(user_id, memory)
        return True
    
    def add_api_keys(self, user_id, api_keys):
        """
        Store customer's API keys securely
        api_keys = {
            'twilio_sid': 'ACxxxx',
            'twilio_token': 'xxxx',
            'openai_key': 'sk-xxxx'
        }
        """
        memory = self.load_customer_memory(user_id)
        if not memory:
            return False
        
        for key, value in api_keys.items():
            if value:  # Only update if provided
                memory['business_profile']['api_keys'][key] = value
        
        self.save_customer_memory(user_id, memory)
        return True
    
    def get_conversation_context(self, user_id, phone_number, last_n_messages=10):
        """
        Get recent conversation context for AI prompt
        Returns formatted conversation history
        """
        memory = self.load_customer_memory(user_id)
        if not memory:
            return ""
        
        # Filter conversations with this phone number
        relevant_convos = [
            c for c in memory['conversation_history']
            if c.get('from') == phone_number or c.get('to') == phone_number
        ]
        
        # Get last N
        recent = relevant_convos[-last_n_messages:] if relevant_convos else []
        
        # Format for AI
        context = "CONVERSATION HISTORY:\n"
        for convo in recent:
            direction = "Customer" if convo['direction'] == 'inbound' else "AI Agent"
            context += f"{direction}: {convo['content']}\n"
        
        return context
    
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
        
        return {
            "memory_file": memory,
            "communication_logs": comms,
            "change_logs": changes
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
    
    # Example 3: Log a conversation
    print("\n--- Logging SMS conversation ---")
    memory_mgr.log_conversation(user_id, {
        'type': 'sms',
        'direction': 'inbound',
        'from_number': '+15551234567',
        'to_number': '+15559876543',
        'content': 'I need emergency plumbing help!',
        'lead_id': 456,
        'ai_model': 'gpt-4',
        'tokens': 120,
        'cost': 0.0036
    })
    
    # Example 4: Log a call
    print("\n--- Logging phone call ---")
    memory_mgr.log_conversation(user_id, {
        'type': 'call',
        'direction': 'inbound',
        'from_number': '+15551234567',
        'to_number': '+15559876543',
        'content': 'Customer called about water heater installation. Quoted $1500.',
        'duration': 180,  # 3 minutes
        'lead_id': 456,
        'ai_model': 'gpt-4',
        'tokens': 450,
        'cost': 0.0135
    })
    
    # Example 5: Track login
    print("\n--- Logging user login ---")
    memory_mgr.log_login(user_id, ip_address='192.168.1.1', user_agent='Mozilla/5.0')
    
    # Example 6: Get conversation context for AI
    print("\n--- Getting conversation context ---")
    context = memory_mgr.get_conversation_context(user_id, '+15551234567')
    print(context)
    
    # Example 7: Get analytics
    print("\n--- Getting customer analytics ---")
    analytics = memory_mgr.get_customer_analytics(user_id)
    print(json.dumps(analytics, indent=2))
    
    # Example 8: Get platform stats
    print("\n--- Getting platform-wide stats ---")
    stats = memory_mgr.get_total_usage_stats()
    print(json.dumps(stats, indent=2))
    
    # Example 9: Export customer data
    print("\n--- Exporting customer data ---")
    export = memory_mgr.export_all_customer_data(user_id)
    print(f"Exported {len(export['communication_logs'])} communications")
    print(f"Exported {len(export['change_logs'])} profile changes")
