# modules/core/safe_logger.py
"""
SYNTAX PRIME V2 - THREAD-SAFE LOGGING MODULE
Created: 2025-01-13
Purpose: Prevent log interleaving from concurrent async operations

PROBLEM SOLVED:
When multiple async tasks (chat requests, intelligence collectors, background tasks)
write multi-line content to stdout simultaneously, Railway's log collector splits
by newlines and interleaves them at microsecond intervals, creating unreadable
"stream of consciousness" logs.

SOLUTION:
1. asyncio.Lock() ensures only one coroutine writes multi-line content at a time
2. Atomic logging keeps related lines together
3. Optional structured format for complex context blocks

USAGE:
    from modules.core.safe_logger import get_safe_logger, atomic_log, log_context_block
    
    # For regular logging (unchanged)
    logger = get_safe_logger(__name__)
    logger.info("Single line message")
    
    # For multi-line content that must stay together
    await atomic_log("Line 1\\nLine 2\\nLine 3", level="info")
    
    # For large context blocks (memory context, diagnostics, etc.)
    await log_context_block("MEMORY CONTEXT", formatted_context, logger_name=__name__)
"""

import asyncio
import logging
import sys
import json
from typing import Optional, Any, Dict
from datetime import datetime
from functools import wraps

# =============================================================================
# CONFIGURATION
# =============================================================================

# Global lock for atomic multi-line logging
_log_lock = asyncio.Lock()

# Track if safe logger has been initialized
_initialized = False

# Default log level (can be overridden by environment)
DEFAULT_LOG_LEVEL = logging.DEBUG

# Maximum lines before truncating in atomic logs (prevents massive log dumps)
MAX_ATOMIC_LINES = 500

# Separator used to keep multi-line content together in structured mode
MULTILINE_SEPARATOR = " ⏎ "  # Visual newline indicator that doesn't split logs


# =============================================================================
# LOGGER INITIALIZATION
# =============================================================================

def init_safe_logging(
    level: int = DEFAULT_LOG_LEVEL,
    format_string: str = None,
    use_structured: bool = False
) -> logging.Logger:
    """
    Initialize the safe logging system.
    
    Call this once at application startup (in app.py) to configure logging.
    
    Args:
        level: Logging level (default: DEBUG)
        format_string: Custom format string (optional)
        use_structured: If True, use JSON structured logging
        
    Returns:
        Root logger instance
    """
    global _initialized
    
    if _initialized:
        return logging.getLogger()
    
    # Default format with timestamp and level
    if format_string is None:
        format_string = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Create stdout handler
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(level)
    
    if use_structured:
        # JSON formatter for structured logging
        handler.setFormatter(StructuredFormatter())
    else:
        # Standard formatter
        handler.setFormatter(logging.Formatter(format_string))
    
    root_logger.addHandler(handler)
    
    _initialized = True
    root_logger.info("🔒 Safe logging initialized (thread-safe multi-line support enabled)")
    
    return root_logger


def get_safe_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with safe logging capabilities.
    
    This is a drop-in replacement for logging.getLogger().
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# =============================================================================
# STRUCTURED FORMATTER (Optional JSON output)
# =============================================================================

class StructuredFormatter(logging.Formatter):
    """
    JSON formatter that keeps multi-line content together.
    
    Instead of splitting by newlines, wraps the entire message in JSON
    so Railway treats it as a single log entry.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_entry["data"] = record.extra_data
        
        return json.dumps(log_entry, ensure_ascii=False)


# =============================================================================
# ATOMIC LOGGING FUNCTIONS
# =============================================================================

async def atomic_log(
    message: str,
    level: str = "info",
    logger_name: str = None,
    truncate: bool = True
) -> None:
    """
    Log a message atomically, preventing interleaving with other async tasks.
    
    Use this for multi-line content that must stay together in logs.
    
    Args:
        message: The message to log (can be multi-line)
        level: Log level ("debug", "info", "warning", "error", "critical")
        logger_name: Optional logger name (defaults to root)
        truncate: If True, truncate very long messages
    """
    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    log_func = getattr(logger, level.lower(), logger.info)
    
    # Truncate if too long
    if truncate:
        lines = message.split('\n')
        if len(lines) > MAX_ATOMIC_LINES:
            message = '\n'.join(lines[:MAX_ATOMIC_LINES])
            message += f"\n... [TRUNCATED - {len(lines) - MAX_ATOMIC_LINES} more lines]"
    
    # Acquire lock and log atomically
    async with _log_lock:
        # Log each line separately but within the lock
        # This ensures all lines from this message complete before another task logs
        for line in message.split('\n'):
            if line.strip():  # Skip empty lines
                log_func(line)


async def log_context_block(
    title: str,
    content: str,
    logger_name: str = None,
    level: str = "info",
    max_chars: int = 10000
) -> None:
    """
    Log a large context block (like memory context) atomically.
    
    This is specifically designed for the memory query layer and similar
    modules that generate large formatted context strings.
    
    Args:
        title: Block title (e.g., "MEMORY CONTEXT", "DIAGNOSTIC REPORT")
        content: The content to log
        logger_name: Optional logger name
        level: Log level
        max_chars: Maximum characters to log (truncates if exceeded)
    """
    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    log_func = getattr(logger, level.lower(), logger.info)
    
    # Truncate if too long
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n... [TRUNCATED - {len(content) - max_chars} more chars]"
    
    # Build the block
    separator = "=" * 80
    
    async with _log_lock:
        log_func(separator)
        log_func(f"📋 {title}")
        log_func(separator)
        
        # Log content line by line within the lock
        for line in content.split('\n'):
            log_func(line)
        
        log_func(separator)


def log_context_block_sync(
    title: str,
    content: str,
    logger_name: str = None,
    level: str = "info",
    max_chars: int = 10000
) -> None:
    """
    Synchronous version of log_context_block for non-async contexts.
    
    Note: This doesn't use the async lock, so it's less safe in highly
    concurrent scenarios, but works in synchronous code paths.
    """
    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    log_func = getattr(logger, level.lower(), logger.info)
    
    # Truncate if too long
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n... [TRUNCATED - {len(content) - max_chars} more chars]"
    
    # Build summary instead of full dump
    line_count = len(content.split('\n'))
    char_count = len(content)
    
    separator = "=" * 80
    log_func(separator)
    log_func(f"📋 {title} ({line_count} lines, {char_count} chars)")
    log_func(separator)
    
    # For sync logging, just log a summary to avoid interleaving
    # The full content is available in the context, not needed in logs
    preview_lines = content.split('\n')[:10]
    for line in preview_lines:
        log_func(f"  {line[:200]}")
    
    if line_count > 10:
        log_func(f"  ... [{line_count - 10} more lines]")
    
    log_func(separator)


# =============================================================================
# SUMMARY LOGGING (Preferred for large content)
# =============================================================================

def log_summary(
    title: str,
    stats: Dict[str, Any],
    logger_name: str = None,
    level: str = "info"
) -> None:
    """
    Log a summary of large content instead of the full content.
    
    This is the PREFERRED approach for memory context, diagnostics, etc.
    Instead of logging 300 conversation messages, log:
    - Count of messages
    - Count of threads
    - Character count
    - Time range
    
    Args:
        title: Summary title
        stats: Dictionary of statistics to log
        logger_name: Optional logger name
        level: Log level
    """
    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    log_func = getattr(logger, level.lower(), logger.info)
    
    # Format as single line for Railway
    stats_str = " | ".join(f"{k}: {v}" for k, v in stats.items())
    log_func(f"📊 {title} | {stats_str}")


# =============================================================================
# DECORATOR FOR ASYNC FUNCTIONS WITH LOGGING
# =============================================================================

def atomic_logging(func):
    """
    Decorator that wraps an async function's logging in the atomic lock.
    
    Use this on functions that do heavy logging of multi-line content.
    
    Usage:
        @atomic_logging
        async def my_function():
            logger.info("Line 1")
            logger.info("Line 2")
            # All logging in this function will be atomic
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with _log_lock:
            return await func(*args, **kwargs)
    return wrapper


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'init_safe_logging',
    'get_safe_logger',
    'atomic_log',
    'log_context_block',
    'log_context_block_sync',
    'log_summary',
    'atomic_logging',
    'StructuredFormatter',
    '_log_lock',  # Exported so modules can use the lock directly if needed
]