from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AlertNoteViewSet,
    AlertViewSet,
    ClientPotentialViewSet,
    ClientViewSet,
    CampaignViewSet,
    CSVUploadViewSet,
    ProductViewSet,
    SaleViewSet,
)

router = DefaultRouter()
router.register(r'clients', ClientViewSet)
router.register(r'products', ProductViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'potentials', ClientPotentialViewSet)
router.register(r'campaigns', CampaignViewSet)
router.register(r'alerts', AlertViewSet)
router.register(r'alert-notes', AlertNoteViewSet)
router.register(r'csv-uploads', CSVUploadViewSet)

urlpatterns = [
    path('api/v1/', include(router.urls)),
]
