# modules/integrations/telegram/bot_client.py
"""
Telegram Bot Client - Core API Wrapper
Handles all communication with Telegram Bot API

UPDATED: Added sanitize_markdown() to fix parse errors from unbalanced * and _
"""

import logging
import os
import re
from typing import Dict, List, Optional, Any

import aiohttp

logger = logging.getLogger(__name__)


# ============================================================================
# MARKDOWN SANITIZATION
# ============================================================================

def sanitize_markdown(text: str) -> str:
    """
    Sanitize text for Telegram Markdown to prevent parse errors.
    
    Telegram's Markdown parser fails on:
    - Unbalanced * (bold markers)
    - Unbalanced _ (italic markers)
    - Unclosed formatting entities
    
    This function ensures all formatting markers are properly paired.
    
    Args:
        text: Raw message text that may have unbalanced markdown
        
    Returns:
        Sanitized text safe for Telegram Markdown parsing
    """
    if not text:
        return text
    
    # Strategy: Count markers and remove unpaired ones
    # We process * and _ separately
    
    result = text
    
    # Fix unbalanced asterisks (bold)
    result = _balance_markers(result, '*')
    
    # Fix unbalanced underscores (italic)
    result = _balance_markers(result, '_')
    
    return result


def _balance_markers(text: str, marker: str) -> str:
    """
    Balance a specific markdown marker in text.
    
    For single markers (* or _), ensures they come in pairs.
    Removes trailing unpaired markers.
    
    Args:
        text: Text to process
        marker: The marker character (* or _)
        
    Returns:
        Text with balanced markers
    """
    if marker not in text:
        return text
    
    # Split text by the marker
    parts = text.split(marker)
    
    # If odd number of parts, we have balanced markers (n markers = n+1 parts)
    # If even number of parts, we have unbalanced markers
    if len(parts) % 2 == 0:
        # Unbalanced - we have an odd number of markers
        # Find and remove the last unpaired marker by joining without it
        # This effectively removes the last marker
        
        # Actually, let's be smarter: escape the problematic markers
        # by finding positions and escaping lone ones
        
        # Simple approach: if unbalanced, escape ALL markers
        # This is safe - message will display with literal * or _
        escaped_marker = '\\' + marker
        return text.replace(marker, escaped_marker)
    
    return text


def sanitize_markdown_v2(text: str) -> str:
    """
    More aggressive sanitization - escapes all special characters
    for MarkdownV2 mode (not currently used, but available).
    
    In MarkdownV2, these must be escaped: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    result = text
    for char in special_chars:
        result = result.replace(char, '\\' + char)
    return result


class TelegramBotClient:
    """Wrapper for Telegram Bot API operations"""
    
    def __init__(self, bot_token: str):
        """
        Initialize Telegram bot client
        
        Args:
            bot_token: Telegram bot token from BotFather
        """
        if not bot_token:
            raise ValueError("bot_token is required")
            
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        logger.info("Telegram Bot Client initialized")
    
    def create_inline_keyboard(self, buttons: List[List[Dict[str, str]]]) -> Dict:
        """
        Create inline keyboard markup
        
        Args:
            buttons: 2D array of button dicts with 'text' and 'callback_data'
            Example: [[{"text": "✅ Done", "callback_data": "action:done"}]]
        
        Returns:
            Inline keyboard markup dict for Telegram API
        """
        return {
            "inline_keyboard": buttons
        }
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to Telegram API
        
        Returns:
            Dict with 'success' bool and 'bot_info' or 'error'
        """
        try:
            bot_info = await self.get_me()
            return {
                'success': True,
                'bot_info': bot_info
            }
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_me(self) -> Dict[str, Any]:
        """
        Get bot information (useful for testing connection)
        
        Returns:
            Bot info including username
        """
        url = f"{self.base_url}/getMe"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('result', {})
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to get bot info: {error_text}")
                    raise Exception(f"Telegram API error: {error_text}")
    
    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: Optional[Dict] = None,
        parse_mode: str = "Markdown"
    ) -> Dict[str, Any]:
        """
        Send a text message
        
        Args:
            chat_id: Target chat ID
            text: Message text (supports Markdown or HTML)
            reply_markup: Optional inline keyboard buttons
            parse_mode: "Markdown" or "HTML"
        
        Returns:
            Response from Telegram API including message_id
        """
        url = f"{self.base_url}/sendMessage"
        
        # Sanitize markdown to prevent parse errors
        if parse_mode == "Markdown":
            text = sanitize_markdown(text)
        
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        message_id = result.get('result', {}).get('message_id')
                        logger.info(f"Message sent successfully (ID: {message_id})")
                        return result.get('result', {})
                    else:
                        error_text = await response.text()
                        
                        # If markdown parse failed, retry without parse_mode
                        if "can't parse entities" in error_text.lower():
                            logger.warning(f"Markdown parse failed, retrying without formatting")
                            payload["parse_mode"] = None
                            del payload["parse_mode"]
                            
                            async with session.post(url, json=payload) as retry_response:
                                if retry_response.status == 200:
                                    result = await retry_response.json()
                                    message_id = result.get('result', {}).get('message_id')
                                    logger.info(f"Message sent successfully without formatting (ID: {message_id})")
                                    return result.get('result', {})
                                else:
                                    retry_error = await retry_response.text()
                                    logger.error(f"Retry also failed: {retry_error}")
                                    raise Exception(f"Telegram API error: {retry_error}")
                        
                        logger.error(f"Failed to send message: {error_text}")
                        raise Exception(f"Telegram API error: {error_text}")
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            raise
    
    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
    ) -> bool:
        """
        Answer a callback query (button click)
        
        Args:
            callback_query_id: ID from callback query
            text: Optional notification text to show user
            show_alert: Show as alert instead of notification
        
        Returns:
            True if successful
        """
        url = f"{self.base_url}/answerCallbackQuery"
        
        payload = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert
        }
        
        if text:
            payload["text"] = text
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info("Callback query answered")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to answer callback: {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Error answering callback query: {e}")
            return False
    
    async def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict] = None,
        parse_mode: str = "Markdown"
    ) -> bool:
        """
        Edit an existing message
        
        Args:
            chat_id: Target chat ID
            message_id: Message ID to edit
            text: New message text
            reply_markup: Optional new inline keyboard
            parse_mode: "Markdown" or "HTML"
        
        Returns:
            True if successful
        """
        url = f"{self.base_url}/editMessageText"
        
        # Sanitize markdown to prevent parse errors
        if parse_mode == "Markdown":
            text = sanitize_markdown(text)
        
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Message {message_id} edited successfully")
                        return True
                    else:
                        error_text = await response.text()
                        
                        # If markdown parse failed, retry without parse_mode
                        if "can't parse entities" in error_text.lower():
                            logger.warning(f"Markdown parse failed on edit, retrying without formatting")
                            del payload["parse_mode"]
                            
                            async with session.post(url, json=payload) as retry_response:
                                if retry_response.status == 200:
                                    logger.info(f"Message {message_id} edited successfully without formatting")
                                    return True
                                else:
                                    retry_error = await retry_response.text()
                                    logger.error(f"Edit retry also failed: {retry_error}")
                                    return False
                        
                        logger.error(f"Failed to edit message: {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            return False
            
    async def edit_message(
        self,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict] = None
    ) -> bool:
        """
        Convenience wrapper for edit_message_text
        Automatically uses TELEGRAM_CHAT_ID from environment
        
        Args:
            message_id: Message ID to edit
            text: New message text
            reply_markup: Optional new inline keyboard
        
        Returns:
            True if successful
        """
        # Get chat_id from environment
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if not chat_id:
            logger.error("TELEGRAM_CHAT_ID not set in environment")
            return False
        
        # Call the full edit_message_text method
        return await self.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup
        )
        
    async def delete_message(self, chat_id: str, message_id: int) -> bool:
        """
        Delete a message
        
        Args:
            chat_id: Target chat ID
            message_id: Message ID to delete
        
        Returns:
            True if successful
        """
        url = f"{self.base_url}/deleteMessage"
        
        payload = {
            "chat_id": chat_id,
            "message_id": message_id
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Message {message_id} deleted successfully")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to delete message: {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            return False


# Global singleton instance
_bot_client: Optional[TelegramBotClient] = None


def get_bot_client() -> TelegramBotClient:
    """
    Get the global Telegram bot client instance (singleton pattern)
    
    Returns:
        TelegramBotClient instance
        
    Raises:
        ValueError: If TELEGRAM_BOT_TOKEN environment variable is not set
    """
    global _bot_client
    
    if _bot_client is None:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN environment variable is not set. "
                "Please configure it in your Railway environment."
            )
        _bot_client = TelegramBotClient(bot_token)
    
    return _bot_client


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    'TelegramBotClient',
    'get_bot_client',
    'sanitize_markdown',
    'sanitize_markdown_v2'
]
