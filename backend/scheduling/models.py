import uuid
from django.conf import settings
from django.db import models


class EquipmentBooking(models.Model):
    """Records a specific equipment being occupied by an order for a time range."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='bookings',
    )
    equipment = models.ForeignKey(
        'equipments.Equipment',
        on_delete=models.CASCADE,
        related_name='bookings',
    )
    stage = models.ForeignKey(
        'orders.OrderStage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bookings',
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()

    class Meta:
        db_table = 'equipment_booking'
        indexes = [
            models.Index(fields=['equipment', 'started_at', 'ended_at']),
        ]

    def __str__(self):
        return (
            f'Booking: {self.equipment.code} '
            f'({self.started_at:%Y-%m-%d %H:%M} → {self.ended_at:%Y-%m-%d %H:%M})'
        )


class StageEvent(models.Model):
    """Audit log entry for a single dispatched stage.

    Captures the "上 / 下貨" (load / unload) history that 派貨系統 owes by
    spec: every time a lab member physically loads or unloads a wafer on
    the picked machine, the action lands here with the operator, the
    equipment, the recipe in effect and an optional measurement payload.

    The model deliberately keeps ``measurement`` as a free-form JSON blob
    rather than pinning a schema — recipes from different equipment
    families produce wildly different data (kV / Pa / sccm / Pix etc.),
    and the auto-data-collection (進階需求) story plugs into the same
    table without another migration.
    """

    class EventType(models.TextChoices):
        RECEIVE = 'receive', 'Receive'
        SPLIT = 'split', 'Split'
        DISPATCH = 'dispatch', 'Dispatch'
        SET_PARAMETERS = 'set_parameters', 'Set Parameters'
        ASSIGN = 'assign', 'Assign'
        LOAD = 'load', 'Load'
        UNLOAD = 'unload', 'Unload'
        ABORT = 'abort', 'Abort'
        # NOTE is the catch-all for free-form audit text that doesn't
        # match a workflow milestone (telemetry, ad-hoc comments).
        NOTE = 'note', 'Note'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stage = models.ForeignKey(
        'orders.OrderStage',
        on_delete=models.CASCADE,
        related_name='events',
    )
    equipment = models.ForeignKey(
        'equipments.Equipment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stage_events',
    )
    recipe = models.ForeignKey(
        'equipments.Recipe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stage_events',
    )
    event_type = models.CharField(max_length=16, choices=EventType.choices)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stage_events',
    )
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notes = models.TextField(blank=True, default='')
    measurement = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'stage_event'
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['stage', '-occurred_at']),
            models.Index(fields=['equipment', '-occurred_at']),
            models.Index(fields=['event_type', '-occurred_at']),
        ]

    def __str__(self):
        return (
            f'{self.get_event_type_display()} · '
            f'{self.stage_id} @ {self.occurred_at:%Y-%m-%d %H:%M}'
        )
