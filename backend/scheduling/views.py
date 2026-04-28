"""
scheduling/views.py
"""
from rest_framework import generics, permissions, status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import EquipmentBooking
from .serializers import EquipmentBookingSerializer, AvailabilityQuerySerializer
from .services import check_availability
from equipments.serializers import EquipmentSerializer


class BookingListView(generics.ListAPIView):
    """
    GET /api/scheduling/bookings/
    Optional query params: ?equipment_id=<uuid>&order_id=<uuid>
    """
    serializer_class = EquipmentBookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = EquipmentBooking.objects.select_related(
            'equipment__equipment_type', 'order',
        ).all()
        eq_id = self.request.query_params.get('equipment_id')
        order_id = self.request.query_params.get('order_id')
        if eq_id:
            qs = qs.filter(equipment_id=eq_id)
        if order_id:
            qs = qs.filter(order_id=order_id)
        return qs


class BookingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/scheduling/bookings/<id>/X"""
    queryset = EquipmentBooking.objects.all()
    serializer_class = EquipmentBookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        booking = serializer.save()
        if booking.stage:
            stage = booking.stage
            stage.schedule_start = booking.started_at
            stage.schedule_end = booking.ended_at
            stage.save()



class AvailabilityView(APIView):
    """
    GET /api/scheduling/availability/?experiment_id=...&start=...&end=...
    Returns the available equipment per required type.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        ser = AvailabilityQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        try:
            allocation_map = check_availability(d['experiment_id'], d['start'], d['end'])
        except Exception as e:
            return Response({'detail': str(e)}, status=http_status.HTTP_409_CONFLICT)

        result = []
        for req, equipments in allocation_map.items():
            result.append({
                'equipment_type': req.equipment_type.name,
                'required': req.quantity,
                'available': EquipmentSerializer(equipments, many=True).data,
            })
        return Response(result)
