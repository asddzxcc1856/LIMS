from rest_framework.permissions import BasePermission


class IsSystemSuperuser(BasePermission):
    """Allow access only to authenticated users whose role is ``superuser``.

    Distinct from Django's ``is_superuser`` flag — we authorize on the custom
    ``User.role`` field so business roles stay decoupled from Django auth flags.
    """

    message = 'Superuser role required.'

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.role == 'superuser' or user.is_superuser
