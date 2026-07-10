from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "read_at", "created_at")
    list_filter = ("read_at", "created_at")
    search_fields = ("title", "message", "recipient__username", "recipient__email")
