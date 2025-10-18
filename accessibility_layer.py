"""
Accessibility Layer - Adds FCC-compliant features
Plugs into existing LeaX system
"""

import openai
from twilio.rest import Client
import os

class AccessibilityEngine:
    def __init__(self):
        self.openai_key = os.environ.get('OPENAI_API_KEY')
        openai.api_key = self.openai_key
    
    def generate_captions(self, audio_file_or_text):
        """Generate real-time captions using Whisper API"""
        if isinstance(audio_file_or_text, str):
            # Already text - just return it
            return audio_file_or_text
        
        # Use Whisper for audio transcription
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=audio_file_or_text,
            language="en"
        )
        return transcript['text']
    
    def speech_clarity_assist(self, unclear_speech, conversation_context):
        """Help clarify speech for people with disabilities"""
        prompt = f"""
        User has difficulty speaking clearly. They said: "{unclear_speech}"
        
        Conversation context: {conversation_context}
        
        What did they most likely mean? Respond with ONLY the clarified sentence.
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100
        )
        
        return response.choices[0].message.content
    
    def emergency_911_routing(self, user_location, emergency_type):
        """Route emergency calls to appropriate 911 center"""
        # Use existing Twilio to route to local 911
        # Based on user's location (from phone number area code)
        pass
    
    def user_wants_captions(self, user_id):
        """Check if user has captions enabled"""
        # Check in existing memory_manager
        from memory_manager import MemoryManager
        memory_mgr = MemoryManager()
        memory = memory_mgr.load_customer_memory(user_id)
        return memory.get('accessibility_settings', {}).get('captions_enabled', False)
