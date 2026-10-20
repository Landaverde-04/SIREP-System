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
| `pedidos/` | Aplicación inicial para pedidos, preparación y entrega |
| `cobro/` | Aplicación inicial para consumo y cobro |

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
