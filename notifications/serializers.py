from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            "id",
            "recipient",
            "notification_type",
            "priority",
            "title",
            "message",
            "read_at",
            "is_read",
            "time_ago",
            "action_url",
            "related_entity_type",
            "related_entity_id",
            "is_email_sent",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "recipient",
            "created_at",
            "updated_at",
            "is_email_sent",
            "email_sent_at",
        )

    def get_time_ago(self, obj):
        """Return a human-readable relative time string."""
        from django.utils import timezone

        delta = timezone.now() - obj.created_at
        if delta.days > 365:
            years = delta.days // 365
            return f"{years}y ago"
        if delta.days > 30:
            months = delta.days // 30
            return f"{months}mo ago"
        if delta.days > 0:
            return f"{delta.days}d ago"
        if delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        if delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes}m ago"
        return "just now"


class NotificationMarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of notification IDs to mark as read. If omitted, marks all as read.",
    )


class NotificationPreferencesSerializer(serializers.Serializer):
    email_notifications = serializers.BooleanField(default=True)
    warranty_alerts = serializers.BooleanField(default=True)
    assignment_alerts = serializers.BooleanField(default=True)
    maintenance_alerts = serializers.BooleanField(default=True)
    overdue_alerts = serializers.BooleanField(default=True)