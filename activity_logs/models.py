from django.conf import settings
from django.db import models

from activity_logs.utils import get_client_ip
from core.choices import ActivityAction


class ActivityLog(models.Model):
    """Audit trail for tracking all significant actions in the system."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
        db_index=True,
        help_text="User who performed the action",
    )
    action = models.CharField(
        max_length=64,
        choices=ActivityAction.choices,
        db_index=True,
        help_text="Type of action performed",
    )
    entity_type = models.CharField(
        max_length=120,
        db_index=True,
        help_text="Type of entity affected (e.g., Asset, Assignment)",
    )
    entity_id = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text="ID or identifier of the affected entity",
    )
    entity_repr = models.CharField(
        max_length=255,
        blank=True,
        help_text="String representation of the entity at log time",
    )
    message = models.TextField(
        blank=True,
        help_text="Human-readable description of the action",
    )
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dictionary of field changes (old_value -> new_value)",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional contextual data in JSON format",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the actor",
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string from the request",
    )
    request_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Correlation ID to group related log entries",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the action occurred",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} on {self.entity_type} at {self.created_at:%Y-%m-%d %H:%M:%S}"

    @classmethod
    def log(
        cls,
        actor,
        action,
        entity_type,
        entity_id="",
        entity_repr="",
        message="",
        changes=None,
        metadata=None,
        ip_address=None,
        user_agent="",
        request_id="",
    ):
        """Factory method to create an activity log entry."""
        if ip_address is None:
            ip_address = get_client_ip()

        return cls.objects.create(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else "",
            entity_repr=entity_repr,
            message=message,
            changes=changes or {},
            metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )

    @classmethod
    def log_create(cls, actor, instance, ip_address=None, request_id="", **kwargs):
        """Log a create action for a model instance."""
        return cls.log(
            actor=actor,
            action=ActivityAction.CREATE,
            entity_type=instance._meta.model_name,
            entity_id=instance.pk,
            entity_repr=str(instance),
            message=f"Created {instance._meta.verbose_name}: {instance}",
            ip_address=ip_address,
            request_id=request_id,
            metadata=kwargs,
        )

    @classmethod
    def log_update(cls, actor, instance, changes=None, ip_address=None, request_id="", **kwargs):
        """Log an update action for a model instance."""
        return cls.log(
            actor=actor,
            action=ActivityAction.UPDATE,
            entity_type=instance._meta.model_name,
            entity_id=instance.pk,
            entity_repr=str(instance),
            changes=changes or {},
            message=f"Updated {instance._meta.verbose_name}: {instance}",
            ip_address=ip_address,
            request_id=request_id,
            metadata=kwargs,
        )

    @classmethod
    def log_delete(cls, actor, instance, ip_address=None, request_id="", **kwargs):
        """Log a delete action for a model instance."""
        return cls.log(
            actor=actor,
            action=ActivityAction.DELETE,
            entity_type=instance._meta.model_name,
            entity_id=instance.pk,
            entity_repr=str(instance),
            message=f"Deleted {instance._meta.verbose_name}: {instance}",
            ip_address=ip_address,
            request_id=request_id,
            metadata=kwargs,
        )