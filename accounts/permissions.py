from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    message = "Admin role is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin_role)


class IsITStaffOrAdmin(BasePermission):
    message = "IT Staff or Admin role is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_admin_role or user.is_it_staff_role))


class IsViewerOrAbove(BasePermission):
    message = "Authenticated viewer access is required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
