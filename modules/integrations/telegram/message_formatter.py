"""
Telegram Message Formatter - Personality-Driven Message Generation
Formats notifications with appropriate tone and personality
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime, time

logger = logging.getLogger(__name__)

class MessageFormatter:
    """Formats Telegram notifications with personality"""
    
    def __init__(self):
        # Can integrate with personality engine later if needed
        pass
    
    # ========================================================================
    # PRAYER NOTIFICATIONS
    # ========================================================================
    
    def format_prayer_notification(
        self,
        prayer_name: str,
        prayer_time: time,
        minutes_until: int,
        is_follow_up: bool = False
    ) -> str:
        """
        Format prayer time notification
        
        Args:
            prayer_name: 'Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'
            prayer_time: Time object
            minutes_until: Minutes until prayer
            is_follow_up: True if this is a reminder after initial
        
        Returns:
            Formatted message text
        """
        time_str = prayer_time.strftime("%I:%M %p").lstrip('0')
        
        if is_follow_up:
            if minutes_until <= 0:
                return f"🕌 **{prayer_name} Prayer Time**\n\nIt's time for {prayer_name} prayer now."
            else:
                return f"🕌 **{prayer_name} Prayer Reminder**\n\n{minutes_until} minutes remaining until {prayer_name} ({time_str})."
        else:
            return (
                f"🕌 **{prayer_name} Prayer**\n\n"
                f"{prayer_name} prayer in {minutes_until} minutes ({time_str}).\n"
                f"Time to prepare."
            )
    
    # ========================================================================
    # WEATHER NOTIFICATIONS
    # ========================================================================
    
    def format_weather_alert(
        self,
        alert_type: str,
        details: Dict[str, Any]
    ) -> str:
        """
        Format weather alert notification
        
        Args:
            alert_type: 'rain', 'uv', 'snow', 'emergency'
            details: Weather data
        
        Returns:
            Formatted message text
        """
        if alert_type == 'rain':
            precip_prob = details.get('precipitation_probability', 0)
            time_until = details.get('time_until_hours', 2)
            return (
                f"🌧️ **Rain Alert**\n\n"
                f"Rain likely in {time_until} hours ({precip_prob}% chance).\n"
                f"Plan accordingly."
            )
        
        elif alert_type == 'uv':
            uv_index = details.get('uv_index', 0)
            return (
                f"☀️ **UV Alert**\n\n"
                f"High UV index today: {uv_index}\n"
                f"Sun protection recommended."
            )
        
        elif alert_type == 'snow':
            accumulation = details.get('accumulation_inches', 0)
            return (
                f"❄️ **Snow Alert**\n\n"
                f"Snow expected: {accumulation} inches\n"
                f"Travel may be affected."
            )
        
        elif alert_type == 'emergency':
            alert_text = details.get('alert_text', 'Severe weather alert')
            return (
                f"⚠️ **WEATHER EMERGENCY**\n\n"
                f"{alert_text}\n\n"
                f"Take appropriate precautions."
            )
        
        return "🌤️ **Weather Update**\n\nCheck forecast for details."
    
    # ========================================================================
    # REMINDER NOTIFICATIONS
    # ========================================================================
    
    def format_reminder(
        self,
        reminder_text: str,
        scheduled_time: Optional[datetime] = None
    ) -> str:
        """
        Format custom reminder notification
        
        Args:
            reminder_text: User's reminder text
            scheduled_time: When reminder was scheduled for
        
        Returns:
            Formatted message text
        """
        return f"⏰ **Reminder**\n\n{reminder_text}"
    
    # ========================================================================
    # CALENDAR NOTIFICATIONS
    # ========================================================================
    
    def format_calendar_event(
        self,
        event_title: str,
        event_time: datetime,
        location: Optional[str] = None,
        minutes_until: int = 60
    ) -> str:
        """
        Format calendar event reminder
        
        Args:
            event_title: Event name
            event_time: When event occurs
            location: Optional location
            minutes_until: Minutes until event
        
        Returns:
            Formatted message text
        """
        time_str = event_time.strftime("%I:%M %p").lstrip('0')
        
        message = f"📅 **Calendar Event**\n\n{event_title}\n"
        
        if minutes_until >= 60:
            hours = minutes_until // 60
            message += f"In {hours} hour{'s' if hours > 1 else ''} ({time_str})"
        else:
            message += f"In {minutes_until} minutes ({time_str})"
        
        if location:
            message += f"\n📍 {location}"
        
        return message
    
    # ========================================================================
    # EMAIL NOTIFICATIONS
    # ========================================================================
    
    def format_urgent_email(
        self,
        sender: str,
        subject: str,
        urgency_score: float
    ) -> str:
        """
        Format urgent email notification
        
        Args:
            sender: Email sender name/address
            subject: Email subject line
            urgency_score: AI-calculated urgency (0-10)
        
        Returns:
            Formatted message text
        """
        return (
            f"📧 **Urgent Email**\n\n"
            f"From: {sender}\n"
            f"Subject: {subject}\n\n"
            f"Urgency: {urgency_score:.1f}/10"
        )
    
    # ========================================================================
    # CLICKUP NOTIFICATIONS
    # ========================================================================
    
    def format_clickup_task(
        self,
        task_title: str,
        due_date: datetime,
        priority: str,
        is_overdue: bool = False
    ) -> str:
        """
        Format ClickUp task notification
        
        Args:
            task_title: Task name
            due_date: When task is due
            priority: 'urgent', 'high', 'normal', 'low'
            is_overdue: True if past due date
        
        Returns:
            Formatted message text
        """
        emoji = "🔴" if is_overdue else "📋"
        status = "OVERDUE" if is_overdue else "Due Soon"
        
        due_str = due_date.strftime("%b %d at %I:%M %p").lstrip('0')
        
        return (
            f"{emoji} **Task {status}**\n\n"
            f"{task_title}\n"
            f"Due: {due_str}\n"
            f"Priority: {priority.title()}"
        )
    
    # ========================================================================
    # BLUESKY TRAINING NOTIFICATIONS
    # ========================================================================
    
    def format_bluesky_opportunity(
        self,
        account: str,
        post_preview: str,
        engagement_score: float,
        matched_keywords: list
    ) -> str:
        """
        Format Bluesky engagement opportunity for training
        
        Args:
            account: Account username
            post_preview: First 100 chars of post
            engagement_score: AI-calculated potential (0-1)
            matched_keywords: Keywords that matched
        
        Returns:
            Formatted message text
        """
        score_pct = int(engagement_score * 100)
        keywords_str = ", ".join(matched_keywords[:3])
        
        return (
            f"🔵 **Bluesky Opportunity**\n\n"
            f"Account: @{account}\n"
            f"Score: {score_pct}%\n"
            f"Keywords: {keywords_str}\n\n"
            f'"{post_preview}..."\n\n'
            f"Worth engaging?"
        )
    
    # ========================================================================
    # TRENDS TRAINING NOTIFICATIONS
    # ========================================================================
    
    def format_trends_opportunity(
        self,
        keyword: str,
        business_area: str,
        trend_score: int,
        content_opportunity: float
    ) -> str:
        """
        Format Google Trends keyword opportunity for training
        
        Args:
            keyword: Trending keyword
            business_area: Which business it's relevant to
            trend_score: Google Trends score (0-100)
            content_opportunity: AI-calculated opportunity (0-10)
        
        Returns:
            Formatted message text
        """
        return (
            f"📈 **Trending Keyword**\n\n"
            f"Keyword: {keyword}\n"
            f"Business: {business_area}\n"
            f"Trend Score: {trend_score}/100\n"
            f"Content Opportunity: {content_opportunity:.1f}/10\n\n"
            f"Create content for this?"
        )
    
    # ========================================================================
    # ANALYTICS NOTIFICATIONS
    # ========================================================================
    
    def format_analytics_anomaly(
        self,
        site_name: str,
        anomaly_type: str,
        details: Dict[str, Any]
    ) -> str:
        """
        Format analytics anomaly alert
        
        Args:
            site_name: Website name
            anomaly_type: 'traffic_drop', 'error_spike', 'ranking_drop'
            details: Anomaly data
        
        Returns:
            Formatted message text
        """
        if anomaly_type == 'traffic_drop':
            drop_pct = details.get('drop_percentage', 0)
            return (
                f"📊 **Traffic Anomaly**\n\n"
                f"Site: {site_name}\n"
                f"Traffic down {drop_pct}% vs 7-day average\n\n"
                f"Worth investigating."
            )
        
        elif anomaly_type == 'error_spike':
            error_count = details.get('error_count', 0)
            return (
                f"⚠️ **Error Spike**\n\n"
                f"Site: {site_name}\n"
                f"{error_count} new errors detected\n\n"
                f"Check Search Console."
            )
        
        elif anomaly_type == 'ranking_drop':
            keyword = details.get('keyword', 'Unknown')
            position_change = details.get('position_change', 0)
            return (
                f"📉 **Ranking Drop**\n\n"
                f"Site: {site_name}\n"
                f"Keyword: {keyword}\n"
                f"Dropped {position_change} positions\n\n"
                f"Review content."
            )
        
        return f"📊 **Analytics Alert**\n\nAnomaly detected on {site_name}"


# Global instance
_message_formatter = None

def get_message_formatter() -> MessageFormatter:
    """Get the global message formatter instance"""
    global _message_formatter
    if _message_formatter is None:
        _message_formatter = MessageFormatter()
    return _message_formatter