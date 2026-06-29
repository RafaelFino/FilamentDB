#!/usr/bin/env bash
# run.sh — inicializa e sobe o servidor FilamentDB
set -euo pipefail

# ---------------------------------------------------------------------------
# Cores e helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Diretório do script (permite rodar de qualquer lugar)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Configurações (podem ser sobrepostas via variáveis de ambiente)
# ---------------------------------------------------------------------------
PORT="${PORT:-5000}"
HOST="${HOST:-0.0.0.0}"
FLASK_DEBUG="${FLASK_DEBUG:-0}"
VENV_DIR="${VENV_DIR:-.venv}"
DB_PATH="${FILAMENT_DB_PATH:-filament.db}"

# ---------------------------------------------------------------------------
# 1. Verificar Python 3
# ---------------------------------------------------------------------------
info "Verificando Python 3..."
if ! command -v python3 &>/dev/null; then
    error "python3 não encontrado. Instale o Python 3.9+ e tente novamente."
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [[ "$PYTHON_MAJOR" -lt 3 ]] || { [[ "$PYTHON_MAJOR" -eq 3 ]] && [[ "$PYTHON_MINOR" -lt 9 ]]; }; then
    error "Python 3.9+ é necessário. Versão encontrada: ${PYTHON_VERSION}"
fi
info "Python ${PYTHON_VERSION} — OK"

# ---------------------------------------------------------------------------
# 2. Verificar pip
# ---------------------------------------------------------------------------
info "Verificando pip..."
if ! python3 -m pip --version &>/dev/null; then
    error "pip não encontrado. Instale com: python3 -m ensurepip --upgrade"
fi
info "pip — OK"

# ---------------------------------------------------------------------------
# 3. Criar/ativar virtualenv
# ---------------------------------------------------------------------------
if [[ ! -d "$VENV_DIR" ]]; then
    info "Criando virtualenv em ${VENV_DIR}..."
    python3 -m venv "$VENV_DIR"
fi

info "Ativando virtualenv..."
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

# ---------------------------------------------------------------------------
# 4. Instalar dependências
# ---------------------------------------------------------------------------
info "Instalando/verificando dependências (requirements.txt)..."
pip install --quiet --require-virtualenv -r requirements.txt
info "Dependências — OK"

# ---------------------------------------------------------------------------
# 5. Banco de dados
# ---------------------------------------------------------------------------
if [[ ! -f "$DB_PATH" ]]; then
    info "Banco de dados não encontrado. Criando schema..."
    FILAMENT_DB_PATH="$DB_PATH" python3 create_db.py

    info "Populando banco de dados com seed inicial..."
    FILAMENT_DB_PATH="$DB_PATH" python3 seed.py
else
    info "Banco de dados existente encontrado: ${DB_PATH}"
fi

# ---------------------------------------------------------------------------
# 6. Subir o servidor
# ---------------------------------------------------------------------------
info "Iniciando FilamentDB em http://${HOST}:${PORT}"
info "  Debug  : ${FLASK_DEBUG}"
info "  DB     : ${DB_PATH}"
info "  (Ctrl+C para parar)"
echo ""

export FLASK_DEBUG
export FILAMENT_DB_PATH="$DB_PATH"
export PORT="$PORT"

exec python3 app.py
