from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import CategoriaForm, ClienteForm, MesaForm, ProductoForm
from .models import CategoriaProducto, Cliente, Mesa, Producto


def _ubicaciones():
    return (Mesa.objects.exclude(ubicacion='').values_list('ubicacion', flat=True)
            .distinct().order_by('ubicacion'))


# --- CU-16 a CU-19: mesas -----------------------------------------------------

@login_required
@permission_required('administracion.view_mesa', raise_exception=True)
def lista_mesas(request):
    from reservaciones.models import Atencion
    ocupadas = set(Atencion.objects.abiertas().values_list('mesa_id', flat=True))
    hoy = timezone.localdate()
    mesas = Mesa.objects.annotate(
        reservaciones_hoy=Count('reservaciones', filter=Q(reservaciones__estado='PROGRAMADA',
                                                          reservaciones__fecha_hora_inicio__date=hoy)),
    ).order_by('numero')
    filas = [{'mesa': m, 'ocupada': m.pk in ocupadas} for m in mesas]
    return render(request, 'administracion/lista_mesas.html', {
        'filas': filas,
        'total_activas': sum(1 for f in filas if f['mesa'].activo),
        'capacidad_total': sum(f['mesa'].capacidad for f in filas if f['mesa'].activo),
    })


@login_required
@permission_required('administracion.view_mesa', raise_exception=True)
def detalle_mesa(request, id):
    mesa = get_object_or_404(Mesa, pk=id)
    return render(request, 'administracion/detalle_mesa.html', {
        'mesa': mesa,
        'atencion': mesa.atencion_abierta,
        'pendientes': mesa.reservaciones_pendientes()[:20],
        'motivo_no_deshabilitar': mesa.motivo_para_no_deshabilitar() if mesa.activo else None,
    })


@login_required
@permission_required('administracion.add_mesa', raise_exception=True)
def crear_mesa(request):
    siguiente = (Mesa.objects.order_by('-numero').values_list('numero', flat=True).first() or 0) + 1
    form = MesaForm(request.POST or None, initial={'numero': siguiente, 'capacidad': 4})
    if request.method == 'POST' and form.is_valid():
        mesa = form.save()
        messages.success(request, f'Mesa {mesa.numero} registrada con capacidad para {mesa.capacidad} personas.')
        return redirect('administracion:detalle_mesa', id=mesa.pk)
    return render(request, 'administracion/form_mesa.html', {
        'form': form, 'titulo': 'Registrar mesa', 'ubicaciones': _ubicaciones()})


@login_required
@permission_required('administracion.change_mesa', raise_exception=True)
def editar_mesa(request, id):
    mesa = get_object_or_404(Mesa, pk=id)
    form = MesaForm(request.POST or None, instance=mesa)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Mesa {mesa.numero} actualizada correctamente.')
        return redirect('administracion:detalle_mesa', id=mesa.pk)
    return render(request, 'administracion/form_mesa.html', {
        'form': form, 'mesa': mesa, 'titulo': f'Modificar mesa {mesa.numero}', 'ubicaciones': _ubicaciones()})


@login_required
@permission_required('administracion.change_mesa', raise_exception=True)
@require_POST
def deshabilitar_mesa(request, id):
    mesa = get_object_or_404(Mesa, pk=id)
    try:
        mesa.deshabilitar()
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    else:
        messages.success(request, f'Mesa {mesa.numero} deshabilitada. Ya no se ofrecerá en reservaciones ni ingresos.')
    return redirect('administracion:detalle_mesa', id=mesa.pk)


@login_required
@permission_required('administracion.change_mesa', raise_exception=True)
@require_POST
def habilitar_mesa(request, id):
    mesa = get_object_or_404(Mesa, pk=id)
    mesa.habilitar()
    messages.success(request, f'Mesa {mesa.numero} habilitada nuevamente.')
    return redirect('administracion:detalle_mesa', id=mesa.pk)


# --- CU-24 y CU-25: clientes --------------------------------------------------

@login_required
@permission_required('administracion.view_cliente', raise_exception=True)
def lista_clientes(request):
    q = request.GET.get('q', '').strip()
    clientes = Cliente.objects.annotate(total_reservaciones=Count('reservaciones', distinct=True),
                                        total_visitas=Count('atenciones', distinct=True))
    if q:
        digitos = ''.join(c for c in q if c.isdigit())
        condicion = Q(nombre__icontains=q)
        if len(digitos) >= 3:
            condicion |= Q(telefono__contains=digitos[:4]) if len(digitos) <= 4 else \
                Q(telefono__contains=f'{digitos[:4]}-{digitos[4:8]}')
        clientes = clientes.filter(condicion)
    return render(request, 'administracion/lista_clientes.html', {
        'clientes': clientes.order_by('nombre')[:300], 'q': q, 'total': Cliente.objects.count()})


@login_required
@permission_required('administracion.view_cliente', raise_exception=True)
def detalle_cliente(request, id):
    cliente = get_object_or_404(Cliente, pk=id)
    reservaciones = cliente.reservaciones.select_related('mesa').order_by('-fecha_hora_inicio')[:50]
    atenciones = cliente.atenciones.select_related('mesa', 'reservacion').order_by('-fecha_hora_ingreso')[:50]
    return render(request, 'administracion/detalle_cliente.html', {
        'cliente': cliente, 'reservaciones': reservaciones, 'atenciones': atenciones,
        'canceladas': cliente.reservaciones.filter(estado='CANCELADA').count(),
    })


@login_required
@permission_required('administracion.add_cliente', raise_exception=True)
def crear_cliente(request):
    form = ClienteForm(request.POST or None, initial={'activo': True})
    if request.method == 'POST' and form.is_valid():
        cliente = form.save()
        messages.success(request, f'Cliente {cliente.nombre} registrado.')
        return redirect('administracion:detalle_cliente', id=cliente.pk)
    return render(request, 'administracion/form_cliente.html', {'form': form, 'titulo': 'Registrar cliente'})


@login_required
@permission_required('administracion.change_cliente', raise_exception=True)
def editar_cliente(request, id):
    cliente = get_object_or_404(Cliente, pk=id)
    form = ClienteForm(request.POST or None, instance=cliente)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Datos de {cliente.nombre} actualizados.')
        return redirect('administracion:detalle_cliente', id=cliente.pk)
    return render(request, 'administracion/form_cliente.html', {
        'form': form, 'cliente': cliente, 'titulo': f'Modificar cliente'})


# --- Categorías y productos del menú ---

@login_required
@permission_required('administracion.view_categoriaproducto', raise_exception=True)
def lista_categorias(request):
    return render(request, 'administracion/categorias/lista.html',
                  {'categorias': CategoriaProducto.objects.all()})


@login_required
@permission_required('administracion.add_categoriaproducto', raise_exception=True)
def crear_categoria(request):
    form = CategoriaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Categoría registrada correctamente.')
        return redirect('administracion:lista_categorias')
    return render(request, 'administracion/categorias/form.html', {'form': form, 'accion': 'Registrar'})


@login_required
@permission_required('administracion.change_categoriaproducto', raise_exception=True)
def editar_categoria(request, id):
    categoria = get_object_or_404(CategoriaProducto, pk=id)
    form = CategoriaForm(request.POST or None, instance=categoria)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Categoría actualizada correctamente.')
        return redirect('administracion:lista_categorias')
    return render(request, 'administracion/categorias/form.html',
                  {'form': form, 'accion': 'Modificar', 'categoria': categoria})


@login_required
@permission_required('administracion.change_categoriaproducto', raise_exception=True)
def alternar_categoria(request, id):
    """Deshabilita o habilita una categoría (nunca se elimina)."""
    categoria = get_object_or_404(CategoriaProducto, pk=id)
    if request.method == 'POST':
        categoria.activo = not categoria.activo
        categoria.save(update_fields=['activo', 'fecha_modificacion'])
        messages.success(
            request,
            f'Categoría {"habilitada" if categoria.activo else "deshabilitada"} correctamente.',
        )
        return redirect('administracion:lista_categorias')
    if not categoria.activo:
        accion, boton = 'habilitar', 'Sí, habilitar'
        aviso = 'Volverá a poder asignarse a productos.'
    else:
        accion, boton = 'deshabilitar', 'Sí, deshabilitar'
        aviso = 'No podrá asignarse a productos nuevos; los existentes la conservan.'
    return render(request, 'administracion/confirmar.html', {
        'titulo': f'{accion.capitalize()} categoría',
        'pregunta': f'¿Deseas {accion} la categoría «{categoria.nombre}»?',
        'aviso': aviso, 'boton': boton,
        'cancelar_url': 'administracion:lista_categorias',
    })


@login_required
@permission_required('administracion.view_producto', raise_exception=True)
def lista_productos(request):                               # CU-09 / consulta del menú
    productos = Producto.objects.select_related('categoria')
    categoria = request.GET.get('categoria', '')
    if categoria.isdigit():
        productos = productos.filter(categoria_id=int(categoria))
    return render(request, 'administracion/productos/lista.html', {
        'productos': productos,
        'categorias': CategoriaProducto.objects.all(),
        'categoria_sel': categoria,
        'hay_productos': Producto.objects.exists(),
    })


@login_required
@permission_required('administracion.view_producto', raise_exception=True)
def detalle_producto(request, id):
    producto = get_object_or_404(Producto.objects.select_related('categoria'), pk=id)
    return render(request, 'administracion/productos/detalle.html', {'producto': producto})


@login_required
@permission_required('administracion.add_producto', raise_exception=True)
def crear_producto(request):                                # CU-20
    form = ProductoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        producto = form.save()
        messages.success(request, f'Producto «{producto.nombre}» registrado correctamente.')
        return redirect('administracion:lista_productos')
    return render(request, 'administracion/productos/form.html', {
        'form': form, 'accion': 'Registrar',
        'sin_categorias': not CategoriaProducto.objects.filter(activo=True).exists(),
    })


@login_required
@permission_required('administracion.change_producto', raise_exception=True)
def editar_producto(request, id):                           # CU-21
    producto = get_object_or_404(Producto, pk=id)
    form = ProductoForm(request.POST or None, instance=producto)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Producto «{producto.nombre}» actualizado correctamente.')
        return redirect('administracion:detalle_producto', id=producto.pk)
    return render(request, 'administracion/productos/form.html',
                  {'form': form, 'accion': 'Modificar', 'producto': producto})


@login_required
@permission_required('administracion.change_producto', raise_exception=True)
@require_POST
def cambiar_disponibilidad(request, id):                    # CU-22
    producto = get_object_or_404(Producto, pk=id)
    if not producto.activo:
        messages.error(request, 'Un producto deshabilitado no puede cambiar su disponibilidad.')
    else:
        producto.alternar_disponibilidad()
        estado = 'disponible' if producto.disponible else 'no disponible'
        messages.success(request, f'«{producto.nombre}» ahora está {estado}.')
    destino = request.POST.get('next', '')
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect('administracion:lista_productos')


@login_required
@permission_required('administracion.change_producto', raise_exception=True)
def deshabilitar_producto(request, id):                     # CU-23
    producto = get_object_or_404(Producto, pk=id)
    if request.method == 'POST':
        producto.deshabilitar()
        messages.success(request, f'Producto «{producto.nombre}» deshabilitado correctamente.')
        return redirect('administracion:lista_productos')
    return render(request, 'administracion/confirmar.html', {
        'titulo': 'Deshabilitar producto',
        'pregunta': f'¿Deseas deshabilitar «{producto.nombre}»?',
        'aviso': 'Dejará de ofrecerse en el menú. Su registro histórico se conserva.',
        'boton': 'Sí, deshabilitar',
        'cancelar_url': 'administracion:detalle_producto', 'cancelar_id': producto.pk,
    })


@login_required
@permission_required('administracion.change_producto', raise_exception=True)
@require_POST
def habilitar_producto(request, id):
    producto = get_object_or_404(Producto, pk=id)
    producto.habilitar()
    messages.success(request, f'Producto «{producto.nombre}» habilitado nuevamente.')
    return redirect('administracion:detalle_producto', id=producto.pk)
