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
from orders.models import Order, OrderStage
from equipments.models import Equipment, ExperimentRequiredEquipment


User = get_user_model()


def _send_notification(user, message):
    """Simulates sending a notification (Email/Socket/Push).

    Accepts either a ``User`` instance or a primary-key string/UUID — callers
    in the relay flow sometimes pass the raw ``request.data['assignee']`` value
    that originated as a UUID string, so this helper resolves it into a User
    rather than relying on every caller to do so.
    """
    if not user:
        print(f"[SYSTEM] Notification skipped: No user provided. Message: {message}")
        return
    if not hasattr(user, 'username'):
        # PK string/UUID — try to resolve once. Bail silently if not found.
        try:
            user = User.objects.filter(pk=user).first()
        except (ValueError, TypeError):
            user = None
        if user is None:
            print(f"[SYSTEM] Notification skipped: user not found. Message: {message}")
            return
    print(f"[NOTIFICATION] User {user.username}: {message}")



# ── Allowed state transitions ──────────────────────────────────────────────
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
    target_department,
    experiment,
    is_urgent=False,
    lot_id='',
    remark='',
) -> Order:
    """Phase 1 — Requester sends the wafer to a specific lab.

    The form is just "where to send it + what experiment to run" — the
    requester does NOT pick equipment. The Experiment row encodes the
    experiment's requirements (which equipment types, in what step order,
    how many units of each) and the lab manager later picks the actual
    units, dates and operators per stage.

    Each Order is one lab visit. When the wafer comes back, the requester
    submits another order to the next lab. No cross-lab auto-relay.

    State transitions on creation:
        Order  → WAITING            (whole order is waiting for the manager)
        Stage  → WAITING (first), PENDING (rest in step_order sequence)
    """
    if not user.department:
        raise ValidationError("User must belong to a department to create orders.")
    if target_department is None:
        raise ValidationError("target_department is required.")
    if experiment is None:
        raise ValidationError("experiment is required so the lab manager has a recipe.")

    requirements = list(
        experiment.required_equipments
        .select_related('equipment_type')
        .order_by('step_order', 'id')
    )
    if not requirements:
        raise ValidationError(
            f"Experiment '{experiment.name}' has no equipment requirements yet — "
            "ask the admin to define them before submitting."
        )

    order = Order.objects.create(
        user=user,
        department=user.department,
        experiment=experiment,
        is_urgent=is_urgent,
        lot_id=lot_id,
        remark=remark,
        status=Order.Status.WAITING,
    )

    # One OrderStage per (equipment_type, step_order) requirement. The first
    # stage opens in WAITING so the lab manager can schedule it immediately;
    # the remaining stages start PENDING and unlock when their predecessor
    # is completed (intra-lab relay).
    for idx, req in enumerate(requirements):
        OrderStage.objects.create(
            order=order,
            step_order=req.step_order or (idx + 1),
            department=target_department,
            equipment_type=req.equipment_type,
            status=(
                OrderStage.Status.WAITING if idx == 0
                else OrderStage.Status.PENDING
            ),
        )

    # Notify the target lab's manager so they pick it up promptly.
    target_manager = target_department.members.filter(role='lab_manager').first()
    _send_notification(
        target_manager,
        f"New sample order for your lab: {order.order_no} "
        f"(experiment: {experiment.name}, "
        f"{len(requirements)} step{'s' if len(requirements) != 1 else ''})",
    )

    return order


def approve_and_schedule_stage(
    stage: OrderStage,
    *,
    schedule_start,
    schedule_end,
    assignee=None,
    equipment=None,
) -> OrderStage:
    """Manager approves a specific stage.

    ``equipment`` is the optional UUID/string of the specific machine the
    manager has picked; when None the scheduler auto-picks the first
    available unit of the required equipment_type in the stage's lab.
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

    # Notify assignee
    if assignee:
        _send_notification(assignee, f"You have been assigned to {stage.order.order_no} Step {stage.step_order}")

    return stage


def complete_stage(stage: OrderStage) -> OrderStage:
    """Member finishes a stage. Relays inside the same lab.

    Each Order = one lab visit, so the relay never crosses departments.
    Within the visit there is one stage per required equipment_type; when
    one stage ends we unlock the next PENDING one. Only when all stages in
    the order are DONE do we mark the order DONE and notify the requester
    to collect their wafer.
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

    # Release equipment booking early
    from scheduling.models import EquipmentBooking
    booking = EquipmentBooking.objects.filter(stage=stage).first()
    if booking:
        booking.ended_at = now
        booking.save()

    if stage.equipment:
        stage.equipment.status = Equipment.Status.AVAILABLE
        stage.equipment.save()

    # Intra-lab relay: open the next PENDING stage within the same order so
    # the manager can schedule it.
    next_stage = (
        OrderStage.objects
        .filter(order=stage.order, status=OrderStage.Status.PENDING)
        .order_by('step_order', 'id')
        .first()
    )
    if next_stage:
        next_stage.status = OrderStage.Status.WAITING
        next_stage.save(update_fields=['status'])
        mgr = next_stage.department.members.filter(role='lab_manager').first()
        if mgr:
            _send_notification(
                mgr,
                f"Order {stage.order.order_no} step {next_stage.step_order} "
                f"({next_stage.equipment_type.name}) is ready to schedule.",
            )
        return stage

    # All stages in this lab visit are done → close the order.
    order = stage.order
    order.status = Order.Status.DONE
    order.ended_at = now
    order.save(update_fields=['status', 'ended_at', 'updated_at'])
    _send_notification(
        order.user,
        f"Wafer for Order {order.order_no} is ready — pick it up and submit "
        "a new request if it needs another lab.",
    )

    return stage



def reject_order(order: Order, *, rejection_reason: str) -> Order:
    """Phase 2 – Lab Manager rejects."""
    _assert_transition(order, Order.Status.REJECTED)
    if not rejection_reason.strip():
        raise ValidationError('rejection_reason is required when rejecting.')
    order.status = Order.Status.REJECTED
    order.rejection_reason = rejection_reason
    order.save(update_fields=['status', 'rejection_reason', 'updated_at'])
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
