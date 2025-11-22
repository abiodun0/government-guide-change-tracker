"""
Celery tasks for document processing.
"""
from celery import shared_task
from django.db import transaction

from .services import process_document_source, DocumentFetchError
from .notifiers import get_default_notifier
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def fetch_and_process_document_source(self, source_id: int, fetch_pdfs: bool = True):
    """
    Celery task to fetch and process a document source asynchronously.
    
    Args:
        source_id: ID of the DocumentSource to process
        fetch_pdfs: If True, fetch PDFs to calculate hashes (slower)
        
    Returns:
        Processing results dictionary
    """
    try:
        results = process_document_source(source_id, fetch_pdfs=fetch_pdfs)
        logger.info(f"Successfully processed document source {source_id}: {results}")
        return results
    except DocumentFetchError as e:
        logger.error(f"Failed to process document source {source_id}: {e}")
        # Retry on fetch errors
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
    except Exception as e:
        logger.error(f"Unexpected error processing document source {source_id}: {e}")
        raise


@shared_task
def process_all_active_sources(fetch_pdfs: bool = False):
    """
    Process all active document sources.
    
    Args:
        fetch_pdfs: If True, fetch PDFs to calculate hashes
    """
    from .models import DocumentSource
    
    active_sources = DocumentSource.objects.filter(active=True)
    results = []
    
    for source in active_sources:
        try:
            result = fetch_and_process_document_source.delay(source.id, fetch_pdfs=fetch_pdfs)
            results.append({
                'source_id': source.id,
                'source_name': source.name,
                'task_id': result.id
            })
        except Exception as e:
            logger.error(f"Failed to queue task for source {source.id}: {e}")
            results.append({
                'source_id': source.id,
                'source_name': source.name,
                'error': str(e)
            })
    
    return results


@shared_task
def scheduled_process_all_sources():
    """
    Scheduled task to process all active document sources.
    Runs every 6 hours via Celery Beat.
    Fetches PDFs to calculate hashes for accurate change detection.
    """
    logger.info("Starting scheduled processing of all document sources")
    
    from .models import DocumentSource
    from .notifiers import CompositeNotifier, LoggingNotifier
    
    # Use composite notifier for scheduled runs
    notifier = CompositeNotifier([LoggingNotifier()])
    
    active_sources = DocumentSource.objects.filter(active=True)
    total_changes = 0
    
    for source in active_sources:
        try:
            logger.info(f"Processing source: {source.name} (ID: {source.id})")
            result = process_document_source(
                source.id,
                fetch_pdfs=True,  # Always fetch PDFs for scheduled runs to detect changes
                notifier=notifier
            )
            
            change_count = len(result.get('change_events', []))
            total_changes += change_count
            
            logger.info(
                f"Source {source.name}: "
                f"{result['documents_created']} created, "
                f"{result['documents_updated']} updated, "
                f"{result['versions_created']} versions, "
                f"{change_count} changes"
            )
            
        except Exception as e:
            logger.error(f"Failed to process source {source.id} ({source.name}): {e}")
    
    logger.info(f"Scheduled processing complete. Total changes detected: {total_changes}")
    return {
        'sources_processed': active_sources.count(),
        'total_changes': total_changes
    }

