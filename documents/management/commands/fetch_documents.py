"""
Management command to fetch and process document sources.
"""
from django.core.management.base import BaseCommand, CommandError
from documents.models import DocumentSource
from documents.services import process_document_source


class Command(BaseCommand):
    help = 'Fetch and process documents from a document source'

    def add_arguments(self, parser):
        parser.add_argument(
            'source_id',
            type=int,
            help='ID of the DocumentSource to process'
        )
        parser.add_argument(
            '--fetch-pdfs',
            action='store_true',
            help='Fetch PDFs to calculate hashes (slower but more accurate)'
        )

    def handle(self, *args, **options):
        source_id = options['source_id']
        fetch_pdfs = options['fetch_pdfs']

        try:
            source = DocumentSource.objects.get(id=source_id)
        except DocumentSource.DoesNotExist:
            raise CommandError(f'DocumentSource with id {source_id} does not exist')

        if not source.active:
            self.stdout.write(
                self.style.WARNING(f'DocumentSource "{source.name}" is not active')
            )

        self.stdout.write(f'Processing source: {source.name} (ID: {source_id})')
        self.stdout.write(f'Index URL: {source.index_url}')
        self.stdout.write(f'Parser: {source.parser_type.slug}')

        try:
            results = process_document_source(source_id, fetch_pdfs=fetch_pdfs)

            self.stdout.write(self.style.SUCCESS('\nProcessing complete!'))
            self.stdout.write(f'Documents created: {results["documents_created"]}')
            self.stdout.write(f'Documents updated: {results["documents_updated"]}')
            self.stdout.write(f'Versions created: {results["versions_created"]}')

            if results['errors']:
                self.stdout.write(self.style.WARNING(f'\nErrors ({len(results["errors"])}):'))
                for error in results['errors']:
                    self.stdout.write(self.style.ERROR(f'  - {error}'))

        except Exception as e:
            raise CommandError(f'Error processing source: {e}')

