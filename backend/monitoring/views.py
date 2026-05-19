from datetime import timedelta

from django.db.models import Count, Avg
from django.utils import timezone
from rest_framework import filters, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from equipments.models import Equipment, EquipmentType
from orders.models import Approval, Order, OrderStage
from scheduling.models import EquipmentBooking, StageEvent
from users.models import User

from .models import ActivityLog, Notification
from .permissions import IsSystemSuperuser
from .serializers import ActivityLogSerializer, NotificationSerializer


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

        # Rolling 24h utilization: sum of overlapping booking seconds across
        # every equipment unit divided by the total available equipment-time
        # in that window. More meaningful than the "occupied right now"
        # snapshot the KPI card used to show.
        equipment_count = Equipment.objects.count()
        utilization_24h = 0.0
        if equipment_count:
            busy_sec = 0.0
            for b_start, b_end in EquipmentBooking.objects.filter(
                started_at__lt=now, ended_at__gt=last_24h,
            ).values_list('started_at', 'ended_at'):
                overlap_start = max(b_start, last_24h)
                overlap_end = min(b_end, now)
                if overlap_start < overlap_end:
                    busy_sec += (overlap_end - overlap_start).total_seconds()
            utilization_24h = round(busy_sec / (equipment_count * 86400) * 100, 2)

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
                'utilization_24h': utilization_24h,
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


def _clamp(value, default, lo, hi):
    """Parse a query-string int safely and clamp it to a bounded range."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(n, hi))


def _day_buckets(end, days):
    """Yield ``(label, day_start_aware, day_end_aware)`` for the last *days* days
    ending (inclusive) at *end*'s date — used as a stable axis for the
    daily-aggregate chart endpoints."""
    end_date = timezone.localtime(end).date()
    for i in range(days - 1, -1, -1):
        d = end_date - timedelta(days=i)
        day_start_naive = timezone.datetime(d.year, d.month, d.day)
        day_start = timezone.make_aware(day_start_naive)
        yield d.isoformat(), day_start, day_start + timedelta(days=1)


class ChartEquipmentUtilizationView(APIView):
    """GET /api/monitoring/charts/equipment-utilization/?days=7

    Returns the *real* utilization% per day for the last N days:
    sum of overlapping booking seconds across every equipment unit,
    divided by ``equipment_count × 86400``. Replaces the original
    "occupied right now" snapshot in :class:`DashboardStatsView` which
    overstated short-bursting labs and understated dormant ones.
    """

    permission_classes = (IsSystemSuperuser,)

    def get(self, request):
        days = _clamp(request.query_params.get('days'), default=7, lo=1, hi=60)
        eq_count = Equipment.objects.count()
        now = timezone.now()
        results = []

        for label, day_start, day_end in _day_buckets(now, days):
            # Only fetch bookings that overlap this day; the index on
            # (started_at, ended_at) keeps this tight even with 10k rows.
            bookings = EquipmentBooking.objects.filter(
                started_at__lt=day_end, ended_at__gt=day_start,
            ).values_list('started_at', 'ended_at')

            busy_sec = 0.0
            for b_start, b_end in bookings:
                overlap_start = max(b_start, day_start)
                overlap_end = min(b_end, day_end)
                if overlap_start < overlap_end:
                    busy_sec += (overlap_end - overlap_start).total_seconds()

            total_sec = eq_count * 86400
            util = (busy_sec / total_sec * 100) if total_sec > 0 else 0.0
            results.append({
                'date': label,
                'utilization': round(util, 2),
                'busy_hours': round(busy_sec / 3600.0, 2),
            })

        return Response({
            'days': days,
            'equipment_count': eq_count,
            'series': results,
        })


class ChartOrderTrendView(APIView):
    """GET /api/monitoring/charts/order-trend/?days=30

    Daily order activity:
    * ``created`` — orders submitted on this day
    * ``done``    — orders that ended in DONE on this day
    * ``rejected``— orders that ended in REJECTED on this day
    """

    permission_classes = (IsSystemSuperuser,)

    def get(self, request):
        days = _clamp(request.query_params.get('days'), default=30, lo=1, hi=90)
        now = timezone.now()
        results = []

        for label, day_start, day_end in _day_buckets(now, days):
            created = Order.objects.filter(
                created_at__gte=day_start, created_at__lt=day_end,
            ).count()
            done = Order.objects.filter(
                ended_at__gte=day_start, ended_at__lt=day_end, status=Order.Status.DONE,
            ).count()
            rejected = Order.objects.filter(
                ended_at__gte=day_start, ended_at__lt=day_end, status=Order.Status.REJECTED,
            ).count()
            results.append({
                'date': label,
                'created': created,
                'done': done,
                'rejected': rejected,
            })

        return Response({'days': days, 'series': results})


class ChartOperatorActivityView(APIView):
    """GET /api/monitoring/charts/operator-activity/?days=30&limit=10

    Per-operator counts in the last N days:
    * ``events``    — StageEvent rows the operator authored
    * ``approvals`` — Approval rows the operator wrote (manager only)

    Combined and sorted by total descending so a manager's at-a-glance
    chart shows who's most active across both surfaces.
    """

    permission_classes = (IsSystemSuperuser,)

    def get(self, request):
        days = _clamp(request.query_params.get('days'), default=30, lo=1, hi=90)
        limit = _clamp(request.query_params.get('limit'), default=10, lo=1, hi=50)
        since = timezone.now() - timedelta(days=days)

        event_rows = (
            StageEvent.objects
            .filter(occurred_at__gte=since, operator__isnull=False)
            .values('operator_id', 'operator__username')
            .annotate(events=Count('id'))
        )
        approval_rows = (
            Approval.objects
            .filter(decided_at__gte=since, actor__isnull=False)
            .values('actor_id', 'actor__username')
            .annotate(approvals=Count('id'))
        )

        combined = {}
        for row in event_rows:
            combined[row['operator_id']] = {
                'user_id': str(row['operator_id']),
                'username': row['operator__username'],
                'events': row['events'],
                'approvals': 0,
            }
        for row in approval_rows:
            uid = row['actor_id']
            slot = combined.setdefault(uid, {
                'user_id': str(uid),
                'username': row['actor__username'],
                'events': 0,
                'approvals': 0,
            })
            slot['approvals'] = row['approvals']

        ranked = sorted(
            combined.values(),
            key=lambda r: r['events'] + r['approvals'],
            reverse=True,
        )[:limit]
        return Response({
            'days': days,
            'limit': limit,
            'series': ranked,
        })


class NotificationListView(generics.ListAPIView):
    """GET /api/monitoring/notifications/

    Returns the caller's own notifications, newest first. Optional filters:
    * ``unread_only=true`` — hide already-read rows
    * ``kind=equipment_alert`` — match one Notification.Kind
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        params = self.request.query_params
        if params.get('unread_only') in ('1', 'true', 'True'):
            qs = qs.filter(is_read=False)
        if kind := params.get('kind'):
            qs = qs.filter(kind=kind)
        return qs


class NotificationMarkReadView(APIView):
    """POST /api/monitoring/notifications/<id>/mark-read/ — flip is_read.

    Idempotent — already-read rows just return the current state.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request, pk):
        try:
            row = Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({'detail': 'Notification not found.'}, status=404)
        if not row.is_read:
            row.is_read = True
            row.read_at = timezone.now()
            row.save(update_fields=['is_read', 'read_at'])
        return Response(NotificationSerializer(row).data)


class NotificationMarkAllReadView(APIView):
    """POST /api/monitoring/notifications/mark-all-read/ — bulk flag flip."""

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        count = (
            Notification.objects
            .filter(recipient=request.user, is_read=False)
            .update(is_read=True, read_at=timezone.now())
        )
        return Response({'updated': count})


class NotificationSummaryView(APIView):
    """GET /api/monitoring/notifications/summary/ — header badge feed.

    Returns ``{'unread': N, 'critical_unread': N}`` so the SPA can
    light a red dot on the bell icon without round-tripping the whole
    list every page load.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        base = Notification.objects.filter(recipient=request.user, is_read=False)
        return Response({
            'unread': base.count(),
            'critical_unread': base.filter(level=Notification.Level.CRITICAL).count(),
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
