"""Consulta provisional y su separación del cobro autorizado por lo entregado."""

from decimal import Decimal

from django.urls import reverse

from pedidos.forms import DetallePedidoFormSet, PedidoForm
from pedidos.models import Pedido
from pedidos.servicios import ServicioPedidos

from .excepciones import CobroDuplicadoError, ConsumoInvalidoError, ErrorCobro
from .integracion import AdaptadorConsumoPedidos
from .models import Cobro, DetalleCobro
from .tests_integracion import DatosCobro


class ConsultaEstimadaTests(DatosCobro):
    def consultar(self):
        return AdaptadorConsumoPedidos().consultar(self.atencion)

    def test_pendientes_sin_entregados_muestran_estimado_y_entregado_cero(self):
        for estado in Pedido.ESTADOS_EN_CURSO:
            self.pedido(estado=estado, lineas=[(self.sopa, 2)])
        consumo = self.consultar()
        self.assertEqual(consumo.total, Decimal('0.00'))
        self.assertEqual(consumo.total_estimado, Decimal('18.00'))
        self.assertEqual(len(consumo.lineas_solicitadas), 3)
        self.assertEqual(consumo.lineas, ())
        self.assertFalse(consumo.puede_cobrarse)
        self.assertEqual({linea.estado_pedido for linea in consumo.lineas_solicitadas},
                         set(Pedido.ESTADOS_EN_CURSO))

    def test_mezcla_de_estados_separa_ambos_totales(self):
        self.pedido(lineas=[(self.producto, 2)])
        self.pedido(estado=Pedido.Estado.EN_PREPARACION, lineas=[(self.sopa, 3)])
        consumo = self.consultar()
        self.assertEqual(consumo.total, Decimal('17.00'))
        self.assertEqual(consumo.total_estimado, Decimal('26.00'))
        self.assertEqual(len(consumo.lineas), 1)
        self.assertEqual(len(consumo.lineas_solicitadas), 2)
        self.assertTrue(consumo.lineas_solicitadas[0].entregado)
        self.assertFalse(consumo.lineas_solicitadas[1].entregado)
        self.assertEqual(consumo.lineas_solicitadas[1].estado_pedido_display, 'En preparación')
        self.assertFalse(consumo.puede_cobrarse)

    def test_todos_entregados_totales_coinciden(self):
        self.pedido(lineas=[(self.producto, 2)])
        self.pedido(lineas=[(self.sopa, 1)])
        consumo = self.consultar()
        self.assertEqual(consumo.total, Decimal('20.00'))
        self.assertEqual(consumo.total_estimado, consumo.total)
        self.assertTrue(consumo.puede_cobrarse)

    def test_cancelados_se_excluyen_de_productos_y_ambos_calculos(self):
        self.pedido()
        self.pedido(estado=Pedido.Estado.PENDIENTE, lineas=[(self.sopa, 1)])
        cancelado = self.pedido(estado=Pedido.Estado.CANCELADO, lineas=[(self.producto, 10)])
        # Un dato inválido en lo cancelado tampoco debe contaminar el consumo.
        cancelado.detalles.update(precio_unitario=Decimal('0.00'))
        consumo = self.consultar()
        self.assertEqual(consumo.total, Decimal('8.50'))
        self.assertEqual(consumo.total_estimado, Decimal('11.50'))
        self.assertEqual(len(consumo.lineas_solicitadas), 2)
        self.assertNotIn(cancelado.pk, [linea.origen.pedido_id for linea in consumo.lineas_solicitadas])

    def test_solo_cancelados_y_sin_pedidos_producen_cero(self):
        for hay_cancelado in (False, True):
            with self.subTest(hay_cancelado=hay_cancelado):
                if hay_cancelado:
                    self.pedido(estado=Pedido.Estado.CANCELADO)
                consumo = self.consultar()
                self.assertEqual(consumo.total, Decimal('0.00'))
                self.assertEqual(consumo.total_estimado, Decimal('0.00'))
                self.assertEqual(consumo.lineas_solicitadas, ())
                self.assertFalse(consumo.puede_cobrarse)

    def test_estimado_conserva_precio_historico_aun_sin_entrega(self):
        self.pedido(estado=Pedido.Estado.PENDIENTE, lineas=[(self.producto, 2)])
        self.producto.precio = Decimal('99.00')
        self.producto.save()
        consumo = self.consultar()
        self.assertEqual(consumo.lineas_solicitadas[0].precio_unitario, Decimal('8.50'))
        self.assertEqual(consumo.total_estimado, Decimal('17.00'))
        self.assertEqual(consumo.total, Decimal('0.00'))

    def test_nueva_consulta_refleja_edicion_valida_y_nuevas_lineas(self):
        pedido = self.pedido(estado=Pedido.Estado.PENDIENTE)
        original = pedido.detalles.get()
        self.assertEqual(self.consultar().total_estimado, Decimal('8.50'))
        self.producto.precio = Decimal('99.00')
        self.producto.save()
        datos = {
            'mesa': self.mesa.pk, 'notas': '',
            'detalles-TOTAL_FORMS': 2, 'detalles-INITIAL_FORMS': 1,
            'detalles-MIN_NUM_FORMS': 0, 'detalles-MAX_NUM_FORMS': 1000,
            'detalles-0-id': original.pk, 'detalles-0-producto': self.producto.pk,
            'detalles-0-cantidad': 2, 'detalles-0-nota': '',
            'detalles-1-producto': self.sopa.pk, 'detalles-1-cantidad': 2,
            'detalles-1-nota': '',
        }
        form = PedidoForm(datos, instance=pedido)
        formset = DetallePedidoFormSet(datos, instance=pedido)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)
        ServicioPedidos().guardar(form, formset, self.cajero)
        consumo = self.consultar()
        self.assertEqual(consumo.total_estimado, Decimal('23.00'))
        self.assertEqual(consumo.total, Decimal('0.00'))
        self.assertEqual([linea.cantidad for linea in consumo.lineas_solicitadas], [2, 2])

    def test_estimado_de_otras_atenciones_no_se_mezcla(self):
        self.pedido(estado=Pedido.Estado.PENDIENTE, lineas=[(self.sopa, 1)])
        self.pedido(atencion=self.otra_atencion, lineas=[(self.producto, 10)])
        self.assertEqual(self.consultar().total_estimado, Decimal('3.00'))

    def test_precio_invalido_pendiente_no_muestra_estimado_parcial(self):
        self.pedido()
        pendiente = self.pedido(estado=Pedido.Estado.LISTO, lineas=[(self.sopa, 1)])
        pendiente.detalles.update(precio_unitario=Decimal('0.00'))
        with self.assertRaises(ConsumoInvalidoError):
            self.consultar()

    def test_estimado_no_habilita_cobro_y_entrega_posterior_permite_pago(self):
        self.pedido()
        pendiente = self.pedido(estado=Pedido.Estado.PENDIENTE, lineas=[(self.sopa, 1)])
        antes = self.consultar()
        self.assertEqual(antes.total_estimado, Decimal('11.50'))
        with self.assertRaisesMessage(ErrorCobro, 'pedidos pendientes'):
            self.cobrar(monto='12.00')
        self.assertFalse(Cobro.objects.exists())
        for estado in (Pedido.Estado.EN_PREPARACION, Pedido.Estado.LISTO, Pedido.Estado.ENTREGADO):
            ServicioPedidos().cambiar_estado(pendiente.pk, estado)
        despues = self.consultar()
        self.assertEqual(despues.total, antes.total_estimado)
        self.assertTrue(despues.puede_cobrarse)
        cobro = self.cobrar(monto='12.00')
        self.assertEqual(cobro.total, Decimal('11.50'))
        self.assertEqual(cobro.cambio, Decimal('0.50'))
        self.assertEqual(cobro.cajero, self.cajero)
        self.assertIsNotNone(cobro.fecha_hora_pago)
        self.atencion.refresh_from_db()
        self.assertFalse(self.atencion.esta_abierta)
        self.assertFalse(self.mesa.esta_ocupada)
        with self.assertRaises(CobroDuplicadoError):
            self.cobrar(monto='12.00')
        self.assertEqual(Cobro.objects.count(), 1)


class ConsultaEstimadaVistasTests(DatosCobro):
    def setUp(self):
        self.client.force_login(self.cajero)
        self.url = reverse('cobro:detalle_consumo', args=[self.atencion.pk])

    def comprobar_boton_bloqueado(self, respuesta):
        self.assertContains(respuesta, '<button type="button" class="btn btn-dark w-100" '
                            'id="confirmar-cobro-bloqueado" disabled '
                            'aria-describedby="aviso-pendientes">Registrar cobro y cerrar</button>', html=True)
        self.assertNotContains(respuesta, 'id="form-cobro"')

    def test_pendientes_sin_entrega_muestran_productos_estados_y_totales(self):
        for estado in Pedido.ESTADOS_EN_CURSO:
            self.pedido(estado=estado, lineas=[(self.sopa, 1)])
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Sopa', count=3)
        for estado in Pedido.ESTADOS_EN_CURSO:
            self.assertContains(respuesta, f'data-estado="{estado}"')
        self.assertEqual(respuesta.context['consumo'].total, Decimal('0.00'))
        self.assertEqual(respuesta.context['consumo'].total_estimado, Decimal('9.00'))
        self.assertContains(respuesta, 'data-importe="0.00"')
        self.assertContains(respuesta, 'data-importe="9.00"')
        self.assertContains(respuesta, 'Informativo y provisional')
        self.assertContains(respuesta, 'Cobro habilitado hasta que se entregue el pedido al cliente.')
        for pedido in respuesta.context['consumo'].pendientes:
            self.assertContains(respuesta, f'Pedido #{pedido.pk}: {pedido.get_estado_display()}')
        self.assertNotContains(respuesta, 'El registro estará disponible cuando exista consumo válido '
                               'y no haya pedidos en curso.')
        self.comprobar_boton_bloqueado(respuesta)

    def test_entregados_y_pendientes_visibles_con_pago_bloqueado(self):
        self.pedido()
        self.pedido(estado=Pedido.Estado.LISTO, lineas=[(self.sopa, 2)])
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Plato del día')
        self.assertContains(respuesta, 'Sopa')
        self.assertContains(respuesta, 'data-estado="ENTREGADO"')
        self.assertContains(respuesta, 'data-estado="LISTO"')
        self.assertEqual(respuesta.context['consumo'].total, Decimal('8.50'))
        self.assertEqual(respuesta.context['consumo'].total_estimado, Decimal('14.50'))
        self.comprobar_boton_bloqueado(respuesta)

    def test_post_directo_no_permite_pagar_un_estimado(self):
        self.pedido(estado=Pedido.Estado.PENDIENTE)
        respuesta = self.client.post(reverse('cobro:registrar_cobro', args=[self.atencion.pk]), {
            'monto_recibido': '8.50', 'forma_pago': 'EFECTIVO', 'confirmar': 'on',
            'total': '8.50', 'total_estimado': '8.50',
        })
        self.assertContains(respuesta, 'No se puede cobrar')
        self.comprobar_boton_bloqueado(respuesta)
        self.assertFalse(Cobro.objects.exists())
        self.atencion.refresh_from_db()
        self.assertTrue(self.atencion.esta_abierta)

    def test_sin_pendientes_el_formulario_usa_solo_total_entregado(self):
        self.pedido()
        self.pedido(estado=Pedido.Estado.CANCELADO, lineas=[(self.sopa, 10)])
        respuesta = self.client.get(self.url)
        self.assertNotContains(respuesta, 'Sopa')
        self.assertContains(respuesta, 'id="form-cobro" data-total="8.50"')
        self.assertNotContains(respuesta, 'id="confirmar-cobro-bloqueado"')
        self.assertEqual(respuesta.context['form'].fields['monto_recibido'].initial, Decimal('8.50'))

    def test_error_en_estimado_impide_mostrar_cifras_parciales(self):
        self.pedido()
        pendiente = self.pedido(estado=Pedido.Estado.PENDIENTE, lineas=[(self.sopa, 1)])
        pendiente.detalles.update(precio_unitario=Decimal('0.00'))
        respuesta = self.client.get(self.url)
        self.assertIsNone(respuesta.context['consumo'])
        self.assertNotContains(respuesta, 'data-importe=')
        self.assertNotContains(respuesta, 'id="form-cobro"')

    def test_consulta_ampliada_no_modifica_historial_confirmado(self):
        self.pedido()
        cobro = self.cobrar()
        antes_cobro = list(Cobro.objects.values())
        antes_detalles = list(DetalleCobro.objects.values())
        self.producto.nombre = 'Nombre posterior'
        self.producto.precio = Decimal('99.00')
        self.producto.save()
        destino = reverse('cobro:detalle_cobro', args=[cobro.pk])
        self.assertRedirects(self.client.get(self.url), destino)
        respuesta = self.client.get(destino)
        self.assertContains(respuesta, 'Plato del día')
        self.assertNotContains(respuesta, 'Nombre posterior')
        self.assertNotContains(respuesta, 'Total estimado')
        self.assertEqual(list(Cobro.objects.values()), antes_cobro)
        self.assertEqual(list(DetalleCobro.objects.values()), antes_detalles)
