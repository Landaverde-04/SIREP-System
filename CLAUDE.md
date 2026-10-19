# [COMPLETAR: Nombre del Proyecto]

> [COMPLETAR: Una línea sobre qué hace el sistema y para quién.]

> ⚠️ **Este archivo proviene de `plantilla_django` de Binary Duo.**
> Las secciones marcadas con `[COMPLETAR: ...]` deben editarse al iniciar
> un proyecto nuevo. Las secciones sin esa marca son convenciones fijas
> del equipo y normalmente no se modifican.

---

## 🎯 Objetivo del proyecto

> [COMPLETAR]
>
> Descripción del proyecto, contexto del cliente o iniciativa, y por qué se
> está construyendo. Incluir:
>
> - Tipo de proyecto: ¿demo, MVP, producción, servicio social, comercial?
> - Cliente o destinatario
> - Problema que resuelve

### Alcance

> [COMPLETAR]
>
> Lista de módulos del negocio que se van a implementar.

### Fuera de alcance

> [COMPLETAR]
>
> Lista de funcionalidades que NO se van a hacer en este proyecto.

## 🛠️ Stack tecnológico

| Componente | Elección |
|------------|----------|
| Lenguaje | Python 3.12 |
| Framework | Django (última versión estable) |
| Frontend | Templates nativos de Django + JavaScript vanilla |
| UI/CSS | Bootstrap 5 + Bootstrap Icons vía CDN (con SRI) |
| Base de datos | SQLite |
| Entorno virtual | venv |
| Dependencias | pip + requirements.txt |
| Variables de entorno | django-environ + archivo `.env` |
| Estructura de settings | Un solo `settings.py` |
| Control de versiones | Git + GitHub |

> Si este proyecto necesita cambiar algo del stack, documentar la razón en
> la sección **Decisiones técnicas propias del proyecto** abajo.

## 📁 Estructura de apps

### Apps base de la plantilla

Todos los proyectos arrancan con estas dos apps ya implementadas y
funcionales:

#### App `core`
Base técnica del sistema:
- `base.html` que todas las páginas heredan con `{% extends "core/base.html" %}`
- Layout de dashboard con sidebar lateral (`sidebar.html`)
- Vista y URL del home/dashboard
- `ModeloBase` — modelo abstracto con `fecha_creacion`, `fecha_modificacion`, `activo`
- Página de error 403 personalizada (`templates/403.html`)
- Archivos estáticos base: `estilos.css` y `main.js`

#### App `seguridad`
Gestión completa de acceso al sistema (ya funcional):

**Autenticación**
- Login (`/seguridad/login/`)
- Logout (`/seguridad/logout/`)

**Gestión de usuarios** (CRUD completo con permisos)
- Lista, detalle, crear, editar, eliminar usuarios

**Gestión de roles** (CRUD completo, usa `Group` de Django)
- Lista, crear, editar, eliminar roles
- Asignar permisos a roles
- Asignar usuarios a roles (`/seguridad/roles/<id>/usuarios/`)

**Gestión de contraseñas**
- Reseteo por administrador (`/seguridad/usuarios/<id>/resetear-password/`)
- Cambio de contraseña propia (`/seguridad/mi-perfil/cambiar-password/`)
- Forzado de cambio al siguiente login (vía middleware)

**Perfil propio**
- Pantalla "Mi Perfil" (`/seguridad/mi-perfil/`)
- Hub central del usuario para datos personales y acciones de cuenta

### Apps del negocio

> [COMPLETAR]
>
> Listar las apps específicas de este proyecto y su responsabilidad.
> Ejemplo:
>
> ```
> sistema_X/
> ├── core/                ← (ya viene de la plantilla)
> ├── seguridad/           ← (ya viene de la plantilla)
> ├── inventario/          ← productos, categorías
> └── ventas/              ← órdenes, facturación
> ```

## 👥 Equipo

> [COMPLETAR]
>
> - **Nombre 1** — rol y entorno (ej: "Kevin — Windows + WSL Ubuntu")
> - **Nombre 2** — rol y entorno
>
> División de trabajo: por features dentro de las apps, usando ramas Git
> separadas. No por apps completas.

## 📐 Convenciones del equipo

Convenciones fijas para todos los proyectos de Binary Duo.

### Idioma del código

**Español sin tildes** para todo lo que controlamos:
- Apps: `core`, `seguridad`, y las apps del negocio
- Modelos: `Producto`, `Categoria`, `Usuario`, `Rol`
- Campos: `nombre`, `precio`, `fecha_vencimiento`, `stock_minimo`
- Variables propias: `productos`, `usuario_actual`
- URLs: `/inventario/productos/`, `/seguridad/usuarios/`
- Templates: `lista_productos.html`, `detalle_categoria.html`

**Inglés** para lo de Django (no se cambia):
- ORM: `.objects.filter()`, `.save()`, `.delete()`
- Decoradores: `@login_required`, `@property`
- Tipos de campos: `CharField`, `IntegerField`, `ForeignKey`

**Interfaz de usuario**: español completo con tildes y signos correctos
("Categoría", "¿Estás seguro?").

### Naming en Python (PEP 8)

| Tipo | Convención |
|------|------------|
| Variables y funciones | `snake_case` |
| Clases | `PascalCase` |
| Constantes | `UPPER_SNAKE_CASE` |
| Archivos y módulos | `snake_case.py` |

### Estructura interna de cada app

```
nombre_app/
├── migrations/
├── templates/
│   └── nombre_app/        ← namespace para evitar colisiones
│       └── archivo.html
├── static/
│   └── nombre_app/        ← mismo namespace
│       ├── css/
│       └── js/
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── urls.py                ← creado por nosotros
├── views.py
└── forms.py               ← cuando lo necesitemos
```

El namespace dentro de `templates/` y `static/` es **obligatorio**.

### Templates

- Archivos: `snake_case.html`
- Parciales (fragmentos incluidos con `{% include %}`) **sin guion bajo**:
  `navbar.html`, `footer.html`, `sidebar.html`
- Indentación: 4 espacios
- Bloques con nombre claro: `{% block contenido %}` no `{% block c %}`

### URLs

- Todas en minúsculas
- Separadas por guiones medios: `/lista-productos/`
- Plurales para listados: `/productos/`
- Singulares con ID para detalle: `/producto/<id>/`
- Acciones explícitas: `/producto/<id>/editar/`, `/producto/<id>/eliminar/`
- Cada app define su propio `urls.py` con `app_name` para namespace

### Mensajes de commit

Formato: `tipo: descripción corta en español`, modo imperativo.

Prefijos: `feat`, `fix`, `docs`, `refactor`, `style`, `test`, `chore`.

## ✅ Estado del proyecto

> [COMPLETAR]
>
> **Fase actual**: setup inicial desde plantilla.
>
> Completado:
> - [x] Setup inicial desde plantilla `plantilla_django`
> - [x] Renombrado del proyecto a `[nombre_proyecto]`
> - [x] App `core` operativa (heredada de plantilla)
> - [x] App `seguridad` operativa con todas las features (heredada de plantilla)
>
> Pendiente inmediato:
> - [ ] [feature 1]
> - [ ] [feature 2]
>
> Pendiente de mediano plazo:
> - [ ] [feature 3]
> - [ ] [feature 4]

## ⚠️ Decisiones técnicas heredadas de la plantilla

Estas decisiones vienen de `plantilla_django` y aplican a todos los
proyectos del equipo. **No las contradigas ni "mejores" sin discutirlo
con el equipo primero.**

### Django con templates nativos, NO Django REST Framework + React

**Decisión**: usar Django con templates server-side y JavaScript vanilla.

**Por qué**:
- El equipo prioriza dominar fundamentos de Django antes de meterle complejidad de SPAs
- Menos tecnologías = menos puntos de falla = más velocidad
- Migración a React posible después sin perder los modelos ni la lógica

**No proponer migración a DRF + React** salvo que el equipo lo pida.

### SQLite, NO PostgreSQL (por defecto)

**Decisión**: usar la base de datos por defecto de Django.

**Por qué**:
- Cero configuración entre máquinas distintas
- Portabilidad del archivo `.sqlite3`
- Migración a PostgreSQL toma ~10 minutos cuando se necesite

### venv + requirements.txt, NO Poetry ni uv

**Decisión**: usar el manejador estándar de Python.

### Un solo `settings.py`, NO separación por entornos

**Decisión**: un único archivo de configuración.

**Por qué**:
- Las diferencias entre entornos se resuelven con variables de entorno
- Si el proyecto crece, separarlo después es directo

### Idioma del código: español sin tildes

**No traducir código existente al inglés** "para mejorar".

### Modelos abstractos en `core`

**Decisión**: `core` define `ModeloBase` con campos comunes
(`fecha_creacion`, `fecha_modificacion`, `activo`) que todos los modelos
del sistema heredan.

**Cualquier modelo nuevo debe heredar de `ModeloBase`.**

```python
from core.models import ModeloBase

class Producto(ModeloBase):
    nombre = models.CharField(max_length=200)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
```

### Excepción: Usuario extiende AbstractUser, NO ModeloBase

**Decisión**: `seguridad.Usuario` hereda de
`django.contrib.auth.models.AbstractUser` únicamente.

**Por qué**:
- `AbstractUser` ya provee `is_active`, `date_joined`, `last_login`
- Mezclar ambas clases genera conflictos en la herencia de Django

### Roles = Groups de Django

**Decisión**: usar `django.contrib.auth.models.Group` como sistema de roles.

**Por qué**:
- Django ya tiene un sistema de grupos y permisos integrado y probado
- Evita duplicar funcionalidad
- Se muestra como "Roles" en la interfaz, pero en el código es `Group`

### Modelo Usuario tiene flag `debe_cambiar_password`

**Decisión**: el modelo `Usuario` incluye un campo
`debe_cambiar_password` (BooleanField, default False) que se pone en
True cuando un admin resetea la contraseña.

**Por qué**:
- Forzar al usuario a establecer su propia contraseña después del reseteo
- Evitar que el admin conozca la contraseña final del usuario

### Middleware ForzarCambioPasswordMiddleware

**Decisión**: existe un middleware en `seguridad/middleware.py` que
intercepta cada request. Si el usuario está logueado y tiene
`debe_cambiar_password=True`, lo redirige a la vista de cambio de
contraseña.

**Excepciones permitidas** (no redirige):
- URL de cambio de contraseña (sino loop)
- URL de logout (para que pueda salir si quiere)
- `/static/` (archivos estáticos)
- `/admin/` (Django admin)

**Registrado en `settings.py`** después de
`AuthenticationMiddleware`. No mover de posición.

### Pantalla "Mi Perfil" como hub del usuario

**Decisión**: `/seguridad/mi-perfil/` es el punto central para que el
usuario vea sus datos y acceda a acciones relacionadas con su cuenta
(cambio de contraseña; foto de perfil, preferencias, sesiones activas
en el futuro).

**No agregar opciones de cuenta directamente al sidebar** — todo lo
relacionado a la cuenta del usuario va dentro de "Mi Perfil".

### Bootstrap 5 + Bootstrap Icons vía CDN (con SRI)

**Decisión**: cargar Bootstrap 5 y Bootstrap Icons desde CDN en
`base.html`, con atributo `integrity` para Subresource Integrity (SRI).

**Por qué CDN**:
- Cero dependencias extra en `requirements.txt`
- Sin paso de compilación

**Por qué SRI**:
- Verifica que el navegador descarga el archivo exacto y no una versión
  modificada por un atacante en la red

**Para producción en red interna sin internet**: descargar los archivos
y servirlos como estáticos.

### Layout de dashboard con sidebar lateral

**Decisión**: navegación principal en sidebar lateral izquierdo
(`core/templates/core/sidebar.html`), no en barra superior. Sin footer.

### Herencia de templates desde `core/base.html`

**No crear páginas HTML completas sin extender de `base.html`.**

### Parciales sin guion bajo

**Decisión**: archivos parciales sin guion bajo al inicio.
`navbar.html` en lugar de `_navbar.html`.

### Namespace en URLs con `app_name`

**Decisión**: cada `urls.py` de app define `app_name` para usar
namespaces. Se referencia como `{% url 'core:home' %}`,
`{% url 'seguridad:login' %}`, etc.

### Protección de vistas: doble decorador obligatorio

**Decisión**: todas las vistas que requieren autenticación llevan dos
decoradores en este orden:

```python
@login_required
@permission_required('app.permiso_correspondiente', raise_exception=True)
def mi_vista(request):
    ...
```

**Por qué**:
- `@login_required` redirige al login si no hay sesión
- `@permission_required` con `raise_exception=True` lanza 403 (no redirige) si no tiene el permiso específico
- Combinados: nunca hay vistas accesibles a usuarios no autenticados ni a usuarios sin permiso

### Permisos filtrados por apps del negocio

**Decisión**: en el formulario de roles, los permisos se muestran
filtrados solo por apps relevantes al negocio (no se muestran permisos
internos de Django como `contenttypes`, `sessions`, etc.).

**Implementación**: helper `_permisos_agrupados()` en
`seguridad/views.py`.

### Modales controlados con JS vanilla

**Decisión**: los modales (confirmaciones de eliminar, etc.) se
implementan con JavaScript vanilla, sin depender del JS de Bootstrap.

**Por qué**: control total sobre comportamiento sin acoplarse al
framework de UI.

## 📌 Decisiones técnicas propias del proyecto

> [COMPLETAR — opcional]
>
> Si este proyecto toma decisiones específicas que se desvían o complementan
> las de la plantilla, documentarlas aquí con el mismo formato:
>
> ### [Título de la decisión]
> **Decisión**: ...
> **Por qué**: ...
> **Implicación**: ...

## 🚫 Lo que Claude NO debe hacer

- **No proponer migraciones de stack** (a DRF, React, PostgreSQL, Poetry,
  etc.) sin que el equipo lo pida
- **No traducir código** entre español e inglés sin que se solicite
- **No crear apps adicionales** sin discutirlo
- **No usar características avanzadas** (señales complejas, middleware
  custom adicional, etc.) sin justificación clara
- **No instalar librerías** sin que el equipo lo apruebe primero
- **No hacer commit del `.env`** ni proponer guardar credenciales en código
- **No proponer separar `settings.py`** por entornos
- **No reescribir código existente** "para que esté mejor" sin que se pida
- **No asumir que algo está instalado** — siempre verificar primero
- **No saltarse pasos en explicaciones**: el equipo aprende
- **No usar guion bajo** en nombres de archivos HTML/CSS/JS parciales
- **No modificar el modelo Usuario** para que herede de `ModeloBase` —
  hereda solo de `AbstractUser`
- **No remover el middleware `ForzarCambioPasswordMiddleware`** ni
  cambiarlo de posición en `MIDDLEWARE`
- **No saltarse la doble protección con decoradores** en vistas — siempre
  `@login_required` + `@permission_required`

## 📚 Documentación adicional

> [COMPLETAR]
>
> Enlace al espacio de Notion del proyecto donde vive la documentación
> extendida:
>
> **Centro de Documentos Binary Duo → [Nombre del proyecto]**

Para entender la plantilla base de la cual nació este proyecto, consultar
la sección **"Plantilla Django Binary Duo"** en el Centro de Documentos.

## 🔄 Mantenimiento de este archivo

**Regla**: cada vez que se complete algo o se tome una decisión técnica
nueva, actualizar este archivo en el mismo commit que el cambio. La
documentación es un deliverable vivo.
