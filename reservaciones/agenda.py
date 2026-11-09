"""
Línea de tiempo del día para la consulta de disponibilidad: una fila por mesa
con bloques para las reservaciones programadas y las atenciones.

Las posiciones se calculan aquí como porcentajes de la jornada visible y se
entregan como texto ("12.500") para que la plantilla no las convierta al
formato decimal con coma del idioma español.
"""
import math
from datetime import datetime, time, timedelta

from django.urls import reverse
from django.utils import timezone

HORA_APERTURA = 10
HORA_CIERRE = 23


def _pct(valor):
    return f'{valor:.3f}'


class LineaDeTiempo:
    def __init__(self, fecha, mesas, reservaciones, atenciones, periodo=None, ahora=None):
        self.fecha = fecha
        ahora = ahora or timezone.now()
        locales = [timezone.localtime(r.fecha_hora_inicio) for r in reservaciones] + \
                  [timezone.localtime(a.fecha_hora_ingreso) for a in atenciones]
        finales = [timezone.localtime(r.fecha_hora_fin) for r in reservaciones]
        if periodo:
            locales.append(timezone.localtime(periodo[0]))
            finales.append(timezone.localtime(periodo[1]))
        horas_inicio = [d.hour for d in locales if d.date() == fecha]
        horas_fin = [d.hour + (1 if d.minute or d.second else 0) if d.date() == fecha else 24 for d in finales]
        self.hora_inicio = min([HORA_APERTURA] + horas_inicio)
        self.hora_fin = min(24, max([HORA_CIERRE] + horas_fin))
        self.inicio = timezone.make_aware(datetime.combine(fecha, time(self.hora_inicio)))
        self.fin = self.inicio + timedelta(hours=self.hora_fin - self.hora_inicio)
        self.total = (self.fin - self.inicio).total_seconds()

        n_horas = self.hora_fin - self.hora_inicio
        self.paso_hora = _pct(100 / n_horas)
        self.horas = [{'texto': f'{h:02d}:00' if h < 24 else '24:00',
                       'pos': _pct((h - self.hora_inicio) * 100 / n_horas)}
                      for h in range(self.hora_inicio, self.hora_fin + 1, 2 if n_horas > 14 else 1)]

        self.periodo = self._tramo(*periodo) if periodo else None
        self.ahora = _pct(self._pos(ahora)) if self.inicio <= ahora <= self.fin else None

        por_mesa = {m.pk: [] for m in mesas}
        for r in reservaciones:
            tramo = self._tramo(r.fecha_hora_inicio, r.fecha_hora_fin)
            if tramo and r.mesa_id in por_mesa:
                por_mesa[r.mesa_id].append({
                    **tramo, 'clase': 'tipo-reservacion',
                    'texto': f'{timezone.localtime(r.fecha_hora_inicio):%H:%M} {r.cliente.nombre}',
                    'titulo': f'{r.codigo} · {r.cliente.nombre} · {r.cantidad_personas} personas · '
                              f'{timezone.localtime(r.fecha_hora_inicio):%H:%M}–{timezone.localtime(r.fecha_hora_fin):%H:%M}',
                    'url': reverse('reservaciones:detalle_reservacion', args=[r.codigo]),
                })
        for a in atenciones:
            abierta = a.esta_abierta
            fin = max(a.fin_estimado, ahora) if abierta else a.fecha_hora_cierre
            tramo = self._tramo(a.fecha_hora_ingreso, fin)
            if tramo and a.mesa_id in por_mesa:
                nombre = a.cliente.nombre if a.cliente else 'Sin registro'
                por_mesa[a.mesa_id].append({
                    **tramo, 'clase': 'tipo-atencion' if abierta else 'tipo-cerrada',
                    'texto': ('En curso · ' if abierta else '') + nombre,
                    'titulo': f'{"Atención en curso" if abierta else "Atención cerrada"} · {nombre} · '
                              f'{a.cantidad_personas} personas · desde {timezone.localtime(a.fecha_hora_ingreso):%H:%M}',
                    'url': '',
                })
        self.filas = [{'mesa': m, 'bloques': por_mesa[m.pk]} for m in mesas]

    def _pos(self, momento):
        return max(0.0, min(100.0, (momento - self.inicio).total_seconds() * 100 / self.total))

    def _tramo(self, desde, hasta):
        if hasta <= self.inicio or desde >= self.fin:
            return None
        izquierda, derecha = self._pos(desde), self._pos(hasta)
        return {'izq': _pct(izquierda), 'ancho': _pct(max(derecha - izquierda, 0.6))}


def proxima_media_hora(ahora=None):
    """Hora local redondeada a la siguiente media hora (valor inicial de la consulta)."""
    local = timezone.localtime(ahora or timezone.now()).replace(second=0, microsecond=0)
    minutos = 30 * math.ceil((local.minute + 1) / 30)
    return local.replace(minute=0) + timedelta(minutes=minutos)
