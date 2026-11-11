"""Pruebas con los modelos reales. Django utiliza una base temporal separada."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from administracion.models import CategoriaProducto, Cliente, Mesa, Producto
from pedidos.models import DetallePedido, Pedido
from reservaciones.models import Atencion, Reservacion
from reservaciones.servicios import ServicioDisponibilidad, ServicioIngreso
from seguridad.models import Usuario

from .excepciones import CobroDuplicadoError, ConsumoInvalidoError, ErrorCobro
from .forms import RegistrarCobroForm
from .integracion import AdaptadorConsumoPedidos
from .models import Cobro, DetalleCobro
from .pagos import FormaPago
from .servicios import ServicioCobro


class DatosCobro(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cajero = Usuario.objects.create_user('cajero')
        cls.cajero.user_permissions.set(Permission.objects.filter(
            content_type__app_label='cobro', codename__in=['view_cobro', 'add_cobro']))
        cls.lector = Usuario.objects.create_user('lector')
        cls.lector.user_permissions.add(Permission.objects.get(
            content_type__app_label='cobro', codename='view_cobro'))
        cls.sin_permisos = Usuario.objects.create_user('sin_permisos')
        cls.mesa = Mesa.objects.create(numero=1, capacidad=4)
        cls.mesa2 = Mesa.objects.create(numero=2, capacidad=4)
        cls.cliente = Cliente.objects.create(nombre='Ana López', telefono='7777-8888')
        cls.atencion = ServicioIngreso(cls.cajero).registrar_sin_reservacion(cls.mesa, 2, cls.cliente)
        cls.otra_atencion = ServicioIngreso(cls.cajero).registrar_sin_reservacion(cls.mesa2, 2)
        cls.categoria = CategoriaProducto.objects.create(nombre='Platos')
        cls.producto = Producto.objects.create(nombre='Plato del día', precio=Decimal('8.50'),
                                               categoria=cls.categoria)
        cls.sopa = Producto.objects.create(nombre='Sopa', precio=Decimal('3.00'), categoria=cls.categoria)

    def pedido(self, estado=Pedido.Estado.ENTREGADO, atencion=None, lineas=None):
        atencion = atencion or self.atencion
        pedido = Pedido.objects.create(atencion=atencion, mesa=atencion.mesa,
                                         mesero=self.cajero, estado=estado)
        for producto, cantidad in ([(self.producto, 1)] if lineas is None else lineas):
            DetallePedido.objects.create(pedido=pedido, producto=producto, cantidad=cantidad)
        return pedido

    def cobrar(self, monto='10.00', forma=FormaPago.EFECTIVO, atencion=None, cajero=None):
        return ServicioCobro().registrar(
            atencion_id=(atencion or self.atencion).pk, monto_recibido=Decimal(monto),
            forma_pago=forma, cajero=cajero or self.cajero,
        )


class AdaptadorTests(DatosCobro):
    def test_varios_pedidos_entregados(self):
        self.pedido(lineas=[(self.producto, 2), (self.sopa, 1)])
        self.pedido(lineas=[(self.sopa, 2)])
        consumo = AdaptadorConsumoPedidos().consultar(self.atencion)
        self.assertEqual(len(consumo.lineas), 3)
        self.assertEqual(consumo.total, Decimal('26.00'))
        self.assertTrue(consumo.puede_cobrarse)

    def test_excluye_cancelados_y_no_entregados(self):
        self.pedido()
        for estado in (Pedido.Estado.CANCELADO, *Pedido.ESTADOS_EN_CURSO):
            self.pedido(estado=estado)
        consumo = AdaptadorConsumoPedidos().consultar(self.atencion)
        self.assertEqual(consumo.total, Decimal('8.50'))
        self.assertEqual(len(consumo.lineas), 1)
        self.assertEqual(len(consumo.pendientes), 3)
        self.assertFalse(consumo.puede_cobrarse)

    def test_no_consulta_el_precio_actual_para_calcular(self):
        self.pedido()
        self.producto.precio = Decimal('99.00')
        self.producto.save()
        self.assertEqual(AdaptadorConsumoPedidos().consultar(self.atencion).total, Decimal('8.50'))

    def test_aisla_atenciones_en_la_misma_mesa(self):
        self.pedido(lineas=[(self.producto, 3)])
        self.atencion.cerrar()
        nueva = ServicioIngreso().registrar_sin_reservacion(self.mesa, 2)
        self.pedido(atencion=nueva, lineas=[(self.sopa, 1)])
        self.assertEqual(AdaptadorConsumoPedidos().consultar(nueva).total, Decimal('3.00'))
        self.assertEqual(AdaptadorConsumoPedidos().consultar(self.atencion).total, Decimal('25.50'))

    def test_no_oculta_consumo_por_el_campo_activo(self):
        pedido = self.pedido()
        Pedido.objects.filter(pk=pedido.pk).update(activo=False)
        pedido.detalles.update(activo=False)
        self.assertEqual(AdaptadorConsumoPedidos().consultar(self.atencion).total, Decimal('8.50'))

    def test_precio_historico_invalido_impide_total_parcial(self):
        self.pedido()
        invalido = self.pedido(lineas=[(self.sopa, 1)])
        invalido.detalles.update(precio_unitario=Decimal('0.00'))
        with self.assertRaises(ConsumoInvalidoError):
            AdaptadorConsumoPedidos().consultar(self.atencion)

    def test_precio_ausente_se_rechaza_sin_recurrir_al_catalogo(self):
        # El esquema no admite NULL. Se prueba la frontera con una instancia
        # real sin guardar, antes de que DetallePedido.save copie el precio.
        detalle = DetallePedido(producto=self.producto, cantidad=1, precio_unitario=None)
        with self.assertRaises(ConsumoInvalidoError):
            AdaptadorConsumoPedidos().crear_linea(detalle)

    def test_entregado_sin_lineas_es_un_error_de_integridad(self):
        self.pedido()
        self.pedido(lineas=[])
        with self.assertRaises(ConsumoInvalidoError):
            AdaptadorConsumoPedidos().consultar(self.atencion)

    def test_consumo_vacio_no_es_cobrable(self):
        consumo = AdaptadorConsumoPedidos().consultar(self.atencion)
        self.assertEqual(consumo.total, Decimal('0.00'))
        self.assertFalse(consumo.puede_cobrarse)


class ServicioCobroTests(DatosCobro):
    def test_cobro_exitoso_guarda_fecha_cajero_desglose_y_cierra(self):
        pedido = self.pedido()
        antes = timezone.now()
        cobro = self.cobrar()
        self.assertEqual(cobro.atencion, self.atencion)
        self.assertEqual(cobro.cajero, self.cajero)
        self.assertGreaterEqual(cobro.fecha_hora_pago, antes)
        self.assertTrue(timezone.is_aware(cobro.fecha_hora_pago))
        self.assertEqual(cobro.total, Decimal('8.50'))
        self.assertEqual(cobro.monto_recibido, Decimal('10.00'))
        self.assertEqual(cobro.cambio, Decimal('1.50'))
        detalle = cobro.detalles.get()
        self.assertEqual(detalle.detalle_pedido, pedido.detalles.get())
        self.assertEqual(detalle.nombre_producto, 'Plato del día')
        self.assertEqual(detalle.subtotal, Decimal('8.50'))
        self.atencion.refresh_from_db()
        self.assertEqual(self.atencion.estado, Atencion.Estado.CERRADA)
        self.assertIsNotNone(self.atencion.fecha_hora_cierre)
        self.assertFalse(self.mesa.esta_ocupada)
        self.assertEqual(self.mesa.estado, 'Disponible')

    def test_cobra_varios_pedidos_con_precios_historicos(self):
        self.pedido(lineas=[(self.producto, 2)])
        self.pedido(lineas=[(self.sopa, 2)])
        self.producto.precio = Decimal('40.00')
        self.producto.save()
        cobro = self.cobrar(monto='23.00')
        self.assertEqual(cobro.total, Decimal('23.00'))
        self.assertEqual(cobro.detalles.count(), 2)

    def test_bloquea_los_tres_estados_en_curso(self):
        self.pedido()
        for estado in Pedido.ESTADOS_EN_CURSO:
            with self.subTest(estado=estado):
                pendiente = self.pedido(estado=estado)
                with self.assertRaisesMessage(ErrorCobro, 'pedidos pendientes'):
                    self.cobrar()
                self.atencion.refresh_from_db()
                self.assertTrue(self.atencion.esta_abierta)
                self.assertFalse(Cobro.objects.exists())
                pendiente.delete()

    def test_cancelado_no_se_cobra_y_no_bloquea(self):
        self.pedido()
        self.pedido(estado=Pedido.Estado.CANCELADO, lineas=[(self.sopa, 5)])
        self.assertEqual(self.cobrar().total, Decimal('8.50'))

    def test_sin_consumo_impide_pago(self):
        with self.assertRaisesMessage(ErrorCobro, 'No hay productos entregados'):
            self.cobrar()
        self.assertFalse(Cobro.objects.exists())

    def test_solo_cancelados_impide_pago(self):
        self.pedido(estado=Pedido.Estado.CANCELADO)
        with self.assertRaises(ErrorCobro):
            self.cobrar()

    def test_pago_insuficiente(self):
        self.pedido()
        with self.assertRaisesMessage(ValidationError, 'no cubre'):
            self.cobrar(monto='8.49')
        self.assertFalse(Cobro.objects.exists())

    def test_tarjeta_y_otro_exigen_monto_exacto(self):
        self.pedido()
        for forma in (FormaPago.TARJETA, FormaPago.OTRO):
            with self.subTest(forma=forma):
                with self.assertRaisesMessage(ValidationError, 'monto exacto'):
                    self.cobrar(forma=forma)
        self.assertEqual(self.cobrar(monto='8.50', forma=FormaPago.TARJETA).cambio, Decimal('0.00'))

    def test_otro_medio_exacto_se_registra(self):
        self.pedido()
        self.assertEqual(self.cobrar(monto='8.50', forma=FormaPago.OTRO).forma_pago, FormaPago.OTRO)

    def test_montos_invalidos_y_forma_desconocida(self):
        self.pedido()
        valores = [Decimal('-1'), Decimal('0'), Decimal('NaN'), Decimal('Infinity'),
                   Decimal('10.001'), Decimal('1000000000000.00'), 10.0, '10.00', None]
        for monto in valores:
            with self.subTest(monto=monto):
                with self.assertRaises(ValidationError):
                    ServicioCobro().registrar(atencion_id=self.atencion.pk, monto_recibido=monto,
                                              forma_pago=FormaPago.EFECTIVO, cajero=self.cajero)
        with self.assertRaises(ValidationError):
            self.cobrar(forma='TRANSFERENCIA_NO_DEFINIDA')
        self.assertFalse(Cobro.objects.exists())

    def test_duplicado_rechazado_por_servicio(self):
        self.pedido()
        self.cobrar()
        with self.assertRaises(CobroDuplicadoError):
            self.cobrar()
        self.assertEqual(Cobro.objects.count(), 1)

    def test_unicidad_tambien_existe_en_postgresql(self):
        self.pedido()
        self.cobrar()
        duplicado = Cobro(atencion=self.atencion, total=Decimal('8.50'), monto_recibido=Decimal('10.00'),
                           forma_pago=FormaPago.EFECTIVO, cajero=self.cajero)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cobro.objects.bulk_create([duplicado])

    def test_rechaza_atencion_cerrada_sin_cobro(self):
        self.pedido()
        self.atencion.cerrar()
        with self.assertRaisesMessage(ErrorCobro, 'cerrada'):
            self.cobrar()

    def test_fallo_en_segundo_detalle_revierte_todo(self):
        self.pedido(lineas=[(self.producto, 1), (self.sopa, 1)])
        guardar = DetalleCobro.save
        llamadas = []

        def fallar(detalle, *args, **kwargs):
            llamadas.append(detalle)
            if len(llamadas) == 2:
                raise RuntimeError('Fallo de registro')
            return guardar(detalle, *args, **kwargs)

        with patch.object(DetalleCobro, 'save', autospec=True, side_effect=fallar):
            with self.assertRaises(RuntimeError):
                self.cobrar(monto='20.00')
        self.assertEqual(len(llamadas), 2)
        self.assertFalse(Cobro.objects.exists())
        self.assertFalse(DetalleCobro.objects.exists())
        self.atencion.refresh_from_db()
        self.assertTrue(self.atencion.esta_abierta)
        self.assertTrue(self.mesa.esta_ocupada)

    def test_fallo_despues_de_cerrar_revierte_pago_y_cierre(self):
        self.pedido()
        cerrar = Atencion.cerrar

        def fallar(atencion):
            cerrar(atencion)
            raise RuntimeError('Fallo después del cierre')

        with patch.object(Atencion, 'cerrar', autospec=True, side_effect=fallar):
            with self.assertRaises(RuntimeError):
                self.cobrar()
        self.assertFalse(Cobro.objects.exists())
        self.assertFalse(DetalleCobro.objects.exists())
        self.atencion.refresh_from_db()
        self.assertTrue(self.atencion.esta_abierta)
        self.assertIsNone(self.atencion.fecha_hora_cierre)

    def test_una_nueva_visita_no_reutiliza_consumo_anterior(self):
        self.pedido()
        primero = self.cobrar()
        nueva = ServicioIngreso().registrar_sin_reservacion(self.mesa, 2)
        self.pedido(atencion=nueva, lineas=[(self.sopa, 1)])
        segundo = self.cobrar(monto='3.00', atencion=nueva)
        self.assertEqual(primero.total, Decimal('8.50'))
        self.assertEqual(segundo.total, Decimal('3.00'))
        self.assertEqual(Cobro.objects.count(), 2)

    def test_cierre_respeta_reserva_y_no_habilita_mesa(self):
        self.pedido()
        reserva = Reservacion.objects.create(
            cliente=self.cliente, mesa=self.mesa, cantidad_personas=2,
            fecha_hora_inicio=timezone.now() + timedelta(hours=1))
        self.cobrar()
        self.assertFalse(ServicioDisponibilidad().mesa_disponible(
            self.mesa, timezone.now(), timedelta(hours=2), 2))
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reservacion.Estado.PROGRAMADA)

    def test_cierre_no_habilita_una_mesa_deshabilitada(self):
        self.pedido()
        Mesa.objects.filter(pk=self.mesa.pk).update(activo=False)
        self.cobrar()
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, 'Deshabilitada')

    def test_servicio_tambien_verifica_permiso_de_registro(self):
        self.pedido()
        with self.assertRaises(PermissionDenied):
            self.cobrar(cajero=self.lector)


class HistorialTests(DatosCobro):
    def test_catalogo_modificado_no_altera_historial(self):
        self.pedido()
        cobro = self.cobrar()
        self.producto.nombre = 'Nombre nuevo'
        self.producto.precio = Decimal('90.00')
        self.producto.activo = False
        self.producto.save()
        detalle = cobro.detalles.get()
        self.assertEqual(detalle.nombre_producto, 'Plato del día')
        self.assertEqual(detalle.precio_unitario, Decimal('8.50'))
        self.assertEqual(detalle.subtotal, Decimal('8.50'))
        self.assertEqual(cobro.total, Decimal('8.50'))

    def test_orm_impide_editar_o_eliminar_cobro_y_detalles(self):
        self.pedido()
        cobro = self.cobrar()
        for registro in (cobro, cobro.detalles.get()):
            with self.subTest(modelo=type(registro).__name__):
                with self.assertRaises(ValidationError):
                    registro.save()
                with self.assertRaises(ValidationError):
                    registro.delete()
                consulta = type(registro).objects.filter(pk=registro.pk)
                with self.assertRaises(ValidationError):
                    consulta.update(activo=False)
                with self.assertRaises(ValidationError):
                    consulta.delete()
                with self.assertRaises(ValidationError):
                    consulta.bulk_update([registro], ['activo'])
        with self.assertRaises(ValidationError):
            Cobro.objects.bulk_create([cobro], update_conflicts=True,
                                      unique_fields=['atencion'], update_fields=['total'])

    def test_referencias_originales_protegidas(self):
        pedido = self.pedido()
        self.cobrar()
        for origen in (self.atencion, pedido, pedido.detalles.get(), self.cajero):
            with self.subTest(origen=type(origen).__name__):
                with self.assertRaises(ProtectedError):
                    origen.delete()

    def test_admin_solo_permite_consulta(self):
        self.pedido()
        cobro = self.cobrar()
        request = type('Peticion', (), {'user': self.cajero})()
        configuracion = admin.site._registry[Cobro]
        self.assertTrue(configuracion.has_view_permission(request, cobro))
        self.assertFalse(configuracion.has_add_permission(request))
        self.assertFalse(configuracion.has_change_permission(request, cobro))
        self.assertFalse(configuracion.has_delete_permission(request, cobro))

    def test_no_admite_agregar_lineas_despues_del_cierre(self):
        self.pedido()
        cobro = self.cobrar()
        # Un alta directa fuera del servicio de pedidos no debe permitir
        # extender un historial financiero que ya se confirmó.
        posterior = self.pedido(lineas=[(self.sopa, 1)])
        with self.assertRaises(ValidationError):
            DetalleCobro.objects.create(
                cobro=cobro, detalle_pedido=posterior.detalles.get(),
                nombre_producto='Sopa', cantidad=1, precio_unitario=Decimal('3.00'))
        self.assertEqual(cobro.detalles.count(), 1)

    def test_base_de_datos_rechaza_pagos_incoherentes(self):
        casos = [('0.00', '1.00', 'EFECTIVO'), ('8.50', '8.49', 'EFECTIVO'),
                 ('8.50', '-1.00', 'EFECTIVO'), ('8.50', '10.00', 'TARJETA'),
                 ('8.50', '8.50', 'INVALIDO')]
        for total, monto, forma in casos:
            with self.subTest(total=total, monto=monto, forma=forma):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Cobro.objects.bulk_create([Cobro(
                        atencion=self.atencion, cajero=self.cajero, total=Decimal(total),
                        monto_recibido=Decimal(monto), forma_pago=forma)])
        self.assertFalse(Cobro.objects.exists())


class FormularioPagoTests(TestCase):
    def test_rechaza_montos_y_medios_invalidos(self):
        for monto in ('-1', '0', 'NaN', 'Infinity', '8.501', 'no-es-un-numero', ''):
            with self.subTest(monto=monto):
                form = RegistrarCobroForm({'forma_pago': 'EFECTIVO', 'monto_recibido': monto, 'confirmar': 'on'})
                self.assertFalse(form.is_valid())
                self.assertIn('monto_recibido', form.errors)
        form = RegistrarCobroForm({'forma_pago': 'INVALIDO', 'monto_recibido': '10', 'confirmar': 'on'})
        self.assertFalse(form.is_valid())
        self.assertIn('forma_pago', form.errors)

    def test_exige_confirmacion(self):
        form = RegistrarCobroForm({'forma_pago': 'EFECTIVO', 'monto_recibido': '10'})
        self.assertFalse(form.is_valid())
        self.assertIn('confirmar', form.errors)


class VistasCobroTests(DatosCobro):
    def setUp(self):
        self.client.force_login(self.cajero)

    def url_consumo(self):
        return reverse('cobro:detalle_consumo', args=[self.atencion.pk])

    def url_registro(self):
        return reverse('cobro:registrar_cobro', args=[self.atencion.pk])

    def datos_pago(self, **extra):
        return {'monto_recibido': '10.00', 'forma_pago': 'EFECTIVO', 'confirmar': 'on', **extra}

    def test_lista_y_detalle_heredan_base_y_no_cierran(self):
        self.pedido()
        lista = self.client.get(reverse('cobro:lista_atenciones'))
        self.assertContains(lista, 'Mesa 1')
        respuesta = self.client.get(self.url_consumo())
        self.assertTemplateUsed(respuesta, 'core/base.html')
        self.assertContains(respuesta, 'Plato del día')
        self.assertContains(respuesta, 'cobro/css/cobro.css')
        self.atencion.refresh_from_db()
        self.assertTrue(self.atencion.esta_abierta)
        self.assertFalse(Cobro.objects.exists())

    def test_muestra_sin_consumo_y_no_ofrece_pago(self):
        respuesta = self.client.get(self.url_consumo())
        self.assertContains(respuesta, 'No hay consumo entregado')
        self.assertNotContains(respuesta, 'id="form-cobro"')
        self.client.post(self.url_registro(), self.datos_pago())
        self.assertFalse(Cobro.objects.exists())

    def test_pendientes_muestran_bloqueo_y_no_ofrecen_pago(self):
        self.pedido()
        self.pedido(estado=Pedido.Estado.LISTO)
        respuesta = self.client.get(self.url_consumo())
        self.assertContains(respuesta, 'Cobro habilitado hasta que se entregue el pedido al cliente.')
        self.assertNotContains(respuesta, 'id="form-cobro"')

    def test_datos_historicos_invalidos_no_muestran_total_parcial(self):
        self.pedido()
        invalido = self.pedido(lineas=[(self.sopa, 1)])
        invalido.detalles.update(precio_unitario=Decimal('0.00'))
        respuesta = self.client.get(self.url_consumo())
        self.assertContains(respuesta, 'No disponible')
        self.assertIsNone(respuesta.context['consumo'])
        self.assertNotContains(respuesta, 'id="form-cobro"')
        self.client.post(self.url_registro(), self.datos_pago())
        self.assertFalse(Cobro.objects.exists())

    def test_post_ignora_total_cajero_y_cambio_del_navegador(self):
        self.pedido()
        respuesta = self.client.post(self.url_registro(), self.datos_pago(
            total='0.01', cajero=self.sin_permisos.pk, cambio='99.00'))
        cobro = Cobro.objects.get()
        self.assertRedirects(respuesta, reverse('cobro:detalle_cobro', args=[cobro.pk]))
        self.assertEqual(cobro.total, Decimal('8.50'))
        self.assertEqual(cobro.cajero, self.cajero)
        self.assertEqual(cobro.cambio, Decimal('1.50'))

    def test_pago_invalido_muestra_error_de_campo(self):
        self.pedido()
        respuesta = self.client.post(self.url_registro(), self.datos_pago(monto_recibido='1.00'))
        self.assertContains(respuesta, 'no cubre')
        self.assertIn('monto_recibido', respuesta.context['form'].errors)
        self.assertFalse(Cobro.objects.exists())

    def test_registrar_no_admite_get(self):
        self.assertEqual(self.client.get(self.url_registro()).status_code, 405)

    def test_csrf_es_obligatorio(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.cajero)
        self.assertEqual(cliente.post(self.url_registro(), self.datos_pago()).status_code, 403)

    def test_anonimo_y_usuario_sin_permisos_no_acceden(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url_consumo()).status_code, 302)
        self.client.force_login(self.sin_permisos)
        for url in (reverse('cobro:lista_atenciones'), self.url_consumo(), reverse('cobro:historial')):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(self.url_registro(), self.datos_pago()).status_code, 403)

    def test_lector_consulta_pero_no_registra(self):
        self.pedido()
        self.client.force_login(self.lector)
        respuesta = self.client.get(self.url_consumo())
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'id="form-cobro"')
        self.assertEqual(self.client.post(self.url_registro(), self.datos_pago()).status_code, 403)

    def test_reenvio_del_post_no_duplica_y_consulta_pagada_usa_historial(self):
        self.pedido()
        self.client.post(self.url_registro(), self.datos_pago())
        cobro = Cobro.objects.get()
        destino = reverse('cobro:detalle_cobro', args=[cobro.pk])
        self.assertRedirects(self.client.post(self.url_registro(), self.datos_pago()), destino)
        self.assertRedirects(self.client.get(self.url_consumo()), destino)
        self.assertEqual(Cobro.objects.count(), 1)
        respuesta = self.client.get(reverse('cobro:lista_atenciones'))
        self.assertNotContains(respuesta, f'Atención #{self.atencion.pk}<')

    def test_historial_muestra_copia_tras_editar_catalogo(self):
        self.pedido()
        cobro = self.cobrar()
        self.producto.nombre = 'Nombre posterior'
        self.producto.save()
        respuesta = self.client.get(reverse('cobro:detalle_cobro', args=[cobro.pk]))
        self.assertContains(respuesta, 'Plato del día')
        self.assertNotContains(respuesta, 'Nombre posterior')
        self.assertContains(self.client.get(reverse('cobro:historial')), f'#{cobro.pk}')

    def test_sidebar_respeta_permiso(self):
        destino = reverse('cobro:lista_atenciones')
        self.assertContains(self.client.get(reverse('core:home')), f'href="{destino}"')
        self.client.force_login(self.sin_permisos)
        self.assertNotContains(self.client.get(reverse('core:home')), f'href="{destino}"')

    def test_atencion_inexistente_es_404(self):
        self.assertEqual(self.client.get(reverse('cobro:detalle_consumo', args=[999999])).status_code, 404)

    def test_flujo_real_formulario_pedido_cocina_entrega_y_cobro_con_csrf(self):
        self.cajero.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='pedidos',
            codename__in=['add_pedido', 'view_pedido', 'cambiar_estado_pedido']))
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.cajero)
        nuevo = reverse('pedidos:crear_pedido')
        self.assertEqual(cliente.get(nuevo).status_code, 200)
        token = cliente.cookies['csrftoken'].value
        respuesta = cliente.post(nuevo, {
            'csrfmiddlewaretoken': token, 'mesa': self.mesa.pk, 'notas': '',
            'detalles-TOTAL_FORMS': 1, 'detalles-INITIAL_FORMS': 0,
            'detalles-MIN_NUM_FORMS': 0, 'detalles-MAX_NUM_FORMS': 1000,
            'detalles-0-producto': self.producto.pk, 'detalles-0-cantidad': 2,
            'detalles-0-nota': '',
        })
        pedido = Pedido.objects.get(atencion=self.atencion)
        self.assertRedirects(respuesta, reverse('pedidos:detalle_pedido', args=[pedido.pk]))
        bloqueado = cliente.post(self.url_registro(), self.datos_pago(
            csrfmiddlewaretoken=token, monto_recibido='20.00'))
        self.assertContains(bloqueado, 'pedidos pendientes')
        for estado in (Pedido.Estado.EN_PREPARACION, Pedido.Estado.LISTO, Pedido.Estado.ENTREGADO):
            cambio = cliente.post(reverse('pedidos:cambiar_estado', args=[pedido.pk, estado]),
                                  {'csrfmiddlewaretoken': token})
            self.assertEqual(cambio.status_code, 302)
        self.producto.precio = Decimal('99.00')
        self.producto.save()
        respuesta = cliente.post(self.url_registro(), self.datos_pago(
            csrfmiddlewaretoken=token, monto_recibido='20.00'))
        cobro = Cobro.objects.get(atencion=self.atencion)
        self.assertRedirects(respuesta, reverse('cobro:detalle_cobro', args=[cobro.pk]))
        self.assertEqual(cobro.total, Decimal('17.00'))
        self.assertEqual(cobro.cambio, Decimal('3.00'))
        self.assertFalse(self.mesa.esta_ocupada)
