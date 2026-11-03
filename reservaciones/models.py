import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import ExpressionWrapper, F, Q
from django.utils import timezone

from core.models import ModeloBase


DURACION_PREDETERMINADA = timedelta(hours=2)
DURACION_MINIMA = timedelta(minutes=30)
DURACION_MAXIMA = timedelta(hours=4)


def validar_duracion(duracion):
    """CU-01 3b / HU-01 CA-4: la duración estimada no puede superar cuatro horas."""
    if duracion is None:
        raise ValidationError('Indique la duración estimada.', code='duracion_requerida')
    if duracion > DURACION_MAXIMA:
        raise ValidationError('La duración máxima permitida es de cuatro horas.', code='duracion_maxima')
    if duracion < DURACION_MINIMA:
        raise ValidationError('La duración mínima es de 30 minutos.', code='duracion_minima')


class PeriodoQuerySet(models.QuerySet):
    """Consultas comunes para objetos que ocupan una mesa durante un período."""

    campo_inicio = None

    def con_fin(self):
        return self.annotate(
            fin_estimado=ExpressionWrapper(
                F(self.campo_inicio) + F('duracion_estimada'),
                output_field=models.DateTimeField(),
            )
        )


class ReservacionQuerySet(PeriodoQuerySet):
    campo_inicio = 'fecha_hora_inicio'

    def programadas(self):
        return self.filter(estado=Reservacion.Estado.PROGRAMADA, activo=True)

    def que_se_cruzan(self, inicio, fin):
        """Reservaciones cuyo período [inicio, fin) se superpone con el indicado (RN-01)."""
        return self.con_fin().filter(fecha_hora_inicio__lt=fin, fin_estimado__gt=inicio)

    def del_dia(self, fecha):
        return self.filter(fecha_hora_inicio__date=fecha)

    def buscar(self, texto):
        """CU-07: busca por código de la reservación, nombre o teléfono del cliente."""
        texto = (texto or '').strip()
        if not texto:
            return self
        condicion = Q(cliente__nombre__icontains=texto)
        if len(texto) >= 3:
            condicion |= Q(codigo__icontains=texto)
        digitos = ''.join(c for c in texto if c.isdigit())
        if len(digitos) >= 4:
            condicion |= Q(cliente__telefono__contains=formatear_digitos(digitos))
        return self.filter(condicion)


def formatear_digitos(digitos):
    """Convierte '77778888' en '7777-8888' para comparar con teléfonos guardados."""
    digitos = digitos[-8:] if len(digitos) > 8 else digitos
    if len(digitos) > 4:
        return f'{digitos[:4]}-{digitos[4:]}'
    return digitos


class Reservacion(ModeloBase):
    """
    Compromiso de una mesa para un cliente durante un período (CU-01).

    Estados: Programada -> Atendida (al registrar el ingreso, CU-03)
                        -> Cancelada (CU-06)
    Solo las reservaciones programadas comprometen la mesa y pueden
    modificarse o cancelarse.
    """

    class Estado(models.TextChoices):
        PROGRAMADA = 'PROGRAMADA', 'Programada'
        ATENDIDA = 'ATENDIDA', 'Atendida'
        CANCELADA = 'CANCELADA', 'Cancelada'

    ALFABETO_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

    codigo = models.CharField('código', max_length=10, unique=True, editable=False)
    cliente = models.ForeignKey('administracion.Cliente', on_delete=models.PROTECT,
                                related_name='reservaciones', verbose_name='cliente')
    mesa = models.ForeignKey('administracion.Mesa', on_delete=models.PROTECT,
                             related_name='reservaciones', verbose_name='mesa')
    fecha_hora_inicio = models.DateTimeField('fecha y hora de inicio')
    duracion_estimada = models.DurationField('duración estimada', default=DURACION_PREDETERMINADA,
                                             validators=[validar_duracion])
    cantidad_personas = models.PositiveSmallIntegerField('cantidad de personas',
                                                         validators=[MinValueValidator(1)])
    estado = models.CharField('estado', max_length=10, choices=Estado.choices,
                              default=Estado.PROGRAMADA)
    motivo_cancelacion = models.CharField('motivo de cancelación', max_length=255, blank=True)
    fecha_hora_cancelacion = models.DateTimeField('fecha y hora de cancelación', null=True, blank=True)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       null=True, blank=True, related_name='reservaciones_registradas',
                                       verbose_name='registrada por')

    objects = ReservacionQuerySet.as_manager()

    class Meta:
        verbose_name = 'reservación'
        verbose_name_plural = 'reservaciones'
        ordering = ['fecha_hora_inicio']
        permissions = [
            ('cancelar_reservacion', 'Puede cancelar reservaciones'),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_personas__gte=1),
                                   name='reservacion_personas_minimo_1'),
        ]

    def __str__(self):
        return f'{self.codigo} · {self.cliente.nombre} · Mesa {self.mesa.numero}'

    # --- Período -------------------------------------------------------------

    @property
    def fecha_hora_fin(self):
        return self.fecha_hora_inicio + self.duracion_estimada

    def se_cruza_con(self, inicio, fin):
        return self.fecha_hora_inicio < fin and self.fecha_hora_fin > inicio

    # --- Estado --------------------------------------------------------------

    @property
    def esta_programada(self):
        return self.estado == self.Estado.PROGRAMADA

    def exigir_programada(self, accion):
        """CU-05 2b / CU-06 2b: solo se operan reservaciones programadas."""
        if not self.esta_programada:
            raise ValidationError(
                f'Solo pueden {accion} reservaciones programadas. '
                f'Esta reservación está {self.get_estado_display().lower()}.',
                code='reservacion_no_programada',
            )

    def cancelar(self, motivo=''):
        """CU-06: deja constancia de la cancelación y libera la mesa en ese período."""
        self.exigir_programada('cancelarse')
        self.estado = self.Estado.CANCELADA
        self.motivo_cancelacion = (motivo or '').strip()
        self.fecha_hora_cancelacion = timezone.now()
        self.save(update_fields=['estado', 'motivo_cancelacion', 'fecha_hora_cancelacion',
                                 'fecha_modificacion'])

    def marcar_atendida(self):
        """CU-03 paso 8: la reservación se concreta en una atención."""
        self.exigir_programada('atenderse')
        self.estado = self.Estado.ATENDIDA
        self.save(update_fields=['estado', 'fecha_modificacion'])

    # --- Validación y guardado -----------------------------------------------

    def clean(self):
        super().clean()
        if self.mesa_id and self.cantidad_personas and not self.mesa.admite(self.cantidad_personas):
            raise ValidationError(
                {'mesa': f'La mesa {self.mesa.numero} admite {self.mesa.capacidad} personas; '
                         f'la reservación es para {self.cantidad_personas}.'}
            )

    @classmethod
    def generar_codigo(cls):
        """Código corto y fácil de dictar por teléfono, por ejemplo R-7K3PQ."""
        while True:
            codigo = 'R-' + ''.join(secrets.choice(cls.ALFABETO_CODIGO) for _ in range(5))
            if not cls.objects.filter(codigo=codigo).exists():
                return codigo

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = self.generar_codigo()
        super().save(*args, **kwargs)


class AtencionQuerySet(PeriodoQuerySet):
    campo_inicio = 'fecha_hora_ingreso'

    def abiertas(self):
        return self.filter(estado=Atencion.Estado.ABIERTA)


class Atencion(ModeloBase):
    """
    Visita concreta de un cliente a una mesa: se abre al registrar el ingreso
    (CU-03) y se cierra al registrar el cobro (CU-15).

    Es el punto de unión entre módulos: los pedidos (módulo de pedidos) y el
    cobro (módulo de cobro) se asocian a una atención, de modo que el consumo
    de visitas distintas en la misma mesa nunca se mezcla.

    Mientras una atención está abierta, su mesa está ocupada.
    """

    class Estado(models.TextChoices):
        ABIERTA = 'ABIERTA', 'Abierta'
        CERRADA = 'CERRADA', 'Cerrada'

    mesa = models.ForeignKey('administracion.Mesa', on_delete=models.PROTECT,
                             related_name='atenciones', verbose_name='mesa')
    cliente = models.ForeignKey('administracion.Cliente', on_delete=models.PROTECT,
                                null=True, blank=True, related_name='atenciones',
                                verbose_name='cliente')
    reservacion = models.OneToOneField(Reservacion, on_delete=models.PROTECT,
                                       null=True, blank=True, related_name='atencion',
                                       verbose_name='reservación')
    fecha_hora_ingreso = models.DateTimeField('fecha y hora de ingreso', default=timezone.now)
    duracion_estimada = models.DurationField('duración estimada', default=DURACION_PREDETERMINADA)
    cantidad_personas = models.PositiveSmallIntegerField('cantidad de personas',
                                                         validators=[MinValueValidator(1)])
    estado = models.CharField('estado', max_length=10, choices=Estado.choices,
                              default=Estado.ABIERTA)
    fecha_hora_cierre = models.DateTimeField('fecha y hora de cierre', null=True, blank=True)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       null=True, blank=True, related_name='atenciones_registradas',
                                       verbose_name='registrada por')

    objects = AtencionQuerySet.as_manager()

    class Meta:
        verbose_name = 'atención'
        verbose_name_plural = 'atenciones'
        ordering = ['-fecha_hora_ingreso']
        constraints = [
            # Una mesa no puede tener dos atenciones abiertas al mismo tiempo.
            models.UniqueConstraint(fields=['mesa'], condition=Q(estado='ABIERTA'),
                                    name='una_atencion_abierta_por_mesa',
                                    violation_error_message='La mesa ya tiene una atención abierta.'),
        ]

    def __str__(self):
        return f'Atención {self.pk} · Mesa {self.mesa.numero} · {self.get_estado_display()}'

    @property
    def esta_abierta(self):
        return self.estado == self.Estado.ABIERTA

    @property
    def fin_estimado(self):
        return self.fecha_hora_ingreso + self.duracion_estimada

    @classmethod
    def abierta_de(cls, mesa):
        """Atención en curso de una mesa, o None. Útil para pedidos (RN-05) y cobro."""
        return cls.objects.abiertas().filter(mesa=mesa).first()

    def cerrar(self):
        """
        Cierra la atención y, con ello, libera la mesa. La invoca el módulo de
        cobro una vez registrado el pago (RN-09).
        """
        if not self.esta_abierta:
            raise ValidationError('La atención ya está cerrada.', code='atencion_cerrada')
        self.estado = self.Estado.CERRADA
        self.fecha_hora_cierre = timezone.now()
        self.save(update_fields=['estado', 'fecha_hora_cierre', 'fecha_modificacion'])
