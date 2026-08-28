#!/usr/bin/env bash
# run.sh — inicializa e sobe o servidor FilamentDB
set -euo pipefail

# ---------------------------------------------------------------------------
# Cores e helpers
# ---------------------------------------------------------------------------
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Diretório do script
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
PORT="${PORT:-5000}"
HOST="${HOST:-0.0.0.0}"
FLASK_DEBUG="${FLASK_DEBUG:-0}"
VENV_DIR="${VENV_DIR:-.venv}"
DB_PATH="${FILAMENT_DB_PATH:-filament.db}"

# ---------------------------------------------------------------------------
# 1. Python 3
# ---------------------------------------------------------------------------
info "Verificando Python 3..."
if ! command -v python3 &>/dev/null; then
    error "python3 nao encontrado. Instale o Python 3.9+ e tente novamente."
fi

PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [[ "$PYTHON_MAJOR" -lt 3 ]] || { [[ "$PYTHON_MAJOR" -eq 3 ]] && [[ "$PYTHON_MINOR" -lt 9 ]]; }; then
    error "Python 3.9+ necessario. Encontrado: ${PYTHON_MAJOR}.${PYTHON_MINOR}"
fi
info "Python ${PYTHON_MAJOR}.${PYTHON_MINOR} — OK"

# ---------------------------------------------------------------------------
# 2. Virtualenv
# ---------------------------------------------------------------------------
if [[ ! -d "$VENV_DIR" ]]; then
    info "Criando virtualenv em ${VENV_DIR}..."
    python3 -m venv "$VENV_DIR"
fi

info "Ativando virtualenv..."
source "${VENV_DIR}/bin/activate"

# ---------------------------------------------------------------------------
# 3. Dependências
# ---------------------------------------------------------------------------
info "Instalando dependencias..."
pip install --quiet --require-virtualenv -r requirements.txt

# ---------------------------------------------------------------------------
# 4. Banco de dados
# ---------------------------------------------------------------------------
# Reconstrói o banco se ele estiver ausente OU inválido (sem a tabela
# principal). Só checar "arquivo existe" não basta: um filament.db vazio ou
# defasado passaria e o serviço subiria com "no such table: filament_profiles".
db_valid() {
    [[ -f "$DB_PATH" ]] || return 1
    python3 -c "import sqlite3,sys; c=sqlite3.connect('$DB_PATH'); \
        c.execute('SELECT 1 FROM filament_profiles LIMIT 1'); sys.exit(0)" 2>/dev/null
}

if db_valid; then
    info "Banco existente e válido: ${DB_PATH}"
else
    info "Banco ausente ou inválido. Executando build..."
    FILAMENT_DB_PATH="$DB_PATH" python3 build.py
fi

# ---------------------------------------------------------------------------
# 5. Servidor
# ---------------------------------------------------------------------------
info "Iniciando FilamentDB em http://${HOST}:${PORT}"
info "  (Ctrl+C para parar)"
echo ""

export FLASK_DEBUG
export FILAMENT_DB_PATH="$DB_PATH"
export PORT="$PORT"

exec python3 -m src.app
