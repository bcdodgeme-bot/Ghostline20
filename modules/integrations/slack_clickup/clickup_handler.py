"""
ClickUp API Handler - Environment-Driven Configuration
Handles all ClickUp API interactions for task creation
"""
import os
import aiohttp
import json
from typing import Dict, Optional
from datetime import datetime, timedelta

#--Section 1: Class Initialization & Environment Setup 9/23/25
class ClickUpHandler:
    def __init__(self):
        self.api_token = os.getenv('CLICKUP_API_TOKEN')
        self.user_id = os.getenv('CLICKUP_USER_ID')
        self.amcf_space_id = os.getenv('CLICKUP_AMCF_SPACE_ID')
        self.personal_space_id = os.getenv('CLICKUP_PERSONAL_SPACE_ID')
        self.base_url = "https://api.clickup.com/api/v2"
        
        if not all([self.api_token, self.user_id]):
            print("⚠️  ClickUp API token or user ID not configured")

#--Section 2: HTTP Headers & Authentication 9/23/25
    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for ClickUp API calls"""
        return {
            'Authorization': self.api_token,
            'Content-Type': 'application/json'
        }

#--Section 3: AMCF Task Creation 9/23/25
    async def create_amcf_task(self, title: str, description: str) -> Optional[Dict]:
        """Create a task in AMCF workspace with 3-day due date"""
        if not self.amcf_space_id:
            print("⚠️  AMCF space ID not configured")
            return None
        
        # Set due date to 3 days from now
        due_date = int((datetime.now() + timedelta(days=3)).timestamp() * 1000)
        
        payload = {
            'name': title,
            'description': description,
            'assignees': [self.user_id] if self.user_id else [],
            'due_date': due_date,
            'priority': 2,  # High priority for work tasks
            'status': 'to do'
        }
        
        return await self._create_task_in_space(self.amcf_space_id, payload)

#--Section 4: Personal Task Creation 9/23/25
    async def create_personal_task(self, title: str, description: str) -> Optional[Dict]:
        """Create a task in personal workspace with 5-day due date"""
        if not self.personal_space_id:
            print("⚠️  Personal space ID not configured")
            return None
        
        # Set due date to 5 days from now
        due_date = int((datetime.now() + timedelta(days=5)).timestamp() * 1000)
        
        payload = {
            'name': title,
            'description': description,
            'assignees': [self.user_id] if self.user_id else [],
            'due_date': due_date,
            'priority': 3,  # Normal priority for personal tasks
            'status': 'to do'
        }
        
        return await self._create_task_in_space(self.personal_space_id, payload)

#--Section 5: Core Task Creation Logic 9/23/25
    async def _create_task_in_space(self, space_id: str, payload: Dict) -> Optional[Dict]:
        """Internal method to create task in specified space"""
        if not self.api_token:
            print("⚠️  ClickUp API token not configured")
            return None
        
        try:
            # First, get lists in the space to find default list
            lists_url = f"{self.base_url}/space/{space_id}/list"
            
            async with aiohttp.ClientSession() as session:
                # Get available lists
                async with session.get(lists_url, headers=self._get_headers()) as resp:
                    if resp.status != 200:
                        print(f"❌ Failed to get lists for space {space_id}")
                        return None
                    
                    lists_data = await resp.json()
                    lists = lists_data.get('lists', [])
                    
                    if not lists:
                        print(f"❌ No lists found in space {space_id}")
                        return None
                    
                    # Use first available list
                    list_id = lists[0]['id']
                    
                # Create task in the list
                task_url = f"{self.base_url}/list/{list_id}/task"
                
                async with session.post(task_url, headers=self._get_headers(), json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        task_id = result.get('id')
                        task_url = result.get('url')
                        
                        print(f"✅ Created ClickUp task: {task_id}")
                        return {
                            'id': task_id,
                            'url': task_url,
                            'title': payload['name'],
                            'space_id': space_id,
                            'list_id': list_id
                        }
                    else:
                        error_text = await resp.text()
                        print(f"❌ Failed to create ClickUp task: {resp.status} - {error_text}")
                        return None
                        
        except Exception as e:
            print(f"❌ ClickUp API error: {e}")
            return None

#--Section 6: Utility Methods 9/23/25
    async def test_connection(self) -> bool:
        """Test ClickUp API connection"""
        if not self.api_token:
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                test_url = f"{self.base_url}/user"
                async with session.get(test_url, headers=self._get_headers()) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    def get_configuration(self) -> Dict:
        """Get current configuration status"""
        return {
            'api_token_set': bool(self.api_token),
            'user_id_set': bool(self.user_id),
            'amcf_space_configured': bool(self.amcf_space_id),
            'personal_space_configured': bool(self.personal_space_id)
        }
