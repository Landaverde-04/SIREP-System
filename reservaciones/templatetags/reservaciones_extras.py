from django import template

register = template.Library()


@register.filter
def duracion(valor):
    """Muestra un timedelta como '2 h' o '2 h 30 min'."""
    if valor is None:
        return ''
    minutos = int(valor.total_seconds() // 60)
    horas, minutos = divmod(minutos, 60)
    if horas and minutos:
        return f'{horas} h {minutos} min'
    if horas:
        return f'{horas} h'
    return f'{minutos} min'
