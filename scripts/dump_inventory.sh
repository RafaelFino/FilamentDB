#!/usr/bin/env bash
#
# dump_inventory.sh — Dump JSON lógico do estoque LENDO O BANCO DIRETO (sem API).
#
# Gera o mesmo envelope versionado de GET /api/inventory/export, mas chamando
# inventory.export_data() em processo Python — portanto NÃO depende da API/web
# estar no ar. É o par offline de backup_inventory.sh (que usa HTTP) e produz
# um arquivo restaurável por restore_inventory.sh / POST /api/inventory/import.
#
# Use este quando quiser o dump independente dos serviços (ex.: no início do
# deploy, antes de qualquer alteração, ou com o Flask parado). Use o
# backup_inventory.sh quando quiser bater na API remota de um servidor no ar.
#
# Uso:
#   ./scripts/dump_inventory.sh                         # backups/inventory-json/inventory_<ts>.json
#   ./scripts/dump_inventory.sh -o /caminho/backup.json # arquivo de saída fixo (sem rotação)
#
# Sem -o, grava em backups/inventory-json/inventory_<timestamp>.json e mantém
# os últimos MAX_JSON_BACKUPS (default 30) por rotação.
#
# Variáveis de ambiente:
#   PYTHON             Interpretador Python (default: .venv/bin/python se existir, senão python3)
#   BACKUP_DIR         Diretório-base de backups (default: <repo>/backups)
#   MAX_JSON_BACKUPS   Quantos dumps manter na rotação (default: 30)
#
# Saída: imprime o caminho do arquivo gerado na última linha (para scripts que
# queiram capturá-lo).
#
set -euo pipefail

# ── Cores ──
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*" >&2; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*" >&2; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Argumentos ──
OUTPUT=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o|--output) OUTPUT="${2:-}"; shift 2 ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) warn "Argumento ignorado: $1"; shift ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Interpretador: prefere o venv do projeto, cai no python3 do sistema.
# inventory.py só usa stdlib + src.config, então qualquer python3 serve.
if [ -n "${PYTHON:-}" ]; then
    :
elif [ -x "${REPO_DIR}/.venv/bin/python" ]; then
    PYTHON="${REPO_DIR}/.venv/bin/python"
else
    PYTHON="python3"
fi

# ── Define o arquivo de saída ──
if [ -n "$OUTPUT" ]; then
    DEST="$OUTPUT"
    mkdir -p "$(dirname "$DEST")"
else
    BACKUP_DIR="${BACKUP_DIR:-${REPO_DIR}/backups}"
    JSON_DIR="${BACKUP_DIR}/inventory-json"
    mkdir -p "$JSON_DIR"
    DEST="${JSON_DIR}/inventory_$(date '+%Y%m%d_%H%M%S').json"
fi

# ── Gera o dump lendo o banco direto (sem HTTP) ──
# O Python escreve o envelope e falha (exit!=0) se export_data() quebrar ou o
# resultado não tiver 'items'. Grava num temporário e só move se válido, para
# nunca deixar um arquivo-dump parcial/corrompido no destino.
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

COUNT=$(cd "$REPO_DIR" && "$PYTHON" - "$TMP" <<'PY'
import json, sys
sys.path.insert(0, ".")
from src import inventory

data = inventory.export_data()
if "items" not in data:
    sys.exit("export_data() não retornou 'items' — nada gravado.")
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(data.get("count", len(data["items"])))
PY
) || error "Falha ao gerar o dump do estoque via ${PYTHON}."

mv "$TMP" "$DEST"
trap - EXIT
info "Dump do estoque → ${DEST} (${COUNT} itens)"

# ── Rotação (só no modo diretório padrão) ──
if [ -z "$OUTPUT" ]; then
    MAX_JSON_BACKUPS="${MAX_JSON_BACKUPS:-30}"
    count=$(find "$JSON_DIR" -maxdepth 1 -name "inventory_*.json" -type f 2>/dev/null | wc -l)
    if [ "$count" -gt "$MAX_JSON_BACKUPS" ]; then
        find "$JSON_DIR" -maxdepth 1 -name "inventory_*.json" -type f -printf '%T+ %p\n' \
            | sort | head -n "$((count - MAX_JSON_BACKUPS))" | cut -d' ' -f2- \
            | while read -r old; do rm -f "$old"; done
        info "Rotação: mantidos os últimos ${MAX_JSON_BACKUPS} dumps."
    fi
fi

# Caminho do arquivo na última linha do stdout (para captura por outros scripts).
echo "$DEST"
