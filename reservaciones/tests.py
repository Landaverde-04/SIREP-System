from datetime import datetime, timedelta

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from administracion.models import Cliente, Mesa, normalizar_nombre, normalizar_telefono
from seguridad.models import Usuario
from .models import Atencion, Reservacion
from .servicios import (
    MesaNoDisponibleError, ReglaNegocioError, ServicioDisponibilidad, ServicioIngreso,
    ServicioReservaciones,
)

H2 = timedelta(hours=2)


def momento(dias=1, hora=19, minuto=0):
    """Fecha y hora local consciente de zona, relativa a hoy."""
    fecha = timezone.localdate() + timedelta(days=dias)
    return timezone.make_aware(datetime.combine(fecha, datetime.min.time()).replace(hour=hora, minute=minuto))


class DatosBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mesa2 = Mesa.objects.create(numero=1, capacidad=2, ubicacion='Ventana')
        cls.mesa4 = Mesa.objects.create(numero=2, capacidad=4, ubicacion='Salón')
        cls.mesa6 = Mesa.objects.create(numero=3, capacidad=6, ubicacion='Terraza')
        cls.cliente = Cliente.objects.create(nombre='Ana López', telefono='7777-8888')
        cls.otro_cliente = Cliente.objects.create(nombre='Luis Pérez', telefono='6111-2222')

    def setUp(self):
        self.reservas = ServicioReservaciones()
        self.disponibilidad = ServicioDisponibilidad()


class TelefonoTests(TestCase):
    def test_normaliza_formatos_aceptados(self):
        for valor in ['77778888', '7777-8888', '7777 8888', '+503 7777-8888']:
            self.assertEqual(normalizar_telefono(valor), '7777-8888')

    def test_rechaza_formato_invalido(self):
        for valor in ['', '1234', '5777-8888', '7777-88889', 'abc']:
            with self.assertRaises(ValidationError):
                normalizar_telefono(valor)


class NombreTests(TestCase):
    def test_mayuscula_inicial_y_conectores(self):
        casos = {
            'ana lópez': 'Ana López',
            '  JOSÉ   DE LA   o ': 'José de la O',
            'maría-josé del cid': 'María-José del Cid',
            'de la cruz': 'De la Cruz',
        }
        for entrada, esperado in casos.items():
            self.assertEqual(normalizar_nombre(entrada), esperado)

    def test_cliente_se_guarda_normalizado(self):
        cliente = Cliente.objects.create(nombre='pedro gómez', telefono='7111-2222')
        self.assertEqual(cliente.nombre, 'Pedro Gómez')


class DisponibilidadTests(DatosBase):
    """CU-02 / HU-02."""

    def test_filtra_por_capacidad_y_ordena_de_menor_a_mayor(self):
        mesas = list(self.disponibilidad.mesas_disponibles(momento(), H2, 3))
        self.assertEqual(mesas, [self.mesa4, self.mesa6])

    def test_excluye_mesa_con_reservacion_que_se_cruza(self):
        self.reservas.registrar(self.cliente, self.mesa4, momento(hora=19), H2, 4)
        # 20:00-22:00 se cruza con 19:00-21:00
        self.assertNotIn(self.mesa4, self.disponibilidad.mesas_disponibles(momento(hora=20), H2, 2))
        # 21:00-23:00 empieza justo cuando termina la otra: no se cruza
        self.assertIn(self.mesa4, self.disponibilidad.mesas_disponibles(momento(hora=21), H2, 2))

    def test_reservacion_cancelada_no_compromete_la_mesa(self):
        r = self.reservas.registrar(self.cliente, self.mesa4, momento(), H2, 4)
        self.reservas.cancelar(r, 'Cambio de planes')
        self.assertIn(self.mesa4, self.disponibilidad.mesas_disponibles(momento(), H2, 4))

    def test_excluye_mesa_deshabilitada(self):
        Mesa.objects.filter(pk=self.mesa6.pk).update(activo=False)
        self.assertNotIn(self.mesa6, self.disponibilidad.mesas_disponibles(momento(), H2, 2))

    def test_atencion_abierta_ocupa_la_mesa(self):
        ServicioIngreso().registrar_sin_reservacion(self.mesa4, 3)
        ahora = timezone.now()
        self.assertNotIn(self.mesa4, self.disponibilidad.mesas_disponibles(ahora, H2, 2))
        # Más tarde, cuando se espera que haya terminado, sí puede reservarse.
        self.assertIn(self.mesa4, self.disponibilidad.mesas_disponibles(ahora + timedelta(hours=3), H2, 2))

    def test_estado_mesas_coincide_con_mesas_disponibles(self):
        self.reservas.registrar(self.cliente, self.mesa4, momento(hora=19), H2, 2)
        estados = {e.mesa: e.estado for e in self.disponibilidad.estado_mesas(momento(hora=20), H2, 3)}
        self.assertEqual(estados, {self.mesa2: 'pequena', self.mesa4: 'reservada', self.mesa6: 'libre'})
        libres = [m for m, estado in estados.items() if estado == 'libre']
        self.assertEqual(libres, list(self.disponibilidad.mesas_disponibles(momento(hora=20), H2, 3)))
        # Sin cantidad de personas no se descarta ninguna por capacidad.
        sin_personas = {e.mesa: e.estado for e in self.disponibilidad.estado_mesas(momento(hora=20), H2)}
        self.assertEqual(sin_personas[self.mesa2], 'libre')

    def test_rechaza_fecha_pasada_y_duracion_mayor_a_cuatro_horas(self):
        with self.assertRaisesMessage(ReglaNegocioError, 'fecha y hora futuras'):
            self.disponibilidad.validar_periodo(timezone.now() - timedelta(hours=1), H2)
        with self.assertRaisesMessage(ValidationError, 'cuatro horas'):
            self.disponibilidad.validar_periodo(momento(), timedelta(hours=4, minutes=30))


class RegistrarReservacionTests(DatosBase):
    """CU-01 / HU-01."""

    def test_registra_programada_con_codigo_unico(self):
        r = self.reservas.registrar(self.cliente, self.mesa4, momento(), H2, 3)
        self.assertEqual(r.estado, Reservacion.Estado.PROGRAMADA)
        self.assertRegex(r.codigo, r'^R-[A-Z2-9]{5}$')
        otra = self.reservas.registrar(self.otro_cliente, self.mesa6, momento(), H2, 3)
        self.assertNotEqual(r.codigo, otra.codigo)

    def test_no_permite_dos_reservaciones_superpuestas(self):
        """RN-01: segundo anfitrión que intenta la misma mesa (CU-01 8a)."""
        self.reservas.registrar(self.cliente, self.mesa4, momento(hora=19), H2, 2)
        with self.assertRaisesMessage(MesaNoDisponibleError, 'ya está reservada'):
            self.reservas.registrar(self.otro_cliente, self.mesa4, momento(hora=20, minuto=30), H2, 2)
        self.assertEqual(Reservacion.objects.count(), 1)

    def test_rechaza_mesa_sin_capacidad(self):
        """RN-02."""
        with self.assertRaisesMessage(MesaNoDisponibleError, 'admite 2 personas'):
            self.reservas.registrar(self.cliente, self.mesa2, momento(), H2, 3)

    def test_rechaza_fecha_pasada(self):
        with self.assertRaises(ReglaNegocioError):
            self.reservas.registrar(self.cliente, self.mesa4, timezone.now() - timedelta(minutes=30), H2, 2)


class ModificarCancelarTests(DatosBase):
    """CU-05 y CU-06 / HU-06 y HU-07."""

    def test_modificar_conserva_codigo_y_libera_periodo_anterior(self):
        r = self.reservas.registrar(self.cliente, self.mesa4, momento(hora=19), H2, 2)
        codigo = r.codigo
        r = self.reservas.modificar(r, self.mesa4, momento(hora=20), H2, 4)
        self.assertEqual((r.codigo, r.estado, r.cantidad_personas), (codigo, 'PROGRAMADA', 4))
        # Puede modificarse sobre su propio período sin chocar consigo misma.
        self.reservas.modificar(r, self.mesa4, momento(hora=20, minuto=30), H2, 4)
        # El período anterior 19:00-20:30 ya no está comprometido.
        self.assertIn(self.mesa4, self.disponibilidad.mesas_disponibles(momento(hora=18), H2, 2))

    def test_modificar_a_mesa_ocupada_se_rechaza(self):
        self.reservas.registrar(self.otro_cliente, self.mesa6, momento(hora=20), H2, 5)
        r = self.reservas.registrar(self.cliente, self.mesa4, momento(hora=20), H2, 4)
        with self.assertRaises(MesaNoDisponibleError):
            self.reservas.modificar(r, self.mesa6, momento(hora=20), H2, 4)
        r.refresh_from_db()
        self.assertEqual(r.mesa, self.mesa4)

    def test_cancelar_guarda_motivo_y_no_permite_repetir(self):
        r = self.reservas.registrar(self.cliente, self.mesa4, momento(), H2, 2)
        self.reservas.cancelar(r, 'El cliente avisó por teléfono')
        r.refresh_from_db()
        self.assertEqual(r.estado, Reservacion.Estado.CANCELADA)
        self.assertEqual(r.motivo_cancelacion, 'El cliente avisó por teléfono')
        with self.assertRaisesMessage(ValidationError, 'Solo pueden cancelarse reservaciones programadas'):
            self.reservas.cancelar(r)
        with self.assertRaisesMessage(ValidationError, 'Solo pueden modificarse'):
            self.reservas.modificar(r, self.mesa4, momento(), H2, 2)

    def test_buscar_por_codigo_nombre_o_telefono(self):
        r = self.reservas.registrar(self.cliente, self.mesa4, momento(), H2, 2)
        for texto in [r.codigo, r.codigo.lower(), 'ana', '77778888', '7777-8888']:
            self.assertIn(r, Reservacion.objects.buscar(texto), texto)
        self.assertFalse(Reservacion.objects.buscar('Pedro').exists())


class IngresoTests(DatosBase):
    """CU-03 / HU-03 y HU-04."""

    def reservacion_de_hoy(self, mesa=None, personas=3):
        inicio = timezone.now() + timedelta(minutes=10)
        return self.reservas.registrar(self.cliente, mesa or self.mesa4, inicio, H2, personas)

    def test_ingreso_con_reservacion_abre_atencion(self):
        r = self.reservacion_de_hoy()
        atencion = ServicioIngreso().registrar_con_reservacion(r, 3)
        r.refresh_from_db()
        self.assertEqual(r.estado, Reservacion.Estado.ATENDIDA)
        self.assertTrue(atencion.esta_abierta)
        self.assertEqual((atencion.mesa, atencion.cliente, atencion.reservacion), (self.mesa4, self.cliente, r))
        self.assertTrue(self.mesa4.esta_ocupada)
        self.assertEqual(Atencion.abierta_de(self.mesa4), atencion)

    def test_mas_personas_que_la_capacidad_exige_otra_mesa(self):
        r = self.reservacion_de_hoy(personas=4)
        servicio = ServicioIngreso()
        self.assertIn('admite 4', servicio.problema_con_mesa_reservada(r, 5))
        with self.assertRaises(MesaNoDisponibleError):
            servicio.registrar_con_reservacion(r, 5)
        atencion = servicio.registrar_con_reservacion(r, 5, mesa=self.mesa6)
        self.assertEqual(atencion.mesa, self.mesa6)

    def test_mesa_reservada_ocupada_por_atencion_anterior(self):
        r = self.reservacion_de_hoy(mesa=self.mesa6)
        # Un grupo anterior se quedó más tiempo del estimado y la mesa sigue ocupada (CU-03 6a).
        Atencion.objects.create(mesa=self.mesa6, cantidad_personas=2,
                                fecha_hora_ingreso=timezone.now() - timedelta(hours=3))
        servicio = ServicioIngreso()
        self.assertIn('sigue ocupada', servicio.problema_con_mesa_reservada(r, 3))
        with self.assertRaisesMessage(MesaNoDisponibleError, 'sigue ocupada'):
            servicio.registrar_con_reservacion(r, 3)
        self.assertEqual(servicio.registrar_con_reservacion(r, 3, mesa=self.mesa4).mesa, self.mesa4)

    def test_no_registra_ingreso_de_reservacion_de_otro_dia(self):
        r = self.reservas.registrar(self.cliente, self.mesa4, momento(dias=2), H2, 2)
        with self.assertRaisesMessage(ReglaNegocioError, 'programadas para hoy'):
            ServicioIngreso().registrar_con_reservacion(r, 2)

    def test_ingreso_sin_reservacion_y_sin_cliente(self):
        atencion = ServicioIngreso().registrar_sin_reservacion(self.mesa2, 2)
        self.assertIsNone(atencion.cliente)
        self.assertIsNone(atencion.reservacion)
        with self.assertRaisesMessage(MesaNoDisponibleError, 'atención en curso'):
            ServicioIngreso().registrar_sin_reservacion(self.mesa2, 2)

    def test_sin_reservacion_respeta_reservaciones_proximas(self):
        self.reservas.registrar(self.cliente, self.mesa4, timezone.now() + timedelta(hours=1), H2, 2)
        self.assertNotIn(self.mesa4, ServicioIngreso().mesas_para_ingreso(2))

    def test_cerrar_atencion_libera_la_mesa(self):
        atencion = ServicioIngreso().registrar_sin_reservacion(self.mesa2, 2)
        atencion.cerrar()
        self.assertFalse(self.mesa2.esta_ocupada)
        self.assertIn(self.mesa2, ServicioIngreso().mesas_para_ingreso(2))
        with self.assertRaises(ValidationError):
            atencion.cerrar()

    def test_base_de_datos_impide_dos_atenciones_abiertas(self):
        Atencion.objects.create(mesa=self.mesa2, cantidad_personas=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Atencion.objects.create(mesa=self.mesa2, cantidad_personas=1)


class VistasTests(DatosBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.anfitrion = Usuario.objects.create_user('anfitrion', password='clave-segura-123')
        codigos = ['view_reservacion', 'add_reservacion', 'change_reservacion', 'cancelar_reservacion',
                   'add_atencion', 'view_atencion', 'add_cliente']
        cls.anfitrion.user_permissions.set(Permission.objects.filter(codename__in=codigos))
        cls.sin_permisos = Usuario.objects.create_user('mesero', password='clave-segura-123')

    def setUp(self):
        super().setUp()
        self.client.force_login(self.anfitrion)

    def datos_periodo(self, **extra):
        inicio = timezone.localtime(momento(hora=19))
        datos = {'fecha': inicio.date().isoformat(), 'hora': '19:00', 'duracion_horas': '2',
                 'cantidad_personas': '3'}
        datos.update(extra)
        return datos

    def test_requiere_permiso(self):
        self.client.force_login(self.sin_permisos)
        self.assertEqual(self.client.get(reverse('reservaciones:lista_reservaciones')).status_code, 403)
        self.assertEqual(self.client.get(reverse('reservaciones:panel_ingresos')).status_code, 403)

    def test_paginas_principales_cargan(self):
        for nombre in ['lista_reservaciones', 'consultar_disponibilidad', 'crear_reservacion',
                       'panel_ingresos', 'ingreso_sin_reservacion']:
            self.assertEqual(self.client.get(reverse(f'reservaciones:{nombre}')).status_code, 200, nombre)

    def test_consultar_muestra_mesas_y_confirmar_registra(self):
        url = reverse('reservaciones:crear_reservacion')
        respuesta = self.client.post(url, self.datos_periodo(accion='consultar'))
        self.assertEqual(respuesta.context['mesas'], [self.mesa4, self.mesa6])

        respuesta = self.client.post(url, self.datos_periodo(accion='confirmar', mesa=self.mesa4.pk,
                                                             cliente=self.cliente.pk))
        reservacion = Reservacion.objects.get()
        self.assertRedirects(respuesta, reverse('reservaciones:detalle_reservacion', args=[reservacion.codigo]))
        self.assertEqual(reservacion.registrada_por, self.anfitrion)

    def test_confirmar_sin_cliente_o_con_duracion_excesiva_muestra_errores(self):
        url = reverse('reservaciones:crear_reservacion')
        respuesta = self.client.post(url, self.datos_periodo(accion='confirmar', mesa=self.mesa4.pk))
        self.assertIn('cliente', respuesta.context['form'].errors)
        respuesta = self.client.post(url, self.datos_periodo(duracion_horas='5'))
        self.assertIn('cuatro horas', str(respuesta.context['form'].errors))
        self.assertFalse(Reservacion.objects.exists())

    def test_mesa_tomada_mientras_tanto_muestra_disponibilidad_actualizada(self):
        url = reverse('reservaciones:crear_reservacion')
        self.reservas.registrar(self.otro_cliente, self.mesa4, momento(hora=19), H2, 2)
        respuesta = self.client.post(url, self.datos_periodo(accion='confirmar', mesa=self.mesa4.pk,
                                                             cliente=self.cliente.pk))
        self.assertIn('ya está reservada', str(respuesta.context['form'].errors['mesa']))
        self.assertEqual(respuesta.context['mesas'], [self.mesa6])

    def test_mapa_de_disponibilidad(self):
        url = reverse('reservaciones:consultar_disponibilidad')
        self.assertEqual(self.client.get(url).context['total'], 3)  # sin parámetros: ahora, todas las mesas
        respuesta = self.client.get(url, self.datos_periodo(cantidad_personas=''))
        self.assertEqual(respuesta.context['conteo']['libre'], 3)
        self.reservas.registrar(self.cliente, self.mesa4, momento(hora=19), H2, 2)
        respuesta = self.client.get(url, self.datos_periodo(cantidad_personas='3'))
        self.assertEqual(respuesta.context['conteo'], {'libre': 1, 'reservada': 1, 'ocupada': 0, 'pequena': 1})
        self.assertContains(respuesta, 'agenda-bloque tipo-reservacion')

    def test_cancelar_desde_la_vista(self):
        r = self.reservas.registrar(self.cliente, self.mesa4, momento(), H2, 2)
        self.client.post(reverse('reservaciones:cancelar_reservacion', args=[r.codigo]), {'motivo': 'Lluvia'})
        r.refresh_from_db()
        self.assertEqual((r.estado, r.motivo_cancelacion), ('CANCELADA', 'Lluvia'))

    def test_registrar_cliente_rapido_detecta_duplicado(self):
        url = reverse('reservaciones:registrar_cliente')
        respuesta = self.client.post(url, {'nombre': 'maría  pérez', 'telefono': '22223333'})
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()['cliente']['nombre'], 'María Pérez')
        self.assertEqual(respuesta.json()['cliente']['telefono'], '2222-3333')
        respuesta = self.client.post(url, {'nombre': 'Otra María', 'telefono': '2222 3333'})
        self.assertTrue(respuesta.json()['existe'])
        respuesta = self.client.post(url, {'nombre': '', 'telefono': '123'})
        self.assertEqual(set(respuesta.json()['errores']), {'nombre', 'telefono'})
        self.assertEqual(Cliente.objects.filter(telefono='2222-3333').count(), 1)

    def test_ingreso_sin_reservacion_desde_la_vista(self):
        url = reverse('reservaciones:ingreso_sin_reservacion')
        respuesta = self.client.post(url, {'cantidad_personas': 2, 'accion': 'confirmar'})
        self.assertIn('mesa', respuesta.context['form'].errors)
        self.client.post(url, {'cantidad_personas': 2, 'accion': 'confirmar', 'mesa': self.mesa2.pk})
        self.assertTrue(self.mesa2.esta_ocupada)
