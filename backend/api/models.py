from django.db import models


class Client(models.Model):
    """A client company that buys medical products from the supplier."""

    client_id = models.IntegerField(unique=True, db_index=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['client_id']

    def __str__(self):
        return f"Client {self.client_id} ({self.province})"


class Product(models.Model):
    """A medical product sold by the supplier."""

    ANALYTICAL_BLOCK_CHOICES = [
        ('Commodities', 'Commodities'),
        ('Tecnicos', 'Técnicos'),
        ('Otros', 'Otros'),
    ]

    product_id = models.IntegerField(unique=True, db_index=True)
    analytical_block = models.CharField(max_length=100, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    family = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['product_id']

    def __str__(self):
        return f"Product {self.product_id} — {self.family}"


class Sale(models.Model):
    """A sales transaction (line of an invoice)."""

    invoice_number = models.CharField(max_length=50, db_index=True)
    date = models.DateTimeField()
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='sales')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sales')
    units = models.DecimalField(max_digits=12, decimal_places=4)
    value = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['client', 'date']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} — {self.client} × {self.product}"


class ClientPotential(models.Model):
    """Estimated potential consumption of a product family for a client."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='potentials')
    family = models.CharField(max_length=100)
    product_category = models.CharField(max_length=100, blank=True, null=True)
    potential_value = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        unique_together = [('client', 'family')]
        ordering = ['client', 'family']

    def __str__(self):
        return f"{self.client} — {self.family}: {self.potential_value}"


class Campaign(models.Model):
    """A commercial campaign period."""

    name = models.CharField(max_length=100, unique=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"Campaign {self.name} ({self.start_date.date()} → {self.end_date.date()})"


# ---------------------------------------------------------------------------
# Alert system
# ---------------------------------------------------------------------------

class Alert(models.Model):
    """An alert flagged by an ML model about a client's commercial behaviour."""

    class Priority(models.TextChoices):
        CRITICAL = 'CRITICAL', 'Critical'
        HIGH = 'HIGH', 'High'
        MEDIUM = 'MEDIUM', 'Medium'
        LOW = 'LOW', 'Low'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        RESOLVED = 'RESOLVED', 'Resolved'
        DISMISSED = 'DISMISSED', 'Dismissed'

    class AlertType(models.TextChoices):
        A1_REPLENISHMENT = 'A1', 'A1 — Reposición pendiente'
        A2_CAPTURE = 'A2', 'A2 — Ventana de captación'
        A3_COMMODITY_CHURN = 'A3', 'A3 — Cliente fiel en riesgo'
        A4_TECHNICAL_RISK = 'A4', 'A4 — Cliente técnico en riesgo'
        A5_REACTIVATION = 'A5', 'A5 — Oportunidad de reactivación'
        A6_SUDDEN_DROP = 'A6', 'A6 — Caída brusca de ventas'

    class RecommendedChannel(models.TextChoices):
        SALES_REP = 'SALES_REP', 'Sales representative'
        TELEMARKETER = 'TELEMARKETER', 'Telemarketer'
        MARKETING_AUTO = 'MARKETING_AUTO', 'Marketing automation'

    class ModelSource(models.TextChoices):
        M0_SEGMENTATION = 'M0', 'M0 — Customer segmentation'
        M1_REPLENISHMENT = 'M1', 'M1 — Replenishment prediction'
        M2_COMMODITY_CHURN = 'M2', 'M2 — Commodity churn'
        M3_TECHNICAL_CHURN = 'M3', 'M3 — Technical product churn'
        M4_RETURN_RISK = 'M4', 'M4 — Return risk'
        M5_PRE_CHURN = 'M5', 'M5 — Pre-churn signal'

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=10, choices=AlertType.choices)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    model_source = models.CharField(max_length=5, choices=ModelSource.choices, blank=True, null=True)

    title = models.CharField(max_length=300)
    reason = models.TextField(blank=True, help_text='Natural language explanation generated by the model')
    affected_family = models.CharField(max_length=100, blank=True, null=True)
    recommended_channel = models.CharField(
        max_length=20, choices=RecommendedChannel.choices, blank=True, null=True
    )
    economic_impact = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Estimated annual revenue at risk (EUR)'
    )
    urgency_days = models.IntegerField(
        null=True, blank=True,
        help_text='Number of days before the situation becomes critical'
    )

    # Scores / confidence from the model (0–1)
    confidence_score = models.FloatField(null=True, blank=True)

    last_order_date = models.DateField(
        null=True, blank=True,
        help_text='Date of the last order placed by the client for this family'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['alert_type']),
        ]

    def __str__(self):
        return f"[{self.priority}] {self.alert_type} — {self.client} ({self.status})"


class AlertNote(models.Model):
    """A free-text note or action log entry attached to an alert."""

    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='alert_notes'
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Note on {self.alert} at {self.created_at:%Y-%m-%d %H:%M}"


class CSVUpload(models.Model):
    """Tracks each CSV file imported into the system."""

    class UploadType(models.TextChoices):
        CLIENTS = 'CLIENTS', 'Clients (Clientes.csv)'
        PRODUCTS = 'PRODUCTS', 'Products (Productos.csv)'
        SALES = 'SALES', 'Sales (Ventas.csv)'
        POTENTIALS = 'POTENTIALS', 'Potentials (Potencial.csv)'
        CAMPAIGNS = 'CAMPAIGNS', 'Campaigns (Campañas.csv)'

    class UploadStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        SUCCESS = 'SUCCESS', 'Success'
        PARTIAL = 'PARTIAL', 'Partial (with errors)'
        FAILED = 'FAILED', 'Failed'

    file = models.FileField(upload_to='csv_uploads/')
    upload_type = models.CharField(max_length=20, choices=UploadType.choices)
    status = models.CharField(max_length=20, choices=UploadStatus.choices, default=UploadStatus.PENDING)
    uploaded_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    rows_total = models.IntegerField(default=0)
    rows_processed = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)
    error_log = models.TextField(blank=True, help_text='JSON list of row-level errors')

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.upload_type} upload at {self.uploaded_at:%Y-%m-%d %H:%M} ({self.status})"
