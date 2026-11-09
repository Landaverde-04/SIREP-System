# SIREP

Sistema de Reservaciones y Pedidos para un Restaurante.
Proyecto académico de Tecnología Orientada a Objetos TOO115, Universidad de El Salvador.

SIREP está dirigido al personal del restaurante para gestionar reservaciones,
el ingreso de clientes, pedidos y cobros, junto con las mesas y el menú.

## Estado actual

La base proviene de la plantilla Django de Binary Duo. El proyecto interno se
llama `sirep` y las pantallas comunes ya utilizan la identidad de SIREP.

Las aplicaciones de negocio conservan la estructura estándar de Django e incluyen
una plantilla de ejemplo en `templates/<app>/ejemplo.html`, junto con sus archivos
`static/<app>/css/ejemplo.css` y `static/<app>/js/ejemplo.js`, como guía de estructura.
Los ejemplos no están conectados a vistas ni rutas. Todavía no contienen modelos,
formularios ni reglas del negocio.
Cada responsable desarrollará su módulo. La seguridad heredada queda pendiente
de los ajustes específicos de SIREP.

## Organización

| Carpeta | Responsabilidad |
|---|---|
| `sirep/` | Configuración general del proyecto Django |
| `core/` | Interfaz común, inicio y modelo abstracto heredado |
| `seguridad/` | Usuarios, sesiones, grupos y permisos heredados |
| `administracion/` | Aplicación inicial para mesas, menú y clientes |
| `reservaciones/` | Aplicación inicial para disponibilidad, reservas e ingreso |
| `pedidos/` | Pedidos por mesa, tablero de cocina y entrega |
| `cobro/` | Aplicación inicial para consumo y cobro |

## Módulo de reservaciones

Implementa CU-01 a CU-07: consulta de disponibilidad, registro, modificación,
cancelación y búsqueda de reservaciones, registro rápido de clientes e ingreso
del cliente con o sin reservación, que abre la `Atencion` de la mesa.

- Reglas de negocio en `reservaciones/servicios.py` (`ServicioDisponibilidad`,
  `ServicioReservaciones`, `ServicioIngreso`) y en los modelos.
- `administracion.Mesa` y `administracion.Cliente` contienen los datos mínimos
  que necesita el módulo; administración completará sus pantallas.
- `reservaciones.Atencion` representa la visita a una mesa. Pedidos y cobro se
  asocian a ella; cobro la cierra con `atencion.cerrar()`, lo que libera la mesa.
  `Atencion.abierta_de(mesa)` devuelve la atención en curso de una mesa.

La consulta de disponibilidad muestra un mapa de mesas por ubicación (libre,
reservada, ocupada o sin capacidad) y la agenda del día de cada mesa. La
cantidad de personas es opcional en esa consulta.

Gestión en administración (`/administracion/`): mesas (CU-16 a CU-19) y
clientes con su historial (CU-24 y CU-25).

Datos de prueba (mesas, clientes y roles «Anfitrión» y «Gerente»):

```
python manage.py migrate
python manage.py datos_demo_reservaciones
```

Pruebas automáticas: `python manage.py test reservaciones`.

## Módulo de pedidos

Toma de pedidos por mesa, preparación en cocina y entrega (`/pedidos/`).

- Un pedido pertenece a la `Atencion` abierta de su mesa (RN-05): solo se ofrecen
  mesas ocupadas y, si la atención se cierra mientras se llena el formulario,
  el guardado se rechaza. Los pedidos de visitas distintas nunca se mezclan.
- Solo se piden productos habilitados y disponibles (RN-06). El precio se copia
  del menú a cada línea (`DetallePedido.precio_unitario`), así que cambiar el
  precio después no altera pedidos ya tomados ni su cobro.
- Estados: Pendiente → En preparación → Listo → Entregado; Cancelado mientras no
  esté listo. Solo un pedido pendiente puede editarse. Las transiciones viven en
  `Pedido.TRANSICIONES` y se aplican con bloqueo de fila en `pedidos/servicios.py`.
- Tablero de cocina (`/pedidos/cocina/`): pedidos en curso de atenciones abiertas,
  los más antiguos primero, con botón de avance y recarga cada 30 segundos.
- Permisos: `view_pedido`, `add_pedido`, `change_pedido` y el propio
  `cambiar_estado_pedido`.
- Para cobro: `Pedido.objects.de_atencion(a).facturables()` excluye los cancelados y
  `.con_monto()` anota el total de cada pedido.

Datos de prueba (menú y roles «Mesero» y «Cocina»):

```
python manage.py datos_demo_pedidos
```

Para tomar un pedido hace falta una mesa con atención abierta (registre un ingreso
en `/reservaciones/ingresos/`). Pruebas automáticas: `python manage.py test pedidos`.

## Tecnologías

- Python 3.12 y Django; versiones de dependencias en `requirements.txt`.
- Plantillas de Django, JavaScript y Bootstrap 5.
- PostgreSQL 18 local, Psycopg y variables de entorno mediante `django-environ`.

## Instalación y ejecución

Cada integrante crea su propio `venv`, `.env` y base PostgreSQL local.
La conexión se configura con `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`
y `DB_PORT`. Los nombres acordados son `sirep_db` y `sirep_user`, con una
contraseña propia en cada computadora. Al repositorio se
suben `.env.example`, `requirements.txt`, las migraciones y el código.

## Convenciones

La definición de modelos compartidos y las reglas de cada módulo se acordarán
antes de su implementación.
