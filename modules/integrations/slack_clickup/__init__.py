"""
Slack-ClickUp Integration Module
Provides seamless task creation from Slack mentions and AI commands

Updated: Session 13 - Added missing logger, updated to use singleton getters

Module Structure:
- slack_handler.py: Slack API interactions and webhook verification
- clickup_handler.py: ClickUp task creation and space management  
- clickup_sync_manager.py: Syncs ClickUp tasks to local database
- task_mapper.py: Business logic for mapping messages to tasks
- router.py: FastAPI endpoints for webhooks and manual controls

Workflow:
1. Slack mentions → AMCF workspace tasks (3-day due date)
2. AI commands → Personal workspace tasks (5-day due date)
"""

import os
import logging

logger = logging.getLogger(__name__)

#--Section 1: Module Exports & Public API
from .slack_handler import SlackHandler
from .clickup_handler import ClickUpHandler
from .clickup_sync_manager import ClickUpSyncManager, get_clickup_sync_manager
from .task_mapper import TaskMapper
from .router import router, get_slack_handler, get_clickup_handler, get_task_mapper

# Public API - what other modules can import
__all__ = [
    # Classes
    'SlackHandler',
    'ClickUpHandler',
    'ClickUpSyncManager',
    'TaskMapper',
    # Router
    'router',
    # Singleton getters
    'get_slack_handler',
    'get_clickup_handler',
    'get_clickup_sync_manager',
    'get_task_mapper',
]

#--Section 2: Module Metadata & Configuration
__version__ = '1.1.0'  # Bumped for Session 13 fixes
__author__ = 'Syntax Prime V2'
__description__ = 'Slack to ClickUp task automation integration'

# Module configuration constants
MODULE_NAME = 'slack_clickup'
INTEGRATION_TYPE = 'webhook'
SUPPORTED_EVENTS = ['app_mention', 'message']
REQUIRED_SCOPES = ['chat:write', 'app_mentions:read']

#--Section 3: Module Initialization & Health Checks
def check_module_health() -> dict:
    """Check if all required environment variables are configured"""
    
    required_vars = {
        'slack': [
            'SLACK_BOT_TOKEN',
            'SLACK_SIGNING_SECRET',
            'SLACK_USER_ID'
        ],
        'clickup': [
            'CLICKUP_API_TOKEN',
            'CLICKUP_USER_ID',
            'CLICKUP_AMCF_SPACE_ID',
            'CLICKUP_PERSONAL_SPACE_ID'
        ]
    }
    
    status = {'healthy': True, 'missing_vars': [], 'configured_vars': []}
    
    for service, vars_list in required_vars.items():
        for var in vars_list:
            if os.getenv(var):
                status['configured_vars'].append(var)
            else:
                status['missing_vars'].append(var)
                status['healthy'] = False
    
    return status


def get_integration_info() -> dict:
    """Get module information and configuration"""
    
    return {
        'module': MODULE_NAME,
        'version': __version__,
        'type': INTEGRATION_TYPE,
        'description': __description__,
        'endpoints': {
            'slack_events': '/integrations/slack-clickup/slack/events',
            'slack_slash': '/integrations/slack-clickup/slack/slash',
            'personal_tasks': '/integrations/slack-clickup/tasks/personal',
            'work_tasks': '/integrations/slack-clickup/tasks/work',
            'status': '/integrations/slack-clickup/status'
        },
        'configuration': {
            'slack_user_id': os.getenv('SLACK_USER_ID'),
            'clickup_user_id': os.getenv('CLICKUP_USER_ID'),
            'amcf_space_id': os.getenv('CLICKUP_AMCF_SPACE_ID'),
            'personal_space_id': os.getenv('CLICKUP_PERSONAL_SPACE_ID')
        },
        'health': check_module_health()
    }


#--Section 4: Module Initialization Functions
async def initialize_handlers():
    """Initialize and validate all handlers using singleton getters"""
    try:
        # Get handlers via singletons (validates they can be created)
        slack = get_slack_handler()
        clickup = get_clickup_handler()
        mapper = get_task_mapper()
        sync_manager = get_clickup_sync_manager()
        
        return {
            'status': 'initialized',
            'handlers': ['SlackHandler', 'ClickUpHandler', 'TaskMapper', 'ClickUpSyncManager'],
            'message': 'All handlers initialized successfully'
        }
        
    except Exception as e:
        logger.error(f"Handler initialization failed: {e}")
        return {
            'status': 'error',
            'handlers': [],
            'message': f'Initialization failed: {str(e)}'
        }


#--Section 5: Convenience Functions for External Use
async def create_work_task(title: str, description: str = "") -> dict:
    """Convenience function to create AMCF work task"""
    handler = get_clickup_handler()
    result = await handler.create_amcf_task(title, description)
    return {'success': bool(result), 'task': result}


async def create_personal_task(title: str, description: str = "") -> dict:
    """Convenience function to create personal task"""
    handler = get_clickup_handler()
    result = await handler.create_personal_task(title, description)
    return {'success': bool(result), 'task': result}


async def process_slack_mention(message_data: dict) -> dict:
    """Convenience function to process Slack mention"""
    mapper = get_task_mapper()
    clickup = get_clickup_handler()
    
    task_info = mapper.extract_mention_task(message_data)
    if task_info:
        result = await clickup.create_amcf_task(
            title=task_info['title'],
            description=task_info['description']
        )
        return {'success': bool(result), 'task': result}
    
    return {'success': False, 'task': None}


async def sync_clickup_tasks() -> dict:
    """Convenience function to sync ClickUp tasks to database"""
    sync_manager = get_clickup_sync_manager()
    result = await sync_manager.sync_all_tasks()
    return result


#--Section 6: Module Registration & Startup
def register_with_app(app):
    """Register this integration module with the main FastAPI app"""
    # Include the router
    app.include_router(router)
    
    # Add startup event
    @app.on_event("startup")
    async def startup_slack_clickup():
        try:
            health = check_module_health()
            if health['healthy']:
                logger.info(f"✅ {MODULE_NAME} integration loaded successfully")
            else:
                logger.warning(f"⚠️ {MODULE_NAME} integration loaded with warnings")
                logger.warning(f"   Missing vars: {health['missing_vars']}")
        except Exception as e:
            logger.error(f"❌ {MODULE_NAME} startup failed: {e}")
    
    return {
        'module': MODULE_NAME,
        'router_prefix': '/integrations/slack-clickup',
        'status': 'registered'
    }
