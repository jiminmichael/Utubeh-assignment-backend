from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminRole
from .models import Notification
from .serializers import (
    NotificationMarkReadSerializer,
    NotificationSerializer,
)


class NotificationListView(generics.ListAPIView):
    """
    GET /api/notifications/
    Returns notifications for the authenticated user, ordered by newest first.
    Supports ?unread=true to filter only unread notifications.
    Supports ?type=assignment|maintenance|warranty|overdue|system to filter by type.
    Supports ?limit=N to limit results (default: 50).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        queryset = Notification.objects.filter(recipient=self.request.user)

        # Filter by unread
        if self.request.query_params.get("unread", "").lower() == "true":
            queryset = queryset.filter(read_at__isnull=True)

        # Filter by notification type
        notif_type = self.request.query_params.get("type", "")
        if notif_type:
            queryset = queryset.filter(notification_type=notif_type)

        # Limit results
        try:
            limit = int(self.request.query_params.get("limit", 50))
            limit = min(limit, 200)  # Cap at 200
        except (ValueError, TypeError):
            limit = 50

        return queryset.order_by("-created_at")[:limit]


class NotificationDetailView(APIView):
    """
    GET /api/notifications/<id>/
    Returns a single notification.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        notification = generics.get_object_or_404(
            Notification, pk=pk, recipient=request.user
        )
        serializer = NotificationSerializer(notification, context={"request": request})
        return Response(serializer.data)


class NotificationMarkReadView(APIView):
    """
    POST /api/notifications/mark-read/
    Marks specific notifications or all notifications as read.

    Request body (optional):
    { "ids": [1, 2, 3] } — marks specific notifications
    { } — marks all unread notifications as read
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = NotificationMarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data.get("ids")

        if ids:
            count = Notification.objects.filter(
                id__in=ids,
                recipient=request.user,
                read_at__isnull=True,
            ).update(read_at=timezone.now())
        else:
            count = Notification.mark_all_as_read(request.user)

        return Response(
            {"marked_read": count, "detail": f"{count} notification(s) marked as read."},
            status=status.HTTP_200_OK,
        )


class NotificationMarkUnreadView(APIView):
    """
    POST /api/notifications/<id>/mark-unread/
    Marks a specific notification as unread.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = generics.get_object_or_404(
            Notification, pk=pk, recipient=request.user
        )
        notification.mark_as_unread()
        serializer = NotificationSerializer(notification, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationUnreadCountView(APIView):
    """
    GET /api/notifications/unread-count/
    Returns the count of unread notifications for the authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            recipient=request.user,
            read_at__isnull=True,
        ).count()
        return Response({"unread_count": count})


class NotificationClearAllView(APIView):
    """
    DELETE /api/notifications/clear-all/
    Deletes all notifications for the authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request):
        count, _ = Notification.objects.filter(recipient=request.user).delete()
        return Response(
            {"deleted": count, "detail": f"{count} notification(s) deleted."},
            status=status.HTTP_200_OK,
        )


class NotificationGenerateView(APIView):
    """
    POST /api/notifications/generate/
    Manually triggers notification generation for all alert types.
    Useful for testing or on-demand generation.
    """

    permission_classes = [IsAdminRole]

    def post(self, request):
        from .services import NotificationGenerator

        result = NotificationGenerator.run_all_checks()
        total = sum(result.values())
        return Response(
            {
                "generated": result,
                "total": total,
                "detail": f"Generated {total} notification(s).",
            },
            status=status.HTTP_200_OK,
        )