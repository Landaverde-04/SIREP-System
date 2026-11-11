from io import StringIO

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Usuario
from .roles_base import ROLES_BASE


class RolesBaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('crear_roles_base', stdout=StringIO())
        cls.administrador = Usuario.objects.create_user('administrador-operativo')
        cls.administrador.groups.add(Group.objects.get(name='Administrador'))
        cls.superusuario = Usuario.objects.create_superuser('superusuario')

    def test_comando_crea_los_roles_y_conserva_ajustes_hasta_pedir_actualizacion(self):
        self.assertEqual(set(Group.objects.values_list('name', flat=True)), set(ROLES_BASE))
        permiso = Permission.objects.get(content_type__app_label='pedidos', codename='cancelar_pedido')
        self.assertFalse(Group.objects.filter(permissions=permiso).exists())

        mesero = Group.objects.get(name='Mesero')
        mesero.permissions.add(permiso)
        call_command('crear_roles_base', stdout=StringIO())
        self.assertIn(permiso, mesero.permissions.all())
        call_command('crear_roles_base', '--actualizar', stdout=StringIO())
        self.assertNotIn(permiso, mesero.permissions.all())

    def test_administrador_puede_crear_roles_con_permisos_de_rol(self):
        self.client.force_login(self.administrador)
        url = reverse('seguridad:crear_rol')
        permiso = Permission.objects.get(content_type__app_label='auth', codename='view_group')
        respuesta = self.client.get(url)
        seguridad = next(modulo for modulo in respuesta.context['permisos_agrupados']
                         if modulo['nombre'] == 'Seguridad')
        rol = next(modelo for modelo in seguridad['modelos'] if modelo['nombre'] == 'rol')
        self.assertIn(permiso.pk, [item['pk'] for item in rol['permisos']])
        self.assertRedirects(self.client.post(url, {'name': 'Consulta de roles', 'permissions': [permiso.pk]}),
                             reverse('seguridad:lista_roles'))
        self.assertEqual(list(Group.objects.get(name='Consulta de roles').permissions.all()), [permiso])

    def test_administrador_operativo_no_puede_modificar_superusuario(self):
        self.client.force_login(self.administrador)
        for vista in ('editar_usuario', 'desactivar_usuario', 'activar_usuario', 'resetear_password'):
            with self.subTest(vista=vista):
                url = reverse('seguridad:' + vista, args=[self.superusuario.pk])
                self.assertEqual(self.client.post(url).status_code, 403)
        self.superusuario.refresh_from_db()
        self.assertTrue(self.superusuario.is_active)
        self.assertFalse(self.superusuario.debe_cambiar_password)
