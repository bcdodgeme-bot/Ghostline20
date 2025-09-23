# modules/ai/__init__.py
"""
Syntax Prime V2 - AI Brain Module
Complete AI assistant with personality, memory, and learning
"""

from .router import router, get_integration_info, check_module_health
from .openrouter_client import get_openrouter_client
from .inception_client import get_inception_client
from .conversation_manager import get_memory_manager
from .knowledge_query import get_knowledge_engine
from .personality_engine import get_personality_engine
from .feedback_processor import get_feedback_processor

__version__ = "2.0.0"
__author__ = "Carl's AI Brain"

# Export main components
__all__ = [
    # Main router
    'router',
    'get_integration_info', 
    'check_module_health',
    
    # Core clients
    'get_openrouter_client',
    'get_inception_client',
    
    # AI Brain components
    'get_memory_manager',
    'get_knowledge_engine', 
    'get_personality_engine',
    'get_feedback_processor'
]