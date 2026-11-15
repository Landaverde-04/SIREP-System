"""Adaptador entre los pedidos reales y el cálculo independiente aprobado."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError

from pedidos.models import DetallePedido, Pedido

from .consumo import ConsumoCalculado, DetalleConsumo, ServicioConsumo
from .excepciones import ConsumoInvalidoError
from .pagos import validar_importe


@dataclass(frozen=True, slots=True)
class LineaConsumoPedido:
    origen: DetallePedido
    nombre_producto: str
    consumo: DetalleConsumo

    @property
    def cantidad(self):
        return self.consumo.cantidad

    @property
    def precio_unitario(self):
        return self.consumo.precio_unitario

    @property
    def subtotal(self):
        return self.consumo.subtotal

    @property
    def entregado(self):
        return self.origen.pedido.estado == Pedido.Estado.ENTREGADO

    @property
    def estado_pedido(self):
        return self.origen.pedido.estado

    @property
    def estado_pedido_display(self):
        return self.origen.pedido.get_estado_display()


@dataclass(frozen=True, slots=True)
class ConsumoAtencion:
    lineas: tuple[LineaConsumoPedido, ...]
    calculo: ConsumoCalculado
    pendientes: tuple[Pedido, ...]

    @property
    def total(self):
        return self.calculo.total

    @property
    def puede_cobrarse(self):
        return bool(self.lineas) and not self.pendientes


@dataclass(frozen=True, slots=True)
class ConsultaConsumoAtencion:
    """Consulta ampliada; el estimado informativo no se utiliza al registrar pagos."""

    entregado: ConsumoAtencion
    lineas_solicitadas: tuple[LineaConsumoPedido, ...]
    estimado: ConsumoCalculado

    @property
    def lineas(self):
        return self.entregado.lineas

    @property
    def total(self):
        return self.entregado.total

    @property
    def total_estimado(self):
        return self.estimado.total

    @property
    def pendientes(self):
        return self.entregado.pendientes

    @property
    def puede_cobrarse(self):
        return self.entregado.puede_cobrarse


class AdaptadorConsumoPedidos:
    def consultar(self, atencion):
        pedidos = list(Pedido.objects.filter(atencion=atencion).order_by('pk'))
        solicitados = [p.pk for p in pedidos if p.estado != Pedido.Estado.CANCELADO]
        detalles = list(DetallePedido.objects.filter(pedido_id__in=solicitados)
                        .select_related('producto').order_by('pedido_id', 'pk'))
        pedidos_por_id = {pedido.pk: pedido for pedido in pedidos}
        for detalle in detalles:
            # La etiqueta y los totales usan los mismos estados leídos en esta
            # consulta, aunque cocina avance un pedido entre ambas lecturas.
            detalle.pedido = pedidos_por_id[detalle.pedido_id]
        entregado = self.desde_datos(pedidos, detalles)
        lineas = tuple(self.crear_linea(detalle) for detalle in detalles)
        estimado = ServicioConsumo().calcular(linea.consumo for linea in lineas)
        return ConsultaConsumoAtencion(entregado, lineas, estimado)

    def crear_linea(self, detalle):
        try:
            consumo = DetalleConsumo(detalle.cantidad, detalle.precio_unitario)
        except ValueError as error:
            raise ConsumoInvalidoError(
                f'El detalle #{detalle.pk} del pedido #{detalle.pedido_id} tiene cantidad o precio '
                'histórico inválido. No es posible calcular un total completo. Revise el pedido.',
                code='consumo_invalido',
            ) from error
        return LineaConsumoPedido(detalle, detalle.producto.nombre, consumo)

    def desde_datos(self, pedidos, detalles):
        """También acepta filas ya bloqueadas por el servicio transaccional."""
        pedidos = tuple(pedidos)
        if any(p.estado not in Pedido.Estado.values for p in pedidos):
            raise ConsumoInvalidoError('Hay un pedido con estado desconocido. Revíselo antes de cobrar.')
        entregados = {p.pk for p in pedidos if p.estado == Pedido.Estado.ENTREGADO}
        lineas = tuple(self.crear_linea(d) for d in detalles if d.pedido_id in entregados)
        if entregados - {linea.origen.pedido_id for linea in lineas}:
            raise ConsumoInvalidoError('Hay un pedido entregado sin productos. No se puede confirmar su consumo.')
        calculo = ServicioConsumo().calcular(linea.consumo for linea in lineas)
        if lineas:
            try:
                validar_importe(calculo.total, 'total')
            except ValidationError as error:
                raise ConsumoInvalidoError('El consumo excede el importe admitido para un cobro.') from error
        pendientes = tuple(p for p in pedidos if p.estado in Pedido.ESTADOS_EN_CURSO)
        return ConsumoAtencion(lineas, calculo, pendientes)
