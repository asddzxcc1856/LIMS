"""
orders/views.py
"""
from rest_framework import generics, permissions, status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from django.shortcuts import get_object_or_404

from equipments.models import Experiment
from scheduling.models import StageEvent
from scheduling.serializers import StageEventSerializer
from scheduling.services import record_stage_event
from users.models import WaferLot
from .models import Order, OrderStage
from .serializers import (
    ApprovalSerializer,
    OrderListSerializer,
    OrderDetailSerializer,
    OrderCreateSerializer,
    OrderReviewSerializer,
    OrderStageSerializer,
    SampleSerializer,
)

from . import services


# ── Permission helpers ─────────────────────────────────────────────────────

class IsLabManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ('lab_manager', 'superuser')


class IsLabMember(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ('lab_member', 'lab_manager', 'superuser')


class IsRegularEmployee(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ('regular_employee', 'superuser')



# ── Views ──────────────────────────────────────────────────────────────────

class OrderListView(generics.ListAPIView):
    """
    GET /api/orders/
    Requester sees own orders, Manager sees department orders, Superuser sees all.
    """
    serializer_class = OrderListSerializer

    def get_queryset(self):
        """Visibility scoping per role:

        * superuser          — every order
        * lab_manager        — orders whose department is the manager's lab
        * lab_member         — orders that have at least one stage assigned to them
        * regular_employee   — only orders they themselves submitted
        """
        user = self.request.user
        qs = Order.objects.select_related('user', 'experiment', 'department', 'assignee')

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        if user.role == 'superuser':
            return qs
        if user.role == 'lab_manager' and user.department_id:
            dept = user.department
            return qs.filter(
                Q(department_id=user.department_id) |
                Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
        if user.role == 'lab_member':
            return qs.filter(stages__assignee=user).distinct()
        # regular_employee
        return qs.filter(user=user)


class OrderCreateView(APIView):
    """POST /api/orders/create/ – Requester submits a new order (no schedule)."""
    permission_classes = [IsRegularEmployee]

    def post(self, request):
        ser = OrderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        experiment = get_object_or_404(
            Experiment, id=ser.validated_data['experiment']
        )

        # Lot ID is the WaferLot's primary key (its code). Reject anything
        # that isn't a registered lot in the requester's fab — the dropdown
        # already constrains the UI, this is the API-level safety net.
        lot_code = ser.validated_data['lot_id']
        try:
            lot = WaferLot.objects.get(pk=lot_code)
        except WaferLot.DoesNotExist:
            return Response(
                {'lot_id': [f'Wafer lot "{lot_code}" is not registered.']},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        user_fab_id = (
            request.user.department.fab_id if request.user.department else None
        )
        if (
            request.user.role != 'superuser'
            and user_fab_id is not None
            and lot.fab_id != user_fab_id
        ):
            return Response(
                {'lot_id': ['Wafer lot belongs to a different fab.']},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        order = services.create_order(
            user=request.user,
            experiment=experiment,
            lot=lot,
            is_urgent=ser.validated_data.get('is_urgent', False),
            requirements=ser.validated_data.get('requirements', ''),
            remark=ser.validated_data.get('remark', ''),
        )
        return Response(
            OrderDetailSerializer(order).data,
            status=http_status.HTTP_201_CREATED,
        )


class OrderDetailView(generics.RetrieveAPIView):
    """GET /api/orders/<uuid:pk>/

    Returns 404 instead of 403 when the requester lacks visibility — mirrors
    the row-level filtering of the list endpoint and avoids leaking the
    existence of orders outside the caller's scope.
    """
    serializer_class = OrderDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = (
            Order.objects
            .select_related('user', 'experiment', 'department', 'department__fab', 'assignee')
            .prefetch_related(
                'stages__department',
                'stages__equipment_type',
                'stages__equipment',
                'stages__assignee',
            )
        )
        if user.role == 'superuser':
            return qs
        if user.role == 'lab_manager' and user.department_id:
            dept = user.department
            return qs.filter(
                Q(department_id=user.department_id) |
                Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
        if user.role == 'lab_member':
            return qs.filter(stages__assignee=user).distinct()
        return qs.filter(user=user)


class OrderReviewView(generics.UpdateAPIView):
    """
    PATCH /api/v1/orders/stages/<uuid:pk>/review/
    { "action": "approve", "schedule_start": "...", "schedule_end": "...", "assignee": "..." }
    """
    queryset = OrderStage.objects.all()
    serializer_class = OrderStageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        stage = self.get_object()
        action = request.data.get('action')
        user = request.user

        # Role gating per req:
        # * 簽核 / 駁回         — lab_manager (or superuser) only
        # * 派工 (approve combo) — lab_member  (or superuser) only;
        #                          the manager has been removed from the
        #                          dispatch flow on purpose
        # * reassign            — lab_member  (or superuser) only
        if action == 'reject':
            if user.role not in ('lab_manager', 'superuser'):
                return Response(
                    {'detail': 'Reject is restricted to lab_manager.'},
                    status=http_status.HTTP_403_FORBIDDEN,
                )
        elif action in ('approve', 'reassign'):
            if user.role not in ('lab_member', 'superuser'):
                return Response(
                    {'detail': f'{action} is restricted to lab_member.'},
                    status=http_status.HTTP_403_FORBIDDEN,
                )

        if action == 'approve':
            from .services import approve_and_schedule_stage
            approve_and_schedule_stage(
                stage,
                schedule_start=request.data.get('schedule_start'),
                schedule_end=request.data.get('schedule_end'),
                assignee=request.data.get('assignee'),
                equipment=request.data.get('equipment'),
                recipe=request.data.get('recipe'),
                parameter_overrides=request.data.get('parameter_overrides'),
                actor=request.user,
                comment=request.data.get('comment', ''),
            )
            return Response({'detail': f'Stage {stage.step_order} approved.'})

        if action == 'reject':
            from .services import reject_order
            reject_order(
                stage.order,
                rejection_reason=request.data.get('rejection_reason'),
                actor=request.user,
            )
            return Response({'detail': 'Order rejected.'})

        if action == 'reassign':
            return self._reassign(stage, request)

        return Response({'detail': 'Invalid action.'}, status=400)

    @staticmethod
    def _reassign(stage, request):
        from django.utils import timezone
        from django.utils.dateparse import parse_datetime
        from django.utils.timezone import is_aware, make_aware

        from scheduling.models import EquipmentBooking

        assignee_id = request.data.get('assignee', stage.assignee_id)
        new_start = request.data.get('schedule_start') or stage.schedule_start
        new_end = request.data.get('schedule_end') or stage.schedule_end

        d_start = parse_datetime(new_start) if isinstance(new_start, str) else new_start
        d_end = parse_datetime(new_end) if isinstance(new_end, str) else new_end

        if d_start and d_end:
            if not is_aware(d_start):
                d_start = make_aware(d_start)
            if not is_aware(d_end):
                d_end = make_aware(d_end)
            if d_start >= d_end:
                return Response({'detail': 'End time must be after start time.'}, status=400)
            if d_start < timezone.now():
                return Response({'detail': 'Start time cannot be in the past.'}, status=400)

        stage.assignee_id = assignee_id
        stage.schedule_start = new_start
        stage.schedule_end = new_end
        stage.save()

        EquipmentBooking.objects.filter(stage=stage).update(
            started_at=new_start, ended_at=new_end,
        )
        return Response({'detail': 'Task reassigned/rescheduled.'})


class OrderStageListView(generics.ListAPIView):
    """GET /api/v1/orders/stages/?status=waiting"""
    serializer_class = OrderStageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Visibility scoping for stages:

        * superuser        — every stage
        * lab_manager      — stages whose department is the manager's lab
                             (so they see who is assigned to what in their lab)
        * lab_member       — only stages assigned to them
        * regular_employee — only stages on their own orders
        """
        user = self.request.user
        qs = (
            OrderStage.objects
            .select_related(
                'order',
                'order__user',
                'order__experiment',
                'department',
                'equipment_type',
                'equipment',
                'assignee',
            )
            .all()
        )

        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)

        if user.role == 'superuser':
            return qs
        if user.role == 'lab_manager' and user.department_id:
            # Primary path: exact dept_id match (the original behaviour).
            # The (fab, name) branch is a belt-and-braces fallback in case
            # future data leaves duplicate Department rows in the wild —
            # Q.OR keeps both working in either direction.
            dept = user.department
            return qs.filter(
                Q(department_id=user.department_id) |
                Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
        if user.role == 'lab_member':
            # Lab member default scope is "stages assigned to me", which
            # keeps the OrderTasks list focused. Pass ``lab_queue=true``
            # to broaden to the whole lab (used by the 接件 / 等待簽核 tabs
            # where the assignee field hasn't been set yet).
            if self.request.query_params.get('lab_queue') == 'true' and user.department_id:
                dept = user.department
                return qs.filter(
                    Q(department_id=user.department_id) |
                    Q(department__fab_id=dept.fab_id, department__name=dept.name)
                )
            return qs.filter(assignee=user)
        return qs.filter(order__user=user)



class OrderSampleListCreateView(APIView):
    """
    GET  /api/orders/<uuid:pk>/samples/ — list this order's WIP groups
    POST same path body={splits: [{sub_code, wafer_count, notes}, …]}

    分貨 (split) is restricted to lab personnel:
    * lab_member / lab_manager in the order's department
    * superuser

    Read scope mirrors row-level order visibility so the requester can
    inspect how their lot was divided up.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _resolve_order(self, pk, user, *, for_write=False):
        from django.db.models import Q
        qs = Order.objects.select_related('department', 'lot').all()
        if user.role == 'superuser':
            pass
        elif user.role == 'lab_manager' and user.department_id:
            dept = user.department
            qs = qs.filter(
                Q(department_id=user.department_id)
                | Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
        elif user.role == 'lab_member' and user.department_id:
            # Member: any order routed to their lab is OK for split write
            # (they handle samples once received), but read still works
            # through the visibility filter via assigned stages.
            if for_write:
                qs = qs.filter(department_id=user.department_id)
            else:
                qs = qs.filter(stages__assignee=user).distinct()
        else:
            qs = qs.filter(user=user)
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        order = self._resolve_order(pk, request.user)
        samples = order.samples.select_related('created_by', 'parent_sample').order_by('sub_code')
        return Response(SampleSerializer(samples, many=True).data)

    def post(self, request, pk):
        user = request.user
        is_lab = user.role in ('lab_member', 'lab_manager') and user.department_id
        if not (is_lab or user.role == 'superuser'):
            return Response(
                {'detail': 'Only lab personnel may split a sample.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )
        order = self._resolve_order(pk, user, for_write=True)
        splits = request.data.get('splits') or []
        parent_sample_id = request.data.get('parent_sample')

        from .models import Sample
        parent = None
        if parent_sample_id:
            try:
                parent = Sample.objects.get(pk=parent_sample_id, order=order)
            except Sample.DoesNotExist:
                return Response(
                    {'detail': 'parent_sample does not belong to this order.'},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )

        from .services import split_order
        try:
            created = split_order(
                order, splits=splits, operator=user, parent_sample=parent,
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)

        return Response(
            SampleSerializer(created, many=True).data,
            status=http_status.HTTP_201_CREATED,
        )


class OrderReceiveView(APIView):
    """POST /api/orders/stages/<uuid:pk>/receive/

    Lab personnel acknowledge the sample is physically at the lab. Any
    lab_member / lab_manager whose department matches the stage's
    department (or a superuser) can call this — the spec puts receiving
    firmly in the lab's hands.

    Visibility deliberately broadens past :func:`_stage_visibility_filter`
    for lab_members: members normally only see stages assigned to them,
    but a not-yet-assigned waiting stage still needs to be receivable by
    anyone in the lab. We narrow back down to the same lab + the
    requester's own orders so out-of-lab leaks stay impossible.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _resolve_stage(self, pk, user):
        from django.db.models import Q
        qs = OrderStage.objects.select_related('order').all()
        if user.role == 'superuser':
            pass
        elif user.role in ('lab_manager', 'lab_member') and user.department_id:
            dept = user.department
            qs = qs.filter(
                Q(department_id=user.department_id)
                | Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
        else:
            qs = qs.filter(order__user=user)
        return get_object_or_404(qs, pk=pk)

    def post(self, request, pk):
        stage = self._resolve_stage(pk, request.user)
        user = request.user

        in_lab = (
            user.role in ('lab_member', 'lab_manager')
            and stage.department_id == user.department_id
        )
        if not (in_lab or user.role == 'superuser'):
            return Response(
                {'detail': 'Only lab personnel may receive the sample for this stage.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )

        from .services import receive_stage
        try:
            receive_stage(stage, operator=user, notes=request.data.get('notes', ''))
        except Exception as exc:
            return Response({'detail': str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)

        return Response({
            'detail': f'Stage {stage.step_order} marked as received.',
            'received_at': stage.received_at,
            'received_by': stage.received_by_id,
        }, status=http_status.HTTP_200_OK)


def _resolve_lab_sample_for_write(pk, user):
    """Resolve a Sample for a per-sub-LOT write action. Visibility:
    lab_member / lab_manager / superuser in the sample's lab. Action
    role rules are enforced by callers (e.g. dispatch refuses manager)."""
    from django.db.models import Q
    from .models import Sample
    qs = (
        Sample.objects
        .select_related(
            'order', 'order__department', 'order__experiment',
            'equipment', 'equipment__equipment_type', 'recipe', 'assignee',
        )
        .all()
    )
    if user.role == 'superuser':
        pass
    elif user.role in ('lab_member', 'lab_manager') and user.department_id:
        dept = user.department
        qs = qs.filter(
            Q(order__department_id=user.department_id)
            | Q(order__department__fab_id=dept.fab_id, order__department__name=dept.name)
        )
    else:
        qs = qs.none()
    return get_object_or_404(qs, pk=pk)


class SampleListView(APIView):
    """GET /api/orders/samples/

    Lists samples visible to the caller. The lab workbench reads this
    instead of /stages/ now that 派工 / 設定參數 / 指派 / 上下貨 are
    per-sample. Filtered by ``status`` query param when provided.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Q
        from .models import Sample
        user = request.user
        qs = (
            Sample.objects
            .select_related(
                'order', 'order__department', 'order__experiment', 'order__user',
                'equipment', 'equipment__equipment_type', 'recipe', 'assignee',
            )
            .all()
        )
        if user.role == 'superuser':
            pass
        elif user.role in ('lab_member', 'lab_manager') and user.department_id:
            dept = user.department
            qs = qs.filter(
                Q(order__department_id=user.department_id)
                | Q(order__department__fab_id=dept.fab_id, order__department__name=dept.name)
            )
        else:
            qs = qs.filter(order__user=user)

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(SampleSerializer(qs.order_by('order', 'execution_order', 'sub_code'), many=True).data)


class SampleDispatchView(APIView):
    """POST /api/orders/samples/<uuid:pk>/dispatch/ — per-sample dispatch."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'superuser'):
            return Response({'detail': '派工限 lab_member 操作。'}, status=403)
        sample = _resolve_lab_sample_for_write(pk, user)
        from .services import dispatch_sample
        try:
            dispatch_sample(
                sample, operator=user,
                equipment=request.data.get('equipment'),
                recipe=request.data.get('recipe'),
                schedule_start=request.data.get('schedule_start'),
                schedule_end=request.data.get('schedule_end'),
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(SampleSerializer(sample).data, status=200)


class SampleParametersView(APIView):
    """POST /api/orders/samples/<uuid:pk>/parameters/ — per-sample 設定參數."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'superuser'):
            return Response({'detail': '設定參數限 lab_member 操作。'}, status=403)
        sample = _resolve_lab_sample_for_write(pk, user)
        from .services import set_sample_parameters
        try:
            set_sample_parameters(
                sample, operator=user,
                parameter_overrides=request.data.get('parameter_overrides') or {},
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(SampleSerializer(sample).data, status=200)


class SampleAssignView(APIView):
    """POST /api/orders/samples/<uuid:pk>/assign/ — per-sample 指派 lab_member."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'superuser'):
            return Response({'detail': '指派員工限 lab_member 操作。'}, status=403)
        sample = _resolve_lab_sample_for_write(pk, user)
        from .services import assign_sample
        try:
            assign_sample(
                sample, operator=user,
                assignee=request.data.get('assignee'),
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(SampleSerializer(sample).data, status=200)


class SampleLoadView(APIView):
    """POST /api/orders/samples/<uuid:pk>/load/ — per-sample 上貨."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'superuser'):
            return Response({'detail': '上貨限 lab_member 操作。'}, status=403)
        sample = _resolve_lab_sample_for_write(pk, user)
        if sample.assignee_id != user.id and user.role != 'superuser':
            return Response(
                {'detail': '只有被指派的員工可以執行上貨。'}, status=403,
            )
        from .services import load_sample
        try:
            load_sample(sample, operator=user)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(SampleSerializer(sample).data, status=200)


class SampleTelemetryView(APIView):
    """POST /api/orders/samples/<uuid:pk>/telemetry/ — push one measurement.

    Body: ``{measurement: {...}, finished: bool, notes: str}``.

    Authentication: same lab + lab_member / superuser. Designed to be
    called by machine agents OR by the "Simulate telemetry" button on
    the Running tab for demo / dev. When ``finished=true`` the call also
    closes the sample (and cascades to closing the order if it was the
    last running sample).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'superuser'):
            return Response(
                {'detail': '上傳量測數據限 lab_member 操作。'}, status=403,
            )
        sample = _resolve_lab_sample_for_write(pk, user)
        if (
            sample.assignee_id != user.id
            and user.role != 'superuser'
        ):
            return Response(
                {'detail': '只有此 sample 的執行員工可以上傳量測數據。'},
                status=403,
            )
        from .services import record_sample_telemetry
        try:
            record_sample_telemetry(
                sample, operator=user,
                measurement=request.data.get('measurement') or {},
                finished=bool(request.data.get('finished', False)),
                notes=request.data.get('notes', ''),
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(SampleSerializer(sample).data, status=200)


class SampleCompleteView(APIView):
    """POST /api/orders/samples/<uuid:pk>/complete/ — per-sample 下貨 / 完成."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'superuser'):
            return Response({'detail': '下貨限 lab_member 操作。'}, status=403)
        sample = _resolve_lab_sample_for_write(pk, user)
        if sample.assignee_id != user.id and user.role != 'superuser':
            return Response(
                {'detail': '只有被指派的員工可以執行下貨 / 完成。'}, status=403,
            )
        from .services import complete_sample
        try:
            complete_sample(
                sample, operator=user,
                measurement=request.data.get('measurement') or {},
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(SampleSerializer(sample).data, status=200)


def _resolve_lab_stage_for_write(pk, user):
    """Visibility for lab-personnel write endpoints (dispatch / params /
    start). lab_member + lab_manager + superuser in the stage's lab.

    Whether a *specific* role is allowed to invoke the action itself is
    decided by the caller (e.g. dispatch refuses lab_manager).
    """
    from django.db.models import Q
    qs = (
        OrderStage.objects
        .select_related('order', 'department', 'equipment', 'recipe', 'assignee')
        .all()
    )
    if user.role == 'superuser':
        pass
    elif user.role in ('lab_member', 'lab_manager') and user.department_id:
        dept = user.department
        qs = qs.filter(
            Q(department_id=user.department_id)
            | Q(department__fab_id=dept.fab_id, department__name=dept.name)
        )
    else:
        qs = qs.none()
    return get_object_or_404(qs, pk=pk)


class StageDispatchView(APIView):
    """POST /api/orders/stages/<uuid:pk>/dispatch/

    派工 step — restricted to lab_member + superuser. The spec calls out
    that dispatch is owned by lab personnel, not the lab manager
    ("派工應該是另外一位實驗室人員負責不是主管"), so a lab_manager
    request is rejected with 403.

    Body::
        {
          "equipment": "<uuid>",
          "recipe": "<uuid>",
          "schedule_start": "...",
          "schedule_end": "..."
        }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'superuser'):
            return Response(
                {'detail': 'Dispatch is restricted to lab_member.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )
        stage = _resolve_lab_stage_for_write(pk, user)
        from .services import dispatch_stage
        try:
            dispatch_stage(
                stage,
                operator=user,
                equipment=request.data.get('equipment'),
                recipe=request.data.get('recipe'),
                schedule_start=request.data.get('schedule_start'),
                schedule_end=request.data.get('schedule_end'),
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Dispatched.'}, status=http_status.HTTP_200_OK)


class StageParametersView(APIView):
    """POST /api/orders/stages/<uuid:pk>/parameters/

    設定參數 step — lab_member + superuser only. Same role rules as
    dispatch; the manager is intentionally locked out.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'superuser'):
            return Response(
                {'detail': 'Parameter setting is restricted to lab_member.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )
        stage = _resolve_lab_stage_for_write(pk, user)
        from .services import set_stage_parameters
        try:
            set_stage_parameters(
                stage,
                operator=user,
                parameter_overrides=request.data.get('parameter_overrides') or {},
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Parameters set.'}, status=http_status.HTTP_200_OK)


class StageStartView(APIView):
    """POST /api/orders/stages/<uuid:pk>/start/

    啟動 step — final hand-off: pick the assignee (must be lab_member,
    never lab_manager) and flip the stage to IN_PROGRESS.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'superuser'):
            return Response(
                {'detail': 'Starting a stage is restricted to lab_member.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )
        stage = _resolve_lab_stage_for_write(pk, user)
        from .services import start_stage
        try:
            start_stage(
                stage,
                operator=user,
                assignee=request.data.get('assignee'),
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Started.'}, status=http_status.HTTP_200_OK)


class OrderCompleteView(generics.UpdateAPIView):
    """Member completes a stage."""
    queryset = OrderStage.objects.all()
    serializer_class = OrderStageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        stage = self.get_object()
        # Only the assignee or any manager in the dept can complete
        if stage.assignee != request.user and request.user.role != 'lab_manager':
            return Response({'detail': 'You are not assigned to this stage.'}, status=403)

        from .services import complete_stage
        complete_stage(stage, operator=request.user)
        return Response({'detail': f'Stage {stage.step_order} completed.'})


def _stage_visibility_filter(qs, user):
    """Mirror OrderStage list scoping for adjacent endpoints (events).

    Returns a queryset narrowed by the caller's role:
    * superuser           — every row
    * lab_manager         — stages in the manager's lab
    * lab_member          — only stages assigned to them
    * regular_employee    — only stages on their own orders
    """
    if user.role == 'superuser':
        return qs
    if user.role == 'lab_manager' and user.department_id:
        dept = user.department
        return qs.filter(
            Q(department_id=user.department_id)
            | Q(department__fab_id=dept.fab_id, department__name=dept.name)
        )
    if user.role == 'lab_member':
        return qs.filter(assignee=user)
    return qs.filter(order__user=user)


class StageApprovalListCreateView(APIView):
    """GET  /api/orders/stages/<uuid:pk>/approvals/ — list approval history.
    POST same path — record a sign-off (signoff-only, no scheduling).

    The POST endpoint exists alongside the compound ``/review/`` endpoint to
    let a manager 簽核 without committing to a schedule. Status stays
    WAITING; the next operator just sees "已簽核, 等待排程".
    """

    permission_classes = [permissions.IsAuthenticated]

    def _resolve_stage(self, pk, user):
        qs = _stage_visibility_filter(
            OrderStage.objects.select_related('order', 'department', 'assignee').all(),
            user,
        )
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        stage = self._resolve_stage(pk, request.user)
        approvals = stage.approvals.select_related('actor').order_by('-decided_at')
        return Response(ApprovalSerializer(approvals, many=True).data)

    def post(self, request, pk):
        stage = self._resolve_stage(pk, request.user)
        user = request.user

        # Only same-lab manager or superuser may sign off — requesters and
        # outsiders can read the history but never write.
        is_lab_manager = user.role == 'lab_manager' and (
            stage.department_id == user.department_id
        )
        if not (is_lab_manager or user.role == 'superuser'):
            return Response(
                {'detail': 'Only the lab manager may sign off this stage.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )

        decision = request.data.get('decision', 'approved')
        if decision != 'approved':
            # Reject still flows through /review/ — keeps state-machine
            # transitions in one place.
            return Response(
                {'detail': 'This endpoint records sign-offs only. Use /review/ to reject.'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        from .services import sign_off_stage
        try:
            approval = sign_off_stage(
                stage, actor=user, comment=request.data.get('comment', ''),
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        return Response(
            ApprovalSerializer(approval).data,
            status=http_status.HTTP_201_CREATED,
        )


class StageEventListCreateView(APIView):
    """GET /api/orders/stages/<uuid:pk>/events/ — list events for one stage.
    POST same path — record a new event (load / unload / abort / note).

    Visibility uses the same row-level rules as :class:`OrderStageListView`,
    so a regular employee can read their own stage's audit trail but never
    another lab's; a lab member sees only stages assigned to them.

    Permission to *write* an event is stricter: only the stage's assignee,
    a manager scoped to the stage's lab, or a superuser may post — this
    keeps an outsider from polluting the operator history.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _resolve_stage(self, pk, user):
        qs = _stage_visibility_filter(
            OrderStage.objects
            .select_related('order', 'department', 'equipment', 'recipe', 'assignee')
            .all(),
            user,
        )
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        stage = self._resolve_stage(pk, request.user)
        events = (
            stage.events
            .select_related('equipment', 'recipe', 'operator')
            .order_by('-occurred_at')
        )
        return Response(StageEventSerializer(events, many=True).data)

    def post(self, request, pk):
        stage = self._resolve_stage(pk, request.user)

        # Only the assignee, a manager scoped to this lab, or a superuser
        # may write events. Other readers get 403 (the row exists; they
        # just lack write permission).
        user = request.user
        is_assignee = stage.assignee_id == user.id
        is_lab_manager = user.role == 'lab_manager' and (
            stage.department_id == user.department_id
        )
        if not (is_assignee or is_lab_manager or user.role == 'superuser'):
            return Response(
                {'detail': 'Only the assignee or the lab manager may record stage events.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )

        event_type = request.data.get('event_type')
        try:
            event = record_stage_event(
                stage,
                event_type=event_type,
                operator=user,
                notes=request.data.get('notes', ''),
                measurement=request.data.get('measurement') or {},
            )
        except Exception as exc:  # ValidationError surfaced from the service
            return Response({'detail': str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)

        return Response(
            StageEventSerializer(event).data,
            status=http_status.HTTP_201_CREATED,
        )
