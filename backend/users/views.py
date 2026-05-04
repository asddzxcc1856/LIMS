"""
users/views.py
API views for profile and lookup. New accounts are created via the admin
console (/api/admin/users/ + /api/admin/users/bulk-create/) — there is no
public registration endpoint.
"""
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from .models import FAB, Department
from .serializers import (
    FABSerializer,
    DepartmentSerializer,
    UserProfileSerializer,
    UserSerializer,
)

User = get_user_model()


class ProfileView(APIView):
    """GET /api/users/profile/ – return current user info."""
    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)


class FABListView(generics.ListAPIView):
    """GET /api/users/fabs/"""
    queryset = FAB.objects.all()
    serializer_class = FABSerializer
    permission_classes = [permissions.IsAuthenticated]


class DepartmentListView(generics.ListAPIView):
    """GET /api/users/departments/?fab_id=<uuid>"""
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Department.objects.select_related('fab').all()
        fab_id = self.request.query_params.get('fab_id')
        if fab_id:
            qs = qs.filter(fab_id=fab_id)
        return qs


class UserListView(generics.ListAPIView):
    """GET /api/users/ – list all users (lab_manager / superuser only)."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.select_related('department').all()
        if user.is_authenticated and user.role == 'lab_manager':
            qs = qs.filter(department=user.department)

        return qs
