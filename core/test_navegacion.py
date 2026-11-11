from datetime import timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from administracion.models import Cliente, Mesa
from pedidos.models import Pedido
from reservaciones.models import Atencion, Reservacion
from seguridad.models import Empleado, Usuario


class NavegacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user('operador-panel', password='Clave-panel-2026')
        cls.administrador = Usuario.objects.create_superuser('admin-panel', password='Clave-panel-2026')

    def setUp(self):
        self.client.force_login(self.usuario)

    def permitir(self, *permisos):
        self.usuario.user_permissions.set(Permission.objects.filter(codename__in=permisos))

    def modulo(self, clave):
        return reverse('core:modulo', kwargs={'modulo': clave})

    def test_modulos_y_dashboard_exigen_login(self):
        self.client.logout()
        for url in (reverse('core:home'), self.modulo('seguridad'), self.modulo('pedidos')):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_sin_permisos_no_hay_indicadores_ni_accesos_de_negocio(self):
        respuesta = self.client.get(reverse('core:home'))
        self.assertEqual(respuesta.context['indicadores'], [])
        self.assertIsNone(respuesta.context['agenda'])
        self.assertIsNone(respuesta.context['estados_pedidos'])
        self.assertEqual(respuesta.context['modulos_navegacion'], [])
        self.assertContains(respuesta, 'Solicita al administrador')
        self.assertEqual(self.client.get(self.modulo('seguridad')).status_code, 403)

    def test_sidebar_contiene_modulos_y_no_los_listados_individuales(self):
        self.permitir('view_usuario', 'view_empleado')
        respuesta = self.client.get(reverse('core:home'))
        sidebar = respuesta.content.decode().split('</aside>')[0]
        self.assertIn(self.modulo('seguridad'), sidebar)
        self.assertNotIn(reverse('seguridad:lista_usuarios'), sidebar)
        self.assertNotIn(reverse('seguridad:lista_empleados'), sidebar)
        self.assertNotIn(self.modulo('administracion'), sidebar)
        self.assertNotIn(self.modulo('pedidos'), sidebar)

    def test_modulo_seguridad_muestra_solo_accesos_autorizados(self):
        self.permitir('view_usuario')
        respuesta = self.client.get(self.modulo('seguridad'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, reverse('seguridad:lista_usuarios'))
        self.assertNotContains(respuesta, 'href="' + reverse('seguridad:lista_empleados') + '"')
        self.assertNotContains(respuesta, reverse('seguridad:lista_roles'))
        self.assertEqual(self.client.get(self.modulo('administracion')).status_code, 403)
        self.assertEqual(respuesta.context['modulo_actual'], 'seguridad')

    def test_solo_registro_puede_abrir_su_modulo_y_va_al_formulario(self):
        self.permitir('add_empleado')
        respuesta = self.client.get(self.modulo('seguridad'))
        self.assertContains(respuesta, reverse('seguridad:crear_empleado'))
        self.assertNotContains(respuesta, 'href="' + reverse('seguridad:lista_empleados') + '"')

    def test_rol_consulta_group_sin_permisos_de_seguridad_puede_abrir_roles(self):
        self.permitir('view_group')
        respuesta = self.client.get(self.modulo('seguridad'))
        self.assertContains(respuesta, reverse('seguridad:lista_roles'))
        self.assertNotContains(respuesta, reverse('seguridad:lista_usuarios'))

    def test_modulo_desconocido_es_404(self):
        self.assertEqual(self.client.get(self.modulo('no-existe')).status_code, 404)

    def test_todos_los_accesos_del_administrador_resuelven(self):
        self.client.force_login(self.administrador)
        for modulo in ('seguridad', 'administracion', 'reservaciones', 'pedidos'):
            respuesta = self.client.get(self.modulo(modulo))
            self.assertEqual(respuesta.status_code, 200)
            for acceso in respuesta.context['modulo']['accesos']:
                with self.subTest(acceso=acceso['nombre']):
                    self.assertEqual(self.client.get(acceso['url']).status_code, 200)

    def test_indicadores_y_agenda_provienen_de_datos_reales(self):
        self.client.force_login(self.administrador)
        mesa = Mesa.objects.create(numero=1, capacidad=4)
        cliente = Cliente.objects.create(nombre='Ana López', telefono='7777-8888')
        atencion = Atencion.objects.create(mesa=mesa, cantidad_personas=2)
        Pedido.objects.create(mesa=mesa, atencion=atencion, mesero=self.administrador)
        Pedido.objects.create(mesa=mesa, atencion=atencion, mesero=self.administrador, estado=Pedido.Estado.CANCELADO)
        reserva = Reservacion.objects.create(mesa=mesa, cliente=cliente, cantidad_personas=2, fecha_hora_inicio=timezone.now())
        Reservacion.objects.create(mesa=mesa, cliente=cliente, cantidad_personas=2, fecha_hora_inicio=timezone.now() + timedelta(days=1))
        Empleado.objects.create(nombres='Ana', apellidos='López', cargo='Mesera', fecha_ingreso=timezone.localdate())
        respuesta = self.client.get(reverse('core:home'))
        indicadores = {item['nombre']: item['valor'] for item in respuesta.context['indicadores']}
        self.assertEqual(indicadores, {'Reservaciones hoy': 1, 'Mesas ocupadas': 1, 'Pedidos en curso': 1, 'Empleados activos': 1})
        self.assertEqual(list(respuesta.context['agenda']), [reserva])
        estados = respuesta.context['estados_pedidos']
        self.assertEqual(sum(estado['total'] for estado in estados), 1)
        self.assertEqual(estados[0]['porcentaje'], 100)

    def test_permiso_de_empleados_no_revela_operacion_de_restaurante(self):
        self.permitir('view_empleado')
        respuesta = self.client.get(reverse('core:home'))
        self.assertEqual([item['nombre'] for item in respuesta.context['indicadores']], ['Empleados activos'])
        self.assertIsNone(respuesta.context['agenda'])
        self.assertIsNone(respuesta.context['estados_pedidos'])
        self.assertEqual(respuesta.context['accesos_rapidos'], [])

    def test_login_mantiene_next_y_autenticacion(self):
        self.client.logout()
        destino = reverse('seguridad:mi_perfil')
        respuesta = self.client.get(reverse('seguridad:login'), {'next': destino})
        self.assertContains(respuesta, 'name="next"')
        respuesta = self.client.post(reverse('seguridad:login'), {'username': self.usuario.username,
                                    'password': 'Clave-panel-2026', 'next': destino})
        self.assertRedirects(respuesta, destino)

    def test_login_conserva_error_de_credenciales_sin_exponer_password(self):
        self.client.logout()
        respuesta = self.client.post(reverse('seguridad:login'), {'username': self.usuario.username, 'password': 'incorrecta-secreta'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context['form'].non_field_errors())
        self.assertContains(respuesta, 'role="alert"')
        self.assertNotContains(respuesta, 'incorrecta-secreta')
