from django.apps import AppConfig


class EquipmentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'equipments'

    def ready(self):
        # Import signal handlers so equipment status changes generate
        # notifications for the relevant lab manager.
        from . import signals  # noqa: F401
