from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .models import Empleado, Usuario


class AsociacionEmpleadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administrador = Usuario.objects.create_user('administrador-asociaciones')
        cls.administrador.user_permissions.set(Permission.objects.filter(
            content_type__app_label='seguridad', codename__in=[
                'view_empleado', 'change_empleado', 'view_usuario', 'change_usuario',
            ],
        ))
        cls.consulta = Usuario.objects.create_user('consulta-asociaciones')
        cls.consulta.user_permissions.add(Permission.objects.get(codename='view_empleado'))
        cls.empleado = Empleado.objects.create(nombres='Ana', apellidos='López', cargo='Mesera', fecha_ingreso=date(2026, 11, 10))
        cls.otro = Empleado.objects.create(nombres='Mario', apellidos='Soto', cargo='Cocinero', fecha_ingreso=date(2026, 11, 10))
        cls.usuarios = [Usuario.objects.create_user(f'libre{i:02}', first_name='Persona', last_name='Prueba') for i in range(12)]
        cls.objetivo = Usuario.objects.create_user('zzz-objetivo', first_name='Zulema', last_name='Soto', email='objetivo@example.com')
        cls.rol = Group.objects.create(name='Rol de prueba asociación')
        cls.objetivo.groups.add(cls.rol)
        cls.inactivo = Usuario.objects.create_user('libre-inactivo', is_active=False)

    def setUp(self):
        self.client.force_login(self.administrador)
        self.detalle = reverse('seguridad:detalle_empleado', args=[self.empleado.pk])
        self.disponibles = reverse('seguridad:usuarios_disponibles_empleado', args=[self.empleado.pk])
        self.asociar = reverse('seguridad:asociar_usuario_empleado', args=[self.empleado.pk])
        self.desactivar = reverse('seguridad:desactivar_empleado', args=[self.empleado.pk])
        self.activar = reverse('seguridad:activar_empleado', args=[self.empleado.pk])

    def vincular(self, usuario=None):
        self.empleado.usuario = usuario or self.objetivo
        self.empleado.save(update_fields=['usuario'])

    def test_detalle_y_enlace_desde_listado(self):
        self.assertContains(self.client.get(reverse('seguridad:lista_empleados')), self.detalle)
        respuesta = self.client.get(self.detalle)
        self.assertContains(respuesta, 'Sin usuario asociado')
        self.assertContains(respuesta, 'modal-asociar-usuario')
        self.assertContains(respuesta, 'busqueda-usuario-disponible')

    def test_excluye_usuarios_asignados_incluso_a_empleados_inactivos(self):
        self.otro.usuario = self.objetivo
        self.otro.activo = False
        self.otro.save()
        respuesta = self.client.get(self.disponibles, {'q': 'zzz-objetivo'})
        self.assertEqual(respuesta.context['usuarios'].paginator.count, 0)
        self.assertNotContains(respuesta, 'value="' + str(self.objetivo.pk) + '"')

    def test_pagina_de_ocho_usuarios_y_busqueda_global(self):
        pagina = self.client.get(self.disponibles).context['usuarios']
        self.assertEqual(len(pagina), 8)
        segunda = self.client.get(self.disponibles, {'pagina': 2}).context['usuarios']
        self.assertFalse({u.pk for u in pagina} & {u.pk for u in segunda})
        self.assertNotIn(self.objetivo, pagina)
        for consulta in ('Zu', 'Zulema Soto', 'objetivo@', 'zzz-objetivo'):
            with self.subTest(consulta=consulta):
                self.assertEqual(list(self.client.get(self.disponibles, {'q': consulta}).context['usuarios']), [self.objetivo])
        self.assertEqual(self.client.get(self.disponibles, {'q': 'Z'}).context['usuarios'].paginator.count, pagina.paginator.count)

    def test_muestra_tambien_cuentas_inactivas_con_su_estado(self):
        respuesta = self.client.get(self.disponibles, {'q': 'libre-inactivo'})
        self.assertEqual(list(respuesta.context['usuarios']), [self.inactivo])
        self.assertContains(respuesta, 'Desactivada')

    def test_asocia_sin_cambiar_credenciales_roles_estado_ni_datos_personales(self):
        antes = Usuario.objects.values().get(pk=self.objetivo.pk)
        roles_antes = list(self.objetivo.groups.values_list('pk', flat=True))
        self.assertRedirects(self.client.post(self.asociar, {'usuario': self.objetivo.pk}), self.detalle)
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.usuario_id, self.objetivo.pk)
        self.assertEqual(Usuario.objects.values().get(pk=self.objetivo.pk), antes)
        self.assertEqual(list(self.objetivo.groups.values_list('pk', flat=True)), roles_antes)
        respuesta = self.client.get(self.detalle)
        self.assertContains(respuesta, self.objetivo.username)
        self.assertNotContains(respuesta, 'modal-asociar-usuario')
        self.assertContains(respuesta, reverse('seguridad:detalle_usuario', args=[self.objetivo.pk]))

    def test_asociar_cuenta_inactiva_no_la_reactiva(self):
        self.client.post(self.asociar, {'usuario': self.inactivo.pk})
        self.inactivo.refresh_from_db()
        self.assertFalse(self.inactivo.is_active)
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.usuario_id, self.inactivo.pk)

    def test_no_sustituye_la_cuenta_ya_asociada(self):
        self.vincular()
        respuesta = self.client.post(self.asociar, {'usuario': self.inactivo.pk}, follow=True)
        self.assertContains(respuesta, 'ya tiene un usuario asociado')
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.usuario_id, self.objetivo.pk)

    def test_revalida_usuario_asignado_despues_de_abrir_selector(self):
        self.assertEqual(self.client.get(self.disponibles, {'q': 'zzz-objetivo'}).context['usuarios'].paginator.count, 1)
        self.otro.usuario = self.objetivo
        self.otro.save()
        respuesta = self.client.post(self.asociar, {'usuario': self.objetivo.pk}, follow=True)
        self.assertContains(respuesta, 'ya está asociado a otro empleado')
        self.empleado.refresh_from_db()
        self.assertIsNone(self.empleado.usuario_id)

    def test_base_impide_dos_empleados_para_una_cuenta(self):
        self.vincular()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.otro.usuario = self.objetivo
            self.otro.save()

    def test_requiere_reactivar_empleado_incluso_con_post_manipulado(self):
        self.empleado.activo = False
        self.empleado.save()
        self.assertNotContains(self.client.get(self.detalle), 'modal-asociar-usuario')
        self.assertEqual(self.client.get(self.disponibles).status_code, 409)
        respuesta = self.client.post(self.asociar, {'usuario': self.objetivo.pk}, follow=True)
        self.assertContains(respuesta, 'Primero debes reactivar')
        self.empleado.refresh_from_db()
        self.assertIsNone(self.empleado.usuario_id)
        self.objetivo.refresh_from_db()
        self.assertTrue(self.objetivo.is_active)

    def test_usuario_invalido_o_inexistente_no_asocia(self):
        for valor in ('', 'texto', '-1', '999999', '1' * 100):
            with self.subTest(valor=valor):
                self.assertRedirects(self.client.post(self.asociar, {'usuario': valor}), self.detalle)
                self.empleado.refresh_from_db()
                self.assertIsNone(self.empleado.usuario_id)

    def test_selector_no_disponible_cuando_ya_tiene_cuenta(self):
        self.vincular()
        respuesta = self.client.get(self.disponibles)
        self.assertEqual(respuesta.status_code, 409)
        self.assertNotContains(respuesta, 'name="usuario"', status_code=409)

    def test_permisos_y_login_en_detalle_selector_y_asociacion(self):
        self.client.force_login(self.consulta)
        self.assertEqual(self.client.get(self.detalle).status_code, 200)
        self.assertNotContains(self.client.get(self.detalle), 'modal-asociar-usuario')
        self.assertEqual(self.client.get(self.disponibles).status_code, 403)
        self.assertEqual(self.client.post(self.asociar, {'usuario': self.objetivo.pk}).status_code, 403)
        self.consulta.user_permissions.add(Permission.objects.get(codename='change_empleado'))
        self.assertEqual(self.client.get(self.disponibles).status_code, 403)
        self.client.logout()
        for url in (self.detalle, self.disponibles, self.asociar):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_asociacion_exige_post_y_csrf(self):
        self.assertEqual(self.client.get(self.asociar).status_code, 405)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.administrador)
        self.assertEqual(cliente.post(self.asociar, {'usuario': self.objetivo.pk}).status_code, 403)

    def test_desactivar_empleado_desactiva_cuenta_y_conserva_relacion(self):
        self.vincular()
        confirmacion = self.client.get(self.desactivar)
        self.assertContains(confirmacion, 'También se desactivará la cuenta')
        self.client.post(self.desactivar)
        self.empleado.refresh_from_db()
        self.objetivo.refresh_from_db()
        self.assertFalse(self.empleado.activo)
        self.assertFalse(self.objetivo.is_active)
        self.assertEqual(self.empleado.usuario_id, self.objetivo.pk)
        self.assertTrue(self.objetivo.groups.filter(pk=self.rol.pk).exists())

    def test_baja_es_atomica_si_falla_la_cuenta_no_cambia_empleado(self):
        self.vincular()
        with patch.object(Usuario, 'save', side_effect=RuntimeError('fallo simulado')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.desactivar)
        self.empleado.refresh_from_db()
        self.objetivo.refresh_from_db()
        self.assertTrue(self.empleado.activo)
        self.assertTrue(self.objetivo.is_active)

    def test_reactivar_empleado_no_reactiva_cuenta(self):
        self.vincular()
        self.client.post(self.desactivar)
        self.client.post(self.activar)
        self.empleado.refresh_from_db()
        self.objetivo.refresh_from_db()
        self.assertTrue(self.empleado.activo)
        self.assertFalse(self.objetivo.is_active)

    def test_no_desactiva_la_propia_cuenta_desde_empleado(self):
        self.vincular(self.administrador)
        for metodo in ('get', 'post'):
            getattr(self.client, metodo)(self.desactivar)
            self.empleado.refresh_from_db()
            self.administrador.refresh_from_db()
            self.assertTrue(self.empleado.activo)
            self.assertTrue(self.administrador.is_active)
        self.assertNotContains(self.client.get(self.detalle), self.desactivar)

    def test_desactivar_solo_usuario_no_desactiva_empleado(self):
        self.vincular()
        self.client.post(reverse('seguridad:desactivar_usuario', args=[self.objetivo.pk]))
        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.activo)

    def test_reactivar_cuenta_exige_empleado_activo_tambien_desde_edicion(self):
        self.vincular()
        self.client.post(self.desactivar)
        activar_usuario = reverse('seguridad:activar_usuario', args=[self.objetivo.pk])
        self.client.post(activar_usuario)
        editar_usuario = reverse('seguridad:editar_usuario', args=[self.objetivo.pk])
        respuesta = self.client.post(editar_usuario, {'username': self.objetivo.username, 'is_active': 'on'})
        self.assertIn('is_active', respuesta.context['form'].errors)
        self.objetivo.refresh_from_db()
        self.assertFalse(self.objetivo.is_active)
        self.client.post(self.activar)
        self.client.post(activar_usuario)
        self.objetivo.refresh_from_db()
        self.assertTrue(self.objetivo.is_active)

    def test_selector_escapa_datos_y_no_devuelve_credenciales(self):
        self.objetivo.first_name = '<script>alert(1)</script>'
        self.objetivo.save()
        respuesta = self.client.get(self.disponibles, {'q': 'zzz-objetivo'})
        self.assertContains(respuesta, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(respuesta, '<script>alert(1)</script>')
        self.assertNotContains(respuesta, self.objetivo.password)
