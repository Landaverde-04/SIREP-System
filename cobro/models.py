"""Historial financiero de una atención, separado de los pedidos operativos."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import ModeloBase

from .consumo import DetalleConsumo
from .pagos import FormaPago, validar_pago


MENSAJE_INMUTABLE = 'El historial de cobros confirmado no puede modificarse ni eliminarse.'


class HistorialQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(MENSAJE_INMUTABLE)

    def delete(self):
        raise ValidationError(MENSAJE_INMUTABLE)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(MENSAJE_INMUTABLE)

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                    update_conflicts=False, update_fields=None, unique_fields=None):
        if update_conflicts:
            raise ValidationError(MENSAJE_INMUTABLE)
        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts, update_fields=update_fields, unique_fields=unique_fields,
        )


class RegistroInmutable(ModeloBase):
    objects = HistorialQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding or kwargs.get('force_update'):
            raise ValidationError(MENSAJE_INMUTABLE)
        self.full_clean()
        # Un objeto nuevo con PK explícita tampoco debe sobrescribir un registro.
        kwargs['force_insert'] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(MENSAJE_INMUTABLE)


class Cobro(RegistroInmutable):
    FormaPago = FormaPago

    atencion = models.OneToOneField(
        'reservaciones.Atencion', on_delete=models.PROTECT, related_name='cobro',
        verbose_name='atención',
    )
    total = models.DecimalField(max_digits=14, decimal_places=2,
                                validators=[MinValueValidator(Decimal('0.01'))])
    monto_recibido = models.DecimalField('monto recibido', max_digits=14, decimal_places=2,
                                         validators=[MinValueValidator(Decimal('0.01'))])
    forma_pago = models.CharField('forma de pago', max_length=8, choices=FormaPago.choices)
    fecha_hora_pago = models.DateTimeField('fecha y hora de pago', default=timezone.now, editable=False)
    cajero = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name='cobros_registrados')

    class Meta:
        verbose_name = 'cobro'
        verbose_name_plural = 'cobros'
        ordering = ['-fecha_hora_pago', '-id']
        default_permissions = ('add', 'view')
        constraints = [
            models.CheckConstraint(condition=Q(total__gt=0), name='cobro_total_positivo'),
            models.CheckConstraint(
                condition=(Q(forma_pago='EFECTIVO', monto_recibido__gte=F('total'))
                           | Q(forma_pago__in=['TARJETA', 'OTRO'], monto_recibido=F('total'))),
                name='cobro_pago_completo_valido',
            ),
        ]

    def __str__(self):
        return f'Cobro #{self.pk} · Atención {self.atencion_id}'

    @property
    def cambio(self):
        return self.monto_recibido - self.total

    def clean(self):
        super().clean()
        validar_pago(self.total, self.monto_recibido, self.forma_pago)
        if self._state.adding and self.atencion_id and not self.atencion.esta_abierta:
            raise ValidationError('Solo puede registrarse un cobro para una atención abierta.')


class DetalleCobro(RegistroInmutable):
    cobro = models.ForeignKey(Cobro, on_delete=models.PROTECT, related_name='detalles')
    detalle_pedido = models.OneToOneField(
        'pedidos.DetallePedido', on_delete=models.PROTECT, related_name='detalle_cobro',
        verbose_name='detalle de pedido original',
    )
    nombre_producto = models.CharField('producto al cobrar', max_length=100)
    cantidad = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    precio_unitario = models.DecimalField('precio unitario histórico', max_digits=8, decimal_places=2,
                                          validators=[MinValueValidator(Decimal('0.01'))])

    class Meta:
        verbose_name = 'detalle de cobro'
        verbose_name_plural = 'detalles de cobro'
        ordering = ['id']
        default_permissions = ()
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gte=1), name='cobro_detalle_cantidad_positiva'),
            models.CheckConstraint(condition=Q(precio_unitario__gt=0), name='cobro_detalle_precio_positivo'),
        ]

    def __str__(self):
        return f'{self.cantidad} × {self.nombre_producto}'

    @property
    def subtotal(self):
        return DetalleConsumo(self.cantidad, self.precio_unitario).subtotal

    def clean(self):
        super().clean()
        if self.cobro_id and self.detalle_pedido_id:
            if not self.cobro.atencion.esta_abierta:
                raise ValidationError('No pueden añadirse detalles a un cobro de una atención cerrada.')
            pedido = self.detalle_pedido.pedido
            if pedido.atencion_id != self.cobro.atencion_id or pedido.estado != pedido.Estado.ENTREGADO:
                raise ValidationError('El detalle debe pertenecer a un pedido entregado de la atención cobrada.')
