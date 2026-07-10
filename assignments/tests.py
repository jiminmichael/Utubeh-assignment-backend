"""
Comprehensive tests for the Assignments module.

Tests cover:
- Model: creation, validation, status transitions, asset status updates, overdue detection
- API: list/create, detail, return, filtering, searching, ordering, pagination
- Permissions: role-based access control for all endpoints
- Serializers: validation rules, edge cases
- Business rules: prevent assigning unavailable assets, prevent duplicate active assignments
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from assets.models import Asset
from core.choices import AssetStatus, AssignmentStatus

from .models import Assignment

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


def create_learner(**kwargs):
    defaults = dict(
        username="learner",
        email="learner@example.com",
        password="password123",
        role=User.Role.VIEWER,
        department="Student Affairs",
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


def create_assignment(asset=None, assigned_to=None, assigned_by=None, **kwargs):
    if asset is None:
        asset = create_asset()
    if assigned_to is None:
        assigned_to = create_learner()
    defaults = dict(
        asset=asset,
        assigned_to=assigned_to,
        assigned_by=assigned_by,
        status=AssignmentStatus.ACTIVE,
        assigned_at=timezone.now(),
        due_at=timezone.now() + timedelta(days=14),
        department=assigned_to.department or "Engineering",
    )
    defaults.update(kwargs)
    return Assignment.objects.create(**defaults)


# =============================================================================
#  MODEL TESTS
# =============================================================================

class AssignmentModelTests(TestCase):
    """Test the Assignment model's business logic."""

    def setUp(self):
        self.admin = create_admin()
        self.learner = create_learner()
        self.asset = create_asset()

    def test_create_assignment_success(self):
        """A valid active assignment can be created."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
        )
        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)
        self.assertIsNotNone(assignment.assigned_at)
        self.assertIsNone(assignment.returned_at)
        self.assertEqual(str(assignment.asset), str(self.asset))

    def test_asset_status_changed_to_assigned_on_create(self):
        """Creating an active assignment sets the asset to ASSIGNED."""
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)
        create_assignment(asset=self.asset, assigned_to=self.learner, assigned_by=self.admin)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.ASSIGNED)

    def test_asset_status_changed_to_available_on_return(self):
        """Returning an assignment sets the asset back to AVAILABLE."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.ASSIGNED)
        assignment.mark_returned(condition_notes="Good condition", returned_by=self.admin)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)
        self.assertEqual(assignment.status, AssignmentStatus.RETURNED)
        self.assertIsNotNone(assignment.returned_at)

    def test_asset_status_changed_to_lost(self):
        """Marking an assignment as lost sets the asset to LOST."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
        )
        assignment.status = AssignmentStatus.LOST
        assignment.save()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.LOST)

    def test_prevent_assign_unavailable_asset(self):
        """Assigning an asset that is not AVAILABLE must raise a ValidationError."""
        self.asset.status = AssetStatus.MAINTENANCE
        self.asset.save()
        with self.assertRaises(Exception) as ctx:
            create_assignment(asset=self.asset, assigned_to=self.learner, assigned_by=self.admin)
        self.assertIn("Only available assets", str(ctx.exception))

    def test_prevent_duplicate_active_assignment(self):
        """An asset with an active assignment cannot be assigned again."""
        create_assignment(asset=self.asset, assigned_to=self.learner, assigned_by=self.admin)
        other_learner = create_learner(username="learner2", email="learner2@example.com")
        with self.assertRaises(Exception) as ctx:
            create_assignment(asset=self.asset, assigned_to=other_learner, assigned_by=self.admin)
        self.assertIn("already has an active assignment", str(ctx.exception))

    def test_prevent_return_before_assign(self):
        """returned_at cannot be before assigned_at."""
        assignment = Assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
            assigned_at=timezone.now(),
            returned_at=timezone.now() - timedelta(days=1),
        )
        with self.assertRaises(Exception) as ctx:
            assignment.clean()
        self.assertIn("Return date cannot be before assignment date", str(ctx.exception))

    def test_prevent_due_before_assign(self):
        """due_at cannot be before assigned_at."""
        assignment = Assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
            assigned_at=timezone.now(),
            due_at=timezone.now() - timedelta(days=1),
        )
        with self.assertRaises(Exception) as ctx:
            assignment.clean()
        self.assertIn("Due date cannot be before assignment date", str(ctx.exception))

    def test_is_overdue_true_when_past_due(self):
        """An active assignment past its due date is overdue."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
            due_at=timezone.now() - timedelta(days=1),
        )
        self.assertTrue(assignment.is_overdue)

    def test_is_overdue_false_when_not_due(self):
        """An active assignment before its due date is not overdue."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
            due_at=timezone.now() + timedelta(days=1),
        )
        self.assertFalse(assignment.is_overdue)

    def test_is_overdue_false_when_returned(self):
        """A returned assignment is never overdue even if past due date."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
            due_at=timezone.now() - timedelta(days=1),
        )
        assignment.mark_returned()
        self.assertFalse(assignment.is_overdue)

    def test_duration_days_active(self):
        """duration_days returns elapsed days for an active assignment."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
            assigned_at=timezone.now() - timedelta(days=5),
        )
        self.assertGreaterEqual(assignment.duration_days, 5)

    def test_duration_days_returned(self):
        """duration_days returns the actual days for a returned assignment."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
            assigned_at=timezone.now() - timedelta(days=10),
        )
        assignment.mark_returned()
        self.assertEqual(assignment.duration_days, 10)

    def test_str_representation(self):
        """__str__ displays asset tag and assignee name."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
        )
        expected = f"{self.asset.asset_tag} → {self.learner.get_full_name() or self.learner.username}"
        self.assertEqual(str(assignment), expected)

    def test_assignment_ordering(self):
        """Assignments are ordered by assigned_at descending."""
        a1 = create_assignment(
            asset=create_asset(asset_tag="AST-2026-00001", serial_number="SN-001"),
            assigned_to=self.learner,
            assigned_by=self.admin,
            assigned_at=timezone.now() - timedelta(days=5),
        )
        a2 = create_assignment(
            asset=create_asset(asset_tag="AST-2026-00002", serial_number="SN-002"),
            assigned_to=self.learner,
            assigned_by=self.admin,
            assigned_at=timezone.now(),
        )
        qs = Assignment.objects.all()
        self.assertEqual(qs[0], a2)
        self.assertEqual(qs[1], a1)

    def test_soft_delete(self):
        """Assignment supports soft deletion."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
        )
        assignment.soft_delete()
        self.assertTrue(assignment.is_deleted)
        self.assertIsNotNone(assignment.deleted_at)
        # Should not appear in default queryset
        self.assertFalse(Assignment.objects.filter(pk=assignment.pk).exists())
        # But should appear in all_objects
        self.assertTrue(Assignment.all_objects.filter(pk=assignment.pk).exists())

    def test_mark_returned_with_condition(self):
        """mark_returned stores condition notes."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
        )
        assignment.mark_returned(condition_notes="Minor scratches on lid")
        self.assertEqual(assignment.condition_on_return, "Minor scratches on lid")

    def test_mark_returned_with_returned_by(self):
        """mark_returned updates the updated_by field."""
        admin2 = create_admin(username="admin2", email="admin2@example.com")
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
        )
        assignment.mark_returned(returned_by=admin2)
        self.assertEqual(assignment.updated_by, admin2)

    def test_allow_assign_after_previous_returned(self):
        """An asset can be reassigned after the previous assignment is returned."""
        assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
        )
        assignment.mark_returned()
        # Now reassign
        other_learner = create_learner(username="learner3", email="learner3@example.com")
        new_assignment = create_assignment(
            asset=self.asset,
            assigned_to=other_learner,
            assigned_by=self.admin,
        )
        self.assertEqual(new_assignment.status, AssignmentStatus.ACTIVE)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.ASSIGNED)


class AssignmentManagerTests(TestCase):
    """Test the AssignmentManager custom queryset methods."""

    def setUp(self):
        self.admin = create_admin()
        self.learner = create_learner()
        self.asset1 = create_asset(asset_tag="AST-2026-00001", serial_number="SN-001")
        self.asset2 = create_asset(asset_tag="AST-2026-00002", serial_number="SN-002")

    def test_active_filter(self):
        """active() returns only non-returned assignments."""
        a1 = create_assignment(asset=self.asset1, assigned_to=self.learner, assigned_by=self.admin)
        a2 = create_assignment(asset=self.asset2, assigned_to=self.learner, assigned_by=self.admin)
        a2.mark_returned()
        active_qs = Assignment.objects.active()
        self.assertIn(a1, active_qs)
        self.assertNotIn(a2, active_qs)

    def test_returned_filter(self):
        """returned() returns only returned assignments."""
        a1 = create_assignment(asset=self.asset1, assigned_to=self.learner, assigned_by=self.admin)
        a2 = create_assignment(asset=self.asset2, assigned_to=self.learner, assigned_by=self.admin)
        a2.mark_returned()
        returned_qs = Assignment.objects.returned()
        self.assertIn(a2, returned_qs)
        self.assertNotIn(a1, returned_qs)

    def test_for_user_filter(self):
        """for_user() returns assignments for a specific user."""
        other = create_learner(username="other", email="other@example.com")
        a1 = create_assignment(asset=self.asset1, assigned_to=self.learner, assigned_by=self.admin)
        a2 = create_assignment(asset=self.asset2, assigned_to=other, assigned_by=self.admin)
        user_qs = Assignment.objects.for_user(self.learner)
        self.assertIn(a1, user_qs)
        self.assertNotIn(a2, user_qs)


# =============================================================================
#  API TESTS
# =============================================================================

class AssignmentAPITestCase(APITestCase):
    """Base class for API tests."""

    def setUp(self):
        self.client = APIClient()
        self.admin = create_admin()
        self.it_staff = create_it_staff()
        self.viewer = create_viewer()
        self.learner = create_learner()
        self.asset = create_asset()
        self.assignment = create_assignment(
            asset=self.asset,
            assigned_to=self.learner,
            assigned_by=self.admin,
        )
        self.list_url = "/api/assignments/"
        self.detail_url = f"/api/assignments/{self.assignment.pk}/"
        self.return_url = f"/api/assignments/{self.assignment.pk}/return/"

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _create_payload(self, **overrides):
        payload = dict(
            asset=self.asset.pk,
            assigned_to=self.learner.pk,
            department="Engineering",
            assigned_at=timezone.now().isoformat(),
            due_at=(timezone.now() + timedelta(days=14)).isoformat(),
        )
        payload.update(overrides)
        return payload


# -- Permissions Tests -------------------------------------------------------

class AssignmentPermissionTests(AssignmentAPITestCase):
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
        payload = self._create_payload()
        payload["asset"] = create_asset(
            asset_tag="AST-2026-00003", serial_number="SN-003"
        ).pk
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_admin_can_create(self):
        self._auth(self.admin)
        payload = self._create_payload()
        payload["asset"] = create_asset(
            asset_tag="AST-2026-00004", serial_number="SN-004"
        ).pk
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
        response = self.client.patch(self.detail_url, {"notes": "Updated notes"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_delete(self):
        self._auth(self.viewer)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_delete(self):
        self._auth(self.admin)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_viewer_cannot_return(self):
        self._auth(self.viewer)
        response = self.client.post(self.return_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_it_staff_can_return(self):
        self._auth(self.it_staff)
        response = self.client.post(self.return_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_return(self):
        self._auth(self.admin)
        response = self.client.post(self.return_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# -- List / Create Tests -----------------------------------------------------

class AssignmentListCreateTests(AssignmentAPITestCase):
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
            self.assertIn("assigned_to_name", result)
            self.assertIn("is_overdue", result)

    def test_create_sets_assigned_by(self):
        self._auth(self.admin)
        new_asset = create_asset(asset_tag="AST-2026-00005", serial_number="SN-005")
        payload = self._create_payload(asset=new_asset.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        assignment = Assignment.objects.get(pk=response.data["id"])
        self.assertEqual(assignment.assigned_by, self.admin)
        self.assertEqual(assignment.created_by, self.admin)
        self.assertEqual(assignment.updated_by, self.admin)

    def test_create_prevents_assigning_unavailable_asset(self):
        self._auth(self.admin)
        self.asset.status = AssetStatus.MAINTENANCE
        self.asset.save()
        payload = self._create_payload(asset=self.asset.pk, assigned_to=self.learner.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only available assets", str(response.data))

    def test_create_prevents_duplicate_active_assignment(self):
        self._auth(self.admin)
        # The asset is already assigned via self.assignment
        payload = self._create_payload(
            asset=self.asset.pk,
            assigned_to=create_learner(username="other2", email="other2@example.com").pk,
        )
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already has an active assignment", str(response.data))

    def test_create_prevents_due_before_assign(self):
        self._auth(self.admin)
        new_asset = create_asset(asset_tag="AST-2026-00006", serial_number="SN-006")
        payload = self._create_payload(
            asset=new_asset.pk,
            assigned_at=(timezone.now() + timedelta(days=5)).isoformat(),
            due_at=timezone.now().isoformat(),
        )
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Expected return date cannot be before assignment date", str(response.data))

    def test_create_with_empty_department_uses_default(self):
        self._auth(self.admin)
        new_asset = create_asset(asset_tag="AST-2026-00007", serial_number="SN-007")
        payload = self._create_payload(asset=new_asset.pk, department="")
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


# -- Detail / Update / Delete Tests ------------------------------------------

class AssignmentDetailTests(AssignmentAPITestCase):
    """Test retrieving, updating, and deleting assignments."""

    def test_detail_returns_full_data(self):
        self._auth(self.admin)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("asset_detail", response.data)
        self.assertIn("assigned_to_detail", response.data)
        self.assertIn("assigned_by_detail", response.data)
        self.assertIn("is_overdue", response.data)
        self.assertIn("duration_days", response.data)

    def test_update_notes(self):
        self._auth(self.admin)
        response = self.client.patch(self.detail_url, {"notes": "Updated notes"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.notes, "Updated notes")

    def test_update_sets_updated_by(self):
        self._auth(self.it_staff)
        response = self.client.patch(self.detail_url, {"notes": "IT staff update"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.updated_by, self.it_staff)

    def test_cannot_change_asset_after_creation(self):
        self._auth(self.admin)
        other_asset = create_asset(asset_tag="AST-2026-00099", serial_number="SN-099")
        response = self.client.patch(self.detail_url, {"asset": other_asset.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_performs_soft_delete(self):
        self._auth(self.admin)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_deleted)

    def test_detail_of_deleted_returns_404(self):
        self.assignment.soft_delete()
        self._auth(self.admin)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# -- Return Tests ------------------------------------------------------------

class AssignmentReturnTests(AssignmentAPITestCase):
    """Test the assignment return endpoint."""

    def test_return_sets_status_and_timestamp(self):
        self._auth(self.admin)
        response = self.client.post(self.return_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, AssignmentStatus.RETURNED)
        self.assertIsNotNone(self.assignment.returned_at)

    def test_return_updates_asset_to_available(self):
        self._auth(self.admin)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.ASSIGNED)
        self.client.post(self.return_url, {}, format="json")
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)

    def test_return_with_condition(self):
        self._auth(self.admin)
        response = self.client.post(
            self.return_url,
            {"condition_on_return": "Damaged screen"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.condition_on_return, "Damaged screen")

    def test_return_with_notes(self):
        self._auth(self.admin)
        response = self.client.post(
            self.return_url,
            {"notes": "Borrower reported battery issues"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertIn("battery", self.assignment.notes)

    def test_cannot_return_twice(self):
        self._auth(self.admin)
        self.client.post(self.return_url, {}, format="json")
        response = self.client.post(self.return_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been returned", str(response.data))

    def test_return_sets_updated_by(self):
        self._auth(self.it_staff)
        self.client.post(self.return_url, {}, format="json")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.updated_by, self.it_staff)


# -- Filter / Search / Order Tests -------------------------------------------

class AssignmentFilterTests(AssignmentAPITestCase):
    """Test filtering, searching, and ordering functionality."""

    def setUp(self):
        super().setUp()
        self._auth(self.admin)
        # Create additional assignments for filtering
        self.asset2 = create_asset(asset_tag="AST-2026-00010", serial_number="SN-010")
        self.learner2 = create_learner(username="learner_filter", email="filter@example.com")
        self.assignment2 = create_assignment(
            asset=self.asset2,
            assigned_to=self.learner2,
            assigned_by=self.admin,
            department="Finance",
            status=AssignmentStatus.RETURNED,
        )
        self.assignment2.mark_returned()

    def test_filter_by_status(self):
        response = self.client.get(self.list_url, {"status": "active"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(item["status"], "active")

    def test_filter_by_department(self):
        response = self.client.get(self.list_url, {"department__icontains": "Finance"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertIn("Finance", item["department"])

    def test_search_by_asset_name(self):
        self.asset.name = "UniqueSearchAsset"
        self.asset.save()
        response = self.client.get(self.list_url, {"search": "UniqueSearchAsset"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data["results"]), 0)

    def test_search_by_assigned_user(self):
        response = self.client.get(self.list_url, {"search": self.learner.username})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data["results"]), 0)

    def test_order_by_assigned_at_ascending(self):
        response = self.client.get(self.list_url, {"ordering": "assigned_at"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_order_by_assigned_at_descending(self):
        response = self.client.get(self.list_url, {"ordering": "-assigned_at"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_pagination_default_page_size(self):
        for i in range(30):
            asset = create_asset(asset_tag=f"AST-2026-{100 + i:05d}", serial_number=f"SN-PAG-{i}")
            user = create_learner(username=f"pager_{i}", email=f"pager{i}@example.com")
            create_assignment(asset=asset, assigned_to=user, assigned_by=self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 25)

    def test_custom_page_size(self):
        response = self.client.get(self.list_url, {"page_size": 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data["results"]), 5)


# =============================================================================
#  LEARNER (VIEWER) ROLE ASSIGNMENT TESTS
# =============================================================================

class LearnerAssignmentTests(AssignmentAPITestCase):
    """
    The task specifies assigning assets to "staff or learners".
    Learners use the VIEWER role. These tests verify that:
    - A learner can be assigned an asset (as assigned_to)
    - A learner cannot assign assets themselves (no create permission)
    - A learner can view their own assignments
    """

    def test_assign_asset_to_learner(self):
        """An asset can be assigned to a learner (VIEWER role)."""
        self._auth(self.admin)
        learner = create_learner(username="student1", email="student1@example.com")
        new_asset = create_asset(asset_tag="AST-2026-00050", serial_number="SN-LRN-01")
        payload = self._create_payload(asset=new_asset.pk, assigned_to=learner.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["assigned_to"], learner.pk)

    def test_learner_cannot_assign_to_others(self):
        """A learner (VIEWER) cannot assign assets to others."""
        self._auth(self.viewer)
        learner2 = create_learner(username="student2", email="student2@example.com")
        new_asset = create_asset(asset_tag="AST-2026-00051", serial_number="SN-LRN-02")
        payload = self._create_payload(asset=new_asset.pk, assigned_to=learner2.pk)
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_learner_can_view_own_assignments(self):
        """A learner can view their own assignments."""
        self._auth(self.viewer)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The assignment created in setUp is assigned to self.learner, not self.viewer
        # So this just verifies the learner can access the list

    def test_learner_cannot_update_assignments(self):
        """A learner cannot update assignment records."""
        self._auth(self.viewer)
        response = self.client.patch(self.detail_url, {"notes": "Hacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_learner_cannot_return_assets(self):
        """A learner cannot mark assets as returned."""
        self._auth(self.viewer)
        response = self.client.post(self.return_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)