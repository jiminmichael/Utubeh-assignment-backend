from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from assets.models import Asset
from core.choices import AssetStatus, MaintenanceStatus

from .models import MaintenanceAttachment, MaintenanceRecord

User = get_user_model()


class MaintenanceAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.StringRelatedField(source="created_by", read_only=True)

    class Meta:
        model = MaintenanceAttachment
        fields = (
            "id",
            "name",
            "file",
            "uploaded_by",
            "created_at",
        )
        read_only_fields = ("id", "uploaded_by", "created_at")


class MaintenanceUserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "full_name", "role", "department")


class MaintenanceAssetSerializer(serializers.ModelSerializer):
    device_type = serializers.CharField(source="category", read_only=True)

    class Meta:
        model = Asset
        fields = (
            "id",
            "asset_tag",
            "serial_number",
            "name",
            "manufacturer",
            "model",
            "device_type",
            "location",
            "status",
            "condition",
        )


class MaintenanceSerializer(serializers.ModelSerializer):
    asset_detail = MaintenanceAssetSerializer(source="asset", read_only=True)
    reported_by_detail = MaintenanceUserSerializer(source="reported_by", read_only=True)
    assigned_to_detail = MaintenanceUserSerializer(source="assigned_to", read_only=True)
    duration_hours = serializers.FloatField(read_only=True)
    attachments = MaintenanceAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = MaintenanceRecord
        fields = (
            "id",
            "asset",
            "asset_detail",
            "reported_by",
            "reported_by_detail",
            "assigned_to",
            "assigned_to_detail",
            "title",
            "description",
            "maintenance_type",
            "priority",
            "status",
            "scheduled_for",
            "started_at",
            "completed_at",
            "resolution_notes",
            "cost",
            "vendor_reference",
            "duration_hours",
            "attachments",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "reported_by",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "duration_hours",
            "attachments",
        )

    def validate_assigned_to(self, value):
        if value and not value.is_active:
            raise serializers.ValidationError("Maintenance can only be assigned to active users.")
        return value

    def validate_asset(self, value):
        if self.instance and value.pk != self.instance.asset_id:
            raise serializers.ValidationError("The asset cannot be changed after creation.")
        return value

    def validate(self, attrs):
        instance = self.instance
        status = attrs.get("status", getattr(instance, "status", MaintenanceStatus.OPEN))
        completed_at = attrs.get("completed_at", getattr(instance, "completed_at", None))
        started_at = attrs.get("started_at", getattr(instance, "started_at", None))
        scheduled_for = attrs.get("scheduled_for", getattr(instance, "scheduled_for", None))

        if completed_at and started_at and completed_at < started_at:
            raise serializers.ValidationError(
                {"completed_at": "Completion date cannot be before start date."}
            )
        if scheduled_for and scheduled_for < timezone.now():
            raise serializers.ValidationError(
                {"scheduled_for": "Scheduled date cannot be in the past."}
            )

        # Auto-set timestamps based on status transitions
        if status == MaintenanceStatus.IN_PROGRESS and (not instance or instance.status != MaintenanceStatus.IN_PROGRESS):
            if not started_at:
                attrs["started_at"] = timezone.now()

        if status == MaintenanceStatus.COMPLETED:
            if not completed_at:
                attrs["completed_at"] = timezone.now()
            if not started_at:
                attrs["started_at"] = timezone.now()

        return attrs


class MaintenanceListSerializer(serializers.ModelSerializer):
    asset_tag = serializers.CharField(source="asset.asset_tag", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    serial_number = serializers.CharField(source="asset.serial_number", read_only=True)
    device_type = serializers.CharField(source="asset.category", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True)
    reported_by_name = serializers.CharField(source="reported_by.get_full_name", read_only=True)
    duration_hours = serializers.FloatField(read_only=True)

    class Meta:
        model = MaintenanceRecord
        fields = (
            "id",
            "asset",
            "asset_tag",
            "asset_name",
            "serial_number",
            "device_type",
            "title",
            "maintenance_type",
            "priority",
            "status",
            "assigned_to",
            "assigned_to_name",
            "reported_by",
            "reported_by_name",
            "scheduled_for",
            "started_at",
            "completed_at",
            "cost",
            "duration_hours",
            "created_at",
        )


class MaintenanceExportSerializer(serializers.ModelSerializer):
    """
    A simplified serializer for exporting maintenance records to CSV.
    """
    asset_tag = serializers.CharField(source="asset.asset_tag", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    reported_by_name = serializers.CharField(source="reported_by.get_full_name", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = MaintenanceRecord
        fields = (
            "id",
            "asset_tag",
            "asset_name",
            "title",
            "maintenance_type",
            "priority",
            "status",
            "reported_by_name",
            "assigned_to_name",
            "scheduled_for",
            "started_at",
            "completed_at",
            "cost",
            "vendor_reference",
            "resolution_notes",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
        )


class MaintenanceStartSerializer(serializers.Serializer):
    started_at = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        record = self.context["record"]
        if record.status not in [MaintenanceStatus.OPEN, MaintenanceStatus.ON_HOLD]:
            raise serializers.ValidationError(
                "Only OPEN or ON_HOLD maintenance can be started."
            )
        return attrs

    def save(self, **kwargs):
        record = self.context["record"]
        record.status = MaintenanceStatus.IN_PROGRESS
        record.started_at = self.validated_data.get("started_at", timezone.now())
        if self.validated_data.get("notes"):
            record.resolution_notes = self.validated_data["notes"]
        record.updated_by = self.context["request"].user
        record.save()
        return record


class MaintenanceCompleteSerializer(serializers.Serializer):
    completed_at = serializers.DateTimeField(required=False)
    resolution_notes = serializers.CharField(required=False, allow_blank=True)
    cost = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, allow_null=True)
    vendor_reference = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        record = self.context["record"]
        if record.status == MaintenanceStatus.COMPLETED:
            raise serializers.ValidationError("This maintenance record has already been completed.")
        if record.status == MaintenanceStatus.CANCELLED:
            raise serializers.ValidationError("This maintenance record has been cancelled.")
        completed_at = attrs.get("completed_at", timezone.now())
        if record.started_at and completed_at < record.started_at:
            raise serializers.ValidationError(
                {"completed_at": "Completion date cannot be before start date."}
            )
        attrs["completed_at"] = completed_at
        return attrs

    def save(self, **kwargs):
        record = self.context["record"]
        record.status = MaintenanceStatus.COMPLETED
        record.completed_at = self.validated_data["completed_at"]
        if self.validated_data.get("resolution_notes"):
            record.resolution_notes = self.validated_data["resolution_notes"]
        if self.validated_data.get("cost") is not None:
            record.cost = self.validated_data["cost"]
        if self.validated_data.get("vendor_reference"):
            record.vendor_reference = self.validated_data["vendor_reference"]
        record.updated_by = self.context["request"].user
        record.save()
        return record


class MaintenanceCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        record = self.context["record"]
        if record.status == MaintenanceStatus.COMPLETED:
            raise serializers.ValidationError("Cannot cancel a completed maintenance record.")
        if record.status == MaintenanceStatus.CANCELLED:
            raise serializers.ValidationError("This maintenance record has already been cancelled.")
        return attrs

    def save(self, **kwargs):
        record = self.context["record"]
        record.status = MaintenanceStatus.CANCELLED
        if self.validated_data.get("reason"):
            record.resolution_notes = self.validated_data["reason"]
        record.updated_by = self.context["request"].user
        record.save()
        return record