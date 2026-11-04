from datetime import datetime, timedelta

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from reservaciones.servicios import ServicioIngreso, ServicioReservaciones
from seguridad.models import Usuario
from .models import Cliente, Mesa


def manana(hora=19):
    fecha = timezone.localdate() + timedelta(days=1)
    return timezone.make_aware(datetime.combine(fecha, datetime.min.time()).replace(hour=hora))


class MesaTests(TestCase):
    """CU-16 a CU-19."""

    @classmethod
    def setUpTestData(cls):
        cls.mesa = Mesa.objects.create(numero=1, capacidad=6, ubicacion='Terraza')
        cls.cliente = Cliente.objects.create(nombre='Ana López', telefono='7777-8888')
        cls.gerente = Usuario.objects.create_user('gerente', password='clave-segura-123')
        cls.gerente.user_permissions.set(Permission.objects.filter(
            content_type__app_label='administracion'))

    def setUp(self):
        self.client.force_login(self.gerente)

    def test_registrar_mesa_y_rechazar_numero_repetido(self):
        url = reverse('administracion:crear_mesa')
        respuesta = self.client.post(url, {'numero': 2, 'capacidad': 4, 'ubicacion': '  salón  principal '})
        mesa = Mesa.objects.get(numero=2)
        self.assertRedirects(respuesta, reverse('administracion:detalle_mesa', args=[mesa.pk]))
        self.assertEqual(mesa.ubicacion, 'Salón principal')
        respuesta = self.client.post(url, {'numero': 2, 'capacidad': 4})
        self.assertIn('Ya existe una mesa con ese número.', respuesta.context['form'].errors['numero'])

    def test_capacidad_fuera_de_rango(self):
        respuesta = self.client.post(reverse('administracion:crear_mesa'), {'numero': 3, 'capacidad': 0})
        self.assertIn('capacidad', respuesta.context['form'].errors)

    def test_no_reduce_capacidad_por_debajo_de_sus_reservaciones(self):
        ServicioReservaciones().registrar(self.cliente, self.mesa, manana(), timedelta(hours=2), 5)
        url = reverse('administracion:editar_mesa', args=[self.mesa.pk])
        respuesta = self.client.post(url, {'numero': 1, 'capacidad': 4, 'ubicacion': 'Terraza'})
        self.assertIn('reservaciones programadas para 5 personas', str(respuesta.context['form'].errors))
        self.client.post(url, {'numero': 1, 'capacidad': 5, 'ubicacion': 'Terraza'})
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.capacidad, 5)

    def test_deshabilitar_respeta_reservaciones_y_atenciones(self):
        reservacion = ServicioReservaciones().registrar(self.cliente, self.mesa, manana(), timedelta(hours=2), 2)
        with self.assertRaisesMessage(ValidationError, 'reservación(es) programada(s)'):
            self.mesa.deshabilitar()
        ServicioReservaciones().cancelar(reservacion)
        atencion = ServicioIngreso().registrar_sin_reservacion(self.mesa, 2)
        with self.assertRaisesMessage(ValidationError, 'está ocupada'):
            self.mesa.deshabilitar()
        atencion.cerrar()
        self.client.post(reverse('administracion:deshabilitar_mesa', args=[self.mesa.pk]))
        self.mesa.refresh_from_db()
        self.assertFalse(self.mesa.activo)
        self.assertEqual(self.mesa.estado, 'Deshabilitada')
        self.client.post(reverse('administracion:habilitar_mesa', args=[self.mesa.pk]))
        self.mesa.refresh_from_db()
        self.assertTrue(self.mesa.activo)

    def test_paginas_cargan(self):
        for url in [reverse('administracion:lista_mesas'), reverse('administracion:crear_mesa'),
                    reverse('administracion:detalle_mesa', args=[self.mesa.pk]),
                    reverse('administracion:editar_mesa', args=[self.mesa.pk]),
                    reverse('administracion:lista_clientes'), reverse('administracion:crear_cliente'),
                    reverse('administracion:detalle_cliente', args=[self.cliente.pk]),
                    reverse('administracion:editar_cliente', args=[self.cliente.pk])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_requiere_permiso(self):
        self.client.force_login(Usuario.objects.create_user('mesero', password='clave-segura-123'))
        self.assertEqual(self.client.get(reverse('administracion:lista_mesas')).status_code, 403)
        self.assertEqual(self.client.get(reverse('administracion:lista_clientes')).status_code, 403)


class ClienteVistasTests(TestCase):
    """CU-24 y CU-25."""

    @classmethod
    def setUpTestData(cls):
        cls.ana = Cliente.objects.create(nombre='Ana López', telefono='7777-8888')
        cls.luis = Cliente.objects.create(nombre='Luis Pérez', telefono='6111-2222')
        cls.gerente = Usuario.objects.create_user('gerente', password='clave-segura-123')
        cls.gerente.user_permissions.set(Permission.objects.filter(content_type__app_label='administracion'))

    def setUp(self):
        self.client.force_login(self.gerente)

    def test_buscar_por_nombre_o_telefono(self):
        url = reverse('administracion:lista_clientes')
        self.assertEqual(list(self.client.get(url, {'q': 'ana'}).context['clientes']), [self.ana])
        self.assertEqual(list(self.client.get(url, {'q': '61112222'}).context['clientes']), [self.luis])

    def test_modificar_normaliza_y_evita_telefono_repetido(self):
        url = reverse('administracion:editar_cliente', args=[self.ana.pk])
        respuesta = self.client.post(url, {'nombre': 'ana maría lópez', 'telefono': '61112222', 'activo': 'on'})
        self.assertIn('Ya existe un cliente con ese teléfono', str(respuesta.context['form'].errors))
        self.client.post(url, {'nombre': 'ana maría lópez', 'telefono': '7777 9999', 'activo': 'on'})
        self.ana.refresh_from_db()
        self.assertEqual((self.ana.nombre, self.ana.telefono), ('Ana María López', '7777-9999'))
