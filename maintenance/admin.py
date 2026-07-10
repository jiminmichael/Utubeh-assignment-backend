from django.contrib import admin

from .models import MaintenanceRecord


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ("title", "asset", "status", "scheduled_for", "completed_at")
    list_filter = ("status", "scheduled_for")
    search_fields = ("title", "asset__asset_tag", "asset__name")
