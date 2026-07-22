"""
ShopAI API — Object-level permissions.
"""
from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """Allows access only to the object's owning user (checks `obj.user`)."""

    def has_object_permission(self, request, view, obj):
        return getattr(obj, 'user_id', None) == request.user.id


class ReadOnly(permissions.BasePermission):
    """Allows only safe (GET/HEAD/OPTIONS) methods."""

    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS
