from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Alert, AlertNote, Client, ClientPotential, Campaign, CSVUpload, Product, Sale
from .serializers import (
    AlertDetailSerializer,
    AlertListSerializer,
    AlertNoteSerializer,
    AlertStatusUpdateSerializer,
    ClientPotentialSerializer,
    ClientSerializer,
    CampaignSerializer,
    CSVUploadSerializer,
    ProductSerializer,
    SaleSerializer,
)


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['province']
    search_fields = ['client_id', 'postal_code', 'province']
    ordering_fields = ['client_id', 'province']

    @action(detail=True, methods=['get'])
    def alerts(self, request, pk=None):
        """Return all alerts for a specific client."""
        client = self.get_object()
        client_alerts = client.alerts.all()

        status_filter = request.query_params.get('status')
        if status_filter:
            client_alerts = client_alerts.filter(status=status_filter)

        serializer = AlertListSerializer(client_alerts, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def sales(self, request, pk=None):
        """Return sales history for a specific client."""
        client = self.get_object()
        client_sales = client.sales.select_related('product').order_by('-date')[:200]
        serializer = SaleSerializer(client_sales, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def potentials(self, request, pk=None):
        """Return potential consumption for a specific client."""
        client = self.get_object()
        potentials = client.potentials.all()
        serializer = ClientPotentialSerializer(potentials, many=True)
        return Response(serializer.data)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['analytical_block', 'category', 'family']
    search_fields = ['product_id', 'category', 'family']
    ordering_fields = ['product_id', 'family', 'category']


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.select_related('client', 'product').all()
    serializer_class = SaleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['client', 'product']
    search_fields = ['invoice_number']
    ordering_fields = ['date', 'value', 'units']


class ClientPotentialViewSet(viewsets.ModelViewSet):
    queryset = ClientPotential.objects.select_related('client').all()
    serializer_class = ClientPotentialSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['client', 'family', 'product_category']
    ordering_fields = ['potential_value', 'family']


class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['start_date', 'end_date', 'name']


class AlertViewSet(viewsets.ModelViewSet):
    queryset = Alert.objects.select_related('client').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'priority', 'alert_type', 'model_source', 'client', 'affected_family']
    search_fields = ['title', 'reason', 'client__client_id', 'affected_family']
    ordering_fields = ['created_at', 'updated_at', 'priority', 'economic_impact', 'urgency_days']

    def get_serializer_class(self):
        if self.action == 'list':
            return AlertListSerializer
        if self.action == 'update_status':
            return AlertStatusUpdateSerializer
        return AlertDetailSerializer

    @action(detail=True, methods=['patch'], url_path='status')
    def update_status(self, request, pk=None):
        """Change the status of an alert (e.g., OPEN → IN_PROGRESS → RESOLVED)."""
        alert = self.get_object()
        new_status = request.data.get('status')

        if new_status not in Alert.Status.values:
            return Response(
                {'error': f'Invalid status. Choices: {Alert.Status.values}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        alert.status = new_status
        if new_status == Alert.Status.RESOLVED and not alert.resolved_at:
            alert.resolved_at = timezone.now()
        alert.save(update_fields=['status', 'resolved_at', 'updated_at'])

        return Response(AlertDetailSerializer(alert).data)

    @action(detail=True, methods=['get', 'post'], url_path='notes')
    def notes(self, request, pk=None):
        """List or add notes to an alert."""
        alert = self.get_object()

        if request.method == 'GET':
            serializer = AlertNoteSerializer(alert.notes.all(), many=True)
            return Response(serializer.data)

        serializer = AlertNoteSerializer(data={**request.data, 'alert': alert.pk})
        if serializer.is_valid():
            serializer.save(
                alert=alert,
                author=request.user if request.user.is_authenticated else None,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """Dashboard summary: counts grouped by status and priority."""
        qs = self.get_queryset()

        by_status = {
            s: qs.filter(status=s).count()
            for s in Alert.Status.values
        }
        by_priority = {
            p: qs.filter(priority=p).count()
            for p in Alert.Priority.values
        }
        by_type = {
            t: qs.filter(alert_type=t).count()
            for t in Alert.AlertType.values
        }

        return Response({
            'total': qs.count(),
            'by_status': by_status,
            'by_priority': by_priority,
            'by_type': by_type,
        })


class AlertNoteViewSet(viewsets.ModelViewSet):
    queryset = AlertNote.objects.select_related('alert', 'author').all()
    serializer_class = AlertNoteSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['alert']

    def perform_create(self, serializer):
        serializer.save(
            author=self.request.user if self.request.user.is_authenticated else None
        )


class CSVUploadViewSet(viewsets.ModelViewSet):
    queryset = CSVUpload.objects.all()
    serializer_class = CSVUploadSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['upload_type', 'status']
    ordering_fields = ['uploaded_at']

    def perform_create(self, serializer):
        serializer.save(
            uploaded_by=self.request.user if self.request.user.is_authenticated else None
        )
