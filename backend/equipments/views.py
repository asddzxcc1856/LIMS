"""
equipments/views.py
"""
from rest_framework import generics, permissions, status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Experiment, EquipmentType, Equipment, ExperimentRequiredEquipment
from .serializers import (
    ExperimentSerializer,
    EquipmentTypeSerializer,
    EquipmentSerializer,
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
    inventory: lab managers only see their own lab's units; superusers see
    everything; everyone else gets an empty list.
    """
    serializer_class = EquipmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Equipment.objects.select_related('equipment_type', 'department').all()
        if user.role == 'superuser':
            pass  # full access
        elif user.role == 'lab_manager' and user.department_id:
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
    """GET/PUT /api/equipments/<id>/"""
    queryset = Equipment.objects.select_related('equipment_type').all()
    serializer_class = EquipmentSerializer
    permission_classes = [permissions.IsAuthenticated]


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
        elif user.role == 'lab_manager' and user.department_id:
            dept = user.department
            from django.db.models import Q
            scoped_equipments = Equipment.objects.filter(
                Q(department_id=user.department_id) |
                Q(department__fab_id=dept.fab_id, department__name=dept.name)
            )
        else:
            return Response(
                {'detail': 'Equipment overview is restricted to lab managers.'},
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
