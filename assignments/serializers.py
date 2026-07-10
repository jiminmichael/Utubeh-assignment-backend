from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from assets.models import Asset
from core.choices import AssetStatus, AssignmentStatus

from .models import Assignment

User = get_user_model()


class AssignmentUserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "full_name", "role", "department")


class AssignmentAssetSerializer(serializers.ModelSerializer):
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


class AssignmentSerializer(serializers.ModelSerializer):
    asset_detail = AssignmentAssetSerializer(source="asset", read_only=True)
    assigned_to_detail = AssignmentUserSerializer(source="assigned_to", read_only=True)
    assigned_by_detail = AssignmentUserSerializer(source="assigned_by", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    duration_days = serializers.IntegerField(read_only=True)

    class Meta:
        model = Assignment
        fields = (
            "id",
            "asset",
            "asset_detail",
            "assigned_to",
            "assigned_to_detail",
            "assigned_by",
            "assigned_by_detail",
            "status",
            "assigned_at",
            "due_at",
            "returned_at",
            "expected_location",
            "department",
            "condition_on_assign",
            "condition_on_return",
            "notes",
            "is_overdue",
            "duration_days",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "assigned_by",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "is_overdue",
            "duration_days",
        )

    def validate_assigned_to(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Assets can only be assigned to active users.")
        return value

    def validate_asset(self, value):
        if self.instance and value.pk != self.instance.asset_id:
            raise serializers.ValidationError("The assigned asset cannot be changed after creation.")
        return value

    def validate(self, attrs):
        instance = self.instance
        asset = attrs.get("asset", getattr(instance, "asset", None))
        status = attrs.get("status", getattr(instance, "status", AssignmentStatus.ACTIVE))
        assigned_at = attrs.get("assigned_at", getattr(instance, "assigned_at", timezone.now()))
        due_at = attrs.get("due_at", getattr(instance, "due_at", None))
        returned_at = attrs.get("returned_at", getattr(instance, "returned_at", None))

        if due_at and assigned_at and due_at < assigned_at:
            raise serializers.ValidationError({"due_at": "Expected return date cannot be before assignment date."})
        if returned_at and assigned_at and returned_at < assigned_at:
            raise serializers.ValidationError({"returned_at": "Actual return date cannot be before assignment date."})

        if instance is None and status == AssignmentStatus.ACTIVE:
            if asset.status != AssetStatus.AVAILABLE:
                raise serializers.ValidationError({"asset": "Only available assets can be assigned."})
            if Assignment.objects.filter(asset=asset, status=AssignmentStatus.ACTIVE).exists():
                raise serializers.ValidationError({"asset": "This asset already has an active assignment."})

        if status == AssignmentStatus.RETURNED and not returned_at:
            attrs["returned_at"] = timezone.now()

        return attrs


class AssignmentListSerializer(serializers.ModelSerializer):
    asset_tag = serializers.CharField(source="asset.asset_tag", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    serial_number = serializers.CharField(source="asset.serial_number", read_only=True)
    device_type = serializers.CharField(source="asset.category", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True)
    assigned_to_username = serializers.CharField(source="assigned_to.username", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Assignment
        fields = (
            "id",
            "asset",
            "asset_tag",
            "asset_name",
            "serial_number",
            "device_type",
            "assigned_to",
            "assigned_to_name",
            "assigned_to_username",
            "status",
            "department",
            "assigned_at",
            "due_at",
            "returned_at",
            "expected_location",
            "is_overdue",
        )


class AssignmentReturnSerializer(serializers.Serializer):
    returned_at = serializers.DateTimeField(required=False)
    condition_on_return = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        assignment = self.context["assignment"]
        if assignment.status == AssignmentStatus.RETURNED:
            raise serializers.ValidationError("This assignment has already been returned.")
        returned_at = attrs.get("returned_at", timezone.now())
        if returned_at < assignment.assigned_at:
            raise serializers.ValidationError({"returned_at": "Actual return date cannot be before assignment date."})
        attrs["returned_at"] = returned_at
        return attrs

    def save(self, **kwargs):
        assignment = self.context["assignment"]
        assignment.status = AssignmentStatus.RETURNED
        assignment.returned_at = self.validated_data["returned_at"]
        assignment.condition_on_return = self.validated_data.get("condition_on_return", assignment.condition_on_return)
        if self.validated_data.get("notes"):
            assignment.notes = self.validated_data["notes"]
        assignment.updated_by = self.context["request"].user
        assignment.save()
        return assignment
