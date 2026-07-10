from django.urls import path

from .views import AssetBulkImportView, AssetDetailView, AssetExportView, AssetListCreateView, AssetQRCodeView

app_name = "assets"

urlpatterns = [
    path("", AssetListCreateView.as_view(), name="asset-list-create"),
    path("bulk-import/", AssetBulkImportView.as_view(), name="asset-bulk-import"),
    path("export/", AssetExportView.as_view(), name="asset-export"),
    path("<int:pk>/", AssetDetailView.as_view(), name="asset-detail"),
    path("<int:pk>/qr-code/", AssetQRCodeView.as_view(), name="asset-qr-code"),
]
