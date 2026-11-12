from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse

from .forms import EmpleadoEditarForm
from .models import Empleado, Usuario


class EdicionEmpleadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.encargado = Usuario.objects.create_user('editor-empleados')
        cls.encargado.user_permissions.set(Permission.objects.filter(
            content_type__app_label='seguridad', codename__in=['view_empleado', 'change_empleado']))
        cls.consulta = Usuario.objects.create_user('lector-empleados')
        cls.consulta.user_permissions.add(Permission.objects.get(codename='view_empleado'))
        cls.cuenta = Usuario.objects.create_user('cuenta-empleado', first_name='Nombre de cuenta')
        cls.cuenta.groups.add(Group.objects.create(name='Mesero edición'))
        cls.empleado = Empleado.objects.create(
            nombres='Ana María', apellidos='López Pérez', cargo='Mesera', telefono='7777-8888',
            correo='ana@example.com', fecha_ingreso=date(2026, 10, 1), salario_mensual=Decimal('450.25'),
            usuario=cls.cuenta,
        )

    def setUp(self):
        self.client.force_login(self.encargado)
        self.url = reverse('seguridad:editar_empleado', args=[self.empleado.pk])
        self.detalle = reverse('seguridad:detalle_empleado', args=[self.empleado.pk])
        self.lista = reverse('seguridad:lista_empleados')
        self.datos = {'nombres': 'Ana María', 'apellidos': 'López Pérez', 'cargo': 'Mesera',
                      'telefono': '7777-8888', 'correo': 'ana@example.com',
                      'fecha_ingreso': '2026-10-01', 'salario_mensual': '450.25'}

    def test_get_muestra_datos_y_fecha_sin_guardar(self):
        antes = Empleado.objects.values().get(pk=self.empleado.pk)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Guardar cambios')
        self.assertContains(respuesta, 'value="2026-10-01"')
        self.assertContains(respuesta, self.empleado.codigo)
        self.assertEqual(Empleado.objects.values().get(pk=self.empleado.pk), antes)

    def test_actualiza_datos_conservando_identidad_cuenta_y_usuario(self):
        creado = self.empleado.fecha_creacion
        codigo = self.empleado.codigo
        cuenta_antes = Usuario.objects.values().get(pk=self.cuenta.pk)
        roles_antes = list(self.cuenta.groups.values_list('pk', flat=True))
        respuesta = self.client.post(self.url, {**self.datos, 'nombres': 'Ana', 'cargo': 'Supervisora',
                                               'telefono': '7777-9999', 'correo': 'nuevo@example.com',
                                               'fecha_ingreso': '2026-10-02', 'salario_mensual': '600.50'})
        self.assertRedirects(respuesta, self.detalle)
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.nombres, 'Ana')
        self.assertEqual(self.empleado.cargo, 'Supervisora')
        self.assertEqual(self.empleado.fecha_ingreso, date(2026, 10, 2))
        self.assertEqual(self.empleado.salario_mensual, Decimal('600.50'))
        self.assertEqual(self.empleado.codigo, codigo)
        self.assertEqual(self.empleado.fecha_creacion, creado)
        self.assertEqual(self.empleado.usuario_id, self.cuenta.pk)
        self.assertEqual(Usuario.objects.values().get(pk=self.cuenta.pk), cuenta_antes)
        self.assertEqual(list(self.cuenta.groups.values_list('pk', flat=True)), roles_antes)

    def test_permite_vaciar_opcionales_y_salario_sigue_siendo_null(self):
        self.client.post(self.url, {**self.datos, 'telefono': '', 'correo': '', 'salario_mensual': ''})
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.telefono, '')
        self.assertEqual(self.empleado.correo, '')
        self.assertIsNone(self.empleado.salario_mensual)

    def test_rechaza_datos_invalidos_sin_guardar_parcialmente(self):
        antes = Empleado.objects.values().get(pk=self.empleado.pk)
        for campo, valor in (('nombres', '   '), ('apellidos', ''), ('cargo', ''),
                             ('correo', 'invalido'), ('fecha_ingreso', '2026-02-30'),
                             ('salario_mensual', '-1'), ('salario_mensual', '1.123')):
            with self.subTest(campo=campo, valor=valor):
                respuesta = self.client.post(self.url, {**self.datos, 'nombres': 'Nombre modificado', campo: valor})
                self.assertIn(campo, respuesta.context['form'].errors)
                self.assertEqual(Empleado.objects.values().get(pk=self.empleado.pk), antes)

    def test_post_manipulado_no_cambia_estado_codigo_cuenta_ni_fechas_internas(self):
        self.client.post(self.url, {**self.datos, 'cargo': 'Gerente', 'activo': '', 'usuario': self.encargado.pk,
                                   'id': 999999, 'codigo': 'OTRO', 'fecha_creacion': '2000-01-01'})
        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.activo)
        self.assertEqual(self.empleado.usuario_id, self.cuenta.pk)
        self.assertNotEqual(self.empleado.pk, 999999)
        self.assertEqual(self.empleado.cargo, 'Gerente')

    def test_edita_desactivado_sin_reactivar_empleado_ni_cuenta(self):
        Empleado.objects.filter(pk=self.empleado.pk).update(activo=False)
        Usuario.objects.filter(pk=self.cuenta.pk).update(is_active=False)
        self.client.post(self.url, {**self.datos, 'cargo': 'Cargo actualizado', 'activo': 'on'})
        self.empleado.refresh_from_db()
        self.cuenta.refresh_from_db()
        self.assertFalse(self.empleado.activo)
        self.assertFalse(self.cuenta.is_active)
        self.assertEqual(self.empleado.cargo, 'Cargo actualizado')

    def test_guardar_edicion_no_sobrescribe_una_baja_concurrente(self):
        guardar_original = EmpleadoEditarForm.save
        def guardar_con_baja(form, commit=True):
            Empleado.objects.filter(pk=self.empleado.pk).update(activo=False)
            Usuario.objects.filter(pk=self.cuenta.pk).update(is_active=False)
            return guardar_original(form, commit=commit)
        with patch.object(EmpleadoEditarForm, 'save', autospec=True, side_effect=guardar_con_baja):
            self.client.post(self.url, {**self.datos, 'cargo': 'Supervisora'})
        self.empleado.refresh_from_db()
        self.assertFalse(self.empleado.activo)
        self.assertEqual(self.empleado.cargo, 'Supervisora')

    def test_guardar_edicion_no_sobrescribe_una_asociacion_concurrente(self):
        Empleado.objects.filter(pk=self.empleado.pk).update(usuario=None)
        guardar_original = EmpleadoEditarForm.save
        def guardar_con_asociacion(form, commit=True):
            Empleado.objects.filter(pk=self.empleado.pk).update(usuario=self.cuenta)
            return guardar_original(form, commit=commit)
        with patch.object(EmpleadoEditarForm, 'save', autospec=True, side_effect=guardar_con_asociacion):
            self.client.post(self.url, {**self.datos, 'cargo': 'Supervisora'})
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.usuario_id, self.cuenta.pk)

    def test_sin_cambios_no_actualiza_la_fecha_del_expediente(self):
        antes = Empleado.objects.values().get(pk=self.empleado.pk)
        self.client.post(self.url, self.datos)
        self.assertEqual(Empleado.objects.values().get(pk=self.empleado.pk), antes)

    def test_conserva_el_contexto_del_listado_y_rechaza_redirecciones_ajenas(self):
        siguiente = self.lista + '?q=Ana&estado=activo&pagina=2'
        respuesta = self.client.get(self.url, {'siguiente': siguiente})
        self.assertEqual(respuesta.context['volver_url'], siguiente)
        self.assertRedirects(self.client.post(self.url, {**self.datos, 'siguiente': siguiente}), siguiente)
        for destino in ('https://ajeno.example/seguridad/empleados/', '/seguridad/usuarios/',
                        reverse('seguridad:detalle_empleado', args=[999999])):
            self.assertRedirects(self.client.post(self.url, {**self.datos, 'siguiente': destino}), self.detalle)

    def test_muestra_editar_en_lista_y_detalle_solo_con_permiso(self):
        for url in (self.lista, self.detalle):
            self.assertContains(self.client.get(url), self.url)
        self.client.force_login(self.consulta)
        for url in (self.lista, self.detalle):
            self.assertNotContains(self.client.get(url), self.url)

    def test_exige_login_permiso_post_con_csrf_y_id_existente(self):
        self.client.force_login(self.consulta)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.encargado)
        self.assertEqual(self.client.get(reverse('seguridad:editar_empleado', args=[999999])).status_code, 404)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.encargado)
        self.assertEqual(cliente.post(self.url, self.datos).status_code, 403)

    def test_permiso_de_cambio_sin_consulta_regresa_al_inicio(self):
        self.consulta.user_permissions.set([Permission.objects.get(codename='change_empleado')])
        self.client.force_login(self.consulta)
        self.assertRedirects(self.client.post(self.url, {**self.datos, 'cargo': 'Nuevo cargo'}), reverse('core:home'))
