"""
orders/services.py
Business logic for order creation and state transitions.

State machine (SOP-aligned):
  Created → Waiting       (auto, after field validation)
  Waiting → In Progress   (manager approve + schedule)
  Waiting → Rejected      (manager reject)
  In Progress → Done      (lab member completes)
"""
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model
from orders.models import Approval, Order, OrderStage, Sample
from equipments.models import Equipment, ExperimentRequiredEquipment


User = get_user_model()


def _send_notification(user, message, **kwargs):
    """Persist a Notification row + opt-in side-channel delivery.

    Replaces the original ``print()`` stub: every call now lands in
    ``monitoring.Notification`` so the bell-icon UI, the email channel
    and any future Slack/webhook adapter all read the same source.

    Optional kwargs (``level``, ``kind``, ``related_order``, …) flow
    straight into :func:`monitoring.services.notify`; defaults are tuned
    for the existing call sites that only know "user + message".
    """
    from monitoring.models import Notification
    from monitoring.services import notify

    kwargs.setdefault('level', Notification.Level.INFO)
    kwargs.setdefault('kind', Notification.Kind.SYSTEM)
    notify(user, title=message, body=message, **kwargs)



# ── Allowed state transitions ──────────────────────────────────────────────
def _record_approval(stage: OrderStage, *, actor, decision: str, comment: str = '') -> Approval:
    """Persist an Approval audit row. Append-only — never updates.

    The actor may be a User instance, a UUID, or None (system-driven
    actions such as automated approvals via a future workflow engine
    leave actor NULL).
    """
    actor_obj = actor
    if actor_obj is not None and not hasattr(actor_obj, 'pk'):
        try:
            actor_obj = User.objects.filter(pk=actor_obj).first()
        except (ValueError, TypeError):
            actor_obj = None
    return Approval.objects.create(
        stage=stage,
        actor=actor_obj,
        decision=decision,
        comment=(comment or '').strip(),
    )


def split_order(order: Order, *, splits, operator, parent_sample=None) -> list:
    """Split an order's wafer lot into smaller WIP groups.

    ``splits`` is an iterable of ``{sub_code, wafer_count, notes}`` dicts.
    Each dict becomes a ``Sample`` row pinned to ``order``. When
    ``parent_sample`` is provided the new samples link to it so the
    audit tree shows a re-split rather than the original wafer-lot
    decomposition.

    Validation: ``sub_code`` must be unique per ``order`` (the DB
    constraint catches collisions but we surface a clean error early),
    and ``wafer_count`` must be a positive integer.

    A paired ``StageEvent(note)`` is appended to every IN_PROGRESS stage
    of the order so the load/unload audit shows when the lot was split.
    """
    if not splits:
        raise ValidationError('At least one split entry is required.')

    seen_codes = set()
    cleaned = []
    for entry in splits:
        sub_code = (entry.get('sub_code') or '').strip()
        if not sub_code:
            raise ValidationError('Each split needs a sub_code.')
        if sub_code in seen_codes:
            raise ValidationError(f'Duplicate sub_code "{sub_code}" in payload.')
        seen_codes.add(sub_code)
        try:
            wafer_count = int(entry.get('wafer_count', 1))
        except (TypeError, ValueError):
            raise ValidationError(f'wafer_count for "{sub_code}" must be an integer.')
        if wafer_count < 1:
            raise ValidationError(f'wafer_count for "{sub_code}" must be ≥ 1.')
        cleaned.append({
            'sub_code': sub_code,
            'wafer_count': wafer_count,
            'notes': entry.get('notes', ''),
        })

    existing = set(
        Sample.objects.filter(order=order, sub_code__in=seen_codes)
        .values_list('sub_code', flat=True)
    )
    if existing:
        raise ValidationError(
            f'sub_code already used on this order: {sorted(existing)}'
        )

    created = []
    for entry in cleaned:
        sample = Sample.objects.create(
            order=order,
            sub_code=entry['sub_code'],
            wafer_count=entry['wafer_count'],
            notes=entry['notes'],
            parent_sample=parent_sample,
            created_by=operator if operator and hasattr(operator, 'pk') else None,
        )
        created.append(sample)

    # Best-effort audit trail: drop a note on every active stage so the
    # split shows up alongside load / unload / telemetry events.
    from scheduling.services import record_stage_event
    summary = ', '.join(f'{s.sub_code}×{s.wafer_count}' for s in created)
    for stage in order.stages.filter(status=OrderStage.Status.IN_PROGRESS):
        record_stage_event(
            stage,
            event_type='note',
            operator=operator,
            notes=f'Split into WIP groups: {summary}',
        )

    return created


def receive_stage(stage: OrderStage, *, operator, notes: str = '') -> OrderStage:
    """Mark a stage's sample as physically received by the lab.

    Receive happens *before* approval / scheduling — it represents the
    moment the wafer arrives at the lab counter. The flag is recorded on
    the stage itself (``received_at`` + ``received_by``) and a paired
    ``StageEvent(type=receive)`` row keeps the audit trail consistent
    with the load / unload history.

    Idempotent: receiving a stage twice keeps the original timestamp and
    raises so the caller can surface the duplicate intent.
    """
    if stage.received_at:
        raise ValidationError(
            f'Stage already received at {stage.received_at:%Y-%m-%d %H:%M}.'
        )
    if stage.status not in (OrderStage.Status.WAITING, OrderStage.Status.PENDING):
        raise ValidationError(
            f'Cannot receive a stage in "{stage.get_status_display()}" status.'
        )

    stage.received_at = timezone.now()
    stage.received_by = operator
    stage.save(update_fields=['received_at', 'received_by'])

    from scheduling.services import record_stage_event
    record_stage_event(
        stage,
        event_type='receive',
        operator=operator,
        notes=notes or 'Sample physically received at lab.',
    )

    from monitoring.models import Notification
    _send_notification(
        stage.order.user,
        f'Sample for Order {stage.order.order_no} received by '
        f'{getattr(operator, "username", "lab")}.',
        level=Notification.Level.INFO,
        kind=Notification.Kind.ORDER_RECEIVED,
        related_order=stage.order,
        related_stage=stage,
    )
    return stage


def sign_off_stage(stage: OrderStage, *, actor, comment: str = '') -> Approval:
    """Record a sign-off on a stage without scheduling it yet.

    Separates the "簽核" decision from the operational "排程" step so a
    manager can approve first and let an admin or coordinator fill in the
    schedule later. The stage status stays ``WAITING`` — the dispatch
    panel surfaces "簽核已通過, 等待排程" so the next operator knows the
    sign-off is already cleared.
    """
    if stage.status != OrderStage.Status.WAITING:
        raise ValidationError(
            f'Cannot sign off a stage in "{stage.get_status_display()}" status.'
        )
    approval = _record_approval(
        stage, actor=actor, decision=Approval.Decision.APPROVED, comment=comment,
    )
    if actor is not None:
        from monitoring.models import Notification
        _send_notification(
            stage.order.user,
            f"Order {stage.order.order_no} signed off by "
            f"{getattr(actor, 'username', 'manager')} — awaiting schedule.",
            level=Notification.Level.INFO,
            kind=Notification.Kind.ORDER_SIGNED_OFF,
            related_order=stage.order,
            related_stage=stage,
        )
    return approval


def _attach_recipe(stage: OrderStage, *, recipe_id) -> None:
    """Validate and attach a Recipe to ``stage``.

    Recipe is type-bound: the recipe's ``equipment_type`` must match the
    stage's picked equipment, otherwise the parameters are nonsense for
    that machine. Deactivated recipes are also rejected so retired
    parameter sets don't sneak back into production schedules.
    """
    from equipments.models import Recipe

    try:
        recipe = Recipe.objects.select_related('equipment_type').get(pk=recipe_id)
    except Recipe.DoesNotExist:
        raise ValidationError({'recipe': 'Recipe does not exist.'})

    if not recipe.is_active:
        raise ValidationError({'recipe': 'Recipe is deactivated.'})

    if stage.equipment and recipe.equipment_type_id != stage.equipment.equipment_type_id:
        raise ValidationError({
            'recipe': (
                f"Recipe '{recipe.name}' is for "
                f"{recipe.equipment_type.name}, not "
                f"{stage.equipment.equipment_type.name}."
            ),
        })

    stage.recipe = recipe
    stage.save(update_fields=['recipe'])


_TRANSITIONS = {
    Order.Status.CREATED:     [Order.Status.WAITING],
    Order.Status.WAITING:     [Order.Status.IN_PROGRESS, Order.Status.REJECTED],
    Order.Status.IN_PROGRESS: [Order.Status.DONE],
    Order.Status.DONE:        [],
    Order.Status.REJECTED:    [],
}


def _assert_transition(order: Order, target: str):
    allowed = _TRANSITIONS.get(order.status, [])
    if target not in allowed:
        raise ValidationError(
            f'Cannot transition from "{order.get_status_display()}" '
            f'to "{target}".'
        )


# ── Public API ─────────────────────────────────────────────────────────────

def create_order(
    *,
    user,
    experiment,
    lot=None,
    is_urgent=False,
    requirements='',
    remark='',
) -> Order:
    """Phase 1 — Requester picks an experiment; the order goes to that
    experiment's lab automatically.

    Each Experiment is pinned to one Department, so the requester does not
    pick a lab and never sees a machine. The order has exactly one stage
    at the experiment's lab. The lab manager later picks date / assignee /
    (optionally) machine.
    """
    if not user.department:
        raise ValidationError("User must belong to a department to create orders.")
    if experiment is None:
        raise ValidationError("experiment is required.")
    target_department = experiment.department
    if target_department is None:
        raise ValidationError(
            f"Experiment '{experiment.name}' is not assigned to a lab yet — "
            "ask the admin to set its department before submitting."
        )

    # Order.department is the **routing target** (the lab that will run
    # the experiment) — NOT the requester's home dept. This makes the
    # manager-scoped queries on OrderListView line up with the stage's
    # department, so a manager sees the order and the stage together when
    # they belong to that lab.
    order = Order.objects.create(
        user=user,
        department=target_department,
        experiment=experiment,
        is_urgent=is_urgent,
        lot=lot,
        requirements=requirements,
        remark=remark,
        status=Order.Status.WAITING,
    )

    OrderStage.objects.create(
        order=order,
        step_order=1,
        department=target_department,
        equipment_type=None,
        status=OrderStage.Status.WAITING,
    )

    from monitoring.models import Notification
    target_manager = target_department.members.filter(role='lab_manager').first()
    _send_notification(
        target_manager,
        f"New sample order for your lab: {order.order_no} "
        f"(experiment: {experiment.name})",
        level=Notification.Level.INFO,
        kind=Notification.Kind.ORDER_SIGNED_OFF,
        related_order=order,
    )

    return order


def approve_and_schedule_stage(
    stage: OrderStage,
    *,
    schedule_start,
    schedule_end,
    assignee=None,
    equipment=None,
    recipe=None,
    actor=None,
    comment: str = '',
) -> OrderStage:
    """Manager approves a specific stage.

    ``equipment`` is the optional UUID/string of the specific machine the
    manager has picked; when None the scheduler auto-picks the first
    available unit of the required equipment_type in the stage's lab.

    ``recipe`` is the optional UUID/string of the Recipe to apply on the
    picked machine. A recipe can only be pinned together with a specific
    equipment, and the recipe's ``equipment_type`` must match that
    machine's type — otherwise we reject the request rather than silently
    losing the recipe link.
    """
    if stage.status != OrderStage.Status.WAITING:
        raise ValidationError(f"Cannot approve stage in {stage.status} status.")

    from django.utils.dateparse import parse_datetime
    from django.utils.timezone import is_aware, make_aware

    # Parse into datetime objects if they are strings
    if isinstance(schedule_start, str):
        schedule_start = parse_datetime(schedule_start)
    if isinstance(schedule_end, str):
        schedule_end = parse_datetime(schedule_end)

    if not schedule_start or not schedule_end:
        raise ValidationError('Invalid date format.')

    if not is_aware(schedule_start):
        schedule_start = make_aware(schedule_start)
    if not is_aware(schedule_end):
        schedule_end = make_aware(schedule_end)

    if schedule_start >= schedule_end:
        raise ValidationError('schedule_end must be after schedule_start.')

    now = timezone.now()
    if schedule_start < now:
        raise ValidationError('schedule_start cannot be in the past.')

    if recipe and not equipment:
        raise ValidationError(
            'Pick a machine first — a recipe only makes sense once you have '
            'an equipment to apply it on.'
        )

    stage.schedule_start = schedule_start
    stage.schedule_end = schedule_end
    if assignee:
        stage.assignee_id = assignee  # Handle ID string or object
    stage.status = OrderStage.Status.IN_PROGRESS
    stage.save()

    # Promote the parent order from WAITING → IN_PROGRESS the first time any
    # stage is approved. Subsequent stage approvals are no-ops here because
    # the order is already IN_PROGRESS.
    order = stage.order
    if order.status == Order.Status.WAITING:
        order.status = Order.Status.IN_PROGRESS
        order.save(update_fields=['status', 'updated_at'])

    # Allocate equipment for THIS stage (manager's pick if provided)
    from scheduling.services import allocate_equipments_for_stage
    allocate_equipments_for_stage(stage, equipment_id=equipment)

    if recipe:
        _attach_recipe(stage, recipe_id=recipe)

    # Notify assignee
    if assignee:
        _send_notification(assignee, f"You have been assigned to {stage.order.order_no} Step {stage.step_order}")

    # Append an Approval audit row so the dispatch action is captured
    # alongside any standalone sign-offs the manager recorded earlier.
    _record_approval(
        stage,
        actor=actor,
        decision=Approval.Decision.APPROVED,
        comment=comment or 'Scheduled with approval.',
    )

    return stage


def complete_stage(stage: OrderStage, *, operator=None) -> OrderStage:
    """Member finishes the lab visit. The wafer is ready for pickup.

    Each order is one stage at one lab, so completing the stage closes the
    order and notifies the requester so they can collect the wafer (and
    submit a fresh order to the next lab if their flow needs more steps).

    A guaranteed ``unload`` ``StageEvent`` is appended at the tail so the
    上 / 下貨歷史 always has at least one row per dispatched stage — even
    when the member skipped pressing the explicit "Unload wafer" button.
    """
    if stage.status != OrderStage.Status.IN_PROGRESS:
        raise ValidationError("Only in-progress stages can be completed.")

    if stage.schedule_start and timezone.now() < stage.schedule_start:
        raise ValidationError("Cannot complete a task before its scheduled start time.")

    now = timezone.now()
    stage.status = OrderStage.Status.DONE
    stage.completed_at = now
    stage.schedule_end = now  # release early in stage data
    stage.save()

    from scheduling.models import EquipmentBooking, StageEvent
    from scheduling.services import record_stage_event

    booking = EquipmentBooking.objects.filter(stage=stage).first()
    if booking:
        booking.ended_at = now
        booking.save()

    if stage.equipment:
        stage.equipment.status = Equipment.Status.AVAILABLE
        stage.equipment.save()

    # Auto-append an UNLOAD event when the member didn't already record one
    # via the dedicated endpoint — keeps the audit trail consistent.
    already_unloaded = StageEvent.objects.filter(
        stage=stage, event_type=StageEvent.EventType.UNLOAD,
    ).exists()
    if not already_unloaded:
        record_stage_event(
            stage,
            event_type=StageEvent.EventType.UNLOAD,
            operator=operator,
            notes='auto-recorded by complete_stage',
        )

    order = stage.order
    order.status = Order.Status.DONE
    order.ended_at = now
    order.save(update_fields=['status', 'ended_at', 'updated_at'])
    from monitoring.models import Notification
    _send_notification(
        order.user,
        f"Wafer for Order {order.order_no} is ready — pick it up and submit "
        "a new request if it needs another lab.",
        level=Notification.Level.INFO,
        kind=Notification.Kind.ORDER_COMPLETED,
        related_order=order,
        related_stage=stage,
    )

    return stage



def reject_order(order: Order, *, rejection_reason: str, actor=None) -> Order:
    """Phase 2 – Lab Manager rejects.

    Writes a paired ``Approval(rejected)`` row against every WAITING
    stage on this order so the rejection reason is searchable in the
    audit log.
    """
    _assert_transition(order, Order.Status.REJECTED)
    if not rejection_reason.strip():
        raise ValidationError('rejection_reason is required when rejecting.')
    order.status = Order.Status.REJECTED
    order.rejection_reason = rejection_reason
    order.save(update_fields=['status', 'rejection_reason', 'updated_at'])

    waiting_stages = order.stages.filter(status=OrderStage.Status.WAITING)
    for stage in waiting_stages:
        stage.status = OrderStage.Status.REJECTED
        stage.save(update_fields=['status'])
        _record_approval(
            stage,
            actor=actor,
            decision=Approval.Decision.REJECTED,
            comment=rejection_reason,
        )

    from monitoring.models import Notification
    _send_notification(
        order.user,
        f'Order {order.order_no} was rejected: {rejection_reason}',
        level=Notification.Level.WARNING,
        kind=Notification.Kind.ORDER_REJECTED,
        related_order=order,
    )
    return order


def approve_and_schedule(order: Order, *, schedule_start, schedule_end, assignee=None) -> Order:
    """
    Phase 2-3: Lab Manager approves → picks schedule time →
    system checks conflicts & allocates equipment → status = In Progress.
    Also sets booked equipment status to Occupied and notifies Lab Members.
    """
    _assert_transition(order, Order.Status.IN_PROGRESS)

    if schedule_start >= schedule_end:
        raise ValidationError('schedule_start must be before schedule_end.')

    order.schedule_start = schedule_start
    order.schedule_end = schedule_end
    order.assignee = assignee
    order.save(update_fields=['schedule_start', 'schedule_end', 'assignee', 'updated_at'])

    # Allocate equipment (conflict check + booking creation)
    from scheduling.services import allocate_equipments
    bookings = allocate_equipments(order)

    # Set booked equipment status to Occupied
    booked_eq_ids = [b.equipment_id for b in bookings]
    Equipment.objects.filter(id__in=booked_eq_ids).update(status=Equipment.Status.OCCUPIED)

    order.status = Order.Status.IN_PROGRESS
    order.save(update_fields=['status', 'updated_at'])

    # NOTIFICATION: Notify lab members in the same department
    members_to_notify = User.objects.filter(
        department=order.department,
        role__in=[User.Role.LAB_MEMBER, User.Role.LAB_MANAGER]
    )
    if assignee:
        _send_notification(assignee, f"You have been assigned to Order {order.order_no}.")
    
    msg = f"Experiment for Order {order.order_no} ({order.experiment.name}) is starting."
    for m in members_to_notify:
        if m != assignee:  # Don't notify twice
            _send_notification(m, msg)

    return order


def complete_order(order: Order) -> Order:
    """Phase 4 – Lab Member marks experiment as done.
    Resets booked equipment to Available.
    """
    _assert_transition(order, Order.Status.DONE)
    order.status = Order.Status.DONE
    order.ended_at = timezone.now()
    order.save(update_fields=['status', 'ended_at', 'updated_at'])

    # Reset equipment status to Available
    from scheduling.models import EquipmentBooking
    booked_eq_ids = list(
        EquipmentBooking.objects.filter(order=order).values_list('equipment_id', flat=True)
    )
    if booked_eq_ids:
        Equipment.objects.filter(id__in=booked_eq_ids).update(status=Equipment.Status.AVAILABLE)

    # NOTIFICATION: Notify requester
    _send_notification(order.user, f"Your experiment for Order {order.order_no} is completed.")

    return order
