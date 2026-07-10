"""
Notification generator service.

Automatically creates notifications for:
- Warranty expiry alerts
- Overdue assignment alerts
- Maintenance completion alerts
- Newly assigned device alerts
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from assets.models import Asset
from assignments.models import Assignment
from core.choices import (
    AssignmentStatus,
    MaintenanceStatus,
    NotificationPriority,
    NotificationType,
)
from maintenance.models import MaintenanceRecord

from .models import Notification

User = get_user_model()


class NotificationGenerator:
    """
    Service class for generating system notifications.
    Each method checks for conditions and creates notifications as needed.
    """

    # ------------------------------------------------------------------
    #  Warranty Expiry Alerts
    # ------------------------------------------------------------------

    @classmethod
    def check_warranty_expiry(cls, days_ahead=30, admin_only=True):
        """
        Generate notifications for assets whose warranty is expiring soon.
        Notifies IT staff and admins.

        Returns: list of created Notification IDs
        """
        today = timezone.localdate()
        expiry_end = today + timedelta(days=days_ahead)

        expiring_assets = Asset.objects.filter(
            warranty_expiry__gte=today,
            warranty_expiry__lte=expiry_end,
        )

        if not expiring_assets.exists():
            return []

        recipients = cls._get_alert_recipients(admin_only=admin_only)
        if not recipients:
            return []

        created_ids = []
        for asset in expiring_assets:
            days_left = (asset.warranty_expiry - today).days
            title = f"Warranty Expiring: {asset.name}"
            message = (
                f"The warranty for {asset.name} ({asset.asset_tag}) "
                f"will expire in {days_left} day{'s' if days_left != 1 else ''} "
                f"on {asset.warranty_expiry.strftime('%b %d, %Y')}."
            )
            action_url = f"/assets/{asset.id}/"

            for recipient in recipients:
                # Avoid duplicate notifications for the same asset+recipient
                existing = Notification.objects.filter(
                    recipient=recipient,
                    notification_type=NotificationType.WARRANTY,
                    related_entity_type="asset",
                    related_entity_id=asset.id,
                    read_at__isnull=True,
                ).exists()
                if existing:
                    continue

                notification = Notification.create_notification(
                    recipient=recipient,
                    title=title,
                    message=message,
                    notification_type=NotificationType.WARRANTY,
                    priority=NotificationPriority.MEDIUM,
                    action_url=action_url,
                    related_entity_type="asset",
                    related_entity_id=asset.id,
                )
                created_ids.append(notification.id)

        return created_ids

    # ------------------------------------------------------------------
    #  Overdue Assignment Alerts
    # ------------------------------------------------------------------

    @classmethod
    def check_overdue_assignments(cls, admin_only=False):
        """
        Generate notifications for overdue assignments.
        Notifies the assignee and optionally IT staff/admins.

        Returns: list of created Notification IDs
        """
        now = timezone.now()
        overdue_assignments = Assignment.objects.filter(
            status=AssignmentStatus.ACTIVE,
            due_at__lt=now,
        ).select_related("asset", "assigned_to", "assigned_by")

        if not overdue_assignments.exists():
            return []

        created_ids = []

        for assignment in overdue_assignments:
            days_overdue = (now - assignment.due_at).days
            title = "Overdue Asset Return"
            message = (
                f"{assignment.asset.name} ({assignment.asset.asset_tag}) "
                f"assigned to {assignment.assigned_to.get_full_name() or assignment.assigned_to.username} "
                f"is {days_overdue} day{'s' if days_overdue != 1 else ''} overdue. "
                f"It was due on {assignment.due_at.strftime('%b %d, %Y')}."
            )
            action_url = f"/assignments/{assignment.id}/"

            # Notify the assignee
            existing_assignee = Notification.objects.filter(
                recipient=assignment.assigned_to,
                notification_type=NotificationType.OVERDUE,
                related_entity_type="assignment",
                related_entity_id=assignment.id,
                read_at__isnull=True,
            ).exists()
            if not existing_assignee:
                notification = Notification.create_notification(
                    recipient=assignment.assigned_to,
                    title=title,
                    message=message,
                    notification_type=NotificationType.OVERDUE,
                    priority=NotificationPriority.HIGH,
                    action_url=action_url,
                    related_entity_type="assignment",
                    related_entity_id=assignment.id,
                )
                created_ids.append(notification.id)

            # Notify IT staff/admins
            if not admin_only:
                recipients = cls._get_alert_recipients(admin_only=False).exclude(
                    id=assignment.assigned_to.id
                )
                for recipient in recipients:
                    existing_admin = Notification.objects.filter(
                        recipient=recipient,
                        notification_type=NotificationType.OVERDUE,
                        related_entity_type="assignment",
                        related_entity_id=assignment.id,
                        read_at__isnull=True,
                    ).exists()
                    if existing_admin:
                        continue
                    notification = Notification.create_notification(
                        recipient=recipient,
                        title=title,
                        message=message,
                        notification_type=NotificationType.OVERDUE,
                        priority=NotificationPriority.HIGH,
                        action_url=action_url,
                        related_entity_type="assignment",
                        related_entity_id=assignment.id,
                    )
                    created_ids.append(notification.id)

        return created_ids

    # ------------------------------------------------------------------
    #  Maintenance Completion Alerts
    # ------------------------------------------------------------------

    @classmethod
    def check_maintenance_completion(cls, admin_only=True):
        """
        Generate notifications for recently completed maintenance.
        Notifies the reporter and IT staff/admins.

        Returns: list of created Notification IDs
        """
        recently = timezone.now() - timedelta(hours=1)
        completed_records = MaintenanceRecord.objects.filter(
            status=MaintenanceStatus.COMPLETED,
            completed_at__gte=recently,
        ).select_related("asset", "reported_by", "assigned_to")

        if not completed_records.exists():
            return []

        created_ids = []

        for record in completed_records:
            title = f"Maintenance Completed: {record.asset.name}"
            message = (
                f"Maintenance for {record.asset.name} ({record.asset.asset_tag}) "
                f"has been completed. "
                f"Issue: {record.title}. "
                f"{'Resolution: ' + record.resolution_notes if record.resolution_notes else ''}"
            )
            action_url = f"/maintenance/{record.id}/"

            # Notify the reporter
            if record.reported_by:
                existing_reporter = Notification.objects.filter(
                    recipient=record.reported_by,
                    notification_type=NotificationType.MAINTENANCE,
                    related_entity_type="maintenance",
                    related_entity_id=record.id,
                    read_at__isnull=True,
                ).exists()
                if not existing_reporter:
                    notification = Notification.create_notification(
                        recipient=record.reported_by,
                        title=title,
                        message=message,
                        notification_type=NotificationType.MAINTENANCE,
                        priority=NotificationPriority.MEDIUM,
                        action_url=action_url,
                        related_entity_type="maintenance",
                        related_entity_id=record.id,
                    )
                    created_ids.append(notification.id)

            # Notify IT staff/admins
            if not admin_only:
                recipients = cls._get_alert_recipients(admin_only=False)
                for recipient in recipients:
                    if record.reported_by and recipient.id == record.reported_by.id:
                        continue
                    existing_admin = Notification.objects.filter(
                        recipient=recipient,
                        notification_type=NotificationType.MAINTENANCE,
                        related_entity_type="maintenance",
                        related_entity_id=record.id,
                        read_at__isnull=True,
                    ).exists()
                    if existing_admin:
                        continue
                    notification = Notification.create_notification(
                        recipient=recipient,
                        title=title,
                        message=message,
                        notification_type=NotificationType.MAINTENANCE,
                        priority=NotificationPriority.MEDIUM,
                        action_url=action_url,
                        related_entity_type="maintenance",
                        related_entity_id=record.id,
                    )
                    created_ids.append(notification.id)

        return created_ids

    # ------------------------------------------------------------------
    #  New Assignment Alerts
    # ------------------------------------------------------------------

    @classmethod
    def check_new_assignments(cls, admin_only=False):
        """
        Generate notifications for recently created assignments.
        Notifies the assignee and optionally IT staff/admins.

        Returns: list of created Notification IDs
        """
        recently = timezone.now() - timedelta(hours=1)
        new_assignments = Assignment.objects.filter(
            created_at__gte=recently,
        ).select_related("asset", "assigned_to", "assigned_by")

        if not new_assignments.exists():
            return []

        created_ids = []

        for assignment in new_assignments:
            title = "New Device Assigned"
            message = (
                f"{assignment.asset.name} ({assignment.asset.asset_tag}) "
                f"has been assigned to {assignment.assigned_to.get_full_name() or assignment.assigned_to.username}. "
                f"{'Due back: ' + assignment.due_at.strftime('%b %d, %Y') if assignment.due_at else ''}"
            )
            action_url = f"/assignments/{assignment.id}/"

            # Notify the assignee
            existing_assignee = Notification.objects.filter(
                recipient=assignment.assigned_to,
                notification_type=NotificationType.ASSIGNMENT,
                related_entity_type="assignment",
                related_entity_id=assignment.id,
                read_at__isnull=True,
            ).exists()
            if not existing_assignee:
                notification = Notification.create_notification(
                    recipient=assignment.assigned_to,
                    title=title,
                    message=message,
                    notification_type=NotificationType.ASSIGNMENT,
                    priority=NotificationPriority.MEDIUM,
                    action_url=action_url,
                    related_entity_type="assignment",
                    related_entity_id=assignment.id,
                )
                created_ids.append(notification.id)

            # Notify IT staff/admins
            if not admin_only:
                recipients = cls._get_alert_recipients(admin_only=False).exclude(
                    id=assignment.assigned_to.id
                )
                for recipient in recipients:
                    existing_admin = Notification.objects.filter(
                        recipient=recipient,
                        notification_type=NotificationType.ASSIGNMENT,
                        related_entity_type="assignment",
                        related_entity_id=assignment.id,
                        read_at__isnull=True,
                    ).exists()
                    if existing_admin:
                        continue
                    notification = Notification.create_notification(
                        recipient=recipient,
                        title=title,
                        message=message,
                        notification_type=NotificationType.ASSIGNMENT,
                        priority=NotificationPriority.MEDIUM,
                        action_url=action_url,
                        related_entity_type="assignment",
                        related_entity_id=assignment.id,
                    )
                    created_ids.append(notification.id)

        return created_ids

    # ------------------------------------------------------------------
    #  Run All Checks (for scheduled tasks / cron)
    # ------------------------------------------------------------------

    @classmethod
    def run_all_checks(cls):
        """
        Run all notification generators.
        Useful for scheduled tasks (cron jobs, Celery beat, etc.).

        Returns: dict with counts per category
        """
        result = {
            "warranty": len(cls.check_warranty_expiry()),
            "overdue": len(cls.check_overdue_assignments()),
            "maintenance_completed": len(cls.check_maintenance_completion()),
            "new_assignments": len(cls.check_new_assignments()),
        }
        return result

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_alert_recipients(admin_only=True):
        """Get users who should receive alert notifications."""
        if admin_only:
            return User.objects.filter(
                Q(role=User.Role.ADMIN) | Q(is_superuser=True),
                is_active=True,
            )
        return User.objects.filter(
            Q(role=User.Role.ADMIN) | Q(role=User.Role.IT_STAFF) | Q(is_superuser=True),
            is_active=True,
        )