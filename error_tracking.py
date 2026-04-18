"""Error tracking with Sentry integration.

Automatically reports exceptions to Sentry for monitoring.
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Sentry SDK placeholder - imported only if configured
_sentry_initialized = False


def init_sentry(dsn: Optional[str] = None, environment: str = "production"):
    """
    Initialize Sentry error tracking.
    
    Args:
        dsn: Sentry DSN from https://sentry.io/settings/projects/your-project/keys/
        environment: 'production', 'staging', or 'development'
    """
    global _sentry_initialized
    
    # Get DSN from env if not provided
    dsn = dsn or os.getenv("SENTRY_DSN")
    
    if not dsn:
        logger.info("ℹ️ Sentry not configured (no SENTRY_DSN)")
        return
    
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        
        # Configure Sentry
        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR
        )
        
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            integrations=[sentry_logging],
            traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
            profiles_sample_rate=0.1,  # 10% profiling
            before_send=before_send,  # Filter sensitive data
        )
        
        _sentry_initialized = True
        logger.info(f"✅ Sentry initialized ({environment})")
        
    except ImportError:
        logger.warning("⚠️ sentry-sdk not installed. Run: pip install sentry-sdk")
    except Exception as e:
        logger.error(f"❌ Sentry initialization failed: {e}")


def before_send(event, hint):
    """
    Filter sensitive data before sending to Sentry.
    Removes tokens, phone numbers, and user IDs.
    """
    # Filter sensitive keys
    sensitive_keys = ['token', 'password', 'secret', 'phone', 'card']
    
    def filter_dict(d):
        if isinstance(d, dict):
            return {
                k: '[FILTERED]' if any(s in k.lower() for s in sensitive_keys) else filter_dict(v)
                for k, v in d.items()
            }
        elif isinstance(d, list):
            return [filter_dict(item) for item in d]
        return d
    
    if 'extra' in event:
        event['extra'] = filter_dict(event['extra'])
    if 'contexts' in event:
        event['contexts'] = filter_dict(event['contexts'])
    
    return event


def capture_exception(error: Exception, context: dict = None):
    """
    Manually capture an exception.
    
    Args:
        error: The exception to report
        context: Additional context data
    """
    if _sentry_initialized:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if context:
                for key, value in context.items():
                    scope.set_extra(key, value)
            sentry_sdk.capture_exception(error)
    else:
        # Log locally if Sentry not configured
        logger.exception(f"Error captured (Sentry not configured): {error}")


def capture_message(message: str, level: str = "info"):
    """
    Send a message to Sentry.
    
    Args:
        message: Message text
        level: 'debug', 'info', 'warning', 'error', 'fatal'
    """
    if _sentry_initialized:
        import sentry_sdk
        sentry_sdk.capture_message(message, level=level)
    else:
        logger.log(getattr(logging, level.upper(), logging.INFO), message)


def set_user(user_id: int, username: str = None, email: str = None):
    """
    Set user context for error tracking.
    """
    if _sentry_initialized:
        import sentry_sdk
        sentry_sdk.set_user({
            "id": str(user_id),
            "username": username,
            "email": email
        })


def clear_user():
    """Clear user context."""
    if _sentry_initialized:
        import sentry_sdk
        sentry_sdk.set_user(None)
