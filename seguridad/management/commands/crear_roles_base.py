from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from seguridad.roles_base import ROLES_BASE, permisos_del_rol


class Command(BaseCommand):
    help = 'Crea los roles base de SIREP.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--actualizar', action='store_true',
            help='Restablece los permisos de los roles base que ya existen.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        for nombre in ROLES_BASE:
            rol, creado = Group.objects.get_or_create(name=nombre)
            if not creado and not options['actualizar']:
                self.stdout.write(f'{nombre}: ya existe.')
                continue
            permisos = permisos_del_rol(nombre)
            rol.permissions.set(permisos)
            accion = 'creado' if creado else 'actualizado'
            self.stdout.write(f'{nombre}: {accion}, {len(permisos)} permisos.')
