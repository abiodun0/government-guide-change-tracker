"""
Celery tasks for document processing.
"""
from celery import shared_task
from django.db import transaction

from .services import process_document_source, DocumentFetchError
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def fetch_and_process_document_source(self, source_id: int, fetch_pdfs: bool = False):
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

