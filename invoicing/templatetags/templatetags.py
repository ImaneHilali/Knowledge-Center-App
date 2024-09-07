from django import template

register = template.Library()


@register.filter
def get_attr(obj, attr_name):
    try:
        return getattr(obj, attr_name)
    except AttributeError:
        return None

