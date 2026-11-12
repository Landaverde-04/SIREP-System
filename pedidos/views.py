from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import DetallePedidoFormSet, PedidoForm
from .models import DetallePedido, Pedido
from .servicios import ServicioPedidos

PEDIDOS_POR_PAGINA = 15

# Columnas del tablero de cocina, en el orden en que avanza un pedido.
COLUMNAS_COCINA = (
    (Pedido.Estado.PENDIENTE, 'Pendientes'),
    (Pedido.Estado.EN_PREPARACION, 'En preparación'),
    (Pedido.Estado.LISTO, 'Listos para entregar'),
)


def _con_detalles():
    """Precarga las líneas (con su producto) para no consultar la base por cada pedido."""
    return Prefetch('detalles', queryset=DetallePedido.objects.select_related('producto'))


def _obtener_pedido(id):
    return get_object_or_404(
        Pedido.objects.select_related('mesa', 'mesero', 'atencion').prefetch_related(_con_detalles()),
        pk=id)


@login_required
@permission_required('pedidos.view_pedido', raise_exception=True)
def lista_pedidos(request):
    estado = request.GET.get('estado', '')
    if estado not in Pedido.Estado.values:
        estado = ''
    pedidos = Pedido.objects.select_related('mesa', 'mesero', 'atencion').con_monto()
    if estado:
        pedidos = pedidos.filter(estado=estado)
    pagina = Paginator(pedidos.order_by('-fecha_creacion', '-id'), PEDIDOS_POR_PAGINA).get_page(
        request.GET.get('page'))
    return render(request, 'pedidos/lista.html', {
        'pagina': pagina,
        'estados': Pedido.Estado.choices,
        'estado_actual': estado,
    })


@login_required
@permission_required('pedidos.view_pedido', raise_exception=True)
def detalle_pedido(request, id):
    pedido = _obtener_pedido(id)
    acciones = [
        accion for accion in pedido.acciones_disponibles
        if request.user.has_perm(Pedido.PERMISOS_ESTADO[accion['estado']])
    ]
    return render(request, 'pedidos/detalle.html', {'pedido': pedido, 'acciones': acciones})


def _procesar_formulario(request, pedido, accion):
    """Lógica común de crear y editar: valida, guarda con el servicio y redirige o vuelve a mostrar."""
    form = PedidoForm(request.POST or None, instance=pedido,
                      initial={'mesa': request.GET.get('mesa')} if request.method == 'GET' else None)
    formset = DetallePedidoFormSet(request.POST or None, instance=pedido)

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        try:
            guardado = ServicioPedidos().guardar(form, formset, request.user)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            if accion == 'Nuevo':
                messages.success(request, f'Pedido #{guardado.pk} registrado para la {guardado.mesa}.')
            else:
                messages.success(request, f'Pedido #{guardado.pk} actualizado.')
            return redirect('pedidos:detalle_pedido', id=guardado.pk)

    return render(request, 'pedidos/form.html', {
        'form': form,
        'formset': formset,
        'accion': accion,
        'pedido': pedido if pedido.pk else None,
        'sin_mesas': not form.fields['mesa'].queryset.exists(),
    })


@login_required
@permission_required('pedidos.add_pedido', raise_exception=True)
def crear_pedido(request):
    return _procesar_formulario(request, Pedido(), 'Nuevo')


@login_required
@permission_required('pedidos.change_pedido', raise_exception=True)
def editar_pedido(request, id):
    pedido = get_object_or_404(Pedido.objects.select_related('mesa', 'atencion'), pk=id)
    if not pedido.editable:
        messages.error(
            request, f'El pedido #{pedido.pk} está {pedido.get_estado_display().lower()} y no puede modificarse.')
        return redirect('pedidos:detalle_pedido', id=pedido.pk)
    return _procesar_formulario(request, pedido, 'Editar')


@login_required
@permission_required('pedidos.view_pedido', raise_exception=True)
def cocina(request):
    """Tablero de preparación: pedidos en curso de atenciones abiertas, los más antiguos primero."""
    pedidos = list(
        Pedido.objects.en_curso().filter(atencion__estado='ABIERTA')
        .select_related('mesa', 'atencion').prefetch_related(_con_detalles())
        .order_by('fecha_creacion', 'id'))
    columnas = [{
        'titulo': titulo,
        'pedidos': [pedido for pedido in pedidos if pedido.estado == estado],
        'puede_avanzar': request.user.has_perm(Pedido.PERMISOS_ESTADO[Pedido.TRANSICIONES[estado][0]]),
    } for estado, titulo in COLUMNAS_COCINA]
    return render(request, 'pedidos/cocina.html', {'columnas': columnas})


@login_required
@require_POST
def cambiar_estado(request, id, estado):
    permiso = Pedido.PERMISOS_ESTADO.get(estado)
    if not permiso or not request.user.has_perm(permiso):
        raise PermissionDenied
    get_object_or_404(Pedido, pk=id)  # 404 si no existe, antes de tocar nada
    try:
        pedido = ServicioPedidos().cambiar_estado(id, estado)
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
        pedido = None
    else:
        messages.success(request, f'Pedido #{pedido.pk}: {pedido.get_estado_display().lower()}.')
    if request.POST.get('volver') == 'cocina':
        return redirect('pedidos:cocina')
    return redirect('pedidos:detalle_pedido', id=id)
