import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Order(models.Model):
    """A booking / service order submitted by a requester."""

    class Status(models.TextChoices):
        CREATED = 'created', 'Created'
        WAITING = 'waiting', 'Waiting'
        IN_PROGRESS = 'in_progress', 'In Progress'
        DONE = 'done', 'Done'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    department = models.ForeignKey(
        'users.Department',
        on_delete=models.CASCADE,
        related_name='orders',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders',
    )
    order_no = models.CharField(max_length=30, unique=True, editable=False)
    # In the single-lab-per-order model the experiment is no longer the
    # driver of stage generation — each order is one lab visit. Keeping the
    # field as a nullable optional tag so legacy orders still resolve and
    # admins can group historical batches if they want.
    experiment = models.ForeignKey(
        'equipments.Experiment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    # FK to the registered WaferLot. Column name stays "lot_id" (Django's
    # default for the FK) so reads like ``order.lot_id`` continue to return
    # the lot code string used everywhere downstream — and traceability is
    # now enforced at the database level rather than as free text.
    lot = models.ForeignKey(
        'users.WaferLot',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders',
        help_text='Registered wafer lot. Pick from the dropdown — picked code is stored as the FK.',
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks',
        help_text='Lab member assigned to this order'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.WAITING,
    )
    is_urgent = models.BooleanField(default=False)
    schedule_start = models.DateTimeField(null=True, blank=True)
    schedule_end = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')
    requirements = models.TextField(
        blank=True,
        default='',
        help_text="What the requester needs from this experiment — surfaced "
                  "to the lab manager during scheduling.",
    )
    remark = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'order'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.order_no:
            self.order_no = self._generate_order_no()
        super().save(*args, **kwargs)

    def _generate_order_no(self):
        """Generate FAB-style order number: FAB12A-20260428-0001"""
        fab_name = 'LAB'
        if self.department and self.department.fab:
            fab_name = self.department.fab.fab_name

        today = timezone.localdate()
        date_str = today.strftime('%Y%m%d')
        prefix = f'{fab_name}-{date_str}-'

        # Find the max sequence for today's prefix
        last = (
            Order.objects
            .filter(order_no__startswith=prefix)
            .order_by('-order_no')
            .values_list('order_no', flat=True)
            .first()
        )
        if last:
            seq = int(last.split('-')[-1]) + 1
        else:
            seq = 1

        return f'{prefix}{seq:04d}'

    def __str__(self):
        return f'Order {self.order_no} – {self.get_status_display()}'


class OrderStage(models.Model):
    """Specific step in an order's relay pipeline."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'   # Waiting for prev stage
        WAITING = 'waiting', 'Waiting'   # Waiting for manager to assign
        IN_PROGRESS = 'in_progress', 'In Progress'
        DONE = 'done', 'Done'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='stages')
    step_order = models.PositiveIntegerField()
    department = models.ForeignKey('users.Department', on_delete=models.CASCADE)
    # equipment_type used to be required (one stage per equipment recipe).
    # Now experiments map to a single lab visit and don't pre-define machines,
    # so this is optional metadata — set if the manager wants the wafer on a
    # specific machine type, NULL otherwise.
    equipment_type = models.ForeignKey(
        'equipments.EquipmentType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    
    # Execution data (set by manager/member)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_stages'
    )
    equipment = models.ForeignKey(
        'equipments.Equipment',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stage_bookings'
    )
    recipe = models.ForeignKey(
        'equipments.Recipe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stages',
        help_text='Recipe used on the picked equipment for this stage.',
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)

    schedule_start = models.DateTimeField(null=True, blank=True)
    schedule_end = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # 接件 — lab personnel acknowledged the wafer is physically at the lab.
    # Captured independently of approval / scheduling so the receive audit
    # has its own timestamp.
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stages_received',
    )

    class Meta:
        db_table = 'order_stage'
        ordering = ['order', 'step_order']
        unique_together = ('order', 'step_order')

    def __str__(self):
        return f'{self.order.order_no} | Step {self.step_order} | {self.get_status_display()}'


class Sample(models.Model):
    """A subset of wafers carved out of an Order's parent wafer lot.

    分貨系統 (WIP split): lab personnel can break a submitted lot into
    multiple sub-groups so different recipes can run in parallel without
    forcing the requester to file separate orders. Each Sample is a leaf
    or interior node in a small tree — ``parent_sample`` lets the system
    track a re-split when the lab decides to subdivide further.

    The model deliberately stays light: no FK to OrderStage so the same
    Sample can travel through multiple dispatches; downstream events
    record which Sample they handled via :class:`scheduling.StageEvent`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='samples',
    )
    sub_code = models.CharField(
        max_length=40,
        help_text='Suffix identifying this WIP group (e.g. "A", "B").',
    )
    wafer_count = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True, default='')
    parent_sample = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='samples_created',
    )

    class Meta:
        db_table = 'sample'
        ordering = ['order', 'sub_code']
        unique_together = ('order', 'sub_code')
        indexes = [
            models.Index(fields=['order', 'sub_code']),
            models.Index(fields=['parent_sample']),
        ]

    @property
    def full_code(self):
        """Stable display string: ``<lot_code>-<sub_code>``."""
        lot = self.order.lot_id or 'NA'
        return f'{lot}-{self.sub_code}'

    def __str__(self):
        return self.full_code


class Approval(models.Model):
    """Append-only sign-off record for an OrderStage.

    Every manager decision on a stage — pure sign-off, full schedule, or
    rejection — leaves one Approval row. The model is deliberately
    independent of ``OrderStage.status`` so the audit history survives any
    later status flip (a re-opened stage doesn't erase the original
    sign-off; a fresh row is added instead).

    ``decision`` distinguishes the three outcomes; ``comment`` is the
    free-text rationale the manager typed (mandatory on reject, optional
    on approve). ``actor`` may go NULL when the original manager account
    is later deleted — the historical record stays useful as long as the
    decided_at + comment are intact.
    """

    class Decision(models.TextChoices):
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stage = models.ForeignKey(
        OrderStage,
        on_delete=models.CASCADE,
        related_name='approvals',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approvals_given',
    )
    decision = models.CharField(max_length=10, choices=Decision.choices)
    comment = models.TextField(blank=True, default='')
    decided_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'approval'
        ordering = ['-decided_at']
        indexes = [
            models.Index(fields=['stage', '-decided_at']),
            models.Index(fields=['actor', '-decided_at']),
            models.Index(fields=['decision', '-decided_at']),
        ]

    def __str__(self):
        actor = self.actor.username if self.actor else 'unknown'
        return f'{actor} {self.get_decision_display()} {self.stage_id} @ {self.decided_at:%Y-%m-%d %H:%M}'

