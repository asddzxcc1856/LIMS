from rest_framework import serializers

from .models import ActivityLog, Notification


class ActivityLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, default=None)
    user_role = serializers.CharField(source='user.role', read_only=True, default=None)
    action_type_display = serializers.CharField(source='get_action_type_display', read_only=True)

    class Meta:
        model = ActivityLog
        fields = (
            'id',
            'timestamp',
            'username',
            'user_role',
            'action_type',
            'action_type_display',
            'http_method',
            'path',
            'status_code',
            'ip_address',
            'user_agent',
            'request_data',
            'duration_ms',
            'request_id',
        )
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    related_order_no = serializers.CharField(
        source='related_order.order_no', read_only=True, default=None,
    )
    related_equipment_code = serializers.CharField(
        source='related_equipment.code', read_only=True, default=None,
    )

    class Meta:
        model = Notification
        fields = (
            'id',
            'level', 'level_display',
            'kind', 'kind_display',
            'title', 'body',
            'related_order', 'related_order_no',
            'related_stage',
            'related_equipment', 'related_equipment_code',
            'is_read', 'created_at', 'read_at',
        )
        read_only_fields = fields
