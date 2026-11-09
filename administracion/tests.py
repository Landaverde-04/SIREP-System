from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from reservaciones.servicios import ServicioIngreso, ServicioReservaciones
from seguridad.models import Usuario
from .models import CategoriaProducto, Cliente, Mesa, Producto


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


def usuario_con_permisos(username='gerente', todos=True, codenames=()):
    u = Usuario.objects.create_user(username, password='Clave12345!')
    perms = Permission.objects.filter(content_type__app_label='administracion')
    if not todos:
        perms = perms.filter(codename__in=codenames)
    u.user_permissions.set(perms)
    return u


class MesaModeloTests(TestCase):
    def test_numero_unico(self):
        Mesa.objects.create(numero=1, capacidad=4)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Mesa.objects.create(numero=1, capacidad=2)

    def test_nace_disponible(self):
        self.assertEqual(Mesa.objects.create(numero=2, capacidad=4).estado, 'Disponible')

    def test_deshabilitar_y_habilitar(self):
        m = Mesa.objects.create(numero=3, capacidad=4)
        m.deshabilitar()
        m.refresh_from_db()
        self.assertFalse(m.activo)
        self.assertEqual(m.estado, 'Deshabilitada')
        self.assertNotIn(m, Mesa.objects.filter(activo=True))
        m.habilitar()
        self.assertIn(m, Mesa.objects.filter(activo=True))

    def test_no_se_deshabilita_mesa_ocupada(self):
        m = Mesa.objects.create(numero=4, capacidad=4)
        ServicioIngreso().registrar_sin_reservacion(m, 2)
        with self.assertRaises(ValidationError):
            m.deshabilitar()
        m.refresh_from_db()
        self.assertTrue(m.activo)


class ProductoModeloTests(TestCase):
    def setUp(self):
        self.cat = CategoriaProducto.objects.create(nombre='Bebidas')

    def test_ofertables_exige_habilitado_y_disponible(self):
        a = Producto.objects.create(nombre='Café', precio=Decimal('1.50'), categoria=self.cat)
        b = Producto.objects.create(nombre='Té', precio=Decimal('1.25'), categoria=self.cat, disponible=False)
        c = Producto.objects.create(nombre='Jugo', precio=Decimal('2.00'), categoria=self.cat)
        c.deshabilitar()
        self.assertQuerySetEqual(Producto.objects.ofertables(), [a])
        self.assertIn(b, Producto.objects.habilitados())

    def test_alternar_disponibilidad(self):
        p = Producto.objects.create(nombre='Café', precio=Decimal('1.50'), categoria=self.cat)
        p.alternar_disponibilidad()
        self.assertFalse(p.disponible)
        p.alternar_disponibilidad()
        self.assertTrue(p.disponible)

    def test_nombre_unico_sin_importar_mayusculas(self):
        # ASCII a propósito: lower() de SQLite no maneja acentos; PostgreSQL sí.
        Producto.objects.create(nombre='Cafe', precio=Decimal('1.50'), categoria=self.cat)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Producto.objects.create(nombre='CAFE', precio=Decimal('2.00'), categoria=self.cat)

    def test_categoria_con_productos_no_se_borra(self):
        from django.db.models import ProtectedError
        Producto.objects.create(nombre='Café', precio=Decimal('1.50'), categoria=self.cat)
        with self.assertRaises(ProtectedError):
            self.cat.delete()


class ClienteModeloTests(TestCase):
    def test_telefono_unico_y_validado(self):
        Cliente.objects.create(nombre='Ana', telefono='7000-0000')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cliente.objects.create(nombre='Luis', telefono='7000-0000')
        with self.assertRaises(ValidationError):
            Cliente(nombre='X', telefono='abc').full_clean()


class AccesoTests(TestCase):
    def test_requiere_login(self):
        r = self.client.get(reverse('administracion:lista_mesas'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/seguridad/login/', r.url)

    def test_sin_permiso_da_403(self):
        Usuario.objects.create_user('sin', password='Clave12345!')
        self.client.login(username='sin', password='Clave12345!')
        for nombre in ('lista_mesas', 'lista_productos', 'lista_clientes', 'lista_categorias'):
            self.assertEqual(self.client.get(reverse(f'administracion:{nombre}')).status_code, 403, nombre)

    def test_solo_lectura_no_puede_crear(self):
        usuario_con_permisos('lector', todos=False, codenames=['view_mesa'])
        self.client.login(username='lector', password='Clave12345!')
        self.assertEqual(self.client.get(reverse('administracion:lista_mesas')).status_code, 200)
        self.assertEqual(self.client.get(reverse('administracion:crear_mesa')).status_code, 403)


class MesaVistasTests(TestCase):
    def setUp(self):
        usuario_con_permisos()
        self.client.login(username='gerente', password='Clave12345!')

    def test_lista_vacia(self):                                       # CU-16 camino 1a
        r = self.client.get(reverse('administracion:lista_mesas'))
        self.assertContains(r, 'No hay mesas registradas')

    def test_registrar_mesa(self):                                    # CU-17
        r = self.client.post(reverse('administracion:crear_mesa'),
                             {'numero': 5, 'capacidad': 4, 'ubicacion': 'Terraza'})
        self.assertRedirects(r, reverse('administracion:detalle_mesa', args=[Mesa.objects.get(numero=5).pk]))
        m = Mesa.objects.get(numero=5)
        self.assertEqual(m.estado, 'Disponible')

    def test_registrar_mesa_duplicada(self):                          # CU-17 camino 3a
        Mesa.objects.create(numero=5, capacidad=2)
        r = self.client.post(reverse('administracion:crear_mesa'), {'numero': 5, 'capacidad': 4})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Ya existe una mesa con ese número')
        self.assertEqual(Mesa.objects.count(), 1)

    def test_registrar_mesa_datos_invalidos(self):                    # CU-17 camino 2a
        r = self.client.post(reverse('administracion:crear_mesa'), {'numero': '', 'capacidad': 0})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Mesa.objects.count(), 0)

    def test_modificar_mesa(self):                                    # CU-18
        m = Mesa.objects.create(numero=1, capacidad=2)
        self.client.post(reverse('administracion:editar_mesa', args=[m.pk]),
                         {'numero': 1, 'capacidad': 6, 'ubicacion': 'Salón'})
        m.refresh_from_db()
        self.assertEqual((m.capacidad, m.ubicacion), (6, 'Salón'))

    def test_modificar_invalido_conserva_datos(self):                 # CU-18 camino 3a
        m = Mesa.objects.create(numero=1, capacidad=2)
        self.client.post(reverse('administracion:editar_mesa', args=[m.pk]), {'numero': 1, 'capacidad': -3})
        m.refresh_from_db()
        self.assertEqual(m.capacidad, 2)

    def test_deshabilitar_confirma_en_detalle_y_exige_post(self):                    # CU-19
        m = Mesa.objects.create(numero=1, capacidad=2)
        url = reverse('administracion:deshabilitar_mesa', args=[m.pk])
        self.assertContains(self.client.get(reverse('administracion:detalle_mesa', args=[m.pk])),
                            'Deshabilitar mesa')
        self.assertEqual(self.client.get(url).status_code, 405)
        m.refresh_from_db()
        self.assertTrue(m.activo)                                     # GET no cambia nada (2a)
        self.client.post(url)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'Deshabilitada')

    def test_deshabilitar_mesa_ocupada_se_rechaza(self):
        m = Mesa.objects.create(numero=1, capacidad=2)
        ServicioIngreso().registrar_sin_reservacion(m, 2)
        self.client.post(reverse('administracion:deshabilitar_mesa', args=[m.pk]))
        m.refresh_from_db()
        self.assertTrue(m.activo)

    def test_habilitar_solo_por_post(self):
        m = Mesa.objects.create(numero=1, capacidad=2)
        m.deshabilitar()
        url = reverse('administracion:habilitar_mesa', args=[m.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'Disponible')


class ProductoVistasTests(TestCase):
    def setUp(self):
        usuario_con_permisos()
        self.client.login(username='gerente', password='Clave12345!')
        self.cat = CategoriaProducto.objects.create(nombre='Platos fuertes')

    def datos(self, **extra):
        d = {'nombre': 'Pupusa', 'descripcion': 'Revuelta', 'precio': '0.75',
             'categoria': self.cat.pk, 'disponible': 'on'}
        d.update(extra)
        return d

    def test_registrar_producto(self):                                # CU-20
        r = self.client.post(reverse('administracion:crear_producto'), self.datos())
        self.assertRedirects(r, reverse('administracion:lista_productos'))
        self.assertEqual(Producto.objects.get().precio, Decimal('0.75'))

    def test_producto_duplicado_por_nombre(self):                     # CU-20 camino 3a
        Producto.objects.create(nombre='Pupusa', precio=1, categoria=self.cat)
        r = self.client.post(reverse('administracion:crear_producto'), self.datos(nombre='pupusa'))
        self.assertContains(r, 'Ya existe un producto con ese nombre')
        self.assertEqual(Producto.objects.count(), 1)

    def test_precio_debe_ser_positivo(self):
        r = self.client.post(reverse('administracion:crear_producto'), self.datos(precio='0'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Producto.objects.count(), 0)

    def test_no_acepta_categoria_deshabilitada(self):
        self.cat.activo = False
        self.cat.save()
        r = self.client.post(reverse('administracion:crear_producto'), self.datos())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Producto.objects.count(), 0)

    def test_modificar_producto_conserva_su_nombre(self):             # CU-21
        p = Producto.objects.create(nombre='Pupusa', precio=1, categoria=self.cat)
        r = self.client.post(reverse('administracion:editar_producto', args=[p.pk]),
                             self.datos(precio='1.10'))
        self.assertRedirects(r, reverse('administracion:detalle_producto', args=[p.pk]))
        p.refresh_from_db()
        self.assertEqual(p.precio, Decimal('1.10'))

    def test_cambiar_disponibilidad(self):                            # CU-22
        p = Producto.objects.create(nombre='Pupusa', precio=1, categoria=self.cat)
        url = reverse('administracion:cambiar_disponibilidad', args=[p.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        p.refresh_from_db()
        self.assertFalse(p.disponible)

    def test_next_externo_no_se_sigue(self):
        p = Producto.objects.create(nombre='Pupusa', precio=1, categoria=self.cat)
        r = self.client.post(reverse('administracion:cambiar_disponibilidad', args=[p.pk]),
                             {'next': 'https://malo.example/'})
        self.assertRedirects(r, reverse('administracion:lista_productos'))

    def test_deshabilitar_producto(self):                             # CU-23
        p = Producto.objects.create(nombre='Pupusa', precio=1, categoria=self.cat)
        url = reverse('administracion:deshabilitar_producto', args=[p.pk])
        self.assertContains(self.client.get(url), 'Deshabilitar producto')
        self.client.post(url)
        p.refresh_from_db()
        self.assertFalse(p.activo)
        self.assertNotIn(p, Producto.objects.ofertables())

    def test_producto_deshabilitado_no_cambia_disponibilidad(self):
        p = Producto.objects.create(nombre='Pupusa', precio=1, categoria=self.cat)
        p.deshabilitar()
        self.client.post(reverse('administracion:cambiar_disponibilidad', args=[p.pk]))
        p.refresh_from_db()
        self.assertTrue(p.disponible)

    def test_filtro_por_categoria(self):
        otra = CategoriaProducto.objects.create(nombre='Postres')
        Producto.objects.create(nombre='Pupusa', precio=1, categoria=self.cat)
        Producto.objects.create(nombre='Flan', precio=2, categoria=otra)
        r = self.client.get(reverse('administracion:lista_productos'), {'categoria': otra.pk})
        self.assertContains(r, 'Flan')
        self.assertNotContains(r, 'Pupusa')


class CategoriaVistasTests(TestCase):
    def setUp(self):
        usuario_con_permisos()
        self.client.login(username='gerente', password='Clave12345!')

    def test_crear_y_rechazar_duplicada(self):
        self.client.post(reverse('administracion:crear_categoria'), {'nombre': 'Entradas'})
        r = self.client.post(reverse('administracion:crear_categoria'), {'nombre': 'entradas'})
        self.assertContains(r, 'Ya existe una categoría con ese nombre')
        self.assertEqual(CategoriaProducto.objects.count(), 1)

    def test_alternar_estado(self):
        c = CategoriaProducto.objects.create(nombre='Entradas')
        self.client.post(reverse('administracion:alternar_categoria', args=[c.pk]))
        c.refresh_from_db()
        self.assertFalse(c.activo)
        self.client.post(reverse('administracion:alternar_categoria', args=[c.pk]))
        c.refresh_from_db()
        self.assertTrue(c.activo)


class ClienteAdicionalVistasTests(TestCase):
    def setUp(self):
        usuario_con_permisos()
        self.client.login(username='gerente', password='Clave12345!')

    def test_lista_vacia(self):                                       # CU-24 camino 1a
        self.assertContains(self.client.get(reverse('administracion:lista_clientes')),
                            'No existen clientes registrados')

    def test_registrar_y_buscar(self):                                # CU-04 / CU-24
        self.client.post(reverse('administracion:crear_cliente'), {'nombre': '  Ana   López ', 'telefono': '7000-0000', 'activo': 'on'})
        self.client.post(reverse('administracion:crear_cliente'), {'nombre': 'Luis', 'telefono': '7111-1111', 'activo': 'on'})
        self.assertEqual(Cliente.objects.get(telefono='7000-0000').nombre, 'Ana López')
        r = self.client.get(reverse('administracion:lista_clientes'), {'q': '7111'})
        self.assertEqual([c.nombre for c in r.context['clientes']], ['Luis'])

    def test_telefono_duplicado(self):
        Cliente.objects.create(nombre='Ana', telefono='7000-0000')
        r = self.client.post(reverse('administracion:crear_cliente'), {'nombre': 'Otra', 'telefono': '7000-0000', 'activo': 'on'})
        self.assertContains(r, 'Ya existe un cliente con ese teléfono')

    def test_modificar_cliente(self):                                 # CU-25
        c = Cliente.objects.create(nombre='Ana', telefono='7000-0000')
        self.client.post(reverse('administracion:editar_cliente', args=[c.pk]),
                         {'nombre': 'Ana María', 'telefono': '7000-0000', 'activo': 'on'})
        c.refresh_from_db()
        self.assertEqual(c.nombre, 'Ana María')

    def test_modificar_invalido_conserva_datos(self):                 # CU-25 camino 3a
        c = Cliente.objects.create(nombre='Ana', telefono='7000-0000')
        self.client.post(reverse('administracion:editar_cliente', args=[c.pk]),
                         {'nombre': 'Ana', 'telefono': 'xx', 'activo': 'on'})
        c.refresh_from_db()
        self.assertEqual(c.telefono, '7000-0000')


class SidebarTests(TestCase):
    def test_gerente_ve_seccion_administracion(self):
        usuario_con_permisos()
        self.client.login(username='gerente', password='Clave12345!')
        r = self.client.get('/')
        for texto in ('Mesas', 'Menú', 'Clientes'):
            self.assertContains(r, texto)

    def test_usuario_sin_permisos_no_la_ve(self):
        Usuario.objects.create_user('sin', password='Clave12345!')
        self.client.login(username='sin', password='Clave12345!')
        self.assertNotContains(self.client.get('/'), reverse('administracion:lista_mesas'))
