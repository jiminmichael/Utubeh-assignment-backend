import csv
import io

from django.utils import timezone
from rest_framework import serializers

from .models import Asset


class AssetSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    warranty_remaining_days = serializers.IntegerField(read_only=True)

    class Meta:
        model = Asset
        fields = (
            "id",
            "name",
            "asset_tag",
            "serial_number",
            "barcode",
            "category",
            "subcategory",
            "manufacturer",
            "model",
            "status",
            "condition",
            "description",
            "purchase_date",
            "purchase_cost",
            "warranty_expiry",
            "warranty_provider",
            "vendor_name",
            "vendor_contact",
            "location",
            "image",
            "qr_code_image",
            "thumbnail",
            "notes",
            "is_active",
            "custom_fields",
            "is_overdue",
            "warranty_remaining_days",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "is_overdue",
            "warranty_remaining_days",
            "qr_code_image",
            "thumbnail",
        )
        extra_kwargs = {
            "asset_tag": {"required": False, "allow_blank": True},
            "serial_number": {"required": False, "allow_blank": True, "allow_null": True},
            "barcode": {"required": False, "allow_blank": True, "allow_null": True},
            "image": {"required": False},
        }

    def validate_serial_number(self, value):
        value = value or None
        if value is None:
            return value

        queryset = Asset.all_objects.filter(serial_number__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("An asset with this serial number already exists.")
        return value

    def validate_barcode(self, value):
        value = value or None
        if value is None:
            return value

        queryset = Asset.all_objects.filter(barcode__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("An asset with this barcode already exists.")
        return value

    def validate_asset_tag(self, value):
        if not value:
            return value

        queryset = Asset.all_objects.filter(asset_tag__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("An asset with this asset tag already exists.")
        return value.upper()

    def validate_custom_fields(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Custom fields must be a JSON object.")
        return value

    def validate(self, attrs):
        purchase_date = attrs.get("purchase_date", getattr(self.instance, "purchase_date", None))
        warranty_expiry = attrs.get("warranty_expiry", getattr(self.instance, "warranty_expiry", None))

        if purchase_date and purchase_date > timezone.now().date():
            raise serializers.ValidationError({"purchase_date": "Purchase date cannot be in the future."})
        if purchase_date and warranty_expiry and warranty_expiry < purchase_date:
            raise serializers.ValidationError({"warranty_expiry": "Warranty expiry cannot be before purchase date."})

        return attrs


class AssetExportSerializer(serializers.ModelSerializer):
    """
    A simplified serializer for exporting asset data to CSV.
    """
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Asset
        fields = (
            "id",
            "name",
            "asset_tag",
            "serial_number",
            "barcode",
            "category",
            "subcategory",
            "manufacturer",
            "model",
            "status",
            "condition",
            "location",
            "purchase_date",
            "purchase_cost",
            "warranty_expiry",
            "vendor_name",
            "notes",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
        )


class AssetBulkImportSerializer(serializers.Serializer):
    """
    Serializer for bulk importing assets from a CSV file.
    Handles validation of the entire file, checks for internal and external duplicates,
    and prepares data for atomic creation.
    """
    file = serializers.FileField(
        write_only=True,
        help_text="CSV file with asset data. Required headers: name, category, status, condition. Optional: serial_number, manufacturer, model, etc.",
    )

    def validate_file(self, file):
        """Ensure the file is a valid CSV."""
        if not file.name.endswith(".csv"):
            raise serializers.ValidationError("File must be a CSV.")
        return file

    def validate(self, data):
        file = data["file"]
        errors = []
        assets_to_create = []
        seen_serial_numbers = set()
        seen_asset_tags = set()

        try:
            decoded_file = file.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(decoded_file))

            # Collect all serial numbers and asset tags from the CSV for efficient DB checking
            rows = list(reader)
            csv_serial_numbers = {row.get("serial_number") for row in rows if row.get("serial_number")}
            csv_asset_tags = {row.get("asset_tag") for row in rows if row.get("asset_tag")}

            existing_serials = set(
                Asset.all_objects.filter(serial_number__in=csv_serial_numbers).values_list(
                    "serial_number", flat=True
                )
            )
            existing_tags = set(
                Asset.all_objects.filter(asset_tag__in=csv_asset_tags).values_list(
                    "asset_tag", flat=True
                )
            )

            for i, row in enumerate(rows):
                row_num = i + 2  # Account for header row
                row_errors = {}

                # Check for duplicates within the CSV itself
                serial = row.get("serial_number")
                if serial:
                    if serial in seen_serial_numbers:
                        row_errors["serial_number"] = f"Duplicate serial number '{serial}' found in the CSV."
                    seen_serial_numbers.add(serial)
                    if serial in existing_serials:
                        row_errors["serial_number"] = f"An asset with serial number '{serial}' already exists."

                tag = row.get("asset_tag")
                if tag:
                    if tag in seen_asset_tags:
                        row_errors["asset_tag"] = f"Duplicate asset tag '{tag}' found in the CSV."
                    seen_asset_tags.add(tag)
                    if tag in existing_tags:
                        row_errors["asset_tag"] = f"An asset with asset tag '{tag}' already exists."

                # Use AssetSerializer for row-level validation
                serializer = AssetSerializer(data=row)
                if not serializer.is_valid():
                    for field, errs in serializer.errors.items():
                        row_errors[field] = errs[0]

                if row_errors:
                    errors.append({"row": row_num, "errors": row_errors})
                else:
                    assets_to_create.append(serializer.validated_data)

        except Exception as e:
            raise serializers.ValidationError(f"Error processing CSV file: {e}")

        if errors:
            raise serializers.ValidationError({"rows": errors})

        return {"assets": assets_to_create}


class AssetListSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True, source="is_overdue")
    warranty_remaining_days = serializers.IntegerField(read_only=True, source="warranty_remaining_days")

    class Meta:
        model = Asset
        fields = (
            "id",
            "name",
            "asset_tag",
            "serial_number",
            "category",
            "manufacturer",
            "model",
            "status",
            "condition",
            "location",
            "image",
            "qr_code_image",
            "thumbnail",
            "is_active",
            "is_overdue",
            "warranty_remaining_days",
            "created_at",
            "updated_at",
        )
