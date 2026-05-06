"""Merge duplicate Department rows that share (fab, name).

Database invariant: ``Department.unique_together = ('fab', 'name')`` should
prevent duplicates, but historical seed_data fixtures + the demo migrations
were both able to create the same logical department under different UUIDs
in setups where the unique index hadn't yet been enforced. When that
happens, users who joined via one UUID can't see equipment / stages bound
to the other UUID.

Run this once if ``OrderStageListView`` was returning empty results for a
manager whose department visually matched a stage:

    python manage.py reconcile_departments [--dry-run]

For each duplicate group, keeps the row with the most members + equipment
attached (so the more "real" one), and re-points everything else
(equipment, members, orders, stages) to that survivor before deleting the
duplicates. Idempotent.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from equipments.models import Equipment
from orders.models import Order, OrderStage
from users.models import Department, User


class Command(BaseCommand):
    help = 'Merge duplicate Department rows that share (fab, name).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without touching the database.',
        )

    def handle(self, *args, **options):
        dry = options['dry_run']

        # Group by (fab_id, name)
        groups = defaultdict(list)
        for d in Department.objects.all():
            groups[(d.fab_id, d.name)].append(d)

        duplicates = {key: rows for key, rows in groups.items() if len(rows) > 1}

        if not duplicates:
            self.stdout.write(self.style.SUCCESS('No duplicate departments found.'))
            return

        self.stdout.write(
            f'Found {len(duplicates)} duplicate group(s):\n',
        )

        for (fab_id, name), rows in duplicates.items():
            self.stdout.write(f'\n  fab_id={fab_id}  name="{name}"  rows={len(rows)}')

            # Pick the survivor: the row with the most attached resources,
            # then by oldest pk (deterministic tiebreaker).
            def score(dept):
                return (
                    User.objects.filter(department=dept).count()
                    + Equipment.objects.filter(department=dept).count()
                    + Order.objects.filter(department=dept).count()
                    + OrderStage.objects.filter(department=dept).count()
                )

            rows_sorted = sorted(rows, key=lambda d: (-score(d), str(d.id)))
            survivor = rows_sorted[0]
            losers = rows_sorted[1:]

            self.stdout.write(f'    survivor: {survivor.id}  (score={score(survivor)})')
            for loser in losers:
                self.stdout.write(f'    loser:    {loser.id}  (score={score(loser)})')

            if dry:
                continue

            with transaction.atomic():
                for loser in losers:
                    User.objects.filter(department=loser).update(department=survivor)
                    Equipment.objects.filter(department=loser).update(department=survivor)
                    Order.objects.filter(department=loser).update(department=survivor)
                    OrderStage.objects.filter(department=loser).update(department=survivor)
                    loser.delete()

        if dry:
            self.stdout.write(self.style.WARNING('\n--dry-run: no changes written.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nReconciliation complete.'))
