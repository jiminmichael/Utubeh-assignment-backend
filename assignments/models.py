from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from assets.models import Asset
from core.choices import AssetStatus, AssignmentStatus
from core.managers import AssignmentManager
from core.models import AuditableModel, SoftDeleteModel, TimeStampedModel


class Assignment(TimeStampedModel, SoftDeleteModel, AuditableModel):
    """Tracks the assignment of an asset to a user or employee."""

    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name="assignments",
        help_text="The asset being assigned",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="asset_assignments",
        help_text="The user receiving the asset",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_assets",
        help_text="The user who performed the assignment",
    )
    status = models.CharField(
        max_length=32,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ACTIVE,
        db_index=True,
        help_text="Current status of the assignment",
    )
    assigned_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the asset was assigned",
    )
    returned_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the asset was returned",
    )
    due_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Expected return date/time",
    )
    expected_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Expected location of the asset during assignment",
    )
    department = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text="Department responsible for this assignment",
    )
    condition_on_assign = models.TextField(
        blank=True,
        help_text="Condition notes when the asset was assigned",
    )
    condition_on_return = models.TextField(
        blank=True,
        help_text="Condition notes when the asset was returned",
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about the assignment",
    )

    objects = AssignmentManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-assigned_at"]
        verbose_name = "Assignment"
        verbose_name_plural = "Assignments"
        indexes = [
            models.Index(fields=["assigned_at", "returned_at"]),
            models.Index(fields=["status", "due_at"]),
            models.Index(fields=["department", "status"]),
            models.Index(fields=["asset", "status"]),
            models.Index(fields=["assigned_to", "status"]),
        ]

    def __str__(self):
        return f"{self.asset.asset_tag} → {self.assigned_to.get_full_name() or self.assigned_to.username}"

    def clean(self):
        """Validate assignment business rules."""
        super().clean()
        if self.returned_at and self.assigned_at and self.returned_at < self.assigned_at:
            raise ValidationError({"returned_at": "Return date cannot be before assignment date."})
        if self.due_at and self.assigned_at and self.due_at < self.assigned_at:
            raise ValidationError({"due_at": "Due date cannot be before assignment date."})
        if self.pk is None and self.status == AssignmentStatus.ACTIVE:
            if self.asset.status != AssetStatus.AVAILABLE:
                raise ValidationError({"asset": "Only available assets can be assigned."})
            active_assignment_exists = Assignment.objects.filter(
                asset=self.asset,
                status=AssignmentStatus.ACTIVE,
            ).exists()
            if active_assignment_exists:
                raise ValidationError({"asset": "This asset already has an active assignment."})

    def save(self, *args, **kwargs):
        """Override save to update asset status on assignment/return."""
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and self.status == AssignmentStatus.ACTIVE:
            self.asset.mark_as(AssetStatus.ASSIGNED)
        elif self.status == AssignmentStatus.RETURNED and self.returned_at:
            self.asset.mark_as(AssetStatus.AVAILABLE)
        elif self.status == AssignmentStatus.LOST:
            self.asset.mark_as(AssetStatus.LOST)

    def mark_returned(self, condition_notes="", returned_by=None):
        """Mark the assignment as returned."""
        from django.utils import timezone

        self.status = AssignmentStatus.RETURNED
        self.returned_at = timezone.now()
        if condition_notes:
            self.condition_on_return = condition_notes
        if returned_by:
            self.updated_by = returned_by
        self.save()

    @property
    def is_overdue(self):
        """Check if the assignment is overdue."""
        from django.utils import timezone

        if self.status == AssignmentStatus.ACTIVE and self.due_at:
            return self.due_at < timezone.now()
        return False

    @property
    def duration_days(self):
        """Get the duration of the assignment in days."""
        if not self.returned_at:
            from django.utils import timezone

            end = timezone.now()
        else:
            end = self.returned_at
        delta = end - self.assigned_at
        return delta.days
