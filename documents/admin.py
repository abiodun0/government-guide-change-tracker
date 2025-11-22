from django.contrib import admin
from .models import ParserType, DocumentSource, Document, DocumentVersion


@admin.register(ParserType)
class ParserTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'active', 'created_at']
    list_filter = ['active', 'created_at']
    search_fields = ['name', 'slug']
    list_editable = ['active']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DocumentSource)
class DocumentSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'parser_type', 'active', 'created_at']
    list_filter = ['active', 'parser_type', 'created_at']
    search_fields = ['name', 'index_url']
    list_editable = ['active']
    raw_id_fields = ['parser_type']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'source', 'slug', 'has_current_version', 'created_at']
    list_filter = ['source', 'created_at']
    search_fields = ['title', 'slug', 'description']
    raw_id_fields = ['source', 'current_version']
    readonly_fields = ['created_at', 'updated_at']

    def has_current_version(self, obj):
        return obj.current_version is not None
    has_current_version.boolean = True
    has_current_version.short_description = 'Has Current Version'


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ['document', 'published_date', 'pdf_hash_short', 'fetched_at']
    list_filter = ['fetched_at', 'published_date']
    search_fields = ['document__title', 'pdf_hash', 'pdf_url']
    raw_id_fields = ['document']
    readonly_fields = ['fetched_at', 'pdf_hash']

    def pdf_hash_short(self, obj):
        return f"{obj.pdf_hash[:16]}..." if obj.pdf_hash else "-"
    pdf_hash_short.short_description = 'PDF Hash'

