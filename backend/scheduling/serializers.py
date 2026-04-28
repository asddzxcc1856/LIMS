"""
scheduling/serializers.py
"""
from rest_framework import serializers
from .models import EquipmentBooking


class EquipmentBookingSerializer(serializers.ModelSerializer):
    equipment_code = serializers.CharField(source='equipment.code', read_only=True)
    equipment_type_name = serializers.CharField(
        source='equipment.equipment_type.name', read_only=True,
    )
    order_no = serializers.CharField(source='order.order_no', read_only=True)
    order_status = serializers.CharField(source='order.status', read_only=True)
    assignee_name = serializers.CharField(source='stage.assignee.username', read_only=True)
    stage_status = serializers.CharField(source='stage.status', read_only=True)


    class Meta:
        model = EquipmentBooking
        fields = [
            'id', 'order', 'order_no', 'order_status', 'stage_status', 'assignee_name',
            'equipment', 'equipment_code', 'equipment_type_name',
            'started_at', 'ended_at',
        ]



class AvailabilityQuerySerializer(serializers.Serializer):
    """Query params for the availability check endpoint."""
    experiment_id = serializers.UUIDField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
