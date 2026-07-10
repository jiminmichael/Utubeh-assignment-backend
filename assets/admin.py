from django.contrib import admin

from .models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("asset_tag", "name", "category", "status", "purchase_date")
    list_filter = ("status", "category")
    search_fields = ("asset_tag", "name", "serial_number")
