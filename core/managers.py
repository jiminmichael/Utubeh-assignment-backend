from django.db import models


class ActiveManager(models.Manager):
    """Manager that filters out soft-deleted records."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Manager that returns all records including soft-deleted ones."""

    pass


class AssetManager(ActiveManager):
    """Custom manager for Asset model with common query methods."""

    def available(self):
        return self.filter(status="available")

    def assigned(self):
        return self.filter(status="assigned")

    def under_maintenance(self):
        return self.filter(status="maintenance")

    def retired(self):
        return self.filter(status="retired")

    def by_category(self, category):
        return self.filter(category=category)

    def recently_added(self, days=30):
        from django.utils import timezone

        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.filter(created_at__gte=cutoff)


class AssignmentManager(ActiveManager):
    """Custom manager for Assignment model."""

    def active(self):
        return self.filter(returned_at__isnull=True)

    def returned(self):
        return self.filter(returned_at__isnull=False)

    def overdue(self):
        from django.utils import timezone

        return self.active().filter(due_at__lt=timezone.now())

    def for_user(self, user):
        return self.filter(assigned_to=user)


class MaintenanceManager(ActiveManager):
    """Custom manager for MaintenanceRecord model."""

    def open(self):
        return self.filter(status="open")

    def in_progress(self):
        return self.filter(status="in_progress")

    def completed(self):
        return self.filter(status="completed")

    def critical(self):
        return self.filter(priority="critical")

    def for_asset(self, asset):
        return self.filter(asset=asset)


class NotificationManager(ActiveManager):
    """Custom manager for Notification model."""

    def unread(self):
        return self.filter(read_at__isnull=True)

    def for_recipient(self, user):
        return self.filter(recipient=user)

    def high_priority(self):
        return self.filter(priority="high")