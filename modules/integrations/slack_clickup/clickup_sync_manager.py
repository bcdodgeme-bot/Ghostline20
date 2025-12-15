# modules/integrations/slack_clickup/clickup_sync_manager.py
"""
ClickUp Sync Manager
Syncs tasks FROM ClickUp API into local database for notifications

Updated: Session 13 - Converted to db_manager pattern, added singleton getter
"""

import os
import aiohttp
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
from uuid import UUID

from ...core.database import db_manager

logger = logging.getLogger(__name__)

#--Section 1: Singleton Pattern
_sync_manager_instance: Optional['ClickUpSyncManager'] = None

def get_clickup_sync_manager() -> 'ClickUpSyncManager':
    """Get singleton ClickUpSyncManager instance"""
    global _sync_manager_instance
    if _sync_manager_instance is None:
        _sync_manager_instance = ClickUpSyncManager()
    return _sync_manager_instance


#--Section 2: Class Definition & Initialization
class ClickUpSyncManager:
    """Syncs ClickUp tasks to local database for notification system"""
    
    def __init__(self):
        self.api_token = os.getenv('CLICKUP_API_TOKEN')
        self.user_id = os.getenv('CLICKUP_USER_ID')
        self.amcf_space_id = os.getenv('CLICKUP_AMCF_SPACE_ID')
        self.personal_space_id = os.getenv('CLICKUP_PERSONAL_SPACE_ID')
        self.base_url = "https://api.clickup.com/api/v2"
        
        # Carl's user UUID (from database inspection)
        self.carl_user_uuid = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
        
        if not self.api_token:
            logger.error("⚠️ ClickUp API token not configured")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for ClickUp API calls"""
        return {
            'Authorization': self.api_token,
            'Content-Type': 'application/json'
        }
    
    #--Section 3: Main Sync Entry Point
    async def sync_all_tasks(self) -> Dict[str, Any]:
        """
        Sync tasks from both AMCF and Personal workspaces
        
        Returns:
            Dict with sync statistics
        """
        logger.info("🔄 Starting ClickUp task sync...")
        
        stats = {
            'tasks_synced': 0,
            'tasks_new': 0,
            'tasks_updated': 0,
            'amcf_tasks': 0,
            'personal_tasks': 0,
            'errors': []
        }
        
        try:
            # Sync AMCF workspace
            if self.amcf_space_id:
                amcf_result = await self._sync_space_tasks(
                    space_id=self.amcf_space_id,
                    workspace_name='AMCF'
                )
                stats['amcf_tasks'] = amcf_result['synced']
                stats['tasks_synced'] += amcf_result['synced']
                stats['tasks_new'] += amcf_result['new']
                stats['tasks_updated'] += amcf_result['updated']
            
            # Sync Personal workspace
            if self.personal_space_id:
                personal_result = await self._sync_space_tasks(
                    space_id=self.personal_space_id,
                    workspace_name='Personal'
                )
                stats['personal_tasks'] = personal_result['synced']
                stats['tasks_synced'] += personal_result['synced']
                stats['tasks_new'] += personal_result['new']
                stats['tasks_updated'] += personal_result['updated']
            
            logger.info(f"✅ ClickUp sync complete: {stats['tasks_synced']} tasks total "
                       f"({stats['tasks_new']} new, {stats['tasks_updated']} updated)")
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ ClickUp sync failed: {e}")
            stats['errors'].append(str(e))
            return stats
    
    #--Section 4: Space-Level Sync
    async def _sync_space_tasks(self, space_id: str, workspace_name: str) -> Dict[str, int]:
        """
        Sync tasks from a specific ClickUp space
        
        Args:
            space_id: ClickUp space ID
            workspace_name: Human-readable workspace name (for logging)
        
        Returns:
            Dict with sync counts
        """
        result = {'synced': 0, 'new': 0, 'updated': 0}
        
        try:
            # Fetch tasks from ClickUp API
            tasks = await self._fetch_space_tasks(space_id)
            
            if not tasks:
                logger.warning(f"⚠️ No tasks found in {workspace_name} workspace")
                return result
            
            logger.info(f"📥 Fetched {len(tasks)} tasks from {workspace_name}")
            
            # Store tasks in database
            for task in tasks:
                was_new = await self._store_task(task, workspace_name)
                if was_new:
                    result['new'] += 1
                else:
                    result['updated'] += 1
                result['synced'] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to sync {workspace_name} workspace: {e}")
            return result
    
    #--Section 5: ClickUp API Fetch
    async def _fetch_space_tasks(self, space_id: str) -> List[Dict]:
        """
        Fetch all tasks from a ClickUp space
        
        Args:
            space_id: ClickUp space ID
        
        Returns:
            List of task dictionaries
        """
        if not self.api_token:
            logger.error("❌ No ClickUp API token configured")
            return []
        
        try:
            async with aiohttp.ClientSession() as session:
                # Get all lists in the space
                lists_url = f"{self.base_url}/space/{space_id}/list"
                
                async with session.get(lists_url, headers=self._get_headers()) as resp:
                    if resp.status != 200:
                        logger.error(f"❌ Failed to fetch lists: {resp.status}")
                        return []
                    
                    lists_data = await resp.json()
                    lists = lists_data.get('lists', [])
                    
                    if not lists:
                        logger.warning(f"⚠️ No lists found in space {space_id}")
                        return []
                
                # Fetch tasks from each list
                all_tasks = []
                
                for list_item in lists:
                    list_id = list_item['id']
                    list_name = list_item.get('name', 'Unnamed List')
                    
                    # Get tasks from this list
                    tasks_url = f"{self.base_url}/list/{list_id}/task"
                    params = {
                        'archived': 'false',  # Only get active tasks
                        'include_closed': 'true'  # But include completed ones for tracking
                    }
                    
                    async with session.get(tasks_url, headers=self._get_headers(), params=params) as resp:
                        if resp.status == 200:
                            tasks_data = await resp.json()
                            tasks = tasks_data.get('tasks', [])
                            
                            # Add list context to each task
                            for task in tasks:
                                task['list_name'] = list_name
                                task['space_id'] = space_id
                            
                            all_tasks.extend(tasks)
                            logger.info(f"   📋 {list_name}: {len(tasks)} tasks")
                        else:
                            logger.error(f"❌ Failed to fetch tasks from list {list_name}: {resp.status}")
                
                return all_tasks
                
        except Exception as e:
            logger.error(f"❌ ClickUp API error: {e}")
            return []
    
    #--Section 6: Database Storage (Using db_manager)
    async def _store_task(self, task_data: Dict, workspace_name: str) -> bool:
        """
        Store or update task in database using db_manager
        
        Args:
            task_data: Task data from ClickUp API
            workspace_name: Workspace name (AMCF or Personal)
        
        Returns:
            True if new task was created, False if existing task was updated
        """
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            clickup_task_id = task_data['id']
            
            # Check if task already exists
            existing = await conn.fetchrow(
                'SELECT id FROM clickup_tasks WHERE clickup_task_id = $1',
                clickup_task_id
            )
            
            # Parse task data
            task_name = task_data.get('name', 'Untitled Task')
            task_description = task_data.get('description', '')
            status = task_data.get('status', {}).get('status', 'open')
            priority_obj = task_data.get('priority')
            priority = None
            if priority_obj:
                priority_str = priority_obj.get('priority', '').lower() if isinstance(priority_obj, dict) else str(priority_obj).lower()
                priority_map = {
                    'urgent': 1,
                    'high': 2,
                    'normal': 3,
                    'low': 4
                }
                priority = priority_map.get(priority_str)
            
            # Parse due date (ClickUp uses millisecond timestamps)
            due_date = None
            if task_data.get('due_date'):
                due_date = datetime.fromtimestamp(int(task_data['due_date']) / 1000)
            
            # Parse assignees
            import json
            assignees_list = [
                assignee.get('username', assignee.get('email', 'Unknown'))
                for assignee in task_data.get('assignees', [])
            ]
            assignees = json.dumps(assignees_list)  # Convert to JSON string for JSONB
            
            # Parse tags
            tags_list = [tag.get('name', '') for tag in task_data.get('tags', [])]
            tags = json.dumps(tags_list)  # Convert to JSON string for JSONB
            
            # List and space info
            list_id = task_data.get('list', {}).get('id')
            list_name = task_data.get('list_name', '')
            space_id = task_data.get('space_id', '')
            space_name = workspace_name
            
            # Task URL
            url = task_data.get('url', '')
            
            # Completed timestamp
            completed_at = None
            if task_data.get('date_closed'):
                completed_at = datetime.fromtimestamp(int(task_data['date_closed']) / 1000)
            
            if existing:
                # Update existing task
                await conn.execute('''
                    UPDATE clickup_tasks SET
                        task_name = $1,
                        task_description = $2,
                        status = $3,
                        priority = $4,
                        due_date = $5,
                        assignees = $6,
                        tags = $7,
                        list_id = $8,
                        list_name = $9,
                        space_id = $10,
                        space_name = $11,
                        url = $12,
                        completed_at = $13,
                        last_synced = NOW(),
                        updated_at = NOW()
                    WHERE clickup_task_id = $14
                ''', task_name, task_description, status, priority, due_date,
                    assignees, tags, list_id, list_name, space_id, space_name,
                    url, completed_at, clickup_task_id)
                
                return False  # Existing task updated
            else:
                # Insert new task
                await conn.execute('''
                    INSERT INTO clickup_tasks (
                        user_id, clickup_task_id, task_name, task_description,
                        status, priority, due_date, assignees, tags,
                        list_id, list_name, space_id, space_name, url,
                        completed_at, last_synced, created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                        NOW(), NOW(), NOW()
                    )
                ''', self.carl_user_uuid, clickup_task_id, task_name, task_description,
                    status, priority, due_date, assignees, tags,
                    list_id, list_name, space_id, space_name, url, completed_at)
                
                return True  # New task created
            
        except Exception as e:
            logger.error(f"Failed to store task {task_data.get('id', 'unknown')}: {e}")
            return False
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    #--Section 7: Utility Methods
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
