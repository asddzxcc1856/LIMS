import uuid
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
