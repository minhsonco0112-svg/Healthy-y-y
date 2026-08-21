"""
Monkey patch to suppress memory usage warnings from LiveKit agents
"""
import logging
import sys
from functools import wraps

# Store original warning method
_original_warning = logging.Logger.warning

def patched_warning(self, message, *args, **kwargs):
    """Patched warning method that filters out memory usage warnings"""
    try:
        # Format the message if it has args
        if args:
            formatted_message = message % args
        else:
            formatted_message = str(message)
        
        # Check if this is a memory usage warning
        if ("memory usage is high" in formatted_message or 
            "memory_usage_mb" in formatted_message or
            "memory_warn_mb" in formatted_message):
            return  # Suppress the warning
            
    except:
        pass  # If formatting fails, let it through
    
    # Call original warning method for non-memory warnings
    return _original_warning(self, message, *args, **kwargs)

def suppress_memory_warnings():
    """Apply the memory warning suppression patch"""
    logging.Logger.warning = patched_warning
    print("🔇 Memory usage warnings suppressed")

# Auto-apply when imported
suppress_memory_warnings()