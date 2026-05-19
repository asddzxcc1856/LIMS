"""Equipment domain signals → notification pipeline.

Captures abnormal status transitions (``available`` → ``maintenance`` or
``pending``) on :class:`equipments.models.Equipment` and broadcasts an
``equipment_alert`` notification to every lab_manager in the owning
department. Mirrors what the spec calls the "報警系統": "機台狀態異常
的時候,可以發出通知,通知相對應的人員介入處理."

We use ``pre_save`` (not ``post_save``) so we have access to the *old*
status, then act in ``post_save`` to keep the row written first.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from monitoring.models import Notification
from monitoring.services import notify_many

from .models import Equipment


_ALERT_STATUSES = {Equipment.Status.MAINTENANCE, Equipment.Status.PENDING}


@receiver(pre_save, sender=Equipment)
def _capture_previous_status(sender, instance, **kwargs):
    """Stash the pre-save status on the instance so post_save can compare.

    Skips fresh inserts where there's no previous state to compare against.
    """
    if not instance.pk:
        instance._previous_status = None
        return
    try:
        previous = Equipment.objects.only('status').get(pk=instance.pk)
        instance._previous_status = previous.status
    except Equipment.DoesNotExist:
        instance._previous_status = None


@receiver(post_save, sender=Equipment)
def _alert_on_status_change(sender, instance, created, **kwargs):
    if created:
        return
    previous = getattr(instance, '_previous_status', None)
    if previous == instance.status:
        return  # unrelated update (code, type, …)

    moved_to_alert = (
        instance.status in _ALERT_STATUSES
        and previous not in _ALERT_STATUSES
    )
    if not moved_to_alert:
        return

    # Fan out to every lab manager of the equipment's department.
    if instance.department_id is None:
        return
    managers = instance.department.members.filter(role='lab_manager')
    title = f'機台 {instance.code} 進入 {instance.get_status_display()} 狀態'
    body = (
        f'設備 {instance.code} ({instance.equipment_type.name}) 在 '
        f'{instance.department.name} 從 {previous} 轉為 {instance.status}。'
    )
    notify_many(
        managers,
        level=Notification.Level.CRITICAL,
        kind=Notification.Kind.EQUIPMENT_ALERT,
        title=title,
        body=body,
        related_equipment=instance,
    )
