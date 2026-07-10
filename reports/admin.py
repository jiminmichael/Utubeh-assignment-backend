from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("name", "requested_by", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "requested_by__username", "requested_by__email")
