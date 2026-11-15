from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, TransactionTestCase

from administracion.models import CategoriaProducto, Cliente, Mesa, Producto
from seguridad.models import Usuario


CLAVE_ADMIN = 'Prueba-Humo-Gestion-27!'
CLAVE_OPERACION = 'Prueba-Humo-Operacion-51!'


class CargarDatosDemoTests(TestCase):
    def cargar(self):
        with patch.dict('os.environ', {
            'SIREP_DEMO_ADMIN_PASSWORD': CLAVE_ADMIN,
            'SIREP_DEMO_PASSWORD': CLAVE_OPERACION,
        }):
            call_command('cargar_datos_demo', '--no-input', stdout=StringIO())

    def test_carga_cuentas_por_rol_y_datos_minimos(self):
        self.cargar()

        roles = {
            'admin': ('Administrador', 'seguridad.view_usuario'),
            'gerente': ('Gerente', 'administracion.add_mesa'),
            'anfitrion': ('Anfitrión', 'reservaciones.add_atencion'),
            'mesero': ('Mesero', 'pedidos.entregar_pedido'),
            'cocina': ('Encargado de cocina', 'pedidos.preparar_pedido'),
            'cajero': ('Cajero', 'cobro.add_cobro'),
        }
        self.assertEqual(Usuario.objects.count(), 6)
        for nombre, (rol, permiso) in roles.items():
            usuario = Usuario.objects.get(username=nombre)
            self.assertEqual(list(usuario.groups.values_list('name', flat=True)), [rol])
            self.assertTrue(usuario.has_perm(permiso))
            self.assertEqual(usuario.is_superuser, nombre == 'admin')
            self.assertEqual(usuario.is_staff, nombre == 'admin')
            clave = CLAVE_ADMIN if nombre == 'admin' else CLAVE_OPERACION
            self.assertTrue(self.client.login(username=nombre, password=clave))
            self.client.logout()

        self.assertFalse(Usuario.objects.get(username='mesero').has_perm('seguridad.view_usuario'))
        self.assertTrue(Usuario.objects.get(username='admin').has_perm('cobro.add_cobro'))
        self.assertEqual(list(Mesa.objects.values_list('numero', 'capacidad')), [(1, 2), (3, 4)])
        self.assertEqual(Cliente.objects.count(), 2)
        self.assertEqual(set(CategoriaProducto.objects.values_list('nombre', flat=True)),
                         {'Entradas', 'Platos fuertes'})
        self.assertEqual(set(Producto.objects.ofertables().values_list('nombre', flat=True)),
                         {'Sopa del día', 'Pollo a la plancha'})

    def test_repetir_sin_secretos_conserva_cambios_y_no_duplica(self):
        self.cargar()
        usuario = Usuario.objects.get(username='mesero')
        usuario.set_password('Cambio local de cuenta 14!')
        usuario.save(update_fields=['password'])
        hash_guardado = usuario.password
        mesa = Mesa.objects.get(numero=1)
        mesa.capacidad = 3
        mesa.save(update_fields=['capacidad'])
        sopa = Producto.objects.get(nombre='Sopa del día')
        sopa.nombre = 'SOPA DEL DÍA'
        sopa.disponible = False
        sopa.save(update_fields=['nombre', 'disponible'])
        rol = Group.objects.get(name='Mesero')
        rol.permissions.clear()

        with patch.dict('os.environ', {'SIREP_DEMO_ADMIN_PASSWORD': '', 'SIREP_DEMO_PASSWORD': ''}):
            call_command('cargar_datos_demo', '--no-input', stdout=StringIO())

        usuario.refresh_from_db()
        mesa.refresh_from_db()
        sopa.refresh_from_db()
        self.assertEqual(usuario.password, hash_guardado)
        self.assertEqual(mesa.capacidad, 3)
        self.assertEqual(sopa.nombre, 'SOPA DEL DÍA')
        self.assertFalse(sopa.disponible)
        self.assertFalse(rol.permissions.exists())
        self.assertEqual((Usuario.objects.count(), Mesa.objects.count(), Cliente.objects.count(),
                          CategoriaProducto.objects.count(), Producto.objects.count()), (6, 2, 2, 2, 2))

    def test_sin_clave_de_operacion_no_hay_carga_parcial(self):
        with patch.dict('os.environ', {
            'SIREP_DEMO_ADMIN_PASSWORD': CLAVE_ADMIN,
            'SIREP_DEMO_PASSWORD': '',
        }):
            with self.assertRaisesMessage(CommandError, 'SIREP_DEMO_PASSWORD'):
                call_command('cargar_datos_demo', '--no-input', stdout=StringIO())

        for model in (Usuario, Group, Mesa, Cliente, CategoriaProducto, Producto):
            self.assertFalse(model.objects.exists())


class ReiniciarDatosDemoTests(TransactionTestCase):
    def setUp(self):
        Usuario.objects.create_user(username='anterior')
        Mesa.objects.create(numero=91, capacidad=7)

    @patch.dict('os.environ', {
        'SIREP_DEMO_ADMIN_PASSWORD': CLAVE_ADMIN,
        'SIREP_DEMO_PASSWORD': CLAVE_OPERACION,
    })
    def test_reinicia_la_base_y_crea_admin_superusuario(self):
        call_command('cargar_datos_demo', '--reiniciar', '--no-input', stdout=StringIO())
        self.assertEqual(set(Usuario.objects.values_list('username', flat=True)),
                         {'admin', 'gerente', 'anfitrion', 'mesero', 'cocina', 'cajero'})
        self.assertTrue(Usuario.objects.get(username='admin').is_superuser)
        self.assertEqual(list(Mesa.objects.values_list('numero', 'capacidad')), [(1, 2), (3, 4)])
        self.assertEqual((Cliente.objects.count(), Producto.objects.count()), (2, 2))

    @patch.dict('os.environ', {
        'SIREP_DEMO_ADMIN_PASSWORD': CLAVE_ADMIN,
        'SIREP_DEMO_PASSWORD': CLAVE_OPERACION,
    })
    def test_reinicio_revierte_el_borrado_si_falla_la_carga(self):
        def ejecutar(nombre, *args, **kwargs):
            if nombre == 'datos_demo_pedidos':
                raise CommandError('Carga interrumpida')
            return call_command(nombre, *args, **kwargs)

        with patch('core.management.commands.cargar_datos_demo.call_command', side_effect=ejecutar):
            with self.assertRaisesMessage(CommandError, 'Carga interrumpida'):
                call_command('cargar_datos_demo', '--reiniciar', '--no-input', stdout=StringIO())
        self.assertEqual(list(Usuario.objects.values_list('username', flat=True)), ['anterior'])
        self.assertEqual(list(Mesa.objects.values_list('numero', flat=True)), [91])
