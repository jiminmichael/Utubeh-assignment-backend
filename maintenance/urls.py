from django.urls import path

from .views import (
    MaintenanceCancelView,
    MaintenanceCompleteView,
    MaintenanceExportView,
    MaintenanceAttachmentView,
    MaintenanceDetailView,
    MaintenanceListCreateView,
    MaintenanceStartView,
)

app_name = "maintenance"

urlpatterns = [
    path("", MaintenanceListCreateView.as_view(), name="maintenance-list-create"),
    path("export/", MaintenanceExportView.as_view(), name="maintenance-export"),
    path("<int:pk>/", MaintenanceDetailView.as_view(), name="maintenance-detail"),
    path("<int:pk>/start/", MaintenanceStartView.as_view(), name="maintenance-start"),
    path("<int:pk>/complete/", MaintenanceCompleteView.as_view(), name="maintenance-complete"),
    path("<int:pk>/cancel/", MaintenanceCancelView.as_view(), name="maintenance-cancel"),
    path("<int:pk>/attachments/", MaintenanceAttachmentView.as_view(), name="maintenance-attachment-create"),
]