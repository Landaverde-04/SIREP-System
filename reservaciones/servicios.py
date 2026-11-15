"""
Lógica de negocio del módulo de reservaciones.

Las vistas solo recogen datos y muestran resultados; las reglas viven aquí y
en los modelos, para que se apliquen igual desde cualquier pantalla.

- ServicioDisponibilidad: única implementación de CU-02 (RN-01, RN-02). La
  usan el registro y la modificación de reservaciones y el ingreso.
- ServicioReservaciones: CU-01, CU-05 y CU-06.
- ServicioIngreso: CU-03 con y sin reservación; abre la Atención.

Antes de guardar se bloquea la fila de la mesa (SELECT ... FOR UPDATE) y se
vuelve a comprobar la disponibilidad. Así, si dos anfitriones intentan
comprometer la misma mesa a la vez, el segundo recibe el aviso de que ya no
está libre (CU-01 8a, CU-05 6a) en lugar de crear una reservación duplicada.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from administracion.models import Mesa
from .models import (
    DURACION_PREDETERMINADA, Atencion, Reservacion, validar_duracion,
)


# Margen para no rechazar una consulta "para ahora" por los segundos que tarda
# el anfitrión en enviar el formulario.
MARGEN_INICIO = timedelta(minutes=5)


@dataclass
class EstadoMesa:
    """Situación de una mesa en el período consultado (para el mapa de disponibilidad)."""
    mesa: Mesa
    estado: str                      # libre | reservada | ocupada | pequena
    reservacion: Reservacion = None  # la que la compromete, si está reservada
    atencion: Atencion = None        # la atención en curso, si está ocupada

    ETIQUETAS = {'libre': 'Libre', 'reservada': 'Reservada', 'ocupada': 'Ocupada',
                 'pequena': 'Capacidad insuficiente'}

    @property
    def etiqueta(self):
        return self.ETIQUETAS[self.estado]

    @property
    def disponible(self):
        return self.estado == 'libre'


class ReglaNegocioError(ValidationError):
    """Operación rechazada por una regla de negocio; el mensaje es para el usuario."""


class MesaNoDisponibleError(ReglaNegocioError):
    """La mesa ya está comprometida u ocupada en el período solicitado."""


class ServicioDisponibilidad:
    """CU-02 Consultar disponibilidad de mesas."""

    def __init__(self, ahora=None):
        self.ahora = ahora or timezone.now()

    def validar_periodo(self, inicio, duracion):
        """CU-02 3a y 3b: fecha y hora futuras y duración máxima de cuatro horas."""
        validar_duracion(duracion)
        if inicio < self.ahora - MARGEN_INICIO:
            raise ReglaNegocioError('La reservación debe ser para una fecha y hora futuras.',
                                    code='fecha_pasada')

    def mesas_disponibles(self, inicio, duracion, cantidad_personas, excluir_reservacion=None):
        """
        Mesas activas con capacidad suficiente que no tienen, en el período
        [inicio, inicio + duración), una reservación programada ni una atención
        en curso. Se ordenan de menor a mayor capacidad (CU-02 paso 6).
        """
        fin = inicio + duracion
        return (Mesa.objects
                .filter(activo=True, capacidad__gte=cantidad_personas)
                .exclude(pk__in=self._mesas_reservadas(inicio, fin, excluir_reservacion))
                .exclude(pk__in=self._mesas_con_atencion(inicio))
                .order_by('capacidad', 'numero'))

    def mesa_disponible(self, mesa, inicio, duracion, cantidad_personas, excluir_reservacion=None):
        return self.mesas_disponibles(
            inicio, duracion, cantidad_personas, excluir_reservacion
        ).filter(pk=mesa.pk).exists()

    def motivo_no_disponible(self, mesa, inicio, duracion, cantidad_personas, excluir_reservacion=None):
        """Explica por qué una mesa concreta no se puede ofrecer, o devuelve None."""
        if not mesa.activo:
            return f'La mesa {mesa.numero} está deshabilitada.'
        if not mesa.admite(cantidad_personas):
            return (f'La mesa {mesa.numero} admite {mesa.capacidad} personas '
                    f'y se necesitan {cantidad_personas}.')
        fin = inicio + duracion
        if self._mesas_con_atencion(inicio).filter(mesa=mesa).exists():
            return f'La mesa {mesa.numero} está ocupada por una atención en curso.'
        if self._mesas_reservadas(inicio, fin, excluir_reservacion).filter(mesa=mesa).exists():
            return f'La mesa {mesa.numero} ya está reservada en ese período.'
        return None

    def _mesas_reservadas(self, inicio, fin, excluir_reservacion=None):
        reservaciones = Reservacion.objects.programadas().que_se_cruzan(inicio, fin)
        if excluir_reservacion is not None:
            reservaciones = reservaciones.exclude(pk=excluir_reservacion.pk)
        return reservaciones.values('mesa')

    def _atenciones_que_bloquean(self, inicio):
        """
        Una atención abierta ocupa su mesa desde el ingreso hasta que se cobra.
        Para una consulta inmediata, cualquier atención abierta bloquea la mesa;
        para una consulta futura, la bloquea si se espera que siga en curso a
        la hora de inicio.
        """
        atenciones = Atencion.objects.abiertas()
        if inicio > self.ahora + MARGEN_INICIO:
            atenciones = atenciones.con_fin().filter(fin_calculado__gt=inicio)
        return atenciones

    def _mesas_con_atencion(self, inicio):
        return self._atenciones_que_bloquean(inicio).values('mesa')

    def estado_mesas(self, inicio, duracion, cantidad_personas=None):
        """
        Estado de cada mesa habilitada en el período, con la misma regla que
        mesas_disponibles(): las "libres" son exactamente las disponibles.
        Si no se indica la cantidad de personas, no se filtra por capacidad.
        """
        fin = inicio + duracion
        reservadas = {}
        for reservacion in (Reservacion.objects.programadas().que_se_cruzan(inicio, fin)
                            .select_related('cliente').order_by('fecha_hora_inicio')):
            reservadas.setdefault(reservacion.mesa_id, reservacion)
        ocupadas = {a.mesa_id: a for a in self._atenciones_que_bloquean(inicio).select_related('cliente')}

        resultado = []
        for mesa in Mesa.objects.filter(activo=True).order_by('ubicacion', 'numero'):
            if mesa.pk in ocupadas:
                resultado.append(EstadoMesa(mesa, 'ocupada', atencion=ocupadas[mesa.pk]))
            elif mesa.pk in reservadas:
                resultado.append(EstadoMesa(mesa, 'reservada', reservacion=reservadas[mesa.pk]))
            elif cantidad_personas and not mesa.admite(cantidad_personas):
                resultado.append(EstadoMesa(mesa, 'pequena'))
            else:
                resultado.append(EstadoMesa(mesa, 'libre'))
        return resultado

    def agenda_del_dia(self, fecha):
        """Reservaciones programadas y atenciones que ocupan cada mesa durante un día."""
        dia_inicio = timezone.make_aware(datetime.combine(fecha, time.min))
        dia_fin = dia_inicio + timedelta(days=1)
        reservaciones = (Reservacion.objects.programadas().que_se_cruzan(dia_inicio, dia_fin)
                         .select_related('cliente'))
        atenciones = (Atencion.objects.filter(fecha_hora_ingreso__lt=dia_fin)
                      .filter(Q(estado=Atencion.Estado.ABIERTA) | Q(fecha_hora_cierre__gt=dia_inicio))
                      .select_related('cliente', 'reservacion'))
        return list(reservaciones), list(atenciones)


class ServicioReservaciones:
    """CU-01 Registrar, CU-05 Modificar y CU-06 Cancelar reservación."""

    def __init__(self, usuario=None, disponibilidad=None):
        self.usuario = usuario
        self.disponibilidad = disponibilidad or ServicioDisponibilidad()

    @transaction.atomic
    def registrar(self, cliente, mesa, inicio, duracion, cantidad_personas):
        self.disponibilidad.validar_periodo(inicio, duracion)
        mesa = self._bloquear_y_verificar(mesa, inicio, duracion, cantidad_personas)
        reservacion = Reservacion(
            cliente=cliente, mesa=mesa, fecha_hora_inicio=inicio, duracion_estimada=duracion,
            cantidad_personas=cantidad_personas, registrada_por=self._usuario(),
        )
        reservacion.full_clean(exclude=['codigo'])  # el código se genera al guardar
        reservacion.save()
        return reservacion

    @transaction.atomic
    def modificar(self, reservacion, mesa, inicio, duracion, cantidad_personas):
        reservacion = Reservacion.objects.select_for_update().get(pk=reservacion.pk)
        reservacion.exigir_programada('modificarse')
        self.disponibilidad.validar_periodo(inicio, duracion)
        mesa = self._bloquear_y_verificar(mesa, inicio, duracion, cantidad_personas,
                                          excluir_reservacion=reservacion)
        reservacion.mesa = mesa
        reservacion.fecha_hora_inicio = inicio
        reservacion.duracion_estimada = duracion
        reservacion.cantidad_personas = cantidad_personas
        reservacion.full_clean()
        reservacion.save()
        return reservacion

    @transaction.atomic
    def cancelar(self, reservacion, motivo=''):
        reservacion = Reservacion.objects.select_for_update().get(pk=reservacion.pk)
        reservacion.cancelar(motivo)
        return reservacion

    def _bloquear_y_verificar(self, mesa, inicio, duracion, cantidad_personas, excluir_reservacion=None):
        mesa = Mesa.objects.select_for_update().get(pk=mesa.pk)
        motivo = self.disponibilidad.motivo_no_disponible(
            mesa, inicio, duracion, cantidad_personas, excluir_reservacion)
        if motivo:
            raise MesaNoDisponibleError(motivo + ' Elija otra de las mesas disponibles.',
                                        code='mesa_no_disponible')
        return mesa

    def _usuario(self):
        return self.usuario if getattr(self.usuario, 'is_authenticated', False) else None


class ServicioIngreso:
    """CU-03 Registrar ingreso y asignar mesa (con o sin reservación)."""

    def __init__(self, usuario=None, disponibilidad=None):
        self.usuario = usuario
        self.disponibilidad = disponibilidad or ServicioDisponibilidad()

    @property
    def ahora(self):
        return self.disponibilidad.ahora

    def mesas_para_ingreso(self, cantidad_personas, duracion=DURACION_PREDETERMINADA,
                           reservacion=None):
        """Mesas libres en este momento para quienes acaban de llegar."""
        return self.disponibilidad.mesas_disponibles(
            self.ahora, duracion, cantidad_personas, excluir_reservacion=reservacion)

    def problema_con_mesa_reservada(self, reservacion, cantidad_personas):
        """CU-03 pasos 5 y 6: ¿la mesa reservada sirve para los que llegaron?"""
        mesa = reservacion.mesa
        if not mesa.activo:
            return f'La mesa {mesa.numero} reservada está deshabilitada.'
        if not mesa.admite(cantidad_personas):
            return (f'Llegaron {cantidad_personas} personas y la mesa {mesa.numero} '
                    f'admite {mesa.capacidad}.')
        if Atencion.abierta_de(mesa):
            return f'La mesa {mesa.numero} sigue ocupada por una atención anterior.'
        return None

    @transaction.atomic
    def registrar_con_reservacion(self, reservacion, cantidad_personas, mesa=None):
        reservacion = Reservacion.objects.select_for_update().get(pk=reservacion.pk)
        reservacion.exigir_programada('atenderse')
        hoy = timezone.localdate(self.ahora)
        if timezone.localdate(reservacion.fecha_hora_inicio) != hoy:
            raise ReglaNegocioError(
                'Solo se registra el ingreso de reservaciones programadas para hoy. '
                f'Esta reservación es para el {timezone.localtime(reservacion.fecha_hora_inicio):%d/%m/%Y}.',
                code='reservacion_otro_dia')

        mesa = mesa or reservacion.mesa
        mesa = Mesa.objects.select_for_update().get(pk=mesa.pk)
        if mesa.pk == reservacion.mesa_id:
            problema = self.problema_con_mesa_reservada(reservacion, cantidad_personas)
        else:
            problema = self.disponibilidad.motivo_no_disponible(
                mesa, self.ahora, reservacion.duracion_estimada, cantidad_personas,
                excluir_reservacion=reservacion)
        if problema:
            raise MesaNoDisponibleError(problema + ' Asigne otra mesa disponible.',
                                        code='mesa_no_disponible')

        atencion = self._abrir(mesa, cantidad_personas, reservacion.duracion_estimada,
                               cliente=reservacion.cliente, reservacion=reservacion)
        reservacion.marcar_atendida()
        return atencion

    @transaction.atomic
    def registrar_sin_reservacion(self, mesa, cantidad_personas, cliente=None):
        mesa = Mesa.objects.select_for_update().get(pk=mesa.pk)
        motivo = self.disponibilidad.motivo_no_disponible(
            mesa, self.ahora, DURACION_PREDETERMINADA, cantidad_personas)
        if motivo:
            raise MesaNoDisponibleError(motivo + ' Elija otra de las mesas disponibles.',
                                        code='mesa_no_disponible')
        return self._abrir(mesa, cantidad_personas, DURACION_PREDETERMINADA, cliente=cliente)

    def _abrir(self, mesa, cantidad_personas, duracion, cliente=None, reservacion=None):
        atencion = Atencion(
            mesa=mesa, cliente=cliente, reservacion=reservacion,
            fecha_hora_ingreso=self.ahora, duracion_estimada=duracion,
            cantidad_personas=cantidad_personas,
            registrada_por=self.usuario if getattr(self.usuario, 'is_authenticated', False) else None,
        )
        atencion.full_clean(validate_constraints=False)
        atencion.save()
        return atencion
