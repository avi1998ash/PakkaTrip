from rest_framework.permissions import BasePermission

from accounts.models import User


class IsAdminRole(BasePermission):
    message = "Admin access only."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.ADMIN)


class IsOperatorRole(BasePermission):
    """Operator staff. Sets request.operator — every operator query filters by it."""
    message = "Operator access only."

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and u.role == User.Role.OPERATOR):
            return False
        membership = getattr(u, "operator_membership", None)
        if not membership:
            return False
        request.operator = membership.operator
        return True
