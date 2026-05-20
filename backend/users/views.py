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
from .models import FAB, Department, WaferLot
from .serializers import (
    FABSerializer,
    DepartmentSerializer,
    UserProfileSerializer,
    UserSerializer,
    WaferLotSerializer,
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


class WaferLotListView(generics.ListAPIView):
    """GET /api/users/wafer-lots/

    Scoped to the requester's own fab — they pick from a curated dropdown
    rather than typing a lot ID free-form. Superusers can override the scope
    via ``?fab_id=<uuid>``.

    Each row carries lock / history annotations so the submission UI can
    grey out locked lots and surface what experiments have already run.
    """
    serializer_class = WaferLotSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        from django.db.models import Prefetch
        from orders.models import Order
        qs = WaferLot.objects.select_related('fab').prefetch_related(
            Prefetch(
                'orders',
                # Only the columns the serializer needs — keeps the join
                # small even when a hot lot has dozens of historical orders.
                queryset=Order.objects.select_related('experiment').only(
                    'id', 'order_no', 'status', 'ended_at',
                    'experiment__id', 'experiment__name', 'lot_id',
                ).order_by('-created_at'),
            ),
        )
        user = self.request.user
        fab_id_override = self.request.query_params.get('fab_id')
        if user.role == 'superuser':
            if fab_id_override:
                qs = qs.filter(fab_id=fab_id_override)
            return qs
        # Non-superusers: locked to their own fab.
        if user.department and user.department.fab_id:
            return qs.filter(fab_id=user.department.fab_id)
        return qs.none()


class UserListView(generics.ListAPIView):
    """GET /api/users/ – list users in the caller's scope.

    Query params:
      * ``role=lab_member`` — narrow to a single role (used by the
        派工 / 啟動 dialogs whose assignee picker must NOT include
        lab_manager).
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.select_related('department').all()
        if user.is_authenticated and user.role == 'lab_manager':
            qs = qs.filter(department=user.department)
        elif user.is_authenticated and user.role == 'lab_member' and user.department_id:
            # Lab members need to see their own lab roster too — the 啟動
            # dialog (which they own now) pops up an assignee dropdown.
            qs = qs.filter(department=user.department)

        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)
        return qs
