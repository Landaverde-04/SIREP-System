"""Pruebas del dominio de consumo; no requieren Django ni base de datos."""

from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
from unittest import TestCase

from .consumo import DetalleConsumo, ServicioConsumo


class DetalleConsumoTests(TestCase):
    def test_cantidades_invalidas(self):
        for cantidad in (0, -1, True, False, 1.5, Decimal('2'), '2', None):
            with self.subTest(cantidad=cantidad):
                with self.assertRaisesRegex(ValueError, 'cantidad'):
                    DetalleConsumo(cantidad, Decimal('1.50'))

    def test_precios_invalidos(self):
        precios = (
            Decimal('0'), Decimal('-0.01'), Decimal('NaN'), Decimal('sNaN'),
            Decimal('Infinity'), Decimal('-Infinity'), Decimal('1.001'),
            Decimal('0.001'), 1.50, 2, True, '1.50', None,
        )
        for precio in precios:
            with self.subTest(precio=precio):
                with self.assertRaisesRegex(ValueError, 'precio'):
                    DetalleConsumo(1, precio)

    def test_admite_ceros_adicionales_sin_redondear(self):
        detalle = DetalleConsumo(2, Decimal('1.5000'))
        self.assertEqual(detalle.precio_unitario, Decimal('1.50'))
        self.assertEqual(detalle.precio_unitario.as_tuple().exponent, -2)
        self.assertEqual(detalle.subtotal, Decimal('3.00'))

    def test_admite_un_centavo(self):
        self.assertEqual(DetalleConsumo(1, Decimal('0.01')).subtotal, Decimal('0.01'))

    def test_detalle_es_inmutable(self):
        detalle = DetalleConsumo(1, Decimal('2.00'))
        with self.assertRaises(FrozenInstanceError):
            detalle.precio_unitario = Decimal('3.00')
        with self.assertRaises(FrozenInstanceError):
            detalle.cantidad = 2


class ServicioConsumoTests(TestCase):
    def setUp(self):
        self.servicio = ServicioConsumo()

    def test_un_producto(self):
        detalle = DetalleConsumo(1, Decimal('4.75'))
        consumo = self.servicio.calcular([detalle])
        self.assertEqual(consumo.detalles, (detalle,))
        self.assertEqual(consumo.detalles[0].subtotal, Decimal('4.75'))
        self.assertEqual(consumo.total, Decimal('4.75'))
        self.assertIsInstance(consumo.total, Decimal)

    def test_varios_productos(self):
        consumo = self.servicio.calcular([
            DetalleConsumo(1, Decimal('4.75')),
            DetalleConsumo(1, Decimal('1.25')),
            DetalleConsumo(1, Decimal('2.10')),
        ])
        self.assertEqual(
            [detalle.subtotal for detalle in consumo.detalles],
            [Decimal('4.75'), Decimal('1.25'), Decimal('2.10')],
        )
        self.assertEqual(consumo.total, Decimal('8.10'))

    def test_cantidades_multiples(self):
        consumo = self.servicio.calcular([
            DetalleConsumo(3, Decimal('2.50')),
            DetalleConsumo(2, Decimal('1.25')),
        ])
        self.assertEqual(
            [detalle.subtotal for detalle in consumo.detalles],
            [Decimal('7.50'), Decimal('2.50')],
        )
        self.assertEqual(consumo.total, Decimal('10.00'))

    def test_precision_decimal(self):
        consumo = self.servicio.calcular([
            DetalleConsumo(3, Decimal('0.10')),
            DetalleConsumo(1, Decimal('0.20')),
        ])
        self.assertEqual(consumo.detalles[0].subtotal, Decimal('0.30'))
        self.assertEqual(consumo.total, Decimal('0.50'))
        self.assertEqual(consumo.total.as_tuple().exponent, -2)

    def test_consumo_vacio(self):
        consumo = self.servicio.calcular([])
        self.assertEqual(consumo.detalles, ())
        self.assertEqual(consumo.total, Decimal('0.00'))
        self.assertEqual(consumo.total.as_tuple().exponent, -2)

    def test_precio_historico_independiente_del_catalogo(self):
        # Datos simples: no se simula un modelo ni una integración de pedidos.
        catalogo = {'precio': Decimal('2.50')}
        detalle = DetalleConsumo(2, catalogo['precio'])
        catalogo['precio'] = Decimal('9.00')
        consumo = self.servicio.calcular([detalle])
        self.assertEqual(consumo.detalles[0].precio_unitario, Decimal('2.50'))
        self.assertEqual(consumo.total, Decimal('5.00'))

    def test_acepta_generadores(self):
        detalles = (DetalleConsumo(1, Decimal('1.25')) for _ in range(3))
        consumo = self.servicio.calcular(detalles)
        self.assertEqual(len(consumo.detalles), 3)
        self.assertEqual(consumo.total, Decimal('3.75'))

    def test_rechaza_detalles_sin_el_contrato_de_entrada(self):
        for detalle in (None, {'cantidad': 1, 'precio_unitario': Decimal('1.00')}, object()):
            with self.subTest(detalle=detalle):
                with self.assertRaisesRegex(TypeError, 'DetalleConsumo'):
                    self.servicio.calcular([detalle])

    def test_lista_original_no_altera_el_resultado(self):
        detalles = [DetalleConsumo(1, Decimal('2.00'))]
        consumo = self.servicio.calcular(detalles)
        detalles.append(DetalleConsumo(1, Decimal('8.00')))
        self.assertEqual(len(consumo.detalles), 1)
        self.assertEqual(consumo.total, Decimal('2.00'))
        with self.assertRaises(FrozenInstanceError):
            consumo.total = Decimal('10.00')

    def test_no_acumula_consumos_entre_llamadas(self):
        self.servicio.calcular([DetalleConsumo(1, Decimal('8.00'))])
        self.assertEqual(self.servicio.calcular([]).total, Decimal('0.00'))

    def test_calculo_exacto_con_contexto_decimal_de_baja_precision(self):
        with localcontext() as contexto:
            contexto.prec = 4
            consumo = self.servicio.calcular([
                DetalleConsumo(300, Decimal('1234.56')),
                DetalleConsumo(2, Decimal('0.01')),
            ])
            self.assertEqual(consumo.detalles[0].subtotal, Decimal('370368.00'))
            self.assertEqual(consumo.total, Decimal('370368.02'))
            self.assertEqual(contexto.prec, 4)

    def test_importes_grandes_no_pierden_centavos(self):
        consumo = self.servicio.calcular([
            DetalleConsumo(3, Decimal('123456789012345678901234567890.12')),
            DetalleConsumo(1, Decimal('0.01')),
        ])
        self.assertEqual(consumo.total, Decimal('370370367037037036703703703670.37'))
