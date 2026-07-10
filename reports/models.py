from django.conf import settings
from django.db import models

from core.choices import ReportStatus, ReportType
from core.models import AuditableModel, TimeStampedModel


class Report(TimeStampedModel, AuditableModel):
    """Represents a generated report in the system."""

    name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Name/title of the report",
    )
    report_type = models.CharField(
        max_length=64,
        choices=ReportType.choices,
        default=ReportType.CUSTOM,
        db_index=True,
        help_text="Type/category of the report",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
        help_text="User who requested the report",
    )
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON parameters used to generate the report",
    )
    status = models.CharField(
        max_length=32,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
        db_index=True,
        help_text="Current generation status",
    )
    file = models.FileField(
        upload_to="reports/",
        blank=True,
        help_text="Generated report file (PDF, CSV, XLSX, etc.)",
    )
    file_format = models.CharField(
        max_length=16,
        blank=True,
        help_text="File format extension (pdf, csv, xlsx, etc.)",
    )
    file_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="File size in bytes",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if report generation failed",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When report generation started",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When report generation completed",
    )
    is_scheduled = models.BooleanField(
        default=False,
        help_text="Whether this is a scheduled/automated report",
    )
    schedule_cron = models.CharField(
        max_length=100,
        blank=True,
        help_text="Cron expression for scheduled reports",
    )
    recipients = models.JSONField(
        default=list,
        blank=True,
        help_text="List of email recipients for scheduled reports",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Report"
        verbose_name_plural = "Reports"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["report_type"]),
            models.Index(fields=["requested_by", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.name

    def mark_as_running(self):
        """Mark the report as currently being generated."""
        from django.utils import timezone

        self.status = ReportStatus.RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at", "updated_at"])

    def mark_as_completed(self, file_path="", file_format="", file_size=0):
        """Mark the report as successfully generated."""
        from django.utils import timezone

        self.status = ReportStatus.COMPLETED
        self.completed_at = timezone.now()
        if file_path:
            self.file = file_path
        if file_format:
            self.file_format = file_format
        if file_size:
            self.file_size = file_size
        self.save(
            update_fields=[
                "status",
                "completed_at",
                "file",
                "file_format",
                "file_size",
                "updated_at",
            ]
        )

    def mark_as_failed(self, error_message=""):
        """Mark the report as failed."""
        from django.utils import timezone

        self.status = ReportStatus.FAILED
        self.completed_at = timezone.now()
        if error_message:
            self.error_message = error_message
        self.save(update_fields=["status", "completed_at", "error_message", "updated_at"])