from datetime import timedelta

from django.db.models import Count, Avg
from django.utils import timezone
from rest_framework import filters, generics
from rest_framework.response import Response
from rest_framework.views import APIView

from equipments.models import Equipment, EquipmentType
from orders.models import Order, OrderStage
from scheduling.models import EquipmentBooking
from users.models import User

from .models import ActivityLog
from .permissions import IsSystemSuperuser
from .serializers import ActivityLogSerializer


def _counts_by(queryset, field):
    """Return ``{value: count}`` for the given field."""
    return {row[field]: row['n'] for row in queryset.values(field).annotate(n=Count('id'))}


class DashboardStatsView(APIView):
    """Aggregate snapshot for the superuser dashboard."""

    permission_classes = (IsSystemSuperuser,)

    def get(self, request):
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        order_status = _counts_by(Order.objects.all(), 'status')
        stage_status = _counts_by(OrderStage.objects.all(), 'status')
        equipment_status = _counts_by(Equipment.objects.all(), 'status')
        user_role = _counts_by(User.objects.all(), 'role')

        recent_logs = ActivityLog.objects.filter(timestamp__gte=last_24h)
        recent_log_actions = _counts_by(recent_logs, 'action_type')
        avg_duration = recent_logs.aggregate(avg=Avg('duration_ms'))['avg'] or 0

        active_bookings = EquipmentBooking.objects.filter(
            started_at__lte=now, ended_at__gte=now
        ).count()

        return Response({
            'generated_at': now,
            'orders': {
                'total': Order.objects.count(),
                'by_status': order_status,
                'created_last_7d': Order.objects.filter(created_at__gte=last_7d).count(),
            },
            'order_stages': {
                'total': OrderStage.objects.count(),
                'by_status': stage_status,
            },
            'equipment': {
                'total': Equipment.objects.count(),
                'by_status': equipment_status,
                'types': EquipmentType.objects.count(),
                'active_bookings_now': active_bookings,
            },
            'users': {
                'total': User.objects.count(),
                'by_role': user_role,
                'active': User.objects.filter(status='active').count(),
            },
            'activity': {
                'total_logs': ActivityLog.objects.count(),
                'last_24h_total': recent_logs.count(),
                'last_24h_by_action': recent_log_actions,
                'avg_duration_ms_24h': round(float(avg_duration), 2),
            },
        })


class ActivityLogListView(generics.ListAPIView):
    """Paginated activity log feed with filtering for the audit page."""

    permission_classes = (IsSystemSuperuser,)
    serializer_class = ActivityLogSerializer
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ('timestamp', 'duration_ms', 'status_code')
    ordering = ('-timestamp',)

    def get_queryset(self):
        params = self.request.query_params
        qs = ActivityLog.objects.select_related('user').all()

        if user_id := params.get('user'):
            qs = qs.filter(user_id=user_id)
        if username := params.get('username'):
            qs = qs.filter(user__username__icontains=username)
        if action := params.get('action_type'):
            qs = qs.filter(action_type=action)
        if method := params.get('method'):
            qs = qs.filter(http_method=method.upper())
        if status_code := params.get('status_code'):
            qs = qs.filter(status_code=status_code)
        if path := params.get('path'):
            qs = qs.filter(path__icontains=path)
        if since := params.get('since'):
            qs = qs.filter(timestamp__gte=since)
        if until := params.get('until'):
            qs = qs.filter(timestamp__lte=until)

        return qs
