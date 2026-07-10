import re

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


@deconstructible
class AssetTagValidator:
    """Validate asset tag format (e.g., AST-2024-00001)."""

    message = _("Enter a valid asset tag in format AST-YYYY-NNNNN.")
    code = "invalid_asset_tag"
    pattern = re.compile(r"^AST-\d{4}-\d{5}$")

    def __call__(self, value):
        if not self.pattern.match(value):
            raise ValidationError(self.message, code=self.code)


@deconstructible
class SerialNumberValidator:
    """Validate serial number format (alphanumeric, hyphens, underscores allowed)."""

    message = _("Enter a valid serial number (alphanumeric, hyphens, underscores).")
    code = "invalid_serial_number"
    pattern = re.compile(r"^[A-Za-z0-9_-]+$")

    def __call__(self, value):
        if value and not self.pattern.match(value):
            raise ValidationError(self.message, code=self.code)


@deconstructible
class FileValidator:
    """
    Validates file size and content type.
    Usage:
    validators=[FileValidator(max_size=1024*1024, content_types=('image/jpeg',))]
    """

    def __init__(self, max_size=None, content_types=None):
        self.max_size = max_size
        self.content_types = content_types

    def __call__(self, value):
        if self.max_size and value.size > self.max_size:
            raise ValidationError(
                _("File size must not exceed %(max_size)s bytes."),
                params={"max_size": self.max_size},
            )

        if self.content_types and value.content_type not in self.content_types:
            raise ValidationError(
                _("Invalid file type: %(content_type)s."),
                params={"content_type": value.content_type},
            )


def validate_positive_cost(value):
    """Validate that cost is a positive number."""
    if value is not None and value < 0:
        raise ValidationError(_("Cost must be a positive value."))


def validate_future_date(value):
    """Validate that a date is not in the past (can be used for scheduled dates)."""
    from django.utils import timezone

    if value and value < timezone.now():
        raise ValidationError(_("Date must be in the future."))


def validate_phone_number(value):
    """Validate phone number format."""
    if value:
        cleaned = re.sub(r"[\s\-\(\)\+\.]", "", value)
        if not cleaned.isdigit() or len(cleaned) < 7:
            raise ValidationError(_("Enter a valid phone number."))