from django.urls import path

from .views import (
    NotificationClearAllView,
    NotificationDetailView,
    NotificationGenerateView,
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkUnreadView,
    NotificationUnreadCountView,
)

app_name = "notifications"

urlpatterns = [
    # List all notifications for the authenticated user
    path("", NotificationListView.as_view(), name="notification-list"),
    # Get a single notification
    path("<int:pk>/", NotificationDetailView.as_view(), name="notification-detail"),
    # Mark a single notification as unread
    path("<int:pk>/mark-unread/", NotificationMarkUnreadView.as_view(), name="notification-mark-unread"),
    # Mark notifications as read (specific or all)
    path("mark-read/", NotificationMarkReadView.as_view(), name="notification-mark-read"),
    # Get unread count
    path("unread-count/", NotificationUnreadCountView.as_view(), name="notification-unread-count"),
    # Clear all notifications for the user
    path("clear-all/", NotificationClearAllView.as_view(), name="notification-clear-all"),
    # Manually trigger notification generation
    path("generate/", NotificationGenerateView.as_view(), name="notification-generate"),
]