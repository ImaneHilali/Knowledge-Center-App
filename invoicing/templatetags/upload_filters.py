from django import template

register = template.Library()


@register.filter(name='add_class')
def add_class(value, css_class):
    attrs = value.field.widget.attrs
    if 'class' in attrs:
        attrs['class'] += ' ' + css_class
    else:
        attrs['class'] = css_class
    rendered_widget = str(value)
    return rendered_widget
