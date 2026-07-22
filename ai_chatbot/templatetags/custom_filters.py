from django import template

register = template.Library()

@register.filter
def split(value, key):
    """Returns the value split by the key."""
    return value.split(key)