import io
from pathlib import Path

import qrcode
from django.conf import settings
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.core.files.base import ContentFile
from django.db import models
from PIL import Image as PILImage

from core.choices import AssetCategory, AssetCondition, AssetStatus
from core.managers import AssetManager
from core.models import AuditableModel, SoftDeleteModel, TimeStampedModel
from core.validators import AssetTagValidator, FileValidator, SerialNumberValidator, validate_positive_cost


class Asset(TimeStampedModel, SoftDeleteModel, AuditableModel):
    """Represents a physical or digital asset in the organization's inventory."""

    name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Display name of the asset",
    )
    asset_tag = models.CharField(
        max_length=64,
        unique=True,
        validators=[AssetTagValidator()],
        db_index=True,
        help_text="Unique asset identifier (e.g., AST-2024-00001)",
    )
    serial_number = models.CharField(
        max_length=128,
        unique=True,
        blank=True,
        null=True,
        validators=[SerialNumberValidator()],
        db_index=True,
        help_text="Manufacturer serial number",
    )
    barcode = models.CharField(
        max_length=128,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
        help_text="Barcode or QR code value for scanning",
    )
    category = models.CharField(
        max_length=64,
        choices=AssetCategory.choices,
        db_index=True,
        help_text="Asset category type",
    )
    subcategory = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional subcategory for finer classification",
    )
    manufacturer = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Manufacturer or brand name",
    )
    model = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Manufacturer model name or number",
    )
    status = models.CharField(
        max_length=32,
        choices=AssetStatus.choices,
        default=AssetStatus.AVAILABLE,
        db_index=True,
        help_text="Current lifecycle status of the asset",
    )
    condition = models.CharField(
        max_length=32,
        choices=AssetCondition.choices,
        default=AssetCondition.GOOD,
        db_index=True,
        help_text="Current physical or operational condition",
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the asset",
    )
    purchase_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the asset was purchased",
    )
    purchase_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[validate_positive_cost],
        help_text="Purchase cost in the organization's currency",
    )
    warranty_expiry = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Date the manufacturer warranty expires",
    )
    warranty_provider = models.CharField(
        max_length=255,
        blank=True,
        help_text="Warranty provider name",
    )
    vendor_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Vendor/supplier name",
    )
    vendor_contact = models.CharField(
        max_length=255,
        blank=True,
        help_text="Vendor contact information",
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Physical location or room where the asset is kept",
    )
    image = models.ImageField(
        upload_to="assets/",
        blank=True,
        help_text="Photo of the asset",
        validators=[
            FileValidator(
                max_size=5 * 1024 * 1024,  # 5MB
                content_types=("image/jpeg", "image/png", "image/webp"),
            )
        ],
    )
    thumbnail = models.ImageField(
        upload_to="assets/thumbnails/",
        blank=True,
        null=True,
        editable=False,
        help_text="Auto-generated thumbnail",
    )
    qr_code_image = models.ImageField(
        upload_to="qrcodes/",
        blank=True,
        editable=False,
        help_text="Auto-generated QR code for the asset",
    )
    notes = models.TextField(
        blank=True,
        help_text="Internal notes or comments about the asset",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether the asset is currently active in the system",
    )
    custom_fields = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON field for custom metadata",
    )
    search_vector = SearchVectorField(
        null=True,
        editable=False,
        help_text="Optimized search vector for full-text search (PostgreSQL only).",
    )

    objects = AssetManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["asset_tag"]
        verbose_name = "Asset"
        verbose_name_plural = "Assets"
        indexes = [
            models.Index(fields=["asset_tag", "status"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["manufacturer", "model"]),
            models.Index(fields=["condition", "status"]),
            models.Index(fields=["purchase_date"]),
            models.Index(fields=["warranty_expiry"]),
            models.Index(fields=["location"]),
            models.Index(fields=["search_vector"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purchase_cost__gte=0) | models.Q(purchase_cost__isnull=True),
                name="check_purchase_cost_positive",
            ),
        ]

    def __str__(self):
        return f"{self.asset_tag} - {self.name}"

    def save(self, *args, **kwargs):
        """Override save to auto-generate asset tag and QR code if not provided."""
        is_new = self.pk is None
        if is_new and not self.asset_tag:
            self.asset_tag = self._generate_asset_tag()

        # Update search vector before saving if using PostgreSQL
        if "postgres" in settings.DATABASES["default"]["ENGINE"]:
            self.update_search_vector()

        super().save(*args, **kwargs)

        if self.image and not self.thumbnail:
            self.generate_thumbnail()
        if is_new and not self.qr_code_image:
            self.generate_qr_code(save=True)

    def update_search_vector(self):
        """Pre-calculates and sets the search vector field."""
        self.search_vector = (
            SearchVector("name", weight="A")
            + SearchVector("asset_tag", weight="A")
            + SearchVector("serial_number", weight="A")
            + SearchVector("manufacturer", weight="B")
            + SearchVector("model", weight="B")
            + SearchVector("category", weight="C")
            + SearchVector("location", weight="C")
        )

    def _generate_asset_tag(self):
        """Generate a unique asset tag in the format AST-YYYY-NNNNN."""
        from django.utils import timezone

        year = timezone.now().year
        last_asset = (
            Asset.all_objects.filter(asset_tag__startswith=f"AST-{year}-")
            .order_by("asset_tag")
            .last()
        )
        if last_asset:
            last_number = int(last_asset.asset_tag.split("-")[-1])
            new_number = last_number + 1
        else:
            new_number = 1
        return f"AST-{year}-{new_number:05d}"

    @property
    def is_overdue(self):
        """Check if warranty has expired."""
        from django.utils import timezone

        return self.warranty_expiry and self.warranty_expiry < timezone.now().date()

    @property
    def warranty_remaining_days(self):
        """Get number of days remaining in warranty."""
        from django.utils import timezone

        if not self.warranty_expiry:
            return 0
        delta = self.warranty_expiry - timezone.now().date()
        return max(delta.days, 0)

    def generate_thumbnail(self, size=(200, 200)):
        """Generate a thumbnail from the main image."""
        if not self.image:
            return

        img = PILImage.open(self.image)
        img.thumbnail(size)

        thumb_io = io.BytesIO()
        img_format = Path(self.image.name).suffix.lower().replace("jpg", "jpeg")[1:]
        img.save(thumb_io, format=img_format)

        thumb_name = f"{Path(self.image.name).stem}_thumb.{img_format}"
        self.thumbnail.save(
            thumb_name, ContentFile(thumb_io.getvalue()), save=False
        )

    def generate_qr_code(self, save=False):
        """Generate and save a QR code for the asset's detail URL."""
        if not self.pk:
            return

        qr_url = settings.ASSET_DETAIL_URL_FORMAT.format(pk=self.pk)
        qr_img = qrcode.make(qr_url, box_size=10, border=4)

        buffer = io.BytesIO()
        qr_img.save(buffer, format="PNG")

        file_name = f"{self.asset_tag or self.pk}_qr.png"
        self.qr_code_image.save(
            file_name,
            ContentFile(buffer.getvalue()),
            save=save,
        )
        if save:
            self.save(update_fields=["qr_code_image"])

    def mark_as(self, new_status):
        """Transition the asset to a new status."""
        valid_transitions = AssetStatus.values
        if new_status in valid_transitions:
            self.status = new_status
            self.save(update_fields=["status", "updated_at"])
            return True
        return False
