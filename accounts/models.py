from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import TimeStampedModel


class User(AbstractUser, TimeStampedModel):
    """Custom user model with role-based access control for asset management."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        IT_STAFF = "it_staff", "IT Staff"
        VIEWER = "viewer", "Viewer"

    email = models.EmailField(
        unique=True,
        help_text="Email address used for login and notifications",
    )
    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.VIEWER,
        db_index=True,
        help_text="User role for access control",
    )
    phone_number = models.CharField(
        max_length=32,
        blank=True,
        help_text="Contact phone number",
    )
    department = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text="Department the user belongs to",
    )
    job_title = models.CharField(
        max_length=120,
        blank=True,
        help_text="User's job title/position",
    )
    employee_id = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        null=True,
        help_text="Employee/Staff ID from HR system",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the user account is active",
    )

    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ["username"]
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["department"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_admin_role(self):
        """Check if user has admin role or is superuser."""
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_it_staff_role(self):
        """Check if user has IT staff role."""
        return self.role == self.Role.IT_STAFF

    @property
    def is_viewer_role(self):
        """Check if user has viewer role."""
        return self.role == self.Role.VIEWER

    @property
    def display_name(self):
        """Get the best display name for the user."""
        return self.get_full_name() or self.username

    def has_management_permission(self):
        """Check if user can manage assets (admin or IT staff)."""
        return self.is_admin_role or self.is_it_staff_role