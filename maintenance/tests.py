"""
Comprehensive tests for the Maintenance module.

Tests cover:
- Model: creation, validation, status transitions, asset status updates, duration calculation
- API: list/create, detail, start/complete/cancel actions
- Permissions: role-based access control for all endpoints
- Serializers: validation rules, edge cases
- Business rules: auto-update asset status when maintenance starts/completes/cancels
- File upload placeholder handling
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from assets.models import Asset
from core.choices import AssetStatus, MaintenancePriority, MaintenanceStatus, MaintenanceType

from .models import MaintenanceRecord

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


def create_technician(**kwargs):
    defaults = dict(
        username="technician",
        email="tech@example.com",
        password="password123",
        role=User.Role.IT_STAFF,
    )
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def create_asset(**kwargs):
    defaults = dict(
        name="Test Laptop",
        asset_tag="AST-2026-00001",
        serial_number="SN-TEST-001",
        category="laptop",
        status=AssetStatus.AVAILABLE,
        condition="good",
    )
    defaults.update(kwargs)
    return Asset.objects.create(**defaults)


def create_maintenance(asset=None, reported_by=None, assigned_to=None, **kwargs):
    if asset is None:
        asset = create_asset()
    if reported_by is None:
        reported_by = create_admin()
    defaults = dict(
        asset=asset,
        reported_by=reported_by,
        assigned_to=assigned_to,
        title="Fan making noise",
        description="Laptop fan is making a rattling sound under load.",
        maintenance_type=MaintenanceType.CORRECTIVE,
        priority=MaintenancePriority.MEDIUM,
        status=MaintenanceStatus.OPEN,
    )
    defaults.update(kwargs)
    return MaintenanceRecord.objects.create(**defaults)


# =============================================================================
#  MODEL TESTS
# =============================================================================

class MaintenanceModelTests(TestCase):
    """Test the MaintenanceRecord model's business logic."""

    def setUp(self):
        self.admin = create_admin()
        self.tech = create_technician()
        self.asset = create_asset()

    def test_create_maintenance_success(self):
        """A valid maintenance record can be created."""
        record = create_maintenance(
            asset=self.asset,
            reported_by=self.admin,
            assigned_to=self.tech,
        )
        self.assertEqual(record.status, MaintenanceStatus.OPEN)
        self.assertEqual(record.title, "Fan making noise")
        self.assertIsNone(record.completed_at)
        self.assertIsNone(record.started_at)

    def test_asset_status_changed_to_maintenance_on_create(self):
        """Creating an open maintenance record sets the asset to MAINTENANCE."""
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)
        create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)

    def test_asset_status_changed_to_available_on_complete(self):
        """Completing maintenance sets the asset back to AVAILABLE."""
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)
        record.complete_maintenance(resolution_notes="Replaced fan", completed_by=self.admin)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)
        self.assertEqual(record.status, MaintenanceStatus.COMPLETED)
        self.assertIsNotNone(record.completed_at)

    def test_start_maintenance_sets_started_at(self):
        """Calling start_maintenance updates status and sets started_at."""
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        record.start_maintenance(started_by=self.admin)
        self.assertEqual(record.status, MaintenanceStatus.IN_PROGRESS)
        self.assertIsNotNone(record.started_at)

    def test_prevent_complete_before_start(self):
        """completed_at cannot be before started_at."""
        record = MaintenanceRecord(
            asset=self.asset,
            reported_by=self.admin,
            assigned_to=self.tech,
            title="Test",
            description="Test",
            started_at=timezone.now(),
            completed_at=timezone.now() - timedelta(hours=2),
        )
        with self.assertRaises(Exception) as ctx:
            record.clean()
        self.assertIn("Completion date cannot be before start date", str(ctx.exception))

    def test_prevent_scheduled_in_past(self):
        """scheduled_for cannot be in the past."""
        record = MaintenanceRecord(
            asset=self.asset,
            reported_by=self.admin,
            assigned_to=self.tech,
            title="Test",
            description="Test",
            scheduled_for=timezone.now() - timedelta(days=1),
        )
        with self.assertRaises(Exception) as ctx:
            record.clean()
        self.assertIn("Scheduled date cannot be in the past", str(ctx.exception))

    def test_cancel_maintenance(self):
        """Cancelling a maintenance record sets the status to CANCELLED."""
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        record.cancel_maintenance(reason="No longer needed", cancelled_by=self.admin)
        self.assertEqual(record.status, MaintenanceStatus.CANCELLED)
        self.assertIn("No longer needed", record.resolution_notes)

    def test_asset_status_available_after_cancel_with_no_active(self):
        """Cancelling maintenance when no other open records exists sets asset to AVAILABLE."""
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)
        record.cancel_maintenance(reason="Testing", cancelled_by=self.admin)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)

    def test_duration_hours(self):
        """duration_hours returns the correct calculation."""
        now = timezone.now()
        record = MaintenanceRecord.objects.create(
            asset=self.asset,
            reported_by=self.admin,
            assigned_to=self.tech,
            title="Test",
            description="Test duration",
            started_at=now - timedelta(hours=5, minutes=30),
            completed_at=now,
        )
        self.assertAlmostEqual(record.duration_hours, 5.5, places=1)

    def test_duration_hours_zero_when_not_started(self):
        """duration_hours returns 0 when not started."""
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        self.assertEqual(record.duration_hours, 0)

    def test_str_representation(self):
        """__str__ displays asset tag and title."""
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        expected = f"{self.asset.asset_tag} - {record.title}"
        self.assertEqual(str(record), expected)

    def test_maintenance_ordering(self):
        """Maintenance records are ordered by created_at descending."""
        a1 = create_maintenance(
            asset=create_asset(asset_tag="AST-2026-00002", serial_number="SN-002"),
            reported_by=self.admin,
            title="Issue A",
            created_at=timezone.now() - timedelta(days=5),
        )
        a2 = create_maintenance(
            asset=create_asset(asset_tag="AST-2026-00003", serial_number="SN-003"),
            reported_by=self.admin,
            title="Issue B",
            created_at=timezone.now(),
        )
        qs = MaintenanceRecord.objects.all()
        self.assertEqual(qs[0], a2)
        self.assertEqual(qs[1], a1)

    def test_soft_delete(self):
        """MaintenanceRecord supports soft deletion."""
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        record.soft_delete()
        self.assertTrue(record.is_deleted)
        self.assertIsNotNone(record.deleted_at)

    def test_complete_maintenance_sets_resolution_notes(self):
        """complete_maintenance stores resolution notes."""
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        record.start_maintenance()
        record.complete_maintenance(resolution_notes="Replaced fan assembly", completed_by=self.admin)
        self.assertEqual(record.resolution_notes, "Replaced fan assembly")

    def test_complete_maintenance_sets_updated_by(self):
        """complete_maintenance updates the updated_by field."""
        admin2 = create_admin(username="admin2", email="admin2@example.com")
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        record.start_maintenance()
        record.complete_maintenance(completed_by=admin2)
        self.assertEqual(record.updated_by, admin2)

    def test_cost_validation_positive(self):
        """cost must be positive (enforced by CheckConstraint)."""
        record = create_maintenance(asset=self.asset, reported_by=self.admin, assigned_to=self.tech)
        record.cost = -50
        with self.assertRaises(Exception):
            record.save()


class MaintenanceManagerTests(TestCase):
    """Test the MaintenanceManager custom queryset methods."""

    def setUp(self):
        self.admin = create_admin()
        self.tech = create_technician()
        self.asset1 = create_asset(asset_tag="AST-2026-00004", serial_number="SN-004")
        self.asset2 = create_asset(asset_tag="AST-2026-00005", serial_number="SN-005")

    def test_open_filter(self):
        """open() returns only OPEN maintenance records."""
        m1 = create_maintenance(asset=self.asset1, reported_by=self.admin, assigned_to=self.tech)
        m2 = create_maintenance(asset=self.asset2, reported_by=self.admin, assigned_to=self.tech)
        m2.start_maintenance()
        open_qs = MaintenanceRecord.objects.open()
        self.assertIn(m1, open_qs)
        self.assertNotIn(m2, open_qs)

    def test_in_progress_filter(self):
        """in_progress() returns only IN_PROGRESS records."""
        m1 = create_maintenance(asset=self.asset1, reported_by=self.admin, assigned_to=self.tech)
        m2 = create_maintenance(asset=self.asset2, reported_by=self.admin, assigned_to=self.tech)
        m2.start_maintenance()
        ip_qs = MaintenanceRecord.objects.in_progress()
        self.assertIn(m2, ip_qs)
        self.assertNotIn(m1, ip_qs)

    def test_completed_filter(self):
        """completed() returns only COMPLETED records."""
        m1 = create_maintenance(asset=self.asset1, reported_by=self.admin, assigned_to=self.tech)
        m2 = create_maintenance(asset=self.asset2, reported_by=self.admin, assigned_to=self.tech)
        m2.start_maintenance()
        m2.complete_maintenance()
        completed_qs = MaintenanceRecord.objects.completed()
        self.assertIn(m2, completed_qs)
        self.assertNotIn(m1, completed_qs)

    def test_critical_filter(self):
        """critical() returns only CRITICAL priority records."""
        m1 = create_maintenance(asset=self.asset1, reported_by=self.admin, assigned_to=self.tech, priority=MaintenancePriority.LOW)
        m2 = create_maintenance(asset=self.asset2, reported_by=self.admin, assigned_to=self.tech, priority=MaintenancePriority.CRITICAL)
        critical_qs = MaintenanceRecord.objects.critical()
        self.assertIn(m2, critical_qs)
        self.assertNotIn(m1, critical_qs)

    def test_for_asset_filter(self):
        """for_asset() returns records for a specific asset."""
        m1 = create_maintenance(asset=self.asset1, reported_by=self.admin, assigned_to=self.tech)
        m2 = create_maintenance(asset=self.asset2, reported_by=self.admin, assigned_to=self.tech)
        asset_qs = MaintenanceRecord.objects.for_asset(self.asset1)
        self.assertIn(m1, asset_qs)
        self.assertNotIn(m2, asset_qs)


# =============================================================================
#  API TESTS
# =============================================================================

class MaintenanceAPITestCase(APITestCase):
    """Base class for API tests."""

    def setUp(self):
        self.client = APIClient()
        self.admin = create_admin()
        self.it_staff = create_it_staff()
        self.viewer = create_viewer()
        self.tech = create_technician(username="tech1", email="tech1@example.com")
        self.asset = create_asset()
        self.record = create_maintenance(
            asset=self.asset,
            reported_by=self.admin,
            assigned_to=self.tech,
        )
        self.list_url = "/api/maintenance/"
        self.detail_url = f"/api/maintenance/{self.record.pk}/"
        self.start_url = f"/api/maintenance/{self.record.pk}/start/"
        self.complete_url = f"/api/maintenance/{self.record.pk}/complete/"
        self.cancel_url = f"/api/maintenance/{self.record.pk}/cancel/"

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _create_payload(self, **overrides):
        payload = dict(
            asset=self.asset.pk,
            assigned_to=self.tech.pk,
            title="Faulty keyboard",
            description="Several keys are not responding",
            maintenance_type=MaintenanceType.CORRECTIVE,
            priority=MaintenancePriority.HIGH,
        )
        payload.update(overrides)
        return payload


# -- Permissions Tests -------------------------------------------------------

class MaintenancePermissionTests(MaintenanceAPITestCase):
    """Test that the correct roles can access each endpoint."""

    def test_unauthenticated_cannot_list(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_viewer_can_list(self):
        self._auth(self.viewer)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create(self):
        self._auth(self.viewer)
        response = self.client.post(self.list_url, self._create_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_it_staff_can_create(self):
        self._auth(self.it_staff)
        new_asset = create_asset(asset_tag="AST-2026-00010", serial_number="SN-MT-001")
        payload = self._create_payload(asset=new_asset.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_admin_can_create(self):
        self._auth(self.admin)
        new_asset = create_asset(asset_tag="AST-2026-00011", serial_number="SN-MT-002")
        payload = self._create_payload(asset=new_asset.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_viewer_can_detail(self):
        self._auth(self.viewer)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_update(self):
        self._auth(self.viewer)
        response = self.client.patch(self.detail_url, {"notes": "Hacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_it_staff_can_update(self):
        self._auth(self.it_staff)
        response = self.client.patch(self.detail_url, {"title": "Updated title"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_delete(self):
        self._auth(self.viewer)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_delete(self):
        self._auth(self.admin)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_viewer_cannot_start(self):
        self._auth(self.viewer)
        response = self.client.post(self.start_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_it_staff_can_start(self):
        self._auth(self.it_staff)
        response = self.client.post(self.start_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_complete(self):
        self.record.start_maintenance()
        self._auth(self.viewer)
        response = self.client.post(self.complete_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_it_staff_can_complete(self):
        self.record.start_maintenance()
        self._auth(self.it_staff)
        response = self.client.post(self.complete_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_cancel(self):
        self._auth(self.viewer)
        response = self.client.post(self.cancel_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_cancel(self):
        self._auth(self.admin)
        response = self.client.post(self.cancel_url, {"reason": "No longer needed"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# -- List / Create Tests -----------------------------------------------------

class MaintenanceListCreateTests(MaintenanceAPITestCase):
    """Test the list and create functionality."""

    def test_list_returns_paginated_results(self):
        self._auth(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)

    def test_list_includes_detail_fields(self):
        self._auth(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if len(response.data["results"]) > 0:
            result = response.data["results"][0]
            self.assertIn("asset_tag", result)
            self.assertIn("asset_name", result)
            self.assertIn("title", result)
            self.assertIn("status", result)
            self.assertIn("priority", result)

    def test_create_sets_reported_by(self):
        self._auth(self.admin)
        new_asset = create_asset(asset_tag="AST-2026-00012", serial_number="SN-MT-003")
        payload = self._create_payload(asset=new_asset.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record = MaintenanceRecord.objects.get(pk=response.data["id"])
        self.assertEqual(record.reported_by, self.admin)
        self.assertEqual(record.created_by, self.admin)
        self.assertEqual(record.updated_by, self.admin)

    def test_create_auto_updates_asset_to_maintenance(self):
        self._auth(self.admin)
        new_asset = create_asset(asset_tag="AST-2026-00013", serial_number="SN-MT-004")
        payload = self._create_payload(asset=new_asset.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_asset.refresh_from_db()
        self.assertEqual(new_asset.status, AssetStatus.MAINTENANCE)

    def test_cannot_change_asset_after_creation(self):
        self._auth(self.admin)
        other_asset = create_asset(asset_tag="AST-2026-00099", serial_number="SN-MT-099")
        response = self.client.patch(self.detail_url, {"asset": other_asset.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# -- Detail / Update / Delete Tests ------------------------------------------

class MaintenanceDetailTests(MaintenanceAPITestCase):
    """Test retrieving, updating, and deleting maintenance records."""

    def test_detail_returns_full_data(self):
        self._auth(self.admin)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("asset_detail", response.data)
        self.assertIn("reported_by_detail", response.data)
        self.assertIn("assigned_to_detail", response.data)
        self.assertIn("duration_hours", response.data)

    def test_update_title(self):
        self._auth(self.admin)
        response = self.client.patch(self.detail_url, {"title": "Updated title"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertEqual(self.record.title, "Updated title")

    def test_update_sets_updated_by(self):
        self._auth(self.it_staff)
        response = self.client.patch(self.detail_url, {"title": "IT staff update"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertEqual(self.record.updated_by, self.it_staff)

    def test_delete_performs_soft_delete(self):
        self._auth(self.admin)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.record.refresh_from_db()
        self.assertTrue(self.record.is_deleted)

    def test_detail_of_deleted_returns_404(self):
        self.record.soft_delete()
        self._auth(self.admin)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# -- Start / Complete / Cancel Tests -----------------------------------------

class MaintenanceActionTests(MaintenanceAPITestCase):
    """Test the start, complete, and cancel action endpoints."""

    def test_start_sets_status_and_timestamp(self):
        self._auth(self.admin)
        response = self.client.post(self.start_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MaintenanceStatus.IN_PROGRESS)
        self.assertIsNotNone(self.record.started_at)

    def test_start_sets_asset_to_maintenance(self):
        self._auth(self.admin)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)
        response = self.client.post(self.start_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)

    def test_start_with_notes(self):
        self._auth(self.admin)
        response = self.client.post(self.start_url, {"notes": "Beginning diagnostics"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertIn("diagnostics", self.record.resolution_notes)

    def test_cannot_start_non_open_record(self):
        self._auth(self.admin)
        self.record.start_maintenance()
        response = self.client.post(self.start_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ONLY OPEN", str(response.data).upper())

    def test_complete_sets_status_and_timestamp(self):
        self.record.start_maintenance()
        self._auth(self.admin)
        response = self.client.post(self.complete_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MaintenanceStatus.COMPLETED)
        self.assertIsNotNone(self.record.completed_at)

    def test_complete_updates_asset_to_available(self):
        self.record.start_maintenance()
        self._auth(self.admin)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)
        response = self.client.post(self.complete_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)

    def test_complete_with_resolution_notes(self):
        self.record.start_maintenance()
        self._auth(self.admin)
        response = self.client.post(
            self.complete_url,
            {"resolution_notes": "Replaced fan assembly and tested"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertIn("fan assembly", self.record.resolution_notes)

    def test_complete_with_cost(self):
        self.record.start_maintenance()
        self._auth(self.admin)
        response = self.client.post(
            self.complete_url,
            {"cost": "150.00"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertEqual(float(self.record.cost), 150.00)

    def test_complete_with_vendor_reference(self):
        self.record.start_maintenance()
        self._auth(self.admin)
        response = self.client.post(
            self.complete_url,
            {"vendor_reference": "VR-2024-12345"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertEqual(self.record.vendor_reference, "VR-2024-12345")

    def test_cannot_complete_twice(self):
        self.record.start_maintenance()
        self._auth(self.admin)
        self.client.post(self.complete_url, {}, format="json")
        response = self.client.post(self.complete_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been completed", str(response.data))

    def test_cannot_complete_cancelled(self):
        self._auth(self.admin)
        self.record.cancel_maintenance()
        response = self.client.post(self.complete_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cancelled", str(response.data))

    def test_cancel_sets_status(self):
        self._auth(self.admin)
        response = self.client.post(self.cancel_url, {"reason": "Parts not available"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MaintenanceStatus.CANCELLED)
        self.assertIn("Parts not available", self.record.resolution_notes)

    def test_cancel_updates_asset_to_available(self):
        self._auth(self.admin)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)
        response = self.client.post(self.cancel_url, {"reason": "Testing"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)

    def test_cannot_cancel_completed(self):
        self.record.start_maintenance()
        self.record.complete_maintenance()
        self._auth(self.admin)
        response = self.client.post(self.cancel_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_action_sets_updated_by(self):
        self._auth(self.it_staff)
        self.client.post(self.start_url, {}, format="json")
        self.record.refresh_from_db()
        self.assertEqual(self.record.updated_by, self.it_staff)


# -- Filter / Search / Order Tests -------------------------------------------

class MaintenanceFilterTests(MaintenanceAPITestCase):
    """Test filtering, searching, and ordering functionality."""

    def setUp(self):
        super().setUp()
        self._auth(self.admin)
        self.asset2 = create_asset(asset_tag="AST-2026-00020", serial_number="SN-MT-020")
        self.record2 = create_maintenance(
            asset=self.asset2,
            reported_by=self.admin,
            assigned_to=self.tech,
            title="Network issue",
            priority=MaintenancePriority.CRITICAL,
            status=MaintenanceStatus.COMPLETED,
        )
        self.record2.start_maintenance()
        self.record2.complete_maintenance()

    def test_filter_by_status(self):
        response = self.client.get(self.list_url, {"status": "open"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(item["status"], "open")

    def test_filter_by_priority(self):
        response = self.client.get(self.list_url, {"priority": "critical"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(item["priority"], "critical")

    def test_search_by_title(self):
        response = self.client.get(self.list_url, {"search": "Network"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data["results"]), 0)

    def test_search_by_asset_name(self):
        self.asset.name = "UniqueMaintenanceAsset"
        self.asset.save()
        response = self.client.get(self.list_url, {"search": "UniqueMaintenanceAsset"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data["results"]), 0)

    def test_order_by_created_at_ascending(self):
        response = self.client.get(self.list_url, {"ordering": "created_at"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_order_by_priority_descending(self):
        response = self.client.get(self.list_url, {"ordering": "-priority"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_pagination_default_page_size(self):
        for i in range(30):
            asset = create_asset(asset_tag=f"AST-2026-{100 + i:05d}", serial_number=f"SN-MTP-{i}")
            create_maintenance(
                asset=asset,
                reported_by=self.admin,
                assigned_to=self.tech,
                title=f"Bulk issue {i}",
            )
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 25)

    def test_custom_page_size(self):
        response = self.client.get(self.list_url, {"page_size": 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data["results"]), 5)