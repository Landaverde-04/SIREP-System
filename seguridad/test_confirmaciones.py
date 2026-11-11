from datetime import date

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from .models import Empleado, Usuario


class ConfirmacionesSeguridadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administrador = Usuario.objects.create_user('gestor-confirmaciones')
        cls.administrador.user_permissions.set(Permission.objects.filter(codename__in=[
            'view_usuario', 'change_usuario', 'view_empleado', 'change_empleado', 'view_group', 'delete_group']))
        cls.usuario = Usuario.objects.create_user('cuenta-confirmaciones')
        cls.empleado = Empleado.objects.create(nombres='Ana', apellidos='López', cargo='Mesera',
                                               fecha_ingreso=date(2026, 11, 10), usuario=cls.usuario)
        cls.rol = Group.objects.create(name='Rol de confirmación')
        cls.usuario.groups.add(cls.rol)
        cls.sin_permisos = Usuario.objects.create_user('sin-confirmaciones')

    def setUp(self):
        self.client.force_login(self.administrador)

    def url(self, nombre, objeto):
        return reverse('seguridad:' + nombre, args=[objeto.pk])

    def confirmar(self, nombre, objeto, **parametros):
        return self.client.get(self.url(nombre, objeto), parametros, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_confirmaciones_ajax_son_fragmentos_y_no_cambian_registros(self):
        usuarios = list(Usuario.objects.order_by('pk').values())
        empleados = list(Empleado.objects.order_by('pk').values())
        for nombre, objeto in (('desactivar_usuario', self.usuario), ('activar_usuario', self.usuario),
                               ('desactivar_empleado', self.empleado), ('activar_empleado', self.empleado),
                               ('eliminar_rol', self.rol)):
            with self.subTest(nombre=nombre):
                respuesta = self.confirmar(nombre, objeto)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTemplateUsed(respuesta, 'seguridad/confirmacion_accion.html')
                self.assertContains(respuesta, 'data-confirmacion-seguridad')
                self.assertContains(respuesta, 'csrfmiddlewaretoken')
                self.assertContains(respuesta, 'data-cerrar-confirmacion')
                self.assertNotContains(respuesta, '<!DOCTYPE html>')
                self.assertNotContains(respuesta, '<aside')
                self.assertIn('no-store', respuesta.headers['Cache-Control'])
                self.assertIn('X-Requested-With', respuesta.headers['Vary'])
        self.assertEqual(list(Usuario.objects.order_by('pk').values()), usuarios)
        self.assertEqual(list(Empleado.objects.order_by('pk').values()), empleados)
        self.assertTrue(Group.objects.filter(pk=self.rol.pk).exists())

    def test_modal_empleado_advierte_sobre_baja_de_cuenta_asociada(self):
        respuesta = self.confirmar('desactivar_empleado', self.empleado)
        self.assertContains(respuesta, 'También se desactivará la cuenta')
        self.assertContains(respuesta, self.usuario.username)
        respuesta = self.confirmar('activar_empleado', self.empleado)
        self.assertContains(respuesta, 'Reactivarla será una acción independiente')

    def test_modal_rol_muestra_la_informacion_real_de_usuarios_asignados(self):
        respuesta = self.confirmar('eliminar_rol', self.rol)
        self.assertContains(respuesta, '1 usuario asignado')
        self.assertContains(respuesta, 'Sí, eliminar')
        self.assertContains(respuesta, 'action="' + self.url('eliminar_rol', self.rol) + '"')

    def test_post_estado_regresa_al_mismo_detalle(self):
        for nombre, objeto, detalle in (
            ('desactivar_usuario', self.usuario, 'detalle_usuario'),
            ('activar_usuario', self.usuario, 'detalle_usuario'),
            ('desactivar_empleado', self.empleado, 'detalle_empleado'),
            ('activar_empleado', self.empleado, 'detalle_empleado'),
        ):
            with self.subTest(nombre=nombre):
                destino = self.url(detalle, objeto)
                respuesta = self.confirmar(nombre, objeto, siguiente=destino)
                self.assertEqual(respuesta.context['siguiente'], destino)
                self.assertRedirects(self.client.post(self.url(nombre, objeto), {'siguiente': destino}), destino)

    def test_modal_conserva_busqueda_estado_y_pagina_del_listado(self):
        destino = reverse('seguridad:lista_empleados') + '?q=Ana&estado=activo&pagina=2'
        respuesta = self.confirmar('desactivar_empleado', self.empleado, siguiente=destino)
        self.assertEqual(respuesta.context['siguiente'], destino)
        self.assertRedirects(self.client.post(self.url('desactivar_empleado', self.empleado), {'siguiente': destino}), destino)

    def test_no_acepta_destinos_externos_ni_detalles_de_otras_personas(self):
        for nombre, objeto, destino in (
            ('desactivar_usuario', self.usuario, 'https://ajeno.example/seguridad/usuarios/'),
            ('desactivar_usuario', self.usuario, self.url('detalle_usuario', self.administrador)),
            ('desactivar_empleado', self.empleado, '/seguridad/empleados/999999/'),
        ):
            respuesta = self.confirmar(nombre, objeto, siguiente=destino)
            self.assertNotEqual(respuesta.context['siguiente'], destino)

    def test_listados_y_detalles_tienen_modal_y_disparadores(self):
        for nombre, objeto in (('detalle_usuario', self.usuario), ('detalle_empleado', self.empleado)):
            respuesta = self.client.get(self.url(nombre, objeto))
            self.assertContains(respuesta, 'id="confirmacion-seguridad"')
            self.assertContains(respuesta, 'data-confirmar')
        for nombre in ('lista_usuarios', 'lista_empleados', 'lista_roles'):
            respuesta = self.client.get(reverse('seguridad:' + nombre))
            self.assertContains(respuesta, 'id="confirmacion-seguridad"')
            self.assertContains(respuesta, 'data-confirmar')
            if nombre == 'lista_roles':
                self.assertNotContains(respuesta, 'data-accion="eliminar"')

    def test_ajax_no_elude_permisos_y_proteccion_de_cuenta_propia(self):
        self.client.force_login(self.sin_permisos)
        for nombre, objeto in (('desactivar_usuario', self.usuario), ('activar_usuario', self.usuario),
                               ('desactivar_empleado', self.empleado), ('activar_empleado', self.empleado),
                               ('eliminar_rol', self.rol)):
            self.assertEqual(self.confirmar(nombre, objeto).status_code, 403)
        self.client.force_login(self.administrador)
        self.confirmar('desactivar_usuario', self.administrador)
        self.administrador.refresh_from_db()
        self.assertTrue(self.administrador.is_active)

    def test_nombres_del_modal_se_escapan(self):
        self.rol.name = '<script>alert(1)</script>'
        self.rol.save()
        respuesta = self.confirmar('eliminar_rol', self.rol)
        self.assertContains(respuesta, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(respuesta, '<script>alert(1)</script>')
