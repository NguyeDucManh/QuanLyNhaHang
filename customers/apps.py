from django.apps import AppConfig


class CustomersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "customers"
    def ready(self):
        from . import audit_service  # noqa: F401
    verbose_name = "Khách hàng"

