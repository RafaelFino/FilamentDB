#!/usr/bin/env bash
# run-api.sh — executa manualmente o serviço público de ingestão do FilamentDB.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f "${SCRIPT_DIR}/config.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/config.env"
    set +a
fi

VENV_DIR="${VENV_DIR:-.venv}"
HOST="${FILAMENTDB_API_HOST:-0.0.0.0}"
PORT="${FILAMENTDB_API_PORT:-5001}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "[ERROR] Virtualenv não encontrado em ${VENV_DIR}. Execute ./run.sh primeiro." >&2
    exit 1
fi

export FILAMENTDB_API_HOST="$HOST"
export FILAMENTDB_API_PORT="$PORT"

exec "${VENV_DIR}/bin/python" -m src.api_app
