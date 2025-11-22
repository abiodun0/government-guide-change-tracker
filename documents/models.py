from django.db import models
from django.core.exceptions import ValidationError


class ParserType(models.Model):
    """
    Parser types for different document sources.
    Uses dash-slug as unique identifier for strategy pattern.
    """
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Dash-separated unique identifier (e.g., 'ginnie-mae', 'usda')"
    )
    name = models.CharField(
        max_length=255,
        help_text="Display name for the parser type (e.g., 'Ginnie Mae')"
    )
    active = models.BooleanField(
        default=True,
        help_text="Whether this parser type is currently active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Parser Type'
        verbose_name_plural = 'Parser Types'

    def clean(self):
        """Validate that slug uses dashes, not underscores."""
        if self.slug and '_' in self.slug:
            raise ValidationError({
                'slug': 'Slug must use dashes, not underscores (e.g., "ginnie-mae" not "ginnie_mae")'
            })

    def save(self, *args, **kwargs):
        """Ensure slug uses dashes before saving."""
        if self.slug:
            self.slug = self.slug.replace('_', '-').lower()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.slug})"


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
    parser_type = models.ForeignKey(
        ParserType,
        on_delete=models.PROTECT,
        related_name='document_sources',
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

