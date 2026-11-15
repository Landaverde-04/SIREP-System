"""Cobro completo: bloqueos, validación, historial y cierre en una transacción."""

from django.core.exceptions import PermissionDenied
from django.db import transaction

from administracion.models import Mesa
from pedidos.models import DetallePedido, Pedido
from reservaciones.models import Atencion

from .excepciones import CobroDuplicadoError, ErrorCobro
from .integracion import AdaptadorConsumoPedidos
from .models import Cobro, DetalleCobro
from .pagos import validar_pago


class ServicioCobro:
    @transaction.atomic
    def registrar(self, *, atencion_id, monto_recibido, forma_pago, cajero):
        if (not getattr(cajero, 'is_authenticated', False) or not cajero.is_active
                or not cajero.has_perm('cobro.add_cobro')):
            raise PermissionDenied('No tiene permiso para registrar cobros.')

        # Ingreso/reservaciones bloquean Mesa. Pedidos.guardar bloquea primero
        # Atencion y luego Pedido. El cambio de estado solo bloquea Pedido.
        # Nunca adquirimos una fila anterior de esta cadena después de una posterior.
        mesa_id = Atencion.objects.values_list('mesa_id', flat=True).get(pk=atencion_id)
        # NO KEY UPDATE también permite las comprobaciones FK de un pedido
        # que ya retenía Atencion: FOR UPDATE aquí podría provocar un ciclo
        # Mesa -> Atencion -> FK Mesa al confirmar ese pedido.
        Mesa.objects.select_for_update(no_key=True).get(pk=mesa_id)
        atencion = Atencion.objects.select_for_update(of=('self',)).get(pk=atencion_id)
        if atencion.mesa_id != mesa_id:
            raise ErrorCobro('La mesa de la atención cambió. Actualice la consulta.')
        if Cobro.objects.filter(atencion=atencion).exists():
            raise CobroDuplicadoError('Esta atención ya tiene un cobro registrado.', code='cobro_duplicado')
        if not atencion.esta_abierta:
            raise ErrorCobro('La atención está cerrada y no admite cobros.', code='atencion_cerrada')

        pedidos = list(Pedido.objects.select_for_update(of=('self',))
                       .filter(atencion=atencion).order_by('pk'))
        # Se comprueba después de bloquear, incluso si la consulta previa decía otra cosa.
        if any(p.estado in Pedido.ESTADOS_EN_CURSO for p in pedidos):
            raise ErrorCobro(
                'No se puede cobrar: hay pedidos pendientes, en preparación o listos para entregar.',
                code='pedidos_pendientes',
            )
        detalles = list(DetallePedido.objects.select_for_update(of=('self',))
                        .filter(pedido_id__in=[p.pk for p in pedidos])
                        .select_related('producto', 'pedido').order_by('pk'))
        consumo = AdaptadorConsumoPedidos().desde_datos(pedidos, detalles)
        if not consumo.lineas:
            raise ErrorCobro('No hay productos entregados para cobrar.', code='sin_consumo')
        validar_pago(consumo.total, monto_recibido, forma_pago)

        cobro = Cobro.objects.create(atencion=atencion, total=consumo.total,
                                      monto_recibido=monto_recibido, forma_pago=forma_pago, cajero=cajero)
        for linea in consumo.lineas:
            DetalleCobro.objects.create(
                cobro=cobro, detalle_pedido=linea.origen, nombre_producto=linea.nombre_producto,
                cantidad=linea.cantidad, precio_unitario=linea.precio_unitario,
            )
        atencion.cerrar()
        return cobro
