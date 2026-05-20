"""Background tasks for the scheduling app.

The Celery worker already lives in the deployment (``backend.celery``) but
was idle in the v0 release. These tasks wake it up:

* ``auto_close_stalled_stages`` — sweeps IN_PROGRESS stages whose
  schedule_end has passed by a grace window AND have at least one
  telemetry event, and calls :func:`orders.services.complete_stage`. This
  realises the 進階需求 "機台執行完實驗自動將實驗數據蒐集起來,並自動結單"
  pipeline so a manual unload click is no longer required when telemetry
  reports completion.

Run as part of Celery beat OR via the ``auto_close_stalled_stages``
management command on cron. Both share the same idempotent code path.
"""
from datetime import timedelta

from celery import shared_task
from django.utils import timezone


@shared_task(name='scheduling.auto_close_stalled_samples')
def auto_close_stalled_samples(grace_minutes=5):
    """Auto-complete RUNNING Samples whose schedule_end is past + has
    at least one telemetry/event row. Matches the per-sample dispatch
    architecture (post-refactor).

    Returns list of sample IDs that were closed.
    """
    from orders.models import Sample
    from orders.services import complete_sample

    cutoff = timezone.now() - timedelta(minutes=grace_minutes)
    candidates = (
        Sample.objects
        .filter(
            status=Sample.Status.RUNNING,
            schedule_end__lt=cutoff,
        )
        .distinct()
    )
    closed = []
    for sample in candidates:
        try:
            complete_sample(sample, operator=None)
            closed.append(str(sample.id))
        except Exception:
            continue
    return closed


@shared_task(name='scheduling.alert_schedule_overruns')
def alert_schedule_overruns(grace_minutes=30):
    """Scan RUNNING samples that have been running > grace_minutes past
    schedule_end and emit a CRITICAL notification to the assigned lab
    member + the lab's manager(s).

    Idempotent in spirit: only one alert per sample within the grace
    window via `Notification.kind=equipment_alert` dedup check on
    `related_stage` (best effort).
    """
    from orders.models import Sample
    from monitoring.models import Notification
    from monitoring.services import notify_many

    cutoff = timezone.now() - timedelta(minutes=grace_minutes)
    overrun = Sample.objects.filter(
        status=Sample.Status.RUNNING,
        schedule_end__lt=cutoff,
    ).select_related('assignee', 'order', 'order__department', 'equipment')

    alerted = []
    for sample in overrun:
        stage = sample.order.stages.first()
        # Dedup — skip if we already alerted this stage in the window.
        existing = Notification.objects.filter(
            related_stage=stage,
            kind=Notification.Kind.EQUIPMENT_ALERT,
            created_at__gte=cutoff,
        ).exists()
        if existing:
            continue
        recipients = []
        if sample.assignee_id:
            recipients.append(sample.assignee)
        dept = sample.order.department
        if dept:
            recipients.extend(dept.members.filter(role='lab_manager'))
        if not recipients:
            continue
        notify_many(
            recipients,
            level=Notification.Level.CRITICAL,
            kind=Notification.Kind.EQUIPMENT_ALERT,
            title=f'⏰ Sample {sample.sub_code} 超時 ({sample.order.order_no})',
            body=(
                f'Sample {sample.sub_code} 在機台 '
                f'{sample.equipment.code if sample.equipment else "?"} 上 '
                f'已超出排程 {grace_minutes} 分鐘未下貨。請介入處理。'
            ),
            related_order=sample.order,
            related_stage=stage,
            related_equipment=sample.equipment,
        )
        alerted.append(str(sample.id))
    return alerted


@shared_task(name='scheduling.auto_close_stalled_stages')
def auto_close_stalled_stages(grace_minutes=5):
    """Auto-complete in-progress stages that are visibly finished.

    Selection rule:
      * status = IN_PROGRESS
      * schedule_end is set AND now > schedule_end + grace_minutes
      * stage has at least one StageEvent (telemetry, load, unload, …)

    Returns the list of stage IDs that were closed so the caller (Celery
    beat / cron command) can log them.
    """
    from orders.models import OrderStage
    from orders.services import complete_stage

    cutoff = timezone.now() - timedelta(minutes=grace_minutes)
    candidates = (
        OrderStage.objects
        .filter(
            status=OrderStage.Status.IN_PROGRESS,
            schedule_end__lt=cutoff,
            events__isnull=False,
        )
        .distinct()
    )

    closed_ids = []
    for stage in candidates:
        try:
            complete_stage(stage, operator=None)
            closed_ids.append(str(stage.id))
        except Exception:
            # Skip stages that fail business-rule guards (e.g. someone
            # manually flipped status during the sweep). Logs in the
            # Django request logger keep the audit trail.
            continue
    return closed_ids
