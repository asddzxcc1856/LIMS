from datetime import timedelta

from django.db.models import Avg, Count, ExpressionWrapper, F, Min, Q, fields
from django.utils import timezone
from rest_framework import filters, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from equipments.models import Equipment, EquipmentType
from orders.models import Approval, Order, OrderStage, Sample
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


class ChartOrderBusinessView(APIView):
    """GET /api/monitoring/charts/order-business/?days=30

    Lab-scoped business metrics on top of raw counts. Returns four blocks
    the 主管 report wants:

    * ``totals`` — order totals over the window (created / done / rejected /
      in-progress) plus the rejection rate %.
    * ``order_status`` — current order status distribution (snapshot).
    * ``stage_status`` — per OrderStage.Status counts (snapshot) so the
      manager sees how many stages are stuck where.
    * ``sample_status`` — per Sample.Status counts (snapshot) — same
      "where is everything stuck" view at sub-LOT granularity.
    * ``lead_times`` — mean hours from order ``created_at`` → ``ended_at``
      split by ended status (done vs rejected) and mean hours from
      stage ``created_at`` → first approval (sign-off latency).
    * ``by_equipment_type`` — per equipment type breakdown: in-progress
      stages and finished samples in the window, plus mean run hours.

    The shapes are deliberately list-of-objects so the SPA can render
    each as a table without bespoke transforms.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not _is_manager_or_superuser(request.user):
            return Response(
                {'detail': 'Restricted to lab supervisors and superusers.'},
                status=403,
            )
        days = _clamp(request.query_params.get('days'), default=30, lo=1, hi=180)
        since = timezone.now() - timedelta(days=days)
        orders_qs = _order_qs_for_user(request.user)
        eq_qs = _equipment_qs_for_user(request.user)

        # Stages + samples filtered to the same lab via order FK.
        stage_qs = OrderStage.objects.filter(order__in=orders_qs)
        sample_qs = Sample.objects.filter(order__in=orders_qs)

        window_orders = orders_qs.filter(created_at__gte=since)
        ended_in_window = orders_qs.filter(ended_at__gte=since)

        created = window_orders.count()
        done = ended_in_window.filter(status=Order.Status.DONE).count()
        rejected = ended_in_window.filter(status=Order.Status.REJECTED).count()
        in_progress = orders_qs.filter(status=Order.Status.IN_PROGRESS).count()
        # Rejection rate measured on orders that *reached a terminal state*
        # in the window — using `created` as the denominator misleads when
        # there are long-running orders still in flight.
        decided = done + rejected
        rejection_rate = (rejected / decided * 100) if decided else 0.0

        # Lead time: order.created_at → order.ended_at for orders that
        # ended in the window. Computed in Python after fetching the two
        # timestamps so the math stays DB-agnostic (MySQL doesn't expose
        # EXTRACT(epoch) without TIMESTAMPDIFF gymnastics).
        def _mean_hours(qs):
            rows = list(qs.values_list('created_at', 'ended_at'))
            if not rows:
                return 0.0
            total = sum((b - a).total_seconds() for a, b in rows if a and b)
            return round(total / len(rows) / 3600.0, 2)

        lead_done = _mean_hours(ended_in_window.filter(status=Order.Status.DONE))
        lead_rejected = _mean_hours(
            ended_in_window.filter(status=Order.Status.REJECTED),
        )

        # Sign-off latency: first Approval per stage minus the stage's
        # source order.created_at (OrderStage has no created_at field, so
        # we fall back to the parent order's created_at — both timestamps
        # mark "when the request landed on the manager's desk").
        first_approvals = (
            Approval.objects
            .filter(stage__in=stage_qs, decided_at__gte=since)
            .values('stage__order__created_at')
            .annotate(first_dt=Min('decided_at'))
        )
        deltas = []
        for row in first_approvals:
            order_created = row['stage__order__created_at']
            first_dt = row['first_dt']
            if order_created and first_dt:
                deltas.append((first_dt - order_created).total_seconds())
        signoff_latency = (
            round(sum(deltas) / len(deltas) / 3600.0, 2)
            if deltas else 0.0
        )

        order_status = _counts_by(orders_qs, 'status')
        stage_status = _counts_by(stage_qs, 'status')
        sample_status = _counts_by(sample_qs, 'status')

        # Per-equipment-type breakdown — running stages + completed samples
        # in the window, plus mean run hours of the completed samples.
        et_rows = []
        for et in EquipmentType.objects.filter(equipments__in=eq_qs).distinct():
            running = stage_qs.filter(
                equipment__equipment_type=et,
                status=OrderStage.Status.IN_PROGRESS,
            ).count()
            window_samples = sample_qs.filter(
                equipment__equipment_type=et,
                status=Sample.Status.DONE,
                completed_at__gte=since,
            )
            done_count = window_samples.count()
            run_hours = 0.0
            if done_count:
                pairs = window_samples.values_list('loaded_at', 'completed_at')
                durations = [
                    (b - a).total_seconds()
                    for a, b in pairs if a and b
                ]
                if durations:
                    run_hours = round(sum(durations) / len(durations) / 3600.0, 2)
            if running or done_count:
                et_rows.append({
                    'equipment_type_id': et.id,
                    'name': et.name,
                    'name_en': getattr(et, 'name_en', '') or et.name,
                    'running_stages': running,
                    'completed_samples': done_count,
                    'mean_run_hours': run_hours,
                })
        et_rows.sort(key=lambda r: r['completed_samples'] + r['running_stages'], reverse=True)

        return Response({
            'days': days,
            'totals': {
                'created': created,
                'done': done,
                'rejected': rejected,
                'in_progress': in_progress,
                'rejection_rate_pct': round(rejection_rate, 2),
            },
            'order_status': [
                {'status': k, 'count': v} for k, v in order_status.items()
            ],
            'stage_status': [
                {'status': k, 'count': v} for k, v in stage_status.items()
            ],
            'sample_status': [
                {'status': k, 'count': v} for k, v in sample_status.items()
            ],
            'lead_times': {
                'mean_hours_done': lead_done,
                'mean_hours_rejected': lead_rejected,
                'signoff_latency_hours': signoff_latency,
            },
            'by_equipment_type': et_rows,
        })


class OperatorActivityDetailView(APIView):
    """GET /api/monitoring/charts/operator-activity/<user_id>/?days=30

    Per-operator action timeline. Manager-only; the requested user must
    belong to the manager's lab (superuser sees everyone).

    Merges three sources into one chronological list:

    * **approve / reject** — :class:`orders.models.Approval` rows the
      user authored (decision + comment + order_no).
    * **load / unload / receive / note** — :class:`scheduling.models.StageEvent`
      rows where ``operator`` is the user (the 上下貨 history).
    * **dispatch / set_parameters / assign / complete** — Sample
      lifecycle stamps (``dispatched_by``, ``parameters_set_by``,
      ``assignee`` + ``loaded_by``, ``completed_by``) projected as
      synthetic timeline rows so the manager sees the *whole* relay,
      not just the load/unload bits.

    Returns ``{user, totals, timeline: [{ts, kind, action, order_no,
    sample_code, status, detail}, …]}`` — newest first, capped at 200.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request, user_id):
        if not _is_manager_or_superuser(request.user):
            return Response(
                {'detail': 'Restricted to lab supervisors and superusers.'},
                status=403,
            )
        days = _clamp(request.query_params.get('days'), default=30, lo=1, hi=180)
        limit = _clamp(request.query_params.get('limit'), default=200, lo=10, hi=500)
        since = timezone.now() - timedelta(days=days)

        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=404)

        manager = request.user
        if manager.role == 'lab_manager':
            if not manager.department_id or (
                target.department_id != manager.department_id
                and not (
                    target.department
                    and manager.department
                    and target.department.fab_id == manager.department.fab_id
                    and target.department.name == manager.department.name
                )
            ):
                return Response(
                    {'detail': 'Operator is outside your lab.'},
                    status=403,
                )

        timeline = []

        # 1) Approval rows ---------------------------------------------------
        approvals = (
            Approval.objects
            .filter(actor=target, decided_at__gte=since)
            .select_related('stage__order')
            .order_by('-decided_at')[:limit]
        )
        for ap in approvals:
            order = ap.stage.order
            timeline.append({
                'ts': ap.decided_at,
                'kind': 'approval',
                'action': ap.decision,  # 'approved' | 'rejected'
                'order_id': str(order.id),
                'order_no': order.order_no,
                'sample_code': '',
                'status': ap.decision,
                'detail': ap.comment or '',
            })

        # 2) StageEvent rows -------------------------------------------------
        events = (
            StageEvent.objects
            .filter(operator=target, occurred_at__gte=since)
            .select_related('stage__order', 'equipment')
            .order_by('-occurred_at')[:limit]
        )
        for ev in events:
            order = ev.stage.order
            timeline.append({
                'ts': ev.occurred_at,
                'kind': 'event',
                'action': ev.event_type,  # load / unload / receive / note / abort
                'order_id': str(order.id),
                'order_no': order.order_no,
                'sample_code': '',
                'status': ev.event_type,
                'detail': ev.notes or '',
                'equipment_code': ev.equipment.code if ev.equipment else '',
            })

        # NOTE — historically this view also emitted synthetic "sample
        # lifecycle" rows projected from Sample.*_by / *_at pairs. The
        # StageEvent table now carries proper typed entries for every
        # milestone (split / dispatch / set_parameters / assign / load /
        # unload), so the synthetic rows were causing duplicates and the
        # mis-labelled "量測" the user reported. We rely on the typed
        # StageEvent rows only.

        timeline.sort(key=lambda r: r['ts'], reverse=True)
        timeline = timeline[:limit]

        # Summary counts by action so the manager has a glance-able
        # breakdown next to the raw timeline.
        totals = {}
        for row in timeline:
            totals[row['action']] = totals.get(row['action'], 0) + 1

        return Response({
            'user': {
                'id': str(target.id),
                'username': target.username,
                'display_name': target.name,
                'role': target.role,
                'department': target.department.name if target.department else '',
            },
            'days': days,
            'totals': totals,
            'timeline': timeline,
        })


class SampleListForReportsView(APIView):
    """GET /api/monitoring/lot-history/?days=30&status=…

    Manager-only browse list — every Sample in the lab over the last
    N days, with the per-step user names so the report row already
    shows the routing without a drill-down click. The detail rows
    behind each row come from :class:`SampleHistoryView` above.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not _is_manager_or_superuser(request.user):
            return Response(
                {'detail': 'Restricted to lab supervisors and superusers.'},
                status=403,
            )
        from orders.models import Sample
        days = _clamp(request.query_params.get('days'), default=30, lo=1, hi=180)
        since = timezone.now() - timedelta(days=days)
        qs = (
            Sample.objects
            .select_related(
                'order', 'order__department',
                'equipment', 'recipe',
                'created_by', 'dispatched_by', 'parameters_set_by', 'assignee',
                'loaded_by', 'completed_by',
            )
            .filter(created_at__gte=since)
        )
        user = request.user
        if user.role == 'lab_manager' and user.department_id:
            dept = user.department
            qs = qs.filter(
                Q(order__department_id=user.department_id)
                | Q(order__department__fab_id=dept.fab_id,
                    order__department__name=dept.name)
            )
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        rows = []
        for s in qs.order_by('-created_at')[:200]:
            rows.append({
                'id': str(s.id),
                'sub_code': s.sub_code,
                'full_code': s.full_code,
                'order_no': s.order.order_no,
                'department_name': s.order.department.name if s.order.department else None,
                'wafer_count': s.wafer_count,
                'status': s.status,
                'status_display': s.get_status_display(),
                'equipment_code': s.equipment.code if s.equipment else None,
                'recipe_name': s.recipe.name if s.recipe else None,
                'split_by': s.created_by.username if s.created_by else None,
                'dispatch_by': s.dispatched_by.username if s.dispatched_by else None,
                'params_by': s.parameters_set_by.username if s.parameters_set_by else None,
                'operator': s.assignee.username if s.assignee else None,
                'loaded_at': s.loaded_at,
                'completed_at': s.completed_at,
                'created_at': s.created_at,
            })
        return Response({'days': days, 'count': len(rows), 'rows': rows})


class SampleHistoryView(APIView):
    """GET /api/monitoring/lot-history/<uuid:sample_id>/

    Per-sub-LOT (Sample) life-cycle timeline. Designed for the lab-supervisor
    drill-down so each LOT can be traced step-by-step:

    * 接件 + 簽核 — Approval rows on the parent OrderStage
    * 分貨 — Sample created_at / created_by
    * 派工 — Sample dispatched_by / equipment / recipe / schedule
    * 設定參數 — Sample parameters_set_at / parameters_set_by / overrides
    * 自動指派 — Sample assignee (auto-picked by workload)
    * 上貨 / 量測 / 下貨 — StageEvent rows whose [<sub_code>] tag
      matches this sample (services route the per-sample events that way).

    Access: lab_manager (own lab only), superuser (all labs). lab_member
    can only drill into samples they directly touched (created /
    dispatched / params-set / assigned) so the per-LOT history page is
    useful from the workbench too.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request, sample_id):
        from orders.models import Sample
        try:
            sample = (
                Sample.objects
                .select_related(
                    'order', 'order__department', 'order__department__fab',
                    'order__user',
                    'equipment', 'equipment__equipment_type',
                    'recipe',
                    'created_by', 'dispatched_by', 'parameters_set_by',
                    'assignee', 'loaded_by', 'completed_by',
                )
                .get(pk=sample_id)
            )
        except Sample.DoesNotExist:
            return Response({'detail': 'Sample not found.'}, status=404)

        user = request.user
        if not self._can_view(user, sample):
            return Response({'detail': 'Out-of-scope sample.'}, status=403)

        # Build the timeline rows from each model surface.
        timeline = []

        # 1) Approval rows on the parent stage (簽核 / 駁回).
        stage = sample.order.stages.first()
        if stage:
            for ap in stage.approvals.select_related('actor').order_by('decided_at'):
                timeline.append({
                    'ts': ap.decided_at,
                    'step': 'approval',
                    'actor': ap.actor.username if ap.actor else None,
                    'actor_name': ap.actor.name if ap.actor else None,
                    'detail': ap.comment or '',
                    'status': ap.decision,
                })
            # 接件 (now auto-stamped on signoff)
            if stage.received_at:
                timeline.append({
                    'ts': stage.received_at,
                    'step': 'receive',
                    'actor': stage.received_by.username if stage.received_by else None,
                    'actor_name': stage.received_by.name if stage.received_by else None,
                    'detail': '簽核時自動接件',
                    'status': 'received',
                })

        # 2) StageEvent rows tagged with this sample's sub_code. The
        # StageEvent table now carries typed entries for every milestone
        # (split / dispatch / set_parameters / assign / load / unload),
        # so we just project them and drop the old "synthetic snapshot"
        # rows that used to read Sample.*_by / *_at directly — those
        # were causing duplicate steps and the mislabelled "量測" the
        # user reported.
        if stage:
            for ev in stage.events.select_related('operator', 'equipment').order_by('occurred_at'):
                tag = f'[{sample.sub_code}]'
                # split events are stage-wide (one per stage), no tag.
                belongs_to_sample = (
                    tag in (ev.notes or '')
                    or ev.event_type == 'split'
                )
                if not belongs_to_sample:
                    continue
                timeline.append({
                    'ts': ev.occurred_at,
                    'step': ev.event_type,
                    'actor': ev.operator.username if ev.operator else None,
                    'actor_name': ev.operator.name if ev.operator else None,
                    'detail': (ev.notes or '').replace(tag, '').strip() or ev.event_type,
                    'status': ev.event_type,
                    'measurement': ev.measurement or {},
                })

        # Stable sort by timestamp ascending — easier to read as a story.
        timeline.sort(key=lambda r: r['ts'])

        return Response({
            'sample': {
                'id': str(sample.id),
                'sub_code': sample.sub_code,
                'full_code': sample.full_code,
                'wafer_count': sample.wafer_count,
                'status': sample.status,
                'status_display': sample.get_status_display(),
                'equipment_code': sample.equipment.code if sample.equipment else None,
                'recipe_name': sample.recipe.name if sample.recipe else None,
                'parameter_overrides': sample.parameter_overrides or {},
                'department_name': (
                    sample.order.department.name if sample.order.department else None
                ),
                'fab_name': (
                    sample.order.department.fab.fab_name
                    if sample.order.department and sample.order.department.fab else None
                ),
                'order_no': sample.order.order_no,
                'requester': sample.order.user.username if sample.order.user else None,
            },
            'timeline': timeline,
        })

    def _can_view(self, user, sample):
        if user.role == 'superuser':
            return True
        if user.role == 'lab_manager':
            if not user.department_id:
                return False
            dept = user.department
            ord_dept = sample.order.department
            if not ord_dept:
                return False
            return (
                ord_dept.id == user.department_id
                or (
                    ord_dept.fab_id == dept.fab_id
                    and ord_dept.name == dept.name
                )
            )
        if user.role == 'lab_member':
            ids_touching = {
                sample.created_by_id, sample.dispatched_by_id,
                sample.parameters_set_by_id, sample.assignee_id,
                sample.loaded_by_id, sample.completed_by_id,
            }
            return user.id in ids_touching
        if user.role == 'regular_employee':
            return sample.order.user_id == user.id
        return False


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

        # Cards are scoped to the user's specialty so each role only sees
        # the queues they actually act on. The 待指派 card is gone —
        # the operator step is auto-assigned. Operators get personal
        # "我待上貨 / 我進行中 / 我已完成" counters.
        specialty = getattr(user, 'lab_specialty', '') or ''
        cards = []

        if specialty == 'coord':
            to_split = OrderStage.objects.filter(
                same_lab_stage,
                status=OrderStage.Status.APPROVED,
            ).annotate(sample_count=Count('order__samples')).filter(
                sample_count=0,
            ).count()
            cards.append({
                'key': 'to_split', 'label': '待分貨', 'value': to_split,
                'color': '#722ed1',
                'hint': '主管已簽核但尚未進行分貨的訂單 (你是 WIP 協調員)',
            })
        elif specialty == 'dispatcher':
            to_dispatch = Sample.objects.filter(
                same_lab_sample, status=Sample.Status.WAITING,
            ).count()
            cards.append({
                'key': 'to_dispatch', 'label': '待派工 (子LOT)',
                'value': to_dispatch, 'color': '#1890ff',
                'hint': '已分貨但尚未指派機台 + Recipe + 排程的子 LOT (你是派工排班員)',
            })
        elif specialty == 'engineer':
            to_params = Sample.objects.filter(
                same_lab_sample, status=Sample.Status.DISPATCHED,
            ).count()
            cards.append({
                'key': 'to_params', 'label': '待設定參數 (子LOT)',
                'value': to_params, 'color': '#13c2c2',
                'hint': '已派工但尚未在 Recipe 範圍內設定參數的子 LOT (你是製程工程師)',
            })
        elif specialty == 'operator':
            my_ready = Sample.objects.filter(assignee=user, status=Sample.Status.READY).count()
            my_running = Sample.objects.filter(assignee=user, status=Sample.Status.RUNNING).count()
            my_done = Sample.objects.filter(assignee=user, status=Sample.Status.DONE).count()
            cards += [
                {'key': 'my_ready', 'label': '我待上貨', 'value': my_ready, 'color': '#722ed1',
                 'hint': '已指派給我、等我上貨開始實驗的子 LOT'},
                {'key': 'my_running', 'label': '我進行中', 'value': my_running, 'color': '#fa541c',
                 'hint': '我正在機台上執行中的子 LOT'},
                {'key': 'my_done', 'label': '我已完成', 'value': my_done, 'color': '#8c8c8c',
                 'hint': '我累計完成的子 LOT 數'},
            ]
        else:
            # No specialty set — show the whole lab summary so the user
            # can at least see what's going on. Treat this as a fallback
            # for accounts created without the demo seeder.
            to_split = OrderStage.objects.filter(
                same_lab_stage, status=OrderStage.Status.APPROVED,
            ).annotate(sample_count=Count('order__samples')).filter(
                sample_count=0,
            ).count()
            to_dispatch = Sample.objects.filter(same_lab_sample, status=Sample.Status.WAITING).count()
            to_params = Sample.objects.filter(same_lab_sample, status=Sample.Status.DISPATCHED).count()
            my_running = Sample.objects.filter(assignee=user, status=Sample.Status.RUNNING).count()
            cards = [
                {'key': 'to_split', 'label': '待分貨', 'value': to_split, 'color': '#722ed1', 'hint': '主管已簽核但尚未進行分貨的訂單'},
                {'key': 'to_dispatch', 'label': '待派工', 'value': to_dispatch, 'color': '#1890ff', 'hint': '已分貨但尚未派工的子 LOT'},
                {'key': 'to_params', 'label': '待設定參數', 'value': to_params, 'color': '#13c2c2', 'hint': '已派工但尚未設定參數的子 LOT'},
                {'key': 'my_running', 'label': '我進行中', 'value': my_running, 'color': '#fa541c', 'hint': '我正在機台上執行中的子 LOT'},
            ]
        return cards

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
