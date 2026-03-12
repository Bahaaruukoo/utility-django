from .models import Customer


def create_customer(*, tenant, user, data):
    return Customer.objects.create(
        tenant=tenant,
        first_name=data["first_name"],
        middle_name=data.get("middle_name", ""),
        last_name=data["last_name"],
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        address=data["address"],
        id_number=data.get("id_number", ""),
        customer_type=data.get("customer_type", "RES"),
        registered_by=user,
    )


def deactivate_customer(customer):
    customer.is_active = False
    customer.save()


def activate_customer(customer):
    customer.is_active = True
    customer.save()
