from django import template

register = template.Library()


@register.filter
def campo_bs(campo):
    """Dibuja el campo con sus clases de Bootstrap y marca ``is-invalid`` si tiene errores."""
    clase = campo.field.widget.attrs.get('class', '')
    if campo.errors:
        clase = f'{clase} is-invalid'.strip()
    return campo.as_widget(attrs={'class': clase})
