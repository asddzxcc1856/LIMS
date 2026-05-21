"""Synchronous wrapper for ``scheduling.tasks.alert_schedule_overruns``."""
from django.core.management.base import BaseCommand

from scheduling.tasks import alert_schedule_overruns


class Command(BaseCommand):
    help = 'Send CRITICAL alerts for samples running past schedule_end.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--grace-minutes', type=int, default=30,
            help='Wait N minutes past schedule_end before alerting (default: 30).',
        )

    def handle(self, *args, **options):
        alerted = alert_schedule_overruns(grace_minutes=options['grace_minutes'])
        if alerted:
            self.stdout.write(self.style.SUCCESS(
                f'Alerted on {len(alerted)} overrun sample(s): {", ".join(alerted)}',
            ))
        else:
            self.stdout.write('No samples are overrunning.')
