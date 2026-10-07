from rest_framework.permissions import BasePermission


def is_app_admin(user):
    """Loyiha adminimi? (role='admin' yoki Django superuser)"""
    return bool(user and user.is_authenticated and (user.role == 'admin' or user.is_superuser))


class IsAppAdmin(BasePermission):
    message = "Bu amal faqat admin uchun."

    def has_permission(self, request, view):
        return is_app_admin(request.user)
