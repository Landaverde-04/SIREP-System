"""Prepara los datos mínimos para demostrar el flujo completo de SIREP."""

import os
import sys
from getpass import getpass

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from seguridad.models import Usuario


CLAVE_ADMIN = 'SIREP_DEMO_ADMIN_PASSWORD'
CLAVE_OPERACION = 'SIREP_DEMO_PASSWORD'
CUENTAS = {
    'admin': ('Administrador', CLAVE_ADMIN),
    'gerente': ('Gerente', CLAVE_OPERACION),
    'anfitrion': ('Anfitrión', CLAVE_OPERACION),
    'mesero': ('Mesero', CLAVE_OPERACION),
    'cocina': ('Encargado de cocina', CLAVE_OPERACION),
    'cajero': ('Cajero', CLAVE_OPERACION),
}


class Command(BaseCommand):
    help = 'Carga seis cuentas de demostración, sus roles y los datos mínimos para la prueba de humo.'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument('--reiniciar', action='store_true',
                            help='Borra los datos de SIREP en la base configurada y vuelve a cargar la demostración.')
        parser.add_argument('--no-input', '--noinput', dest='interactive', action='store_false',
                            help='Obtiene las contraseñas de las variables de entorno.')

    def handle(self, *args, **options):
        reiniciar = options['reiniciar']
        existentes = {} if reiniciar else Usuario.objects.in_bulk(CUENTAS, field_name='username')
        claves = {}
        for nombre, (_, variable) in CUENTAS.items():
            if nombre in existentes:
                continue
            if variable not in claves:
                claves[variable] = self.leer_clave(variable, options['interactive'])
            try:
                validate_password(claves[variable], Usuario(username=nombre))
            except ValidationError as error:
                raise CommandError(f'{variable} para {nombre}: {" ".join(error.messages)}') from error

        with transaction.atomic():
            if reiniciar:
                call_command('flush', interactive=False, verbosity=0)
            call_command('crear_roles_base', stdout=self.stdout)
            self.cargar_usuarios(existentes, claves)
            call_command('datos_demo_reservaciones', minimo=True, stdout=self.stdout)
            call_command('datos_demo_pedidos', minimo=True, stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS('Datos de demostración listos.'))

    def leer_clave(self, variable, interactivo):
        clave = os.environ.get(variable)
        if clave:
            return clave
        if interactivo and sys.stdin.isatty():
            clave = getpass(f'Contraseña para {variable}: ')
            if clave and clave == getpass('Confirmar contraseña: '):
                return clave
            raise CommandError('La contraseña no coincide o se dejó vacía.')
        raise CommandError(f'Configura {variable} para crear las cuentas de demostración que faltan.')

    def cargar_usuarios(self, existentes, claves):
        roles = Group.objects.in_bulk((rol for rol, _ in CUENTAS.values()), field_name='name')
        for nombre, (rol, variable) in CUENTAS.items():
            es_admin = nombre == 'admin'
            if nombre in existentes:
                usuario, creado = existentes[nombre], False
            else:
                usuario, creado = Usuario.objects.get_or_create(
                    username=nombre, defaults={
                        'password': lambda: make_password(claves[variable]),
                        'is_staff': es_admin,
                        'is_superuser': es_admin,
                    },
                )
            if creado:
                usuario.groups.add(roles[rol])
                self.stdout.write(f'{nombre} creado con rol {rol}.')
            else:
                tiene_acceso = usuario.is_superuser if es_admin else usuario.groups.filter(pk=roles[rol].pk).exists()
                if not usuario.is_active or not tiene_acceso:
                    acceso = 'sea superusuario' if es_admin else f'tenga el rol {rol}'
                    self.stderr.write(self.style.WARNING(f'{nombre} ya existe. Revisa que esté activo y {acceso}.'))
                self.stdout.write(f'{nombre} ya existe.')
