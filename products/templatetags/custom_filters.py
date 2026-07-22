from django import template

register = template.Library()

@register.filter(name='split')
def split(value, arg):
    """Splits a string by a given delimiter."""
    return value.split(arg)