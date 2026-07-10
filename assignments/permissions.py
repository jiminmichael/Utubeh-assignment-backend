from rest_framework.permissions import SAFE_METHODS, BasePermission


class AssignmentPermission(BasePermission):
    """
    Viewer: read-only.
    IT Staff and Admin: create, update, return, and delete assignments.
    """

    message = "You do not have permission to perform this assignment action."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.is_admin_role or user.is_it_staff_role
