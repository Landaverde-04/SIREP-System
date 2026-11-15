"""Permisos iniciales de los roles del restaurante."""

from django.contrib.auth.models import Permission
from django.core.management.base import CommandError


ROLES_BASE = {
    'Anfitrión': {
        'reservaciones': ('view_reservacion', 'add_reservacion', 'change_reservacion',
                          'cancelar_reservacion', 'add_atencion'),
        'administracion': ('view_cliente', 'add_cliente'),
    },
    'Mesero': {
        'pedidos': ('view_pedido', 'add_pedido', 'change_pedido', 'entregar_pedido'),
        'administracion': ('view_producto',),
    },
    'Encargado de cocina': {
        'pedidos': ('view_pedido', 'preparar_pedido'),
    },
    'Cajero': {
        'cobro': ('view_cobro', 'add_cobro'),
    },
    'Gerente': {
        'administracion': (
            'view_mesa', 'add_mesa', 'change_mesa',
            'view_producto', 'add_producto', 'change_producto',
            'view_categoriaproducto', 'add_categoriaproducto', 'change_categoriaproducto',
            'view_cliente', 'change_cliente',
        ),
    },
    'Administrador': {
        'seguridad': ('view_usuario', 'add_usuario', 'change_usuario',
                      'view_empleado', 'add_empleado', 'change_empleado'),
        'auth': ('view_group', 'add_group', 'change_group', 'delete_group'),
    },
}



def permisos_del_rol(nombre):
    permisos = []
    for modulo, codigos in ROLES_BASE[nombre].items():
        encontrados = list(Permission.objects.filter(
            content_type__app_label=modulo, codename__in=codigos,
        ))
        faltan = set(codigos) - {permiso.codename for permiso in encontrados}
        if faltan:
            raise CommandError(f'Faltan permisos de {modulo}: {", ".join(sorted(faltan))}. Ejecuta migrate.')
        permisos.extend(encontrados)
    return permisos
