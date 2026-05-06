"""Wipe all sample-order history and reset equipment back to available.

Used to clean out demo/test orders before opening the system to real
traffic, and to inspect why a freshly-submitted order isn't visible to a
manager (the diagnostic dump below).

    python manage.py clear_orders          # actually delete
    python manage.py clear_orders --dry-run  # report counts only
    python manage.py clear_orders --diagnose-visibility  # extra dump

Idempotent: running twice on an already-empty system is a no-op.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from equipments.models import Equipment, Experiment
from orders.models import Order, OrderStage
from scheduling.models import EquipmentBooking
from users.models import Department, User


class Command(BaseCommand):
    help = 'Delete all sample orders / stages / bookings; reset equipment to available.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--diagnose-visibility',
            action='store_true',
            help='After clearing, dump experiment->department vs manager->department '
                 'so we can see where a routing mismatch comes from.',
        )

    def handle(self, *args, **options):
        dry = options['dry_run']

        order_count = Order.objects.count()
        stage_count = OrderStage.objects.count()
        booking_count = EquipmentBooking.objects.count()
        occupied = Equipment.objects.exclude(status=Equipment.Status.AVAILABLE).count()

        self.stdout.write(
            f'Currently:\n'
            f'  orders                  {order_count}\n'
            f'  stages                  {stage_count}\n'
            f'  bookings                {booking_count}\n'
            f'  non-available equipment {occupied}\n'
        )

        if dry:
            self.stdout.write(self.style.WARNING('--dry-run: nothing deleted.'))
        else:
            with transaction.atomic():
                EquipmentBooking.objects.all().delete()
                OrderStage.objects.all().delete()
                Order.objects.all().delete()
                Equipment.objects.exclude(
                    status=Equipment.Status.AVAILABLE
                ).update(status=Equipment.Status.AVAILABLE)
            self.stdout.write(self.style.SUCCESS('Cleared. Equipment reset to available.'))

        if options['diagnose_visibility']:
            self.stdout.write('\n=== Diagnose: experiment -> dept -> manager ===')
            self._dump_visibility()

    def _dump_visibility(self):
        # Group experiments by their department
        by_dept = {}
        for exp in Experiment.objects.select_related('department', 'department__fab'):
            key = (
                str(exp.department_id) if exp.department_id else None,
                exp.department.name if exp.department else '(unassigned)',
            )
            by_dept.setdefault(key, []).append(exp.name)

        # Map dept_id -> list of managers
        managers_by_dept = {}
        for u in User.objects.filter(role='lab_manager').select_related('department'):
            managers_by_dept.setdefault(str(u.department_id), []).append(u.username)

        # Dept duplicates: same (fab, name) but different IDs?
        seen = {}
        for d in Department.objects.select_related('fab'):
            seen.setdefault((d.fab_id, d.name), []).append(str(d.id))
        duplicates = {k: v for k, v in seen.items() if len(v) > 1}

        for (dept_id, dept_name), exps in by_dept.items():
            mgrs = managers_by_dept.get(dept_id, [])
            self.stdout.write(
                f'  {dept_name!s:<35} dept_id={dept_id}\n'
                f'    managers in this dept: {mgrs or "(none)"}\n'
                f'    experiments routed here: {exps}'
            )

        if duplicates:
            self.stdout.write(self.style.WARNING(
                '\n!!  Duplicate Department rows detected (same fab+name, different ID):'
            ))
            for (fab_id, name), ids in duplicates.items():
                self.stdout.write(f'    fab_id={fab_id} name="{name}" ids={ids}')
            self.stdout.write(self.style.WARNING(
                '    Run `python manage.py reconcile_departments` to merge them.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\nNo duplicate Department rows.'))
