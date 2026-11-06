from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import CategoriaProducto, Cliente, Mesa, Producto

Usuario = get_user_model()


def usuario_con_permisos(username='gerente', todos=True, codenames=()):
    u = Usuario.objects.create_user(username, password='Clave12345!')
    perms = Permission.objects.filter(content_type__app_label='administracion')
    if not todos:
        perms = perms.filter(codename__in=codenames)
    u.user_permissions.set(perms)
    return u


# ------------------------------------------------------------ Modelos

class MesaModeloTests(TestCase):
    def test_numero_unico(self):
        Mesa.objects.create(numero=1, capacidad=4)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Mesa.objects.create(numero=1, capacidad=2)

    def test_nace_disponible(self):
        self.assertEqual(Mesa.objects.create(numero=2, capacidad=4).estado, Mesa.Estado.DISPONIBLE)

    def test_deshabilitar_y_habilitar(self):
        m = Mesa.objects.create(numero=3, capacidad=4)
        m.deshabilitar()
        m.refresh_from_db()
        self.assertFalse(m.activo)
        self.assertEqual(m.estado, Mesa.Estado.DESHABILITADA)
        self.assertNotIn(m, Mesa.objects.disponibles())
        m.habilitar()
        self.assertIn(m, Mesa.objects.disponibles())

    def test_no_se_deshabilita_mesa_ocupada(self):
        m = Mesa.objects.create(numero=4, capacidad=4, estado=Mesa.Estado.OCUPADA)
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


# -------------------------------------------------------------- Vistas

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
        self.assertRedirects(r, reverse('administracion:lista_mesas'))
        m = Mesa.objects.get(numero=5)
        self.assertEqual(m.estado, Mesa.Estado.DISPONIBLE)

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

    def test_deshabilitar_pide_confirmacion(self):                    # CU-19
        m = Mesa.objects.create(numero=1, capacidad=2)
        url = reverse('administracion:deshabilitar_mesa', args=[m.pk])
        self.assertContains(self.client.get(url), 'Deshabilitar mesa')
        m.refresh_from_db()
        self.assertTrue(m.activo)                                     # GET no cambia nada (2a)
        self.client.post(url)
        m.refresh_from_db()
        self.assertEqual(m.estado, Mesa.Estado.DESHABILITADA)

    def test_deshabilitar_mesa_ocupada_se_rechaza(self):
        m = Mesa.objects.create(numero=1, capacidad=2, estado=Mesa.Estado.OCUPADA)
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
        self.assertEqual(m.estado, Mesa.Estado.DISPONIBLE)


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


class ClienteVistasTests(TestCase):
    def setUp(self):
        usuario_con_permisos()
        self.client.login(username='gerente', password='Clave12345!')

    def test_lista_vacia(self):                                       # CU-24 camino 1a
        self.assertContains(self.client.get(reverse('administracion:lista_clientes')),
                            'No existen clientes registrados')

    def test_registrar_y_buscar(self):                                # CU-04 / CU-24
        self.client.post(reverse('administracion:crear_cliente'), {'nombre': '  Ana   López ', 'telefono': '7000-0000'})
        self.client.post(reverse('administracion:crear_cliente'), {'nombre': 'Luis', 'telefono': '7111-1111'})
        self.assertEqual(Cliente.objects.get(telefono='7000-0000').nombre, 'Ana López')
        r = self.client.get(reverse('administracion:lista_clientes'), {'q': '7111'})
        self.assertEqual([c.nombre for c in r.context['clientes']], ['Luis'])

    def test_telefono_duplicado(self):
        Cliente.objects.create(nombre='Ana', telefono='7000-0000')
        r = self.client.post(reverse('administracion:crear_cliente'), {'nombre': 'Otra', 'telefono': '7000-0000'})
        self.assertContains(r, 'Ya existe un cliente con ese teléfono')

    def test_modificar_cliente(self):                                 # CU-25
        c = Cliente.objects.create(nombre='Ana', telefono='7000-0000')
        self.client.post(reverse('administracion:editar_cliente', args=[c.pk]),
                         {'nombre': 'Ana María', 'telefono': '7000-0000'})
        c.refresh_from_db()
        self.assertEqual(c.nombre, 'Ana María')

    def test_modificar_invalido_conserva_datos(self):                 # CU-25 camino 3a
        c = Cliente.objects.create(nombre='Ana', telefono='7000-0000')
        self.client.post(reverse('administracion:editar_cliente', args=[c.pk]),
                         {'nombre': 'Ana', 'telefono': 'xx'})
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
