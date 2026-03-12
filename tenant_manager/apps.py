from django.apps import AppConfig
from django.db import ProgrammingError, connection
from django.db.models.signals import post_migrate

# your_tenant_app/apps.py

def setup_public_tenant(sender, **kwargs):
    # Local imports to avoid AppRegistryNotReady
    from .models import Domain, Tenant

    # Guard: Check if the required tables actually exist in the DB
    # This prevents errors during the very first migration run
    required_tables = [Tenant._meta.db_table, Domain._meta.db_table]
    existing_tables = connection.introspection.table_names()
    
    if not all(table in existing_tables for table in required_tables):
        return  # Exit silently; the signal will run again after the next migrate

    try:
        # 1. Create the Public Tenant
        public_tenant, created = Tenant.objects.get_or_create(
            schema_name='public',
            defaults={'name': 'public', 'on_trial': False}
        )

        # 2. Create the Domain for the Public Tenant
        Domain.objects.get_or_create(
            domain='localhost',
            tenant=public_tenant,
            defaults={'is_primary': True}
        )
    except ProgrammingError:
        # Final fallback for cases where introspection might miss a table
        pass

class TenantsConfig(AppConfig):    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenant_manager'

    def ready(self):
        post_migrate.connect(setup_public_tenant, sender=self)
