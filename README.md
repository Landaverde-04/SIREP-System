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
- SQLite y variables de entorno mediante `django-environ`.

## Instalación en Windows PowerShell

Ejecutar desde la raíz del repositorio:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Generar una clave y copiarla al campo `SECRET_KEY` de `.env`:

```powershell
.\venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Preparar la base local, crear la cuenta administrativa y ejecutar:

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py createsuperuser
.\venv\Scripts\python.exe manage.py runserver
```

Abrir http://127.0.0.1:8000/ en el navegador.

## Instalación en Linux o WSL

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copiar la clave generada a `SECRET_KEY` en `.env`. Luego ejecutar:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Cada integrante utiliza su propia clave y base de datos local. No subir `.env`,
el entorno virtual ni archivos `.sqlite3` al repositorio.

## Convenciones

La definición de modelos compartidos y las reglas de cada módulo se acordarán
antes de su implementación.
