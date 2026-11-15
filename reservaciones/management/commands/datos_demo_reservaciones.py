"""
Carga datos de prueba para el módulo de reservaciones:

    python manage.py datos_demo_reservaciones

Crea (si no existen) mesas, algunos clientes y los roles "Anfitrión" y
"Gerente" con sus permisos. Se puede ejecutar varias veces sin duplicar datos.
Solo para desarrollo y demostración.
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from administracion.models import Cliente, Mesa
from seguridad.roles_base import permisos_del_rol

MESAS = [
    (1, 2, 'Ventana'), (2, 2, 'Ventana'), (3, 4, 'Salón principal'), (4, 4, 'Salón principal'),
    (5, 4, 'Salón principal'), (6, 6, 'Terraza'), (7, 6, 'Terraza'), (8, 10, 'Salón privado'),
]

CLIENTES = [
    ('Ana López', '7777-8888'), ('Carlos Martínez', '7012-3456'), ('María Hernández', '6123-4567'),
    ('José Ramírez', '2250-1000'), ('Lucía Flores', '7555-1212'),
]


class Command(BaseCommand):
    help = 'Carga mesas, clientes y el rol Anfitrión para probar el módulo de reservaciones.'

    def add_arguments(self, parser):
        parser.add_argument('--minimo', action='store_true', help='Carga dos mesas y dos clientes.')

    @transaction.atomic
    def handle(self, *args, **opciones):
        mesas_demo = MESAS
        clientes_demo = CLIENTES
        if opciones['minimo']:
            mesas_demo = [mesa for mesa in MESAS if mesa[0] in (1, 3)]
            clientes_demo = CLIENTES[:2]

        mesas = sum(Mesa.objects.get_or_create(numero=n, defaults={'capacidad': c, 'ubicacion': u})[1]
                    for n, c, u in mesas_demo)
        clientes = sum(Cliente.objects.get_or_create(telefono=t, defaults={'nombre': n})[1]
                       for n, t in clientes_demo)
        for nombre_rol in ('Anfitrión', 'Gerente'):
            rol, creado = Group.objects.get_or_create(name=nombre_rol)
            if creado:
                rol.permissions.set(permisos_del_rol(nombre_rol))
        self.stdout.write(self.style.SUCCESS(
            f'Listo: {mesas} mesas y {clientes} clientes nuevos; roles "Anfitrión" y "Gerente" con sus permisos.'))
