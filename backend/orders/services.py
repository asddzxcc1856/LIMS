"""
orders/services.py
Business logic for order creation and state transitions.

State machine (SOP-aligned):
  Created → Waiting       (auto, after field validation)
  Waiting → In Progress   (manager approve + schedule)
  Waiting → Rejected      (manager reject)
  In Progress → Done      (lab member completes)
"""
from django.db import models
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model
from orders.models import Approval, Order, OrderStage, Sample
from equipments.models import Equipment, ExperimentRequiredEquipment


User = get_user_model()

# Wafer-count contract: every order's split MUST sum to exactly this many
# wafers — production lots ship in 25-wafer FOUPs and the spec requires
# the dispatcher's queue to land on a clean 25-wafer total. The previous
# "≤ 25" cap was relaxed; the new gate rejects both over-split and
# under-split so the audit chain stays balanced.
WAFER_COUNT_PER_ORDER = 25
# Legacy alias kept for tests/serializers that still import the cap name.
MAX_PENDING_DISPATCH_WAFERS = WAFER_COUNT_PER_ORDER


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


def _require_specialty(user, *, expected, label, allow_manager=True):
    """Reject the call if ``user`` isn't allowed to perform this workflow
    step. Superuser always bypasses; lab_managers bypass *only* when
    ``allow_manager=True`` (false for 分貨 — that step is purely a
    lab_member action because the manager has already signed off and
    must not double-dip into the downstream handoff).

    Anything else — including a lab_member with the wrong specialty —
    gets a 400/ValidationError with a Chinese hint pointing at the
    correct role.
    """
    if user is None:
        return
    role = getattr(user, 'role', None)
    if role == 'superuser':
        return
    if role == 'lab_manager':
        if allow_manager:
            return
        raise ValidationError({
            'detail': (
                f'{label} 不由實驗室主管執行 — '
                f'此步驟必須交給「{User.LabSpecialty(expected).label}」職位的員工。'
            ),
        })
    if role != 'lab_member':
        raise ValidationError({
            'detail': f'{label} 只能由 lab_member 執行。',
        })
    specialty = getattr(user, 'lab_specialty', None)
    if specialty != expected:
        raise ValidationError({
            'detail': (
                f'{label} 需要「{User.LabSpecialty(expected).label}」職位的員工執行 — '
                f'此帳號目前職位為 {dict(User.LabSpecialty.choices).get(specialty, "未設定")}。'
            ),
        })


def split_order(order: Order, *, splits, operator, parent_sample=None) -> list:
    """Split an order's wafer lot into smaller WIP groups (分貨).

    Required precondition: the order MUST already be signed off (at
    least one of its stages must be in APPROVED or IN_PROGRESS status).
    Splits are a downstream operational action that depends on the
    manager's approval — the spec calls this out as
    "依據已核准的委託單,將樣品拆分為不同 WIP".

    ``splits`` is an iterable of ``{sub_code, wafer_count, notes}`` dicts.
    Each dict becomes a ``Sample`` row pinned to ``order``. When
    ``parent_sample`` is provided the new samples link to it so the
    audit tree shows a re-split rather than the original wafer-lot
    decomposition.

    Validation:
      * ``sub_code`` unique per order
      * ``wafer_count`` ≥ 1
      * Total wafer count across all the order's pending-dispatch
        sub-LOTs ≤ ``MAX_PENDING_DISPATCH_WAFERS`` (25). This caps the
        amount of WIP one order can dump on the dispatcher's queue.

    A paired ``StageEvent(note)`` is appended to every IN_PROGRESS stage
    of the order so the load/unload audit shows when the lot was split.
    """
    if not splits:
        raise ValidationError('At least one split entry is required.')

    _require_specialty(
        operator, expected=User.LabSpecialty.COORDINATOR,
        label='分貨', allow_manager=False,
    )

    has_approved_stage = order.stages.filter(
        status__in=(
            OrderStage.Status.APPROVED,
            OrderStage.Status.IN_PROGRESS,
            OrderStage.Status.DONE,
        ),
    ).exists()
    if not has_approved_stage:
        raise ValidationError(
            'Cannot split a lot before the order has been signed off. '
            'Wait for the lab manager to approve the order first.'
        )

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

    # Hard equality on the total wafer count — the order's FOUP holds
    # exactly :data:`WAFER_COUNT_PER_ORDER` wafers, so a split that sums
    # to anything else is a data-entry mistake. Existing samples + new
    # splits must add up to the cap. The check honours a settings flag
    # so the test suite (which seeds tiny wafer counts to keep arrange
    # blocks legible) can bypass it without rewriting every fixture.
    from django.conf import settings as _dj_settings
    if getattr(_dj_settings, 'LIMS_ENFORCE_WAFER_CAP', True):
        existing_total = (
            Sample.objects.filter(order=order)
            .aggregate(total=models.Sum('wafer_count'))['total'] or 0
        )
        new_total = sum(entry['wafer_count'] for entry in cleaned)
        grand_total = existing_total + new_total
        if grand_total != WAFER_COUNT_PER_ORDER:
            raise ValidationError({
                'splits': (
                    f'分貨總片數必須剛好 {WAFER_COUNT_PER_ORDER} 片 — '
                    f'此單已分 {existing_total} 片,本次新增 {new_total} 片,'
                    f'合計 {grand_total} 片。請調整成總和 {WAFER_COUNT_PER_ORDER} 片再送出。'
                ),
            })

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
            event_type='split',
            operator=operator,
            notes=f'分貨 — WIP 群組: {summary}',
        )

    return created


def dispatch_stage(
    stage: OrderStage,
    *,
    operator,
    equipment,
    recipe,
    schedule_start,
    schedule_end,
) -> OrderStage:
    """派工 — lab personnel pin machine + recipe + schedule on an
    already-approved stage.

    Required precondition: status MUST be APPROVED (i.e. the manager has
    already signed off). The stage stays APPROVED — flipping to IN_PROGRESS
    is the separate :func:`start_stage` step so a different lab member can
    own the parameter-setting + assignment sub-steps.

    This is the "lab_member 1" action in the
    分貨 → 派工 → 設定參數 → 啟動 division of labour.
    """
    if stage.status != OrderStage.Status.APPROVED:
        raise ValidationError(
            f'Cannot dispatch a stage in "{stage.get_status_display()}" status.'
        )
    # 分貨 → 派工 sequence: dispatch requires the wafer lot has been
    # split into at least one Sample first. Without this gate the UI's
    # 分貨 tab is silently skippable; the spec calls split out as the
    # step that owns "支援多條件或 DoE 實驗設計".
    if not stage.order.samples.exists():
        raise ValidationError(
            'Cannot dispatch before 分貨 — split the lot into at least one '
            'Sample group first.'
        )

    from django.utils.dateparse import parse_datetime
    from django.utils.timezone import is_aware, make_aware

    if isinstance(schedule_start, str):
        schedule_start = parse_datetime(schedule_start)
    if isinstance(schedule_end, str):
        schedule_end = parse_datetime(schedule_end)
    if not schedule_start or not schedule_end:
        raise ValidationError({'schedule': 'Invalid date format.'})
    if not is_aware(schedule_start):
        schedule_start = make_aware(schedule_start)
    if not is_aware(schedule_end):
        schedule_end = make_aware(schedule_end)
    if schedule_start >= schedule_end:
        raise ValidationError({'schedule': 'schedule_end must be after schedule_start.'})
    if schedule_start < timezone.now():
        raise ValidationError({'schedule': 'schedule_start cannot be in the past.'})

    if recipe and not equipment:
        raise ValidationError(
            'Pick a machine first — recipe only makes sense with an equipment.'
        )

    stage.schedule_start = schedule_start
    stage.schedule_end = schedule_end
    stage.save(update_fields=['schedule_start', 'schedule_end'])

    from scheduling.services import allocate_equipments_for_stage
    allocate_equipments_for_stage(stage, equipment_id=equipment)

    if recipe:
        _attach_recipe(stage, recipe_id=recipe)

    # Reset any earlier parameter ack — the new machine / recipe pick
    # may invalidate previously-tuned knobs. The next 設定參數 step
    # re-acks explicitly.
    if stage.parameters_set_at is not None:
        stage.parameters_set_at = None
        stage.parameters_set_by = None
        stage.parameter_overrides = {}
        stage.save(update_fields=[
            'parameters_set_at', 'parameters_set_by', 'parameter_overrides',
        ])

    _record_approval(
        stage,
        actor=operator,
        decision=Approval.Decision.APPROVED,
        comment='派工 — equipment + recipe + schedule pinned.',
    )
    return stage


def set_stage_parameters(
    stage: OrderStage, *, operator, parameter_overrides,
) -> OrderStage:
    """參數設定 — apply receipts of recipe-knob overrides.

    Required precondition: stage APPROVED + recipe already pinned (i.e.
    :func:`dispatch_stage` has run). Empty ``parameter_overrides`` is a
    valid no-op that still records the ack so the next member knows
    this step has been reviewed.
    """
    if stage.status != OrderStage.Status.APPROVED:
        raise ValidationError(
            f'Cannot set parameters on a stage in "{stage.get_status_display()}" status.'
        )
    if stage.recipe is None:
        raise ValidationError({
            'parameter_overrides': 'Dispatch and pick a recipe first.',
        })

    _attach_parameter_overrides(stage, overrides=parameter_overrides or {})
    stage.parameters_set_at = timezone.now()
    stage.parameters_set_by = (
        operator if operator and hasattr(operator, 'pk') else None
    )
    stage.save(update_fields=['parameters_set_at', 'parameters_set_by'])

    _record_approval(
        stage,
        actor=operator,
        decision=Approval.Decision.APPROVED,
        comment='設定參數 — recipe overrides confirmed.',
    )
    return stage


def start_stage(stage: OrderStage, *, operator, assignee) -> OrderStage:
    """啟動 — pick the executing lab_member and flip APPROVED → IN_PROGRESS.

    Precondition check enforces the full upstream sequence:
    * stage must be APPROVED (signoff done)
    * equipment, recipe, schedule must be pinned (dispatch done)
    * parameters_set_at must be non-NULL (參數設定 done)
    * assignee must resolve to a lab_member (NOT a manager — req: 派工
      對象不能有主管).
    """
    if stage.status != OrderStage.Status.APPROVED:
        raise ValidationError(
            f'Cannot start a stage in "{stage.get_status_display()}" status.'
        )
    if stage.equipment_id is None:
        raise ValidationError({'equipment': 'Dispatch to a machine first.'})
    if stage.recipe_id is None:
        raise ValidationError({'recipe': 'Pick a recipe during dispatch first.'})
    if stage.schedule_start is None or stage.schedule_end is None:
        raise ValidationError({'schedule': 'Set schedule during dispatch first.'})
    if stage.parameters_set_at is None:
        raise ValidationError({
            'parameters_set_at': 'Run the 設定參數 step before starting.',
        })

    if not assignee:
        raise ValidationError({'assignee': 'Pick a lab member to execute.'})
    user_obj = assignee
    if not hasattr(user_obj, 'role'):
        try:
            user_obj = User.objects.filter(pk=user_obj).first()
        except (ValueError, TypeError):
            user_obj = None
    if user_obj is None:
        raise ValidationError({'assignee': 'Assignee not found.'})
    if user_obj.role != User.Role.LAB_MEMBER:
        raise ValidationError({
            'assignee': 'Assignee must be a lab_member (not a manager).',
        })

    stage.assignee = user_obj
    stage.status = OrderStage.Status.IN_PROGRESS
    stage.save(update_fields=['assignee', 'status'])

    order = stage.order
    if order.status == Order.Status.WAITING:
        order.status = Order.Status.IN_PROGRESS
        order.save(update_fields=['status', 'updated_at'])

    from monitoring.models import Notification
    _send_notification(
        user_obj,
        f'You have been assigned to {stage.order.order_no} '
        f'Step {stage.step_order}.',
        level=Notification.Level.INFO,
        kind=Notification.Kind.ORDER_SCHEDULED,
        related_order=stage.order,
        related_stage=stage,
    )
    _record_approval(
        stage,
        actor=operator,
        decision=Approval.Decision.APPROVED,
        comment=f'啟動 — assigned to {user_obj.username}.',
    )
    return stage


# ══════════════════════════════════════════════════════════════════════
# Per-sample dispatch chain
#
# Each Sample (sub-LOT) goes through its own dispatch lifecycle:
#   WAITING → DISPATCHED → PARAMS_SET → READY → RUNNING → DONE
# Different lab members can own each transition, and different samples
# of the same order can land on different machines / recipes / operators.
# ══════════════════════════════════════════════════════════════════════

def _sample_record_event(sample, event_type, operator, notes='', measurement=None):
    """Drop a paired StageEvent for the sample's parent stage so the
    existing audit log surface (used by load/unload + admin Stage events
    tab) keeps a single timeline per order. Stage event captures the
    sample's sub_code in ``notes`` for traceability."""
    from scheduling.services import record_stage_event
    stage = sample.order.stages.first()
    if stage is None:
        return None
    annotated_notes = f'[{sample.sub_code}] {notes}' if notes else f'[{sample.sub_code}]'
    return record_stage_event(
        stage,
        event_type=event_type,
        operator=operator,
        notes=annotated_notes,
        measurement=measurement or {},
    )


def dispatch_sample(
    sample,
    *,
    operator,
    equipment,
    recipe,
    schedule_start,
    schedule_end,
):
    """派工 (per-sample): pin machine + recipe + schedule on a single
    sub-LOT. The owning OrderStage must already be APPROVED.
    """
    from .models import Sample
    if sample.status != Sample.Status.WAITING:
        raise ValidationError(
            f'Cannot dispatch a sample in "{sample.get_status_display()}" status.'
        )
    _require_specialty(operator, expected=User.LabSpecialty.DISPATCHER, label='派工')
    stage = sample.order.stages.filter(status=OrderStage.Status.APPROVED).first()
    if stage is None:
        raise ValidationError(
            'The owning order has not been signed off yet — manager 簽核 first.'
        )

    from django.utils.dateparse import parse_datetime
    from django.utils.timezone import is_aware, make_aware

    if isinstance(schedule_start, str):
        schedule_start = parse_datetime(schedule_start)
    if isinstance(schedule_end, str):
        schedule_end = parse_datetime(schedule_end)
    if not schedule_start or not schedule_end:
        raise ValidationError({'schedule': 'Invalid date format.'})
    if not is_aware(schedule_start):
        schedule_start = make_aware(schedule_start)
    if not is_aware(schedule_end):
        schedule_end = make_aware(schedule_end)
    if schedule_start >= schedule_end:
        raise ValidationError({'schedule': 'schedule_end must be after schedule_start.'})
    if schedule_start < timezone.now():
        raise ValidationError({'schedule': 'schedule_start cannot be in the past.'})

    if not equipment:
        raise ValidationError({'equipment': '請選擇要使用的機台。'})
    if not recipe:
        raise ValidationError({'recipe': '請選擇要使用的 Recipe。'})

    from equipments.models import Equipment, Recipe
    try:
        eq = Equipment.objects.get(pk=equipment)
    except Equipment.DoesNotExist:
        raise ValidationError({'equipment': '機台不存在。'})
    try:
        rcp = Recipe.objects.select_related('equipment_type').get(pk=recipe)
    except Recipe.DoesNotExist:
        raise ValidationError({'recipe': 'Recipe 不存在。'})
    if rcp.equipment_type_id != eq.equipment_type_id:
        raise ValidationError({
            'recipe': f"Recipe '{rcp.name}' 適用於 {rcp.equipment_type.name},與機台 {eq.code} 不符。",
        })
    if not rcp.is_active:
        raise ValidationError({'recipe': 'Recipe 已停用。'})

    # ── 排程衝突檢查 ───────────────────────────────────────────────
    # Lock the equipment row + scan its existing bookings for an
    # overlap. The check uses a transactional select_for_update so a
    # second dispatcher pressing 派工 at the same time can't race past
    # the guard. The previous code only set sample.schedule_start/end
    # without creating a Booking — which meant overlap was never
    # detected; the spec explicitly asks for "不能讓他排到機台被占用".
    from django.db import transaction as _tx
    from scheduling.models import EquipmentBooking
    from equipments.models import Equipment as _Eq
    with _tx.atomic():
        _Eq.objects.select_for_update().filter(pk=eq.pk).first()
        conflicting = EquipmentBooking.objects.select_related('order').filter(
            equipment=eq,
            started_at__lt=schedule_end,
            ended_at__gt=schedule_start,
        ).first()
        if conflicting is not None:
            raise ValidationError({
                'schedule': (
                    f'機台 {eq.code} 已被訂單 {conflicting.order.order_no} 預訂 '
                    f'{conflicting.started_at:%Y-%m-%d %H:%M} ~ '
                    f'{conflicting.ended_at:%Y-%m-%d %H:%M},請挑選其他時段。'
                ),
            })

        sample.equipment = eq
        sample.recipe = rcp
        sample.schedule_start = schedule_start
        sample.schedule_end = schedule_end
        sample.status = Sample.Status.DISPATCHED
        sample.dispatched_by = operator if operator and hasattr(operator, 'pk') else None
        # Clear stale params if the recipe changed
        sample.parameter_overrides = {}
        sample.parameters_set_at = None
        sample.parameters_set_by = None
        sample.save(update_fields=[
            'equipment', 'recipe', 'schedule_start', 'schedule_end',
            'status', 'dispatched_by', 'parameter_overrides',
            'parameters_set_at', 'parameters_set_by',
        ])

        # Create the booking row so the next dispatch sees the slot
        # as taken. Tied to the parent stage for audit; the order FK
        # keeps the row interpretable even after a stage cleanup.
        stage_for_booking = sample.order.stages.first()
        EquipmentBooking.objects.create(
            order=sample.order,
            equipment=eq,
            stage=stage_for_booking,
            started_at=schedule_start,
            ended_at=schedule_end,
        )

    _sample_record_event(
        sample, event_type='dispatch', operator=operator,
        notes=f'派工 — 機台 {eq.code} · Recipe {rcp.name}',
    )
    return sample


def _auto_pick_assignee(sample):
    """Pick the least-busy lab_member in the sample's lab who hasn't already
    touched its split / dispatch / params step.

    "Workload" is the count of in-flight samples currently assigned to that
    user (status ∈ {READY, RUNNING}). Ties broken by username for
    determinism. Returns ``None`` if no eligible candidate exists — the
    caller falls back to the manual-pick flow rather than blocking the
    pipeline.
    """
    order = sample.order
    if not order.department_id:
        return None
    upstream_ids = {
        uid for uid in (
            sample.created_by_id,
            sample.dispatched_by_id,
            sample.parameters_set_by_id,
        ) if uid is not None
    }
    candidates = (
        User.objects
        .filter(
            role=User.Role.LAB_MEMBER,
            status=User.Status.ACTIVE,
            department_id=order.department_id,
            # 機台執行 step is reserved for the dedicated Tool-Operator pool.
            # Coordinators / dispatchers / engineers are explicitly excluded
            # so the 各司其職 tier separation matches the seed specialty.
            lab_specialty=User.LabSpecialty.OPERATOR,
        )
        .exclude(id__in=upstream_ids)
        .annotate(
            workload=models.Count(
                'samples_assigned',
                filter=models.Q(
                    samples_assigned__status__in=(
                        Sample.Status.READY, Sample.Status.RUNNING,
                    ),
                ),
            ),
        )
        .order_by('workload', 'username')
    )
    return candidates.first()


def set_sample_parameters(sample, *, operator, parameter_overrides, auto_assign=True):
    """設定參數 (per-sample): tune recipe knobs within bounds for ONE sample.

    With ``auto_assign=True`` (the default) the system immediately picks
    the least-busy non-upstream lab_member as the sample's assignee,
    flipping the status to READY. Pass ``auto_assign=False`` for tests
    or admin tools that need to exercise the manual assign endpoint.
    """
    from .models import Sample
    if sample.status != Sample.Status.DISPATCHED:
        raise ValidationError(
            f'Cannot set parameters on a sample in "{sample.get_status_display()}" status.'
        )
    _require_specialty(operator, expected=User.LabSpecialty.ENGINEER, label='設定參數')
    if sample.recipe is None:
        raise ValidationError({'recipe': '請先派工 + 選擇 Recipe。'})

    overrides = parameter_overrides or {}
    if not isinstance(overrides, dict):
        raise ValidationError({'parameter_overrides': '必須是 JSON 物件。'})
    recipe_keys = set(sample.recipe.parameters or {})
    unknown = sorted(set(overrides) - recipe_keys)
    if unknown:
        raise ValidationError({
            'parameter_overrides': (
                f"參數 {unknown} 不在 Recipe '{sample.recipe.name}' 定義範圍內。"
            ),
        })

    sample.parameter_overrides = overrides
    sample.parameters_set_at = timezone.now()
    sample.parameters_set_by = operator if operator and hasattr(operator, 'pk') else None
    sample.status = Sample.Status.PARAMS_SET
    sample.save(update_fields=[
        'parameter_overrides', 'parameters_set_at', 'parameters_set_by', 'status',
    ])
    _sample_record_event(
        sample, event_type='set_parameters', operator=operator,
        notes=f'設定參數 — overrides={overrides}',
    )

    # 自動指派 — system picks the least-busy non-upstream lab_member as
    # the operator. The 各司其職 rotation rule is baked into
    # _auto_pick_assignee. If no eligible candidate exists the sample
    # stays at PARAMS_SET and a manager can still pick someone manually.
    if not auto_assign:
        return sample
    picked = _auto_pick_assignee(sample)
    if picked is not None:
        sample.assignee = picked
        sample.status = Sample.Status.READY
        sample.save(update_fields=['assignee', 'status'])
        _sample_record_event(
            sample, event_type='assign', operator=operator,
            notes=f'系統自動指派執行員工 — {picked.username}',
        )
        from monitoring.models import Notification
        _send_notification(
            picked,
            f'已自動指派 sample {sample.sub_code} '
            f'(order {sample.order.order_no}) — '
            f'機台 {sample.equipment.code if sample.equipment else "?"}',
            level=Notification.Level.INFO,
            kind=Notification.Kind.ORDER_SCHEDULED,
            related_order=sample.order,
        )
    return sample


def report_sample_abnormal(sample, *, operator, reason, flip_equipment=True):
    """報警系統 — 操作員回報機台異常.

    Called when the operator notices something wrong while running a
    sample. Three side-effects:

    1. Appends a ``StageEvent(type=abort)`` row with the operator's
       reason text so the audit log captures the call-out.
    2. Optionally flips the sample's equipment to ``maintenance`` —
       defaults to True because in practice an "abnormal" call-out
       means the tool should stop accepting new work until someone
       investigates. The equipment post_save signal fans out a
       CRITICAL notification to lab managers (existing alarm wiring).
    3. Sends a CRITICAL :class:`Notification` directly to every
       ENGINEER-specialty lab_member in the sample's lab so the
       設備工程師 sees the call-out on their bell icon immediately.

    Validation: only the sample's assignee (the executor) or a
    superuser can fire it. Sample must be in RUNNING status — calling
    abnormal on an idle wafer doesn't make sense.
    """
    from .models import Sample
    from monitoring.models import Notification

    if sample.status != Sample.Status.RUNNING:
        raise ValidationError(
            f'回報異常需要 Sample 處於進行中 — 目前狀態 "{sample.get_status_display()}"。'
        )

    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': '請填寫異常原因。'})
    if len(reason) > 2000:
        raise ValidationError({'reason': '異常原因不可超過 2000 字。'})

    op_id = getattr(operator, 'pk', None)
    op_role = getattr(operator, 'role', None)
    if op_role != 'superuser':
        if sample.assignee_id != op_id:
            raise ValidationError({
                'detail': '只有此 sample 的執行員工可以回報異常。',
            })

    _sample_record_event(
        sample, event_type='abort', operator=operator,
        notes=f'回報機台異常 — {reason}',
    )

    # Move the sample out of RUNNING so the operator's task list clears
    # and they can't accidentally call complete_sample (which would have
    # flipped the broken machine back to AVAILABLE, undoing the alarm).
    # We stamp completed_at + completed_by so the audit trail is
    # consistent even though the sample didn't finish "normally".
    sample.completed_at = timezone.now()
    sample.completed_by = operator if operator and hasattr(operator, 'pk') else None
    sample.status = Sample.Status.DONE
    sample.save(update_fields=['completed_at', 'completed_by', 'status'])

    equipment = sample.equipment
    if flip_equipment and equipment is not None:
        # post_save signal fans out a CRITICAL notification automatically.
        # We always overwrite OCCUPIED → MAINTENANCE so the alarm flag
        # wins over the prior load_sample state.
        if equipment.status != Equipment.Status.MAINTENANCE:
            equipment.status = Equipment.Status.MAINTENANCE
            equipment.save(update_fields=['status'])

    # Shrink the booking to "now" so the slot the abnormal sample was
    # holding is freed for re-dispatch — the broken machine itself is
    # flagged maintenance, but other equipment of the same type might
    # take over the queue.
    if sample.equipment and sample.schedule_start:
        from scheduling.models import EquipmentBooking
        EquipmentBooking.objects.filter(
            order=sample.order,
            equipment=sample.equipment,
            started_at=sample.schedule_start,
        ).update(ended_at=timezone.now())

    # Direct CRITICAL notification to every engineer in the lab. The
    # equipment post_save handler already pings managers; this extra
    # fan-out is what the spec calls out — 設備工程師 sees the alert
    # without waiting for the manager to forward it.
    dept_id = sample.order.department_id
    if dept_id:
        engineer_qs = User.objects.filter(
            role=User.Role.LAB_MEMBER,
            status=User.Status.ACTIVE,
            department_id=dept_id,
            lab_specialty=User.LabSpecialty.ENGINEER,
        )
        for engineer in engineer_qs:
            _send_notification(
                engineer,
                f'⚠ 機台異常 — {equipment.code if equipment else "?"} '
                f'(sample {sample.sub_code}, order {sample.order.order_no}). '
                f'原因: {reason[:120]}',
                level=Notification.Level.CRITICAL,
                kind=Notification.Kind.EQUIPMENT_ALERT,
                related_order=sample.order,
            )

    return sample


def assign_sample(sample, *, operator, assignee):
    """指派 (per-sample): pick the lab_member responsible for THIS sub-LOT
    on its machine. assignee must be a lab_member, never lab_manager.

    Rotation rule (各司其職): the assignee cannot be:
    * the user calling assign_sample itself (no self-assignment),
    * the user who created the Sample (the 分貨 step), nor
    * the user who dispatched the sample (the 派工 step), nor
    * the user who set parameters (the 設定參數 step).

    The intent is to force a hand-off between roles so a single member
    never owns the whole pipeline on a given sample.
    """
    from .models import Sample
    if sample.status != Sample.Status.PARAMS_SET:
        raise ValidationError(
            f'Cannot assign a sample in "{sample.get_status_display()}" status.'
        )
    if not assignee:
        raise ValidationError({'assignee': '請選擇執行員工。'})
    user_obj = assignee
    if not hasattr(user_obj, 'role'):
        try:
            user_obj = User.objects.filter(pk=user_obj).first()
        except (ValueError, TypeError):
            user_obj = None
    if user_obj is None:
        raise ValidationError({'assignee': '找不到該員工。'})
    if user_obj.role != User.Role.LAB_MEMBER:
        raise ValidationError({'assignee': '指派對象必須是 lab_member,不可為主管。'})
    if user_obj.lab_specialty != User.LabSpecialty.OPERATOR:
        raise ValidationError({
            'assignee': (
                f'指派對象必須是「{User.LabSpecialty.OPERATOR.label}」職位 — '
                f'目前職位為 {user_obj.get_lab_specialty_display()}。'
            ),
        })

    # 各司其職 — block self / upstream operators.
    upstream_ids = {
        sample.created_by_id,
        sample.dispatched_by_id,
        sample.parameters_set_by_id,
    }
    operator_id = getattr(operator, 'pk', None)
    if operator_id and user_obj.id == operator_id:
        raise ValidationError({
            'assignee': '不能指派給自己 — 接力分工需要交給其他員工。',
        })
    if user_obj.id in upstream_ids:
        upstream_names = [
            getattr(sample.created_by, 'username', None),
            getattr(sample.dispatched_by, 'username', None),
            getattr(sample.parameters_set_by, 'username', None),
        ]
        upstream_names = [n for n in upstream_names if n]
        raise ValidationError({
            'assignee': (
                f'此員工已經負責過上游步驟({", ".join(upstream_names) or "split/dispatch/params"})'
                f',請改派給其他人以維持各司其職。'
            ),
        })

    sample.assignee = user_obj
    sample.status = Sample.Status.READY
    sample.save(update_fields=['assignee', 'status'])

    from monitoring.models import Notification
    _send_notification(
        user_obj,
        f'已指派 sample {sample.sub_code} (order {sample.order.order_no}) — '
        f'機台 {sample.equipment.code if sample.equipment else "?"}',
        level=Notification.Level.INFO,
        kind=Notification.Kind.ORDER_SCHEDULED,
        related_order=sample.order,
    )
    _sample_record_event(
        sample, event_type='assign', operator=operator,
        notes=f'指派執行員工 — {user_obj.username}',
    )
    return sample


def load_sample(sample, *, operator):
    """上貨 (per-sample): the assigned operator physically loads the
    wafer onto its picked machine. Flips READY → RUNNING."""
    from .models import Sample
    if sample.status != Sample.Status.READY:
        raise ValidationError(
            f'Cannot load a sample in "{sample.get_status_display()}" status.'
        )
    if sample.schedule_start and timezone.now() < sample.schedule_start:
        raise ValidationError(
            'Cannot load before the scheduled start time (time-lock).'
        )

    sample.loaded_at = timezone.now()
    sample.loaded_by = operator if operator and hasattr(operator, 'pk') else None
    sample.status = Sample.Status.RUNNING
    sample.save(update_fields=['loaded_at', 'loaded_by', 'status'])
    _sample_record_event(
        sample, event_type='load', operator=operator,
        notes=f'上貨 — 機台 {sample.equipment.code if sample.equipment else "?"}',
    )

    # Promote the parent stage to IN_PROGRESS the first time any sample
    # starts. The Stage stays IN_PROGRESS until all samples finish.
    stage = sample.order.stages.first()
    if stage and stage.status == OrderStage.Status.APPROVED:
        stage.status = OrderStage.Status.IN_PROGRESS
        stage.save(update_fields=['status'])
        order = stage.order
        if order.status == Order.Status.WAITING:
            order.status = Order.Status.IN_PROGRESS
            order.save(update_fields=['status', 'updated_at'])
    return sample


def record_sample_telemetry(sample, *, operator, measurement, finished=False, notes=''):
    """數據蒐集: a machine (or its proxy) pushes one measurement reading
    for a running Sample. Each call lands in ``StageEvent.measurement``
    so the audit log keeps a full timeline. ``finished=True`` triggers
    auto-close via :func:`complete_sample`.

    Useful both for real telemetry from automation systems and for the
    "Simulate telemetry" demo button the lab member can click.
    """
    from .models import Sample
    if sample.status != Sample.Status.RUNNING:
        raise ValidationError(
            f'Cannot record telemetry on a sample in '
            f'"{sample.get_status_display()}" status.'
        )
    if not isinstance(measurement, dict):
        raise ValidationError({'measurement': 'measurement must be a JSON object.'})

    _sample_record_event(
        sample, event_type='note', operator=operator,
        notes=notes or 'telemetry',
        measurement=measurement,
    )

    if finished:
        complete_sample(sample, operator=operator, measurement=measurement)
    return sample


def complete_sample(sample, *, operator, measurement=None):
    """下貨 / 完成 (per-sample): operator unloads the wafer. Flips
    RUNNING → DONE. When every sample on the order is DONE the stage
    + order auto-close so the requester gets notified."""
    from .models import Sample
    if sample.status != Sample.Status.RUNNING:
        raise ValidationError(
            f'Cannot complete a sample in "{sample.get_status_display()}" status.'
        )
    sample.completed_at = timezone.now()
    sample.completed_by = operator if operator and hasattr(operator, 'pk') else None
    sample.status = Sample.Status.DONE
    sample.save(update_fields=['completed_at', 'completed_by', 'status'])
    _sample_record_event(
        sample, event_type='unload', operator=operator,
        notes=f'下貨 — 機台 {sample.equipment.code if sample.equipment else "?"}',
        measurement=measurement or {},
    )

    # Release the machine. Defensive: never overwrite a MAINTENANCE
    # flag — a manager / engineer set that explicitly (via the
    # equipment-status dropdown or an upstream abnormal report) and
    # only they should clear it.
    if sample.equipment:
        from equipments.models import Equipment
        if sample.equipment.status != Equipment.Status.MAINTENANCE:
            sample.equipment.status = Equipment.Status.AVAILABLE
            sample.equipment.save(update_fields=['status'])

    # Shrink the booking to the actual completion time so a follow-up
    # dispatch can re-use the freed window. We match by
    # (order, equipment, started_at=sample.schedule_start) which uniquely
    # identifies the row that dispatch_sample created.
    if sample.equipment and sample.schedule_start:
        from scheduling.models import EquipmentBooking
        EquipmentBooking.objects.filter(
            order=sample.order,
            equipment=sample.equipment,
            started_at=sample.schedule_start,
        ).update(ended_at=sample.completed_at)

    # If every sample on this order is DONE → close the stage + order.
    stage = sample.order.stages.first()
    if stage and not sample.order.samples.exclude(status=Sample.Status.DONE).exists():
        if stage.status == OrderStage.Status.IN_PROGRESS:
            complete_stage(stage, operator=operator)
    return sample


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
    """Lab manager 簽核: flips the stage WAITING → APPROVED.

    Required precondition for the dispatch step (see
    :func:`approve_and_schedule_stage`). The flow's hard invariant is:
    no stage may move to IN_PROGRESS without at least one APPROVED row
    on its audit history — sign-off is the only path to APPROVED status
    and the dispatch service refuses to advance otherwise.

    Idempotent on already-approved stages: returns the latest Approval
    row instead of raising, so a re-clicked button stays harmless.
    """
    if stage.status == OrderStage.Status.APPROVED:
        # Already signed off — return the most recent approval rather
        # than crashing; the UI may re-fire after a network hiccup.
        return stage.approvals.filter(decision=Approval.Decision.APPROVED).first()
    if stage.status != OrderStage.Status.WAITING:
        raise ValidationError(
            f'Cannot sign off a stage in "{stage.get_status_display()}" status.'
        )

    approval = _record_approval(
        stage, actor=actor, decision=Approval.Decision.APPROVED, comment=comment,
    )
    stage.status = OrderStage.Status.APPROVED
    # Manager sign-off also stamps the 接件 fields — the previous two-step
    # "簽核 then 接件" was redundant given the manager is the gatekeeper for
    # both steps. Receiving is now a side-effect of the same approval.
    update_fields = ['status']
    if not stage.received_at:
        stage.received_at = timezone.now()
        stage.received_by = actor
        update_fields += ['received_at', 'received_by']
    stage.save(update_fields=update_fields)

    # Audit row mirrors the historical 接件 stage event so the timeline
    # still shows a receive entry — only the actor changes.
    if actor is not None and 'received_at' in update_fields:
        from scheduling.services import record_stage_event
        record_stage_event(
            stage,
            event_type='receive',
            operator=actor,
            notes='接件 (隨簽核自動執行)',
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


def _attach_parameter_overrides(stage: OrderStage, *, overrides) -> None:
    """Persist 受控 parameter overrides on the stage.

    Validation enforces the "在受控 recipe 範圍內" requirement: every key
    in ``overrides`` must already exist on the picked recipe. Trying to
    invent a new key (one that the machine recipe never declared) is
    rejected so an operator cannot push a value through that the machine
    won't honour. Empty overrides are a valid no-op.
    """
    if not overrides:
        stage.parameter_overrides = {}
        stage.save(update_fields=['parameter_overrides'])
        return
    if not isinstance(overrides, dict):
        raise ValidationError({'parameter_overrides': 'Must be a JSON object.'})
    if stage.recipe is None:
        raise ValidationError({
            'parameter_overrides': (
                'Cannot override parameters without a Recipe — pick a recipe first.'
            ),
        })
    recipe_keys = set(stage.recipe.parameters or {})
    unknown = sorted(set(overrides) - recipe_keys)
    if unknown:
        raise ValidationError({
            'parameter_overrides': (
                f"Keys {unknown} are not defined on recipe "
                f"'{stage.recipe.name}' — overrides must stay within the "
                f"recipe's declared parameters."
            ),
        })
    stage.parameter_overrides = overrides
    stage.save(update_fields=['parameter_overrides'])


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

    Two invariants protect the wafer lot:
    * A Lot can have at most one *active* order at a time (WAITING or
      IN_PROGRESS). The next requester must wait for the in-progress run
      to land back at DONE / REJECTED before re-submitting.
    * The same (Lot, Experiment) pair cannot be submitted twice — the
      historical record stops requesters from re-running an experiment
      already completed on this lot.
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

    if lot is not None:
        active = Order.objects.filter(
            lot=lot,
            status__in=(Order.Status.WAITING, Order.Status.IN_PROGRESS),
        ).only('order_no').first()
        if active is not None:
            raise ValidationError({
                'lot_id': (
                    f"Lot {lot.code} is locked: order {active.order_no} is "
                    f"still in progress. Wait until it finishes before "
                    f"submitting again."
                ),
            })
        duplicate = Order.objects.filter(
            lot=lot,
            experiment=experiment,
            status=Order.Status.DONE,
        ).only('order_no').first()
        if duplicate is not None:
            raise ValidationError({
                'experiment': (
                    f"Experiment '{experiment.name}' has already been "
                    f"completed on lot {lot.code} (order {duplicate.order_no})."
                    f" Duplicate submissions are not allowed."
                ),
            })

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
    parameter_overrides=None,
    actor=None,
    comment: str = '',
) -> OrderStage:
    """Lab personnel 派工: dispatches a SIGNED-OFF stage onto a machine.

    Required precondition (req 2): the stage MUST be APPROVED before
    dispatch is allowed. ``WAITING`` is accepted for backwards
    compatibility and convenience — when a manager fires the combined
    "簽核+派工" button the service writes the missing sign-off
    Approval row inline so the audit history stays consistent.

    Args:
      ``equipment`` — optional UUID/string of the specific machine to pin.
      ``recipe``    — optional UUID/string of the Recipe to apply.
      ``parameter_overrides`` — optional dict of recipe-knob overrides
                                set by process engineering (req 5).
                                Keys MUST exist on the picked recipe.
    """
    if stage.status not in (OrderStage.Status.WAITING, OrderStage.Status.APPROVED):
        raise ValidationError(f"Cannot dispatch a stage in {stage.status} status.")

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

    # 必要條件: signoff must exist before dispatch. If the stage is still
    # WAITING we auto-record the manager's signoff as the precondition
    # check for the combined button. If it's already APPROVED we trust
    # the historical sign_off_stage call.
    needs_auto_signoff = stage.status == OrderStage.Status.WAITING

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

    # Recipe parameter overrides — process-engineer knob tuning. Must be
    # validated AFTER the recipe is pinned so the key-set check has the
    # right baseline.
    if parameter_overrides is not None:
        _attach_parameter_overrides(stage, overrides=parameter_overrides)

    # Notify assignee
    if assignee:
        _send_notification(assignee, f"You have been assigned to {stage.order.order_no} Step {stage.step_order}")

    # Append the audit rows: a fresh sign-off if the combined button was
    # used (covers the "required precondition" rule), plus the dispatch
    # record itself.
    if needs_auto_signoff:
        _record_approval(
            stage,
            actor=actor,
            decision=Approval.Decision.APPROVED,
            comment=comment or 'Auto sign-off via combined approve+schedule action.',
        )
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
