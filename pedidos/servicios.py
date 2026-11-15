"""
Lógica de negocio del módulo de pedidos.

Las vistas solo recogen datos y muestran resultados; las reglas viven aquí y
en los modelos (igual que en reservaciones).

- ServicioPedidos.guardar: toma o modifica un pedido (RN-05, RN-06).
- ServicioPedidos.cambiar_estado: avance por cocina y entrega, y cancelación.

Antes de guardar se bloquea la fila de la atención (SELECT ... FOR UPDATE) y se
vuelve a comprobar que siga abierta, de modo que un pedido no se cuele en una
mesa que cobro acaba de cerrar. Del mismo modo, el estado del pedido se lee
bloqueado, para que dos pulsaciones simultáneas no apliquen la misma
transición dos veces.
"""

from django.db import transaction

from reservaciones.models import Atencion
from reservaciones.servicios import ReglaNegocioError

from .models import Pedido


class PedidoNoEditableError(ReglaNegocioError):
    """El pedido ya no está pendiente o su atención se cerró."""


class ServicioPedidos:

    @transaction.atomic
    def guardar(self, form, formset, mesero):
        """
        Guarda el pedido y sus líneas. ``form`` y ``formset`` ya son válidos y
        comparten la misma instancia de Pedido. ``mesero`` solo se asigna al
        crear: quien edita no pasa a ser el autor del pedido.
        """
        pedido = form.instance
        mesa = form.cleaned_data['mesa']

        atencion = (Atencion.objects.select_for_update()
                    .filter(mesa=mesa, estado=Atencion.Estado.ABIERTA).first())
        if atencion is None:
            raise ReglaNegocioError(
                f'La {mesa} ya no tiene una atención abierta. Registre el ingreso del cliente.',
                code='atencion_cerrada')

        if pedido.pk:
            actual = Pedido.objects.select_for_update(of=('self',)).get(pk=pedido.pk)
            if actual.estado != Pedido.Estado.PENDIENTE:
                raise PedidoNoEditableError(
                    f'El pedido #{pedido.pk} ya está {actual.get_estado_display().lower()} '
                    'y no puede modificarse.', code='pedido_no_editable')
        else:
            pedido.mesero = mesero

        pedido = form.save(commit=False)
        pedido.atencion = atencion
        pedido.save()
        formset.save()
        return pedido

    @transaction.atomic
    def cambiar_estado(self, pedido_id, nuevo_estado):
        pedido = (Pedido.objects.select_for_update(of=('self',))
                  .select_related('atencion', 'mesa').get(pk=pedido_id))
        pedido.cambiar_estado(nuevo_estado)
        return pedido
