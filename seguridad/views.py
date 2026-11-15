from itertools import groupby
from urllib.parse import urlsplit

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.db.models import Count, Min, Q, Value
from django.db.models.functions import Concat
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_headers
from django.views.decorators.http import require_http_methods

from core.navegacion import MODULOS

from .models import Empleado, Usuario
from .forms import EmpleadoCrearForm, EmpleadoEditarForm, UsuarioCrearForm, UsuarioEditarForm, RolForm, ResetearPasswordForm


_ACCIONES_ES = {
    'view': 'Ver',
    'add': 'Agregar',
    'change': 'Modificar',
    'delete': 'Eliminar',
}


def _permisos_agrupados(form):
    seleccionados = {str(valor) for valor in form['permissions'].value() or []}
    def clave_modulo(permiso):
        app_label = permiso.content_type.app_label
        return 'seguridad' if app_label == 'auth' else app_label

    permisos = sorted(form.fields['permissions'].queryset, key=clave_modulo)
    modulos = []
    for app_label, grupo in groupby(permisos, key=clave_modulo):
        por_modelo = {}
        for permiso in grupo:
            por_modelo.setdefault(permiso.content_type.model, []).append(permiso)

        modelos = []
        for clave, permisos_modelo in por_modelo.items():
            clase = permisos_modelo[0].content_type.model_class()
            nombre = str(clase._meta.verbose_name) if clase else clave
            if clave == 'group':
                nombre = 'rol'
            items = []
            # Los permisos estándar siguen el orden de las acciones del formulario.
            pendientes = {permiso.codename: permiso for permiso in permisos_modelo}
            for accion, etiqueta in _ACCIONES_ES.items():
                permiso = pendientes.pop(f'{accion}_{clave}', None)
                if permiso:
                    items.append({
                        'pk': permiso.pk, 'label': etiqueta,
                        'seleccionado': str(permiso.pk) in seleccionados,
                    })
            for permiso in pendientes.values():
                items.append({
                    'pk': permiso.pk, 'label': permiso.name.removeprefix('Puede ').capitalize(),
                    'seleccionado': str(permiso.pk) in seleccionados,
                })
            modelos.append({'nombre': nombre, 'permisos': items})

        modulo = MODULOS.get(app_label, {})
        modulos.append({
            'nombre': modulo.get('nombre', app_label.capitalize()),
            'icono': modulo.get('icono', 'bi-shield'),
            'modelos': sorted(modelos, key=lambda modelo: modelo['nombre'].casefold()),
        })
    return modulos


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
    usuario = get_object_or_404(Usuario.objects.select_related('empleado').prefetch_related('groups'), pk=id)
    return render(request, 'seguridad/detalle_usuario.html', {
        'usuario': usuario, 'empleado_asociado': getattr(usuario, 'empleado', None),
    })


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
    if usuario.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    if request.method == 'POST':
        form = UsuarioEditarForm(request.POST, instance=usuario, usuario_actual=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuario actualizado correctamente.')
            return redirect('seguridad:lista_usuarios')
    else:
        form = UsuarioEditarForm(instance=usuario, usuario_actual=request.user)
    return render(request, 'seguridad/form_usuario.html', {'form': form, 'accion': 'Editar', 'usuario': usuario})


def _destino_lista_usuarios(request, usuario=None):
    destino = request.POST.get('siguiente', request.GET.get('siguiente', ''))
    lista = reverse('seguridad:lista_usuarios')
    permitidas = {lista}
    if usuario is not None and request.user.has_perm('seguridad.view_usuario'):
        permitidas.add(reverse('seguridad:detalle_usuario', args=[usuario.pk]))
    if (url_has_allowed_host_and_scheme(
            destino, allowed_hosts={request.get_host()}, require_https=request.is_secure())
            and urlsplit(destino).path in permitidas):
        return destino
    return lista


def _cambiar_estado_usuario(request, id, activar):
    usuario = get_object_or_404(Usuario, pk=id)
    if usuario.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    siguiente = _destino_lista_usuarios(request, usuario)
    if activar and Empleado.objects.filter(usuario=usuario, activo=False).exists():
        messages.error(request, 'Primero debes reactivar al empleado asociado a esta cuenta.')
        return redirect(siguiente)
    if not activar and usuario.pk == request.user.pk:
        messages.error(request, 'No puedes desactivar tu propia cuenta desde esta pantalla.')
        return redirect(siguiente)
    if request.method == 'POST':
        usuario.is_active = activar
        usuario.save(update_fields=['is_active'])
        estado = 'activado' if activar else 'desactivado'
        messages.success(request, f'Usuario {usuario.username} {estado} correctamente.')
        return redirect(siguiente)
    return _render_confirmacion(request, 'seguridad/estado_usuario.html', {
        'tipo': 'usuario', 'usuario': usuario, 'activar': activar,
        'accion': 'Activar' if activar else 'Desactivar', 'siguiente': siguiente,
    })


@login_required
@permission_required('seguridad.change_usuario', raise_exception=True)
@never_cache
@vary_on_headers('X-Requested-With')
@require_http_methods(['GET', 'HEAD', 'POST'])
def desactivar_usuario(request, id):
    return _cambiar_estado_usuario(request, id, activar=False)


@login_required
@permission_required('seguridad.change_usuario', raise_exception=True)
@never_cache
@vary_on_headers('X-Requested-With')
@require_http_methods(['GET', 'HEAD', 'POST'])
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
    form = RolForm(request.POST if request.method == 'POST' else None)
    if form.is_bound and form.is_valid():
        form.save()
        messages.success(request, 'Rol creado correctamente.')
        return redirect('seguridad:lista_roles')
    return render(request, 'seguridad/form_rol.html', {
        'form': form,
        'accion': 'Crear',
        'permisos_agrupados': _permisos_agrupados(form),
    })


@login_required
@permission_required('auth.change_group', raise_exception=True)
def editar_rol(request, id):
    rol = get_object_or_404(Group, pk=id)
    form = RolForm(request.POST if request.method == 'POST' else None, instance=rol)
    if form.is_bound and form.is_valid():
        form.save()
        messages.success(request, 'Rol actualizado correctamente.')
        return redirect('seguridad:lista_roles')
    return render(request, 'seguridad/form_rol.html', {
        'form': form,
        'accion': 'Editar',
        'rol': rol,
        'permisos_agrupados': _permisos_agrupados(form),
    })


@login_required
@permission_required('auth.delete_group', raise_exception=True)
@never_cache
@vary_on_headers('X-Requested-With')
@require_http_methods(['GET', 'HEAD', 'POST'])
def eliminar_rol(request, id):
    if request.method == 'POST':
        with transaction.atomic():
            rol = get_object_or_404(Group.objects.select_for_update(), pk=id)
            if rol.user_set.exists():
                messages.error(request, 'Quita los usuarios asignados antes de eliminar el rol.')
            else:
                rol.delete()
                messages.success(request, 'Rol eliminado correctamente.')
        return redirect('seguridad:lista_roles')
    rol = get_object_or_404(Group, pk=id)
    return _render_confirmacion(request, 'seguridad/eliminar_rol.html', {
        'tipo': 'rol', 'rol': rol, 'accion': 'Eliminar',
        'siguiente': reverse('seguridad:lista_roles'),
        'total_usuarios': rol.user_set.count(),
    })


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
    if usuario.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
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
    empleados = Empleado.objects.filter(activo=(estado == 'activo')).select_related('usuario')
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
    return render(request, 'seguridad/form_empleado.html', {
        'form': form, 'accion': 'Registrar', 'modo_edicion': False,
        'volver_url': reverse('seguridad:lista_empleados'),
    })


def _destino_lista_empleados(request, empleado=None):
    if not request.user.has_perm('seguridad.view_empleado'):
        return reverse('core:home')
    destino = request.POST.get('siguiente', request.GET.get('siguiente', ''))
    lista = reverse('seguridad:lista_empleados')
    permitidas = {lista}
    if empleado is not None:
        permitidas.add(reverse('seguridad:detalle_empleado', args=[empleado.pk]))
    if (url_has_allowed_host_and_scheme(
            destino, allowed_hosts={request.get_host()}, require_https=request.is_secure())
            and urlsplit(destino).path in permitidas):
        return destino
    return lista


def _cambiar_estado_empleado(request, id, activar):
    empleado = get_object_or_404(Empleado.objects.select_related('usuario'), pk=id)
    siguiente = _destino_lista_empleados(request, empleado)
    if not activar and empleado.usuario and empleado.usuario.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    if not activar and empleado.usuario_id == request.user.pk:
        messages.error(request, 'No puedes desactivar al empleado asociado a tu propia cuenta.')
        return redirect(siguiente)
    if request.method == 'POST':
        with transaction.atomic():
            # Bloquear primero el empleado y después su usuario, igual que al asociar.
            empleado = get_object_or_404(Empleado.objects.select_for_update(), pk=id)
            if not activar and empleado.usuario_id == request.user.pk:
                messages.error(request, 'No puedes desactivar al empleado asociado a tu propia cuenta.')
                return redirect(siguiente)
            usuario = None
            if not activar and empleado.usuario_id:
                usuario = Usuario.objects.select_for_update().get(pk=empleado.usuario_id)
                if usuario.is_superuser and not request.user.is_superuser:
                    raise PermissionDenied
            cambio = empleado.activo != activar
            if cambio:
                empleado.activo = activar
                empleado.save(update_fields=['activo', 'fecha_modificacion'])
            cambio_usuario = usuario is not None and usuario.is_active
            if cambio_usuario:
                usuario.is_active = False
                usuario.save(update_fields=['is_active'])
        if cambio or cambio_usuario:
            estado = 'reactivado' if activar else 'desactivado'
            mensaje = f'Empleado {empleado.codigo} {estado} correctamente.'
            if not activar and usuario is not None:
                mensaje += ' La cuenta asociada también está desactivada.'
            messages.success(request, mensaje)
        else:
            estado = 'activado' if activar else 'desactivado'
            messages.info(request, f'El empleado {empleado.codigo} ya estaba {estado}.')
        return redirect(siguiente)
    return _render_confirmacion(request, 'seguridad/estado_empleado.html', {
        'tipo': 'empleado', 'empleado': empleado,
        'activar': activar,
        'accion': 'Reactivar' if activar else 'Desactivar',
        'siguiente': siguiente,
    })


@login_required
@permission_required('seguridad.change_empleado', raise_exception=True)
@never_cache
@vary_on_headers('X-Requested-With')
@require_http_methods(['GET', 'HEAD', 'POST'])
def desactivar_empleado(request, id):
    return _cambiar_estado_empleado(request, id, activar=False)


@login_required
@permission_required('seguridad.change_empleado', raise_exception=True)
@never_cache
@vary_on_headers('X-Requested-With')
@require_http_methods(['GET', 'HEAD', 'POST'])
def activar_empleado(request, id):
    return _cambiar_estado_empleado(request, id, activar=True)


@login_required
@permission_required('seguridad.view_empleado', raise_exception=True)
@never_cache
def detalle_empleado(request, id):
    empleado = get_object_or_404(Empleado.objects.select_related('usuario'), pk=id)
    return render(request, 'seguridad/detalle_empleado.html', {'empleado': empleado})


@login_required
@permission_required(('seguridad.view_empleado', 'seguridad.change_empleado', 'seguridad.view_usuario'), raise_exception=True)
@never_cache
@require_http_methods(['GET'])
def usuarios_disponibles_empleado(request, id):
    empleado = get_object_or_404(Empleado, pk=id)
    if not empleado.activo or empleado.usuario_id:
        return render(request, 'seguridad/usuarios_disponibles.html', {
            'no_disponible': True,
        }, status=409)
    consulta = request.GET.get('q', '').strip()
    consulta_aplicada = consulta if len(consulta) >= 2 else ''
    usuarios = Usuario.objects.filter(empleado__isnull=True)
    if not request.user.is_superuser:
        usuarios = usuarios.filter(is_superuser=False)
    if consulta_aplicada:
        usuarios = usuarios.annotate(nombre_completo=Concat('first_name', Value(' '), 'last_name')).filter(
            Q(username__icontains=consulta_aplicada) | Q(nombre_completo__icontains=consulta_aplicada)
            | Q(email__icontains=consulta_aplicada),
        )
    paginador = Paginator(usuarios.order_by('username', 'pk'), 8)
    pagina = paginador.get_page(request.GET.get('pagina'))
    return render(request, 'seguridad/usuarios_disponibles.html', {
        'usuarios': pagina, 'consulta_aplicada': consulta_aplicada,
        'paginas': paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1),
        'elipsis': paginador.ELLIPSIS,
    })


@login_required
@permission_required(('seguridad.view_empleado', 'seguridad.change_empleado', 'seguridad.view_usuario'), raise_exception=True)
@require_http_methods(['POST'])
def asociar_usuario_empleado(request, id):
    get_object_or_404(Empleado, pk=id)
    error = ''
    identificador = request.POST.get('usuario', '')
    if not (identificador.isascii() and identificador.isdecimal() and len(identificador) <= 18):
        error = 'Selecciona un usuario disponible.'
    else:
        try:
            with transaction.atomic():
                empleado = get_object_or_404(Empleado.objects.select_for_update(), pk=id)
                usuario = Usuario.objects.select_for_update().filter(pk=int(identificador)).first()
                if not empleado.activo:
                    error = 'Primero debes reactivar al empleado para asociarle una cuenta.'
                elif empleado.usuario_id:
                    error = 'Este empleado ya tiene un usuario asociado.'
                elif usuario is None or (usuario.is_superuser and not request.user.is_superuser):
                    error = 'El usuario seleccionado ya no está disponible.'
                elif Empleado.objects.filter(usuario=usuario).exists():
                    error = 'El usuario seleccionado ya está asociado a otro empleado. Elige otro.'
                else:
                    empleado.usuario = usuario
                    empleado.save(update_fields=['usuario', 'fecha_modificacion'])
        except IntegrityError:
            # La unicidad de la base protege también frente a asignaciones simultáneas.
            error = 'El usuario seleccionado acaba de ser asignado. Actualiza la lista y elige otro.'
    if error:
        messages.error(request, error)
    else:
        messages.success(request, 'Usuario asociado correctamente. Se conservó el estado de la cuenta.')
    return redirect('seguridad:detalle_empleado', id=id)


def _destino_edicion_empleado(request, empleado):
    if not request.user.has_perm('seguridad.view_empleado'):
        return reverse('core:home')
    detalle = reverse('seguridad:detalle_empleado', args=[empleado.pk])
    lista = reverse('seguridad:lista_empleados')
    destino = request.POST.get('siguiente', request.GET.get('siguiente', ''))
    if (url_has_allowed_host_and_scheme(
            destino, allowed_hosts={request.get_host()}, require_https=request.is_secure())
            and urlsplit(destino).path in {lista, detalle}):
        return destino
    return detalle


@login_required
@permission_required('seguridad.change_empleado', raise_exception=True)
@never_cache
@require_http_methods(['GET', 'HEAD', 'POST'])
def editar_empleado(request, id):
    empleado = get_object_or_404(Empleado, pk=id)
    siguiente = _destino_edicion_empleado(request, empleado)
    form = EmpleadoEditarForm(request.POST if request.method == 'POST' else None, instance=empleado)
    if request.method == 'POST' and form.is_valid():
        if form.has_changed():
            empleado = form.save(commit=False)
            # Solo se escriben los datos editables: una baja o asociación concurrente
            # no debe ser sobrescrita con el estado leído al abrir el formulario.
            empleado.save(update_fields=[*form.fields, 'fecha_modificacion'])
            messages.success(request, f'Empleado {empleado.codigo} actualizado correctamente.')
        else:
            messages.info(request, 'No se realizaron cambios en los datos del empleado.')
        return redirect(siguiente)
    return render(request, 'seguridad/form_empleado.html', {
        'form': form, 'empleado': empleado, 'accion': 'Editar',
        'modo_edicion': True, 'volver_url': siguiente,
    })


def _render_confirmacion(request, plantilla, contexto):
    contexto['form_action'] = request.path
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        plantilla = 'seguridad/confirmacion_accion.html'
    return render(request, plantilla, contexto)
