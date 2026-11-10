from itertools import groupby
from urllib.parse import urlsplit

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.models import Group, Permission
from django.db.models import Count, Min, Q, Value
from django.db.models.functions import Concat
from django.core.paginator import Paginator
from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers

from .models import Empleado, Usuario
from .forms import EmpleadoCrearForm, UsuarioCrearForm, UsuarioEditarForm, RolForm, ResetearPasswordForm, APPS_NEGOCIO


_ACCIONES_ES = {
    'add': 'Agregar',
    'change': 'Modificar',
    'delete': 'Eliminar',
    'view': 'Ver',
}


def _permisos_agrupados():
    permisos = Permission.objects.filter(
        content_type__app_label__in=APPS_NEGOCIO
    ).select_related('content_type').order_by('content_type__app_label', 'codename')
    resultado = []
    for app_label, grupo in groupby(permisos, key=lambda p: p.content_type.app_label):
        items = []
        for p in grupo:
            accion = p.codename.split('_')[0]
            label = f"{_ACCIONES_ES.get(accion, accion)} {p.content_type.model}"
            items.append({'pk': p.pk, 'label': label})
        resultado.append((app_label, items))
    return resultado


@login_required
@permission_required('seguridad.view_usuario', raise_exception=True)
@never_cache
@vary_on_headers('X-Requested-With')
def lista_usuarios(request):
    consulta = request.GET.get('q', '').strip()
    consulta_aplicada = consulta if len(consulta) >= 2 else ''
    estado = request.GET.get('estado', 'activo')
    if estado not in {'activo', 'inactivo'}:
        estado = 'activo'
    usuarios = Usuario.objects.filter(is_active=(estado == 'activo')).prefetch_related('groups')
    if consulta_aplicada:
        usuarios = usuarios.annotate(nombre_completo=Concat('first_name', Value(' '), 'last_name')).filter(
            Q(nombre_completo__icontains=consulta_aplicada)
            | Q(username__icontains=consulta_aplicada)
            | Q(first_name__icontains=consulta_aplicada)
            | Q(last_name__icontains=consulta_aplicada)
            | Q(email__icontains=consulta_aplicada)
        )

    ordenes = {
        'usuario': ('Usuario', ('username',)),
        'nombre': ('Nombre completo', ('first_name', 'last_name')),
        'correo': ('Correo', ('email',)),
        'roles': ('Roles', ('primer_rol',)),
        'estado': ('Estado', ('is_active',)),
    }
    ordenar = request.GET.get('ordenar', 'usuario')
    if ordenar not in ordenes:
        ordenar = 'usuario'
    direccion = 'desc' if request.GET.get('direccion') == 'desc' else 'asc'
    if ordenar == 'roles':
        # Un usuario con varios roles debe seguir ocupando una sola fila.
        usuarios = usuarios.annotate(primer_rol=Min('groups__name'))
    prefijo = '-' if direccion == 'desc' else ''
    campos = [prefijo + campo for campo in ordenes[ordenar][1]]
    usuarios = usuarios.order_by(*campos, 'pk')

    paginador = Paginator(usuarios, 10)
    pagina = paginador.get_page(request.GET.get('pagina'))
    columnas = [{
        'clave': clave,
        'titulo': titulo,
        'seleccionada': clave == ordenar,
        'aria_orden': 'descending' if direccion == 'desc' else 'ascending',
        'siguiente': 'desc' if clave == ordenar and direccion == 'asc' else 'asc',
    } for clave, (titulo, _) in ordenes.items()]
    contexto = {
        'usuarios': pagina,
        'paginas': paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1),
        'elipsis': paginador.ELLIPSIS,
        'q': consulta,
        'consulta_aplicada': consulta_aplicada,
        'activados': estado == 'activo',
        'desactivados': estado == 'inactivo',
        'ordenar': ordenar,
        'direccion': direccion,
        'columnas': columnas,
    }
    plantilla = 'seguridad/lista_usuarios.html'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        plantilla = 'seguridad/resultados_usuarios.html'
    return render(request, plantilla, contexto)


@login_required
@permission_required('seguridad.view_usuario', raise_exception=True)
def detalle_usuario(request, id):
    usuario = get_object_or_404(Usuario, pk=id)
    return render(request, 'seguridad/detalle_usuario.html', {'usuario': usuario})


@login_required
@permission_required('seguridad.add_usuario', raise_exception=True)
def crear_usuario(request):
    if request.method == 'POST':
        form = UsuarioCrearForm(request.POST)
        if form.is_valid():
            usuario = form.save(commit=False)
            usuario.debe_cambiar_password = True
            usuario.save()
            form.save_m2m()
            messages.success(request, 'Usuario creado correctamente.')
            return redirect('seguridad:lista_usuarios')
    else:
        form = UsuarioCrearForm()
    return render(request, 'seguridad/form_usuario.html', {'form': form, 'accion': 'Crear'})


@login_required
@permission_required('seguridad.change_usuario', raise_exception=True)
def editar_usuario(request, id):
    usuario = get_object_or_404(Usuario, pk=id)
    if request.method == 'POST':
        form = UsuarioEditarForm(request.POST, instance=usuario, usuario_actual=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuario actualizado correctamente.')
            return redirect('seguridad:lista_usuarios')
    else:
        form = UsuarioEditarForm(instance=usuario, usuario_actual=request.user)
    return render(request, 'seguridad/form_usuario.html', {'form': form, 'accion': 'Editar', 'usuario': usuario})


def _destino_lista_usuarios(request):
    destino = request.POST.get('siguiente', request.GET.get('siguiente', ''))
    lista = reverse('seguridad:lista_usuarios')
    if (url_has_allowed_host_and_scheme(
            destino, allowed_hosts={request.get_host()}, require_https=request.is_secure())
            and urlsplit(destino).path == lista):
        return destino
    return lista


def _cambiar_estado_usuario(request, id, activar):
    usuario = get_object_or_404(Usuario, pk=id)
    siguiente = _destino_lista_usuarios(request)
    if not activar and usuario.pk == request.user.pk:
        messages.error(request, 'No puedes desactivar tu propia cuenta desde esta pantalla.')
        return redirect(siguiente)
    if request.method == 'POST':
        usuario.is_active = activar
        usuario.save(update_fields=['is_active'])
        estado = 'activado' if activar else 'desactivado'
        messages.success(request, f'Usuario {usuario.username} {estado} correctamente.')
        return redirect(siguiente)
    return render(request, 'seguridad/estado_usuario.html', {
        'usuario': usuario, 'activar': activar,
        'accion': 'Activar' if activar else 'Desactivar', 'siguiente': siguiente,
    })


@login_required
@permission_required('seguridad.change_usuario', raise_exception=True)
def desactivar_usuario(request, id):
    return _cambiar_estado_usuario(request, id, activar=False)


@login_required
@permission_required('seguridad.change_usuario', raise_exception=True)
def activar_usuario(request, id):
    return _cambiar_estado_usuario(request, id, activar=True)


# --- Roles ---

@login_required
@permission_required('auth.view_group', raise_exception=True)
def lista_roles(request):
    roles = Group.objects.annotate(total_usuarios=Count('user')).order_by('name')
    return render(request, 'seguridad/lista_roles.html', {'roles': roles})


@login_required
@permission_required('auth.add_group', raise_exception=True)
def crear_rol(request):
    if request.method == 'POST':
        form = RolForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rol creado correctamente.')
            return redirect('seguridad:lista_roles')
        permisos_seleccionados = set(int(pk) for pk in request.POST.getlist('permissions') if pk)
    else:
        form = RolForm()
        permisos_seleccionados = set()
    return render(request, 'seguridad/form_rol.html', {
        'form': form,
        'accion': 'Crear',
        'permisos_agrupados': _permisos_agrupados(),
        'permisos_seleccionados': permisos_seleccionados,
    })


@login_required
@permission_required('auth.change_group', raise_exception=True)
def editar_rol(request, id):
    rol = get_object_or_404(Group, pk=id)
    if request.method == 'POST':
        form = RolForm(request.POST, instance=rol)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rol actualizado correctamente.')
            return redirect('seguridad:lista_roles')
        permisos_seleccionados = set(int(pk) for pk in request.POST.getlist('permissions') if pk)
    else:
        form = RolForm(instance=rol)
        permisos_seleccionados = set(rol.permissions.values_list('pk', flat=True))
    return render(request, 'seguridad/form_rol.html', {
        'form': form,
        'accion': 'Editar',
        'rol': rol,
        'permisos_agrupados': _permisos_agrupados(),
        'permisos_seleccionados': permisos_seleccionados,
    })


@login_required
@permission_required('auth.delete_group', raise_exception=True)
def eliminar_rol(request, id):
    rol = get_object_or_404(Group, pk=id)
    if request.method == 'POST':
        rol.delete()
        messages.success(request, 'Rol eliminado correctamente.')
        return redirect('seguridad:lista_roles')
    return render(request, 'seguridad/eliminar_rol.html', {'rol': rol})


@login_required
@permission_required('auth.change_group', raise_exception=True)
def usuarios_rol(request, id):
    rol = get_object_or_404(Group, pk=id)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        usuario_id = request.POST.get('usuario_id')
        usuario = get_object_or_404(Usuario, pk=usuario_id)
        if accion == 'agregar':
            usuario.groups.add(rol)
            messages.success(request, f'Usuario {usuario.username} agregado al rol.')
        elif accion == 'quitar':
            usuario.groups.remove(rol)
            messages.success(request, f'Usuario {usuario.username} quitado del rol.')
        return redirect('seguridad:usuarios_rol', id=id)

    usuarios_con_rol = rol.user_set.all().order_by('username')
    usuarios_sin_rol = Usuario.objects.exclude(groups=rol).order_by('username')
    return render(request, 'seguridad/usuarios_rol.html', {
        'rol': rol,
        'usuarios_con_rol': usuarios_con_rol,
        'usuarios_sin_rol': usuarios_sin_rol,
    })


# --- Reseteo de contraseña por administrador ---

@login_required
@permission_required('seguridad.change_usuario', raise_exception=True)
def resetear_password(request, id):
    usuario = get_object_or_404(Usuario, pk=id)
    if request.method == 'POST':
        form = ResetearPasswordForm(request.POST)
        if form.is_valid():
            usuario.set_password(form.cleaned_data['password1'])
            usuario.debe_cambiar_password = True
            usuario.save()
            messages.success(
                request,
                f'Contraseña de {usuario.username} restablecida. '
                'El usuario deberá cambiarla en su próximo acceso.'
            )
            return redirect('seguridad:detalle_usuario', id=id)
    else:
        form = ResetearPasswordForm()
    return render(request, 'seguridad/resetear_password.html', {'form': form, 'usuario': usuario})


# --- Perfil propio ---

@login_required
def mi_perfil(request):
    return render(request, 'seguridad/mi_perfil.html')


class CambiarPasswordView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'seguridad/cambiar_password.html'
    success_url = reverse_lazy('seguridad:mi_perfil')

    def form_valid(self, form):
        self.request.user.debe_cambiar_password = False
        self.request.user.save(update_fields=['debe_cambiar_password'])
        messages.success(self.request, 'Contraseña actualizada correctamente.')
        return super().form_valid(form)


@login_required
@permission_required('seguridad.view_empleado', raise_exception=True)
@never_cache
@vary_on_headers('X-Requested-With')
def lista_empleados(request):
    consulta = request.GET.get('q', '').strip()
    consulta_aplicada = consulta if len(consulta) >= 2 else ''
    estado = request.GET.get('estado', 'activo')
    if estado not in {'activo', 'inactivo'}:
        estado = 'activo'
    empleados = Empleado.objects.filter(activo=(estado == 'activo'))
    if consulta_aplicada:
        filtro = (
            Q(nombre_completo__icontains=consulta_aplicada)
            | Q(cargo__icontains=consulta_aplicada)
            | Q(telefono__icontains=consulta_aplicada)
            | Q(correo__icontains=consulta_aplicada)
        )
        codigo = consulta_aplicada.upper().removeprefix('EMP-')
        if codigo.isascii() and codigo.isdecimal() and len(codigo) <= 18:
            filtro |= Q(pk=int(codigo))
        empleados = empleados.annotate(
            nombre_completo=Concat('nombres', Value(' '), 'apellidos'),
        ).filter(filtro)
    paginador = Paginator(empleados, 10)
    pagina = paginador.get_page(request.GET.get('pagina'))
    contexto = {
        'empleados': pagina,
        'paginas': paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1),
        'elipsis': paginador.ELLIPSIS,
        'q': consulta,
        'consulta_aplicada': consulta_aplicada,
        'activados': estado == 'activo',
        'desactivados': estado == 'inactivo',
    }
    plantilla = 'seguridad/lista_empleados.html'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        plantilla = 'seguridad/resultados_empleados.html'
    return render(request, plantilla, contexto)


@login_required
@permission_required('seguridad.add_empleado', raise_exception=True)
def crear_empleado(request):
    form = EmpleadoCrearForm(request.POST if request.method == 'POST' else None,
                             initial={'fecha_ingreso': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        empleado = form.save()
        messages.success(request, f'Empleado {empleado.codigo} registrado correctamente.')
        if request.user.has_perm('seguridad.view_empleado'):
            return redirect('seguridad:lista_empleados')
        return redirect('seguridad:crear_empleado')
    return render(request, 'seguridad/form_empleado.html', {'form': form})
