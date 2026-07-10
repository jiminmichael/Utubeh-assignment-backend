from django.conf import settings
from django.db import models

from core.choices import NotificationPriority, NotificationType
from core.managers import NotificationManager
from core.models import SoftDeleteModel, TimeStampedModel


class Notification(TimeStampedModel, SoftDeleteModel):
    """System notification for users about assignments, maintenance, and other events."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
        help_text="User who receives this notification",
    )
    notification_type = models.CharField(
        max_length=32,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
        db_index=True,
        help_text="Category/type of notification",
    )
    priority = models.CharField(
        max_length=16,
        choices=NotificationPriority.choices,
        default=NotificationPriority.MEDIUM,
        db_index=True,
        help_text="Priority level of the notification",
    )
    title = models.CharField(
        max_length=255,
        help_text="Notification title/subject",
    )
    message = models.TextField(
        help_text="Notification body content",
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the notification was read by the recipient",
    )
    action_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="URL to navigate to when the notification is clicked",
    )
    related_entity_type = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Type of related entity (asset, assignment, maintenance, etc.)",
    )
    related_entity_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the related entity",
    )
    is_email_sent = models.BooleanField(
        default=False,
        help_text="Whether an email notification was also sent",
    )
    email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the email notification was sent",
    )

    objects = NotificationManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=["recipient", "read_at"]),
            models.Index(fields=["recipient", "notification_type"]),
            models.Index(fields=["recipient", "priority"]),
            models.Index(fields=["related_entity_type", "related_entity_id"]),
        ]

    def __str__(self):
        return f"[{self.get_notification_type_display()}] {self.title}"

    def mark_as_read(self):
        """Mark the notification as read."""
        from django.utils import timezone

        self.read_at = timezone.now()
        self.save(update_fields=["read_at", "updated_at"])

    def mark_as_unread(self):
        """Mark the notification as unread."""
        self.read_at = None
        self.save(update_fields=["read_at", "updated_at"])

    @property
    def is_read(self):
        """Check if the notification has been read."""
        return self.read_at is not None

    @classmethod
    def mark_all_as_read(cls, user):
        """Mark all unread notifications for a user as read."""
        from django.utils import timezone

        now = timezone.now()
        cls.objects.filter(recipient=user, read_at__isnull=True).update(read_at=now)

    @classmethod
    def create_notification(
        cls,
        recipient,
        title,
        message,
        notification_type=NotificationType.SYSTEM,
        priority=NotificationPriority.MEDIUM,
        action_url="",
        related_entity_type="",
        related_entity_id=None,
        created_by=None,
    ):
        """Factory method to create a notification with all fields."""
        return cls.objects.create(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            action_url=action_url,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            created_by=created_by,
        )