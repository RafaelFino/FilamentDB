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
# Config centralizada (fonte única de verdade). Carrega config.env se existir,
# sem sobrescrever variáveis já presentes no ambiente (systemd/cron > config.env).
# ---------------------------------------------------------------------------
if [[ -f "${SCRIPT_DIR}/config.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/config.env"
    set +a
fi

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
PORT="${PORT:-5000}"
HOST="${HOST:-0.0.0.0}"
FLASK_DEBUG="${FLASK_DEBUG:-0}"
VENV_DIR="${VENV_DIR:-.venv}"
# Default absoluto (não relativo): garante o mesmo arquivo independente do cwd.
DB_PATH="${DB_PATH:-}"

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

# Resolve o DB_PATH pelo carregador central quando não veio do ambiente/config.env.
if [[ -z "$DB_PATH" ]]; then
    DB_PATH="$(python3 -c 'from src import config; print(config.get("DB_PATH"))')"
fi

# ---------------------------------------------------------------------------
# 4. Banco de dados
# ---------------------------------------------------------------------------
# Reconstrói o banco se ele estiver ausente OU inválido (sem a tabela
# principal). Só checar "arquivo existe" não basta: um filament.db vazio ou
# defasado passaria e o serviço subiria com "no such table: filament_profiles".
db_valid() {
    [[ -f "$DB_PATH" ]] || return 1
    python3 - "$DB_PATH" "$SCRIPT_DIR" <<'PY'
import hashlib, sqlite3, sys
from pathlib import Path
db_path = Path(sys.argv[1])
root = Path(sys.argv[2])
h = hashlib.sha256()
for path in sorted((root / "filament-data").glob("*.yaml")):
    h.update(path.name.encode("utf-8"))
    h.update(path.read_bytes())
expected = h.hexdigest()
try:
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(filament_profiles)").fetchall()}
    if "filament_key" not in cols:
        conn.close()
        raise SystemExit(1)
    conn.execute("SELECT 1 FROM filament_profiles LIMIT 1")
    actual = conn.execute("SELECT value FROM build_metadata WHERE key='catalog_source_hash'").fetchone()[0]
    conn.close()
    raise SystemExit(0 if actual == expected else 1)
except Exception:
    raise SystemExit(1)
PY
}

if db_valid; then
    info "Banco existente, válido e atualizado: ${DB_PATH}"
else
    info "Banco ausente, inválido ou desatualizado. Executando build (IDs existentes serão preservados)..."
    DB_PATH="$DB_PATH" python3 build.py
fi

# ---------------------------------------------------------------------------
# 4.5 Snapshots de preços (fonte: data/price-data/*.json → price-history.db)
# ---------------------------------------------------------------------------
# JSONs versionados são a fonte de verdade; o SQLite é projeção para a UI.
# O importer é idempotente: compara hash de cada arquivo e só reimporta se mudou.
info "Sincronizando snapshots de preços..."
if ! python3 scripts/import_price_data.py 2>&1 | sed 's/^/  /'; then
    error "import_price_data.py falhou. Verifique data/price-data/*.json"
fi

# ---------------------------------------------------------------------------
# 5. Servidor
# ---------------------------------------------------------------------------
info "Iniciando FilamentDB em http://${HOST}:${PORT}"
info "  (Ctrl+C para parar)"
echo ""

export FLASK_DEBUG
export DB_PATH="$DB_PATH"
export PORT="$PORT"

exec python3 -m src.app
