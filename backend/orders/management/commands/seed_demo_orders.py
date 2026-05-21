"""Seed a realistic spread of orders + stages + samples + approvals + events
so the lab-supervisor reports view is populated for demos.

Idempotent-ish: refuses to run if there are already orders in the system,
unless ``--force`` is passed (which wipes first). The data is spread across
the last 7 days and across all three demo labs (Photo, Process, QC) so
charts have multiple buckets to plot.

    python manage.py seed_demo_orders          # safe — refuses if data exists
    python manage.py seed_demo_orders --force  # wipe orders, then seed

For each lab the seeder creates:
    * 2 DONE orders (created → approved → split → dispatched → params → assigned → loaded → completed → unload)
    * 1 IN_PROGRESS order with a sub-LOT currently running
    * 1 REJECTED order (rejection Approval row)
    * 1 WAITING order (still on the manager's sign-off queue)

The timestamps are backdated by writing to the columns after save() so
``ended_at``, ``occurred_at`` and ``decided_at`` land on different days.
"""
import datetime as _dt
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from equipments.models import Equipment, Recipe
from orders.models import Approval, Order, OrderStage, Sample
from scheduling.models import EquipmentBooking, StageEvent
from users.models import Department, User, WaferLot


class Command(BaseCommand):
    help = 'Seed demo orders/stages/samples/approvals/events so reports are populated.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Wipe existing orders before seeding.')

    def handle(self, *args, **options):
        existing = Order.objects.count()
        if existing and not options['force']:
            self.stdout.write(self.style.WARNING(
                f'{existing} orders already exist. Pass --force to wipe + reseed.'
            ))
            return

        if options['force']:
            with transaction.atomic():
                StageEvent.objects.all().delete()
                Approval.objects.all().delete()
                EquipmentBooking.objects.all().delete()
                Sample.objects.all().delete()
                OrderStage.objects.all().delete()
                Order.objects.all().delete()
            self.stdout.write('Cleared old orders.')

        managers = list(User.objects.filter(role='lab_manager').select_related('department'))
        if not managers:
            self.stderr.write(self.style.ERROR(
                'No lab_manager seeded. Run `seed_demo_accounts` first.'
            ))
            return

        for mgr in managers:
            dept = mgr.department
            if not dept:
                continue
            self.stdout.write(f'\n→ Seeding {dept.name}…')
            self._seed_for_lab(mgr, dept)

        self.stdout.write(self.style.SUCCESS('\nDemo orders seeded.'))

    # ------------------------------------------------------------------
    def _seed_for_lab(self, manager, dept):
        members = list(
            User.objects.filter(department=dept, role='lab_member').order_by('username')
        )
        if len(members) < 4:
            self.stderr.write(self.style.WARNING(
                f'  {dept.name} has only {len(members)} lab_members — need 4 for full chain.'
            ))
            return
        coord, dispatcher, engineer, operator = members[:4]

        # A regular_employee (the requester). Any one will do.
        requester = User.objects.filter(role='regular_employee').first()
        if not requester:
            self.stderr.write(self.style.ERROR('No regular_employee to use as requester.'))
            return

        equipments = list(Equipment.objects.filter(department=dept))
        if not equipments:
            self.stderr.write(self.style.WARNING(
                f'  {dept.name} has no equipment.'
            ))
            return

        recipes_by_eq_type = {}
        for r in Recipe.objects.filter(is_active=True):
            recipes_by_eq_type.setdefault(r.equipment_type_id, []).append(r)

        now = timezone.now()
        fab = dept.fab

        # 2× DONE — one 2-day-old, one 5-day-old
        for offset_days in (2, 5):
            self._make_done_order(
                dept=dept, fab=fab, manager=manager,
                coord=coord, dispatcher=dispatcher,
                engineer=engineer, operator=operator,
                requester=requester,
                equipments=equipments, recipes_by_eq_type=recipes_by_eq_type,
                offset_days=offset_days, now=now,
            )

        # 1× IN_PROGRESS (running RIGHT now)
        self._make_in_progress_order(
            dept=dept, fab=fab, manager=manager,
            coord=coord, dispatcher=dispatcher,
            engineer=engineer, operator=operator,
            requester=requester,
            equipments=equipments, recipes_by_eq_type=recipes_by_eq_type,
            now=now,
        )

        # 1× REJECTED — 3 days ago
        self._make_rejected_order(
            dept=dept, fab=fab, manager=manager, requester=requester, now=now,
        )

        # 1× WAITING (fresh, on manager's queue)
        self._make_waiting_order(
            dept=dept, fab=fab, requester=requester, now=now,
        )

        # 1× APPROVED + a WAITING sub-LOT — pre-stages the dispatcher's
        # queue so a fresh install can demo the 派工 dialog (machine +
        # recipe picker) without first walking through sign-off + split.
        self._make_dispatch_demo_order(
            dept=dept, fab=fab, manager=manager, coord=coord,
            requester=requester, now=now,
        )

    # ------------------------------------------------------------------
    def _lot(self, fab):
        """Allocate a fresh registered lot for this order so the create_order
        invariants (no duplicate active lot, no duplicate (lot, experiment))
        don't trip even though we bypass the service."""
        code = f'DEMO-{fab.fab_name}-{random.randint(1000, 9999):04d}'
        lot, _ = WaferLot.objects.get_or_create(code=code, defaults={'fab': fab})
        return lot

    def _pick_equipment(self, equipments):
        return random.choice(equipments)

    def _pick_recipe(self, equipment, recipes_by_eq_type):
        recipes = recipes_by_eq_type.get(equipment.equipment_type_id) or []
        return recipes[0] if recipes else None

    def _backdate(self, instance, field, when):
        """Write ``when`` to ``field`` after save() so auto_now / auto_now_add
        defaults don't clobber the demo timestamp."""
        type(instance).objects.filter(pk=instance.pk).update(**{field: when})
        setattr(instance, field, when)

    # ------------------------------------------------------------------
    def _make_done_order(
        self, *, dept, fab, manager, coord, dispatcher, engineer, operator,
        requester, equipments, recipes_by_eq_type, offset_days, now,
    ):
        start_ts = now - timedelta(days=offset_days, hours=4)
        approve_ts = start_ts + timedelta(hours=1)
        receive_ts = approve_ts + timedelta(hours=1)
        split_ts = receive_ts + timedelta(minutes=20)
        dispatch_ts = split_ts + timedelta(minutes=30)
        params_ts = dispatch_ts + timedelta(minutes=20)
        assign_ts = params_ts + timedelta(minutes=10)
        load_ts = assign_ts + timedelta(minutes=20)
        unload_ts = load_ts + timedelta(hours=1, minutes=30)

        order = Order.objects.create(
            user=requester, department=dept,
            lot=self._lot(fab), status=Order.Status.DONE,
            requirements='Demo done order',
        )
        self._backdate(order, 'created_at', start_ts)
        self._backdate(order, 'ended_at', unload_ts)

        stage = OrderStage.objects.create(
            order=order, step_order=1, department=dept,
            status=OrderStage.Status.DONE,
            received_at=receive_ts, received_by=coord,
            completed_at=unload_ts,
        )
        self._backdate(stage, 'created_at', start_ts) if hasattr(stage, 'created_at') else None

        # Approval
        ap = Approval.objects.create(
            stage=stage, actor=manager, decision='approved', comment='looks good',
        )
        self._backdate(ap, 'decided_at', approve_ts)

        # Sample — one sub-LOT, run to completion on a real equipment + recipe
        eq = self._pick_equipment(equipments)
        recipe = self._pick_recipe(eq, recipes_by_eq_type)
        sample = Sample.objects.create(
            order=order, sub_code='A', wafer_count=12,
            created_by=coord, equipment=eq, recipe=recipe,
            parameter_overrides={},
            parameters_set_at=params_ts, parameters_set_by=engineer,
            assignee=operator,
            dispatched_by=dispatcher,
            schedule_start=load_ts, schedule_end=unload_ts,
            loaded_at=load_ts, loaded_by=operator,
            completed_at=unload_ts, completed_by=operator,
            status=Sample.Status.DONE,
        )
        self._backdate(sample, 'created_at', split_ts)

        # StageEvents — receive / load / unload
        self._mk_event(stage, eq, recipe, 'receive', coord, receive_ts, 'wafer received')
        self._mk_event(stage, eq, recipe, 'load', operator, load_ts, 'load A')
        self._mk_event(stage, eq, recipe, 'unload', operator, unload_ts, 'unload A')

        # Booking — drives utilization chart
        booking = EquipmentBooking.objects.create(
            order=order, equipment=eq, stage=stage,
            started_at=load_ts, ended_at=unload_ts,
        )
        return order

    # ------------------------------------------------------------------
    def _make_in_progress_order(
        self, *, dept, fab, manager, coord, dispatcher, engineer, operator,
        requester, equipments, recipes_by_eq_type, now,
    ):
        start_ts = now - timedelta(days=1, hours=2)
        approve_ts = start_ts + timedelta(hours=1)
        receive_ts = approve_ts + timedelta(hours=1)
        split_ts = receive_ts + timedelta(minutes=15)
        load_ts = now - timedelta(minutes=45)

        order = Order.objects.create(
            user=requester, department=dept,
            lot=self._lot(fab), status=Order.Status.IN_PROGRESS,
            requirements='Demo running order',
        )
        self._backdate(order, 'created_at', start_ts)

        stage = OrderStage.objects.create(
            order=order, step_order=1, department=dept,
            status=OrderStage.Status.IN_PROGRESS,
            received_at=receive_ts, received_by=coord,
        )
        ap = Approval.objects.create(
            stage=stage, actor=manager, decision='approved', comment='approved',
        )
        self._backdate(ap, 'decided_at', approve_ts)

        eq = self._pick_equipment(equipments)
        recipe = self._pick_recipe(eq, recipes_by_eq_type)

        Equipment.objects.filter(pk=eq.pk).update(status=Equipment.Status.OCCUPIED)

        sample = Sample.objects.create(
            order=order, sub_code='A', wafer_count=8,
            created_by=coord, equipment=eq, recipe=recipe,
            parameter_overrides={},
            parameters_set_at=load_ts - timedelta(minutes=20),
            parameters_set_by=engineer,
            assignee=operator, dispatched_by=dispatcher,
            schedule_start=load_ts, schedule_end=load_ts + timedelta(hours=2),
            loaded_at=load_ts, loaded_by=operator,
            status=Sample.Status.RUNNING,
        )
        self._backdate(sample, 'created_at', split_ts)

        self._mk_event(stage, eq, recipe, 'receive', coord, receive_ts, 'wafer received')
        self._mk_event(stage, eq, recipe, 'load', operator, load_ts, 'load A')

        EquipmentBooking.objects.create(
            order=order, equipment=eq, stage=stage,
            started_at=load_ts, ended_at=load_ts + timedelta(hours=2),
        )

        # A pending sub-LOT (B) waiting for params — shows up in sub-LOT breakdown
        sample_b = Sample.objects.create(
            order=order, sub_code='B', wafer_count=4,
            created_by=coord, dispatched_by=dispatcher,
            equipment=eq, recipe=recipe,
            status=Sample.Status.DISPATCHED,
        )
        self._backdate(sample_b, 'created_at', split_ts)

    # ------------------------------------------------------------------
    def _make_dispatch_demo_order(
        self, *, dept, fab, manager, coord, requester, now,
    ):
        """Pre-stage an order that's been signed-off + split into a
        WAITING sub-LOT, so the dispatcher's 派工 queue is non-empty
        on a fresh install. Lets the user open the dispatch dialog
        immediately to demo the machine + recipe picker flow.
        """
        start_ts = now - timedelta(hours=4)
        approve_ts = start_ts + timedelta(minutes=30)
        split_ts = approve_ts + timedelta(minutes=15)

        order = Order.objects.create(
            user=requester, department=dept,
            lot=self._lot(fab), status=Order.Status.WAITING,
            requirements='Demo dispatch — ready for 派工 dialog',
        )
        self._backdate(order, 'created_at', start_ts)

        stage = OrderStage.objects.create(
            order=order, step_order=1, department=dept,
            status=OrderStage.Status.APPROVED,
            received_at=approve_ts, received_by=manager,
        )
        ap = Approval.objects.create(
            stage=stage, actor=manager, decision='approved', comment='ready',
        )
        self._backdate(ap, 'decided_at', approve_ts)

        sample = Sample.objects.create(
            order=order, sub_code='A', wafer_count=25,
            created_by=coord, notes='Waiting for dispatcher pick',
            status=Sample.Status.WAITING,
        )
        self._backdate(sample, 'created_at', split_ts)

    # ------------------------------------------------------------------
    def _make_rejected_order(
        self, *, dept, fab, manager, requester, now,
    ):
        start_ts = now - timedelta(days=3, hours=2)
        reject_ts = start_ts + timedelta(hours=1)
        order = Order.objects.create(
            user=requester, department=dept,
            lot=self._lot(fab), status=Order.Status.REJECTED,
            requirements='Demo rejected — missing safety doc',
            rejection_reason='Missing safety review attachment.',
        )
        self._backdate(order, 'created_at', start_ts)
        self._backdate(order, 'ended_at', reject_ts)

        stage = OrderStage.objects.create(
            order=order, step_order=1, department=dept,
            status=OrderStage.Status.REJECTED,
        )
        ap = Approval.objects.create(
            stage=stage, actor=manager, decision='rejected',
            comment='Missing safety doc.',
        )
        self._backdate(ap, 'decided_at', reject_ts)

    # ------------------------------------------------------------------
    def _make_waiting_order(self, *, dept, fab, requester, now):
        start_ts = now - timedelta(hours=3)
        order = Order.objects.create(
            user=requester, department=dept,
            lot=self._lot(fab), status=Order.Status.WAITING,
            requirements='Demo waiting — needs sign-off',
        )
        self._backdate(order, 'created_at', start_ts)
        OrderStage.objects.create(
            order=order, step_order=1, department=dept,
            status=OrderStage.Status.WAITING,
        )

    # ------------------------------------------------------------------
    def _mk_event(self, stage, equipment, recipe, event_type, operator, when, notes):
        ev = StageEvent.objects.create(
            stage=stage, equipment=equipment, recipe=recipe,
            event_type=event_type, operator=operator, notes=notes,
            measurement={},
        )
        self._backdate(ev, 'occurred_at', when)
        return ev
