"""
Slack API Handler - Environment-Driven Configuration
Handles all Slack API interactions for the integration
"""
import os
import aiohttp
import hmac
import hashlib
import json
from typing import Dict, List, Optional
from datetime import datetime

#--Section 1: Class Initialization & Environment Setup 9/23/25
class SlackHandler:
    def __init__(self):
        self.bot_token = os.getenv('SLACK_BOT_TOKEN')
        self.signing_secret = os.getenv('SLACK_SIGNING_SECRET')
        self.user_id = os.getenv('SLACK_USER_ID')
        self.base_url = "https://slack.com/api"
        
        if not all([self.bot_token, self.signing_secret, self.user_id]):
            raise ValueError("Missing required Slack environment variables")

#--Section 2: HTTP Headers & Authentication 9/23/25
    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for Slack API calls"""
        return {
            'Authorization': f'Bearer {self.bot_token}',
            'Content-Type': 'application/json'
        }

#--Section 3: Webhook Security & Verification 9/23/25
    def verify_request(self, body: bytes, timestamp: str, signature: str) -> bool:
        """Verify Slack webhook request signature"""
        if abs(int(datetime.now().timestamp()) - int(timestamp)) > 300:
            return False
        
        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        computed_hash = hmac.new(
            self.signing_secret.encode(), 
            sig_basestring.encode(), 
            hashlib.sha256
        ).hexdigest()
        computed_signature = f"v0={computed_hash}"
        
        return hmac.compare_digest(computed_signature, signature)

#--Section 4: Message Context & Thread Handling 9/23/25
    async def get_message_context(self, channel_id: str, message_ts: str) -> Optional[Dict]:
        """Get full message context including thread replies"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/conversations.replies"
            params = {'channel': channel_id, 'ts': message_ts}
            
            async with session.get(url, headers=self._get_headers(), params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('messages', [])
                return None

#--Section 5: User Mention Detection & Parsing 9/23/25
    def extract_mentions(self, message_text: str) -> List[str]:
        """Extract user mentions from message text"""
        import re
        mentions = re.findall(r'<@([A-Z0-9]+)>', message_text)
        return mentions
    
    def is_user_mentioned(self, message_text: str) -> bool:
        """Check if the configured user is mentioned in the message"""
        mentions = self.extract_mentions(message_text)
        return self.user_id in mentions

#--Section 6: Response & Communication 9/23/25
    async def send_response(self, channel_id: str, text: str, thread_ts: str = None) -> bool:
        """Send a response message to Slack"""
        payload = {
            'channel': channel_id,
            'text': text,
            'thread_ts': thread_ts
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat.postMessage", 
                headers=self._get_headers(), 
                json=payload
            ) as resp:
                return resp.status == 200