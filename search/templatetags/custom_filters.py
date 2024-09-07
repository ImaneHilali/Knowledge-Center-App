from django import template

register = template.Library()


@register.filter(name='endswith')
def endswith(value, arg):
    """Usage, {{ value|endswith:"arg" }}"""
    return value.endswith(arg)

