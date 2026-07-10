"""
Comprehensive tests for the Reports module.

Tests cover all 8 reporting endpoints plus the dashboard:
1. Asset Summary (by status)
2. Warranty Expiry Report
3. Repair Report
4. Lost & Damaged Assets
5. Assignments by Department
6. Assets by Location
7. Assets by Device Type
8. Monthly Assignment Statistics
9. Dashboard Summary

All endpoints return data optimized for Chart.js visualizations.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from assets.models import Asset
from assignments.models import Assignment
from core.choices import AssetCondition, AssetStatus, AssignmentStatus, MaintenancePriority, MaintenanceStatus, MaintenanceType
from maintenance.models import MaintenanceRecord

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
        status=AssetStatus.AVAILABLE,
        condition=AssetCondition.GOOD,
        location="IT Storage",
    )
    defaults.update(kwargs)
    return Asset.objects.create(**defaults)


def create_assignment(asset=None, assigned_to=None, assigned_by=None, **kwargs):
    if asset is None:
        asset = create_asset()
    if assigned_to is None:
        assigned_to = create_viewer()
    defaults = dict(
        asset=asset,
        assigned_to=assigned_to,
        assigned_by=assigned_by,
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
        maintenance_type=MaintenanceType.CORRECTIVE,
        priority=MaintenancePriority.MEDIUM,
        status=MaintenanceStatus.OPEN,
    )
    defaults.update(kwargs)
    return MaintenanceRecord.objects.create(**defaults)


# =============================================================================
#  BASE TEST CASE
# =============================================================================

class ReportsAPITestCase(APITestCase):
    """Base class for all report API tests."""

    def setUp(self):
        self.client = APIClient()
        self.admin = create_admin()
        self.viewer = create_viewer()
        self.base_url = "/api/reports/"

    def _auth(self, user):
        self.client.force_authenticate(user=user)


# =============================================================================
#  1. ASSET SUMMARY TESTS
# =============================================================================

class AssetSummaryTests(ReportsAPITestCase):
    """Test the asset summary by status endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "asset-summary/"
        # Create assets in various statuses
        create_asset(asset_tag="AST-2026-00001", status=AssetStatus.AVAILABLE)
        create_asset(asset_tag="AST-2026-00002", status=AssetStatus.ASSIGNED)
        create_asset(asset_tag="AST-2026-00003", status=AssetStatus.MAINTENANCE)
        create_asset(asset_tag="AST-2026-00004", status=AssetStatus.LOST)
        create_asset(asset_tag="AST-2026-00005", status=AssetStatus.DISPOSED)
        create_asset(asset_tag="AST-2026-00006", status=AssetStatus.RETIRED)

    def test_unauthenticated_cannot_access(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_viewer_can_access(self):
        self._auth(self.viewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_returns_chartjs_format(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("labels", response.data)
        self.assertIn("datasets", response.data)
        self.assertIn("total", response.data)

    def test_returns_all_statuses(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["labels"]), 6)  # 6 statuses
        self.assertEqual(len(response.data["datasets"][0]["data"]), 6)

    def test_counts_are_correct(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["datasets"][0]["data"]
        self.assertEqual(data[0], 1)  # Available
        self.assertEqual(response.data["total"], 6)

    def test_has_background_colors(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        colors = response.data["datasets"][0]["backgroundColor"]
        self.assertEqual(len(colors), 6)
        for color in colors:
            self.assertTrue(color.startswith("#"))


# =============================================================================
#  2. WARRANTY EXPIRY REPORT TESTS
# =============================================================================

class WarrantyExpiryReportTests(ReportsAPITestCase):
    """Test the warranty expiry report endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "warranty-expiry/"
        today = timezone.localdate()
        # Assets with various warranty dates
        create_asset(asset_tag="AST-2026-0010", name="Expired", warranty_expiry=today - timedelta(days=30))
        create_asset(asset_tag="AST-2026-0011", name="Expiring Soon", warranty_expiry=today + timedelta(days=15))
        create_asset(asset_tag="AST-2026-0012", name="Expiring Later", warranty_expiry=today + timedelta(days=60))
        create_asset(asset_tag="AST-2026-0013", name="No Warranty", warranty_expiry=None)

    def test_returns_chartjs_format(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("labels", response.data)
        self.assertIn("datasets", response.data)
        self.assertIn("summary", response.data)
        self.assertIn("expiring_soonest", response.data)

    def test_summary_counts(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data["summary"]
        self.assertEqual(summary["expired"], 1)
        self.assertEqual(summary["no_warranty"], 1)

    def test_custom_months_param(self):
        self._auth(self.admin)
        response = self.client.get(self.url, {"months": "3"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["months_ahead"], 3)

    def test_expiring_soonest_returns_list(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data["expiring_soonest"], list)


# =============================================================================
#  3. REPAIR REPORT TESTS
# =============================================================================

class RepairReportTests(ReportsAPITestCase):
    """Test the repair/maintenance report endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "repairs/"
        asset = create_asset(asset_tag="AST-2026-0020")
        # Create maintenance records in various states
        create_maintenance(asset=asset, status=MaintenanceStatus.OPEN, priority=MaintenancePriority.CRITICAL)
        create_maintenance(asset=asset, status=MaintenanceStatus.IN_PROGRESS, priority=MaintenancePriority.HIGH)
        create_maintenance(asset=asset, status=MaintenanceStatus.COMPLETED, priority=MaintenancePriority.MEDIUM)
        create_maintenance(asset=asset, status=MaintenanceStatus.CANCELLED, priority=MaintenancePriority.LOW)

    def test_returns_chartjs_format(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("by_status", response.data)
        self.assertIn("by_type", response.data)
        self.assertIn("by_priority", response.data)
        self.assertIn("summary", response.data)

    def test_status_distribution(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_status = response.data["by_status"]
        self.assertIn("labels", by_status)
        self.assertIn("datasets", by_status)

    def test_summary_total_records(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["total_records"], 4)

    def test_custom_days_param(self):
        self._auth(self.admin)
        response = self.client.get(self.url, {"days": "30"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["period_days"], 30)


# =============================================================================
#  4. LOST & DAMAGED ASSETS TESTS
# =============================================================================

class LostDamagedAssetsTests(ReportsAPITestCase):
    """Test the lost and damaged assets endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "lost-damaged/"
        create_asset(asset_tag="AST-2026-0030", status=AssetStatus.LOST, condition=AssetCondition.DAMAGED)
        create_asset(asset_tag="AST-2026-0031", condition=AssetCondition.DAMAGED)
        create_asset(asset_tag="AST-2026-0032", condition=AssetCondition.NEEDS_REPAIR)
        create_asset(asset_tag="AST-2026-0033", condition=AssetCondition.GOOD)
        create_asset(asset_tag="AST-2026-0034", condition=AssetCondition.NEW)

    def test_returns_chartjs_format(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("condition_distribution", response.data)
        self.assertIn("lost_assets", response.data)
        self.assertIn("damaged_assets", response.data)
        self.assertIn("summary", response.data)

    def test_lost_assets_count(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["lost_assets"]["count"], 1)

    def test_damaged_assets_count(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 1 lost (also damaged) + 1 damaged + 1 needs_repair = 3, but lost is excluded from damaged
        self.assertEqual(response.data["damaged_assets"]["count"], 2)

    def test_summary(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["total_lost"], 1)
        self.assertEqual(response.data["summary"]["total_damaged"], 2)

    def test_condition_distribution_has_all_conditions(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cond = response.data["condition_distribution"]
        self.assertEqual(len(cond["labels"]), 6)  # 6 conditions


# =============================================================================
#  5. ASSIGNMENTS BY DEPARTMENT TESTS
# =============================================================================

class AssignmentsByDepartmentTests(ReportsAPITestCase):
    """Test the assignments by department endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "assignments-by-department/"
        asset1 = create_asset(asset_tag="AST-2026-0040")
        asset2 = create_asset(asset_tag="AST-2026-0041")
        asset3 = create_asset(asset_tag="AST-2026-0042")
        user = create_viewer(username="staff1", email="staff1@example.com")
        create_assignment(asset=asset1, assigned_to=user, assigned_by=self.admin, department="Engineering")
        create_assignment(asset=asset2, assigned_to=user, assigned_by=self.admin, department="Engineering")
        create_assignment(asset=asset3, assigned_to=user, assigned_by=self.admin, department="Finance")

    def test_returns_chartjs_format(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("labels", response.data)
        self.assertIn("datasets", response.data)
        self.assertIn("summary", response.data)

    def test_has_two_datasets(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["datasets"]), 2)  # Total + Active

    def test_summary_counts(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["total_assignments"], 3)
        self.assertEqual(response.data["summary"]["total_departments"], 2)

    def test_custom_days_param(self):
        self._auth(self.admin)
        response = self.client.get(self.url, {"days": "30"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# =============================================================================
#  6. ASSETS BY LOCATION TESTS
# =============================================================================

class AssetsByLocationTests(ReportsAPITestCase):
    """Test the assets by location endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "assets-by-location/"
        create_asset(asset_tag="AST-2026-0050", location="IT Storage")
        create_asset(asset_tag="AST-2026-0051", location="IT Storage")
        create_asset(asset_tag="AST-2026-0052", location="Server Room")
        create_asset(asset_tag="AST-2026-0053", location="")  # Unspecified

    def test_returns_chartjs_format(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("labels", response.data)
        self.assertIn("datasets", response.data)
        self.assertIn("summary", response.data)

    def test_location_counts(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["total_assets"], 4)
        self.assertEqual(response.data["summary"]["total_locations"], 3)

    def test_top_location(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["top_location"], "IT Storage")
        self.assertEqual(response.data["summary"]["top_location_count"], 2)

    def test_unspecified_location_grouped(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        labels = response.data["labels"]
        self.assertIn("Unspecified", labels)


# =============================================================================
#  7. ASSETS BY DEVICE TYPE TESTS
# =============================================================================

class AssetsByDeviceTypeTests(ReportsAPITestCase):
    """Test the assets by device type endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "assets-by-device-type/"
        create_asset(asset_tag="AST-2026-0060", category="laptop")
        create_asset(asset_tag="AST-2026-0061", category="laptop")
        create_asset(asset_tag="AST-2026-0062", category="desktop")
        create_asset(asset_tag="AST-2026-0063", category="monitor")
        create_asset(asset_tag="AST-2026-0064", category="printer")

    def test_returns_chartjs_format(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("labels", response.data)
        self.assertIn("datasets", response.data)
        self.assertIn("total", response.data)
        self.assertIn("category_details", response.data)

    def test_type_counts(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 5)

    def test_laptop_has_highest_count(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["datasets"][0]["data"]
        self.assertEqual(max(data), 2)  # Laptop has 2

    def test_category_details(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data["category_details"]), 0)


# =============================================================================
#  8. MONTHLY ASSIGNMENT STATISTICS TESTS
# =============================================================================

class MonthlyAssignmentStatsTests(ReportsAPITestCase):
    """Test the monthly assignment statistics endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "monthly-assignments/"
        asset1 = create_asset(asset_tag="AST-2026-0070")
        asset2 = create_asset(asset_tag="AST-2026-0071")
        user = create_viewer(username="staff2", email="staff2@example.com")
        # Create assignments in different months
        create_assignment(
            asset=asset1, assigned_to=user, assigned_by=self.admin,
            assigned_at=timezone.now() - timedelta(days=45),
            due_at=timezone.now() - timedelta(days=10),  # Overdue
        )
        create_assignment(
            asset=asset2, assigned_to=user, assigned_by=self.admin,
            assigned_at=timezone.now() - timedelta(days=15),
        )

    def test_returns_chartjs_format(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("labels", response.data)
        self.assertIn("datasets", response.data)
        self.assertIn("summary", response.data)

    def test_has_three_datasets(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["datasets"]), 3)  # Assignments, Returns, Overdue

    def test_summary_counts(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_active", response.data["summary"])
        self.assertIn("total_returned", response.data["summary"])
        self.assertIn("total_overdue", response.data["summary"])

    def test_custom_months_param(self):
        self._auth(self.admin)
        response = self.client.get(self.url, {"months": "6"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["months_back"], 6)

    def test_labels_are_month_names(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for label in response.data["labels"]:
            self.assertRegex(label, r"\w{3} \d{4}")  # e.g. "Jan 2026"


# =============================================================================
#  DASHBOARD SUMMARY TESTS
# =============================================================================

class DashboardSummaryTests(ReportsAPITestCase):
    """Test the dashboard summary endpoint."""

    def setUp(self):
        super().setUp()
        self.url = self.base_url + "dashboard/"
        create_asset(asset_tag="AST-2026-0080", status=AssetStatus.AVAILABLE)
        create_asset(asset_tag="AST-2026-0081", status=AssetStatus.ASSIGNED)
        create_asset(asset_tag="AST-2026-0082", status=AssetStatus.MAINTENANCE)
        create_asset(asset_tag="AST-2026-0083", status=AssetStatus.LOST)

    def test_returns_all_sections(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("summary", response.data)
        self.assertIn("asset_distribution_by_type", response.data)
        self.assertIn("assets_by_location", response.data)
        self.assertIn("recent_activities", response.data)
        self.assertIn("assignment_trends", response.data)
        self.assertIn("meta", response.data)

    def test_summary_counts(self):
        self._auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data["summary"]
        self.assertEqual(summary["total_assets"], 4)
        self.assertEqual(summary["available_assets"], 1)
        self.assertEqual(summary["assigned_assets"], 1)
        self.assertEqual(summary["devices_in_repair"], 1)
        self.assertEqual(summary["lost_devices"], 1)

    def test_custom_params(self):
        self._auth(self.admin)
        response = self.client.get(self.url, {
            "warranty_days": "60",
            "trend_days": "90",
            "recent_limit": "5",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        meta = response.data["meta"]
        self.assertEqual(meta["warranty_days"], 60)
        self.assertEqual(meta["trend_days"], 90)
        self.assertEqual(meta["recent_limit"], 5)

    def test_viewer_can_access(self):
        self._auth(self.viewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unauthenticated_cannot_access(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)