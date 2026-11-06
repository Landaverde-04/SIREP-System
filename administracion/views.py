"""
Vistas del módulo de Administración.

Casos de uso (Etapa 1) que cubre:
  Mesas      CU-16 consultar · CU-17 registrar · CU-18 modificar · CU-19 deshabilitar
  Menú       CU-20 registrar · CU-21 modificar · CU-22 cambiar disponibilidad
             CU-23 deshabilitar (consultar menú CU-09 es la lista de productos)
  Clientes   CU-24 consultar · CU-25 modificar · CU-04 registrar cliente nuevo
  Extras     categorías de producto (RF-18) y reactivar mesa/producto
             (deshabilitar nunca borra, así que debe poder revertirse).

Permisos: se usan los permisos estándar de Django de cada modelo
(view/add/change); asignarlos al rol Gerente desde Seguridad > Roles.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import CategoriaForm, ClienteForm, MesaForm, ProductoForm
from .models import CategoriaProducto, Cliente, Mesa, Producto


def _perm(codigo):
    """Atajo: login obligatorio + permiso (403 si no lo tiene)."""
    def decorador(vista):
        return login_required(
            permission_required(f'administracion.{codigo}', raise_exception=True)(vista)
        )
    return decorador


# ================================================================ MESAS

@_perm('view_mesa')
def lista_mesas(request):                                   # CU-16
    mesas = Mesa.objects.all()
    estado = request.GET.get('estado', '')
    if estado in Mesa.Estado.values:
        mesas = mesas.filter(estado=estado)
    return render(request, 'administracion/mesas/lista.html', {
        'mesas': mesas,
        'estado': estado,
        'estados': Mesa.Estado.choices,
        'hay_mesas': Mesa.objects.exists(),
    })


@_perm('view_mesa')
def detalle_mesa(request, id):                              # CU-16 (detalle)
    mesa = get_object_or_404(Mesa, pk=id)
    return render(request, 'administracion/mesas/detalle.html', {'mesa': mesa})


@_perm('add_mesa')
def crear_mesa(request):                                    # CU-17
    form = MesaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        mesa = form.save()
        messages.success(request, f'{mesa} registrada correctamente.')
        return redirect('administracion:lista_mesas')
    return render(request, 'administracion/mesas/form.html', {'form': form, 'accion': 'Registrar'})


@_perm('change_mesa')
def editar_mesa(request, id):                               # CU-18
    mesa = get_object_or_404(Mesa, pk=id)
    form = MesaForm(request.POST or None, instance=mesa)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'{mesa} actualizada correctamente.')
        return redirect('administracion:detalle_mesa', id=mesa.pk)
    return render(request, 'administracion/mesas/form.html',
                  {'form': form, 'accion': 'Modificar', 'mesa': mesa})


@_perm('change_mesa')
def deshabilitar_mesa(request, id):                         # CU-19
    mesa = get_object_or_404(Mesa, pk=id)
    if request.method == 'POST':
        try:
            mesa.deshabilitar()
        except ValidationError as e:
            messages.error(request, e.message)
            return redirect('administracion:detalle_mesa', id=mesa.pk)
        messages.success(request, f'{mesa} deshabilitada correctamente.')
        return redirect('administracion:lista_mesas')
    return render(request, 'administracion/confirmar.html', {
        'titulo': 'Deshabilitar mesa',
        'pregunta': f'¿Deseas deshabilitar la {mesa}?',
        'aviso': 'Dejará de estar disponible para reservaciones e ingresos. '
                 'Su registro histórico se conserva.',
        'boton': 'Sí, deshabilitar',
        'cancelar_url': 'administracion:detalle_mesa', 'cancelar_id': mesa.pk,
    })


@require_POST
@_perm('change_mesa')
def habilitar_mesa(request, id):
    mesa = get_object_or_404(Mesa, pk=id)
    mesa.habilitar()
    messages.success(request, f'{mesa} habilitada nuevamente.')
    return redirect('administracion:detalle_mesa', id=mesa.pk)


# ============================================================ CATEGORÍAS

@_perm('view_categoriaproducto')
def lista_categorias(request):
    return render(request, 'administracion/categorias/lista.html',
                  {'categorias': CategoriaProducto.objects.all()})


@_perm('add_categoriaproducto')
def crear_categoria(request):
    form = CategoriaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Categoría registrada correctamente.')
        return redirect('administracion:lista_categorias')
    return render(request, 'administracion/categorias/form.html', {'form': form, 'accion': 'Registrar'})


@_perm('change_categoriaproducto')
def editar_categoria(request, id):
    categoria = get_object_or_404(CategoriaProducto, pk=id)
    form = CategoriaForm(request.POST or None, instance=categoria)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Categoría actualizada correctamente.')
        return redirect('administracion:lista_categorias')
    return render(request, 'administracion/categorias/form.html',
                  {'form': form, 'accion': 'Modificar', 'categoria': categoria})


@_perm('change_categoriaproducto')
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


# ============================================================ PRODUCTOS

@_perm('view_producto')
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


@_perm('view_producto')
def detalle_producto(request, id):
    producto = get_object_or_404(Producto.objects.select_related('categoria'), pk=id)
    return render(request, 'administracion/productos/detalle.html', {'producto': producto})


@_perm('add_producto')
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


@_perm('change_producto')
def editar_producto(request, id):                           # CU-21
    producto = get_object_or_404(Producto, pk=id)
    form = ProductoForm(request.POST or None, instance=producto)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Producto «{producto.nombre}» actualizado correctamente.')
        return redirect('administracion:detalle_producto', id=producto.pk)
    return render(request, 'administracion/productos/form.html',
                  {'form': form, 'accion': 'Modificar', 'producto': producto})


@require_POST
@_perm('change_producto')
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


@_perm('change_producto')
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


@require_POST
@_perm('change_producto')
def habilitar_producto(request, id):
    producto = get_object_or_404(Producto, pk=id)
    producto.habilitar()
    messages.success(request, f'Producto «{producto.nombre}» habilitado nuevamente.')
    return redirect('administracion:detalle_producto', id=producto.pk)


# ============================================================= CLIENTES

@_perm('view_cliente')
def lista_clientes(request):                                # CU-24
    q = request.GET.get('q', '').strip()
    clientes = Cliente.objects.all()
    if q:
        clientes = clientes.filter(Q(nombre__icontains=q) | Q(telefono__icontains=q))
    return render(request, 'administracion/clientes/lista.html', {
        'clientes': clientes, 'q': q, 'hay_clientes': Cliente.objects.exists(),
    })


@_perm('view_cliente')
def detalle_cliente(request, id):                           # CU-24 (detalle)
    cliente = get_object_or_404(Cliente, pk=id)
    return render(request, 'administracion/clientes/detalle.html', {'cliente': cliente})


@_perm('add_cliente')
def crear_cliente(request):                                 # CU-04 (extiende CU-24)
    form = ClienteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cliente = form.save()
        messages.success(request, f'Cliente {cliente.nombre} registrado correctamente.')
        return redirect('administracion:lista_clientes')
    return render(request, 'administracion/clientes/form.html', {'form': form, 'accion': 'Registrar'})


@_perm('change_cliente')
def editar_cliente(request, id):                            # CU-25
    cliente = get_object_or_404(Cliente, pk=id)
    form = ClienteForm(request.POST or None, instance=cliente)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Datos del cliente actualizados correctamente.')
        return redirect('administracion:detalle_cliente', id=cliente.pk)
    return render(request, 'administracion/clientes/form.html',
                  {'form': form, 'accion': 'Modificar', 'cliente': cliente})
