"""Run ``scheduling.tasks.auto_close_stalled_stages`` synchronously.

Useful for cron deployments that don't run Celery beat — same code path,
no broker dependency at call time.
"""
from django.core.management.base import BaseCommand

from scheduling.tasks import auto_close_stalled_stages


class Command(BaseCommand):
    help = 'Auto-complete in-progress stages whose schedule_end has passed.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--grace-minutes', type=int, default=5,
            help='Wait N minutes past schedule_end before auto-closing (default: 5).',
        )

    def handle(self, *args, **options):
        closed = auto_close_stalled_stages(grace_minutes=options['grace_minutes'])
        if closed:
            self.stdout.write(self.style.SUCCESS(
                f'Auto-closed {len(closed)} stage(s): {", ".join(closed)}',
            ))
        else:
            self.stdout.write('No stalled stages to close.')
