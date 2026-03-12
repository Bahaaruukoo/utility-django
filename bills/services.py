import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from bills.models import Bill, BillingSettings, BlockRate, MeterReading
from customers.models import MeterAssignment

from .models import Bill, BillingSettings, BillItem, BlockRate

logger = logging.getLogger("app")


class BillingService:

    # ============================================
    # SETTINGS
    # ============================================
    @staticmethod
    def get_settings(tenant):
        try:
            return BillingSettings.objects.get(tenant=tenant)
        except BillingSettings.DoesNotExist:
            raise ValidationError("Billing settings not configured.")

    # ============================================
    # RESOLVE ACTIVE CUSTOMER FROM METER
    # ============================================
    @staticmethod
    def get_active_customer(meter, tenant):

        assignment = MeterAssignment.objects.filter(
            tenant=tenant,
            meter=meter,
            is_active=True
        ).select_related("customer").first()

        if not assignment:
            raise ValidationError("No active customer assigned to this meter.")

        return assignment.customer

    # ============================================
    # GET RATE BASED ON CUSTOMER TYPE
    # ============================================
    @staticmethod
    def get_rate_for_customer(block, customer):
        try:
            return getattr(block, customer.customer_type)
        except AttributeError:
            raise ValidationError("Invalid customer type.")

    # ============================================
    # PROGRESSIVE BLOCK CALCULATION
    # ============================================
    @staticmethod
    def calculate_block_amount(meter, tenant, consumption):

        customer = BillingService.get_active_customer(
            meter=meter,
            tenant=tenant
        )

        consumption = Decimal(consumption)

        if consumption <= 0:
            return Decimal("0.00")

        blocks = BlockRate.objects.filter(
            tenant=tenant
        ).order_by("start_unit")

        total = Decimal("0.00")
        remaining = consumption

        for block in blocks:

            if remaining <= 0:
                break

            block_start = block.start_unit
            block_end = block.end_unit

            # Calculate usable units in this block
            block_capacity = block_end - block_start

            units = min(remaining, block_capacity)

            rate = BillingService.get_rate_for_customer(block, customer)

            total += units * rate
            remaining -= units

        return total

    @staticmethod
    def calculate_block_breakdown(tenant, customer, consumption):

        consumption = Decimal(consumption)
        blocks = BlockRate.objects.filter(
            tenant=tenant
        ).order_by("start_unit")

        remaining = consumption
        breakdown = []

        for block in blocks:

            if remaining <= 0:
                break

            block_capacity = block.end_unit - block.start_unit
            units = min(remaining, block_capacity)

            rate = getattr(block, customer.customer_type)

            amount = units * rate

            breakdown.append({
                "block_name": block.name,
                "units": units,
                "rate": rate,
                "amount": amount,
            })

            remaining -= units

        return breakdown
    # ============================================
    # GENERATE BILL
    # ============================================

    ''' @staticmethod
    @transaction.atomic
    def generate_bill(reading):

        tenant = reading.tenant
        branch = reading.branch

        customer = BillingService.get_active_customer(
            meter=reading.meter,
            tenant=tenant
        )

        settings = BillingService.get_settings(tenant)

        breakdown = BillingService.calculate_block_breakdown(
            tenant=tenant,
            customer=customer,
            consumption=reading.consumption
        )

        base_total = sum(item["amount"] for item in breakdown)

        total = (
            base_total
            + settings.meter_rental_fee
            + settings.service_charge_fee
            + settings.operation_charge_fee
        )

        bill = Bill.objects.create(
            tenant=tenant,
            branch=branch,
            meter=reading.meter,
            reading=reading,
            customer=customer,
            amount=total,
            bill_period=reading.reading_date,
        )

        # Save breakdown rows
        for item in breakdown:
            BillItem.objects.create(
                tenant=tenant,
                bill=bill,
                block_name=item["block_name"],
                units=item["units"],
                rate=item["rate"],
                amount=item["amount"],
            )

        return bill
    '''
    @staticmethod
    @transaction.atomic
    def generate_bill(reading):

        logger.info(
            "Starting bill generation | reading_id=%s meter_id=%s tenant=%s",
            reading.id,
            reading.meter_id,
            reading.tenant_id,
        )

        tenant = reading.tenant
        branch = reading.branch

        logger.debug(
            "Reading details | branch=%s consumption=%s reading_date=%s",
            branch.id if branch else None,
            reading.consumption,
            reading.reading_date,
        )

        # -------------------------------
        # Get active customer
        # -------------------------------
        customer = BillingService.get_active_customer(
            meter=reading.meter,
            tenant=tenant
        )

        if not customer:
            logger.error(
                "No active customer found | meter_id=%s tenant=%s",
                reading.meter_id,
                tenant.id,
            )
            raise ValueError("No active customer assigned to meter")

        logger.info(
            "Customer found | customer_id=%s meter_id=%s",
            customer.id,
            reading.meter_id,
        )

        # -------------------------------
        # Get billing settings
        # -------------------------------
        settings = BillingService.get_settings(tenant)

        logger.debug(
            "Billing settings loaded | rental=%s service=%s operation=%s",
            settings.meter_rental_fee,
            settings.service_charge_fee,
            settings.operation_charge_fee,
        )

        # -------------------------------
        # Calculate block tariff breakdown
        # -------------------------------
        breakdown = BillingService.calculate_block_breakdown(
            tenant=tenant,
            customer=customer,
            consumption=reading.consumption
        )

        logger.info(
            "Tariff breakdown calculated | blocks=%s consumption=%s",
            len(breakdown),
            reading.consumption,
        )

        for block in breakdown:
            logger.debug(
                "Block detail | block=%s units=%s rate=%s amount=%s",
                block["block_name"],
                block["units"],
                block["rate"],
                block["amount"],
            )

        # -------------------------------
        # Calculate totals
        # -------------------------------
        base_total = sum(item["amount"] for item in breakdown)

        logger.debug(
            "Base total calculated | amount=%s",
            base_total
        )

        total = (
            base_total
            + settings.meter_rental_fee
            + settings.service_charge_fee
            + settings.operation_charge_fee
        )

        logger.info(
            "Final bill amount calculated | base=%s rental=%s service=%s operation=%s total=%s",
            base_total,
            settings.meter_rental_fee,
            settings.service_charge_fee,
            settings.operation_charge_fee,
            total,
        )

        # -------------------------------
        # Create bill
        # -------------------------------
        from django.db import IntegrityError
        try:
            bill = Bill.objects.create(
                tenant=tenant,
                branch=branch,
                meter=reading.meter,
                reading=reading,
                customer=customer,
                amount=total,
                bill_period=reading.reading_date,
            )

        except :
            raise 

        if bill:
            logger.info(
                "Bill created | bill_id=%s reading_id=%s amount=%s",
                bill.id,
                reading.id,
                total,
            )
        else :
            logger.error(
                "Faild to create bill | customer=%s reading_id=%s amount=%s",
                customer,
                reading.id,
                total,
            )
        # -------------------------------
        # Save bill items
        # -------------------------------
        for item in breakdown:
            bill_item = BillItem.objects.create(
                tenant=tenant,
                bill=bill,
                block_name=item["block_name"],
                units=item["units"],
                rate=item["rate"],
                amount=item["amount"],
            )

            logger.debug(
                "Bill item created | bill_id=%s item_id=%s block=%s units=%s amount=%s",
                bill.id,
                bill_item.id,
                item["block_name"],
                item["units"],
                item["amount"],
            )

        logger.info(
            "Bill generation completed successfully | bill_id=%s reading_id=%s",
            bill.id,
            reading.id,
        )

        return bill

# ============================================
# LATE FEE APPLICATION
# ============================================
@staticmethod
@transaction.atomic
def apply_late_fee(bill):

    if not bill.is_overdue():
        return

    settings = BillingService.get_settings(bill.tenant)

    late_fee = (
        bill.amount * settings.late_fee_rate
    ) / Decimal("100")

    bill.amount += late_fee
    bill.save(update_fields=["amount"])

class MeterReadingService:

    @staticmethod
    @transaction.atomic
    def create_reading(tenant, branch, meter, reading_value, reader, reading_date=None):
        """
        Safely creates a meter reading and optionally generates bill.
        """
        if branch is None:
            raise ValidationError("Branch is required.")
        
        if meter is None:
            raise ValidationError("Meter is required.")
        if reading_value is None:
            raise ValidationError("Reading value is required.")
        
        # Lock previous readings for concurrency safety
        last_reading = (
            MeterReading.objects
            .select_for_update()
            .filter(tenant=tenant, meter=meter)
            .order_by("-reading_date")
            .first()
        )

        if last_reading:
            if reading_value < last_reading.reading_value:
                raise ValidationError(
                    "Reading cannot be less than previous reading."
                )
            previous = last_reading.reading_value
        else:
            previous = meter.initial_reading

        consumption = reading_value - previous

        try:
            reading = MeterReading.objects.create(
                tenant=tenant,
                branch=branch,
                meter=meter,
                reading_value=reading_value,
                previous_reading=previous,
                consumption=consumption,
                reading_date=reading_date,
                reader=reader
            )
        except IntegrityError as e:
            # Optional: inspect constraint name
            message = str(e)

            if "unique" in message.lower():
                raise Exception("A reading for this meter and date already exists")

            # Re-raise unknown DB errors
            raise

        # Auto-generate bill if manual generation is disabled
        settings = BillingService.get_settings(tenant)

        if not settings.manual_bill_generation:
            try:
                BillingService.generate_bill(reading)
                reading.reading_status = "GENERATED"

            except IntegrityError as e:
                reading.reading_status = "FAILED"

                message = str(e).lower()
                if "unique" in message:
                    raise Exception("Bill for the meter has been generated already")
                raise

            except Exception:
                reading.reading_status = "FAILED"
                raise

            reading.save()
        
        return reading

    @staticmethod
    @transaction.atomic
    def update_reading(tenant, reading, new_value):

        # Lock row for safety
        reading = (
            MeterReading.objects
            .select_for_update()
            .get(pk=reading.pk)
        )

        # Get related bill
        bill = Bill.objects.filter(
            tenant=reading.tenant,
            meter=reading.meter,
            bill_period=reading.reading_date
        ).first()

        # ❌ Prevent editing paid bill
        if bill and bill.status == "PAID":
            raise ValidationError("Cannot edit reading. Bill already paid.")

        if bill and bill.status != "VOIDED":
            raise ValidationError("Cannot edit reading. Associated bill should be voided.")

        # Get previous reading
        last_reading = (
            MeterReading.objects
            .filter(
                tenant=reading.tenant,
                meter=reading.meter,
                reading_date__lt=reading.reading_date
            ).exclude(
                reading_status__in=["VOIDED"]
            )
            .order_by("-reading_date")
            .first()
        )

        previous = last_reading.reading_value if last_reading else reading.meter.initial_reading

        if new_value < previous:
            raise ValidationError("Reading cannot be less than previous reading.")

        reading.reading_status = "VOIDED"
        reading.save()

        
        # Update values
        reading.reading_value = new_value
        reading.previous_reading = previous
        reading.consumption = new_value - previous
        created_reading = MeterReadingService.create_reading(tenant=tenant,
                                           branch=reading.branch,
                                           meter=reading.meter,
                                           reading_value=new_value
                                           )
        '''# Regenerate bill if exists
        if bill:
            from bills.services import BillingService
            customer = BillingService.get_active_customer(
                meter=reading.meter,
                tenant=tenant
            )
            breakdown = BillingService.calculate_block_breakdown(
                tenant=tenant,
                customer=customer,
                consumption=reading.consumption
            )
            base_total = sum(item["amount"] for item in breakdown)

            total = (
                base_total
                + settings.meter_rental_fee
                + settings.service_charge_fee
                + settings.operation_charge_fee
            )

            settings = BillingService.get_settings(reading.tenant)

            bill.amount = total
            bill.save()
            # Remove all existing BillItem from old bill
            BillItem.objects.filter(tenant=tenant, bill=bill).delete()

            # Save breakdown rows
            for item in breakdown:
                BillItem.objects.create(
                    tenant=tenant,
                    bill=bill,
                    block_name=item["block_name"],
                    units=item["units"],
                    rate=item["rate"],
                    amount=item["amount"],
                )
        '''
        # Auto-generate bill if manual generation is disabled
        from bills.services import BillingService
        settings = BillingService.get_settings(tenant)

        if not settings.manual_bill_generation:
            try:
                BillingService.generate_bill(created_reading)
                created_reading.reading_status = "GENERATED"
            except Exception:
                created_reading.reading_status = "FAILED"
        
            created_reading.save()

        return reading
    
    @staticmethod
    def get_active_customer(meter, tenant):

        assignment = MeterAssignment.objects.filter(
            tenant=tenant,
            meter=meter,
            is_active=True
        ).select_related("customer").first()

        if not assignment:
            raise ValidationError("No active customer assigned to this meter.")

        return assignment.customer
