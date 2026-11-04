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


@register.filter
def sillas(capacidad):
    """Distribuye las sillas del dibujo de una mesa: la mitad arriba y la mitad abajo (máx. 6 por lado)."""
    capacidad = int(capacidad or 0)
    arriba, abajo = (capacidad + 1) // 2, capacidad // 2
    dibujadas_arriba, dibujadas_abajo = min(arriba, 6), min(abajo, 6)
    return {
        'arriba': range(dibujadas_arriba),
        'abajo': range(dibujadas_abajo),
        'extra': capacidad - dibujadas_arriba - dibujadas_abajo,
        'ancho': max(64, max(dibujadas_arriba, 1) * 24 + 16),
    }
