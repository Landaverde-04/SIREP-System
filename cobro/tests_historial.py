"""Resumen global del historial, calculado a partir de cobros confirmados."""

from decimal import Decimal

from django.urls import reverse

from pedidos.models import Pedido
from reservaciones.servicios import ServicioIngreso

from .tests_integracion import DatosCobro


class ResumenHistorialTests(DatosCobro):
    def setUp(self):
        self.client.force_login(self.cajero)
        self.url = reverse('cobro:historial')

    def test_historial_vacio_muestra_cero_decimal_y_cero_cobros(self):
        self.pedido(estado=Pedido.Estado.PENDIENTE)
        respuesta = self.client.get(self.url)
        resumen = respuesta.context['resumen']
        self.assertEqual(resumen['total_cobrado'], Decimal('0.00'))
        self.assertIsInstance(resumen['total_cobrado'], Decimal)
        self.assertEqual(resumen['cobros_registrados'], 0)
        self.assertContains(respuesta, 'Total cobrado')
        self.assertContains(respuesta, '$ 0.00')
        self.assertContains(respuesta, 'Cobros registrados')
        self.assertContains(respuesta, 'Todavía no hay cobros registrados.')

    def test_suma_totales_sin_duplicar_detalles_ni_incluir_cambio(self):
        self.pedido(lineas=[(self.producto, 1), (self.sopa, 2)])
        primero = self.cobrar(monto='20.00')
        self.pedido(atencion=self.otra_atencion, lineas=[(self.sopa, 1)])
        segundo = self.cobrar(monto='10.00', atencion=self.otra_atencion)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.context['resumen'], {
            'total_cobrado': Decimal('17.50'), 'cobros_registrados': 2,
        })
        self.assertContains(respuesta, '$ 17.50')
        self.assertEqual(len(respuesta.context['pagina']), 2)
        for cobro in (primero, segundo):
            self.assertContains(respuesta, reverse('cobro:detalle_cobro', args=[cobro.pk]))

    def test_precision_decimal_del_acumulado(self):
        self.producto.precio = Decimal('0.10')
        self.producto.save()
        self.sopa.precio = Decimal('0.20')
        self.sopa.save()
        self.pedido()
        self.cobrar(monto='1.00')
        self.pedido(atencion=self.otra_atencion, lineas=[(self.sopa, 1)])
        self.cobrar(monto='1.00', atencion=self.otra_atencion)
        resumen = self.client.get(self.url).context['resumen']
        self.assertEqual(resumen['total_cobrado'], Decimal('0.30'))
        self.assertIsInstance(resumen['total_cobrado'], Decimal)
        self.assertEqual(resumen['cobros_registrados'], 2)

    def test_no_incluye_pedidos_consumos_o_atenciones_sin_pago(self):
        self.pedido()
        self.cobrar()
        for estado in (*Pedido.ESTADOS_EN_CURSO, Pedido.Estado.ENTREGADO, Pedido.Estado.CANCELADO):
            self.pedido(estado=estado, atencion=self.otra_atencion,
                        lineas=[(self.producto, 10)])
        ServicioIngreso().registrar_sin_reservacion(self.mesa, 2)
        self.assertEqual(self.client.get(self.url).context['resumen'], {
            'total_cobrado': Decimal('8.50'), 'cobros_registrados': 1,
        })

    def test_resumen_incluye_paginas_no_visibles(self):
        atencion = self.atencion
        for indice in range(21):
            self.pedido(atencion=atencion, lineas=[(self.sopa, 1)])
            self.cobrar(monto='5.00', atencion=atencion)
            if indice < 20:
                atencion = ServicioIngreso().registrar_sin_reservacion(self.mesa, 2)
        for numero, cantidad_visible in ((1, 20), (2, 1)):
            with self.subTest(pagina=numero):
                respuesta = self.client.get(self.url, {'page': numero})
                self.assertEqual(len(respuesta.context['pagina']), cantidad_visible)
                self.assertEqual(respuesta.context['resumen'], {
                    'total_cobrado': Decimal('63.00'), 'cobros_registrados': 21,
                })
                self.assertContains(respuesta, '$ 63.00')
