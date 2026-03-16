from django.apps import AppConfig


class BillsConfig(AppConfig):
    name = 'bills'
    default_auto_field = 'django.db.models.BigAutoField'
    
    def ready(self):
        import bills.signals