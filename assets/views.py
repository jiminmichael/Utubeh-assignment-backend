from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings
from django.db.models import Q
from django.db import transaction
from django.http import FileResponse
from rest_framework import filters, generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from core.views import ExportAPIView

from activity_logs.models import ActivityLog
from .filters import AssetFilter
from .models import Asset
from .pagination import AssetPagination
from .permissions import AssetPermission
from .serializers import AssetBulkImportSerializer, AssetListSerializer, AssetSerializer, AssetExportSerializer


class AssetListCreateView(generics.ListCreateAPIView):
    queryset = Asset.objects.select_related("created_by", "updated_by")
    permission_classes = [AssetPermission]
    pagination_class = AssetPagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AssetFilter
    search_fields = [
        "name",
        "asset_tag",
        "serial_number",
        "barcode",
        "category",
        "subcategory",
        "manufacturer",
        "model",
        "condition",
        "description",
        "vendor_name",
        "location",
        "notes",
        "assignments__assigned_to__username",
        "assignments__assigned_to__email",
        "assignments__assigned_to__first_name",
        "assignments__assigned_to__last_name",
    ]
    ordering_fields = [
        "id",
        "asset_tag",
        "serial_number",
        "name",
        "category",
        "manufacturer",
        "model",
        "status",
        "condition",
        "purchase_date",
        "purchase_cost",
        "warranty_expiry",
        "location",
        "created_at",
        "updated_at",
    ]
    ordering = ["asset_tag"]

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related("assignments__assigned_to")
        query = self.request.query_params.get("q")
        if query:
            # Use PostgreSQL-specific full-text search if available
            if "postgres" in settings.DATABASES["default"]["ENGINE"]:
                from django.contrib.postgres.search import SearchQuery, SearchRank
                search_query = SearchQuery(query)
                return (
                    queryset.annotate(rank=SearchRank(F("search_vector"), search_query))
                    .filter(search_vector=search_query)
                    .order_by("-rank", "asset_tag")
                    .distinct()
                )
            # Basic search for non-PostgreSQL databases
            return queryset.filter(
                Q(asset_tag__icontains=query) |
                Q(serial_number__icontains=query) |
                Q(name__icontains=query) |
                Q(manufacturer__icontains=query) |
                Q(model__icontains=query) |
                Q(category__icontains=query) |
                Q(location__icontains=query) |
                Q(status__icontains=query) |
                Q(condition__icontains=query) |
                Q(description__icontains=query) |
                Q(notes__icontains=query)
            ).distinct()
        return queryset

    def get_serializer_class(self):
        if self.request.method == "GET":
            return AssetListSerializer
        return AssetSerializer

    def perform_create(self, serializer):
        asset = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        ActivityLog.log_create(
            actor=self.request.user,
            instance=asset,
            message=f"Created asset: {asset.name} ({asset.asset_tag})",
        )


class AssetDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Asset.objects.select_related("created_by", "updated_by")
    serializer_class = AssetSerializer
    permission_classes = [AssetPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    lookup_field = "pk"
    http_method_names = ["get", "put", "patch", "delete", "head", "options"]

    def perform_update(self, serializer):
        # TODO: Implement change detection for a more detailed log message
        asset = serializer.save(updated_by=self.request.user)
        ActivityLog.log_update(
            actor=self.request.user,
            instance=asset,
            message=f"Updated asset: {asset.name} ({asset.asset_tag})",
        )

    def perform_destroy(self, instance):
        ActivityLog.log_delete(
            actor=self.request.user,
            instance=instance,
            message=f"Soft-deleted asset: {instance.name} ({instance.asset_tag})",
        )
        instance.soft_delete()


class AssetQRCodeView(APIView):
    """
    Retrieve the QR code for a specific asset.
    GET /api/assets/<pk>/qr-code/
    """
    permission_classes = [AssetPermission]

    def get(self, request, pk):
        asset = generics.get_object_or_404(Asset, pk=pk)

        if not asset.qr_code_image:
            # This can happen if the asset was created before this feature was added.
            # We can generate it on-the-fly.
            asset.generate_qr_code(save=True)
            asset.refresh_from_db()

        if not asset.qr_code_image:
            return Response({"error": "QR code could not be generated."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Serve the file directly
        return FileResponse(asset.qr_code_image.open(), content_type='image/png')


class AssetExportView(ExportAPIView):
    """
    Handles exporting asset data to a CSV file.
    GET /api/assets/export/
    """
    queryset = Asset.objects.select_related("created_by", "updated_by")
    serializer_class = AssetExportSerializer
    permission_classes = [AssetPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AssetFilter
    # Re-using search and ordering fields from the list view for consistency
    search_fields = AssetListCreateView.search_fields
    ordering_fields = AssetListCreateView.ordering_fields
    ordering = AssetListCreateView.ordering


class AssetBulkImportView(APIView):
    """
    Handles bulk creation of assets from a CSV file.
    POST /api/assets/bulk-import/
    """
    permission_classes = [AssetPermission]
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        serializer = AssetBulkImportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "CSV validation failed.", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assets_data = serializer.validated_data["assets"]
        created_assets = []

        try:
            with transaction.atomic():
                for asset_data in assets_data:
                    asset = Asset.objects.create(
                        **asset_data, created_by=request.user, updated_by=request.user
                    )
                    created_assets.append(asset)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred during transaction: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        ActivityLog.log(
            actor=request.user,
            action=ActivityLog.ActivityAction.CREATE,
            message=f"Bulk imported {len(created_assets)} assets from CSV file '{request.data.get('file').name}'.",
        )

        return Response({"detail": f"Successfully imported {len(created_assets)} assets."}, status=status.HTTP_201_CREATED)
