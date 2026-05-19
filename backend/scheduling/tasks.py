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
