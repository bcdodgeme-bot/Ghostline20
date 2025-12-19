# modules/integrations/telegram/bot_client.py
"""
Telegram Bot Client - Core API Wrapper
Handles all communication with Telegram Bot API

UPDATED: 
- Added sanitize_markdown() to fix parse errors from unbalanced * and _
- Added buttons parameter convenience for send_message and edit_message_text
- Improved return values with success key
- Added webhook management methods
"""

import logging
import os
import re
from typing import Dict, List, Optional, Any, Union

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
        Create inline keyboard markup from button definitions.
        
        Args:
            buttons: 2D array of button dicts with 'text' and either:
                    - 'callback_data' for action buttons
                    - 'url' for link buttons
            Example: [[{"text": "✅ Done", "callback_data": "action:done"}]]
                    [[{"text": "🔗 Open", "url": "https://example.com"}]]
        
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
        chat_id: Union[str, int],
        text: str,
        reply_markup: Optional[Dict] = None,
        buttons: Optional[List[List[Dict[str, str]]]] = None,
        parse_mode: str = "Markdown"
    ) -> Dict[str, Any]:
        """
        Send a text message
        
        Args:
            chat_id: Target chat ID
            text: Message text (supports Markdown or HTML)
            reply_markup: Optional inline keyboard (raw format)
            buttons: Optional inline keyboard (convenience format - will be converted)
            parse_mode: "Markdown", "MarkdownV2", or "HTML"
        
        Returns:
            Dict with 'success', 'message_id', and raw 'result'
        """
        url = f"{self.base_url}/sendMessage"
        
        # Sanitize markdown to prevent parse errors (only for Markdown, not MarkdownV2)
        if parse_mode == "Markdown":
            text = sanitize_markdown(text)
        
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        # Handle buttons convenience parameter
        if buttons and not reply_markup:
            reply_markup = self.create_inline_keyboard(buttons)
        
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        telegram_result = result.get('result', {})
                        message_id = telegram_result.get('message_id')
                        logger.info(f"Message sent successfully (ID: {message_id})")
                        return {
                            'success': True,
                            'message_id': message_id,
                            'result': telegram_result
                        }
                    else:
                        error_text = await response.text()
                        
                        # If markdown parse failed, retry without parse_mode
                        if "can't parse entities" in error_text.lower():
                            logger.warning(f"Markdown parse failed, retrying without formatting")
                            del payload["parse_mode"]
                            
                            async with session.post(url, json=payload) as retry_response:
                                if retry_response.status == 200:
                                    result = await retry_response.json()
                                    telegram_result = result.get('result', {})
                                    message_id = telegram_result.get('message_id')
                                    logger.info(f"Message sent successfully without formatting (ID: {message_id})")
                                    return {
                                        'success': True,
                                        'message_id': message_id,
                                        'result': telegram_result,
                                        'formatting_stripped': True
                                    }
                                else:
                                    retry_error = await retry_response.text()
                                    logger.error(f"Retry also failed: {retry_error}")
                                    return {
                                        'success': False,
                                        'error': retry_error
                                    }
                        
                        logger.error(f"Failed to send message: {error_text}")
                        return {
                            'success': False,
                            'error': error_text
                        }
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
    ) -> bool:
        """
        Answer a callback query (button click).
        This removes the "loading" spinner on the button.
        
        Args:
            callback_query_id: ID from callback query
            text: Optional notification text to show user (toast or alert)
            show_alert: If True, show as popup alert; if False, show as toast
        
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
                        logger.debug(f"Callback query answered: {text or 'no text'}")
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
        chat_id: Union[str, int],
        message_id: int,
        text: str,
        reply_markup: Optional[Dict] = None,
        buttons: Optional[List[List[Dict[str, str]]]] = None,
        parse_mode: str = "Markdown"
    ) -> bool:
        """
        Edit an existing message's text and/or buttons.
        
        Args:
            chat_id: Target chat ID
            message_id: Message ID to edit
            text: New message text
            reply_markup: Optional new inline keyboard (raw format)
            buttons: Optional new inline keyboard (convenience format)
                    Pass empty list [] to remove buttons
                    Pass None to keep existing buttons
            parse_mode: "Markdown", "MarkdownV2", or "HTML"
        
        Returns:
            True if successful
        """
        url = f"{self.base_url}/editMessageText"
        
        # Sanitize markdown to prevent parse errors (only for Markdown, not MarkdownV2)
        if parse_mode == "Markdown":
            text = sanitize_markdown(text)
        
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        # Handle buttons convenience parameter
        if buttons is not None and not reply_markup:
            if buttons:  # Non-empty list
                reply_markup = self.create_inline_keyboard(buttons)
            else:  # Empty list - remove buttons
                reply_markup = {"inline_keyboard": []}
        
        if reply_markup is not None:
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
                        
                        # "message is not modified" is not really an error
                        if "message is not modified" in error_text.lower():
                            logger.debug(f"Message {message_id} was not modified (content unchanged)")
                            return True
                        
                        logger.error(f"Failed to edit message: {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            return False
            
    async def edit_message(
        self,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict] = None,
        buttons: Optional[List[List[Dict[str, str]]]] = None
    ) -> bool:
        """
        Convenience wrapper for edit_message_text.
        Automatically uses TELEGRAM_CHAT_ID from environment.
        
        Args:
            message_id: Message ID to edit
            text: New message text
            reply_markup: Optional new inline keyboard (raw format)
            buttons: Optional new inline keyboard (convenience format)
        
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
            reply_markup=reply_markup,
            buttons=buttons
        )
    
    async def edit_message_reply_markup(
        self,
        chat_id: Union[str, int],
        message_id: int,
        reply_markup: Optional[Dict] = None,
        buttons: Optional[List[List[Dict[str, str]]]] = None
    ) -> bool:
        """
        Edit only the inline keyboard of a message (not the text).
        
        Args:
            chat_id: Target chat ID
            message_id: Message ID to edit
            reply_markup: New inline keyboard (raw format)
            buttons: New inline keyboard (convenience format)
                    Pass empty list [] to remove buttons
        
        Returns:
            True if successful
        """
        url = f"{self.base_url}/editMessageReplyMarkup"
        
        payload = {
            "chat_id": chat_id,
            "message_id": message_id
        }
        
        # Handle buttons convenience parameter
        if buttons is not None and not reply_markup:
            if buttons:
                reply_markup = self.create_inline_keyboard(buttons)
            else:
                reply_markup = {"inline_keyboard": []}
        
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Message {message_id} reply markup edited")
                        return True
                    else:
                        error_text = await response.text()
                        
                        # "message is not modified" is not really an error
                        if "message is not modified" in error_text.lower():
                            logger.debug(f"Message {message_id} markup was not modified")
                            return True
                        
                        logger.error(f"Failed to edit message markup: {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Error editing message markup: {e}")
            return False
        
    async def delete_message(self, chat_id: Union[str, int], message_id: int) -> bool:
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
    
    async def set_webhook(self, url: str, drop_pending_updates: bool = False) -> Dict[str, Any]:
        """
        Set webhook URL for receiving updates.
        
        Args:
            url: HTTPS URL to receive updates
            drop_pending_updates: Whether to drop pending updates
        
        Returns:
            Dict with success status
        """
        api_url = f"{self.base_url}/setWebhook"
        
        payload = {
            "url": url,
            "drop_pending_updates": drop_pending_updates
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as response:
                    result = await response.json()
                    if response.status == 200 and result.get('ok'):
                        logger.info(f"Webhook set to: {url}")
                        return {'success': True, 'result': result}
                    else:
                        logger.error(f"Failed to set webhook: {result}")
                        return {'success': False, 'error': result}
        except Exception as e:
            logger.error(f"Error setting webhook: {e}")
            return {'success': False, 'error': str(e)}
    
    async def delete_webhook(self, drop_pending_updates: bool = False) -> Dict[str, Any]:
        """
        Remove webhook integration.
        
        Args:
            drop_pending_updates: Whether to drop pending updates
        
        Returns:
            Dict with success status
        """
        url = f"{self.base_url}/deleteWebhook"
        
        payload = {
            "drop_pending_updates": drop_pending_updates
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    result = await response.json()
                    if response.status == 200 and result.get('ok'):
                        logger.info("Webhook deleted")
                        return {'success': True, 'result': result}
                    else:
                        logger.error(f"Failed to delete webhook: {result}")
                        return {'success': False, 'error': result}
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_webhook_info(self) -> Dict[str, Any]:
        """
        Get current webhook status.
        
        Returns:
            Dict with webhook info
        """
        url = f"{self.base_url}/getWebhookInfo"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    result = await response.json()
                    if response.status == 200:
                        return {
                            'success': True,
                            'webhook_url': result.get('result', {}).get('url', ''),
                            'pending_update_count': result.get('result', {}).get('pending_update_count', 0),
                            'result': result.get('result', {})
                        }
                    else:
                        return {'success': False, 'error': result}
        except Exception as e:
            logger.error(f"Error getting webhook info: {e}")
            return {'success': False, 'error': str(e)}


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
