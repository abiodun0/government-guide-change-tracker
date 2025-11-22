from django.db import models


class ParserType(models.TextChoices):
    """Parser types for different document sources."""
    GINNIE_MAE = 'ginnie_mae', 'Ginnie Mae'
    USDA = 'usda', 'USDA'
    CUSTOM = 'custom', 'Custom'


class DocumentSource(models.Model):
    """
    Represents a guide (e.g., "Ginnie Mae MBS Guide," "USDA Handbook").
    """
    name = models.CharField(
        max_length=255,
        help_text="Name of the document source, e.g., 'Ginnie Mae MBS Guide'"
    )
    index_url = models.URLField(
        max_length=500,
        help_text="URL of the HTML page listing the PDFs"
    )
    parser_type = models.CharField(
        max_length=50,
        choices=ParserType.choices,
        default=ParserType.CUSTOM,
        help_text="Determines which parser to use for this source"
    )
    active = models.BooleanField(
        default=True,
        help_text="Whether this source is currently active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Document Source'
        verbose_name_plural = 'Document Sources'

    def __str__(self):
        return self.name


class Document(models.Model):
    """
    Represents a specific chapter/section across versions.
    Uniquely identified by a stable key extracted from the source.
    """
    source = models.ForeignKey(
        DocumentSource,
        on_delete=models.CASCADE,
        related_name='documents',
        help_text="The source this document belongs to"
    )
    slug = models.SlugField(
        max_length=255,
        help_text="Normalized unique key, e.g., 'mbs_ch_03'"
    )
    title = models.CharField(
        max_length=500,
        help_text="Title of the document"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the document"
    )
    current_version = models.ForeignKey(
        'DocumentVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_for_documents',
        help_text="The current/latest version of this document"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source', 'slug']
        constraints = [
            models.UniqueConstraint(fields=['source', 'slug'], name='unique_document_source_slug')
        ]
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'
        indexes = [
            models.Index(fields=['source', 'slug']),
        ]

    def __str__(self):
        return f"{self.source.name} - {self.title} ({self.slug})"


class DocumentVersion(models.Model):
    """
    Represents one version of a PDF snapshot.
    """
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='versions',
        help_text="The document this version belongs to"
    )
    pdf_url = models.URLField(
        max_length=1000,
        help_text="URL of the PDF file"
    )
    published_date = models.DateField(
        null=True,
        blank=True,
        help_text="Publication date of this version, if available"
    )
    pdf_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 hash of the downloaded PDF file"
    )
    fetched_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this version was fetched"
    )

    class Meta:
        ordering = ['-fetched_at']
        constraints = [
            models.UniqueConstraint(fields=['document', 'pdf_hash'], name='unique_document_version_hash')
        ]
        verbose_name = 'Document Version'
        verbose_name_plural = 'Document Versions'
        indexes = [
            models.Index(fields=['document', 'pdf_hash']),
            models.Index(fields=['-fetched_at']),
        ]

    def __str__(self):
        date_str = self.published_date.strftime('%Y-%m-%d') if self.published_date else 'No date'
        return f"{self.document.title} - {date_str} ({self.pdf_hash[:8]}...)"

