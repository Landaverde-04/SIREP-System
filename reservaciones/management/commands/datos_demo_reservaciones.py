"""
Carga datos de prueba para el módulo de reservaciones:

    python manage.py datos_demo_reservaciones

Crea (si no existen) mesas, algunos clientes y el rol "Anfitrión" con los
permisos del módulo. Se puede ejecutar varias veces sin duplicar datos.
Solo para desarrollo y demostración.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from administracion.models import Cliente, Mesa

MESAS = [
    (1, 2, 'Ventana'), (2, 2, 'Ventana'), (3, 4, 'Salón principal'), (4, 4, 'Salón principal'),
    (5, 4, 'Salón principal'), (6, 6, 'Terraza'), (7, 6, 'Terraza'), (8, 10, 'Salón privado'),
]

CLIENTES = [
    ('Ana López', '7777-8888'), ('Carlos Martínez', '7012-3456'), ('María Hernández', '6123-4567'),
    ('José Ramírez', '2250-1000'), ('Lucía Flores', '7555-1212'),
]

PERMISOS_ANFITRION = [
    ('reservaciones', 'view_reservacion'), ('reservaciones', 'add_reservacion'),
    ('reservaciones', 'change_reservacion'), ('reservaciones', 'cancelar_reservacion'),
    ('reservaciones', 'view_atencion'), ('reservaciones', 'add_atencion'),
    ('administracion', 'view_cliente'), ('administracion', 'add_cliente'),
    ('administracion', 'view_mesa'),
]


class Command(BaseCommand):
    help = 'Carga mesas, clientes y el rol Anfitrión para probar el módulo de reservaciones.'

    @transaction.atomic
    def handle(self, *args, **opciones):
        mesas = sum(Mesa.objects.get_or_create(numero=n, defaults={'capacidad': c, 'ubicacion': u})[1]
                    for n, c, u in MESAS)
        clientes = sum(Cliente.objects.get_or_create(telefono=t, defaults={'nombre': n})[1]
                       for n, t in CLIENTES)
        rol, _ = Group.objects.get_or_create(name='Anfitrión')
        for app, codigo in PERMISOS_ANFITRION:
            rol.permissions.add(Permission.objects.get(content_type__app_label=app, codename=codigo))
        self.stdout.write(self.style.SUCCESS(
            f'Listo: {mesas} mesas y {clientes} clientes nuevos; rol "Anfitrión" con '
            f'{len(PERMISOS_ANFITRION)} permisos.'))
