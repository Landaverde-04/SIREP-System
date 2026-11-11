from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse


# Cada acceso reutiliza las rutas y los permisos de su módulo.
MODULOS = {
    'reservaciones': {
        'nombre': 'Reservaciones', 'icono': 'bi-calendar2-week', 'color': 'azul',
        'descripcion': 'Organiza las visitas, consulta las mesas y recibe a tus clientes.',
        'accesos': [
            ('Reservaciones', 'Consulta y organiza las reservaciones del restaurante.', 'bi-calendar2-check', [('reservaciones.view_reservacion', 'reservaciones:lista_reservaciones'), ('reservaciones.add_reservacion', 'reservaciones:crear_reservacion')]),
            ('Disponibilidad', 'Encuentra la mesa y el horario adecuados para cada visita.', 'bi-grid', [('reservaciones.view_reservacion', 'reservaciones:consultar_disponibilidad')]),
            ('Ingreso de clientes', 'Registra la llegada de clientes con o sin reservación.', 'bi-door-open', [('reservaciones.add_atencion', 'reservaciones:panel_ingresos')]),
        ],
    },
    'pedidos': {
        'nombre': 'Pedidos', 'icono': 'bi-receipt', 'color': 'naranja',
        'descripcion': 'Conecta el servicio de mesa con la preparación en cocina.',
        'accesos': [
            ('Pedidos', 'Consulta las órdenes y acompaña cada paso del servicio.', 'bi-receipt-cutoff', [('pedidos.view_pedido', 'pedidos:lista_pedidos'), ('pedidos.add_pedido', 'pedidos:crear_pedido')]),
            ('Cocina', 'Visualiza los pedidos pendientes, en preparación y listos.', 'bi-fire', [('pedidos.view_pedido', 'pedidos:cocina')]),
        ],
    },
    'administracion': {
        'nombre': 'Administración', 'icono': 'bi-shop-window', 'color': 'verde',
        'descripcion': 'Mantén al día las mesas, el menú y la información de tus clientes.',
        'accesos': [
            ('Mesas', 'Administra la capacidad, ubicación y disponibilidad de las mesas.', 'bi-grid-1x2', [('administracion.view_mesa', 'administracion:lista_mesas'), ('administracion.add_mesa', 'administracion:crear_mesa')]),
            ('Menú', 'Consulta los productos, precios y disponibilidad del menú.', 'bi-journal-richtext', [('administracion.view_producto', 'administracion:lista_productos'), ('administracion.add_producto', 'administracion:crear_producto')]),
            ('Categorías', 'Organiza los productos del menú en categorías.', 'bi-tags', [('administracion.view_categoriaproducto', 'administracion:lista_categorias'), ('administracion.add_categoriaproducto', 'administracion:crear_categoria')]),
            ('Clientes', 'Consulta y actualiza la información de tus clientes.', 'bi-person-lines-fill', [('administracion.view_cliente', 'administracion:lista_clientes'), ('administracion.add_cliente', 'administracion:crear_cliente')]),
        ],
    },
    'seguridad': {
        'nombre': 'Seguridad', 'icono': 'bi-shield-check', 'color': 'violeta',
        'descripcion': 'Gestiona a tu equipo y controla el acceso al sistema.',
        'accesos': [
            ('Usuarios', 'Administra cuentas, estados y credenciales de acceso.', 'bi-people', [('seguridad.view_usuario', 'seguridad:lista_usuarios'), ('seguridad.add_usuario', 'seguridad:crear_usuario')]),
            ('Roles', 'Define responsabilidades y permisos para cada cuenta.', 'bi-shield-lock', [('auth.view_group', 'seguridad:lista_roles'), ('auth.add_group', 'seguridad:crear_rol')]),
            ('Empleados', 'Consulta al personal y sus cuentas de usuario asociadas.', 'bi-person-badge', [('seguridad.view_empleado', 'seguridad:lista_empleados'), ('seguridad.add_empleado', 'seguridad:crear_empleado')]),
        ],
    },
}


def modulos_disponibles(usuario):
    if not usuario.is_authenticated:
        return []
    resultado = []
    for clave, datos in MODULOS.items():
        accesos = []
        for nombre, descripcion, icono, opciones in datos['accesos']:
            for permiso, ruta in opciones:
                if usuario.has_perm(permiso):
                    accesos.append({'nombre': nombre, 'descripcion': descripcion, 'icono': icono,
                                    'url': reverse(ruta), 'registro': '.add_' in permiso})
                    break
        if accesos:
            resultado.append({**datos, 'clave': clave, 'accesos': accesos,
                              'url': reverse('core:modulo', kwargs={'modulo': clave})})
    return resultado


def acceso_modulo_requerido(vista):
    """Un módulo admite cualquiera de los permisos de sus accesos, no todos."""
    @wraps(vista)
    def protegida(request, modulo, *args, **kwargs):
        if modulo not in MODULOS:
            raise Http404
        disponibles = modulos_disponibles(request.user)
        seleccionado = next((item for item in disponibles if item['clave'] == modulo), None)
        if seleccionado is None:
            raise PermissionDenied
        request.modulo_seleccionado = seleccionado
        return vista(request, modulo, *args, **kwargs)
    return protegida
