"""
Fathom Meeting Integration Module
Automatically processes meeting recordings with AI-powered summaries

Module Structure:
- fathom_handler.py: Fathom API client for fetching meetings/transcripts
- meeting_processor.py: Claude AI integration for intelligent summaries
- database_manager.py: PostgreSQL storage for meetings and insights
- router.py: FastAPI webhook endpoint for Fathom events

Workflow:
1. Fathom webhook fires when meeting ends
2. Fetch full transcript from Fathom API
3. Generate AI summary using Claude (better than Fathom's native AI)
4. Store in PostgreSQL for Syntax's conversational memory
5. Enable queries like "What did we discuss in Tuesday's meeting?"

FIXES APPLIED (Session 6 - Fathom Review):
- Added missing logging import (logger was undefined in register_with_app)
"""

import os
import logging

# Initialize logger for this module
logger = logging.getLogger(__name__)

# --Section 1: Module Exports & Public API
from .fathom_handler import FathomHandler
from .meeting_processor import MeetingProcessor
from .database_manager import FathomDatabaseManager
from .router import router

# Public API - what other modules can import
__all__ = [
    'FathomHandler',
    'MeetingProcessor',
    'FathomDatabaseManager',
    'router'
]

# --Section 2: Module Metadata & Configuration
__version__ = '1.0.0'
__author__ = 'Syntax Prime V2'
__description__ = 'Fathom meeting recording integration with AI summaries'

# Module configuration constants
MODULE_NAME = 'fathom_meetings'
INTEGRATION_TYPE = 'webhook'
SUPPORTED_EVENTS = ['meeting.ended']
API_BASE_URL = 'https://api.fathom.ai/external/v1'


# --Section 3: Module Initialization & Health Checks
def check_module_health() -> dict:
    """Check if all required environment variables are configured"""
    required_vars = [
        'FATHOM_API_KEY',
        'FATHOM_WEBHOOK_SECRET',
        'DATABASE_URL',
        'ANTHROPIC_API_KEY'  # For Claude summaries
    ]
    
    status = {'healthy': True, 'missing_vars': [], 'configured_vars': []}
    
    for var in required_vars:
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
            'webhook': '/integrations/fathom/webhook',
            'meetings': '/integrations/fathom/meetings',
            'meeting_detail': '/integrations/fathom/meetings/{meeting_id}',
            'search': '/integrations/fathom/search',
            'status': '/integrations/fathom/status'
        },
        'configuration': {
            'api_base_url': API_BASE_URL,
            'webhook_configured': bool(os.getenv('FATHOM_WEBHOOK_SECRET')),
            'api_key_configured': bool(os.getenv('FATHOM_API_KEY')),
            'claude_configured': bool(os.getenv('ANTHROPIC_API_KEY'))
        },
        'health': check_module_health()
    }


# --Section 4: Module Initialization Functions
async def initialize_handlers():
    """Initialize and validate all handlers"""
    try:
        # Test Fathom handler
        fathom = FathomHandler()
        
        # Test Database manager
        db = FathomDatabaseManager()
        
        # Test Meeting processor
        processor = MeetingProcessor()
        
        return {
            'status': 'initialized',
            'handlers': ['FathomHandler', 'FathomDatabaseManager', 'MeetingProcessor'],
            'message': 'All handlers initialized successfully'
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'handlers': [],
            'message': f'Initialization failed: {str(e)}'
        }


# --Section 5: Convenience Functions for External Use
async def process_meeting_webhook(webhook_data: dict) -> dict:
    """Convenience function to process Fathom webhook"""
    try:
        # Initialize handlers
        fathom = FathomHandler()
        processor = MeetingProcessor()
        db = FathomDatabaseManager()
        
        # Extract meeting ID from webhook
        meeting_id = webhook_data.get('meeting_id')
        if not meeting_id:
            return {'success': False, 'error': 'No meeting_id in webhook'}
        
        # Fetch meeting details and transcript
        meeting_data = await fathom.get_meeting_details(meeting_id)
        
        # Generate AI summary
        summary_data = await processor.generate_summary(meeting_data)
        
        # Store in database
        db_result = await db.store_meeting(meeting_data, summary_data)
        
        return {
            'success': True,
            'meeting_id': meeting_id,
            'stored': db_result
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


# --Section 6: Module Registration & Startup
def register_with_app(app):
    """Register this integration module with the main FastAPI app"""
    # Include the router
    app.include_router(router)
    
    # Add startup event
    @app.on_event("startup")
    async def startup_fathom():
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
        'router_prefix': '/integrations/fathom',
        'status': 'registered'
    }
