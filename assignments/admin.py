from django.contrib import admin

from .models import Assignment


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("asset", "assigned_to", "assigned_by", "status", "department", "assigned_at", "due_at", "returned_at")
    list_filter = ("status", "department", "assigned_at", "returned_at")
    search_fields = (
        "asset__asset_tag",
        "asset__serial_number",
        "asset__manufacturer",
        "asset__model",
        "assigned_to__username",
        "assigned_to__email",
        "department",
    )
