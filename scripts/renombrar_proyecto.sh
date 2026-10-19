#!/bin/bash
#
# renombrar_proyecto.sh
#
# Renombra el proyecto Django de "plantilla_django" al nombre indicado.
# Este script reemplaza el nombre en todos los archivos relevantes y
# renombra la carpeta del proyecto.
#
# Uso:
#   ./scripts/renombrar_proyecto.sh nuevo_nombre
#
# Ejemplo:
#   ./scripts/renombrar_proyecto.sh sistema_clinica
#
# Requisitos:
#   - El nuevo nombre debe estar en snake_case (minusculas, guiones bajos)
#   - Ejecutar desde la raiz del proyecto (donde esta manage.py)

set -e  # detener al primer error

# ============================================================================
# Validaciones iniciales
# ============================================================================

NOMBRE_VIEJO="plantilla_django"
NOMBRE_NUEVO="$1"

# Verificar que se paso un argumento
if [ -z "$NOMBRE_NUEVO" ]; then
    echo "❌ Error: debes pasar el nuevo nombre del proyecto."
    echo ""
    echo "Uso: $0 nuevo_nombre"
    echo "Ejemplo: $0 sistema_clinica"
    exit 1
fi

# Verificar que el nombre este en snake_case (solo minusculas, numeros y _)
if ! [[ "$NOMBRE_NUEVO" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "❌ Error: el nombre debe estar en snake_case."
    echo "   - Solo minusculas, numeros y guiones bajos"
    echo "   - Debe empezar con letra"
    echo ""
    echo "Recibido: '$NOMBRE_NUEVO'"
    echo "Ejemplos validos: sistema_clinica, mi_proyecto, app_inventario"
    exit 1
fi

# Verificar que estamos en la raiz del proyecto (existe manage.py)
if [ ! -f "manage.py" ]; then
    echo "❌ Error: este script debe ejecutarse desde la raiz del proyecto"
    echo "   (donde esta el archivo manage.py)"
    exit 1
fi

# Verificar que la carpeta del proyecto plantilla existe
if [ ! -d "$NOMBRE_VIEJO" ]; then
    echo "❌ Error: no se encontro la carpeta '$NOMBRE_VIEJO/'"
    echo "   ¿Ya se renombro este proyecto antes?"
    exit 1
fi

# Verificar que el nombre nuevo no es igual al viejo
if [ "$NOMBRE_VIEJO" = "$NOMBRE_NUEVO" ]; then
    echo "❌ Error: el nombre nuevo es igual al viejo. Nada que hacer."
    exit 1
fi

# ============================================================================
# Confirmacion del usuario
# ============================================================================

echo "🔄 Renombrar proyecto Django"
echo "   De: $NOMBRE_VIEJO"
echo "   A:  $NOMBRE_NUEVO"
echo ""
read -p "¿Continuar? [s/N] " confirmacion

if [[ ! "$confirmacion" =~ ^[sS]$ ]]; then
    echo "Cancelado."
    exit 0
fi

# ============================================================================
# Reemplazar contenido en archivos
# ============================================================================

echo ""
echo "📝 Reemplazando '$NOMBRE_VIEJO' por '$NOMBRE_NUEVO' en archivos..."

# Archivos donde Django mete el nombre del proyecto
ARCHIVOS=(
    "manage.py"
    "$NOMBRE_VIEJO/settings.py"
    "$NOMBRE_VIEJO/urls.py"
    "$NOMBRE_VIEJO/wsgi.py"
    "$NOMBRE_VIEJO/asgi.py"
)

# Reemplazar en cada archivo (usando sed compatible con Linux y Mac)
for archivo in "${ARCHIVOS[@]}"; do
    if [ -f "$archivo" ]; then
        # -i sin extension para Linux, vacio para Mac
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/$NOMBRE_VIEJO/$NOMBRE_NUEVO/g" "$archivo"
        else
            sed -i "s/$NOMBRE_VIEJO/$NOMBRE_NUEVO/g" "$archivo"
        fi
        echo "   ✅ $archivo"
    else
        echo "   ⚠️  $archivo no encontrado, saltando"
    fi
done

# Tambien en README.md si existe
if [ -f "README.md" ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/$NOMBRE_VIEJO/$NOMBRE_NUEVO/g" "README.md"
    else
        sed -i "s/$NOMBRE_VIEJO/$NOMBRE_NUEVO/g" "README.md"
    fi
    echo "   ✅ README.md"
fi

# ============================================================================
# Renombrar la carpeta del proyecto
# ============================================================================

echo ""
echo "📁 Renombrando carpeta del proyecto..."
mv "$NOMBRE_VIEJO" "$NOMBRE_NUEVO"
echo "   ✅ $NOMBRE_VIEJO/ → $NOMBRE_NUEVO/"

# ============================================================================
# Auto-eliminacion del script
# ============================================================================

echo ""
echo "🧹 Limpiando script de renombrado (ya no se necesita)..."
SCRIPT_PATH="$(realpath "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"

# Borrar el script
rm "$SCRIPT_PATH"

# Si la carpeta scripts queda vacia, borrarla tambien
if [ -d "$SCRIPT_DIR" ] && [ -z "$(ls -A "$SCRIPT_DIR")" ]; then
    rmdir "$SCRIPT_DIR"
    echo "   ✅ Carpeta scripts/ eliminada (estaba vacia)"
fi

# ============================================================================
# Resultado final
# ============================================================================

echo ""
echo "✅ ¡Listo! El proyecto se renombro correctamente."
echo ""
echo "Siguientes pasos:"
echo "  1. Crear el entorno virtual: python3 -m venv venv"
echo "  2. Activarlo: source venv/bin/activate"
echo "  3. Instalar dependencias: pip install -r requirements.txt"
echo "  4. Copiar variables de entorno: cp .env.example .env"
echo "  5. Generar SECRET_KEY y pegarla en .env"
echo "  6. Aplicar migraciones: python manage.py migrate"
echo "  7. Editar CLAUDE.md y completar las secciones [COMPLETAR]"
echo ""
echo "Ver README.md original o documentacion de la plantilla en Notion"
echo "para mas detalles."
