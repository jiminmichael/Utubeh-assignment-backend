from rest_framework import serializers


class DashboardQuerySerializer(serializers.Serializer):
    warranty_days = serializers.IntegerField(min_value=1, max_value=365, default=30)
    trend_days = serializers.IntegerField(min_value=7, max_value=730, default=180)
    recent_limit = serializers.IntegerField(min_value=1, max_value=50, default=10)


class MonthQuerySerializer(serializers.Serializer):
    months = serializers.IntegerField(min_value=1, max_value=60, default=12)


class DaysQuerySerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=365, default=90)


class StatusQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["open", "in_progress", "completed", "cancelled", ""],
        default="",
        required=False,
    )