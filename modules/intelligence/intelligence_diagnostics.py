# modules/intelligence/intelligence_diagnostics.py
"""
Intelligence System Diagnostics
Created: 2025-10-28

This module provides detailed diagnostic logging for the intelligence system.
Use this to understand why situations aren't being detected.

Run this to see:
- What signals are being collected
- What their data structures look like
- Why detectors are/aren't matching patterns
- What the detectors are expecting vs what they're getting
"""

import logging
from typing import List, Dict, Any
from collections import defaultdict
import json

logger = logging.getLogger(__name__)

class IntelligenceDiagnostics:
    """
    Diagnostic tool for intelligence system debugging
    """
    
    def __init__(self):
        self.signal_analysis = {}
        self.detector_analysis = {}
    
    async def analyze_signals(self, signals: List) -> Dict[str, Any]:
        """
        Deep analysis of collected signals
        
        Args:
            signals: List of ContextSignal objects
            
        Returns:
            Analysis report dict
        """
        logger.info("=" * 80)
        logger.info("🔍 INTELLIGENCE DIAGNOSTICS - SIGNAL ANALYSIS")
        logger.info("=" * 80)
        
        if not signals:
            logger.warning("⚠️ NO SIGNALS COLLECTED - Intelligence system has nothing to analyze!")
            return {'total_signals': 0}
        
        # Group signals by type
        signals_by_type = defaultdict(list)
        signals_by_source = defaultdict(list)
        
        for signal in signals:
            signals_by_type[signal.signal_type].append(signal)
            signals_by_source[signal.source].append(signal)
        
        logger.info(f"📊 TOTAL SIGNALS: {len(signals)}")
        logger.info("-" * 80)
        
        # Log signal types breakdown
        logger.info("📋 SIGNALS BY TYPE:")
        for signal_type, type_signals in sorted(signals_by_type.items()):
            logger.info(f"   • {signal_type}: {len(type_signals)} signals")
        
        logger.info("-" * 80)
        
        # Log source breakdown
        logger.info("📍 SIGNALS BY SOURCE:")
        for source, source_signals in sorted(signals_by_source.items()):
            logger.info(f"   • {source}: {len(source_signals)} signals")
        
        logger.info("-" * 80)
        
        # Detailed analysis of each signal type
        logger.info("🔬 DETAILED SIGNAL STRUCTURE ANALYSIS:")
        logger.info("-" * 80)
        
        for signal_type, type_signals in sorted(signals_by_type.items()):
            logger.info(f"\n📌 Signal Type: {signal_type} ({len(type_signals)} total)")
            
            # Show first signal of this type as example
            example_signal = type_signals[0]
            
            logger.info(f"   Source: {example_signal.source}")
            logger.info(f"   Priority: {example_signal.priority}")
            logger.info(f"   Timestamp: {example_signal.timestamp}")
            logger.info(f"   Data keys: {list(example_signal.data.keys())}")
            
            # Log sample data (first 2 signals of each type)
            for i, signal in enumerate(type_signals[:2]):
                logger.info(f"\n   📄 Sample {i+1} data structure:")
                for key, value in signal.data.items():
                    # Truncate long values
                    if isinstance(value, str) and len(value) > 100:
                        value_display = value[:100] + "..."
                    elif isinstance(value, list) and len(value) > 3:
                        value_display = f"[list with {len(value)} items]"
                    elif isinstance(value, dict):
                        value_display = f"{{dict with {len(value)} keys}}"
                    else:
                        value_display = value
                    
                    logger.info(f"      • {key}: {value_display}")
            
            if len(type_signals) > 2:
                logger.info(f"   ... and {len(type_signals) - 2} more signals of this type")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ Signal analysis complete")
        logger.info("=" * 80)
        
        return {
            'total_signals': len(signals),
            'signals_by_type': {k: len(v) for k, v in signals_by_type.items()},
            'signals_by_source': {k: len(v) for k, v in signals_by_source.items()}
        }
    
    async def analyze_detector_matching(self, signals: List, detector_name: str) -> None:
        """
        Analyze why a specific detector is/isn't finding patterns
        
        Args:
            signals: List of all signals
            detector_name: Name of detector to analyze
        """
        logger.info("=" * 80)
        logger.info(f"🎯 DETECTOR ANALYSIS: {detector_name}")
        logger.info("=" * 80)
        
        # Detector-specific requirements
        detector_requirements = {
            'post_meeting_situations': {
                'required_types': ['meeting_processed'],
                'optional_types': ['action_item_pending', 'action_item_overdue', 'event_upcoming_24h'],
                'required_fields': ['meeting_id', 'meeting_title']
            },
            'deadline_situations': {
                'required_types': ['event_upcoming_24h', 'event_upcoming_48h'],
                'optional_types': ['prep_time_needed', 'action_item_pending'],
                'required_fields': ['event_id', 'event_title', 'hours_until']
            },
            'trend_content_situations': {
                'required_types': ['trend_spike', 'trend_rising', 'trend_opportunity'],
                'optional_types': ['conversation_topic', 'knowledge_entry'],
                'required_fields': ['keyword', 'trend_score']
            },
            'email_meeting_correlation': {
                'required_types': ['email_priority_high', 'email_requires_response'],
                'optional_types': ['event_upcoming_24h', 'meeting_processed'],
                'required_fields': ['email_id', 'sender']
            },
            'conversation_trend_correlation': {
                'required_types': ['conversation_topic', 'trend_spike'],
                'optional_types': ['knowledge_entry'],
                'required_fields': ['topic', 'keyword']
            },
            'weather_impact': {
                'required_types': ['weather_alert', 'weather_extreme_temp'],
                'optional_types': ['event_upcoming_24h'],
                'required_fields': ['condition']
            }
        }
        
        if detector_name not in detector_requirements:
            logger.warning(f"⚠️ Unknown detector: {detector_name}")
            return
        
        requirements = detector_requirements[detector_name]
        
        # Check for required signal types
        logger.info(f"🔍 Checking for REQUIRED signal types:")
        for required_type in requirements['required_types']:
            matching = [s for s in signals if s.signal_type == required_type]
            if matching:
                logger.info(f"   ✅ Found {len(matching)} '{required_type}' signals")
            else:
                logger.error(f"   ❌ MISSING: No '{required_type}' signals found!")
        
        logger.info(f"\n🔍 Checking for OPTIONAL signal types:")
        for optional_type in requirements['optional_types']:
            matching = [s for s in signals if s.signal_type == optional_type]
            if matching:
                logger.info(f"   ✅ Found {len(matching)} '{optional_type}' signals")
            else:
                logger.info(f"   ⚪ Not found: '{optional_type}' (optional, not critical)")
        
        # Check data structure of required signals
        logger.info(f"\n🔍 Checking DATA STRUCTURE of required signals:")
        for required_type in requirements['required_types']:
            matching = [s for s in signals if s.signal_type == required_type]
            if matching:
                example = matching[0]
                logger.info(f"\n   📄 Example '{required_type}' signal data:")
                logger.info(f"      Available keys: {list(example.data.keys())}")
                
                # Check for required fields
                for field in requirements['required_fields']:
                    if field in example.data:
                        value = example.data[field]
                        if value is None:
                            logger.warning(f"      ⚠️ Field '{field}' exists but is None!")
                        else:
                            logger.info(f"      ✅ Field '{field}': {value}")
                    else:
                        logger.error(f"      ❌ MISSING required field: '{field}'")
        
        logger.info("\n" + "=" * 80)
    
    async def full_diagnostic_report(self, signals: List) -> Dict[str, Any]:
        """
        Generate complete diagnostic report
        
        Args:
            signals: List of ContextSignal objects
            
        Returns:
            Complete diagnostic report
        """
        # Step 1: Analyze signals
        signal_report = await self.analyze_signals(signals)
        
        # Step 2: Analyze each detector
        detectors = [
            'post_meeting_situations',
            'deadline_situations',
            'trend_content_situations',
            'email_meeting_correlation',
            'conversation_trend_correlation',
            'weather_impact'
        ]
        
        logger.info("\n\n")
        logger.info("=" * 80)
        logger.info("🔍 ANALYZING ALL DETECTORS")
        logger.info("=" * 80)
        
        for detector in detectors:
            await self.analyze_detector_matching(signals, detector)
            logger.info("\n")
        
        # Step 3: Pattern matching opportunities
        logger.info("=" * 80)
        logger.info("💡 PATTERN MATCHING OPPORTUNITIES")
        logger.info("=" * 80)
        
        await self._suggest_patterns(signals)
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ FULL DIAGNOSTIC REPORT COMPLETE")
        logger.info("=" * 80 + "\n")
        
        return signal_report
    
    async def _suggest_patterns(self, signals: List) -> None:
        """
        Suggest what patterns COULD be detected with current signals
        """
        signals_by_type = defaultdict(list)
        for signal in signals:
            signals_by_type[signal.signal_type].append(signal)
        
        logger.info("\n🔮 POTENTIAL PATTERNS (if data structure matches):\n")
        
        # Check for meeting + action pattern
        if 'meeting_processed' in signals_by_type:
            meeting_count = len(signals_by_type['meeting_processed'])
            action_count = len(signals_by_type.get('action_item_pending', []))
            if action_count > 0:
                logger.info(f"   💡 Post-meeting pattern possible: {meeting_count} meetings + {action_count} actions")
            else:
                logger.info(f"   ⚠️ {meeting_count} meetings found, but no action items to pair with")
        
        # Check for event + prep pattern
        upcoming_events = len(signals_by_type.get('event_upcoming_24h', [])) + len(signals_by_type.get('event_upcoming_48h', []))
        if upcoming_events > 0:
            prep_signals = len(signals_by_type.get('prep_time_needed', []))
            action_count = len(signals_by_type.get('action_item_pending', []))
            logger.info(f"   💡 Deadline pattern possible: {upcoming_events} upcoming events")
            if prep_signals > 0:
                logger.info(f"      • {prep_signals} events need prep")
            if action_count > 0:
                logger.info(f"      • {action_count} action items could be related")
        
        # Check for trend pattern
        trend_signals = len(signals_by_type.get('trend_spike', [])) + len(signals_by_type.get('trend_rising', []))
        if trend_signals > 0:
            conv_topics = len(signals_by_type.get('conversation_topic', []))
            knowledge = len(signals_by_type.get('knowledge_entry', []))
            logger.info(f"   💡 Trend pattern possible: {trend_signals} trending topics")
            if conv_topics > 0:
                logger.info(f"      • {conv_topics} conversation topics to correlate")
            if knowledge > 0:
                logger.info(f"      • {knowledge} knowledge entries to leverage")
        
        # Check for email + meeting pattern
        priority_emails = len(signals_by_type.get('email_priority_high', []))
        if priority_emails > 0 and upcoming_events > 0:
            logger.info(f"   💡 Email-meeting pattern possible: {priority_emails} priority emails + {upcoming_events} upcoming events")
        
        if not any([
            'meeting_processed' in signals_by_type,
            upcoming_events > 0,
            trend_signals > 0,
            priority_emails > 0
        ]):
            logger.warning("   ⚠️ No obvious patterns possible with current signal types")
            logger.warning("   💡 Suggestion: Check if signal collectors are creating the right signal types")


# Standalone diagnostic function
async def run_diagnostics_on_signals(signals: List) -> Dict[str, Any]:
    """
    Run full diagnostics on a list of signals
    
    Usage:
        from modules.intelligence.intelligence_diagnostics import run_diagnostics_on_signals
        report = await run_diagnostics_on_signals(signals)
    """
    diagnostics = IntelligenceDiagnostics()
    return await diagnostics.full_diagnostic_report(signals)


# Add this to intelligence_orchestrator.py after signal collection:
"""
Example integration in intelligence_orchestrator.py:

    # After collecting signals (Phase 1)
    if len(signals) > 0:
        from .intelligence_diagnostics import run_diagnostics_on_signals
        await run_diagnostics_on_signals(signals)
"""