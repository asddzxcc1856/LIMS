"""Idempotently provision the system-superuser account.

Reads the password from the ``LIMS_ADMIN_PASSWORD`` env var when set, falling
back to the project default. Run after ``migrate``:

    python manage.py ensure_admin
"""
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from users.models import User

DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = 'Admin@LIMS_2026!Sup'


class Command(BaseCommand):
    help = 'Ensure the system-superuser admin account exists with the configured password.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default=DEFAULT_USERNAME)
        parser.add_argument(
            '--password',
            default=os.environ.get('LIMS_ADMIN_PASSWORD', DEFAULT_PASSWORD),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options['username']
        password = options['password']

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': f'{username}@lims.local',
                'role': User.Role.SUPERUSER,
                'status': User.Status.ACTIVE,
                'is_staff': True,
                'is_superuser': True,
            },
        )

        user.role = User.Role.SUPERUSER
        user.status = User.Status.ACTIVE
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        verb = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{verb} admin user "{username}".'))
