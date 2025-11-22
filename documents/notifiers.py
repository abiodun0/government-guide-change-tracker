"""
Notification system for document changes.
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import date

from .models import Document, DocumentVersion, DocumentSource

logger = logging.getLogger(__name__)


class ChangeEvent:
    """Represents a change event in a document."""
    
    def __init__(
        self,
        document: Document,
        event_type: str,  # 'new_version', 'new_document', 'updated_document'
        version: Optional[DocumentVersion] = None,
        previous_version: Optional[DocumentVersion] = None,
        change_reason: Optional[str] = None
    ):
        self.document = document
        self.event_type = event_type
        self.version = version
        self.previous_version = previous_version
        self.change_reason = change_reason  # e.g., 'pdf_hash_changed', 'new_published_date'
    
    def __repr__(self):
        return f"ChangeEvent(type={self.event_type}, document={self.document.title}, reason={self.change_reason})"


class BaseNotifier(ABC):
    """Base class for notifiers."""
    
    @abstractmethod
    def notify(self, events: List[ChangeEvent]) -> bool:
        """
        Send notifications for change events.
        
        Args:
            events: List of change events to notify about
            
        Returns:
            True if notification was successful, False otherwise
        """
        pass
    
    def format_message(self, events: List[ChangeEvent]) -> str:
        """Format change events into a human-readable message."""
        if not events:
            return "No changes detected."
        
        lines = [f"Found {len(events)} change(s):\n"]
        
        for event in events:
            source_name = event.document.source.name
            doc_title = event.document.title
            
            if event.event_type == 'new_document':
                lines.append(f"📄 NEW DOCUMENT: {source_name} - {doc_title}")
                if event.version and event.version.published_date:
                    lines.append(f"   Published: {event.version.published_date}")
                if event.version:
                    lines.append(f"   URL: {event.version.pdf_url}")
            
            elif event.event_type == 'new_version':
                lines.append(f"🔄 NEW VERSION: {source_name} - {doc_title}")
                if event.change_reason:
                    lines.append(f"   Reason: {event.change_reason}")
                if event.previous_version and event.previous_version.published_date:
                    lines.append(f"   Previous: {event.previous_version.published_date}")
                if event.version and event.version.published_date:
                    lines.append(f"   New: {event.version.published_date}")
                if event.version:
                    lines.append(f"   URL: {event.version.pdf_url}")
            
            elif event.event_type == 'updated_document':
                lines.append(f"✏️  UPDATED: {source_name} - {doc_title}")
                if event.change_reason:
                    lines.append(f"   Changes: {event.change_reason}")
            
            lines.append("")  # Empty line between events
        
        return "\n".join(lines)


class LoggingNotifier(BaseNotifier):
    """Notifier that logs changes to the application log."""
    
    def notify(self, events: List[ChangeEvent]) -> bool:
        """Log change events."""
        if not events:
            return True
        
        message = self.format_message(events)
        logger.info(f"Document changes detected:\n{message}")
        return True


class ConsoleNotifier(BaseNotifier):
    """Notifier that prints changes to console (useful for testing)."""
    
    def notify(self, events: List[ChangeEvent]) -> bool:
        """Print change events to console."""
        if not events:
            return True
        
        message = self.format_message(events)
        print(message)
        return True


class EmailNotifier(BaseNotifier):
    """Notifier that sends email notifications (placeholder for future implementation)."""
    
    def __init__(self, recipient_emails: List[str]):
        self.recipient_emails = recipient_emails
    
    def notify(self, events: List[ChangeEvent]) -> bool:
        """Send email notifications (to be implemented)."""
        if not events:
            return True
        
        message = self.format_message(events)
        # TODO: Implement email sending
        logger.info(f"Email notification would be sent to {self.recipient_emails}:\n{message}")
        return True


class WebhookNotifier(BaseNotifier):
    """Notifier that sends webhook notifications (placeholder for future implementation)."""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def notify(self, events: List[ChangeEvent]) -> bool:
        """Send webhook notifications (to be implemented)."""
        if not events:
            return True
        
        # TODO: Implement webhook sending
        logger.info(f"Webhook notification would be sent to {self.webhook_url}")
        return True


class CompositeNotifier(BaseNotifier):
    """Notifier that combines multiple notifiers."""
    
    def __init__(self, notifiers: List[BaseNotifier]):
        self.notifiers = notifiers
    
    def notify(self, events: List[ChangeEvent]) -> bool:
        """Notify using all registered notifiers."""
        if not events:
            return True
        
        results = []
        for notifier in self.notifiers:
            try:
                result = notifier.notify(events)
                results.append(result)
            except Exception as e:
                logger.error(f"Notifier {notifier.__class__.__name__} failed: {e}")
                results.append(False)
        
        return all(results)


def get_default_notifier() -> BaseNotifier:
    """Get the default notifier (logging)."""
    return LoggingNotifier()

