from django.conf import settings
from django.db.models.signals import post_migrate, pre_delete
from django.dispatch import receiver


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def protect_system_user(sender, instance, **kwargs):
    if instance.username == "system":
        raise Exception("SYSTEM user cannot be deleted")


@receiver(post_migrate)
def create_system_user(sender, **kwargs):
    user, created = settings.AUTH_USER_MODEL.objects.get_or_create(
        username="system",
        defaults={
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        }
    )
    if created:
        user.set_unusable_password()
        user.save()
