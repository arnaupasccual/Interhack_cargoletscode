from rest_framework import serializers
from .models import Alert, AlertNote, Client, ClientPotential, Campaign, CSVUpload, Product, Sale


class ClientSerializer(serializers.ModelSerializer):
    alert_count = serializers.SerializerMethodField()
    open_alert_count = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = ['id', 'client_id', 'postal_code', 'province', 'alert_count', 'open_alert_count']

    def get_alert_count(self, obj):
        return obj.alerts.count()

    def get_open_alert_count(self, obj):
        return obj.alerts.filter(status=Alert.Status.OPEN).count()


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'product_id', 'analytical_block', 'category', 'family']


class SaleSerializer(serializers.ModelSerializer):
    client_id = serializers.IntegerField(source='client.client_id', read_only=True)
    product_id = serializers.IntegerField(source='product.product_id', read_only=True)
    product_family = serializers.CharField(source='product.family', read_only=True)

    class Meta:
        model = Sale
        fields = [
            'id', 'invoice_number', 'date',
            'client', 'client_id',
            'product', 'product_id', 'product_family',
            'units', 'value',
        ]


class ClientPotentialSerializer(serializers.ModelSerializer):
    client_id = serializers.IntegerField(source='client.client_id', read_only=True)

    class Meta:
        model = ClientPotential
        fields = ['id', 'client', 'client_id', 'family', 'product_category', 'potential_value']


class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = ['id', 'name', 'start_date', 'end_date']


# ---------------------------------------------------------------------------
# Alert serializers
# ---------------------------------------------------------------------------

class AlertNoteSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = AlertNote
        fields = ['id', 'alert', 'author', 'author_username', 'body', 'created_at']
        read_only_fields = ['created_at']


class AlertListSerializer(serializers.ModelSerializer):
    """Compact representation for list views."""
    client_external_id = serializers.IntegerField(source='client.client_id', read_only=True)
    client_province = serializers.CharField(source='client.province', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)

    class Meta:
        model = Alert
        fields = [
            'id', 'alert_type', 'alert_type_display',
            'priority', 'priority_display',
            'status', 'status_display',
            'model_source',
            'title',
            'client', 'client_external_id', 'client_province',
            'affected_family',
            'economic_impact',
            'urgency_days',
            'confidence_score',
            'last_order_date',
            'created_at',
            'updated_at',
        ]


class AlertDetailSerializer(serializers.ModelSerializer):
    """Full representation including client info and notes."""
    client_info = ClientSerializer(source='client', read_only=True)
    notes = AlertNoteSerializer(many=True, read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    recommended_channel_display = serializers.CharField(
        source='get_recommended_channel_display', read_only=True
    )

    class Meta:
        model = Alert
        fields = [
            'id', 'alert_type', 'alert_type_display',
            'priority', 'priority_display',
            'status', 'status_display',
            'model_source',
            'title', 'reason',
            'client', 'client_info',
            'affected_family',
            'recommended_channel', 'recommended_channel_display',
            'economic_impact',
            'urgency_days',
            'confidence_score',
            'last_order_date',
            'created_at', 'updated_at', 'resolved_at',
            'notes',
        ]
        read_only_fields = ['created_at', 'updated_at']


class AlertStatusUpdateSerializer(serializers.ModelSerializer):
    """Minimal serializer for status-only PATCH operations."""

    class Meta:
        model = Alert
        fields = ['status', 'resolved_at']


class CSVUploadSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = CSVUpload
        fields = [
            'id', 'file', 'upload_type', 'status',
            'uploaded_by', 'uploaded_by_username',
            'uploaded_at',
            'rows_total', 'rows_processed', 'rows_failed',
            'error_log',
        ]
        read_only_fields = [
            'status', 'uploaded_at',
            'rows_total', 'rows_processed', 'rows_failed',
            'error_log',
        ]
