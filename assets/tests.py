"""
Comprehensive tests for the Assets module.

Tests cover:
- Model: creation, validation, QR code/thumbnail generation, status transitions
- API: list/create, detail, filtering, searching, ordering, pagination
- Permissions: role-based access control for all endpoints (Admin, IT Staff, Viewer)
- Serializers: validation rules for unique fields and date logic
- Bulk Import: CSV validation, transactional integrity, error reporting
- QR Code and Export endpoints
"""
import io
from unittest.mock import patch
from django.urls import reverse

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import Asset

User = get_user_model()


# =============================================================================
#  HELPER FACTORIES
# =============================================================================

def create_user(role, username, email):
    return User.objects.create_user(username=username, email=email, password="password123", role=role)

def create_asset(**kwargs):
    defaults = {
        "name": "Test Asset",
        "category": "laptop",
        "status": "available",
        "condition": "good",
    }
    # asset_tag is auto-generated, so we don't set it unless testing uniqueness
    if "asset_tag" not in kwargs:
        defaults.pop("asset_tag", None)

    defaults.update(kwargs)
    return Asset.objects.create(**defaults)


# =============================================================================
#  MODEL TESTS
# =============================================================================

class AssetModelTests(TestCase):
    def test_asset_creation_and_auto_tag(self):
        asset = Asset.objects.create(name="New Laptop", category="laptop")
        self.assertIsNotNone(asset.asset_tag)
        self.assertTrue(asset.asset_tag.startswith("AST-"))

    def test_soft_delete_and_restore(self):
        asset = create_asset(name="Deletable Asset")
        asset_id = asset.id
        asset.soft_delete()

        self.assertTrue(asset.is_deleted)
        self.assertIsNotNone(asset.deleted_at)
        self.assertEqual(Asset.objects.filter(id=asset_id).count(), 0)
        self.assertEqual(Asset.all_objects.filter(id=asset_id).count(), 1)

        asset.restore()
        self.assertFalse(asset.is_deleted)
        self.assertIsNone(asset.deleted_at)
        self.assertEqual(Asset.objects.filter(id=asset_id).count(), 1)

    @patch('assets.models.qrcode.make')
    def test_qr_code_generation(self, mock_qrcode_make):
        asset = create_asset(name="QR Asset")
        asset.generate_qr_code(save=True)
        mock_qrcode_make.assert_called_once()
        self.assertTrue(asset.qr_code_image.name.startswith("qrcodes/"))

    def test_thumbnail_generation(self):
        # Create a dummy image file
        image = io.BytesIO()
        from PIL import Image
        Image.new('RGB', (100, 100)).save(image, 'jpeg')
        image.seek(0)
        
        asset = create_asset(name="Thumbnail Asset")
        asset.image = SimpleUploadedFile("test.jpg", image.read(), content_type="image/jpeg")
        asset.save()

        asset.refresh_from_db()
        self.assertTrue(asset.thumbnail.name.startswith("assets/thumbnails/"))

    def test_status_transition(self):
        asset = create_asset(name="Status Asset")
        self.assertEqual(asset.status, "available")
        
        asset.mark_as("assigned")
        self.assertEqual(asset.status, "assigned")

        asset.mark_as("maintenance")
        self.assertEqual(asset.status, "maintenance")

        # Test invalid transition
        result = asset.mark_as("invalid_status")
        self.assertFalse(result)
        self.assertEqual(asset.status, "maintenance")


# =============================================================================
#  API TESTS
# =============================================================================

class AssetAPITestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = create_user(User.Role.ADMIN, "admin", "admin@test.com")
        self.it_staff = create_user(User.Role.IT_STAFF, "itstaff", "it@test.com")
        self.viewer = create_user(User.Role.VIEWER, "viewer", "viewer@test.com")

        self.asset = create_asset(name="API Test Asset", serial_number="API-SN-001", asset_tag="AST-2026-00001")
        self.list_create_url = reverse("assets:asset-list-create")
        self.detail_url = reverse("assets:asset-detail", kwargs={"pk": self.asset.pk})

    def _auth(self, user):
        self.client.force_authenticate(user=user)


class AssetPermissionTests(AssetAPITestCase):
    def test_unauthenticated_access(self):
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_viewer_permissions(self):
        self._auth(self.viewer)
        # Can read
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Cannot write
        response = self.client.post(self.list_create_url, {"name": "Viewer Asset", "category": "other"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.patch(self.detail_url, {"name": "Viewer Edit"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_it_staff_permissions(self):
        self._auth(self.it_staff)
        # Can read
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Can create and update
        response = self.client.post(self.list_create_url, {"name": "IT Asset", "category": "other"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.patch(self.detail_url, {"name": "IT Edit"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Cannot delete
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_permissions(self):
        self._auth(self.admin)
        # Can read, create, update, and delete
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(self.list_create_url, {"name": "Admin Asset", "category": "other"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.patch(self.detail_url, {"name": "Admin Edit"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class AssetCRUDTests(AssetAPITestCase):
    def test_create_asset(self):
        payload = {
            "name": "New Server",
            "category": "server",
            "serial_number": "NEW-SN-123",
            "purchase_cost": "2500.00",
            "purchase_date": "2026-01-15",
        }
        self._auth(self.admin)
        response = self.client.post(self.list_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "New Server")
        self.assertIsNotNone(response.data["asset_tag"])

    def test_create_asset_uniqueness_validation(self):
        # Test unique serial number
        payload = {"name": "Duplicate SN", "category": "other", "serial_number": "API-SN-001"}
        self._auth(self.admin)
        response = self.client.post(self.list_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("serial_number", response.data)

        # Test unique asset tag
        payload = {"name": "Duplicate Tag", "category": "other", "asset_tag": "AST-2026-00001"}
        self._auth(self.admin)
        response = self.client.post(self.list_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("asset_tag", response.data)

    def test_create_asset_date_validation(self):
        # Purchase date in future
        self._auth(self.admin)
        future_date = (timezone.now() + timezone.timedelta(days=10)).strftime('%Y-%m-%d')
        payload = {"name": "Future Asset", "category": "other", "purchase_date": future_date}
        response = self.client.post(self.list_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("purchase_date", response.data)

        # Warranty before purchase
        payload = {
            "name": "Warranty Asset",
            "category": "other",
            "purchase_date": "2026-02-01",
            "warranty_expiry": "2026-01-01",
        }
        self._auth(self.admin)
        response = self.client.post(self.list_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("warranty_expiry", response.data)

    def test_list_assets(self):
        create_asset(name="Asset 2")
        self._auth(self.viewer)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertGreaterEqual(response.data["count"], 2)

    def test_retrieve_asset(self):
        self._auth(self.viewer)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.asset.id)
        self.assertEqual(response.data["name"], self.asset.name)

    def test_update_asset(self):
        self._auth(self.it_staff)
        payload = {"location": "Room 101", "condition": "fair"}
        response = self.client.patch(self.detail_url, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.location, "Room 101")
        self.assertEqual(self.asset.condition, "fair")

    def test_soft_delete_asset(self):
        self._auth(self.admin)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.asset.refresh_from_db()
        self.assertTrue(self.asset.is_deleted)
        
        # Verify it's not in the main list anymore
        self._auth(self.viewer)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.data["count"], 0)


class AssetExtraAPITests(AssetAPITestCase):
    def setUp(self):
        super().setUp()
        self._auth(self.admin)

    def test_get_qr_code(self):
        url = reverse("assets:asset-qr-code", kwargs={"pk": self.asset.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'image/png')

    def test_get_qr_code_generates_if_missing(self):
        asset_no_qr = create_asset(name="No QR Yet")
        self.assertFalse(asset_no_qr.qr_code_image)
        
        url = reverse("assets:asset-qr-code", kwargs={"pk": asset_no_qr.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        asset_no_qr.refresh_from_db()
        self.assertTrue(asset_no_qr.qr_code_image)

    def test_export_assets(self):
        url = reverse("assets:asset-export")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="asset_export.csv"'))
        
        content = response.content.decode('utf-8')
        self.assertIn("id,name,asset_tag", content) # Check for header
        self.assertIn(self.asset.name, content) # Check for data

    def test_bulk_import_assets(self):
        url = reverse("assets:asset-bulk-import")
        csv_content = (
            "name,category,serial_number,purchase_cost\n"
            "Bulk Asset 1,laptop,BULK-SN-001,1200.50\n"
            "Bulk Asset 2,monitor,BULK-SN-002,350.00\n"
        )
        csv_file = SimpleUploadedFile("import.csv", csv_content.encode('utf-8'), content_type="text/csv")
        
        response = self.client.post(url, {"file": csv_file}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["detail"], "Successfully imported 2 assets.")
        self.assertEqual(Asset.objects.filter(serial_number__startswith="BULK-").count(), 2)

    def test_bulk_import_transaction_rollback(self):
        # One valid row, one row with a duplicate serial number
        csv_content = (
            "name,category,serial_number\n"
            "Bulk Asset 3,laptop,BULK-SN-003\n"
            f"Bulk Asset 4,monitor,{self.asset.serial_number}\n"
        )
        csv_file = SimpleUploadedFile("import_fail.csv", csv_content.encode('utf-8'), content_type="text/csv")
        
        url = reverse("assets:asset-bulk-import")
        response = self.client.post(url, {"file": csv_file}, format="multipart")
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", response.data)
        self.assertIn("rows", response.data["errors"])
        # Verify that the valid row was not created due to the transaction rollback
        self.assertFalse(Asset.objects.filter(serial_number="BULK-SN-003").exists())