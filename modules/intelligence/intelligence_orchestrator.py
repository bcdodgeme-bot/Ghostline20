# modules/intelligence/intelligence_orchestrator.py
"""
Intelligence Orchestrator for Syntax Prime V2
The brain that coordinates all intelligence modules

This is the main controller that:
1. Runs all context collectors to gather signals
2. Runs situation detectors to find patterns
3. Generates actions for situations
4. Stores situations in database with learning
5. AUTO-EXECUTES actions for patterns approved 5+ times
6. Sends Telegram notifications
7. Manages the intelligence cycle (hourly/daily)

Created: 10/22/25
Updated: 2025-01-XX - Added singleton pattern, auto-execution logic
"""

import asyncio
import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID

# Import singleton getters from intelligence modules
from modules.intelligence.context_collectors import (
    get_calendar_collector,
    get_email_collector,
    get_meeting_collector,
    get_conversation_collector,
    get_trend_collector,
    get_weather_collector,
    get_knowledge_collector,
    get_performance_collector,
    get_bluesky_collector
)

from modules.intelligence.situation_detector import get_situation_detector
from modules.intelligence.situation_manager import get_situation_manager
from modules.intelligence.action_suggester import get_action_suggester
from modules.intelligence.action_executor import get_action_executor

logger = logging.getLogger(__name__)

#===============================================================================
# CONSTANTS
#===============================================================================

USER_ID = UUID("b7c60682-4815-4d9d-8ebe-66c6cd24eff9")

#===============================================================================
# SINGLETON INSTANCE
#===============================================================================

_orchestrator_instance: Optional['IntelligenceOrchestrator'] = None


def get_intelligence_orchestrator(
    db_manager=None,
    google_calendar_service=None,
    gmail_service=None,
    telegram_service=None,
    weather_service=None,
    user_id: Optional[UUID] = None
) -> 'IntelligenceOrchestrator':
    """
    Get or create the singleton IntelligenceOrchestrator instance.
    
    Args:
        db_manager: Database manager (required on first call)
        google_calendar_service: Google Calendar API service (optional)
        gmail_service: Gmail API service (optional)
        telegram_service: Telegram bot service for notifications (optional)
        weather_service: Weather API service (optional)
        user_id: User ID for this intelligence instance (optional)
        
    Returns:
        IntelligenceOrchestrator singleton instance
    """
    global _orchestrator_instance
    
    if _orchestrator_instance is None:
        if db_manager is None:
            raise ValueError("db_manager required for first IntelligenceOrchestrator initialization")
        _orchestrator_instance = IntelligenceOrchestrator(
            db_manager=db_manager,
            google_calendar_service=google_calendar_service,
            gmail_service=gmail_service,
            telegram_service=telegram_service,
            weather_service=weather_service,
            user_id=user_id
        )
    
    return _orchestrator_instance


#===============================================================================
# INTELLIGENCE ORCHESTRATOR - The Brain
#===============================================================================

class IntelligenceOrchestrator:
    """
    Coordinates all intelligence modules and runs the intelligence cycle.
    
    This is the central controller that makes everything work together.
    Think of it as the conductor of an orchestra - each module is an
    instrument, and this makes them play in harmony.
    
    NEW: Supports auto-execution of actions for patterns that have been
    approved 5+ times with 80%+ action rate.
    """
    
    def __init__(
        self,
        db_manager,
        google_calendar_service=None,
        gmail_service=None,
        telegram_service=None,
        weather_service=None,
        user_id: Optional[UUID] = None
    ):
        """
        Initialize the orchestrator with all necessary services.
        
        Args:
            db_manager: Database manager for all DB operations
            google_calendar_service: Google Calendar API service
            gmail_service: Gmail API service
            telegram_service: Telegram bot service for notifications
            weather_service: Weather API service
            user_id: User ID for this intelligence instance
        """
        self.db = db_manager
        self.user_id = user_id or USER_ID
        
        # Initialize all context collectors using singleton getters
        # Note: Singleton getters use global db_manager from imports, no parameter needed
        self.calendar_collector = get_calendar_collector()
        self.email_collector = get_email_collector()
        self.meeting_collector = get_meeting_collector()
        self.conversation_collector = get_conversation_collector()
        self.trend_collector = get_trend_collector()
        self.weather_collector = get_weather_collector()
        self.knowledge_collector = get_knowledge_collector()
        self.action_item_collector = get_performance_collector()
        self.bluesky_collector = get_bluesky_collector()
        
        # Initialize intelligence modules using singleton getters
        self.situation_detector = get_situation_detector()
        self.situation_manager = get_situation_manager()
        self.action_suggester = get_action_suggester()
        
        # Initialize action executor with integrations
        try:
            from modules.integrations.slack_clickup.clickup_handler import ClickUpHandler
            clickup_handler = ClickUpHandler()
        except Exception:
            clickup_handler = None
            logger.warning("ClickUp handler not available")
            
        try:
            from modules.content.content_generator import ContentGenerator
            database_url = os.getenv('DATABASE_URL')
            content_generator = ContentGenerator(database_url) if database_url else None
        except Exception as e:
            content_generator = None
            logger.warning(f"Content generator not available: {e}")

        self.action_executor = get_action_executor(
            clickup_handler=clickup_handler,
            content_generator=content_generator
        )
        
        # Store services
        self.telegram = telegram_service
        
        # Runtime stats
        self.last_run_time = None
        self.total_runs = 0
        self.total_signals_collected = 0
        self.total_situations_detected = 0
        self.total_auto_executed = 0  # NEW: Track auto-executions
        
        logger.info("🧠 Intelligence Orchestrator initialized (with auto-execution support)")
    
    
    #===========================================================================
    # MAIN INTELLIGENCE CYCLE
    #===========================================================================
    
    async def run_intelligence_cycle(
        self,
        user_id: Optional[UUID] = None,
        send_notifications: bool = True
    ) -> Dict[str, Any]:
        """
        Run the complete intelligence cycle.
        
        This is the main method that orchestrates everything:
        1. Collect signals from all sources
        2. Detect situations from signals
        3. Generate actions for situations
        4. Store in database
        5. AUTO-EXECUTE if pattern qualifies (5+ approvals, 80%+ action rate)
        6. Send notifications
        
        Args:
            user_id: User ID to run cycle for (overrides init user_id)
            send_notifications: Whether to send Telegram notifications
            
        Returns:
            Dictionary with cycle results and statistics
        """
        cycle_start = datetime.utcnow()
        user_id = user_id or self.user_id
        
        if not user_id:
            logger.error("No user_id provided for intelligence cycle")
            return {
                'success': False,
                'error': 'No user_id provided'
            }
        
        logger.info(f"🚀 Starting intelligence cycle for user {user_id}")
        
        try:
            # PHASE 1: Collect all signals
            logger.info("📊 Phase 1: Collecting signals from all sources...")
            signals = await self._collect_all_signals(user_id)
            
            signal_count = len(signals)
            logger.info(f"✅ Collected {signal_count} signals")
            
            # 🔍 DIAGNOSTIC LOGGING
            if len(signals) > 0:
                from .intelligence_diagnostics import run_diagnostics_on_signals
                try:
                    await run_diagnostics_on_signals(signals)
                except Exception as e:
                    logger.error(f"Diagnostic failed: {e}", exc_info=True)
            
            # PHASE 2: Detect situations from signals
            logger.info("🔍 Phase 2: Detecting situations from signals...")
            situations = await self._detect_all_situations(signals)
            
            situation_count = len(situations)
            logger.info(f"✅ Detected {situation_count} situations")
            
            # PHASE 3: Generate actions, store situations, and AUTO-EXECUTE if qualified
            logger.info("💡 Phase 3: Processing situations (with auto-execution check)...")
            process_result = await self._process_and_store_situations(
                situations,
                user_id
            )
            
            stored_situations = process_result['stored_situations']
            auto_executed_situations = process_result['auto_executed_situations']
            
            stored_count = len(stored_situations)
            auto_executed_count = len(auto_executed_situations)
            
            logger.info(f"✅ Stored {stored_count} situations, auto-executed {auto_executed_count}")
            
            # PHASE 4: Send notifications
            notification_count = 0
            if send_notifications and self.telegram:
                logger.info("📱 Phase 4: Sending Telegram notifications...")
                
                # Send approval requests for non-auto-executed situations
                if stored_situations:
                    notification_count = await self._send_notifications(
                        stored_situations,
                        user_id
                    )
                
                # Send confirmations for auto-executed actions
                if auto_executed_situations:
                    auto_notification_count = await self._send_auto_execution_notifications(
                        auto_executed_situations,
                        user_id
                    )
                    notification_count += auto_notification_count
                
                logger.info(f"✅ Sent {notification_count} notifications")
            
            # PHASE 5: Expire old situations
            logger.info("🗑️ Phase 5: Expiring old situations...")
            expired_count = await self.situation_manager.expire_old_situations()
            logger.info(f"✅ Marked {expired_count} situations as expired")
            
            # Update runtime stats
            cycle_duration = (datetime.utcnow() - cycle_start).total_seconds()
            self.last_run_time = cycle_start
            self.total_runs += 1
            self.total_signals_collected += signal_count
            self.total_situations_detected += situation_count
            self.total_auto_executed += auto_executed_count
            
            logger.info(f"✨ Intelligence cycle complete in {cycle_duration:.2f}s")
            
            return {
                'success': True,
                'cycle_start': cycle_start.isoformat(),
                'duration_seconds': cycle_duration,
                'signals_collected': signal_count,
                'situations_detected': situation_count,
                'situations_stored': stored_count,
                'situations_auto_executed': auto_executed_count,
                'notifications_sent': notification_count,
                'situations_expired': expired_count,
                'signal_breakdown': self._get_signal_breakdown(signals),
                'situation_breakdown': self._get_situation_breakdown(situations)
            }
            
        except Exception as e:
            logger.error(f"Error in intelligence cycle: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'cycle_start': cycle_start.isoformat()
            }
    
    
    #===========================================================================
    # PHASE 1: COLLECT SIGNALS
    #===========================================================================
    
    async def _collect_all_signals(self, user_id: UUID) -> List:
        """
        Run all context collectors and gather signals.
        
        Runs collectors in parallel for efficiency.
        
        Args:
            user_id: User ID to collect signals for
            
        Returns:
            Combined list of all signals from all collectors
        """
        # Run all collectors in parallel
        collector_tasks = [
            self.calendar_collector.collect_signals(),
            self.email_collector.collect_signals(),
            self.meeting_collector.collect_signals(),
            self.conversation_collector.collect_signals(),
            self.trend_collector.collect_signals(),
            self.weather_collector.collect_signals(),
            self.knowledge_collector.collect_signals(),
            self.action_item_collector.collect_signals(),
            self.bluesky_collector.collect_signals()
        ]
        
        results = await asyncio.gather(*collector_tasks, return_exceptions=True)
        
        # Combine all signals, filtering out errors
        all_signals = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Collector {i} failed: {result}")
                continue
            
            if isinstance(result, list):
                all_signals.extend(result)
                logger.debug(f"Collector {i} returned {len(result)} signals")
        
        return all_signals
    
    
    #===========================================================================
    # PHASE 2: DETECT SITUATIONS
    #===========================================================================
    
    async def _detect_all_situations(self, signals: List) -> List:
        """
        Run all situation detectors on the collected signals.
        
        Args:
            signals: List of Signal objects from collectors
            
        Returns:
            List of Situation objects
        """
        if not signals:
            logger.debug("No signals to detect situations from")
            return []
        
        # Run all detectors
        all_situations = []
        
        try:
            # Detector 1: Post-meeting actions
            meeting_situations = await self.situation_detector.detect_post_meeting_situations(signals)
            all_situations.extend(meeting_situations)
            
            # Detector 2: Deadline prep
            deadline_situations = await self.situation_detector.detect_deadline_situations(signals)
            all_situations.extend(deadline_situations)
            
            # Detector 3: Trend opportunities
            trend_situations = await self.situation_detector.detect_trend_content_situations(signals)
            all_situations.extend(trend_situations)
            
            # Detector 4: Email-meeting correlations
            email_situations = await self.situation_detector.detect_email_meeting_correlation(signals)
            all_situations.extend(email_situations)
            
            # Detector 5: Conversation-trend alignments
            alignment_situations = await self.situation_detector.detect_conversation_trend_correlation(signals)
            all_situations.extend(alignment_situations)
            
            # Detector 6: Weather impacts
            weather_situations = await self.situation_detector.detect_weather_impact(signals)
            all_situations.extend(weather_situations)
            
            logger.info(f"Ran {6} detectors, found {len(all_situations)} total situations")
            
        except Exception as e:
            logger.error(f"Error running situation detectors: {e}", exc_info=True)
        
        return all_situations
    
    
    #===========================================================================
    # PHASE 3: GENERATE ACTIONS, STORE, AND AUTO-EXECUTE
    #===========================================================================
    
    async def _process_and_store_situations(
        self,
        situations: List,
        user_id: UUID
    ) -> Dict[str, List]:
        """
        Generate actions for situations, store them, and auto-execute if qualified.
        
        For each situation:
        1. Generate suggested actions
        2. Add actions to situation object
        3. Store in database (with duplicate checking)
        4. CHECK: Does this pattern qualify for auto-execution?
           - If YES: Execute primary action, record as 'auto_executed'
           - If NO: Add to notification queue for user approval
        
        Args:
            situations: List of Situation objects
            user_id: User ID
            
        Returns:
            Dict with:
            - stored_situations: List of situations needing user approval
            - auto_executed_situations: List of situations that were auto-executed
        """
        stored_situations = []  # Need user approval
        auto_executed_situations = []  # Already executed automatically
        
        for situation in situations:
            try:
                # Generate actions for this situation
                actions = await self.action_suggester.suggest_actions(situation)
                
                # Add actions to situation object
                situation.suggested_actions = actions
                
                # Store in database (returns None if duplicate)
                situation_id = await self.situation_manager.create_situation(
                    situation=situation,
                    user_id=user_id
                )
                
                if not situation_id:
                    # Duplicate situation, skip
                    logger.debug(f"Skipped duplicate situation: {situation.situation_type}")
                    continue
                
                # Successfully stored - now check for auto-execution
                situation.situation_id = situation_id
                
                # Check if this pattern qualifies for auto-execution
                # Method extracts pattern_key internally from context
                should_auto, learning_record = await self.situation_manager.should_auto_execute(
                    situation_type=situation.situation_type,
                    situation_context=situation.situation_context
                )
                
                # Build pattern key for logging
                pattern_key = self._build_pattern_key(situation)
                
                if should_auto and actions:
                    # AUTO-EXECUTE the primary action!
                    logger.info(f"🤖 AUTO-EXECUTING: {situation.situation_type} (pattern: {pattern_key})")
                    
                    primary_action = actions[0]  # Execute first/primary action
                    
                    try:
                        # Execute the action
                        result = await self.action_executor.execute_action(
                            action=primary_action,
                            user_id=user_id
                        )
                        
                        if result.get('success'):
                            # Record as auto-executed
                            await self.situation_manager.record_user_response(
                                situation_id=situation_id,
                                response='auto_executed',
                                response_data={
                                    'action_type': primary_action.get('action_type'),
                                    'action_description': primary_action.get('description'),
                                    'execution_result': result
                                }
                            )
                            
                            auto_executed_situations.append({
                                'situation_id': situation_id,
                                'situation': situation,
                                'actions': actions,
                                'executed_action': primary_action,
                                'execution_result': result
                            })
                            
                            logger.info(f"✅ Auto-executed successfully: {primary_action.get('description')}")
                        else:
                            # Execution failed - fall back to manual approval
                            logger.warning(f"Auto-execution failed: {result.get('message')}")
                            stored_situations.append({
                                'situation_id': situation_id,
                                'situation': situation,
                                'actions': actions
                            })
                            
                    except Exception as exec_error:
                        # Execution error - fall back to manual approval
                        logger.error(f"Auto-execution error: {exec_error}", exc_info=True)
                        stored_situations.append({
                            'situation_id': situation_id,
                            'situation': situation,
                            'actions': actions
                        })
                else:
                    # Not qualified for auto-execution - needs user approval
                    stored_situations.append({
                        'situation_id': situation_id,
                        'situation': situation,
                        'actions': actions
                    })
                    
                    logger.debug(f"Stored situation for approval: {situation.situation_type}")
            
            except Exception as e:
                logger.error(f"Error processing situation: {e}", exc_info=True)
                continue
        
        return {
            'stored_situations': stored_situations,
            'auto_executed_situations': auto_executed_situations
        }
    
    
    def _build_pattern_key(self, situation) -> str:
        """
        Build a pattern key from situation context for learning lookup.
        
        This should match the logic in situation_manager._build_pattern_key()
        
        Args:
            situation: Situation object
            
        Returns:
            Pattern key string
        """
        context = situation.situation_context
        situation_type = situation.situation_type
        
        # Build pattern key based on situation type
        if situation_type == 'post_meeting_action_required':
            # Pattern by meeting participant or recurring meeting
            participants = context.get('participants', [])
            if participants:
                return f"meeting_with:{participants[0]}"
            return f"meeting:{context.get('meeting_title', 'unknown')[:30]}"
        
        elif situation_type == 'trend_content_opportunity':
            # Pattern by business area + account
            return f"trend:{context.get('business_area', 'general')}:{context.get('suggested_account', 'default')}"
        
        elif situation_type == 'deadline_approaching_prep_needed':
            # Pattern by event type
            return f"deadline:{context.get('prep_reason', 'general')}"
        
        elif situation_type in ['email_priority_meeting_context', 'email_meeting_followup']:
            # Pattern by sender domain
            sender = context.get('sender_email', context.get('sender_name', 'unknown'))
            if '@' in sender:
                domain = sender.split('@')[1]
                return f"email_from:{domain}"
            return f"email_from:{sender[:20]}"
        
        elif situation_type == 'conversation_trend_alignment':
            # Pattern by business area
            return f"alignment:{context.get('business_area', 'general')}"
        
        elif situation_type in ['weather_impact_calendar', 'weather_health_impact', 'weather_emergency_alert']:
            # Pattern by weather condition type
            return f"weather:{context.get('weather_condition', 'unknown')}"
        
        else:
            # Generic pattern
            return f"generic:{situation_type}"
    
    
    #===========================================================================
    # PHASE 4: SEND NOTIFICATIONS
    #===========================================================================
    
    async def _send_notifications(
        self,
        stored_situations: List[Dict[str, Any]],
        user_id: UUID
    ) -> int:
        """
        Send Telegram notifications for new situations that need approval.
        
        Groups situations by priority and sends them in order.
        Only sends notifications for situations with priority >= 7.
        
        Args:
            stored_situations: List of situation dicts from _process_and_store_situations
            user_id: User ID
            
        Returns:
            Count of notifications sent
        """
        if not self.telegram:
            logger.debug("No Telegram service configured, skipping notifications")
            return 0
        
        notification_count = 0
        
        # Filter to high-priority situations only (priority >= 7)
        high_priority = [
            s for s in stored_situations
            if s['situation'].priority_score >= 7
        ]
        
        # Sort by priority (highest first)
        high_priority.sort(
            key=lambda s: s['situation'].priority_score,
            reverse=True
        )
        
        logger.info(f"Sending notifications for {len(high_priority)} high-priority situations")
        
        for situation_data in high_priority:
            try:
                situation = situation_data['situation']
                actions = situation_data['actions']
                
                # Format notification
                message, buttons = await self.action_suggester.format_telegram_notification(
                    situation=situation,
                    actions=actions
                )
                
                # Send to Telegram
                result = await self.telegram.send_notification(
                    user_id=str(user_id),
                    notification_type="intelligence",
                    notification_subtype=situation.situation_type,
                    message_text=message,
                    buttons=buttons,
                    message_data={
                        "situation_id": str(situation.situation_id),
                        "priority": situation.priority_score
                    }
                )

                if result.get('success'):
                    notification_count += 1
                    logger.debug(f"Sent notification for {situation.situation_type}")
                else:
                    logger.warning(f"Failed to send notification for {situation.situation_type}")
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            
            except Exception as e:
                logger.error(f"Error sending notification: {e}", exc_info=True)
                continue
        
        return notification_count
    
    
    async def _send_auto_execution_notifications(
        self,
        auto_executed_situations: List[Dict[str, Any]],
        user_id: UUID
    ) -> int:
        """
        Send Telegram notifications confirming auto-executed actions.
        
        These are informational messages letting the user know what was
        done automatically based on their learned preferences.
        
        Args:
            auto_executed_situations: List of auto-executed situation dicts
            user_id: User ID
            
        Returns:
            Count of notifications sent
        """
        if not self.telegram:
            logger.debug("No Telegram service configured, skipping auto-execution notifications")
            return 0
        
        notification_count = 0
        
        for situation_data in auto_executed_situations:
            try:
                situation = situation_data['situation']
                executed_action = situation_data['executed_action']
                execution_result = situation_data['execution_result']
                
                # Build confirmation message
                message = f"🤖 **Auto-Executed Action**\n\n"
                message += f"Based on your pattern of approving similar situations, I automatically:\n\n"
                message += f"✅ {executed_action.get('description', 'Completed action')}\n\n"
                
                # Add result details if available
                if execution_result.get('message'):
                    result_preview = execution_result['message'][:200]
                    message += f"**Result:**\n{result_preview}\n\n"
                
                message += f"_Situation: {situation.situation_type.replace('_', ' ').title()}_\n"
                message += f"_Confidence: {situation.confidence_score * 100:.0f}%_"
                
                # Simple buttons for feedback
                buttons = [
                    [
                        {"text": "👍 Good", "callback_data": f"auto_feedback:good:{situation.situation_id}"},
                        {"text": "👎 Don't do this", "callback_data": f"auto_feedback:bad:{situation.situation_id}"}
                    ],
                    [
                        {"text": "ℹ️ Details", "callback_data": f"situation:details:{situation.situation_id}"}
                    ]
                ]
                
                # Send to Telegram
                result = await self.telegram.send_notification(
                    user_id=str(user_id),
                    notification_type="intelligence",
                    notification_subtype="auto_executed",
                    message_text=message,
                    buttons=buttons,
                    message_data={
                        "situation_id": str(situation.situation_id),
                        "action_type": executed_action.get('action_type'),
                        "auto_executed": True
                    }
                )

                if result.get('success'):
                    notification_count += 1
                    logger.debug(f"Sent auto-execution confirmation for {situation.situation_type}")
                else:
                    logger.warning(f"Failed to send auto-execution notification")
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            
            except Exception as e:
                logger.error(f"Error sending auto-execution notification: {e}", exc_info=True)
                continue
        
        return notification_count
    
    
    #===========================================================================
    # HELPER METHODS & STATISTICS
    #===========================================================================
    
    def _get_signal_breakdown(self, signals: List) -> Dict[str, int]:
        """
        Get breakdown of signals by type.
        
        Args:
            signals: List of Signal objects
            
        Returns:
            Dictionary mapping signal_type to count
        """
        breakdown = {}
        for signal in signals:
            signal_type = signal.signal_type
            breakdown[signal_type] = breakdown.get(signal_type, 0) + 1
        
        return breakdown
    
    
    def _get_situation_breakdown(self, situations: List) -> Dict[str, int]:
        """
        Get breakdown of situations by type.
        
        Args:
            situations: List of Situation objects
            
        Returns:
            Dictionary mapping situation_type to count
        """
        breakdown = {}
        for situation in situations:
            situation_type = situation.situation_type
            breakdown[situation_type] = breakdown.get(situation_type, 0) + 1
        
        return breakdown
    
    
    async def get_active_situations(
        self,
        user_id: Optional[UUID] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all active situations for display.
        
        Convenience wrapper around situation_manager.get_active_situations().
        
        Args:
            user_id: User ID (defaults to orchestrator's user_id)
            limit: Maximum number of situations to return
            
        Returns:
            List of active situation dictionaries
        """
        user_id = user_id or self.user_id
        
        if not user_id:
            logger.error("No user_id provided")
            return []
        
        return await self.situation_manager.get_active_situations(
            user_id=user_id,
            limit=limit
        )
    
    
    async def record_user_response(
        self,
        situation_id: UUID,
        response: str,
        response_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Record a user's response to a situation.
        
        Convenience wrapper around situation_manager.record_user_response().
        
        Args:
            situation_id: UUID of situation
            response: Response type (acted/dismissed/snoozed/saved_for_later/auto_executed)
            response_data: Optional additional data
            
        Returns:
            True if successful
        """
        return await self.situation_manager.record_user_response(
            situation_id=situation_id,
            response=response,
            response_data=response_data
        )
    
    
    async def generate_daily_digest(
        self,
        user_id: Optional[UUID] = None
    ) -> str:
        """
        Generate daily digest of situations.
        
        Convenience wrapper around situation_manager.generate_daily_digest().
        
        Args:
            user_id: User ID (defaults to orchestrator's user_id)
            
        Returns:
            Formatted digest string
        """
        user_id = user_id or self.user_id
        
        if not user_id:
            return "Error: No user_id provided"
        
        return await self.situation_manager.generate_daily_digest(user_id=user_id)
    
    
    async def get_learning_insights(
        self,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Get what the system has learned about user preferences.
        
        Convenience wrapper around situation_manager.get_learning_insights().
        
        Args:
            user_id: User ID (defaults to orchestrator's user_id)
            
        Returns:
            Dictionary with learning insights
        """
        user_id = user_id or self.user_id
        
        if not user_id:
            return {}
        
        return await self.situation_manager.get_learning_insights(user_id=user_id)
    
    
    async def get_auto_executable_patterns(self) -> List[Dict[str, Any]]:
        """
        Get list of patterns that qualify for auto-execution.
        
        Convenience wrapper around situation_manager.get_auto_executable_patterns().
        
        Returns:
            List of patterns with their stats
        """
        return await self.situation_manager.get_auto_executable_patterns()
    
    
    def get_runtime_stats(self) -> Dict[str, Any]:
        """
        Get runtime statistics for the orchestrator.
        
        Returns:
            Dictionary with runtime stats
        """
        return {
            'last_run_time': self.last_run_time.isoformat() if self.last_run_time else None,
            'total_runs': self.total_runs,
            'total_signals_collected': self.total_signals_collected,
            'total_situations_detected': self.total_situations_detected,
            'total_auto_executed': self.total_auto_executed,
            'avg_signals_per_run': self.total_signals_collected / self.total_runs if self.total_runs > 0 else 0,
            'avg_situations_per_run': self.total_situations_detected / self.total_runs if self.total_runs > 0 else 0
        }
    
    
    #===========================================================================
    # SCHEDULED CYCLE RUNNER
    #===========================================================================
    
    async def run_scheduled_cycle(
        self,
        interval_minutes: int = 60,
        run_once: bool = False
    ):
        """
        Run the intelligence cycle on a schedule.
        
        This is meant to be run as a background task that continuously
        monitors and generates intelligence.
        
        Usage:
            # Run every hour forever
            await orchestrator.run_scheduled_cycle(interval_minutes=60)
            
            # Run once immediately
            await orchestrator.run_scheduled_cycle(run_once=True)
        
        Args:
            interval_minutes: How often to run the cycle (default: 60 minutes)
            run_once: If True, run once and return (for testing)
        """
        logger.info(f"🕐 Starting scheduled intelligence cycle (interval: {interval_minutes} minutes)")
        
        while True:
            try:
                # Run the intelligence cycle
                result = await self.run_intelligence_cycle(
                    user_id=self.user_id,
                    send_notifications=True
                )
                
                if result['success']:
                    auto_count = result.get('situations_auto_executed', 0)
                    logger.info(f"✅ Scheduled cycle completed (auto-executed: {auto_count})")
                else:
                    logger.error(f"❌ Scheduled cycle failed: {result.get('error')}")
                
                # If run_once mode, break after first run
                if run_once:
                    logger.info("Run-once mode: Exiting after single cycle")
                    break
                
                # Wait for next interval
                logger.info(f"⏰ Sleeping for {interval_minutes} minutes until next cycle...")
                await asyncio.sleep(interval_minutes * 60)
            
            except Exception as e:
                logger.error(f"Error in scheduled cycle: {e}", exc_info=True)
                
                # If run_once mode, break even on error
                if run_once:
                    break
                
                # Otherwise wait and retry
                logger.info("Waiting 5 minutes before retry...")
                await asyncio.sleep(300)  # 5 minutes
    
    
    async def run_daily_digest(
        self,
        user_id: Optional[UUID] = None,
        send_notification: bool = True
    ) -> str:
        """
        Generate and optionally send the daily digest.
        
        This should be run once per day (e.g., at 8 AM) to give the user
        a summary of the past 24 hours.
        
        Args:
            user_id: User ID (defaults to orchestrator's user_id)
            send_notification: Whether to send via Telegram
            
        Returns:
            Digest message string
        """
        user_id = user_id or self.user_id
        
        if not user_id:
            logger.error("No user_id provided for daily digest")
            return "Error: No user_id"
        
        logger.info(f"📊 Generating daily digest for user {user_id}")
        
        try:
            # Generate digest
            digest = await self.generate_daily_digest(user_id=user_id)
            
            # Send via Telegram if requested
            if send_notification and self.telegram:
                await self.telegram.send_message(
                    user_id=user_id,
                    message=digest,
                    buttons=None
                )
                logger.info("✅ Sent daily digest notification")
            
            return digest
        
        except Exception as e:
            logger.error(f"Error generating daily digest: {e}", exc_info=True)
            return f"Error generating digest: {str(e)}"
    
    
    #===========================================================================
    # MANUAL TRIGGER METHODS (for testing/debugging)
    #===========================================================================
    
    async def test_signal_collection(
        self,
        user_id: Optional[UUID] = None,
        collector_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Test signal collection from one or all collectors.
        
        Useful for debugging and development.
        
        Args:
            user_id: User ID (defaults to orchestrator's user_id)
            collector_name: Specific collector to test (None = all)
            
        Returns:
            Dictionary with test results
        """
        user_id = user_id or self.user_id
        
        if not user_id:
            return {'error': 'No user_id provided'}
        
        logger.info(f"🧪 Testing signal collection for user {user_id}")
        
        collectors = {
            'calendar': self.calendar_collector,
            'email': self.email_collector,
            'meeting': self.meeting_collector,
            'conversation': self.conversation_collector,
            'trend': self.trend_collector,
            'weather': self.weather_collector,
            'knowledge': self.knowledge_collector,
            'action_item': self.action_item_collector
        }
        
        results = {}
        
        if collector_name:
            # Test specific collector
            if collector_name not in collectors:
                return {'error': f'Unknown collector: {collector_name}'}
            
            collector = collectors[collector_name]
            try:
                signals = await collector.collect(user_id)
                results[collector_name] = {
                    'success': True,
                    'signal_count': len(signals),
                    'signal_types': list(set(s.signal_type for s in signals))
                }
            except Exception as e:
                results[collector_name] = {
                    'success': False,
                    'error': str(e)
                }
        else:
            # Test all collectors
            for name, collector in collectors.items():
                try:
                    signals = await collector.collect(user_id)
                    results[name] = {
                        'success': True,
                        'signal_count': len(signals),
                        'signal_types': list(set(s.signal_type for s in signals))
                    }
                except Exception as e:
                    results[name] = {
                        'success': False,
                        'error': str(e)
                    }
        
        return results
    
    
    async def test_situation_detection(
        self,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Test the full cycle up through situation detection.
        
        Useful for debugging and development.
        
        Args:
            user_id: User ID (defaults to orchestrator's user_id)
            
        Returns:
            Dictionary with test results
        """
        user_id = user_id or self.user_id
        
        if not user_id:
            return {'error': 'No user_id provided'}
        
        logger.info(f"🧪 Testing situation detection for user {user_id}")
        
        try:
            # Collect signals
            signals = await self._collect_all_signals(user_id)
            
            # Detect situations
            situations = await self._detect_all_situations(signals)
            
            return {
                'success': True,
                'signal_count': len(signals),
                'situation_count': len(situations),
                'signal_breakdown': self._get_signal_breakdown(signals),
                'situation_breakdown': self._get_situation_breakdown(situations),
                'situations': [
                    {
                        'type': s.situation_type,
                        'confidence': s.confidence_score,
                        'priority': s.priority_score,
                        'context_summary': str(s.situation_context)[:100]
                    }
                    for s in situations
                ]
            }
        
        except Exception as e:
            logger.error(f"Error testing situation detection: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
            
    async def handle_situation_callback(
        self,
        callback_data: str,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Execute an action from a situation.
        Called by Telegram callback handler when user clicks action button.
        
        Args:
            callback_data: Format "situation:action:situation_id"
            user_id: User ID
            
        Returns:
            Result dict with success and message
        """
        try:
            # Parse callback
            parts = callback_data.split(':')
            action_type = parts[1]  # e.g. "action1", "action2"
            situation_id = parts[2]
            
            # Get situation
            situation = await self.situation_manager.get_situation_by_id(situation_id)
            if not situation:
                return {'success': False, 'message': '❌ Situation not found'}
            
            # Extract action index
            action_index = int(action_type.replace('action', '')) - 1
            
            # Get the specific action
            actions = situation.get('suggested_actions', [])
            if action_index >= len(actions):
                return {'success': False, 'message': '❌ Invalid action'}
            
            clicked_action = actions[action_index]
            
            # Execute using ActionExecutor
            result = await self.action_executor.execute_action(
                action=clicked_action,
                user_id=user_id
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error handling callback: {e}", exc_info=True)
            return {'success': False, 'message': f'❌ Error: {str(e)}'}
    
    
    async def handle_auto_feedback(
        self,
        callback_data: str,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Handle feedback on auto-executed actions.
        
        If user gives negative feedback, we can reduce the pattern's
        action rate to prevent future auto-execution.
        
        Args:
            callback_data: Format "auto_feedback:good/bad:situation_id"
            user_id: User ID
            
        Returns:
            Result dict with success and message
        """
        try:
            parts = callback_data.split(':')
            feedback_type = parts[1]  # 'good' or 'bad'
            situation_id = parts[2]
            
            if feedback_type == 'good':
                # Positive feedback - no action needed, the learning system
                # already recorded this as 'auto_executed' which counts as 'acted'
                return {
                    'success': True,
                    'message': '👍 Thanks for the feedback! I\'ll continue auto-executing similar actions.'
                }
            
            elif feedback_type == 'bad':
                # Negative feedback - we need to record this as 'dismissed'
                # to reduce the action rate for this pattern
                await self.situation_manager.record_user_response(
                    situation_id=UUID(situation_id),
                    response='dismissed',  # Overrides the 'auto_executed'
                    response_data={
                        'feedback': 'negative_auto_execution',
                        'user_requested_stop': True
                    }
                )
                
                return {
                    'success': True,
                    'message': '👎 Got it! I\'ll ask for approval on similar situations in the future.'
                }
            
            else:
                return {
                    'success': False,
                    'message': '❌ Unknown feedback type'
                }
            
        except Exception as e:
            logger.error(f"Error handling auto feedback: {e}", exc_info=True)
            return {'success': False, 'message': f'❌ Error: {str(e)}'}


#===============================================================================
# MODULE EXPORTS
#===============================================================================

__all__ = [
    'IntelligenceOrchestrator',
    'get_intelligence_orchestrator',
    'USER_ID'
]
