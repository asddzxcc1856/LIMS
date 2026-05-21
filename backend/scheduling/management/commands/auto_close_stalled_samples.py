"""Synchronous wrapper for ``scheduling.tasks.auto_close_stalled_samples``."""
from django.core.management.base import BaseCommand

from scheduling.tasks import auto_close_stalled_samples


class Command(BaseCommand):
    help = 'Auto-complete RUNNING samples whose schedule_end has passed.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--grace-minutes', type=int, default=5,
            help='Wait N minutes past schedule_end (default: 5).',
        )

    def handle(self, *args, **options):
        closed = auto_close_stalled_samples(grace_minutes=options['grace_minutes'])
        if closed:
            self.stdout.write(self.style.SUCCESS(
                f'Auto-closed {len(closed)} sample(s): {", ".join(closed)}',
            ))
        else:
            self.stdout.write('No stalled samples to close.')
