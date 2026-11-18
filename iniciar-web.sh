#!/usr/bin/env bash
# Equivalente para Linux/macOS de iniciar-web.ps1 (+ star_web/start.ps1).
# Crea un entorno Python aislado (.venv-star-web), instala las dependencias de
# la web estelar y la inicia en http://localhost:8801 (Ctrl+C para detener).
#
# Uso:
#   ./iniciar-web.sh                 # prepara el entorno e inicia la web
#   ./iniciar-web.sh --prepare-only  # solo prepara el entorno, sin iniciar la web
set -euo pipefail

PREPARE_ONLY=0
if [ "${1:-}" = "--prepare-only" ]; then
    PREPARE_ONLY=1
fi

# Raíz del repositorio = carpeta donde está este script (funciona desde cualquier ruta).
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAR_ENV="$REPO_DIR/.venv-star-web"
STAR_PYTHON="$STAR_ENV/bin/python"
REQUIREMENTS="$REPO_DIR/star_web/requirements.txt"

# Devuelve 0 si el intérprete indicado es Python 3.11, 3.12 o 3.13.
python_soportado() {
    "$1" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)' 2>/dev/null
}

if [ ! -x "$STAR_PYTHON" ]; then
    # Preferir versiones soportadas, sin depender de Anaconda ni de una ruta fija.
    creado=0
    for candidato in python3.12 python3.13 python3.11 python3 python; do
        command -v "$candidato" >/dev/null 2>&1 || continue
        python_soportado "$candidato" || continue
        echo "Creando un entorno Python aislado para la web..."
        if "$candidato" -m venv "$STAR_ENV"; then
            creado=1
            break
        fi
        rm -rf "$STAR_ENV"
    done
    if [ "$creado" -ne 1 ]; then
        echo "Instalar Python 3.11, 3.12 o 3.13 (recomendado: 3.12), con venv y pip, y volver a ejecutar el script." >&2
        echo "En Ubuntu/Xubuntu: sudo apt install python3-venv" >&2
        exit 1
    fi
fi

if ! python_soportado "$STAR_PYTHON"; then
    echo "El entorno existente requiere Python 3.11 a 3.13. Borrar .venv-star-web y volver a ejecutar." >&2
    exit 1
fi

# Reinstalar dependencias solo si cambió requirements.txt (marca con su hash).
STAMP="$STAR_ENV/star-requirements.sha256"
HASH="$("$STAR_PYTHON" -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$REQUIREMENTS")|isolated-v2"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$HASH" ]; then
    echo "Instalando las dependencias de la web..."
    if ! "$STAR_PYTHON" -m pip install --disable-pip-version-check -r "$REQUIREMENTS"; then
        echo "No se pudieron instalar las dependencias. Revisar el acceso a PyPI." >&2
        exit 1
    fi
    printf '%s\n' "$HASH" > "$STAMP"
fi

# Si no existe .env, crearlo a partir de .env.example (valores locales de ejemplo).
if [ ! -f "$REPO_DIR/.env" ] && [ -f "$REPO_DIR/.env.example" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    echo "Se creó .env con los valores locales de ejemplo. Revisar la configuración si corresponde."
fi

if [ "$PREPARE_ONLY" -eq 1 ]; then
    echo "Entorno de la web listo."
    exit 0
fi

echo "Iniciando la web (por defecto http://localhost:8801). Ctrl+C para detener."
exec "$STAR_PYTHON" "$REPO_DIR/star_web/app.py"