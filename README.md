# 🐍 Plantilla Django — Binary Duo

> Plantilla base de proyectos Django para el equipo Binary Duo. Incluye
> apps `core` y `seguridad` ya implementadas, convenciones del equipo y
> archivo `CLAUDE.md` listo para que Claude Code arranque con contexto
> completo.

## 📦 Qué incluye

- **App `core`**: layout base con sidebar, plantilla `base.html`,
  modelo abstracto `ModeloBase`, archivos estáticos comunes
- **App `seguridad`**: modelo `Usuario` extendiendo `AbstractUser`,
  login/logout, CRUD de usuarios, roles via `Group` de Django, cambio
  de contraseña
- **Configuración base**: `settings.py` con `django-environ`, idioma
  español, zona horaria El Salvador, Bootstrap 5 vía CDN
- **Variables de entorno**: `.env.example` y `.gitignore` listos
- **Documentación**: `CLAUDE.md` con todo el contexto técnico y
  convenciones del equipo

## 🚀 Cómo usar esta plantilla

### Paso 1 — Crear un repo nuevo desde el template

1. En GitHub, ir a la página principal de este repo
2. Click en el botón verde **"Use this template"** → **"Create a new repository"**
3. Llenar:
   - Owner: tu cuenta o la organización Binary Duo
   - Repository name: nombre del nuevo proyecto (ej: `sistema-clinica`)
   - Visibilidad: privado o público según el caso
4. Click en **"Create repository"**

### Paso 2 — Clonar el nuevo repo en tu máquina

```bash
cd ~/proyectos
git clone git@github.com:TU-USUARIO/NOMBRE-DEL-NUEVO-REPO.git
cd NOMBRE-DEL-NUEVO-REPO
```

### Paso 3 — Renombrar el proyecto Django

El proyecto Django interno se llama `plantilla_django`. Hay que renombrarlo
al nombre real del proyecto.

Hay un script que hace esto automáticamente:

```bash
chmod +x scripts/renombrar_proyecto.sh
./scripts/renombrar_proyecto.sh sistema_clinica
```

⚠️ El nombre debe estar en `snake_case` (minúsculas, sin espacios,
guiones bajos en lugar de guiones medios).

El script:
- Renombra la carpeta `plantilla_django/` al nuevo nombre
- Reemplaza `plantilla_django` por el nuevo nombre en `manage.py`,
  `settings.py`, `wsgi.py`, `asgi.py` y `urls.py`
- Reemplaza también en el `README.md` y otros archivos de configuración
- Se borra a sí mismo al terminar (la plantilla ya no aplica al proyecto)

### Paso 4 — Setup del entorno

```bash
# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env

# Generar SECRET_KEY y pegarla en .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Editar .env con la nueva SECRET_KEY
nano .env

# Aplicar migraciones
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Verificar que funciona
python manage.py runserver
```

Abrir `http://127.0.0.1:8000` para verificar.

### Paso 5 — Personalizar el `CLAUDE.md`

Abrir el archivo `CLAUDE.md` y completar las secciones marcadas con
`[COMPLETAR: ...]`:

- Nombre del proyecto y descripción
- Objetivo y alcance
- Apps del negocio que se van a crear
- Equipo
- Estado inicial del proyecto
- Enlace al Notion del proyecto

### Paso 6 — Crear el espacio en Notion del proyecto

Crear una nueva sección en el Centro de Documentos Binary Duo con la
documentación extendida del proyecto. Tomar como referencia la estructura
del proyecto Sistema Drogueria si se necesita.

### Paso 7 — Primer commit

```bash
git add .
git commit -m "chore: configura proyecto desde plantilla Django Binary Duo"
git push origin main
```

## 📚 Documentación adicional

Información detallada sobre cómo usar esta plantilla y las decisiones
técnicas detrás de ella en el Centro de Documentos Binary Duo, sección
**"Plantilla Django Binary Duo"**.

## 🔄 Actualizar la plantilla

Si el equipo decide mejorar la plantilla (agregar funcionalidades, ajustar
convenciones), los cambios se hacen directamente en el repo
`plantilla_django`. Los proyectos existentes que ya nacieron de la
plantilla **no se actualizan automáticamente**: cada equipo decide si
quiere portar las mejoras manualmente.

## 👥 Mantenimiento

Equipo Binary Duo. Para sugerencias o reportes, abrir un issue en este
repositorio.
