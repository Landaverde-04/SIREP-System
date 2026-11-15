from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .models import Empleado, Usuario


class EmpleadosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.encargado = Usuario.objects.create_user('encargado-empleados')
        cls.encargado.user_permissions.set(Permission.objects.filter(
            content_type__app_label='seguridad', codename__in=['view_empleado', 'add_empleado'],
        ))
        cls.solo_consulta = Usuario.objects.create_user('consulta-empleados')
        cls.solo_consulta.user_permissions.add(Permission.objects.get(codename='view_empleado'))
        cls.solo_registro = Usuario.objects.create_user('registro-empleados')
        cls.solo_registro.user_permissions.add(Permission.objects.get(codename='add_empleado'))
        cls.sin_permisos = Usuario.objects.create_user('sin-permisos-empleados')

    def setUp(self):
        self.client.force_login(self.encargado)
        self.lista = reverse('seguridad:lista_empleados')
        self.crear = reverse('seguridad:crear_empleado')
        self.datos = {
            'nombres': 'Ana María', 'apellidos': 'López Pérez', 'cargo': 'Jefa de cocina',
            'telefono': '', 'correo': '', 'fecha_ingreso': '2026-11-10', 'salario_mensual': '',
        }

    def empleado(self, **cambios):
        datos = {**self.datos, 'fecha_ingreso': date(2026, 11, 10), 'salario_mensual': None, **cambios}
        return Empleado.objects.create(**datos)

    def test_registra_sin_opcionales_y_sin_crear_usuario(self):
        usuarios_antes = Usuario.objects.count()
        respuesta = self.client.post(self.crear, self.datos)
        self.assertRedirects(respuesta, self.lista)
        empleado = Empleado.objects.get()
        self.assertTrue(empleado.activo)
        self.assertIsNone(empleado.salario_mensual)
        self.assertEqual(empleado.telefono, '')
        self.assertEqual(empleado.correo, '')
        self.assertEqual(Usuario.objects.count(), usuarios_antes)
        self.assertIsNone(empleado.usuario_id)
        self.assertEqual(empleado.codigo, f'EMP-{empleado.pk:06d}')
        self.assertIsNotNone(empleado.fecha_creacion)

    def test_guarda_salario_decimal_y_contacto(self):
        respuesta = self.client.post(self.crear, {
            **self.datos, 'salario_mensual': '450.25', 'telefono': '7777-8888', 'correo': 'ana@example.com',
        })
        self.assertRedirects(respuesta, self.lista)
        empleado = Empleado.objects.get()
        self.assertEqual(empleado.salario_mensual, Decimal('450.25'))
        self.assertEqual(empleado.correo, 'ana@example.com')

    def test_cero_es_distinto_de_salario_no_registrado(self):
        self.empleado(nombres='Sin salario')
        self.empleado(nombres='Con salario cero', salario_mensual=Decimal('0.00'))
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, '$0.00')
        self.assertContains(respuesta, 'Sin registrar')
        self.assertEqual(Empleado.objects.filter(salario_mensual__isnull=True).count(), 1)

    def test_rechaza_salario_negativo_no_finito_y_precision_invalida(self):
        for valor in ('-0.01', '450.123', '100000000.00', 'NaN', 'Infinity'):
            with self.subTest(salario=valor):
                respuesta = self.client.post(self.crear, {**self.datos, 'salario_mensual': valor})
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn('salario_mensual', respuesta.context['form'].errors)
                self.assertFalse(Empleado.objects.exists())

    def test_base_de_datos_rechaza_salario_negativo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.empleado(salario_mensual=Decimal('-1.00'))

    def test_campos_obligatorios_y_fecha_valida(self):
        for campo in ('nombres', 'apellidos', 'cargo', 'fecha_ingreso'):
            with self.subTest(campo=campo):
                respuesta = self.client.post(self.crear, {**self.datos, campo: ''})
                self.assertIn(campo, respuesta.context['form'].errors)
        respuesta = self.client.post(self.crear, {**self.datos, 'fecha_ingreso': '2026-02-30'})
        self.assertIn('fecha_ingreso', respuesta.context['form'].errors)
        self.assertFalse(Empleado.objects.exists())

    def test_valida_correo_opcional_y_conserva_valores_ante_error(self):
        respuesta = self.client.post(self.crear, {**self.datos, 'correo': 'correo-invalido'})
        self.assertIn('correo', respuesta.context['form'].errors)
        self.assertContains(respuesta, 'Ana María')
        self.assertContains(respuesta, 'value="2026-11-10"')

    def test_nombres_repetidos_permitidos_con_codigos_distintos(self):
        primero = self.empleado()
        segundo = self.empleado()
        self.assertNotEqual(primero.codigo, segundo.codigo)
        self.assertEqual(Empleado.objects.count(), 2)

    def test_cargo_es_texto_libre_y_normaliza_espacios(self):
        self.client.post(self.crear, {**self.datos, 'cargo': '  Encargada   de eventos  '})
        self.assertEqual(Empleado.objects.get().cargo, 'Encargada de eventos')

    def test_post_no_puede_forzar_estado_ni_identificador(self):
        self.client.post(self.crear, {**self.datos, 'activo': '', 'id': '999999', 'codigo': 'personalizado'})
        empleado = Empleado.objects.get()
        self.assertTrue(empleado.activo)
        self.assertNotEqual(empleado.pk, 999999)

    def test_get_no_crea_empleado_y_muestra_fecha_html(self):
        respuesta = self.client.get(self.crear)
        self.assertContains(respuesta, 'type="date"')
        self.assertContains(respuesta, 'Salario mensual (USD)')
        self.assertFalse(Empleado.objects.exists())

    def test_lista_pagina_diez_y_ordena_con_desempate(self):
        for _ in range(15):
            self.empleado()
        primera = self.client.get(self.lista).context['empleados']
        segunda = self.client.get(self.lista, {'pagina': 2}).context['empleados']
        self.assertEqual(len(primera), 10)
        self.assertEqual(len(segunda), 5)
        self.assertFalse({e.pk for e in primera} & {e.pk for e in segunda})
        self.assertEqual(primera.paginator.count, 15)
        self.assertEqual(self.client.get(self.lista, {'pagina': 'invalida'}).context['empleados'].number, 1)

    def test_busca_global_desde_dos_caracteres_y_codigo(self):
        for numero in range(12):
            self.empleado(nombres=f'Ana {numero}')
        objetivo = self.empleado(nombres='Zulema', apellidos='Soto', cargo='Barista',
                                 telefono='6666-7777', correo='especial@example.com')
        self.assertEqual(self.client.get(self.lista, {'q': 'Z'}).context['empleados'].paginator.count, 13)
        for consulta in ('Zu', 'Zulema Soto', 'barista', '6666', 'especial@', objetivo.codigo):
            with self.subTest(consulta=consulta):
                self.assertEqual(list(self.client.get(self.lista, {'q': consulta}).context['empleados']), [objetivo])

    def test_filtros_excluyentes_y_valores_invalidos(self):
        activo = self.empleado()
        inactivo = self.empleado(activo=False)
        for parametros, esperado in (({}, activo), ({'estado': 'invalido'}, activo),
                                      ({'estado': 'inactivo'}, inactivo),
                                      ({'estado': ['activo', 'inactivo']}, inactivo)):
            with self.subTest(parametros=parametros):
                self.assertEqual(list(self.client.get(self.lista, parametros).context['empleados']), [esperado])

    def test_paginacion_conserva_busqueda_y_estado(self):
        for _ in range(11):
            self.empleado(activo=False)
        respuesta = self.client.get(self.lista, {'q': 'Ana', 'estado': 'inactivo'})
        self.assertContains(respuesta, 'q=Ana&amp;estado=inactivo&amp;pagina=2')
        self.assertContains(respuesta, 'align-self-center')

    def test_fragmento_ajax_y_pagina_completa_no_se_cachean(self):
        self.empleado()
        completa = self.client.get(self.lista)
        fragmento = self.client.get(self.lista, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTemplateUsed(completa, 'seguridad/lista_empleados.html')
        self.assertTemplateUsed(fragmento, 'seguridad/resultados_empleados.html')
        self.assertNotContains(fragmento, '<!DOCTYPE html>')
        for respuesta in (completa, fragmento):
            self.assertIn('no-store', respuesta.headers['Cache-Control'])
            self.assertIn('X-Requested-With', respuesta.headers['Vary'])

    def test_listado_escapa_contenido(self):
        self.empleado(nombres='<script>alert(1)</script>')
        respuesta = self.client.get(self.lista)
        self.assertContains(respuesta, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(respuesta, '<script>alert(1)</script>')

    def test_login_obligatorio(self):
        self.client.logout()
        for url in (self.lista, self.crear):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_sin_permisos_no_puede_listar_ni_registrar(self):
        self.client.force_login(self.sin_permisos)
        self.assertEqual(self.client.get(self.lista).status_code, 403)
        self.assertEqual(self.client.get(self.crear).status_code, 403)
        self.assertEqual(self.client.post(self.crear, self.datos).status_code, 403)
        self.assertFalse(Empleado.objects.exists())

    def test_permisos_de_consulta_y_registro_son_independientes(self):
        self.client.force_login(self.solo_consulta)
        respuesta = self.client.get(self.lista)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Nuevo empleado')
        self.assertEqual(self.client.post(self.crear, self.datos).status_code, 403)
        self.client.force_login(self.solo_registro)
        self.assertEqual(self.client.get(self.lista).status_code, 403)
        self.assertRedirects(self.client.post(self.crear, self.datos), self.crear)
        respuesta = self.client.get(self.crear)
        self.assertContains(respuesta, reverse('core:modulo', kwargs={'modulo': 'seguridad'}))
        modulo = self.client.get(reverse('core:modulo', kwargs={'modulo': 'seguridad'}))
        self.assertContains(modulo, 'Empleados')
        self.assertContains(modulo, self.crear)
        self.assertNotContains(respuesta, 'Volver al listado')

    def test_registro_exige_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.encargado)
        self.assertEqual(cliente.post(self.crear, self.datos).status_code, 403)
        self.assertFalse(Empleado.objects.exists())


class EstadoEmpleadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.encargado = Usuario.objects.create_user('gestor-estado-empleados')
        cls.encargado.user_permissions.set(Permission.objects.filter(
            content_type__app_label='seguridad', codename__in=['view_empleado', 'change_empleado'],
        ))
        cls.consulta = Usuario.objects.create_user('consulta-estado-empleados')
        cls.consulta.user_permissions.add(Permission.objects.get(codename='view_empleado'))
        cls.empleado = Empleado.objects.create(
            nombres='Ana', apellidos='López', cargo='Encargada de cocina', telefono='7777-8888',
            correo='ana@example.com', fecha_ingreso=date(2026, 11, 10), salario_mensual=Decimal('450.25'),
        )

    def setUp(self):
        self.client.force_login(self.encargado)
        self.lista = reverse('seguridad:lista_empleados')
        self.desactivar = reverse('seguridad:desactivar_empleado', args=[self.empleado.pk])
        self.activar = reverse('seguridad:activar_empleado', args=[self.empleado.pk])

    def test_get_confirma_sin_cambiar_estado(self):
        for url, texto in ((self.desactivar, 'Sí, desactivar'), (self.activar, 'Sí, reactivar')):
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertContains(respuesta, texto)
                self.assertContains(respuesta, 'Cancelar')
                self.assertContains(respuesta, self.empleado.codigo)
                self.assertIn('no-store', respuesta.headers['Cache-Control'])
                self.empleado.refresh_from_db()
                self.assertTrue(self.empleado.activo)

    def test_desactiva_sin_perder_datos_ni_cambiar_usuarios(self):
        anterior = Empleado.objects.values().get(pk=self.empleado.pk)
        usuarios = list(Usuario.objects.order_by('pk').values())
        self.assertRedirects(self.client.post(self.desactivar), self.lista)
        actual = Empleado.objects.values().get(pk=self.empleado.pk)
        self.assertFalse(actual['activo'])
        self.assertGreater(actual['fecha_modificacion'], anterior['fecha_modificacion'])
        for campo in anterior.keys() - {'activo', 'fecha_modificacion'}:
            self.assertEqual(actual[campo], anterior[campo], campo)
        self.assertEqual(usuarios, list(Usuario.objects.order_by('pk').values()))
        self.assertNotIn(self.empleado, self.client.get(self.lista).context['empleados'])
        self.assertIn(self.empleado, self.client.get(self.lista, {'estado': 'inactivo'}).context['empleados'])

    def test_reactiva_empleado_y_conserva_salario(self):
        self.client.post(self.desactivar)
        self.assertRedirects(self.client.post(self.activar), self.lista)
        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.activo)
        self.assertEqual(self.empleado.salario_mensual, Decimal('450.25'))
        self.assertIn(self.empleado, self.client.get(self.lista).context['empleados'])

    def test_repetir_la_accion_no_reescribe_el_registro(self):
        for url in (self.desactivar, self.activar):
            self.client.post(url)
            anterior = Empleado.objects.values().get(pk=self.empleado.pk)
            self.client.post(url)
            self.assertEqual(anterior, Empleado.objects.values().get(pk=self.empleado.pk))

    def test_listado_ofrece_accion_segun_estado_y_permiso(self):
        self.assertContains(self.client.get(self.lista), self.desactivar)
        self.assertNotContains(self.client.get(self.lista), self.activar)
        self.client.post(self.desactivar)
        respuesta = self.client.get(self.lista, {'estado': 'inactivo'})
        self.assertContains(respuesta, self.activar)
        self.assertNotContains(respuesta, self.desactivar)
        self.client.force_login(self.consulta)
        self.assertNotContains(self.client.get(self.lista, {'estado': 'inactivo'}), self.activar)

    def test_requiere_login_y_permiso_tambien_en_post(self):
        for url in (self.desactivar, self.activar):
            with self.subTest(url=url):
                self.client.logout()
                self.assertEqual(self.client.get(url).status_code, 302)
                self.assertEqual(self.client.post(url).status_code, 302)
                self.client.force_login(self.consulta)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url).status_code, 403)
        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.activo)

    def test_exige_csrf_para_ambas_acciones(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.encargado)
        for url in (self.desactivar, self.activar):
            self.assertEqual(cliente.post(url).status_code, 403)

    def test_empleado_inexistente_devuelve_404(self):
        for nombre in ('desactivar_empleado', 'activar_empleado'):
            url = reverse('seguridad:' + nombre, args=[999999])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url).status_code, 404)

    def test_conserva_filtros_y_pagina_al_volver(self):
        destino = self.lista + '?q=Ana&estado=activo&pagina=2'
        respuesta = self.client.get(self.desactivar, {'siguiente': destino})
        self.assertEqual(respuesta.context['siguiente'], destino)
        self.assertRedirects(self.client.post(self.desactivar, {'siguiente': destino}), destino)

    def test_rechaza_destinos_ajenos_al_listado(self):
        for destino in ('https://ajeno.example/seguridad/empleados/', '//ajeno.example/seguridad/empleados/',
                        '/seguridad/usuarios/', '/seguridad/empleados/crear/'):
            with self.subTest(destino=destino):
                respuesta = self.client.get(self.desactivar, {'siguiente': destino})
                self.assertEqual(respuesta.context['siguiente'], self.lista)
                self.assertRedirects(self.client.post(self.desactivar, {'siguiente': destino}), self.lista)

    def test_permiso_cambio_sin_consulta_regresa_al_inicio(self):
        self.consulta.user_permissions.set([Permission.objects.get(codename='change_empleado')])
        self.client.force_login(self.consulta)
        self.assertRedirects(self.client.post(self.desactivar), reverse('core:home'))

    def test_no_admite_otros_metodos(self):
        for url in (self.desactivar, self.activar):
            self.assertEqual(self.client.put(url).status_code, 405)
            self.assertEqual(self.client.delete(url).status_code, 405)
        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.activo)
