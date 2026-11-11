from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Count
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .navegacion import acceso_modulo_requerido, modulos_disponibles


@login_required
@never_cache
def home(request):
    from administracion.models import Mesa
    from pedidos.models import Pedido
    from reservaciones.models import Atencion, Reservacion
    from seguridad.models import Empleado, Usuario

    hoy = timezone.localdate()
    indicadores = []
    agenda = None
    estados_pedidos = None
    if request.user.has_perm('reservaciones.view_reservacion'):
        reservas = Reservacion.objects.del_dia(hoy).filter(activo=True)
        indicadores.append({'nombre': 'Reservaciones hoy', 'valor': reservas.count(),
                            'detalle': 'Todas las reservaciones del día', 'icono': 'bi-calendar2-check',
                            'color': 'azul', 'url': reverse('reservaciones:lista_reservaciones')})
        agenda = reservas.filter(estado=Reservacion.Estado.PROGRAMADA).select_related('cliente', 'mesa').order_by('fecha_hora_inicio')[:5]
    if request.user.has_perm('administracion.view_mesa'):
        ocupadas = Atencion.objects.abiertas().filter(mesa__activo=True).count()
        total = Mesa.objects.filter(activo=True).count()
        indicadores.append({'nombre': 'Mesas ocupadas', 'valor': ocupadas,
                            'detalle': f'De {total} mesas habilitadas', 'icono': 'bi-grid-1x2',
                            'color': 'verde', 'url': reverse('administracion:lista_mesas')})
    if request.user.has_perm('pedidos.view_pedido'):
        conteos = dict(Pedido.objects.en_curso().values('estado').annotate(total=Count('pk')).values_list('estado', 'total'))
        total = sum(conteos.values())
        indicadores.append({'nombre': 'Pedidos en curso', 'valor': total,
                            'detalle': 'Pendientes, en preparación y listos', 'icono': 'bi-receipt',
                            'color': 'naranja', 'url': reverse('pedidos:lista_pedidos')})
        estados_pedidos = [{'nombre': nombre, 'total': conteos.get(estado, 0),
                           'porcentaje': round(conteos.get(estado, 0) * 100 / total) if total else 0,
                           'color': color}
                          for estado, nombre, color in (
                              (Pedido.Estado.PENDIENTE, 'Pendientes', 'naranja'),
                              (Pedido.Estado.EN_PREPARACION, 'En preparación', 'azul'),
                              (Pedido.Estado.LISTO, 'Listos para entregar', 'verde'))]
    if request.user.has_perm('seguridad.view_empleado'):
        indicadores.append({'nombre': 'Empleados activos', 'valor': Empleado.objects.filter(activo=True).count(),
                            'detalle': 'Personal registrado y activado', 'icono': 'bi-person-badge',
                            'color': 'violeta', 'url': reverse('seguridad:lista_empleados')})
    if not indicadores and request.user.has_perm('seguridad.view_usuario'):
        indicadores.append({'nombre': 'Usuarios activos', 'valor': Usuario.objects.filter(is_active=True).count(),
                            'detalle': 'Cuentas con acceso habilitado', 'icono': 'bi-people',
                            'color': 'violeta', 'url': reverse('seguridad:lista_usuarios')})
    if not indicadores and request.user.has_perm('auth.view_group'):
        indicadores.append({'nombre': 'Roles registrados', 'valor': Group.objects.count(),
                            'detalle': 'Perfiles de permisos del sistema', 'icono': 'bi-shield-check',
                            'color': 'violeta', 'url': reverse('seguridad:lista_roles')})

    rapidos = []
    for permiso, ruta, nombre, icono in (
        ('reservaciones.add_reservacion', 'reservaciones:crear_reservacion', 'Nueva reservación', 'bi-calendar-plus'),
        ('pedidos.add_pedido', 'pedidos:crear_pedido', 'Tomar pedido', 'bi-plus-circle'),
        ('reservaciones.add_atencion', 'reservaciones:panel_ingresos', 'Registrar ingreso', 'bi-door-open'),
        ('seguridad.add_empleado', 'seguridad:crear_empleado', 'Registrar empleado', 'bi-person-plus'),
    ):
        if request.user.has_perm(permiso):
            rapidos.append({'url': reverse(ruta), 'nombre': nombre, 'icono': icono})
    return render(request, 'core/home.html', {
        'hoy': hoy, 'indicadores': indicadores, 'agenda': agenda,
        'estados_pedidos': estados_pedidos, 'accesos_rapidos': rapidos,
        'hay_modulos': bool(modulos_disponibles(request.user)),
    })


@login_required
@acceso_modulo_requerido
def modulo(request, modulo):
    return render(request, 'core/modulo.html', {'modulo': request.modulo_seleccionado})
