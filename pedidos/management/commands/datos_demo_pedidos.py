"""
Carga datos de prueba para el módulo de pedidos:

    python manage.py datos_demo_pedidos

Crea (si no existen) categorías y productos del menú y los roles "Mesero" y
"Encargado de cocina" con sus permisos. Se puede ejecutar varias veces sin duplicar datos.
Solo para desarrollo y demostración.

Para tomar un pedido hace falta una mesa con atención abierta: registre un
ingreso en /reservaciones/ingresos/ (ver ``datos_demo_reservaciones``).
"""

from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from administracion.models import CategoriaProducto, Producto
from seguridad.roles_base import permisos_del_rol

MENU = {
    'Entradas': [('Sopa del día', '3.50'), ('Nachos con queso', '5.25')],
    'Platos fuertes': [('Pollo a la plancha', '8.75'), ('Filete de res', '12.50'), ('Pupusas (3)', '3.00')],
    'Bebidas': [('Refresco natural', '1.75'), ('Limonada', '2.00'), ('Café', '1.50')],
    'Postres': [('Tres leches', '3.25')],
}


class Command(BaseCommand):
    help = 'Carga el menú y los roles Mesero y Encargado de cocina para probar el módulo de pedidos.'

    @transaction.atomic
    def handle(self, *args, **opciones):
        productos = 0
        for nombre_categoria, items in MENU.items():
            categoria, _ = CategoriaProducto.objects.get_or_create(nombre=nombre_categoria)
            for nombre, precio in items:
                productos += Producto.objects.get_or_create(
                    nombre=nombre, defaults={'categoria': categoria, 'precio': Decimal(precio)})[1]

        for nombre_rol in ('Mesero', 'Encargado de cocina'):
            rol, creado = Group.objects.get_or_create(name=nombre_rol)
            if creado:
                rol.permissions.set(permisos_del_rol(nombre_rol))
        self.stdout.write(self.style.SUCCESS(
            f'Listo: {productos} productos nuevos; roles "Mesero" y "Encargado de cocina" con sus permisos.'))
