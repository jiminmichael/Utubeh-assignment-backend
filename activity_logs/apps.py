from django.apps import AppConfig


class ActivityLogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "activity_logs"

    def ready(self):
        import activity_logs.signals  # noqa
