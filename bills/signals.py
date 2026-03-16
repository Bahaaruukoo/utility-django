from urllib import request

from django.apps import apps
from django.db import connection, transaction
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django_tenants.signals import post_schema_sync
from django_tenants.utils import get_public_schema_name

from bills.models import BillingSettings, BlockRate

#tenant = request.tenant

@receiver(post_schema_sync) #@receiver(post_migrate)
def create_default_billing_settings(sender, tenant, **kwargs):

    print("------------------------------------------", tenant)
    
    # Skip public schema
    if connection.schema_name == get_public_schema_name():
        return

    BillingSettings = apps.get_model("bills", "BillingSettings")

    tables = connection.introspection.table_names()

    # Ensure required tables exist
    if "bills_billingsettings" not in tables:
        return

    '''if "tenant_utils_branch" not in tables:
        return'''

    if BillingSettings.objects.exists():
        return

    BillingSettings.objects.create(
        tenant = tenant,
        late_fee_rate=0.0,
        meter_rental_fee=15.00,
        billing_cycle_days=30,
        bill_overdue_in_days=15,
        service_charge_fee=10.00,
        operation_charge_fee=20.00,
        manual_bill_generation=True,
        bill_generation_date=5,
    )


@receiver(post_schema_sync) #@receiver(post_migrate)
def create_default_block_rates(sender, tenant, **kwargs):
    """
    Populate default 6 block rates for each tenant
    only if no block rates exist.
    """

    '''# Run only for bills app
    if sender.name != "bills":
        return
    '''
    # Skip public schema
    if connection.schema_name == get_public_schema_name():
        return

    BlockRate = apps.get_model("bills", "BlockRate")

    # Ensure table exists before querying
    table_name = BlockRate._meta.db_table
    if table_name not in connection.introspection.table_names():
        return

    # Skip if data already exists
    if BlockRate.objects.exists():
        return

    sample_data = [
        # name, start,end,RES, GOV, COM, IND, PUB
        ("Block 1", 0, 5, 40, 48, 55, 55, 48),
        ("Block 2", 6, 10, 48, 55, 63, 63, 55),
        ("Block 3", 11, 15, 55, 63, 71, 71, 63),
        ("Block 4", 16, 20, 63, 71, 78, 78, 71),
        ("Block 5", 21, 25, 71, 78, 86, 86, 78),
        ("Block 6", 25, 9999, 78, 86, 94, 94, 86),
    ]

    with transaction.atomic():
        for block in sample_data:
            BlockRate.objects.create(
                tenant=tenant,
                name=block[0],
                start_unit=block[1],
                end_unit=block[2],
                RES=block[3],
                GOV=block[4],
                COM=block[5],
                IND=block[6],
                PUB=block[7],
            )