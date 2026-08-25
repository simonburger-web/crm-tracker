from django.apps import AppConfig


class CrmConfig(AppConfig):
    name = 'crm'

    def ready(self):
        import crm.signals  # noqa: F401 — registers signal handlers
