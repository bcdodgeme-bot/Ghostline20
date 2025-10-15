# modules/integrations/telegram/bot_client.py
"""
Telegram Bot Client - Core API Wrapper
Handles all communication with Telegram Bot API
"""

import logging
import aiohttp
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class TelegramBotClient:
    """Wrapper for Telegram Bot API operations"""
    
    def __init__(self, bot_token: str):
        """
        Initialize Telegram bot client
        
        Args:
            bot_token: Telegram bot token from BotFather
        """
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        if not bot_token:
            raise ValueError("bot_token is required")
        
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
        import os
        
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
