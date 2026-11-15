"""Carreras reales con conexiones y transacciones independientes en PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event
from time import monotonic
from unittest import skipUnless

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase

from administracion.models import CategoriaProducto, Mesa, Producto
from pedidos.forms import DetallePedidoFormSet, PedidoForm
from pedidos.models import DetallePedido, Pedido
from pedidos.servicios import ServicioPedidos
from reservaciones.models import Atencion
from reservaciones.servicios import ServicioIngreso
from seguridad.models import Usuario

from .excepciones import CobroDuplicadoError, ErrorCobro
from .models import Cobro
from .pagos import FormaPago
from .servicios import ServicioCobro


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueos reales de PostgreSQL.')
class ConcurrenciaCobroTests(TransactionTestCase):
    def setUp(self):
        self.cajero = Usuario.objects.create_user('cajero_concurrencia')
        self.cajero.user_permissions.add(Permission.objects.get(
            content_type__app_label='cobro', codename='add_cobro'))
        self.mesa = Mesa.objects.create(numero=1, capacidad=4)
        self.atencion = ServicioIngreso().registrar_sin_reservacion(self.mesa, 2)
        categoria = CategoriaProducto.objects.create(nombre='Platos')
        self.producto = Producto.objects.create(nombre='Plato', precio=Decimal('8.50'), categoria=categoria)
        self.pedido = Pedido.objects.create(mesa=self.mesa, atencion=self.atencion,
                                             mesero=self.cajero, estado=Pedido.Estado.ENTREGADO)
        DetallePedido.objects.create(pedido=self.pedido, producto=self.producto, cantidad=1)

    def cobrar_en_conexion(self, barrera=None, iniciado=None, pid=None):
        close_old_connections()
        try:
            cajero = Usuario.objects.get(pk=self.cajero.pk)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '8s'")
                    cursor.execute('SELECT pg_backend_pid()')
                    if pid is not None:
                        pid.append(cursor.fetchone()[0])
                if iniciado:
                    iniciado.set()
                if barrera:
                    barrera.wait(timeout=10)
                try:
                    cobro = ServicioCobro().registrar(
                        atencion_id=self.atencion.pk, cajero=cajero,
                        monto_recibido=Decimal('10.00'), forma_pago=FormaPago.EFECTIVO)
                except CobroDuplicadoError:
                    return 'duplicado'
                except ErrorCobro as error:
                    return error.code
                return cobro.pk
        finally:
            connections.close_all()

    def esperar_bloqueo(self, pid):
        """Confirma la espera en PostgreSQL; no presupone tiempos de ejecución."""
        limite = monotonic() + 6
        while monotonic() < limite:
            with connection.cursor() as cursor:
                cursor.execute('SELECT cardinality(pg_blocking_pids(%s))', [pid])
                if cursor.fetchone()[0]:
                    return
            Event().wait(0.02)
        self.fail('No se observó el bloqueo esperado entre las conexiones.')

    def test_dos_cobros_simultaneos_generan_un_solo_pago(self):
        barrera = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            futuros = [ejecutor.submit(self.cobrar_en_conexion, barrera) for _ in range(2)]
            resultados = [f.result(timeout=15) for f in futuros]
        self.assertEqual(resultados.count('duplicado'), 1)
        self.assertEqual(sum(isinstance(r, int) for r in resultados), 1)
        self.assertEqual(Cobro.objects.count(), 1)
        self.assertEqual(Cobro.objects.get().detalles.count(), 1)
        self.atencion.refresh_from_db()
        self.assertFalse(self.atencion.esta_abierta)

    def test_cobro_espera_entrega_y_relee_estado_confirmado(self):
        Pedido.objects.filter(pk=self.pedido.pk).update(estado=Pedido.Estado.LISTO)
        retenido, liberar, iniciado = Event(), Event(), Event()
        pid = []

        def entregar():
            close_old_connections()
            try:
                with transaction.atomic():
                    ServicioPedidos().cambiar_estado(self.pedido.pk, Pedido.Estado.ENTREGADO)
                    retenido.set()
                    if not liberar.wait(timeout=10):
                        raise TimeoutError('No se liberó la entrega de prueba.')
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            entrega = ejecutor.submit(entregar)
            try:
                self.assertTrue(retenido.wait(timeout=6))
                cobro = ejecutor.submit(self.cobrar_en_conexion, None, iniciado, pid)
                self.assertTrue(iniciado.wait(timeout=6))
                self.esperar_bloqueo(pid[0])
            finally:
                liberar.set()
            entrega.result(timeout=12)
            self.assertIsInstance(cobro.result(timeout=12), int)
        self.assertEqual(Cobro.objects.get().total, Decimal('8.50'))

    def test_pedido_en_guardado_se_confirma_sin_interbloqueo_y_bloquea_cobro(self):
        retenido, liberar, iniciado = Event(), Event(), Event()
        pid = []

        def guardar_pedido():
            close_old_connections()
            try:
                datos = {
                    'mesa': self.mesa.pk, 'notas': '',
                    'detalles-TOTAL_FORMS': 1, 'detalles-INITIAL_FORMS': 0,
                    'detalles-MIN_NUM_FORMS': 0, 'detalles-MAX_NUM_FORMS': 1000,
                    'detalles-0-producto': self.producto.pk, 'detalles-0-cantidad': 1,
                    'detalles-0-nota': '',
                }
                pedido = Pedido()
                form = PedidoForm(datos, instance=pedido)
                formset = DetallePedidoFormSet(datos, instance=pedido)
                if not form.is_valid() or not formset.is_valid():
                    raise AssertionError((form.errors, formset.errors))
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '8s'")
                    ServicioPedidos().guardar(form, formset, Usuario.objects.get(pk=self.cajero.pk))
                    retenido.set()
                    if not liberar.wait(timeout=10):
                        raise TimeoutError('No se liberó el guardado de prueba.')
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            guardado = ejecutor.submit(guardar_pedido)
            try:
                self.assertTrue(retenido.wait(timeout=6))
                cobro = ejecutor.submit(self.cobrar_en_conexion, None, iniciado, pid)
                self.assertTrue(iniciado.wait(timeout=6))
                self.esperar_bloqueo(pid[0])
            finally:
                liberar.set()
            guardado.result(timeout=12)
            self.assertEqual(cobro.result(timeout=12), 'pedidos_pendientes')
        self.assertEqual(Pedido.objects.en_curso().count(), 1)
        self.assertFalse(Cobro.objects.exists())
        self.atencion.refresh_from_db()
        self.assertTrue(self.atencion.esta_abierta)
