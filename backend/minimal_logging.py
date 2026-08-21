"""
Ultra-minimal logging configuration for clean conversation output
"""
import logging
import sys
import os
from io import StringIO

class NullHandler(logging.Handler):
    """Handler that discards all log records"""
    def emit(self, record):
        pass

def setup_minimal_logging():
    """Configure logging to show only essential conversation information"""
    
    # Custom filter to suppress memory warnings globally
    class MemoryWarningFilter(logging.Filter):
        def filter(self, record):
            # Filter out memory usage warnings from any logger
            try:
                message = record.getMessage()
                # Check for memory warning patterns
                if "process memory usage is high" in message:
                    return False
                if "memory_usage_mb" in message:
                    return False
                if "memory_warn_mb" in message:
                    return False
                if "memory_limit_mb" in message:
                    return False
                # Also check the raw log record args
                if hasattr(record, 'args') and record.args:
                    args_str = str(record.args)
                    if "memory_usage_mb" in args_str or "memory_warn_mb" in args_str:
                        return False
            except:
                # If there's any error processing the record, allow it through
                pass
            return True
    
    # Get root logger and set it to a high level to suppress most messages
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.CRITICAL)
    
    # Add memory warning filter to root logger to catch any stragglers
    root_logger.addFilter(MemoryWarningFilter())
    
    # Remove all existing handlers from root logger
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create our custom conversation logger that will bypass the root suppression
    conversation_logger = logging.getLogger("conversation")
    conversation_logger.setLevel(logging.INFO)
    conversation_logger.propagate = False  # Don't propagate to root logger
    
    # Remove any existing handlers
    for handler in conversation_logger.handlers[:]:
        conversation_logger.removeHandler(handler)
    
    # Custom formatter for clean conversation output
    class ConversationFormatter(logging.Formatter):
        def format(self, record):
            return record.getMessage()
    
    # Add clean handler for conversation messages only
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ConversationFormatter())
    conversation_logger.addHandler(handler)
    
    # Suppress specific noisy loggers completely
    noisy_loggers = [
        "livekit", "livekit.agents", "livekit_api", "livekit_ffi",
        "httpx", "urllib3", "requests", "asyncio", "faster_whisper",
        "ctranslate2", "transformers", "tungstenite"
    ]
    
    for logger_name in noisy_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL + 1)  # Higher than CRITICAL to suppress everything
        logger.disabled = True
        # Also add memory warning filter to any remaining logs
        logger.addFilter(MemoryWarningFilter())
    
    print("🎧 Ultra-clean conversation mode enabled - showing only conversation flow")
    
    return conversation_logger