from django.contrib import admin
from .models import Alert, AlertNote, Client, ClientPotential, Campaign, CSVUpload, Product, Sale


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['client_id', 'postal_code', 'province']
    search_fields = ['client_id', 'postal_code', 'province']
    list_filter = ['province']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['product_id', 'analytical_block', 'category', 'family']
    search_fields = ['product_id', 'category', 'family']
    list_filter = ['analytical_block', 'category', 'family']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'date', 'client', 'product', 'units', 'value']
    search_fields = ['invoice_number', 'client__client_id']
    list_filter = ['date']
    date_hierarchy = 'date'
    raw_id_fields = ['client', 'product']


@admin.register(ClientPotential)
class ClientPotentialAdmin(admin.ModelAdmin):
    list_display = ['client', 'family', 'product_category', 'potential_value']
    search_fields = ['client__client_id', 'family']
    list_filter = ['family', 'product_category']
    raw_id_fields = ['client']


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date']
    search_fields = ['name']


class AlertNoteInline(admin.TabularInline):
    model = AlertNote
    extra = 0
    readonly_fields = ['created_at']


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'alert_type', 'priority', 'status', 'model_source',
        'client', 'affected_family', 'economic_impact', 'urgency_days', 'created_at',
    ]
    list_filter = ['status', 'priority', 'alert_type', 'model_source', 'recommended_channel']
    search_fields = ['title', 'reason', 'client__client_id', 'affected_family']
    date_hierarchy = 'created_at'
    raw_id_fields = ['client']
    inlines = [AlertNoteInline]
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = [
        ('Classification', {
            'fields': ['alert_type', 'priority', 'status', 'model_source'],
        }),
        ('Content', {
            'fields': ['title', 'reason', 'affected_family'],
        }),
        ('Client', {
            'fields': ['client'],
        }),
        ('Actionability', {
            'fields': ['recommended_channel', 'economic_impact', 'urgency_days', 'confidence_score'],
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at', 'resolved_at'],
            'classes': ['collapse'],
        }),
    ]


@admin.register(AlertNote)
class AlertNoteAdmin(admin.ModelAdmin):
    list_display = ['alert', 'author', 'created_at']
    search_fields = ['body', 'alert__title']
    raw_id_fields = ['alert']


@admin.register(CSVUpload)
class CSVUploadAdmin(admin.ModelAdmin):
    list_display = [
        'upload_type', 'status', 'uploaded_by', 'uploaded_at',
        'rows_total', 'rows_processed', 'rows_failed',
    ]
    list_filter = ['upload_type', 'status']
    readonly_fields = ['uploaded_at', 'rows_total', 'rows_processed', 'rows_failed', 'error_log']
