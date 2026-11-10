from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from .models import Usuario


class EnlacesHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.enlaces = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == 'a' and 'data-listado' in atributos:
            self.enlaces.append(atributos['href'])


class ListaUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administrador = Usuario.objects.create_user('administrador', password='Clave-pruebas-2026')
        cls.administrador.user_permissions.set(Permission.objects.filter(
            content_type__app_label='seguridad', codename__in=['view_usuario', 'change_usuario']))
        cls.activados = [Usuario.objects.create_user(
            f'usuario{i:02}', first_name='Persona', last_name='Prueba', email=f'persona{i}@example.com',
        ) for i in range(23)]
        cls.objetivo = cls.activados[-1]
        cls.objetivo.first_name = 'Zulema'
        cls.objetivo.last_name = 'Soto'
        cls.objetivo.email = 'correo.especial@example.com'
        cls.objetivo.save()
        cls.desactivados = [Usuario.objects.create_user(f'baja{i:02}', is_active=False) for i in range(4)]
        cls.objetivo.groups.set([Group.objects.create(name='Cajero'), Group.objects.create(name='Mesero')])

    def setUp(self):
        self.client.force_login(self.administrador)
        self.url = reverse('seguridad:lista_usuarios')

    def listado(self, **parametros):
        return self.client.get(self.url, parametros)

    def test_pagina_inicial_muestra_diez_activados(self):
        respuesta = self.listado()
        pagina = respuesta.context['usuarios']
        self.assertEqual(len(pagina), 10)
        self.assertEqual(pagina.paginator.count, 24)
        self.assertEqual(pagina.paginator.num_pages, 3)
        self.assertTrue(all(u.is_active for u in pagina))
        self.assertTrue(respuesta.context['activados'])
        self.assertFalse(respuesta.context['desactivados'])

    def test_segunda_pagina_contiene_otros_usuarios(self):
        primera = {u.pk for u in self.listado().context['usuarios']}
        segunda = self.listado(pagina=2).context['usuarios']
        self.assertEqual(segunda.number, 2)
        self.assertEqual(len(segunda), 10)
        self.assertFalse(primera & {u.pk for u in segunda})

    def test_pagina_invalida_y_fuera_de_rango(self):
        self.assertEqual(self.listado(pagina='texto').context['usuarios'].number, 1)
        self.assertEqual(self.listado(pagina=999).context['usuarios'].number, 3)

    def test_busqueda_no_filtra_con_una_letra(self):
        respuesta = self.listado(q='Z')
        self.assertEqual(respuesta.context['usuarios'].paginator.count, 24)
        self.assertEqual(respuesta.context['consulta_aplicada'], '')

    def test_busqueda_desde_dos_letras_encuentra_otra_pagina(self):
        self.assertNotIn(self.objetivo.pk, [u.pk for u in self.listado().context['usuarios']])
        respuesta = self.listado(q='Zu')
        self.assertEqual(list(respuesta.context['usuarios']), [self.objetivo])

    def test_busca_por_usuario_apellido_correo_y_nombre_completo(self):
        for consulta in ('usuario22', 'soto', 'correo.especial', 'Zulema Soto', '  zU  '):
            with self.subTest(consulta=consulta):
                self.assertEqual(list(self.listado(q=consulta).context['usuarios']), [self.objetivo])

    def test_borrar_busqueda_recupera_el_listado(self):
        self.assertEqual(self.listado(q='Zu').context['usuarios'].paginator.count, 1)
        self.assertEqual(self.listado(q='').context['usuarios'].paginator.count, 24)

    def test_solo_desactivados(self):
        respuesta = self.listado(filtrar=1, estado='inactivo')
        self.assertEqual(list(respuesta.context['usuarios']), self.desactivados)
        self.assertFalse(respuesta.context['activados'])
        self.assertTrue(respuesta.context['desactivados'])

    def test_estados_repetidos_no_se_combinan(self):
        respuesta = self.listado(estado=['activo', 'inactivo'])
        self.assertEqual(respuesta.context['usuarios'].paginator.count, 4)
        self.assertTrue(all(not u.is_active for u in respuesta.context['usuarios']))
        self.assertFalse(respuesta.context['activados'])
        self.assertTrue(respuesta.context['desactivados'])

    def test_sin_estado_o_estado_invalido_muestra_activados(self):
        for parametros in ({}, {'filtrar': 1}, {'estado': ''}, {'estado': 'todos'}):
            with self.subTest(parametros=parametros):
                respuesta = self.listado(**parametros)
                self.assertEqual(respuesta.context['usuarios'].paginator.count, 24)
                self.assertTrue(respuesta.context['activados'])
                self.assertFalse(respuesta.context['desactivados'])

    def test_busqueda_respeta_estado(self):
        self.assertEqual(self.listado(q='Zu', filtrar=1, estado='inactivo').context['usuarios'].paginator.count, 0)
        self.assertEqual(self.listado(q='baja', filtrar=1, estado='inactivo').context['usuarios'].paginator.count, 4)

    def test_controles_permanecen_visibles_sin_resultados(self):
        respuesta = self.listado(q='no-existe-usuario')
        self.assertContains(respuesta, 'id="buscador"')
        self.assertContains(respuesta, 'id="usuarios-desactivados"')
        self.assertContains(respuesta, 'No se encontraron usuarios')
        self.assertContains(respuesta, 'seguridad/js/lista_usuarios.js')

    def test_paginacion_conserva_busqueda_y_filtros(self):
        respuesta = self.listado(q='usuario', filtrar=1, estado='activo', pagina=2)
        parser = EnlacesHTML()
        parser.feed(respuesta.content.decode())
        paginas = [parse_qs(urlsplit(e).query) for e in parser.enlaces if 'pagina=' in e]
        self.assertTrue(paginas)
        for parametros in paginas:
            self.assertEqual(parametros.get('q'), ['usuario'])
            self.assertEqual(parametros.get('estado'), ['activo'])
            self.assertEqual(parametros.get('filtrar'), ['1'])

    def test_ordenacion_se_aplica_a_todo_el_listado(self):
        respuesta = self.listado(ordenar='usuario', direccion='desc')
        self.assertEqual(respuesta.context['usuarios'][0], self.objetivo)

    def test_ordenar_por_roles_no_duplica_usuarios(self):
        pagina = self.listado(ordenar='roles', estado='activo').context['usuarios']
        self.assertEqual(pagina.paginator.count, 24)
        self.assertEqual(len({u.pk for u in pagina}), len(pagina))

    def test_orden_no_permitido_utiliza_el_predeterminado(self):
        respuesta = self.listado(ordenar='password', direccion='invalida')
        self.assertEqual(respuesta.context['ordenar'], 'usuario')
        self.assertEqual(respuesta.context['direccion'], 'asc')

    def test_respuesta_asincrona_es_fragmento(self):
        respuesta = self.client.get(self.url, {'q': 'Zu'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertContains(respuesta, 'Zulema')
        self.assertNotContains(respuesta, '<html')
        self.assertNotContains(respuesta, 'id="filtros-usuarios"')

    def test_pagina_y_fragmento_no_comparten_cache(self):
        for encabezados in ({}, {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}):
            with self.subTest(encabezados=encabezados):
                respuesta = self.client.get(self.url, {'estado': 'activo'}, **encabezados)
                self.assertIn('X-Requested-With', respuesta.headers['Vary'])
                self.assertIn('no-store', respuesta.headers['Cache-Control'])
                if encabezados:
                    self.assertNotContains(respuesta, 'id="filtros-usuarios"')
                else:
                    self.assertContains(respuesta, 'id="filtros-usuarios"')

    def test_datos_de_busqueda_y_resultados_se_escapan(self):
        self.objetivo.first_name = '<img src=x onerror=alert(1)>'
        self.objetivo.save()
        respuesta = self.listado(q='usuario22')
        self.assertNotContains(respuesta, '<img src=x onerror=alert(1)>')
        self.assertContains(respuesta, '&lt;img')
        respuesta = self.listado(q='"><script>alert(1)</script>')
        self.assertNotContains(respuesta, '<script>alert(1)</script>')

    def test_requiere_login_y_permiso_tambien_en_ajax(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        lector = Usuario.objects.create_user('sin_permisos')
        self.client.force_login(lector)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 403)

    def test_listado_sin_permiso_de_cambio_no_muestra_acciones_de_estado(self):
        lector = Usuario.objects.create_user('solo_lectura')
        lector.user_permissions.add(Permission.objects.get(codename='view_usuario', content_type__app_label='seguridad'))
        self.client.force_login(lector)
        respuesta = self.listado(filtrar=1, estado='inactivo')
        self.assertNotContains(respuesta, reverse('seguridad:activar_usuario', args=[self.desactivados[0].pk]))

    def test_desactivados_ofrecen_activacion_y_no_eliminacion(self):
        respuesta = self.listado(filtrar=1, estado='inactivo')
        self.assertContains(respuesta, reverse('seguridad:activar_usuario', args=[self.desactivados[0].pk]))
        self.assertNotContains(respuesta, 'data-accion="eliminar"')


class EstadoUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administrador = Usuario.objects.create_user('administrador', password='Clave-pruebas-2026')
        cls.administrador.user_permissions.set(Permission.objects.filter(
            content_type__app_label='seguridad', codename__in=['view_usuario', 'change_usuario']))
        cls.usuario = Usuario.objects.create_user('mesero', password='Clave-pruebas-2026', first_name='Mario')
        cls.rol = Group.objects.create(name='Mesero')
        cls.usuario.groups.add(cls.rol)

    def setUp(self):
        self.client.force_login(self.administrador)
        self.lista = reverse('seguridad:lista_usuarios')
        self.desactivar = reverse('seguridad:desactivar_usuario', args=[self.usuario.pk])
        self.activar = reverse('seguridad:activar_usuario', args=[self.usuario.pk])

    def test_get_solicita_confirmacion_sin_desactivar(self):
        self.assertContains(self.client.get(self.desactivar), 'Sí, desactivar')
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.is_active)

    def test_desactivar_conserva_registro_datos_y_roles(self):
        password = self.usuario.password
        respuesta = self.client.post(self.desactivar)
        self.assertRedirects(respuesta, self.lista)
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.is_active)
        self.assertEqual(self.usuario.password, password)
        self.assertEqual(self.usuario.first_name, 'Mario')
        self.assertEqual(list(self.usuario.groups.all()), [self.rol])

    def test_ruta_antigua_tambien_conserva_el_usuario(self):
        self.client.post(reverse('seguridad:eliminar_usuario', args=[self.usuario.pk]))
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.is_active)

    def test_activacion_recupera_acceso_y_conserva_roles(self):
        self.client.post(self.desactivar)
        self.client.logout()
        self.assertFalse(self.client.login(username='mesero', password='Clave-pruebas-2026'))
        self.client.force_login(self.administrador)
        self.assertContains(self.client.get(self.activar), 'Sí, activar')
        self.client.post(self.activar)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.is_active)
        self.assertEqual(list(self.usuario.groups.all()), [self.rol])
        self.client.logout()
        self.assertTrue(self.client.login(username='mesero', password='Clave-pruebas-2026'))

    def test_no_desactiva_la_propia_cuenta(self):
        self.client.post(reverse('seguridad:desactivar_usuario', args=[self.administrador.pk]))
        self.administrador.refresh_from_db()
        self.assertTrue(self.administrador.is_active)

    def test_conserva_filtros_al_regresar(self):
        destino = self.lista + '?filtrar=1&estado=activo&q=me&pagina=2'
        self.assertRedirects(self.client.post(self.desactivar, {'siguiente': destino}), destino)

    def test_destinos_externos_o_ajenos_al_listado_no_se_utilizan(self):
        for destino in ('https://otro.example/seguridad/usuarios/', '//otro.example/seguridad/usuarios/', '/seguridad/roles/'):
            with self.subTest(destino=destino):
                self.assertRedirects(self.client.post(self.activar, {'siguiente': destino}), self.lista)

    def test_estado_exige_permiso_de_modificar(self):
        lector = Usuario.objects.create_user('lector')
        lector.user_permissions.add(Permission.objects.get(codename='view_usuario', content_type__app_label='seguridad'))
        self.client.force_login(lector)
        for url in (self.activar, self.desactivar, reverse('seguridad:eliminar_usuario', args=[self.usuario.pk])):
            self.assertEqual(self.client.post(url).status_code, 403)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.is_active)

    def test_estado_requiere_login(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.desactivar).status_code, 302)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.is_active)

    def test_detalle_de_desactivado_ofrece_activar(self):
        self.client.post(self.desactivar)
        respuesta = self.client.get(reverse('seguridad:detalle_usuario', args=[self.usuario.pk]))
        self.assertContains(respuesta, 'Activar usuario')
        self.assertNotContains(respuesta, 'Eliminar usuario')


    def test_ruta_antigua_y_actual_impiden_la_baja_propia(self):
        for nombre in ('desactivar_usuario', 'eliminar_usuario'):
            for metodo in ('get', 'post'):
                with self.subTest(ruta=nombre, metodo=metodo):
                    respuesta = getattr(self.client, metodo)(reverse('seguridad:' + nombre, args=[self.administrador.pk]))
                    self.assertRedirects(respuesta, self.lista)
                    self.administrador.refresh_from_db()
                    self.assertTrue(self.administrador.is_active)

    def test_no_ofrece_desactivar_la_cuenta_actual_en_listado_ni_detalle(self):
        destino = reverse('seguridad:desactivar_usuario', args=[self.administrador.pk])
        self.assertNotContains(self.client.get(self.lista), destino)
        self.assertNotContains(self.client.get(reverse('seguridad:detalle_usuario', args=[self.administrador.pk])), destino)

    def test_edicion_propia_muestra_estado_bloqueado(self):
        respuesta = self.client.get(reverse('seguridad:editar_usuario', args=[self.administrador.pk]))
        self.assertTrue(respuesta.context['form'].fields['is_active'].disabled)
        self.assertContains(respuesta, 'Tu cuenta debe permanecer activada')

    def test_edicion_propia_no_desactiva_la_cuenta_con_post_manipulado(self):
        respuesta = self.client.post(reverse('seguridad:editar_usuario', args=[self.administrador.pk]), {
            'username': self.administrador.username, 'first_name': 'Nombre actualizado',
            # Se omite is_active, como en un intento de desmarcarlo.
        })
        self.assertRedirects(respuesta, self.lista)
        self.administrador.refresh_from_db()
        self.assertTrue(self.administrador.is_active)
        self.assertEqual(self.administrador.first_name, 'Nombre actualizado')

    def test_edicion_de_otro_usuario_permite_cambiar_su_estado(self):
        respuesta = self.client.post(reverse('seguridad:editar_usuario', args=[self.usuario.pk]), {
            'username': self.usuario.username, 'first_name': self.usuario.first_name,
            'groups': [self.rol.pk],
        })
        self.assertRedirects(respuesta, self.lista)
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.is_active)
