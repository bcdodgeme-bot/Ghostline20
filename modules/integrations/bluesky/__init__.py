# modules/integrations/bluesky/__init__.py
"""
Multi-Account Bluesky Integration for Syntax Prime V2
5 Social Media Assistants That Never Sleep But Always Ask Permission

This module provides comprehensive Bluesky social media management across 5 accounts
with AI-powered engagement intelligence, keyword matching, and approval workflows.
"""

from .multi_account_client import BlueskyMultiClient, get_bluesky_multi_client
from .engagement_analyzer import EngagementAnalyzer, get_engagement_analyzer
from .approval_system import ApprovalSystem, get_approval_system
from .notification_manager import NotificationManager, get_notification_manager
from .router import router
from .integration_info import get_integration_info, check_module_health, get_account_summary

__all__ = [
    'BlueskyMultiClient',
    'EngagementAnalyzer', 
    'ApprovalSystem',
    'NotificationManager',
    'router',
    'get_bluesky_multi_client',
    'get_engagement_analyzer',
    'get_approval_system', 
    'get_notification_manager',
    'get_integration_info',
    'check_module_health',
    'get_account_summary'
]

__version__ = "2.0.0"
__description__ = "Multi-account Bluesky integration with AI-powered engagement intelligence"
__author__ = "Syntax Prime V2"

# Module metadata
MODULE_NAME = 'bluesky_multi_account'
INTEGRATION_TYPE = 'social_media_management'
SUPPORTED_ACCOUNTS = 5
SUPPORTED_PERSONALITIES = ['syntaxprime', 'professional', 'compassionate']
TOTAL_KEYWORDS = 3344  # Sum across all keyword tables

# Account configuration summary
ACCOUNT_MAPPING = {
    'personal': 'bcdodgeme.bsky.social',
    'rose_angel': 'roseandangel.bsky.social', 
    'binge_tv': 'tvsignals.bsky.social',
    'meals_feelz': 'mealsnfeelz.bsky.social',
    'damn_it_carl': 'syntax-ceo.bsky.social'
}