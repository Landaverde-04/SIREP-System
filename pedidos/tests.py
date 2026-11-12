from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from administracion.models import CategoriaProducto, Cliente, Mesa, Producto
from reservaciones.models import Atencion
from reservaciones.servicios import ServicioIngreso
from seguridad.models import Usuario

from .forms import DetallePedidoFormSet, PedidoForm
from .models import DetallePedido, Pedido
from .servicios import PedidoNoEditableError, ServicioPedidos

E = Pedido.Estado


def dar_permisos(usuario, *codigos):
    for codigo in codigos:
        usuario.user_permissions.add(Permission.objects.get(content_type__app_label='pedidos', codename=codigo))


class DatosBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mesa1 = Mesa.objects.create(numero=1, capacidad=4)
        cls.mesa2 = Mesa.objects.create(numero=2, capacidad=4)
        cls.mesa_libre = Mesa.objects.create(numero=3, capacidad=4)
        cls.cliente = Cliente.objects.create(nombre='Ana López', telefono='7777-8888')
        cls.categoria = CategoriaProducto.objects.create(nombre='Platos')
        cls.pollo = Producto.objects.create(nombre='Pollo', precio=Decimal('8.50'), categoria=cls.categoria)
        cls.sopa = Producto.objects.create(nombre='Sopa', precio=Decimal('3.00'), categoria=cls.categoria)
        cls.mesero = Usuario.objects.create_user('mesero', password='x')
        cls.atencion1 = ServicioIngreso(cls.mesero).registrar_sin_reservacion(cls.mesa1, 2, cls.cliente)
        cls.atencion2 = ServicioIngreso(cls.mesero).registrar_sin_reservacion(cls.mesa2, 2)

    def crear_pedido(self, mesa=None, lineas=((None, 1),), **extra):
        mesa = mesa or self.mesa1
        pedido = Pedido.objects.create(
            atencion=Atencion.abierta_de(mesa), mesa=mesa, mesero=self.mesero, **extra)
        for producto, cantidad in lineas:
            DetallePedido.objects.create(pedido=pedido, producto=producto or self.pollo, cantidad=cantidad)
        return pedido


class ModeloTests(DatosBase):
    def test_precio_se_copia_del_menu_y_no_cambia_despues(self):
        pedido = self.crear_pedido(lineas=[(self.pollo, 2)])
        self.pollo.precio = Decimal('99.00')
        self.pollo.save()
        detalle = pedido.detalles.get()
        self.assertEqual(detalle.precio_unitario, Decimal('8.50'))
        self.assertEqual(detalle.subtotal, Decimal('17.00'))

    def test_total_suma_todas_las_lineas(self):
        pedido = self.crear_pedido(lineas=[(self.pollo, 2), (self.sopa, 1)])
        self.assertEqual(pedido.total, Decimal('20.00'))

    def test_monto_anotado_coincide_con_total_y_pedido_sin_lineas_es_cero(self):
        con_lineas = self.crear_pedido(lineas=[(self.pollo, 2), (self.sopa, 3)])
        sin_lineas = self.crear_pedido(mesa=self.mesa2, lineas=[])
        montos = {p.pk: p.monto for p in Pedido.objects.con_monto()}
        self.assertEqual(montos[con_lineas.pk], con_lineas.total)
        self.assertEqual(montos[sin_lineas.pk], Decimal('0.00'))

    def test_clean_asigna_la_atencion_abierta_de_la_mesa(self):
        pedido = Pedido(mesa=self.mesa1, mesero=self.mesero)
        pedido.clean()
        self.assertEqual(pedido.atencion, self.atencion1)

    def test_clean_rechaza_mesa_sin_atencion_abierta(self):
        pedido = Pedido(mesa=self.mesa_libre, mesero=self.mesero)
        with self.assertRaises(ValidationError) as ctx:
            pedido.clean()
        self.assertIn('mesa', ctx.exception.message_dict)

    def test_cantidad_minima_en_base_de_datos(self):
        pedido = self.crear_pedido(lineas=[])
        with self.assertRaises(IntegrityError), transaction.atomic():
            DetallePedido.objects.create(pedido=pedido, producto=self.pollo, cantidad=0)

    def test_flujo_normal_de_estados(self):
        pedido = self.crear_pedido()
        for estado in (E.EN_PREPARACION, E.LISTO, E.ENTREGADO):
            pedido.cambiar_estado(estado)
            self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, estado)
        self.assertEqual(pedido.acciones_disponibles, [])
        self.assertIsNone(pedido.accion_siguiente)

    def test_transiciones_invalidas(self):
        pedido = self.crear_pedido()
        for destino in (E.LISTO, E.ENTREGADO, E.PENDIENTE, 'INEXISTENTE'):
            with self.assertRaises(ValidationError):
                pedido.cambiar_estado(destino)
        self.assertEqual(pedido.estado, E.PENDIENTE)

    def test_cancelacion_solo_antes_de_estar_listo(self):
        for estado_previo, puede in ((E.PENDIENTE, True), (E.EN_PREPARACION, True), (E.LISTO, False)):
            pedido = self.crear_pedido(estado=estado_previo)
            if puede:
                pedido.cambiar_estado(E.CANCELADO)
                self.assertEqual(pedido.estado, E.CANCELADO)
            else:
                with self.assertRaises(ValidationError):
                    pedido.cambiar_estado(E.CANCELADO)

    def test_estados_finales_no_avanzan(self):
        for final in (E.ENTREGADO, E.CANCELADO):
            pedido = self.crear_pedido(estado=final)
            with self.assertRaises(ValidationError):
                pedido.cambiar_estado(E.EN_PREPARACION)

    def test_no_se_cancela_si_la_atencion_esta_cerrada(self):
        pedido = self.crear_pedido()
        self.atencion1.cerrar()
        pedido = Pedido.objects.get(pk=pedido.pk)
        self.assertFalse(pedido.editable)
        self.assertNotIn(E.CANCELADO, [a['estado'] for a in pedido.acciones_disponibles])
        with self.assertRaises(ValidationError):
            pedido.cambiar_estado(E.CANCELADO)

    def test_editable_solo_si_pendiente(self):
        self.assertTrue(self.crear_pedido().editable)
        self.assertFalse(self.crear_pedido(estado=E.EN_PREPARACION).editable)

    def test_acciones_para_los_botones(self):
        acciones = self.crear_pedido().acciones_disponibles
        self.assertEqual([a['estado'] for a in acciones], ['EN_PREPARACION', 'CANCELADO'])
        self.assertTrue(acciones[1]['confirmar'])
        self.assertEqual(self.crear_pedido().accion_siguiente['estado'], 'EN_PREPARACION')

    def test_facturables_excluye_cancelados_y_filtra_por_atencion(self):
        activo = self.crear_pedido()
        self.crear_pedido(estado=E.CANCELADO)
        self.crear_pedido(mesa=self.mesa2)
        self.assertEqual(list(Pedido.objects.de_atencion(self.atencion1).facturables()), [activo])


def datos_post(mesa, lineas, notas='', extra=0):
    """POST de formulario + formset. ``lineas`` = [(producto_id, cantidad, nota)]."""
    datos = {'mesa': mesa.pk, 'notas': notas, 'detalles-TOTAL_FORMS': len(lineas) + extra,
             'detalles-INITIAL_FORMS': 0, 'detalles-MIN_NUM_FORMS': 0, 'detalles-MAX_NUM_FORMS': 1000}
    for i, (producto, cantidad, nota) in enumerate(lineas):
        datos.update({f'detalles-{i}-producto': producto, f'detalles-{i}-cantidad': cantidad,
                      f'detalles-{i}-nota': nota})
    return datos


class FormularioTests(DatosBase):
    def test_solo_ofrece_mesas_con_atencion_abierta(self):
        mesas = PedidoForm().fields['mesa'].queryset
        self.assertCountEqual(mesas, [self.mesa1, self.mesa2])

    def test_mesa_con_atencion_cerrada_deja_de_ofrecerse(self):
        self.atencion2.cerrar()
        self.assertCountEqual(PedidoForm().fields['mesa'].queryset, [self.mesa1])

    def test_rechaza_mesa_sin_atencion(self):
        form = PedidoForm({'mesa': self.mesa_libre.pk, 'notas': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('mesa', form.errors)

    def test_solo_productos_habilitados_y_disponibles(self):
        agotado = Producto.objects.create(nombre='Agotado', precio=1, categoria=self.categoria, disponible=False)
        retirado = Producto.objects.create(nombre='Retirado', precio=1, categoria=self.categoria, activo=False)
        formset = DetallePedidoFormSet(instance=Pedido())
        ofrecidos = formset.forms[0].fields['producto'].queryset
        self.assertCountEqual(ofrecidos, [self.pollo, self.sopa])
        self.assertNotIn(agotado, ofrecidos)
        self.assertNotIn(retirado, ofrecidos)

    def test_al_editar_se_conserva_un_producto_ya_pedido_aunque_se_agote(self):
        pedido = self.crear_pedido(lineas=[(self.sopa, 1)])
        self.sopa.alternar_disponibilidad()
        formset = DetallePedidoFormSet(instance=pedido)
        self.assertIn(self.sopa, formset.forms[0].fields['producto'].queryset)

    def test_formset_rechaza_producto_repetido_y_pedido_vacio(self):
        mesa = self.mesa1
        repetido = DetallePedidoFormSet(
            datos_post(mesa, [(self.pollo.pk, 1, ''), (self.pollo.pk, 2, '')]), instance=Pedido())
        self.assertFalse(repetido.is_valid())
        self.assertIn('repetido', ' '.join(repetido.non_form_errors()))
        vacio = DetallePedidoFormSet(datos_post(mesa, [], extra=1), instance=Pedido())
        self.assertFalse(vacio.is_valid())
        self.assertIn('al menos un producto', ' '.join(vacio.non_form_errors()))

    def test_cantidad_debe_ser_al_menos_uno(self):
        formset = DetallePedidoFormSet(datos_post(self.mesa1, [(self.pollo.pk, 0, '')]), instance=Pedido())
        self.assertFalse(formset.is_valid())


class ServicioTests(DatosBase):
    def guardar(self, pedido, datos):
        form = PedidoForm(datos, instance=pedido)
        formset = DetallePedidoFormSet(datos, instance=pedido)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)
        return ServicioPedidos().guardar(form, formset, self.mesero)

    def test_registra_pedido_con_lineas_mesero_y_atencion(self):
        pedido = self.guardar(Pedido(), datos_post(self.mesa1, [(self.pollo.pk, 2, 'sin sal'), (self.sopa.pk, 1, '')]))
        self.assertEqual((pedido.mesero, pedido.atencion, pedido.estado), (self.mesero, self.atencion1, E.PENDIENTE))
        self.assertEqual(pedido.total, Decimal('20.00'))
        self.assertEqual(pedido.detalles.get(producto=self.pollo).nota, 'sin sal')

    def test_no_registra_si_la_atencion_se_cerro_entre_el_formulario_y_el_guardado(self):
        pedido = Pedido()
        datos = datos_post(self.mesa1, [(self.pollo.pk, 1, '')])
        form, formset = PedidoForm(datos, instance=pedido), DetallePedidoFormSet(datos, instance=pedido)
        self.assertTrue(form.is_valid() and formset.is_valid())
        self.atencion1.cerrar()
        with self.assertRaises(ValidationError):
            ServicioPedidos().guardar(form, formset, self.mesero)
        self.assertFalse(Pedido.objects.exists())

    def test_edicion_no_cambia_mesero_y_respeta_precio_original(self):
        pedido = self.crear_pedido(lineas=[(self.pollo, 1)])
        otro = Usuario.objects.create_user('otro', password='x')
        self.pollo.precio = Decimal('50.00')
        self.pollo.save()
        detalle = pedido.detalles.get()
        datos = {'mesa': self.mesa1.pk, 'notas': 'cambio', 'detalles-TOTAL_FORMS': 1, 'detalles-INITIAL_FORMS': 1,
                 'detalles-MIN_NUM_FORMS': 0, 'detalles-MAX_NUM_FORMS': 1000, 'detalles-0-id': detalle.pk,
                 'detalles-0-pedido': pedido.pk, 'detalles-0-producto': self.pollo.pk, 'detalles-0-cantidad': 3,
                 'detalles-0-nota': ''}
        form, formset = PedidoForm(datos, instance=pedido), DetallePedidoFormSet(datos, instance=pedido)
        self.assertTrue(form.is_valid() and formset.is_valid(), (form.errors, formset.errors))
        ServicioPedidos().guardar(form, formset, otro)
        pedido.refresh_from_db()
        detalle.refresh_from_db()
        self.assertEqual((pedido.mesero, pedido.notas), (self.mesero, 'cambio'))
        self.assertEqual((detalle.cantidad, detalle.precio_unitario), (3, Decimal('8.50')))

    def test_no_edita_un_pedido_que_la_cocina_ya_tomo(self):
        pedido = self.crear_pedido(lineas=[(self.pollo, 1)])
        detalle = pedido.detalles.get()
        datos = {'mesa': self.mesa1.pk, 'notas': '', 'detalles-TOTAL_FORMS': 1, 'detalles-INITIAL_FORMS': 1,
                 'detalles-MIN_NUM_FORMS': 0, 'detalles-MAX_NUM_FORMS': 1000, 'detalles-0-id': detalle.pk,
                 'detalles-0-pedido': pedido.pk, 'detalles-0-producto': self.pollo.pk, 'detalles-0-cantidad': 9,
                 'detalles-0-nota': ''}
        form, formset = PedidoForm(datos, instance=pedido), DetallePedidoFormSet(datos, instance=pedido)
        self.assertTrue(form.is_valid() and formset.is_valid())
        Pedido.objects.filter(pk=pedido.pk).update(estado=E.EN_PREPARACION)  # la cocina lo tomó mientras tanto
        with self.assertRaises(PedidoNoEditableError):
            ServicioPedidos().guardar(form, formset, self.mesero)
        self.assertEqual(pedido.detalles.get().cantidad, 1)

    def test_cambiar_estado_aplica_transicion(self):
        pedido = self.crear_pedido()
        self.assertEqual(ServicioPedidos().cambiar_estado(pedido.pk, E.EN_PREPARACION).estado, E.EN_PREPARACION)
        with self.assertRaises(ValidationError):
            ServicioPedidos().cambiar_estado(pedido.pk, E.EN_PREPARACION)  # doble clic


class VistaBase(DatosBase):
    def entrar(self, *permisos):
        usuario = Usuario.objects.create_user(f'u{Usuario.objects.count()}', password='x')
        dar_permisos(usuario, *permisos)
        self.client.force_login(usuario)
        return usuario


class PermisosTests(VistaBase):
    def test_exige_inicio_de_sesion(self):
        for nombre, args in (('lista_pedidos', []), ('cocina', []), ('crear_pedido', []), ('detalle_pedido', [1])):
            respuesta = self.client.get(reverse(f'pedidos:{nombre}', args=args))
            self.assertEqual(respuesta.status_code, 302, nombre)
            self.assertIn('/seguridad/login/', respuesta['Location'])

    def test_sin_permiso_es_403(self):
        pedido = self.crear_pedido()
        self.entrar()
        for nombre, args in (('lista_pedidos', []), ('cocina', []), ('crear_pedido', []),
                             ('detalle_pedido', [pedido.pk]), ('editar_pedido', [pedido.pk])):
            self.assertEqual(self.client.get(reverse(f'pedidos:{nombre}', args=args)).status_code, 403, nombre)
        respuesta = self.client.post(reverse('pedidos:cambiar_estado', args=[pedido.pk, 'EN_PREPARACION']))
        self.assertEqual(respuesta.status_code, 403)

    def test_solo_consulta_no_puede_crear_ni_cambiar_estado(self):
        pedido = self.crear_pedido()
        self.entrar('view_pedido')
        self.assertEqual(self.client.get(reverse('pedidos:lista_pedidos')).status_code, 200)
        self.assertEqual(self.client.get(reverse('pedidos:crear_pedido')).status_code, 403)
        self.client.post(reverse('pedidos:cambiar_estado', args=[pedido.pk, 'EN_PREPARACION']))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, E.PENDIENTE)

    def test_cambiar_estado_no_acepta_get(self):
        pedido = self.crear_pedido()
        self.entrar('view_pedido', 'preparar_pedido')
        respuesta = self.client.get(reverse('pedidos:cambiar_estado', args=[pedido.pk, 'EN_PREPARACION']))
        self.assertEqual(respuesta.status_code, 405)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, E.PENDIENTE)


    def test_roles_base_separan_preparacion_entrega_y_cancelacion(self):
        call_command('crear_roles_base', verbosity=0)
        pedido = self.crear_pedido()
        mesero = self.mesero
        mesero.groups.add(Group.objects.get(name='Mesero'))
        cocina = Usuario.objects.create_user('cocina')
        cocina.groups.add(Group.objects.get(name='Encargado de cocina'))
        detalle = reverse('pedidos:detalle_pedido', args=[pedido.pk])
        tablero = reverse('pedidos:cocina')
        preparar, listo, entregar, cancelar = [
            reverse('pedidos:cambiar_estado', args=[pedido.pk, estado])
            for estado in (E.EN_PREPARACION, E.LISTO, E.ENTREGADO, E.CANCELADO)
        ]

        self.client.force_login(mesero)
        self.assertNotContains(self.client.get(detalle), preparar)
        self.assertEqual(self.client.post(preparar).status_code, 403)
        self.assertEqual(self.client.post(cancelar).status_code, 403)

        self.client.force_login(cocina)
        self.assertContains(self.client.get(tablero), preparar)
        self.assertRedirects(self.client.post(preparar), detalle)
        self.assertRedirects(self.client.post(listo), detalle)
        self.assertNotContains(self.client.get(tablero), entregar)
        self.assertEqual(self.client.post(entregar).status_code, 403)

        self.client.force_login(mesero)
        self.assertContains(self.client.get(detalle), entregar)
        self.assertRedirects(self.client.post(entregar), detalle)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, E.ENTREGADO)


class VistasTests(VistaBase):
    def setUp(self):
        self.usuario = self.entrar('view_pedido', 'add_pedido', 'change_pedido', 'preparar_pedido', 'entregar_pedido', 'cancelar_pedido')

    def test_crear_pedido_completo(self):
        url = reverse('pedidos:crear_pedido')
        self.assertContains(self.client.get(url), 'Seleccione un producto')
        respuesta = self.client.post(url, datos_post(self.mesa1, [(self.pollo.pk, 2, ''), (self.sopa.pk, 1, 'caliente')],
                                                     notas='alergia al maní', extra=1))
        pedido = Pedido.objects.get()
        self.assertRedirects(respuesta, reverse('pedidos:detalle_pedido', args=[pedido.pk]))
        self.assertEqual((pedido.mesero, pedido.atencion, pedido.notas), (self.usuario, self.atencion1, 'alergia al maní'))
        self.assertEqual(pedido.total, Decimal('20.00'))

    def test_crear_sin_productos_muestra_error_y_no_guarda(self):
        respuesta = self.client.post(reverse('pedidos:crear_pedido'), datos_post(self.mesa1, [], extra=1))
        self.assertContains(respuesta, 'Agregue al menos un producto')
        self.assertFalse(Pedido.objects.exists())

    def test_crear_en_mesa_libre_muestra_error(self):
        respuesta = self.client.post(reverse('pedidos:crear_pedido'),
                                     datos_post(self.mesa_libre, [(self.pollo.pk, 1, '')]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Pedido.objects.exists())

    def test_formulario_preselecciona_mesa_y_avisa_si_no_hay_mesas_ocupadas(self):
        respuesta = self.client.get(reverse('pedidos:crear_pedido') + f'?mesa={self.mesa2.pk}')
        self.assertEqual(respuesta.context['form']['mesa'].value(), str(self.mesa2.pk))
        self.assertFalse(respuesta.context['sin_mesas'])
        self.atencion1.cerrar()
        self.atencion2.cerrar()
        respuesta = self.client.get(reverse('pedidos:crear_pedido'))
        self.assertContains(respuesta, 'No hay mesas con una atención abierta')

    def test_lista_filtra_por_estado_y_calcula_montos(self):
        self.crear_pedido(lineas=[(self.pollo, 2)])
        self.crear_pedido(mesa=self.mesa2, estado=E.LISTO, lineas=[(self.sopa, 1)])
        todos = self.client.get(reverse('pedidos:lista_pedidos'))
        self.assertEqual(len(todos.context['pagina'].object_list), 2)
        self.assertContains(todos, '$17.00')
        listos = self.client.get(reverse('pedidos:lista_pedidos') + '?estado=LISTO')
        self.assertEqual([p.estado for p in listos.context['pagina']], [E.LISTO])
        invalido = self.client.get(reverse('pedidos:lista_pedidos') + '?estado=XYZ')
        self.assertEqual(len(invalido.context['pagina'].object_list), 2)

    def test_lista_pagina(self):
        for _ in range(16):
            self.crear_pedido()
        segunda = self.client.get(reverse('pedidos:lista_pedidos') + '?page=2')
        self.assertEqual(len(segunda.context['pagina'].object_list), 1)

    def test_detalle_muestra_lineas_y_total(self):
        pedido = self.crear_pedido(lineas=[(self.pollo, 2), (self.sopa, 1)], notas='sin cebolla')
        respuesta = self.client.get(reverse('pedidos:detalle_pedido', args=[pedido.pk]))
        for texto in ('Pollo', 'Sopa', '$20.00', 'sin cebolla', 'Iniciar preparación', 'Cancelar pedido'):
            self.assertContains(respuesta, texto)
        self.assertEqual(self.client.get(reverse('pedidos:detalle_pedido', args=[9999])).status_code, 404)

    def test_editar_pendiente_y_bloquear_en_preparacion(self):
        pedido = self.crear_pedido(lineas=[(self.pollo, 1)])
        url = reverse('pedidos:editar_pedido', args=[pedido.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        pedido.cambiar_estado(E.EN_PREPARACION)
        respuesta = self.client.get(url, follow=True)
        self.assertRedirects(respuesta, reverse('pedidos:detalle_pedido', args=[pedido.pk]))
        self.assertContains(respuesta, 'no puede modificarse')

    def test_avance_completo_desde_las_vistas(self):
        pedido = self.crear_pedido()
        for destino in ('EN_PREPARACION', 'LISTO', 'ENTREGADO'):
            respuesta = self.client.post(reverse('pedidos:cambiar_estado', args=[pedido.pk, destino]))
            self.assertRedirects(respuesta, reverse('pedidos:detalle_pedido', args=[pedido.pk]))
            pedido.refresh_from_db()
            self.assertEqual(pedido.estado, destino)

    def test_transicion_invalida_muestra_mensaje_y_no_cambia(self):
        pedido = self.crear_pedido()
        respuesta = self.client.post(reverse('pedidos:cambiar_estado', args=[pedido.pk, 'ENTREGADO']), follow=True)
        self.assertContains(respuesta, 'no puede pasar a entregado')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, E.PENDIENTE)
        self.client.post(reverse('pedidos:cambiar_estado', args=[pedido.pk, 'BASURA']))
        self.assertEqual(self.client.post(reverse('pedidos:cambiar_estado', args=[9999, 'LISTO'])).status_code, 404)

    def test_cancelar(self):
        pedido = self.crear_pedido()
        self.client.post(reverse('pedidos:cambiar_estado', args=[pedido.pk, 'CANCELADO']))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, E.CANCELADO)

    def test_cocina_agrupa_por_estado_y_oculta_terminados_y_atenciones_cerradas(self):
        pendiente = self.crear_pedido()
        preparando = self.crear_pedido(estado=E.EN_PREPARACION)
        listo = self.crear_pedido(mesa=self.mesa2, estado=E.LISTO)
        self.crear_pedido(mesa=self.mesa2, estado=E.ENTREGADO)
        self.crear_pedido(mesa=self.mesa2, estado=E.CANCELADO)
        respuesta = self.client.get(reverse('pedidos:cocina'))
        columnas = {c['titulo']: c['pedidos'] for c in respuesta.context['columnas']}
        self.assertEqual(columnas['Pendientes'], [pendiente])
        self.assertEqual(columnas['En preparación'], [preparando])
        self.assertEqual(columnas['Listos para entregar'], [listo])
        self.atencion1.cerrar()
        respuesta = self.client.get(reverse('pedidos:cocina'))
        self.assertEqual(respuesta.context['columnas'][0]['pedidos'], [])

    def test_cocina_avanza_y_vuelve_al_tablero(self):
        pedido = self.crear_pedido()
        respuesta = self.client.post(reverse('pedidos:cambiar_estado', args=[pedido.pk, 'EN_PREPARACION']),
                                     {'volver': 'cocina'})
        self.assertRedirects(respuesta, reverse('pedidos:cocina'))

    def _consultas(self, url):
        with CaptureQueriesContext(connection) as capturadas:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(capturadas)

    def test_cocina_no_hace_mas_consultas_al_crecer_los_pedidos(self):
        self.crear_pedido(lineas=[(self.pollo, 1), (self.sopa, 2)])
        pocas = self._consultas(reverse('pedidos:cocina'))
        for _ in range(8):
            self.crear_pedido(lineas=[(self.pollo, 1), (self.sopa, 2)])
        self.assertEqual(self._consultas(reverse('pedidos:cocina')), pocas)

    def test_lista_no_hace_mas_consultas_al_crecer_los_pedidos(self):
        self.crear_pedido(lineas=[(self.pollo, 1)])
        pocas = self._consultas(reverse('pedidos:lista_pedidos'))
        for _ in range(8):
            self.crear_pedido(lineas=[(self.pollo, 1)])
        self.assertEqual(self._consultas(reverse('pedidos:lista_pedidos')), pocas)

    def test_sidebar_muestra_pedidos_solo_con_permiso(self):
        self.assertContains(self.client.get(reverse('core:home')), reverse('pedidos:cocina'))
        self.entrar()
        self.assertNotContains(self.client.get(reverse('core:home')), reverse('pedidos:cocina'))


class DatosDemoTests(TestCase):
    def test_comando_es_idempotente_y_crea_roles(self):
        call_command('datos_demo_pedidos', verbosity=0)
        call_command('datos_demo_pedidos', verbosity=0)
        self.assertEqual(Producto.objects.count(), 9)
        mesero = Group.objects.get(name='Mesero')
        self.assertTrue(mesero.permissions.filter(codename='add_pedido').exists())
        cocina = Group.objects.get(name='Encargado de cocina')
        self.assertFalse(cocina.permissions.filter(codename='add_pedido').exists())
        self.assertTrue(cocina.permissions.filter(codename='preparar_pedido').exists())
