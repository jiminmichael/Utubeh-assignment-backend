from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, status, parsers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.views import ExportAPIView
from activity_logs.models import ActivityLog
from .filters import MaintenanceFilter
from .models import MaintenanceAttachment, MaintenanceRecord
from .pagination import MaintenancePagination
from .permissions import MaintenancePermission
from .serializers import (
    MaintenanceAttachmentSerializer,
    MaintenanceCancelSerializer,
    MaintenanceCompleteSerializer,
    MaintenanceListSerializer,
    MaintenanceExportSerializer,
    MaintenanceSerializer,
    MaintenanceStartSerializer,
)


class MaintenanceListCreateView(generics.ListCreateAPIView):
    queryset = MaintenanceRecord.objects.prefetch_related("attachments").select_related(
        "asset", "reported_by", "assigned_to", "created_by", "updated_by"
    )
    permission_classes = [MaintenancePermission]
    pagination_class = MaintenancePagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MaintenanceFilter
    search_fields = [
        "title",
        "description",
        "resolution_notes",
        "vendor_reference",
        "asset__asset_tag",
        "asset__serial_number",
        "asset__name",
        "asset__manufacturer",
        "asset__model",
        "assigned_to__username",
        "assigned_to__email",
        "assigned_to__first_name",
        "assigned_to__last_name",
        "reported_by__username",
        "reported_by__email",
    ]
    ordering_fields = [
        "created_at",
        "updated_at",
        "scheduled_for",
        "started_at",
        "completed_at",
        "status",
        "priority",
        "maintenance_type",
        "cost",
        "asset__asset_tag",
        "assigned_to__username",
    ]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return MaintenanceListSerializer
        return MaintenanceSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        record = serializer.save(
            reported_by=self.request.user,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        ActivityLog.log(
            actor=self.request.user,
            action=ActivityLog.ActivityAction.MAINTENANCE_REQUEST,
            instance=record,
            message=f"Created maintenance request for {record.asset.name}: '{record.title}'",
        )


class MaintenanceDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = MaintenanceRecord.objects.prefetch_related("attachments").select_related(
        "asset", "reported_by", "assigned_to", "created_by", "updated_by"
    )
    serializer_class = MaintenanceSerializer
    permission_classes = [MaintenancePermission]
    http_method_names = ["get", "put", "patch", "delete", "head", "options"]

    @transaction.atomic
    def perform_update(self, serializer):
        record = serializer.save(updated_by=self.request.user)
        ActivityLog.log_update(
            actor=self.request.user,
            instance=record,
            message=f"Updated maintenance request for {record.asset.name}: '{record.title}'",
        )

    def perform_destroy(self, instance):
        instance.soft_delete()
        ActivityLog.log_delete(
            actor=self.request.user,
            instance=instance,
            message=f"Soft-deleted maintenance request for {instance.asset.name}: '{instance.title}'",
        )


class MaintenanceStartView(APIView):
    permission_classes = [MaintenancePermission]

    @transaction.atomic
    def post(self, request, pk):
        record = generics.get_object_or_404(
            MaintenanceRecord.objects.select_related("asset", "assigned_to", "reported_by"),
            pk=pk,
        )
        self.check_object_permissions(request, record)
        serializer = MaintenanceStartSerializer(
            data=request.data,
            context={"request": request, "record": record},
        )
        serializer.is_valid(raise_exception=True)
        record = serializer.save()
        ActivityLog.log(
            actor=request.user,
            action=ActivityLog.ActivityAction.UPDATE,
            instance=record,
            message=f"Started maintenance for {record.asset.name}: '{record.title}'",
        )
        return Response(
            MaintenanceSerializer(record, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class MaintenanceAttachmentView(generics.CreateAPIView):
    """
    Upload an attachment for a maintenance record.
    POST /api/maintenance/<pk>/attachments/
    """
    permission_classes = [MaintenancePermission]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    serializer_class = MaintenanceAttachmentSerializer

    def perform_create(self, serializer):
        record = generics.get_object_or_404(MaintenanceRecord, pk=self.kwargs["pk"])
        attachment = serializer.save(
            maintenance_record=record,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        ActivityLog.log(
            actor=self.request.user,
            action=ActivityLog.ActivityAction.UPDATE,
            instance=record,
            message=f"Uploaded attachment '{attachment.name}' to maintenance record #{record.id}",)


class MaintenanceExportView(ExportAPIView):
    """
    Handles exporting maintenance records to a CSV file.
    GET /api/maintenance/export/
    """
    queryset = MaintenanceRecord.objects.select_related(
        "asset", "reported_by", "assigned_to", "created_by", "updated_by"
    )
    serializer_class = MaintenanceExportSerializer
    permission_classes = [MaintenancePermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MaintenanceFilter
    search_fields = MaintenanceListCreateView.search_fields
    ordering_fields = MaintenanceListCreateView.ordering_fields
    ordering = MaintenanceListCreateView.ordering


class MaintenanceCompleteView(APIView):
    permission_classes = [MaintenancePermission]

    @transaction.atomic
    def post(self, request, pk):
        record = generics.get_object_or_404(
            MaintenanceRecord.objects.select_related("asset", "assigned_to", "reported_by"),
            pk=pk,
        )
        self.check_object_permissions(request, record)
        serializer = MaintenanceCompleteSerializer(
            data=request.data,
            context={"request": request, "record": record},
        )
        serializer.is_valid(raise_exception=True)
        record = serializer.save()
        ActivityLog.log(
            actor=request.user,
            action=ActivityLog.ActivityAction.MAINTENANCE_COMPLETE,
            instance=record,
            message=f"Completed maintenance for {record.asset.name}: '{record.title}'",
        )
        return Response(
            MaintenanceSerializer(record, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class MaintenanceCancelView(APIView):
    permission_classes = [MaintenancePermission]

    @transaction.atomic
    def post(self, request, pk):
        record = generics.get_object_or_404(
            MaintenanceRecord.objects.select_related("asset", "assigned_to", "reported_by"),
            pk=pk,
        )
        self.check_object_permissions(request, record)
        serializer = MaintenanceCancelSerializer(
            data=request.data,
            context={"request": request, "record": record},
        )
        serializer.is_valid(raise_exception=True)
        record = serializer.save()
        ActivityLog.log(
            actor=request.user,
            action=ActivityLog.ActivityAction.UPDATE,
            instance=record,
            message=f"Canceled maintenance for {record.asset.name}: '{record.title}'",
        )
        return Response(
            MaintenanceSerializer(record, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )