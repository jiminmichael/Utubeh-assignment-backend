from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import ActivityLog
from .utils import get_client_ip, get_request


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log user login events."""
    ActivityLog.log(
        actor=user,
        action=ActivityLog.ActivityAction.LOGIN,
        entity_type="user",
        entity_id=user.pk,
        entity_repr=str(user),
        message=f"User {user.username} logged in.",
        ip_address=get_client_ip(request),
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log user logout events."""
    if user:
        ActivityLog.log(
            actor=user,
            action=ActivityLog.ActivityAction.LOGOUT,
            entity_type="user",
            entity_id=user.pk,
            entity_repr=str(user),
            message=f"User {user.username} logged out.",
            ip_address=get_client_ip(request),
        )