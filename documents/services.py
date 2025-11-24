"""
Service layer for fetching and processing document sources.
"""
import hashlib
import logging
from typing import List, Optional

import requests
from django.db import transaction
from django.utils import timezone

from .models import DocumentSource, Document, DocumentVersion
from .parsers import get_parser, ParsedDocumentRow
from .notifiers import ChangeEvent, BaseNotifier, get_default_notifier
from .sample import text_html

logger = logging.getLogger(__name__)


class DocumentFetchError(Exception):
    """Exception raised when document fetching fails."""
    pass


class DocumentSourceService:
    """Service for fetching and processing document sources."""
    
    def __init__(self, source: DocumentSource, notifier: Optional[BaseNotifier] = None):
        self.source = source
        self.parser = get_parser(source.parser_type.slug, source.index_url)
        self.notifier = notifier or get_default_notifier()
        self.change_events: List[ChangeEvent] = []
    
    def fetch_index_page(self) -> str:
        """
        Fetch the index page HTML from the document source.
        
        Returns:
            HTML content as string
            
        Raises:
            DocumentFetchError: If fetching fails
        """
        if self.source.parser_type.slug == 'usda':
            return text_html
        try:
            response = requests.get(
                self.source.index_url,
                timeout=100,
                headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; DocumentTracker/1.0)'
                }
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch index page for {self.source.name}: {e}")
            raise DocumentFetchError(f"Failed to fetch index page: {e}") from e
    
    def parse_documents(self, html: str) -> List[ParsedDocumentRow]:
        """
        Parse HTML to extract document rows.
        
        Args:
            html: HTML content to parse
            
        Returns:
            List of parsed document rows
        """
        try:
            rows = self.parser.extract_rows(html)
            logger.info(f"Parsed {len(rows)} documents from {self.source.name}")
            return rows
        except Exception as e:
            logger.error(f"Failed to parse documents for {self.source.name}: {e}")
            raise DocumentFetchError(f"Failed to parse documents: {e}") from e
    
    def normalize_row(self, row: ParsedDocumentRow) -> dict:
        """
        Normalize a parsed row into a dictionary with all required fields.
        
        Args:
            row: Parsed document row
            
        Returns:
            Dictionary with normalized fields
        """
        slug = self.parser.build_slug(row.title, row.description)
        
        return {
            'title': row.title,
            'slug': slug,
            'description': self.parser.normalize_description(row.description),
            'pdf_link': row.pdf_link,
            'published_date': row.published_date,
        }
    
    def fetch_pdf_hash(self, pdf_url: str) -> Optional[str]:
        """
        Fetch PDF and calculate SHA-256 hash.
        
        Args:
            pdf_url: URL of the PDF file
            
        Returns:
            SHA-256 hash as hex string, or None if fetch fails
        """
        try:
            response = requests.get(pdf_url, timeout=60, stream=True)
            response.raise_for_status()
            
            sha256 = hashlib.sha256()
            for chunk in response.iter_content(chunk_size=8192):
                sha256.update(chunk)
            
            return sha256.hexdigest()
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch PDF {pdf_url}: {e}")
            return None
    
    @transaction.atomic
    def process_source(self, fetch_pdfs: bool = False) -> dict:
        """
        Main method to fetch and process a document source.
        
        Args:
            fetch_pdfs: If True, fetch PDFs to calculate hashes (slower)
            
        Returns:
            Dictionary with processing results:
            {
                'documents_created': int,
                'documents_updated': int,
                'versions_created': int,
                'change_events': list,
                'errors': list
            }
        """
        results = {
            'documents_created': 0,
            'documents_updated': 0,
            'versions_created': 0,
            'change_events': [],
            'errors': []
        }
        self.change_events = []
        
        try:
            # Fetch and parse
            html = self.fetch_index_page()
            parsed_rows = self.parse_documents(html)

            
            # Process each row
            for row in parsed_rows:
                try:
                    normalized = self.normalize_row(row)

                    # ----------------------------------------------
                    # 1. Get or create document
                    # ----------------------------------------------
                    document, created = Document.objects.get_or_create(
                        source=self.source,
                        slug=normalized['slug'],
                        defaults={
                            'title': normalized['title'],
                            'description': normalized['description'],
                        }
                    )

                    if created:
                        results['documents_created'] += 1
                    else:
                        # ----------------------------------------------
                        # Update title/description if needed
                        # ----------------------------------------------
                        updated = False
                        updated_fields = []

                        if document.title != normalized['title']:
                            document.title = normalized['title']
                            updated = True
                            updated_fields.append('title')

                        if document.description != normalized['description']:
                            document.description = normalized['description']
                            updated = True
                            updated_fields.append('description')

                        if updated:
                            document.save()
                            results['documents_updated'] += 1
                            self.change_events.append(ChangeEvent(
                                document=document,
                                event_type='updated_document',
                                change_reason=", ".join(updated_fields)
                            ))

                    previous_version = document.current_version
                    published_date = normalized['published_date']

                    # ---------------------------------------------------
                    # 2. Apply the required rules:
                    #    Rule A: Always compare published date first
                    #    Rule B: If published date unchanged → maybe skip
                    #    Rule C: If published date missing → ALWAYS hash
                    # ---------------------------------------------------

                    # ---------------------------------------------------
                    # CASE 1 — Published date exists
                    # ---------------------------------------------------
                    if published_date:

                        # A: Try to find an existing version matching this date
                        existing_by_date = DocumentVersion.objects.filter(
                            document=document,
                            published_date=published_date
                        ).first()

                        if existing_by_date:
                            # Published date unchanged → No need to hash for now
                            continue

                        # Published date changed → need to confirm via hash if enabled
                        pdf_hash = None
                        if fetch_pdfs:
                            pdf_hash = self.fetch_pdf_hash(normalized['pdf_link'])

                        # If we have a hash, check for duplicate version
                        existing_by_hash = None
                        if pdf_hash:
                            existing_by_hash = DocumentVersion.objects.filter(
                                document=document,
                                pdf_hash=pdf_hash
                            ).first()

                        # If existing version has the same PDF hash → nothing changed
                        if existing_by_hash:
                            continue

                        # Create a new version
                        new_version = DocumentVersion.objects.create(
                            document=document,
                            pdf_url=normalized['pdf_link'],
                            published_date=published_date,
                            pdf_hash=pdf_hash or '',
                            fetched_at=timezone.now()
                        )
                        results['versions_created'] += 1

                        # Determine change reason
                        if not previous_version or not previous_version.published_date:
                            change_reason = "published_date_added"
                        elif published_date > previous_version.published_date:
                            change_reason = "new_published_date"
                        else:
                            change_reason = "pdf_hash_changed"

                        # Add event
                        self.change_events.append(ChangeEvent(
                            document=document,
                            version=new_version,
                            previous_version=previous_version,
                            event_type=("new_document" if created else "new_version"),
                            change_reason=change_reason
                        ))

                        # Update current version
                        if not previous_version or (
                            previous_version.published_date
                            and published_date > previous_version.published_date
                        ):
                            document.current_version = new_version
                            document.save()

                        continue

                    # ---------------------------------------------------
                    # CASE 2 — No published date → ALWAYS hash
                    # ---------------------------------------------------
                    pdf_hash = None
                    if fetch_pdfs:
                        pdf_hash = self.fetch_pdf_hash(normalized['pdf_link'])

                    if not pdf_hash:
                        # No hash and no date: fallback, treat as always new
                        pdf_hash = ''

                    existing_by_hash = DocumentVersion.objects.filter(
                        document=document,
                        pdf_hash=pdf_hash
                    ).first()

                    if existing_by_hash:
                        # Same hash → already exists → no new version needed
                        continue

                    # Create new version because no date + hash mismatch OR no previous version
                    new_version = DocumentVersion.objects.create(
                        document=document,
                        pdf_url=normalized['pdf_link'],
                        published_date=None,
                        pdf_hash=pdf_hash,
                        fetched_at=timezone.now()
                    )
                    results['versions_created'] += 1

                    # Create event
                    self.change_events.append(ChangeEvent(
                        document=document,
                        version=new_version,
                        previous_version=previous_version,
                        event_type=("new_document" if created else "new_version"),
                        change_reason="missing_date_hash_version"
                    ))

                    # Always update current_version when there’s no date
                    document.current_version = new_version
                    document.save()

                
                except Exception as e:
                    error_msg = f"Error processing row {row.title}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
        
        except DocumentFetchError as e:
            error_msg = f"Failed to process source {self.source.name}: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
        
        # Send notifications for changes
        if self.change_events:
            results['change_events'] = self.change_events
            try:
                self.notifier.notify(self.change_events)
            except Exception as e:
                logger.error(f"Failed to send notifications: {e}")
                results['errors'].append(f"Notification error: {e}")
        return results


def process_document_source(source_id: int, fetch_pdfs: bool = False, notifier: Optional[BaseNotifier] = None) -> dict:
    """
    Convenience function to process a document source by ID.
    
    Args:
        source_id: ID of the DocumentSource to process
        fetch_pdfs: If True, fetch PDFs to calculate hashes
        notifier: Optional notifier instance (uses default if not provided)
        
    Returns:
        Processing results dictionary
    """
    try:
        source = DocumentSource.objects.get(id=source_id, active=True)
    except DocumentSource.DoesNotExist:
        raise ValueError(f"DocumentSource with id {source_id} not found or inactive")
    
    service = DocumentSourceService(source, notifier=notifier)
    return service.process_source(fetch_pdfs=fetch_pdfs)

