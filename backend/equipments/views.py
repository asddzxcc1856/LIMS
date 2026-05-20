"""
equipments/views.py
"""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Equipment,
    EquipmentType,
    Experiment,
    ExperimentRequiredEquipment,
    Recipe,
)
from .serializers import (
    EquipmentSerializer,
    EquipmentTypeSerializer,
    ExperimentSerializer,
    RecipeSerializer,
)
from scheduling.models import EquipmentBooking


class ExperimentListView(generics.ListCreateAPIView):
    """GET/POST /api/equipments/experiments/"""
    queryset = Experiment.objects.prefetch_related('required_equipments__equipment_type').all()
    serializer_class = ExperimentSerializer
    permission_classes = [permissions.IsAuthenticated]


class ExperimentDetailView(generics.RetrieveUpdateAPIView):
    """GET/PUT /api/equipments/experiments/<id>/"""
    queryset = Experiment.objects.prefetch_related('required_equipments__equipment_type').all()
    serializer_class = ExperimentSerializer
    permission_classes = [permissions.IsAuthenticated]


class EquipmentTypeListView(generics.ListCreateAPIView):
    """GET/POST /api/equipments/types/"""
    queryset = EquipmentType.objects.all()
    serializer_class = EquipmentTypeSerializer
    permission_classes = [permissions.IsAuthenticated]


class EquipmentListView(generics.ListCreateAPIView):
    """GET/POST /api/equipments/

    Scoped per role to keep the requester UI from peeking at machine
    inventory:
    * lab_manager / lab_member of the lab see their own units (the
      member needs this to populate the 派工 dropdown);
    * superusers see everything;
    * requesters get nothing — they never touch machines.
    """
    serializer_class = EquipmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Equipment.objects.select_related('equipment_type', 'department').all()
        if user.role == 'superuser':
            pass  # full access
        elif user.role in ('lab_manager', 'lab_member') and user.department_id:
            from django.db.models import Q
            dept = user.department
            qs = qs.filter(
                Q(department_id=user.department_id) |
                Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
        else:
            return qs.none()

        type_id = self.request.query_params.get('type_id')
        if type_id:
            qs = qs.filter(equipment_type_id=type_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class EquipmentDetailView(generics.RetrieveUpdateAPIView):
    """GET/PUT /api/equipments/<id>/

    Used by the manager-only UI to flip a machine to ``maintenance`` /
    ``available`` etc. Triggers the post_save signal in
    :mod:`equipments.signals` which fans out CRITICAL notifications
    when status crosses into ``maintenance`` / ``pending``.
    """
    queryset = Equipment.objects.select_related('equipment_type').all()
    serializer_class = EquipmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def update(self, request, *args, **kwargs):
        # Manager + superuser only — operators cannot change machine
        # state from the lab page.
        if request.user.role not in ('lab_manager', 'superuser'):
            return Response(
                {'detail': 'Equipment status changes are restricted to lab supervisors.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if request.user.role not in ('lab_manager', 'superuser'):
            return Response(
                {'detail': 'Equipment status changes are restricted to lab supervisors.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )
        return super().partial_update(request, *args, **kwargs)


class EquipmentStatusMatrixView(APIView):
    """
    GET /api/equipments/status-matrix/

    Equipment visibility intentionally hidden from requesters: lab managers
    see only their own lab's units, superusers see everything, anyone else
    is rejected with 403. The submission UI must not let a regular employee
    see what machines exist — they only pick the lab + the experiment.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == 'superuser':
            scoped_equipments = Equipment.objects.all()
        elif user.role in ('lab_manager', 'lab_member') and user.department_id:
            # Lab members need the equipment timeline when picking a
            # dispatch slot — broadened to match EquipmentListView.
            dept = user.department
            from django.db.models import Q
            scoped_equipments = Equipment.objects.filter(
                Q(department_id=user.department_id) |
                Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
        else:
            return Response(
                {'detail': 'Equipment overview is restricted to lab personnel.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )

        # Only return equipment types that actually have at least one unit
        # in the caller's scope — empty cards just clutter the dashboard
        # and tip a manager off about machinery that lives in another lab.
        type_ids_in_scope = (
            scoped_equipments.values_list('equipment_type_id', flat=True).distinct()
        )
        types = EquipmentType.objects.filter(id__in=type_ids_in_scope)
        result = []
        for eq_type in types:
            equipments = scoped_equipments.filter(
                equipment_type=eq_type
            ).select_related('equipment_type', 'department')
            items = []
            for eq in equipments:
                item = {
                    'id': str(eq.id),
                    'code': eq.code,
                    'status': eq.status,
                    'department_name': eq.department.name if eq.department else 'N/A'
                }
                # If occupied, find active booking
                if eq.status == Equipment.Status.OCCUPIED:
                    active_booking = (
                        EquipmentBooking.objects
                        .filter(equipment=eq, order__status='in_progress')
                        .select_related('order')
                        .first()
                    )
                    if active_booking:
                        item['active_order'] = {
                            'order_no': active_booking.order.order_no,
                            'order_id': str(active_booking.order.id),
                            'started_at': active_booking.started_at.isoformat(),
                            'ended_at': active_booking.ended_at.isoformat(),
                        }
                items.append(item)
            result.append({
                'type_id': str(eq_type.id),
                'type_name': eq_type.name,
                'equipments': items,
            })
        return Response(result)


class RecipeListView(generics.ListAPIView):
    """GET /api/equipments/recipes/

    Lab managers and members see only the recipes whose equipment_type has
    at least one unit deployed in their lab — keeping recipe visibility in
    line with the equipment visibility policy (managers never peek into
    other labs' machinery). Superusers see everything. Regular employees
    get an empty list rather than a 403 to mirror the row-level scoping
    used elsewhere.

    Query params:
      * ``equipment_type`` — UUID, narrow to one type (used by the dispatch
        modal once a machine is picked)
      * ``is_active`` — ``true|false``; defaults to active-only when omitted
    """

    serializer_class = RecipeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Recipe.objects.select_related('equipment_type').all()

        if user.role == 'superuser':
            pass
        elif user.role in ('lab_manager', 'lab_member') and user.department_id:
            from django.db.models import Q
            dept = user.department
            scoped_eq = Equipment.objects.filter(
                Q(department_id=user.department_id)
                | Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
            type_ids = scoped_eq.values_list('equipment_type_id', flat=True).distinct()
            qs = qs.filter(equipment_type_id__in=type_ids)
        else:
            return qs.none()

        equipment_type = self.request.query_params.get('equipment_type')
        if equipment_type:
            qs = qs.filter(equipment_type_id=equipment_type)
        is_active = self.request.query_params.get('is_active')
        if is_active is None:
            qs = qs.filter(is_active=True)
        elif is_active.lower() in ('false', '0', 'no'):
            qs = qs.filter(is_active=False)
        elif is_active.lower() in ('true', '1', 'yes'):
            qs = qs.filter(is_active=True)
        return qs


class EquipmentTelemetryView(APIView):
    """POST /api/equipments/<uuid:pk>/telemetry/

    Machines (or a service-account proxy) push experiment data here while
    a stage is running. Each payload becomes a ``StageEvent`` row attached
    to the equipment's active in-progress stage, so the audit log already
    built for upload/download events keeps a single source of truth.

    Optional ``finished: true`` closes the stage in the same call —
    realising the spec's "自動將實驗數據蒐集起來,並自動結單" pipeline
    without needing a separate manual unload step.

    Body shape::

        {
          "measurement": {"temp": 250.2, "kV": 99.8, "result": "ok"},
          "notes": "free-text observation",
          "finished": true
        }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role not in ('lab_member', 'lab_manager', 'superuser'):
            return Response(
                {'detail': 'Telemetry is restricted to lab personnel.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )

        from django.db.models import Q
        qs = Equipment.objects.all()
        if user.role != 'superuser':
            dept = user.department
            if dept is None:
                return Response(
                    {'detail': 'User must belong to a department to post telemetry.'},
                    status=http_status.HTTP_403_FORBIDDEN,
                )
            qs = qs.filter(
                Q(department_id=user.department_id)
                | Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
        equipment = get_object_or_404(qs, pk=pk)

        # Look up the active in-progress stage running on this machine —
        # bookings span the active window so a single query nails it.
        from orders.models import OrderStage
        now = timezone.now()
        stage = (
            OrderStage.objects
            .filter(
                equipment=equipment,
                status=OrderStage.Status.IN_PROGRESS,
            )
            .order_by('-schedule_start')
            .first()
        )
        if stage is None:
            return Response(
                {'detail': 'No active stage is running on this equipment.'},
                status=http_status.HTTP_409_CONFLICT,
            )

        measurement = request.data.get('measurement') or {}
        if not isinstance(measurement, dict):
            return Response(
                {'detail': 'measurement must be a JSON object.'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        notes = request.data.get('notes', '')
        finished = bool(request.data.get('finished', False))

        from scheduling.services import record_stage_event
        event = record_stage_event(
            stage,
            event_type='note',
            operator=user,
            notes=notes,
            measurement=measurement,
        )

        completed = False
        if finished:
            from orders.services import complete_stage
            try:
                complete_stage(stage, operator=user)
                completed = True
            except Exception as exc:
                # Telemetry still landed in StageEvent — surface the close
                # failure but don't lose the data point.
                return Response(
                    {
                        'event_id': str(event.id),
                        'completed': False,
                        'detail': str(exc),
                    },
                    status=http_status.HTTP_200_OK,
                )

        return Response({
            'event_id': str(event.id),
            'stage_id': str(stage.id),
            'completed': completed,
            'occurred_at': event.occurred_at,
        }, status=http_status.HTTP_201_CREATED)


class CapacityCheckView(APIView):
    """
    GET /api/equipments/capacity-check/?experiment_id=<uuid>
    Returns per-type available vs required, with shortage warnings.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        experiment_id = request.query_params.get('experiment_id')
        if not experiment_id:
            return Response({'detail': 'experiment_id is required.'}, status=400)

        requirements = ExperimentRequiredEquipment.objects.filter(
            experiment_id=experiment_id,
        ).select_related('equipment_type')

        result = []
        has_shortage = False
        for req in requirements:
            available_count = Equipment.objects.filter(
                equipment_type=req.equipment_type,
                status=Equipment.Status.AVAILABLE,
            ).count()
            shortage = available_count < req.quantity
            if shortage:
                has_shortage = True
            result.append({
                'equipment_type': req.equipment_type.name,
                'required': req.quantity,
                'available': available_count,
                'shortage': shortage,
            })

        return Response({
            'has_shortage': has_shortage,
            'details': result,
        })
