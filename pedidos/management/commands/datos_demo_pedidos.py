"""
Carga datos de prueba para el módulo de pedidos:

    python manage.py datos_demo_pedidos

Crea (si no existen) categorías y productos del menú y los roles "Mesero" y
"Cocina" con sus permisos; también concede al rol "Gerente" (si existe) la
consulta de pedidos. Se puede ejecutar varias veces sin duplicar datos.
Solo para desarrollo y demostración.

Para tomar un pedido hace falta una mesa con atención abierta: registre un
ingreso en /reservaciones/ingresos/ (ver ``datos_demo_reservaciones``).
"""

from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from administracion.models import CategoriaProducto, Producto

MENU = {
    'Entradas': [('Sopa del día', '3.50'), ('Nachos con queso', '5.25')],
    'Platos fuertes': [('Pollo a la plancha', '8.75'), ('Filete de res', '12.50'), ('Pupusas (3)', '3.00')],
    'Bebidas': [('Refresco natural', '1.75'), ('Limonada', '2.00'), ('Café', '1.50')],
    'Postres': [('Tres leches', '3.25')],
}

PERMISOS_MESERO = [
    ('pedidos', 'view_pedido'), ('pedidos', 'add_pedido'), ('pedidos', 'change_pedido'),
    ('pedidos', 'cambiar_estado_pedido'),
]
PERMISOS_COCINA = [('pedidos', 'view_pedido'), ('pedidos', 'cambiar_estado_pedido')]
PERMISOS_GERENTE = [('pedidos', 'view_pedido')]


class Command(BaseCommand):
    help = 'Carga el menú y los roles Mesero y Cocina para probar el módulo de pedidos.'

    @transaction.atomic
    def handle(self, *args, **opciones):
        productos = 0
        for nombre_categoria, items in MENU.items():
            categoria, _ = CategoriaProducto.objects.get_or_create(nombre=nombre_categoria)
            for nombre, precio in items:
                productos += Producto.objects.get_or_create(
                    nombre=nombre, defaults={'categoria': categoria, 'precio': Decimal(precio)})[1]

        for nombre_rol, permisos in (('Mesero', PERMISOS_MESERO), ('Cocina', PERMISOS_COCINA),
                                     ('Gerente', PERMISOS_GERENTE)):
            rol, _ = Group.objects.get_or_create(name=nombre_rol)
            for app, codigo in permisos:
                rol.permissions.add(Permission.objects.get(content_type__app_label=app, codename=codigo))
        self.stdout.write(self.style.SUCCESS(
            f'Listo: {productos} productos nuevos; roles "Mesero" y "Cocina" con sus permisos.'))
