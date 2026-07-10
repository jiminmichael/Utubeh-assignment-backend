from rest_framework.permissions import SAFE_METHODS, BasePermission


class AssetPermission(BasePermission):
    """
    Viewer: read-only.
    IT Staff: read, create, and update.
    Admin: full access including delete.
    """

    message = "You do not have permission to perform this asset action."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        if request.method == "DELETE":
            return user.is_admin_role
        return user.is_admin_role or user.is_it_staff_role
