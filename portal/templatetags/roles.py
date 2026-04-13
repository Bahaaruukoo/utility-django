from django import template

register = template.Library()

@register.simple_tag
def has_role(user, role_name):
    return user.tenantuserrole_set.filter(role__name=role_name).exists()
