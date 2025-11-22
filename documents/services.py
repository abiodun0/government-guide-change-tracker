"""
Service layer for fetching and processing document sources.
"""
import hashlib
import logging
from typing import List, Optional
from urllib.parse import urlparse

import requests
from django.db import transaction
from django.utils import timezone

from .models import DocumentSource, Document, DocumentVersion, ParserType
from .parsers import get_parser, ParsedDocumentRow

logger = logging.getLogger(__name__)


class DocumentFetchError(Exception):
    """Exception raised when document fetching fails."""
    pass


class DocumentSourceService:
    """Service for fetching and processing document sources."""
    
    def __init__(self, source: DocumentSource):
        self.source = source
        self.parser = get_parser(source.parser_type.slug, source.index_url)
        print(self.parser, 'what is in the parser')
    
    def fetch_index_page(self) -> str:
        """
        Fetch the index page HTML from the document source.
        
        Returns:
            HTML content as string
            
        Raises:
            DocumentFetchError: If fetching fails
        """
        try:
            response = requests.get(
                self.source.index_url,
                timeout=30,
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
            print(rows, 'what is in the rows')
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
        slug = self.parser.build_slug(row.title)
        
        return {
            'title': self.parser.normalize_title(row.title),
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
                'errors': list
            }
        """
        results = {
            'documents_created': 0,
            'documents_updated': 0,
            'versions_created': 0,
            'errors': []
        }
        
        try:
            # Fetch and parse
            html = self.fetch_index_page()
            parsed_rows = self.parse_documents(html)
            print(parsed_rows, 'what is in the parsed rows')

            
            # Process each row
            for row in parsed_rows:
                try:
                    normalized = self.normalize_row(row)
                    
                    # Get or create document
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
                        # Update title/description if changed
                        updated = False
                        if document.title != normalized['title']:
                            document.title = normalized['title']
                            updated = True
                        if document.description != normalized['description']:
                            document.description = normalized['description']
                            updated = True
                        if updated:
                            document.save()
                            results['documents_updated'] += 1
                    
                    # Check if version already exists
                    pdf_hash = None
                    if fetch_pdfs:
                        pdf_hash = self.fetch_pdf_hash(normalized['pdf_link'])
                    
                    # If we have a hash, check for existing version
                    if pdf_hash:
                        version_exists = DocumentVersion.objects.filter(
                            document=document,
                            pdf_hash=pdf_hash
                        ).exists()
                        
                        if not version_exists:
                            # Create new version
                            DocumentVersion.objects.create(
                                document=document,
                                pdf_url=normalized['pdf_link'],
                                published_date=normalized['published_date'],
                                pdf_hash=pdf_hash,
                                fetched_at=timezone.now()
                            )
                            results['versions_created'] += 1
                            
                            # Update current_version if this is newer
                            new_version = DocumentVersion.objects.get(
                                document=document,
                                pdf_hash=pdf_hash
                            )
                            if not document.current_version:
                                document.current_version = new_version
                                document.save()
                            elif normalized['published_date'] and document.current_version.published_date:
                                if normalized['published_date'] > document.current_version.published_date:
                                    document.current_version = new_version
                                    document.save()
                            elif not document.current_version.published_date and normalized['published_date']:
                                # New version has date, old doesn't - prefer new
                                document.current_version = new_version
                                document.save()
                    else:
                        # Without hash, create version if URL is different
                        version_exists = DocumentVersion.objects.filter(
                            document=document,
                            pdf_url=normalized['pdf_link']
                        ).exists()
                        
                        if not version_exists:
                            DocumentVersion.objects.create(
                                document=document,
                                pdf_url=normalized['pdf_link'],
                                published_date=normalized['published_date'],
                                pdf_hash='',  # Will be updated later
                                fetched_at=timezone.now()
                            )
                            results['versions_created'] += 1
                
                except Exception as e:
                    error_msg = f"Error processing row {row.title}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
        
        except DocumentFetchError as e:
            error_msg = f"Failed to process source {self.source.name}: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
        
        return results


def process_document_source(source_id: int, fetch_pdfs: bool = False) -> dict:
    """
    Convenience function to process a document source by ID.
    
    Args:
        source_id: ID of the DocumentSource to process
        fetch_pdfs: If True, fetch PDFs to calculate hashes
        
    Returns:
        Processing results dictionary
    """
    try:
        source = DocumentSource.objects.get(id=source_id, active=True)
    except DocumentSource.DoesNotExist:
        raise ValueError(f"DocumentSource with id {source_id} not found or inactive")
    
    service = DocumentSourceService(source)
    return service.process_source(fetch_pdfs=fetch_pdfs)

