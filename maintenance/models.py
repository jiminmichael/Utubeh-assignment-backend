from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from assets.models import Asset
from core.choices import MaintenancePriority, MaintenanceStatus, MaintenanceType
from core.managers import MaintenanceManager
from core.models import AuditableModel, SoftDeleteModel, TimeStampedModel
from core.validators import FileValidator, validate_positive_cost


class MaintenanceRecord(TimeStampedModel, SoftDeleteModel, AuditableModel):
    """Tracks maintenance requests and work orders for assets."""

    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="maintenance_records",
        help_text="The asset requiring maintenance",
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_maintenance",
        help_text="User who reported the issue",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_maintenance",
        help_text="Technician or staff assigned to handle this",
    )
    title = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Short title/summary of the maintenance issue",
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the issue",
    )
    maintenance_type = models.CharField(
        max_length=32,
        choices=MaintenanceType.choices,
        default=MaintenanceType.CORRECTIVE,
        db_index=True,
        help_text="Type of maintenance",
    )
    priority = models.CharField(
        max_length=32,
        choices=MaintenancePriority.choices,
        default=MaintenancePriority.MEDIUM,
        db_index=True,
        help_text="Priority level of the maintenance request",
    )
    status = models.CharField(
        max_length=32,
        choices=MaintenanceStatus.choices,
        default=MaintenanceStatus.OPEN,
        db_index=True,
        help_text="Current status of the maintenance record",
    )
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Scheduled date/time for the maintenance",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the maintenance work actually started",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the maintenance was completed",
    )
    resolution_notes = models.TextField(
        blank=True,
        help_text="Notes on how the issue was resolved",
    )
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[validate_positive_cost],
        help_text="Cost of parts/labor for this maintenance",
    )
    vendor_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="External vendor/service provider reference number",
    )

    objects = MaintenanceManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Maintenance Record"
        verbose_name_plural = "Maintenance Records"
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["scheduled_for", "status"]),
            models.Index(fields=["asset", "status"]),
            models.Index(fields=["maintenance_type"]),
            models.Index(fields=["assigned_to", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cost__gte=0) | models.Q(cost__isnull=True),
                name="check_maintenance_cost_positive",
            ),
        ]

    def __str__(self):
        return f"{self.asset.asset_tag} - {self.title}"

    def clean(self):
        """Validate maintenance business rules."""
        super().clean()
        if self.completed_at and self.started_at and self.completed_at < self.started_at:
            raise ValidationError(
                {"completed_at": "Completion date cannot be before start date."}
            )
        if self.scheduled_for and self.created_at and self.scheduled_for < self.created_at:
            raise ValidationError(
                {"scheduled_for": "Scheduled date cannot be in the past."}
            )

    def save(self, *args, **kwargs):
        """Override save to update asset status when maintenance starts/completes."""
        is_new = self.pk is None
        old_status = None
        if not is_new:
            try:
                old_record = MaintenanceRecord.all_objects.get(pk=self.pk)
                old_status = old_record.status
            except MaintenanceRecord.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        # Update asset status based on maintenance status transitions
        if is_new and self.status in [MaintenanceStatus.OPEN, MaintenanceStatus.IN_PROGRESS]:
            self.asset.mark_as("maintenance")
        elif self.status == MaintenanceStatus.IN_PROGRESS and old_status != MaintenanceStatus.IN_PROGRESS:
            self.asset.mark_as("maintenance")
            if not self.started_at:
                from django.utils import timezone

                self.started_at = timezone.now()
                MaintenanceRecord.all_objects.filter(pk=self.pk).update(started_at=self.started_at)
        elif self.status == MaintenanceStatus.COMPLETED:
            self.asset.mark_as("available")
        elif self.status == MaintenanceStatus.CANCELLED:
            # Check if there are other open maintenance records for this asset
            other_open = MaintenanceRecord.all_objects.filter(
                asset=self.asset,
                status__in=[MaintenanceStatus.OPEN, MaintenanceStatus.IN_PROGRESS],
            ).exclude(pk=self.pk)
            if not other_open.exists():
                # Check if asset is currently assigned
                from assignments.models import Assignment

                active_assignment = Assignment.all_objects.filter(
                    asset=self.asset, status="active"
                ).exists()
                if not active_assignment:
                    self.asset.mark_as("available")

    def start_maintenance(self, started_by=None):
        """Mark maintenance as in progress."""
        from django.utils import timezone

        self.status = MaintenanceStatus.IN_PROGRESS
        self.started_at = timezone.now()
        if started_by:
            self.updated_by = started_by
        self.save()

    def complete_maintenance(self, resolution_notes="", completed_by=None):
        """Mark maintenance as completed."""
        from django.utils import timezone

        self.status = MaintenanceStatus.COMPLETED
        self.completed_at = timezone.now()
        if resolution_notes:
            self.resolution_notes = resolution_notes
        if completed_by:
            self.updated_by = completed_by
        self.save()

    def cancel_maintenance(self, reason="", cancelled_by=None):
        """Cancel the maintenance record."""
        self.status = MaintenanceStatus.CANCELLED
        if reason:
            self.resolution_notes = reason
        if cancelled_by:
            self.updated_by = cancelled_by
        self.save()

    @property
    def duration_hours(self):
        """Get the duration of maintenance in hours."""
        if not self.started_at:
            return 0
        end = self.completed_at or self.updated_at
        delta = end - self.started_at
        return round(delta.total_seconds() / 3600, 2)


def maintenance_attachment_path(instance, filename):
    """File will be uploaded to MEDIA_ROOT/maintenance/<year>/<month>/<record_id>/<filename>"""
    now = timezone.now()
    return f"maintenance/{now.year}/{now.month}/{instance.maintenance_record.id}/{filename}"


class MaintenanceAttachment(TimeStampedModel, AuditableModel):
    """Stores files related to a maintenance record."""

    maintenance_record = models.ForeignKey(
        MaintenanceRecord,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    name = models.CharField(max_length=255, help_text="Display name for the file")
    file = models.FileField(
        upload_to=maintenance_attachment_path,
        validators=[
            FileValidator(
                max_size=10 * 1024 * 1024,  # 10MB
                content_types=(
                    "image/jpeg", "image/png", "image/webp", "application/pdf",
                    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            )
        ],
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} for Maintenance #{self.maintenance_record.id}"