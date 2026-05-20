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


def _is_manager_or_superuser(user):
    return user.role in ('lab_manager', 'superuser')


def _equipment_qs_for_user(user):
    """Equipment queryset scoped to the user. lab_manager sees only
    their lab's machines so charts reflect *their* lab,not全廠."""
    from django.db.models import Q
    qs = Equipment.objects.all()
    if user.role == 'superuser':
        return qs
    if user.role == 'lab_manager' and user.department_id:
        dept = user.department
        return qs.filter(
            Q(department_id=user.department_id)
            | Q(department__fab_id=dept.fab_id, department__name=dept.name)
        )
    return qs.none()


def _order_qs_for_user(user):
    """Same idea for orders — manager only sees their lab's orders."""
    from django.db.models import Q
    qs = Order.objects.all()
    if user.role == 'superuser':
        return qs
    if user.role == 'lab_manager' and user.department_id:
        dept = user.department
        return qs.filter(
            Q(department_id=user.department_id)
            | Q(department__fab_id=dept.fab_id, department__name=dept.name)
        )
    return qs.none()


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

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not _is_manager_or_superuser(request.user):
            return Response(
                {'detail': 'Restricted to lab supervisors and superusers.'},
                status=403,
            )
        days = _clamp(request.query_params.get('days'), default=7, lo=1, hi=60)
        eq_qs = _equipment_qs_for_user(request.user)
        eq_count = eq_qs.count()
        eq_ids = list(eq_qs.values_list('id', flat=True))
        now = timezone.now()
        results = []

        for label, day_start, day_end in _day_buckets(now, days):
            # Only fetch bookings that overlap this day AND target the
            # caller's lab; index on (started_at, ended_at) keeps it
            # tight even with 10k rows.
            bookings = EquipmentBooking.objects.filter(
                equipment_id__in=eq_ids,
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

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not _is_manager_or_superuser(request.user):
            return Response(
                {'detail': 'Restricted to lab supervisors and superusers.'},
                status=403,
            )
        days = _clamp(request.query_params.get('days'), default=30, lo=1, hi=90)
        now = timezone.now()
        orders_qs = _order_qs_for_user(request.user)
        results = []

        for label, day_start, day_end in _day_buckets(now, days):
            created = orders_qs.filter(
                created_at__gte=day_start, created_at__lt=day_end,
            ).count()
            done = orders_qs.filter(
                ended_at__gte=day_start, ended_at__lt=day_end, status=Order.Status.DONE,
            ).count()
            rejected = orders_qs.filter(
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

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not _is_manager_or_superuser(request.user):
            return Response(
                {'detail': 'Restricted to lab supervisors and superusers.'},
                status=403,
            )
        days = _clamp(request.query_params.get('days'), default=30, lo=1, hi=90)
        limit = _clamp(request.query_params.get('limit'), default=10, lo=1, hi=50)
        since = timezone.now() - timedelta(days=days)
        user = request.user

        # Lab-scope filter: manager sees only operators of their own
        # dept; superuser sees everyone.
        from django.db.models import Q
        if user.role == 'lab_manager' and user.department_id:
            dept = user.department
            dept_filter = Q(department_id=user.department_id) | Q(
                department__fab_id=dept.fab_id, department__name=dept.name,
            )
        else:
            dept_filter = Q()

        event_rows = (
            StageEvent.objects
            .filter(occurred_at__gte=since, operator__isnull=False)
            .filter(**({'operator__department_id': user.department_id}
                       if user.role == 'lab_manager' and user.department_id else {}))
            .values('operator_id', 'operator__username')
            .annotate(events=Count('id'))
        )
        approval_rows = (
            Approval.objects
            .filter(decided_at__gte=since, actor__isnull=False)
            .filter(**({'actor__department_id': user.department_id}
                       if user.role == 'lab_manager' and user.department_id else {}))
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


class MyStatsView(APIView):
    """GET /api/monitoring/my-stats/

    Per-role workload snapshot for the home dashboard. Different roles
    care about different counters:

    * **lab_manager** — how many stages of *my* lab are waiting for me
      to sign off (or have been signed off and are now moving through
      lab-member hands). Also exposes today's reject count.
    * **lab_member** — per-phase Sample counts the member should pay
      attention to (待派工 / 待設參數 / 待指派 / 待上貨 / 進行中 /
      assigned to me).
    * **regular_employee / superuser** — the requester gets their own
      order status breakdown; superuser falls back to the full dashboard.

    Returns ``{'role': ..., 'cards': [{label, value, color, hint}, …]}``
    so the frontend can drive a single render loop and we can add new
    cards later without changing the contract.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user
        role = user.role
        cards = []

        if role == 'lab_manager':
            cards = self._manager_cards(user)
        elif role == 'lab_member':
            cards = self._member_cards(user)
        elif role == 'regular_employee':
            cards = self._employee_cards(user)
        else:
            # Superusers get the same employee-style cards so the home
            # widget always renders something useful — the full dashboard
            # is one click away.
            cards = self._superuser_cards()

        return Response({'role': role, 'cards': cards})

    # ── per-role builders ───────────────────────────────────────

    def _manager_cards(self, user):
        from orders.models import OrderStage, Order
        dept_id = user.department_id
        from django.db.models import Q
        dept = user.department
        same_lab = (
            Q(department_id=dept_id)
            | Q(department__fab_id=dept.fab_id, department__name=dept.name)
        ) if dept_id else Q(pk=None)

        waiting_signoff = OrderStage.objects.filter(
            same_lab, status=OrderStage.Status.WAITING,
        ).count()
        approved = OrderStage.objects.filter(
            same_lab, status=OrderStage.Status.APPROVED,
        ).count()
        in_progress = OrderStage.objects.filter(
            same_lab, status=OrderStage.Status.IN_PROGRESS,
        ).count()
        rejected_today = OrderStage.objects.filter(
            same_lab, status=OrderStage.Status.REJECTED,
        ).count()

        return [
            {
                'key': 'waiting_signoff',
                'label': '待簽核',
                'value': waiting_signoff,
                'color': '#fa8c16',
                'hint': '此實驗室目前等待主管簽核的訂單階段數',
            },
            {
                'key': 'approved_dispatch',
                'label': '已簽核 進行中分貨/派工',
                'value': approved,
                'color': '#1890ff',
                'hint': '簽核完成,實驗室人員正在分貨 / 派工 / 設定參數 / 指派的階段數',
            },
            {
                'key': 'in_progress',
                'label': '上機進行中',
                'value': in_progress,
                'color': '#52c41a',
                'hint': '至少有一個子 LOT 已上貨並在機台執行',
            },
            {
                'key': 'rejected_total',
                'label': '已駁回',
                'value': rejected_today,
                'color': '#f5222d',
                'hint': '本實驗室目前累計駁回的階段數',
            },
        ]

    def _member_cards(self, user):
        from orders.models import OrderStage, Sample
        from django.db.models import Q
        dept_id = user.department_id
        dept = user.department
        same_lab_stage = (
            Q(department_id=dept_id)
            | Q(department__fab_id=dept.fab_id, department__name=dept.name)
        ) if dept_id else Q(pk=None)
        same_lab_sample = (
            Q(order__department_id=dept_id)
            | Q(order__department__fab_id=dept.fab_id,
                order__department__name=dept.name)
        ) if dept_id else Q(pk=None)

        to_receive = OrderStage.objects.filter(
            same_lab_stage,
            status=OrderStage.Status.WAITING,
            received_at__isnull=True,
        ).count()
        to_split = OrderStage.objects.filter(
            same_lab_stage,
            status=OrderStage.Status.APPROVED,
        ).annotate(sample_count=Count('order__samples')).filter(
            sample_count=0,
        ).count()
        # Sample-level counters
        to_dispatch = Sample.objects.filter(same_lab_sample, status=Sample.Status.WAITING).count()
        to_params = Sample.objects.filter(same_lab_sample, status=Sample.Status.DISPATCHED).count()
        to_assign = Sample.objects.filter(same_lab_sample, status=Sample.Status.PARAMS_SET).count()
        my_ready = Sample.objects.filter(assignee=user, status=Sample.Status.READY).count()
        my_running = Sample.objects.filter(assignee=user, status=Sample.Status.RUNNING).count()
        my_done = Sample.objects.filter(assignee=user, status=Sample.Status.DONE).count()

        return [
            {'key': 'to_receive', 'label': '待接件', 'value': to_receive, 'color': '#fa8c16',
             'hint': '廠區已送來、實驗室尚未點收的訂單'},
            {'key': 'to_split', 'label': '待分貨', 'value': to_split, 'color': '#722ed1',
             'hint': '主管已簽核但尚未進行分貨的訂單'},
            {'key': 'to_dispatch', 'label': '待派工 (子LOT)', 'value': to_dispatch, 'color': '#1890ff',
             'hint': '已分貨但尚未指派機台 + Recipe + 排程的子 LOT'},
            {'key': 'to_params', 'label': '待設定參數 (子LOT)', 'value': to_params, 'color': '#13c2c2',
             'hint': '已派工但尚未在 Recipe 範圍內設定參數的子 LOT'},
            {'key': 'to_assign', 'label': '待指派員工 (子LOT)', 'value': to_assign, 'color': '#52c41a',
             'hint': '已設參數但尚未指派執行員工的子 LOT'},
            {'key': 'my_ready', 'label': '我待上貨', 'value': my_ready, 'color': '#722ed1',
             'hint': '已指派給我、等我上貨開始實驗的子 LOT'},
            {'key': 'my_running', 'label': '我進行中', 'value': my_running, 'color': '#fa541c',
             'hint': '我正在機台上執行中的子 LOT'},
            {'key': 'my_done', 'label': '我已完成', 'value': my_done, 'color': '#8c8c8c',
             'hint': '我累計完成的子 LOT 數'},
        ]

    def _employee_cards(self, user):
        from orders.models import Order
        base = Order.objects.filter(user=user)
        return [
            {'key': 'waiting', 'label': '送樣中 (待主管簽核)', 'value': base.filter(status='waiting').count(),
             'color': '#fa8c16', 'hint': '送出後等實驗室主管簽核的訂單數'},
            {'key': 'in_progress', 'label': '進行中', 'value': base.filter(status='in_progress').count(),
             'color': '#1890ff', 'hint': '已派工、實驗正在進行的訂單數'},
            {'key': 'done', 'label': '已完成', 'value': base.filter(status='done').count(),
             'color': '#52c41a', 'hint': '已完成可取件的訂單數'},
            {'key': 'rejected', 'label': '被駁回', 'value': base.filter(status='rejected').count(),
             'color': '#f5222d', 'hint': '被實驗室主管駁回的訂單數'},
        ]

    def _superuser_cards(self):
        from orders.models import Order, OrderStage, Sample
        return [
            {'key': 'orders', 'label': '訂單總數', 'value': Order.objects.count(),
             'color': '#1890ff', 'hint': '整個系統累計訂單數'},
            {'key': 'stages_waiting', 'label': '待簽核', 'value':
                OrderStage.objects.filter(status='waiting').count(),
             'color': '#fa8c16', 'hint': '全系統等待主管簽核的階段數'},
            {'key': 'samples_running', 'label': 'Sample 進行中', 'value':
                Sample.objects.filter(status='running').count(),
             'color': '#52c41a', 'hint': '全系統正在機台上執行的子 LOT 數'},
        ]


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
