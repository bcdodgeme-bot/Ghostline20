# modules/intelligence/intelligence_orchestrator.py
"""
Intelligence Orchestrator for Syntax Prime V2
The brain that coordinates all intelligence modules

This is the main controller that:
1. Runs all context collectors to gather signals
2. Runs situation detectors to find patterns
3. Generates actions for situations
4. Stores situations in database with learning
5. Sends Telegram notifications
6. Manages the intelligence cycle (hourly/daily)

Created: 10/22/25
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
import json

# Import all our intelligence modules
from modules.intelligence.context_collectors import (
    CalendarContextCollector as CalendarCollector,
    EmailContextCollector as EmailCollector,
    MeetingContextCollector as MeetingCollector,
    ConversationContextCollector as ConversationCollector,
    TrendContextCollector as TrendCollector,
    WeatherContextCollector as WeatherCollector,
    KnowledgeContextCollector as KnowledgeCollector,
    PerformanceContextCollector as ActionItemCollector,
    BlueskyContextCollector as BlueskyCollector
)

from modules.intelligence.situation_detector import SituationDetector
from modules.intelligence.situation_manager import SituationManager
from modules.intelligence.action_suggester import ActionSuggester

logger = logging.getLogger(__name__)

#===============================================================================
# INTELLIGENCE ORCHESTRATOR - The Brain
#===============================================================================

class IntelligenceOrchestrator:
    """
    Coordinates all intelligence modules and runs the intelligence cycle.
    
    This is the central controller that makes everything work together.
    Think of it as the conductor of an orchestra - each module is an
    instrument, and this makes them play in harmony.
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
        self.user_id = user_id
        
        # Initialize all context collectors
        self.calendar_collector = CalendarCollector(db_manager=db_manager)
        self.email_collector = EmailCollector(db_manager=db_manager)
        self.meeting_collector = MeetingCollector(db_manager=db_manager)
        self.conversation_collector = ConversationCollector(db_manager=db_manager)
        self.trend_collector = TrendCollector(db_manager=db_manager)
        self.weather_collector = WeatherCollector(db_manager=db_manager)
        self.knowledge_collector = KnowledgeCollector(db_manager=db_manager)
        self.action_item_collector = ActionItemCollector(db_manager=db_manager)
        self.bluesky_collector = BlueskyCollector(db_manager=db_manager)
        
        # Initialize intelligence modules
        self.situation_detector = SituationDetector()
        self.situation_manager = SituationManager(db_manager=db_manager)
        self.action_suggester = ActionSuggester(db_manager=db_manager)
        
        # Store services
        self.telegram = telegram_service
        
        # Runtime stats
        self.last_run_time = None
        self.total_runs = 0
        self.total_signals_collected = 0
        self.total_situations_detected = 0
        
        logger.info("🧠 Intelligence Orchestrator initialized")
    
    
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
        5. Send notifications
        
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
            
            # PHASE 3: Generate actions and store situations
            logger.info("💡 Phase 3: Generating actions and storing situations...")
            stored_situations = await self._process_and_store_situations(
                situations, 
                user_id
            )
            
            stored_count = len(stored_situations)
            logger.info(f"✅ Stored {stored_count} situations in database")
            
            # PHASE 4: Send notifications
            notification_count = 0
            if send_notifications and self.telegram and stored_situations:
                logger.info("📱 Phase 4: Sending Telegram notifications...")
                notification_count = await self._send_notifications(
                    stored_situations,
                    user_id
                )
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
            
            logger.info(f"✨ Intelligence cycle complete in {cycle_duration:.2f}s")
            
            return {
                'success': True,
                'cycle_start': cycle_start.isoformat(),
                'duration_seconds': cycle_duration,
                'signals_collected': signal_count,
                'situations_detected': situation_count,
                'situations_stored': stored_count,
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
    # PHASE 3: GENERATE ACTIONS & STORE
    #===========================================================================
    
    async def _process_and_store_situations(
        self,
        situations: List,
        user_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Generate actions for situations and store them in database.
        
        For each situation:
        1. Generate suggested actions
        2. Add actions to situation object
        3. Store in database (with duplicate checking)
        4. Track for notification
        
        Args:
            situations: List of Situation objects
            user_id: User ID
            
        Returns:
            List of stored situation dictionaries (only new situations)
        """
        stored_situations = []
        
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
                
                if situation_id:
                    # Successfully stored (not a duplicate)
                    stored_situations.append({
                        'situation_id': situation_id,
                        'situation': situation,
                        'actions': actions
                    })
                    
                    logger.debug(f"Stored situation: {situation.situation_type}")
                else:
                    logger.debug(f"Skipped duplicate situation: {situation.situation_type}")
            
            except Exception as e:
                logger.error(f"Error processing situation: {e}", exc_info=True)
                continue
        
        return stored_situations
    
    
    #===========================================================================
    # PHASE 4: SEND NOTIFICATIONS
    #===========================================================================
    
    async def _send_notifications(
        self,
        stored_situations: List[Dict[str, Any]],
        user_id: UUID
    ) -> int:
        """
        Send Telegram notifications for new situations.
        
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
            response: Response type (acted/dismissed/snoozed/saved_for_later)
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
                    logger.info(f"✅ Scheduled cycle completed successfully")
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
