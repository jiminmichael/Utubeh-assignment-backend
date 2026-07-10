"""
Comprehensive tests for the Notifications module.

Tests cover:
- Model: creation, read/unread state, factory method, mark_as_read, mark_as_unread, mark_all_as_read
- API: list, detail, mark read, mark all read, mark unread, unread count, clear all, generate
- Notification Generator Service: warranty expiry, overdue assignments, maintenance completion, new assignments
- Permissions: user-specific retrieval (users can only see their own notifications)
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

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
from .services import NotificationGenerator

User = get_user_model()


# =============================================================================
#  HELPER FACTORIES
# =============================================================================

def create_admin(**kwargs):
    defaults = dict(
        username="admin",
        email="admin@example.com",
        password="password123",
        role=User.Role.ADMIN,
    )
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def create_it_staff(**kwargs):
    defaults = dict(
        username="itstaff",
        email="itstaff@example.com",
        password="password123",
        role=User.Role.IT_STAFF,
    )
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def create_viewer(**kwargs):
    defaults = dict(
        username="viewer",
        email="viewer@example.com",
        password="password123",
        role=User.Role.VIEWER,
    )
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def create_asset(**kwargs):
    defaults = dict(
        name="Test Laptop",
        asset_tag="AST-2026-00001",
        serial_number="SN-TEST-001",
        category="laptop",
        status="available",
        condition="good",
    )
    defaults.update(kwargs)
    return Asset.objects.create(**defaults)


def create_notification(recipient=None, **kwargs):
    if recipient is None:
        recipient = create_viewer()
    defaults = dict(
        recipient=recipient,
        notification_type=NotificationType.SYSTEM,
        priority=NotificationPriority.MEDIUM,
        title="Test Notification",
        message="This is a test notification.",
    )
    defaults.update(kwargs)
    return Notification.objects.create(**defaults)


def create_assignment(asset=None, assigned_to=None, **kwargs):
    if asset is None:
        asset = create_asset()
    if assigned_to is None:
        assigned_to = create_viewer()
    defaults = dict(
        asset=asset,
        assigned_to=assigned_to,
        assigned_by=create_admin(),
        status=AssignmentStatus.ACTIVE,
        assigned_at=timezone.now(),
        due_at=timezone.now() + timedelta(days=14),
        department="Engineering",
    )
    defaults.update(kwargs)
    return Assignment.objects.create(**defaults)


def create_maintenance(asset=None, reported_by=None, **kwargs):
    if asset is None:
        asset = create_asset()
    if reported_by is None:
        reported_by = create_admin()
    defaults = dict(
        asset=asset,
        reported_by=reported_by,
        title="Test repair",
        description="Test description",
        status=MaintenanceStatus.OPEN,
    )
    defaults.update(kwargs)
    return MaintenanceRecord.objects.create(**defaults)


# =============================================================================
#  MODEL TESTS
# =============================================================================

class NotificationModelTests(TestCase):
    """Test the Notification model's business logic."""

    def setUp(self):
        self.user = create_viewer()

    def test_create_notification_success(self):
        """A valid notification can be created using the factory method."""
        notification = Notification.create_notification(
            recipient=self.user,
            title="Asset Assigned",
            message="You have been assigned a new laptop.",
            notification_type=NotificationType.ASSIGNMENT,
            priority=NotificationPriority.HIGH,
        )
        self.assertEqual(notification.title, "Asset Assigned")
        self.assertEqual(notification.notification_type, NotificationType.ASSIGNMENT)
        self.assertIsNone(notification.read_at)

    def test_is_read_false_when_unread(self):
        """A notification without read_at is unread."""
        notification = create_notification(recipient=self.user)
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

    def test_mark_as_read(self):
        """mark_as_read sets read_at to now."""
        notification = create_notification(recipient=self.user)
        notification.mark_as_read()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_mark_as_unread(self):
        """mark_as_unread sets read_at to None."""
        notification = create_notification(recipient=self.user)
        notification.mark_as_read()
        self.assertTrue(notification.is_read)
        notification.mark_as_unread()
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

    def test_mark_all_as_read(self):
        """mark_all_as_read marks all unread notifications for a user as read."""
        create_notification(recipient=self.user)
        create_notification(recipient=self.user, title="Second notification")
        self.assertEqual(Notification.objects.filter(recipient=self.user, read_at__isnull=True).count(), 2)
        Notification.mark_all_as_read(self.user)
        self.assertEqual(Notification.objects.filter(recipient=self.user, read_at__isnull=True).count(), 0)

    def test_str_representation(self):
        """__str__ displays type and title."""
        notification = create_notification(
            recipient=self.user,
            notification_type=NotificationType.ASSIGNMENT,
            title="New Device",
        )
        expected = "[Assignment] New Device"
        self.assertEqual(str(notification), expected)

    def test_recipient_filtering(self):
        """Notifications are specific to each user."""
        other_user = create_viewer(username="other", email="other@example.com")
        n1 = create_notification(recipient=self.user, title="User 1 notification")
        n2 = create_notification(recipient=other_user, title="User 2 notification")
        self.assertIn(n1, Notification.objects.filter(recipient=self.user))
        self.assertNotIn(n2, Notification.objects.filter(recipient=self.user))

    def test_ordering_newest_first(self):
        """Notifications are ordered by created_at descending."""
        n1 = create_notification(recipient=self.user, title="Older")
        n2 = create_notification(recipient=self.user, title="Newer")
        qs = Notification.objects.all()
        self.assertEqual(qs[0], n2)
        self.assertEqual(qs[1], n1)


# =============================================================================
#  API TESTS
# =============================================================================

class NotificationsAPITestCase(APITestCase):
    """Base class for notification API tests."""

    def setUp(self):
        self.client = APIClient()
        self.user = create_viewer()
        self.admin = create_admin()
        self.base_url = "/api/notifications/"

    def _auth(self, user):
        self.client.force_authenticate(user=user)


class NotificationListTests(NotificationsAPITestCase):
    """Test the notification list endpoint."""

    def setUp(self):
        super().setUp()
        for i in range(5):
            create_notification(recipient=self.user, title=f"Notification {i}")

    def test_unauthenticated_cannot_list(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_list(self):
        self._auth(self.user)
        response = self.client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 5)

    def test_returns_notification_data(self):
        self._auth(self.user)
        response = self.client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if len(response.data) > 0:
            item = response.data[0]
            self.assertIn("title", item)
            self.assertIn("message", item)
            self.assertIn("is_read", item)
            self.assertIn("time_ago", item)
            self.assertIn("notification_type", item)
            self.assertIn("priority", item)

    def test_user_cannot_see_others_notifications(self):
        """Users can only see their own notifications."""
        other_user = create_viewer(username="other", email="other@test.com")
        create_notification(recipient=other_user, title="Secret notification")
        self._auth(self.user)
        response = self.client.get(self.base_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [item["title"] for item in response.data]
        self.assertNotIn("Secret notification", titles)

    def test_unread_filter(self):
        """?unread=true returns only unread notifications."""
        self._auth(self.user)
        response = self.client.get(self.base_url, {"unread": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data:
            self.assertFalse(item["is_read"])

    def test_type_filter(self):
        """?type=assignment filters by notification type."""
        self._auth(self.user)
        create_notification(
            recipient=self.user,
            notification_type=NotificationType.ASSIGNMENT,
            title="Assignment notif",
        )
        response = self.client.get(self.base_url, {"type": "assignment"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data:
            self.assertEqual(item["notification_type"], "assignment")

    def test_limit_param(self):
        """?limit=N limits the number of results."""
        self._auth(self.user)
        response = self.client.get(self.base_url, {"limit": "2"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data), 2)


class NotificationDetailTests(NotificationsAPITestCase):
    """Test the notification detail endpoint."""

    def setUp(self):
        super().setUp()
        self.notification = create_notification(recipient=self.user)
        self.url = f"{self.base_url}{self.notification.id}/"

    def test_get_detail(self):
        self._auth(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Test Notification")

    def test_cannot_access_others_notification(self):
        other_user = create_viewer(username="other2", email="other2@test.com")
        other_notif = create_notification(recipient=other_user)
        self._auth(self.user)
        response = self.client.get(f"{self.base_url}{other_notif.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NotificationMarkReadTests(NotificationsAPITestCase):
    """Test marking notifications as read."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "mark-read/"
        self.notification = create_notification(recipient=self.user)

    def test_mark_specific_notifications_read(self):
        self._auth(self.user)
        response = self.client.post(self.url, {"ids": [self.notification.id]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)

    def test_mark_all_read(self):
        create_notification(recipient=self.user, title="Second")
        self._auth(self.user)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Notification.objects.filter(recipient=self.user, read_at__isnull=True).count(),
            0,
        )

    def test_cannot_mark_others_notifications(self):
        other_user = create_viewer(username="other3", email="other3@test.com")
        other_notif = create_notification(recipient=other_user)
        self._auth(self.user)
        response = self.client.post(self.url, {"ids": [other_notif.id]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        other_notif.refresh_from_db()
        self.assertFalse(other_notif.is_read)


class NotificationMarkUnreadTests(NotificationsAPITestCase):
    """Test marking a notification as unread."""

    def setUp(self):
        super().setUp()
        self.notification = create_notification(recipient=self.user)
        self.notification.mark_as_read()
        self.url = f"{self.base_url}{self.notification.id}/mark-unread/"

    def test_mark_unread(self):
        self._auth(self.user)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.notification.refresh_from_db()
        self.assertFalse(self.notification.is_read)

    def test_cannot_mark_others_unread(self):
        other_user = create_viewer(username="other4", email="other4@test.com")
        other_notif = create_notification(recipient=other_user)
        other_notif.mark_as_read()
        self._auth(self.user)
        response = self.client.post(f"{self.base_url}{other_notif.id}/mark-unread/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NotificationUnreadCountTests(NotificationsAPITestCase):
    """Test the unread count endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "unread-count/"
        create_notification(recipient=self.user)
        create_notification(recipient=self.user, title="Unread 2")
        read_notif = create_notification(recipient=self.user, title="Read")
        read_notif.mark_as_read()

    def test_unread_count(self):
        self._auth(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 2)


class NotificationClearAllTests(NotificationsAPITestCase):
    """Test clearing all notifications."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "clear-all/"
        create_notification(recipient=self.user)
        create_notification(recipient=self.user, title="Second")

    def test_clear_all(self):
        self._auth(self.user)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 0)

    def test_clear_all_only_own(self):
        other_user = create_viewer(username="other5", email="other5@test.com")
        create_notification(recipient=other_user)
        self._auth(self.user)
        self.client.delete(self.url)
        self.assertEqual(Notification.objects.filter(recipient=other_user).count(), 1)


# =============================================================================
#  NOTIFICATION GENERATOR SERVICE TESTS
# =============================================================================

class NotificationGeneratorTests(TestCase):
    """Test the NotificationGenerator service."""

    def setUp(self):
        self.admin = create_admin()
        self.viewer = create_viewer()
        self.it_staff = create_it_staff()

    def test_warranty_expiry_creates_notifications(self):
        """check_warranty_expiry creates notifications for expiring warranties."""
        today = timezone.localdate()
        create_asset(
            asset_tag="AST-2026-0100",
            name="Expiring Laptop",
            warranty_expiry=today + timedelta(days=15),
        )
        ids = NotificationGenerator.check_warranty_expiry(days_ahead=30, admin_only=False)
        self.assertGreater(len(ids), 0)
        # Verify notification content
        notif = Notification.objects.get(id=ids[0])
        self.assertIn("Warranty Expiring", notif.title)
        self.assertIn("Expiring Laptop", notif.message)

    def test_warranty_expiry_no_duplicates(self):
        """check_warranty_expiry does not create duplicate notifications."""
        today = timezone.localdate()
        create_asset(
            asset_tag="AST-2026-0101",
            name="Unique Asset",
            warranty_expiry=today + timedelta(days=20),
        )
        ids_first = NotificationGenerator.check_warranty_expiry(days_ahead=30)
        ids_second = NotificationGenerator.check_warranty_expiry(days_ahead=30)
        self.assertEqual(len(ids_second), 0)  # No new ones created

    def test_overdue_assignments_creates_notifications(self):
        """check_overdue_assignments creates notifications for overdue items."""
        asset = create_asset(asset_tag="AST-2026-0102")
        create_assignment(
            asset=asset,
            assigned_to=self.viewer,
            due_at=timezone.now() - timedelta(days=5),
        )
        ids = NotificationGenerator.check_overdue_assignments(admin_only=False)
        self.assertGreater(len(ids), 0)
        notif = Notification.objects.get(id=ids[0])
        self.assertIn("Overdue", notif.title)

    def test_maintenance_completion_creates_notifications(self):
        """check_maintenance_completion creates notifications for completed maintenance."""
        asset = create_asset(asset_tag="AST-2026-0103")
        record = create_maintenance(
            asset=asset,
            reported_by=self.viewer,
            status=MaintenanceStatus.COMPLETED,
            completed_at=timezone.now() - timedelta(minutes=30),
        )
        ids = NotificationGenerator.check_maintenance_completion(admin_only=False)
        self.assertGreater(len(ids), 0)
        notif = Notification.objects.get(id=ids[0])
        self.assertIn("Maintenance Completed", notif.title)

    def test_new_assignments_creates_notifications(self):
        """check_new_assignments creates notifications for newly assigned devices."""
        asset = create_asset(asset_tag="AST-2026-0104")
        create_assignment(
            asset=asset,
            assigned_to=self.viewer,
            created_at=timezone.now() - timedelta(minutes=30),
        )
        ids = NotificationGenerator.check_new_assignments(admin_only=False)
        self.assertGreater(len(ids), 0)
        notif = Notification.objects.get(id=ids[0])
        self.assertIn("New Device Assigned", notif.title)

    def test_run_all_checks_returns_counts(self):
        """run_all_checks returns a dict with counts per category."""
        today = timezone.localdate()
        create_asset(
            asset_tag="AST-2026-0105",
            name="Test Warranty",
            warranty_expiry=today + timedelta(days=10),
        )
        result = NotificationGenerator.run_all_checks()
        self.assertIn("warranty", result)
        self.assertIn("overdue", result)
        self.assertIn("maintenance_completed", result)
        self.assertIn("new_assignments", result)
        self.assertIsInstance(result["warranty"], int)


class NotificationGenerateAPITests(NotificationsAPITestCase):
    """Test the generate endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "generate/"
        today = timezone.localdate()
        create_asset(
            asset_tag="AST-2026-0200",
            name="Generation Test",
            warranty_expiry=today + timedelta(days=5),
        )

    def test_generate_endpoint_returns_counts(self):
        self._auth(self.admin)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("generated", response.data)
        self.assertIn("total", response.data)
        self.assertIn("detail", response.data)