from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce

from core.models import ModeloBase


class PedidoQuerySet(models.QuerySet):
    def con_monto(self):
        """Agrega ``monto``: total del pedido calculado en la base de datos (para listados)."""
        decimal = DecimalField(max_digits=10, decimal_places=2)
        subtotal = ExpressionWrapper(F('detalles__cantidad') * F('detalles__precio_unitario'),
                                     output_field=decimal)
        return self.annotate(monto=Coalesce(Sum(subtotal), Value(Decimal('0.00')), output_field=decimal))

    def en_curso(self):
        """Pedidos que la cocina o el mesero todavía tienen que atender."""
        return self.filter(estado__in=Pedido.ESTADOS_EN_CURSO)

    def facturables(self):
        """Pedidos que cuentan en el consumo de la atención (todos menos los cancelados). Lo usa cobro."""
        return self.exclude(estado=Pedido.Estado.CANCELADO)

    def de_atencion(self, atencion):
        return self.filter(atencion=atencion)


class Pedido(ModeloBase):
    """
    Pedido tomado por un mesero para una mesa con atención abierta (RN-05).

    Estados: Pendiente -> En preparación -> Listo -> Entregado, y Cancelado
    mientras no esté listo. Solo un pedido pendiente puede modificarse: una vez
    que la cocina lo toma, los cambios se hablan con ella, no se editan.

    ``mesa`` se conserva junto a ``atencion`` porque es lo que el mesero elige;
    ``clean()`` mantiene ambas coherentes. El consumo de una visita nunca se
    mezcla con el de otra porque el cobro trabaja siempre sobre la atención.
    """

    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        EN_PREPARACION = 'EN_PREPARACION', 'En preparación'
        LISTO = 'LISTO', 'Listo'
        ENTREGADO = 'ENTREGADO', 'Entregado'
        CANCELADO = 'CANCELADO', 'Cancelado'

    ESTADOS_EN_CURSO = (Estado.PENDIENTE, Estado.EN_PREPARACION, Estado.LISTO)

    # Primero el avance normal; la cancelación, cuando cabe, siempre al final.
    TRANSICIONES = {
        Estado.PENDIENTE: (Estado.EN_PREPARACION, Estado.CANCELADO),
        Estado.EN_PREPARACION: (Estado.LISTO, Estado.CANCELADO),
        Estado.LISTO: (Estado.ENTREGADO,),
        Estado.ENTREGADO: (),
        Estado.CANCELADO: (),
    }

    COLORES = {
        Estado.PENDIENTE: 'warning',
        Estado.EN_PREPARACION: 'info',
        Estado.LISTO: 'success',
        Estado.ENTREGADO: 'secondary',
        Estado.CANCELADO: 'danger',
    }

    ACCIONES = {
        Estado.EN_PREPARACION: {'etiqueta': 'Iniciar preparación', 'clase': 'primary', 'icono': 'bi-fire'},
        Estado.LISTO: {'etiqueta': 'Marcar como listo', 'clase': 'success', 'icono': 'bi-check2-circle'},
        Estado.ENTREGADO: {'etiqueta': 'Marcar como entregado', 'clase': 'dark', 'icono': 'bi-bag-check'},
        Estado.CANCELADO: {'etiqueta': 'Cancelar pedido', 'clase': 'outline-danger',
                           'icono': 'bi-x-circle', 'confirmar': True},
    }

    atencion = models.ForeignKey('reservaciones.Atencion', on_delete=models.PROTECT,
                                 related_name='pedidos', verbose_name='atención')
    mesa = models.ForeignKey('administracion.Mesa', on_delete=models.PROTECT,
                             related_name='pedidos', verbose_name='mesa')
    mesero = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name='pedidos_tomados', verbose_name='mesero')
    estado = models.CharField('estado', max_length=15, choices=Estado.choices,
                              default=Estado.PENDIENTE)
    notas = models.TextField('notas del pedido', blank=True)

    objects = PedidoQuerySet.as_manager()

    class Meta:
        verbose_name = 'pedido'
        verbose_name_plural = 'pedidos'
        ordering = ['-fecha_creacion']
        permissions = [
            ('cambiar_estado_pedido', 'Puede cambiar el estado de los pedidos'),
        ]
        indexes = [models.Index(fields=['estado', 'fecha_creacion'], name='pedido_estado_fecha_idx')]

    def __str__(self):
        return f'Pedido #{self.pk} · {self.mesa}'

    # --- Estado --------------------------------------------------------------

    @property
    def color_estado(self):
        return self.COLORES[self.estado]

    @property
    def editable(self):
        """Solo se modifica un pedido pendiente cuya atención sigue abierta."""
        return self.estado == self.Estado.PENDIENTE and self.atencion.esta_abierta

    def _accion(self, estado):
        return {'estado': estado.value, **self.ACCIONES[estado]}

    @property
    def acciones_disponibles(self):
        """Cambios de estado permitidos desde el estado actual, listos para dibujar botones."""
        return [self._accion(estado) for estado in self.TRANSICIONES[self.estado]
                if estado != self.Estado.CANCELADO or self.atencion.esta_abierta]

    @property
    def accion_siguiente(self):
        """Paso normal de avance (el que usa el tablero de cocina), o None si ya terminó."""
        for estado in self.TRANSICIONES[self.estado]:
            if estado != self.Estado.CANCELADO:
                return self._accion(estado)
        return None

    def cambiar_estado(self, nuevo):
        """Aplica una transición válida o lanza ValidationError con el motivo."""
        if nuevo not in self.Estado.values:
            raise ValidationError('El estado indicado no existe.', code='estado_invalido')
        if nuevo not in self.TRANSICIONES[self.estado]:
            raise ValidationError(
                f'El pedido #{self.pk} está {self.get_estado_display().lower()} y no puede pasar a '
                f'{self.Estado(nuevo).label.lower()}.', code='transicion_invalida')
        if nuevo == self.Estado.CANCELADO and not self.atencion.esta_abierta:
            raise ValidationError('La atención de este pedido ya está cerrada.', code='atencion_cerrada')
        self.estado = nuevo
        self.save(update_fields=['estado', 'fecha_modificacion'])

    # --- Montos --------------------------------------------------------------

    @property
    def total(self):
        # Se suma en Python para aprovechar los detalles precargados.
        return sum((detalle.subtotal for detalle in self.detalles.all()), Decimal('0.00'))

    # --- Validación ----------------------------------------------------------

    def clean(self):
        """RN-05: el pedido pertenece a la atención abierta de su mesa."""
        super().clean()
        if not self.mesa_id:
            return
        if self.atencion_id and self.atencion.mesa_id == self.mesa_id:
            return
        atencion = self.mesa.atencion_abierta
        if atencion is None:
            raise ValidationError(
                {'mesa': f'La {self.mesa} no tiene una atención abierta. Registre primero el ingreso del cliente.'})
        self.atencion = atencion


class DetallePedido(ModeloBase):
    """
    Línea de un pedido. El precio se copia del menú al agregar el producto
    (``precio_unitario``), de modo que un cambio posterior de precio no altere
    pedidos ya tomados ni sus cobros.
    """

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='detalles',
                               verbose_name='pedido')
    producto = models.ForeignKey('administracion.Producto', on_delete=models.PROTECT,
                                 related_name='detalles_pedido', verbose_name='producto')
    cantidad = models.PositiveSmallIntegerField('cantidad', validators=[MinValueValidator(1)])
    nota = models.CharField('nota', max_length=120, blank=True)
    precio_unitario = models.DecimalField('precio unitario', max_digits=8, decimal_places=2,
                                          editable=False)

    class Meta:
        verbose_name = 'detalle de pedido'
        verbose_name_plural = 'detalles de pedido'
        ordering = ['id']
        constraints = [
            models.CheckConstraint(condition=models.Q(cantidad__gte=1), name='detalle_cantidad_minimo_1'),
        ]

    def __str__(self):
        return f'{self.cantidad} x {self.producto}'

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def save(self, *args, **kwargs):
        # Red de seguridad para altas hechas fuera del formulario (consola, pruebas, admin).
        if self.precio_unitario is None:
            self.precio_unitario = self.producto.precio
        super().save(*args, **kwargs)
