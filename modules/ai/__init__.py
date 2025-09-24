# modules/ai/__init__.py
"""
Syntax Prime V2 - AI Brain Module
Complete AI assistant with personality, memory, and learning
Date: 9/23/25
"""

#-- Section 1: Core Router and Integration - 9/23/25
from .router import router, get_integration_info, check_module_health

#-- Section 2: AI Provider Clients - 9/23/25
from .openrouter_client import get_openrouter_client
from .inception_client import get_inception_client

#-- Section 3: Memory and Knowledge Systems - 9/23/25
from .conversation_manager import get_memory_manager
from .knowledge_query import get_knowledge_engine

#-- Section 4: Personality and Learning Systems - 9/23/25
from .personality_engine import get_personality_engine
from .feedback_processor import get_feedback_processor

#-- Section 5: Module Metadata - 9/23/25
__version__ = "2.0.0"
__author__ = "Carl's AI Brain"
__description__ = "Complete AI brain with 250K context, 4 personalities, and feedback learning"

#-- Section 6: Public API Exports - 9/23/25
__all__ = [
    # Main router and system info
    'router',
    'get_integration_info',
    'check_module_health',
    
    # AI provider clients
    'get_openrouter_client',
    'get_inception_client',
    
    # Core AI brain components
    'get_memory_manager',
    'get_knowledge_engine',
    'get_personality_engine',
    'get_feedback_processor'
]

#-- Section 7: Quick System Status Check - 9/23/25
def get_ai_brain_status():
    """Quick status check for the AI brain system"""
    return {
        'version': __version__,
        'components_loaded': len(__all__),
        'description': __description__,
        'ready': True
    }

# Add to exports
__all__.append('get_ai_brain_status')
