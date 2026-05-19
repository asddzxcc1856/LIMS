import uuid

from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    """Records every authenticated API interaction for audit and admin review."""

    class ActionType(models.TextChoices):
        LOGIN = 'login', 'Login'
        LOGOUT = 'logout', 'Logout'
        CREATE = 'create', 'Create'
        READ = 'read', 'Read'
        UPDATE = 'update', 'Update'
        DELETE = 'delete', 'Delete'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
    )
    action_type = models.CharField(
        max_length=16,
        choices=ActionType.choices,
        default=ActionType.OTHER,
        db_index=True,
    )
    http_method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    status_code = models.PositiveSmallIntegerField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default='')
    request_data = models.JSONField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    duration_ms = models.PositiveIntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'activity_log'
        ordering = ('-timestamp',)
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action_type', '-timestamp']),
        ]

    def __str__(self):
        actor = self.user.username if self.user else 'anonymous'
        return f'[{self.timestamp:%Y-%m-%d %H:%M}] {actor} {self.http_method} {self.path}'


class Notification(models.Model):
    """Persistent user-facing alert.

    Replaces the legacy ``_send_notification`` ``print()`` stub with a real
    row per delivery: the bell icon in the SPA pulls these, every channel
    adapter (email, Slack, push) reads the same table.

    ``level`` separates info pings ("樣品已接件") from critical alerts
    ("機台 EQ-001 進入維修") so the UI can colour-code; ``kind`` is a tag
    used by future routing rules (subscribing to certain kinds).
    """

    class Level(models.TextChoices):
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        CRITICAL = 'critical', 'Critical'

    class Kind(models.TextChoices):
        ORDER_RECEIVED = 'order_received', 'Order received'
        ORDER_SIGNED_OFF = 'order_signed_off', 'Order signed off'
        ORDER_SCHEDULED = 'order_scheduled', 'Order scheduled'
        ORDER_REJECTED = 'order_rejected', 'Order rejected'
        ORDER_COMPLETED = 'order_completed', 'Order completed'
        EQUIPMENT_ALERT = 'equipment_alert', 'Equipment alert'
        SYSTEM = 'system', 'System'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    level = models.CharField(
        max_length=10,
        choices=Level.choices,
        default=Level.INFO,
        db_index=True,
    )
    kind = models.CharField(
        max_length=24,
        choices=Kind.choices,
        default=Kind.SYSTEM,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default='')

    # Optional references to the object that triggered the alert. Kept as
    # FKs to avoid stringly-typed lookup hops; on_delete=SET_NULL means a
    # historical alert survives the source row being purged.
    related_order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifications',
    )
    related_stage = models.ForeignKey(
        'orders.OrderStage',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifications',
    )
    related_equipment = models.ForeignKey(
        'equipments.Equipment',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifications',
    )

    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notification'
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
            models.Index(fields=['kind', '-created_at']),
            models.Index(fields=['level', '-created_at']),
        ]

    def __str__(self):
        return f'[{self.get_level_display()}] {self.recipient.username} · {self.title}'
